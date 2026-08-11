"""Benchmark a render on speed, smoothness, focus and artefacts.

The measurement half of the publish gate. `review_gate.py` asks Gemini whether a
clip is any good; this says what it is DOING, in numbers that are comparable
between clips and that carry a known run-to-run floor.

    python tools/analyse_render.py outputs/nyc-billboard/led/*__bc_1728x540.mp4
    python tools/analyse_render.py --json out.json <clips>

Judge the DELIVERED file. Raw and conformed differ: the retime is a real
processing step with real artefacts of its own.

WHAT IT MEASURES, and why each one exists rather than the obvious alternative
------------------------------------------------------------------------------
SPEED     median optical-flow magnitude, px/frame at delivery scale. Frame
          differencing was tried first and conflates a light change with a move;
          flow does not.

SMOOTHNESS
  lurch   flow magnitude AT keyframe crossings over the median elsewhere. 1.0
          means a keyframe looks like any other frame. This is the one that
          found `skip_boundary: 4` making the crossing a 9x step.
  jitter  median |v[i]-v[i-1]| / median v. Catches the conform retime, which
          decimates 439 frames to 300 by nearest neighbour and makes every third
          output frame a double step.
  loop    the wrap crossing in units of the median step.
  rigid   fraction of flow energy explained by a global affine fit. HIGH means
          the frame moves as one; LOW means it deforms in place, which is what
          "rubbery" looks like mechanically. Measured 2026-08-11: the two renders
          carrying a ControlNet map sit at 23-30%, the map-less Cole and Renoir
          fields at 7-11%. But `led18_casa_plaster` reaches 18.9% with NO map, so
          this is subject-dependent and is NOT a control-map detector. Read it as
          a description of how the clip moves, not as a verdict.

FOCUS     contrast-normalised FFT high-frequency ratio, per frame, on a native
          resolution crop. Reports the TROUGH as well as the mean, because the
          swing alone hides whether the floor moved: on 2026-08-11 a config
          looked like a 21% regression on swing while its softest moment was
          actually 6.8% SHARPER. Never quote the swing without the trough.
          Not comparable BETWEEN subjects, only between configs of one subject:
          it is a ratio against total spectral energy, so a high-contrast
          composition reads as less sharp than it is.

ARTEFACTS
  flicker count of frames whose step exceeds 3x the median.
  border  NOT MEASURED. Five different statistics were tried against a
          hand-labelled set of four dirty and four clean clips on 2026-08-11 and
          every one of them overlapped: high-frequency energy in the band,
          streak direction, bin-count-corrected streak direction, strongest
          vertical edge near the border, local tile detail, and per-pixel
          temporal variance. The artefact is a 55px painted canvas edge that is
          repainted every keyframe, so it drifts with the picture and is neither
          spatially nor temporally anomalous. `review_gate.py` writes native
          edge strips; a person or agent opens them. Do not add a threshold here
          without re-validating against a labelled set.

NOISE FLOORS, from re-running one config unchanged (led15_c_repro):
  lurch +-2%   focus mean +-1.3%   focus trough +-1.6%   loop +-8%
  arc swing +-0.1%   and Gemini itself +-2 on loop, +-1 elsewhere.
A difference smaller than the floor is not a result.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np

FLOW_SCALE = 4          # flow is computed at 1/4 size; 16x cheaper, same verdict
FLOW_STEP = 3           # every 3rd frame, enough to characterise a 10s drift


def probe(path: Path):
    o = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,nb_frames,r_frame_rate", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True).stdout.strip().split(",")
    ints = [int(f) for f in o if f.isdigit()]
    return ints[0], ints[1], ints[2]


def frames(path: Path, w: int, h: int, step: int = 1, limit: int | None = None):
    p = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(path), "-vf", "format=gray",
         "-f", "rawvideo", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    n, i = w * h, 0
    try:
        while True:
            b = p.stdout.read(n)
            if len(b) < n or (limit and i >= limit):
                break
            if i % step == 0:
                yield np.frombuffer(b, np.uint8).reshape(h, w)
            i += 1
    finally:
        p.stdout.close()
        p.terminate()
        p.wait()


def hf_ratio(a: np.ndarray, cutoff: float = 0.25) -> float:
    g = a.astype(np.float32)
    g = g - g.mean()
    s = g.std()
    if s < 1e-6:
        return 0.0
    F = np.fft.rfft2(g / s)
    P = F.real ** 2 + F.imag ** 2
    fy = np.fft.fftfreq(g.shape[0])[:, None] / .5
    fx = np.fft.rfftfreq(g.shape[1])[None, :] / .5
    r = np.sqrt(fy ** 2 + fx ** 2)
    t = P.sum()
    return float(P[r > cutoff].sum() / t) if t else 0.0


def focus_and_step(path: Path, w: int, h: int):
    cw, ch = min(1024, w), min(512, h)
    x0, y0 = (w - cw) // 2, (h - ch) // 2
    sharp, step, prev = [], [], None
    for f in frames(path, w, h):
        c = f[y0:y0 + ch, x0:x0 + cw].astype(np.float32)
        sharp.append(hf_ratio(c))
        d = c - c.mean()                       # remove the light arc
        if prev is not None:
            step.append(float(np.abs(d - prev).mean()))
        prev = d
    return np.array(sharp), np.array(step)


def flow_stats(path: Path, w: int, h: int):
    """Speed, and how much of the motion is a coherent global move."""
    import cv2
    sm = [cv2.resize(f, (w // FLOW_SCALE, h // FLOW_SCALE),
                     interpolation=cv2.INTER_AREA)
          for f in frames(path, w, h, step=FLOW_STEP)]
    if len(sm) < 3:
        return 0.0, 0.0
    gy, gx = np.mgrid[0:sm[0].shape[0], 0:sm[0].shape[1]].astype(np.float32)
    A = np.stack([gx.ravel(), gy.ravel(), np.ones(gx.size, np.float32)], 1)
    pinv = np.linalg.pinv(A)
    mags, rigid = [], []
    for a, b in zip(sm, sm[1:]):
        fl = cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        u, v = fl[..., 0].ravel(), fl[..., 1].ravel()
        tot = float(np.mean(u ** 2 + v ** 2))
        if tot < 1e-12:
            continue
        ru = u - A @ (pinv @ u)
        rv = v - A @ (pinv @ v)
        res = float(np.mean(ru ** 2 + rv ** 2))
        mags.append(float(np.mean(np.sqrt(u ** 2 + v ** 2))))
        rigid.append(1.0 - res / tot)
    if not mags:
        return 0.0, 0.0
    # per FLOW_STEP frames, so divide to get per-frame
    return (float(np.median(mags)) * FLOW_SCALE / FLOW_STEP,
            float(np.median(rigid)))


def analyse(path: Path, K: int) -> dict:
    w, h, _ = probe(path)
    sharp, step = focus_and_step(path, w, h)
    speed, rigid = flow_stats(path, w, h)
    n = len(sharp)
    per = n / K
    bidx = sorted({int(round(k * per)) - 1 for k in range(1, K)} & set(range(len(step))))
    mask = np.zeros(len(step), bool)
    mask[bidx] = True
    med = float(np.median(step[~mask])) or 1e-9
    folded = np.array([sharp[(np.arange(n) % per).astype(int) == i].mean()
                       for i in range(int(per))])
    return dict(
        clip=path.name, frames=n,
        speed_px=round(speed, 3),
        rigid_pct=round(100 * rigid, 1),
        lurch=round(float(step[mask].mean()) / med, 2) if mask.any() else None,
        jitter=round(float(np.median(np.abs(np.diff(step)))) / med, 2),
        loop=round(float(np.abs(sharp[-1] - sharp[0])) / max(float(np.median(np.abs(np.diff(sharp)))), 1e-9), 2),
        focus_mean=round(float(sharp.mean()), 4),
        focus_trough=round(float(folded.min()), 4),
        focus_swing_pct=round(100 * (folded.max() - folded.min()) / folded.mean(), 1),
        flicker=int((step > 3 * med).sum()),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", nargs="+")
    ap.add_argument("-K", "--keyframes", type=int, default=10,
                    help="keyframe count, to fold the curve over one RIFE pair")
    ap.add_argument("--json")
    a = ap.parse_args()
    rows = []
    hdr = (f"{'clip':<34} {'speed':>6} {'rigid%':>7} {'lurch':>6} {'jit':>5} "
           f"{'flick':>6} {'focus':>7} {'TROUGH':>8} {'swing%':>7}")
    print(hdr)
    print("-" * len(hdr))
    for v in a.videos:
        p = Path(v)
        if not p.exists():
            print(f"{p.name:<34} MISSING")
            continue
        r = analyse(p, a.keyframes)
        rows.append(r)
        name = r["clip"].replace("__bc_1728x540.mp4", "").replace(".mp4", "")
        print(f"{name:<34} {r['speed_px']:6.3f} {r['rigid_pct']:7.1f} "
              f"{str(r['lurch']):>6} {r['jitter']:5.2f} {r['flicker']:6d} "
              f"{r['focus_mean']:7.4f} {r['focus_trough']:8.4f} {r['focus_swing_pct']:7.1f}")
    print("\nfloors: lurch +-2%  focus +-1.3%  trough +-1.6%  loop +-8%. "
          "Border is NOT measured here, open the edge strips.")
    if a.json:
        Path(a.json).write_text(json.dumps(rows, indent=1), encoding="utf-8")
        print(f"wrote {a.json}")


if __name__ == "__main__":
    main()
