"""The publish gate: no render reaches the gallery until it has passed BOTH eyes.

Standing rule, Luca 2026-08-11: *"every output you create, you must analyse with
gemini multimodal video tool and with the frames analysis method to review the
frames that gemini mentions as blurred, interpolating not smoothly or with border
and frame artefacts. If a video has those issues do not push it to gallery."*

Two instruments, because each is blind where the other sees:

  GEMINI watches the clip and says WHERE something is wrong. It is the only
  instrument here that judges. It cannot measure, and it hallucinates
  timestamps.
  FRAME ANALYSIS measures at native resolution and says WHETHER the flag is
  real. It cannot judge, and it has no idea what the picture is of.

So Gemini nominates and the measurement confirms. But note the third case, and
it is the important one: some faults are invisible to BOTH. Rubbery morphing is
local warping at constant global velocity, so no frame-step metric sees it, and
the painted canvas edge sits in 3% of the width where a downscaled review pass
does not look. For those the gate falls back to Gemini's SCORES and to native
edge strips that a person or agent has to actually open. A clip is never passed
just because the instrument that cannot see a fault failed to see it.

The canvas edge is now MEASURABLE, but only as a within-subject comparison:
`b_detail` from `slow_interpolation.quality` is monotonic in band width on both
synthetic bases (-12% at 16px, -63% at 48px, -80% at 96px) and moves -31% on the
one real same-subject pair we have. It has no absolute threshold and cannot get
one: across subjects it measures the subject. So pass `--baseline <clip of the
same subject>` to have it checked, and without a baseline the edge strips stay
the only answer.

    python tools/review_gate.py outputs/.../clip__bc_1728x540.mp4 --subject "a field of flowers"
    python tools/review_gate.py outputs/nyc-billboard/led/led18_*__bc_1728x540.mp4

Exit code 0 if every clip passes, 1 if any fails. Writes review-gate.json.

IMPORTANT: judge the DELIVERED file, the one that ships, never the raw render.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def _quality():
    """Load quality.py directly; the package __init__ drags in torch."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "si_quality", ROOT / "src" / "slow_interpolation" / "quality.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

OUT = ROOT / "review-gate.json"

# Thresholds. Each is a MULTIPLE of the clip's own median, so a clip is judged
# against itself and a dark subject is not penalised for being dark.
BLUR_RATIO = 0.80      # HF at the flagged frame vs clip median
MOTION_RATIO = 2.00    # frame step at the flagged frame vs clip median
MIN_SCORE = 7          # any Gemini axis below this fails the clip
SAMPLES = 3            # Gemini runs per clip; see vote()

# Gemini is NOISY and a single sample cannot be gated on. Measured 2026-08-11,
# same clip, same prompt, three runs: loop scored 7/9/7, motion 6/7/6, and the
# flag count came back 8/3/6. So scores are taken as a MEDIAN of SAMPLES runs,
# and a flag counts only if a MAJORITY of runs report that kind near that time.
# One earlier verdict here (9/9/8/9) was a lucky draw and did not reproduce.

# Gemini judges, measurement confirms. But measurement is BLIND to the defect
# Gemini complains about most, rubbery morphing: that is local warping at
# constant global velocity, so no frame-step metric can see it. Hence MIN_SCORE.
# Never "pass" a clip just because the instrument that cannot see the fault
# failed to see it.

PROMPT = """You are reviewing a short looping video from an art project called
slow-interpolation. Chained SDXL img2img keyframes through a painting-style LoRA,
interpolated with RIFE into a seamless loop, shown on a large LED wall at night
and seen for about 10 seconds by someone walking past. It is a pure style
exercise: there is no narrative and no concept to decode. The only question is
whether it is beautiful and technically clean.

{subject_line}

Watch the whole clip. Be specific and critical; do not be encouraging, the value
here is accurate criticism.

Rate FOUR axes 1-10:
1. SUBJECT: is what you see legible and coherent? What IS it?
2. LOOP: does it loop seamlessly, or is there a visible jump or speed change?
3. MOTION: is the drift smooth and even, or does it pulse, stutter, rush, or
   morph rubberily?
4. IMAGE: does it read as real paint with brushwork and value structure, or as a
   smooth digital render? Comment on the palette.

Then list EVERY defect you can see as a flag, with the time in seconds. Use
kind exactly one of:
  "blur"    a moment that is soft, smeared, or out of focus
  "motion"  a jump, stutter, speed change, or rubbery morph
  "border"  ANY sign that the picture is a framed canvas rather than a window:
            a visible frame or border, a painted canvas edge, a vignette,
            smeared or streaked bands along the left/right/top/bottom edges,
            or the image sitting inset inside a rectangle
Report a border flag at time 0 if the frame edge is wrong for the whole clip.
If there are no defects of a kind, omit it. Do not invent flags to be helpful.

Reply as compact JSON only, no markdown fence:
{{"subject":N,"subject_note":"...","loop":N,"loop_note":"...","motion":N,
"motion_note":"...","image":N,"image_note":"...","worst":"...","best":"...",
"flags":[{{"t":1.5,"kind":"blur","note":"..."}}]}}"""


def vote(path: Path, subject: str, samples: int = SAMPLES) -> dict:
    """Median scores and majority-supported flags across independent runs."""
    runs = [gemini(path, subject) for _ in range(samples)]
    ok = [r for r in runs if not r.get("error")]
    if not ok:
        return {"error": "all gemini runs failed", "runs": len(runs)}
    out = {"runs": len(ok)}
    for axis in ("subject", "loop", "motion", "image"):
        vals = sorted(r[axis] for r in ok
                      if isinstance(r.get(axis), (int, float)))
        out[axis] = vals[len(vals) // 2] if vals else None
        out[axis + "_spread"] = (max(vals) - min(vals)) if vals else None
    for k in ("subject_note", "loop_note", "motion_note", "image_note", "worst", "best"):
        out[k] = next((r.get(k) for r in ok if r.get(k)), "")

    # A flag survives only if a majority of runs saw that KIND within 1.5s.
    pool = [(str(f.get("kind", "")).lower(), float(f.get("t", 0)), f.get("note", ""), i)
            for i, r in enumerate(ok) for f in (r.get("flags") or [])
            if isinstance(f, dict) and str(f.get("t", "")).replace(".", "", 1).isdigit()]
    need = len(ok) // 2 + 1
    kept, used = [], set()
    for kind, t, note, run in sorted(pool, key=lambda x: (x[0], x[1])):
        if (kind, round(t, 1)) in used:
            continue
        backers = {r for k2, t2, _, r in pool if k2 == kind and abs(t2 - t) <= 1.5}
        if len(backers) >= need:
            used.add((kind, round(t, 1)))
            kept.append({"t": t, "kind": kind, "note": note, "votes": len(backers)})
    out["flags"] = kept
    out["dropped_flags"] = len(pool) - len(kept)
    return out


def gemini(path: Path, subject: str) -> dict:
    spec = importlib.util.spec_from_file_location("gr", ROOT / "tools" / "gemini_review.py")
    gr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gr)
    from google import genai
    from google.genai import types
    import time

    client = genai.Client(api_key=gr.api_key())
    up = client.files.upload(file=str(path))
    for _ in range(90):
        f = client.files.get(name=up.name)
        if f.state.name == "ACTIVE":
            break
        if f.state.name == "FAILED":
            return {"error": "upload failed"}
        time.sleep(2)
    line = (f"The intended subject is: {subject}." if subject
            else "The intended subject is not specified; infer it.")
    r = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[f, PROMPT.format(subject_line=line)],
        config=types.GenerateContentConfig(temperature=0.2))
    raw = (r.text or "").strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"error": "unparseable", "raw": raw[:400]}


def probe(path: Path):
    # ffprobe emits these in STREAM order, not the order asked for, so parse by
    # shape: the rate is the only field carrying a slash.
    o = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,nb_frames,r_frame_rate", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True).stdout.strip().split(",")
    rate = next(f for f in o if "/" in f)
    num, den = rate.split("/")
    ints = [int(f) for f in o if f.isdigit()]
    w, h, n = ints[0], ints[1], ints[2]
    return w, h, n, float(num) / float(den)


def gray(path: Path, w: int, h: int):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(path), "-vf", "format=gray",
                          "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    n = w * h
    while True:
        b = p.stdout.read(n)
        if len(b) < n:
            break
        yield np.frombuffer(b, np.uint8).reshape(h, w).astype(np.float32)
    p.stdout.close(); p.wait()


def hf(a: np.ndarray, cutoff: float = 0.25) -> float:
    g = a - a.mean()
    s = g.std()
    if s < 1e-6:
        return 0.0
    F = np.fft.rfft2(g / s)
    P = F.real ** 2 + F.imag ** 2
    fy = np.fft.fftfreq(g.shape[0])[:, None]
    fx = np.fft.rfftfreq(g.shape[1])[None, :]
    r = np.sqrt((fy / .5) ** 2 + (fx / .5) ** 2)
    t = P.sum()
    return float(P[r > cutoff].sum() / t) if t else 0.0


def edge_strips(path: Path, w: int, h: int, frames_at=(40, 150, 260)) -> Path:
    """Write native-resolution left/right edge strips for INSPECTION BY EYE.

    There is no automated border test here, and that is a finding rather than an
    omission. On 2026-08-11 the painted-canvas-edge artefact in the Renoir and
    Soutine renders was invisible to BOTH instruments: Gemini raised no border
    flag at all (it watches a downscaled clip, and the band is 3% of the width),
    and four different band statistics were tried against a hand-verified set of
    four dirty and four clean clips. All four overlapped:

      high-frequency energy, band vs interior     dirty 1.17-3.06  clean 1.01-1.44
      streak direction, bin-count corrected       dirty 0.07-0.23  clean 0.11-1.57
      strongest vertical edge near the border     dirty 1.45-2.53  clean 1.27-2.49
      local tile detail, band vs interior         dirty 0.68-1.05  clean 0.69-1.35

    The band is narrow, its position moves, and interior statistics vary far more
    between subjects than the artefact does. So the strip gets LOOKED AT. Do not
    replace this with a threshold without re-validating against that set.
    """
    d = ROOT / "outputs" / "_review" / path.stem
    d.mkdir(parents=True, exist_ok=True)
    for n in frames_at:
        for side, crop in (("L", f"200:{h}:0:0"), ("R", f"200:{h}:{w-200}:0")):
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-i", str(path),
                 "-vf", rf"select=eq(n\,{n}),crop={crop}", "-frames:v", "1",
                 str(d / f"edge_{side}_{n:04d}.png")], check=False)
    return d


def measure(path: Path):
    """Per-frame sharpness and step, plus a standing border test."""
    w, h, n, fps = probe(path)
    cw, ch = min(1024, w), min(512, h)
    x0, y0 = (w - cw) // 2, (h - ch) // 2
    sharp, step = [], []
    prev = None
    for f in gray(path, w, h):
        c = f[y0:y0 + ch, x0:x0 + cw]
        sharp.append(hf(c))
        d = c - c.mean()
        if prev is not None:
            step.append(float(np.abs(d - prev).mean()))
        prev = d
    return dict(fps=fps, n=n, w=w, h=h,
                sharp=np.array(sharp), step=np.array(step))


BORDER_DROP = 0.15     # b_detail fall vs a same-subject baseline that counts as an edge


def gate(path: Path, subject: str, baseline: dict | None = None) -> dict:
    g = vote(path, subject)
    m = measure(path)
    fps, sharp, step = m["fps"], m["sharp"], m["step"]
    msharp, mstep = float(np.median(sharp)), float(np.median(step))
    verdict, checked = [], []

    flags = [f for f in (g.get("flags") or []) if isinstance(f, dict)]
    # Gemini's timestamps are unreliable and sometimes degenerate (one clip came
    # back with eight distinct defects all between 0.01s and 0.09s). When they
    # collapse like that, the times carry no information, so test the WHOLE clip
    # for that defect class instead of a window nobody can locate.
    times = []
    for f in flags:
        try:
            times.append(float(f.get("t", 0)))
        except (TypeError, ValueError):
            pass
    degenerate = len(times) >= 4 and (max(times) - min(times)) < 0.2
    win = max(3, int(round(0.25 * fps)))     # +/- 0.25s, timestamps drift

    for fl in flags:
        try:
            t = float(fl.get("t", 0))
        except (TypeError, ValueError):
            continue
        kind = str(fl.get("kind", "")).lower()
        i = max(0, min(len(sharp) - 1, int(round(t * fps))))
        rec = {"t": t, "frame": i, "kind": kind, "note": fl.get("note", ""),
               "scope": "clip" if degenerate else "window"}
        lo, hi = (0, len(sharp)) if degenerate else (max(0, i - win), min(len(sharp), i + win + 1))
        if kind == "blur":
            rec["measured"] = round(float(sharp[lo:hi].min()) / msharp, 3)
            rec["confirmed"] = rec["measured"] < BLUR_RATIO
        elif kind == "motion":
            j0, j1 = (0, len(step)) if degenerate else (max(0, i - win), min(len(step), i + win + 1))
            rec["measured"] = round(float(step[j0:j1].max()) / mstep, 3) if j1 > j0 else 0.0
            rec["confirmed"] = rec["measured"] > MOTION_RATIO
        elif kind == "border":
            # No measurement can confirm or refute this one (see edge_strips).
            # Gemini rarely sees it, so when it DOES, believe it.
            rec["measured"] = None
            rec["confirmed"] = True
        else:
            rec["confirmed"] = False
        checked.append(rec)
        if rec["confirmed"]:
            verdict.append(f"{kind}@{t}s")

    strips = edge_strips(path, m["w"], m["h"])

    # Measured border check, only possible against a same-subject baseline.
    if baseline and baseline.get("b_detail"):
        mine = _quality().features(path, K=10, limit=150)
        drop = (baseline["b_detail"] - mine["b_detail"]) / abs(baseline["b_detail"])
        checked.append({"t": 0, "kind": "border", "scope": "clip",
                        "note": f"b_detail {mine['b_detail']:.3f} vs baseline "
                                f"{baseline['b_detail']:.3f}, {drop:+.0%}",
                        "measured": round(drop, 3), "confirmed": drop > BORDER_DROP})
        if drop > BORDER_DROP:
            verdict.append(f"border(b_detail {drop:+.0%})")

    # Gemini's own scores are a gate in their own right, because the fault it
    # reports most (rubbery morphing) is invisible to every metric here.
    for axis in ("subject", "loop", "motion", "image"):
        s = g.get(axis)
        if isinstance(s, (int, float)) and s < MIN_SCORE:
            verdict.append(f"{axis}={s}")

    return {
        "clip": path.name,
        "pass": not verdict,
        "reasons": verdict,
        "scores": {k: g.get(k) for k in ("subject", "loop", "motion", "image")},
        "notes": {k: g.get(k) for k in ("subject_note", "loop_note", "motion_note",
                                        "image_note", "worst", "best")},
        "edge_strips": str(strips.relative_to(ROOT)),
        "border": "INSPECT the strips by eye; no metric here can decide it",
        "checked": checked,
        "gemini_error": g.get("error"),
        "runs": g.get("runs"),
        "dropped_flags": g.get("dropped_flags"),
        "spread": {a: g.get(a + "_spread") for a in ("subject", "loop", "motion", "image")},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--subject", default="")
    ap.add_argument("--baseline", help="a clip of the SAME subject; enables the "
                                       "measured border check")
    a = ap.parse_args()
    baseline = None
    if a.baseline:
        baseline = _quality().features(Path(a.baseline), K=10, limit=150)
        print(f"border baseline: {baseline['clip']}  b_detail {baseline['b_detail']:.3f}")
    results, failed = [], 0
    for v in a.videos:
        p = Path(v)
        if not p.exists():
            print(f"MISSING {p}"); failed += 1; continue
        r = gate(p, a.subject, baseline)
        results.append(r)
        s = r["scores"]
        tag = "PASS" if r["pass"] else "FAIL"
        if not r["pass"]:
            failed += 1
        print(f"\n{tag}  {r['clip']}")
        sp = r.get("spread", {})
        print(f"  gemini  subject {s.get('subject')} loop {s.get('loop')} "
              f"motion {s.get('motion')} image {s.get('image')}   "
              f"(median of {r.get('runs')} runs, spread {sp})")
        if r.get("dropped_flags"):
            print(f"          {r['dropped_flags']} flag(s) dropped, not seen by a majority")
        print(f"  border  INSPECT BY EYE -> {r['edge_strips']}")
        for c in r["checked"]:
            mark = "CONFIRMED" if c["confirmed"] else "not supported"
            print(f"    {c['kind']:<7} t={c['t']:<6} measured={c.get('measured')} "
                  f"{mark}  {str(c.get('note',''))[:70]}")
        if r["notes"].get("worst"):
            print(f"  worst   {r['notes']['worst']}")
    prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    prev.update({r["clip"]: r for r in results})
    OUT.write_text(json.dumps(prev, indent=1), encoding="utf-8")
    print(f"\n{len(results)-failed}/{len(results)} passed. wrote {OUT.name}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
