"""Inject a KNOWN artefact at a KNOWN amplitude, to give detectors real ground truth.

Why this exists. On 2026-08-11 five statistics were invented for the painted canvas
edge and three for rubbery morphing, and every one of them was eyeballed against a
handful of clips and shipped or discarded on that basis. All eight failed. The fault
was method: each was fitted to ONE noisy judgement per clip, across clips that also
differed in backbone, subject, palette and schedule, so there was no way to tell a
detector from a coincidence.

This manufactures the missing ground truth. Take a clip that is already clean, add one
artefact at a stated amplitude, and you know exactly what is in the result and how much
of it. That converts "does this threshold look about right" into a sensitivity curve:
is the detector monotonic in amplitude, what is the smallest amplitude it can see, and
how often does it fire on clean input.

    python tools/artefact_sim.py --list
    python tools/artefact_sim.py --src clean.mp4 --artefact canvas_edge --amp 48
    python tools/artefact_sim.py --src clean.mp4 --artefact morph --sweep

TWO RULES that make the output usable as evidence:

1. **amp=0 is an exact no-op** at the array level, asserted in tests. Every injector
   returns its input unchanged at zero amplitude, so a control differs from a positive
   by the injection and nothing else.
2. **Always compare a positive against the amp=0 RE-ENCODE, never against the original
   file.** Re-encoding is lossy, so the original carries different codec noise from
   everything this writes. The sweep emits the amp=0 control for exactly this reason.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CRF = "12"          # near-transparent; the amp=0 control carries the same noise

# Amplitude sweeps. Chosen to straddle what has actually been seen in real renders:
# the observed canvas edge is a ~55px band, real judder came from a 1.463 ratio.
SWEEPS = {
    "canvas_edge": [0, 16, 32, 48, 64, 96],
    "morph": [0, 0.2, 0.5, 1.0, 2.0, 4.0],
    "blur": [0, 0.5, 1.0, 2.0, 3.0, 4.0],
    "decimate": [1.0, 1.03, 1.10, 1.25, 1.46, 1.63],
    "lurch": [0, 1, 2, 4, 6, 8],
    "flicker": [0, 0.005, 0.01, 0.02, 0.035, 0.05],
}

DESCRIPTIONS = {
    "canvas_edge": "band of horizontally-smeared, contrast-reduced content down both "
                   "sides, as the Renoir and Soutine LoRAs paint. amp = band width px",
    "morph": "smooth low-frequency displacement field that decorrelates over time, "
             "i.e. deformation in place rather than a coherent move. amp = peak px",
    "blur": "gaussian blur under a raised-cosine time envelope, the mid-pair "
            "sharpness trough. amp = peak sigma",
    "decimate": "nearest-neighbour resample at a non-integer ratio, exactly what "
                "conform.py does going 439 frames to 300. amp = ratio, 1.0 is clean",
    "lurch": "drop k frames at each keyframe boundary, the skip_boundary jump. amp = k",
    "flicker": "per-frame luminance gain jitter. amp = gain std",
}


def probe(path: Path) -> tuple[int, int, int, float]:
    o = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,nb_frames,r_frame_rate", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True).stdout.strip().split(",")
    rate = next(f for f in o if "/" in f)
    num, den = rate.split("/")
    ints = [int(f) for f in o if f.isdigit()]
    return ints[0], ints[1], ints[2], float(num) / float(den)


def read_frames(path: Path, w: int, h: int, limit: int | None = None):
    p = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo",
         "-pix_fmt", "bgr24", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    n, i = w * h * 3, 0
    try:
        while True:
            b = p.stdout.read(n)
            if len(b) < n or (limit is not None and i >= limit):
                break
            yield np.frombuffer(b, np.uint8).reshape(h, w, 3)
            i += 1
    finally:
        p.stdout.close()
        p.terminate()
        p.wait()


class Writer:
    def __init__(self, path: Path, w: int, h: int, fps: float):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.p = subprocess.Popen(
            ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
             "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", CRF,
             "-pix_fmt", "yuv420p", "-an", str(path)],
            stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def write(self, f: np.ndarray):
        self.p.stdin.write(np.ascontiguousarray(f, dtype=np.uint8).tobytes())

    def close(self):
        self.p.stdin.close()
        self.p.wait()


# ---------------------------------------------------------------- spatial injectors
# Each takes (frame, amp, ctx) and returns a frame. amp=0 MUST return the input
# unchanged, and unchanged means `is` or array-equal, not "visually the same":
# cv2.remap with an identity map still resamples and would defeat the control.

def inject_canvas_edge(f: np.ndarray, amp: float, ctx: dict) -> np.ndarray:
    band = int(round(amp))
    if band <= 0:
        return f
    h, w = f.shape[:2]
    out = f.copy()
    for side in ("L", "R"):
        # take the strip just INSIDE the band and smear it horizontally, so the band
        # is made of the picture's own colours, as a real painted edge is
        if side == "L":
            src = f[:, band:band * 3] if band * 3 < w else f[:, band:band + 8]
        else:
            src = f[:, w - band * 3:w - band] if band * 3 < w else f[:, w - band - 8:w - band]
        if src.shape[1] < 2:
            continue
        smear = cv2.resize(src, (band, h), interpolation=cv2.INTER_LINEAR)
        k = max(3, (band // 2) * 2 + 1)
        smear = cv2.GaussianBlur(smear, (k, 1), 0)          # horizontal smear only
        m = smear.reshape(-1, 3).mean(axis=0)
        smear = (smear.astype(np.float32) * 0.45 + m * 0.55).astype(np.uint8)
        if side == "L":
            out[:, :band] = smear
        else:
            out[:, w - band:] = smear
    return out


def inject_morph(f: np.ndarray, amp: float, ctx: dict) -> np.ndarray:
    if amp <= 0:
        return f
    h, w = f.shape[:2]
    fld = ctx["field"]                    # (2, gh, gw) already time-interpolated
    dx = cv2.resize(fld[0], (w, h), interpolation=cv2.INTER_CUBIC) * amp
    dy = cv2.resize(fld[1], (w, h), interpolation=cv2.INTER_CUBIC) * amp
    gx, gy = ctx["grid"]
    return cv2.remap(f, (gx + dx).astype(np.float32), (gy + dy).astype(np.float32),
                     cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def inject_blur(f: np.ndarray, amp: float, ctx: dict) -> np.ndarray:
    s = amp * ctx["envelope"]
    if s <= 0.01:
        return f
    k = int(s * 4) | 1
    return cv2.GaussianBlur(f, (k, k), s)


def inject_flicker(f: np.ndarray, amp: float, ctx: dict) -> np.ndarray:
    if amp <= 0:
        return f
    return np.clip(f.astype(np.float32) * ctx["gain"], 0, 255).astype(np.uint8)


SPATIAL = {"canvas_edge": inject_canvas_edge, "morph": inject_morph,
           "blur": inject_blur, "flicker": inject_flicker}


# --------------------------------------------------------------- temporal injectors
# These choose WHICH source frame lands at each output index. amp=0 (or ratio 1.0)
# yields the identity mapping.

def index_map(artefact: str, amp: float, n: int, K: int) -> list[int]:
    if artefact == "decimate":
        r = float(amp) if amp else 1.0
        if r <= 1.0:
            return list(range(n))
        return [min(n - 1, int(round(i * r))) for i in range(int((n - 1) / r) + 1)]
    if artefact == "lurch":
        k = int(round(amp))
        if k <= 0:
            return list(range(n))
        drop = set()
        for b in range(1, K):
            at = int(round(b * n / K))
            drop.update(range(at, min(n, at + k)))
        return [i for i in range(n) if i not in drop]
    return list(range(n))


def build_context(artefact: str, n: int, w: int, h: int, seed: int = 1087) -> dict:
    """Precompute anything an injector needs that depends on the whole clip."""
    ctx: dict = {}
    if artefact == "morph":
        rng = np.random.default_rng(seed)
        gh, gw = 6, 12
        # a new random field every ~15 frames, lerped between: smooth in space,
        # decorrelating in time, which is what "boiling" is
        anchors = rng.standard_normal((n // 15 + 2, 2, gh, gw)).astype(np.float32)
        ctx["anchors"] = anchors
        ctx["grid"] = np.meshgrid(np.arange(w, dtype=np.float32),
                                  np.arange(h, dtype=np.float32))
    if artefact == "flicker":
        rng = np.random.default_rng(seed + 1)
        ctx["gains"] = 1.0 + rng.standard_normal(n).astype(np.float32)
    return ctx


def per_frame_context(artefact: str, ctx: dict, i: int, n: int, amp: float) -> dict:
    if artefact == "morph":
        t = i / 15.0
        a, b = int(t), min(int(t) + 1, len(ctx["anchors"]) - 1)
        u = t - int(t)
        ctx["field"] = ctx["anchors"][a] * (1 - u) + ctx["anchors"][b] * u
    if artefact == "blur":
        # raised cosine centred at mid-loop, zero at both ends so the loop still closes
        ctx["envelope"] = 0.5 - 0.5 * np.cos(2 * np.pi * i / max(n - 1, 1))
    if artefact == "flicker":
        ctx["gain"] = 1.0 + (ctx["gains"][i] - 1.0) * amp / 1.0
    return ctx


def inject(src: Path, artefact: str, amp: float, out: Path,
           limit: int | None = None, K: int = 10) -> Path:
    w, h, n, fps = probe(src)
    if limit:
        n = min(n, limit)
    frames = list(read_frames(src, w, h, limit=n))
    n = len(frames)
    ctx = build_context(artefact, n, w, h)
    idx = index_map(artefact, amp, n, K)
    fn = SPATIAL.get(artefact)
    wr = Writer(out, w, h, fps)
    for oi, si in enumerate(idx):
        f = frames[si]
        if fn is not None:
            ctx = per_frame_context(artefact, ctx, si, n, amp)
            f = fn(f, amp, ctx)
        wr.write(f)
    wr.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src")
    ap.add_argument("--artefact", choices=sorted(SWEEPS))
    ap.add_argument("--amp", type=float)
    ap.add_argument("--out")
    ap.add_argument("--sweep", action="store_true", help="emit the whole amplitude ladder")
    ap.add_argument("--dest", default="outputs/_bench")
    ap.add_argument("--limit", type=int, default=150, help="frames, keeps the bench cheap")
    ap.add_argument("-K", "--keyframes", type=int, default=10)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    if a.list or not a.src:
        print("artefact      amplitude ladder")
        print("-" * 78)
        for k, v in SWEEPS.items():
            print(f"{k:<13} {v}")
            print(f"{'':<13} {DESCRIPTIONS[k]}")
        return

    src = Path(a.src)
    stem = src.stem.replace("__bc_1728x540", "")
    dest = ROOT / a.dest
    amps = SWEEPS[a.artefact] if a.sweep else [a.amp]
    for amp in amps:
        name = f"{stem}__{a.artefact}__{str(amp).replace('.', 'p')}.mp4"
        out = Path(a.out) if (a.out and not a.sweep) else dest / name
        inject(src, a.artefact, float(amp), out, limit=a.limit, K=a.keyframes)
        shown = out if not out.is_absolute() else out.relative_to(ROOT)
        print(f"  {a.artefact:<12} amp={amp:<6} -> {shown}")


if __name__ == "__main__":
    main()
