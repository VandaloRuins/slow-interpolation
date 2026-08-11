"""DEPRECATED 2026-08-11. Use `tools/analyse_render.py`, which supersedes this.

Its per-frame delta cannot separate a light change from a movement, and this
pipeline's whole subject is a light change. The replacement measures optical
flow, and adds the keyframe-crossing lurch and decimation jitter that a
single delta curve averages away.

This still runs, and is kept because three skills and two docs reference it. Do
not build on it.

Per-frame motion profile of a render. Finds speed spikes and broken loops.

Why this exists: `analyse_ladder.py` samples 9 frames across 384 and reports a
`loop` ratio from them. That can never see a single-frame discontinuity, so it
reported healthy loops on clips a human immediately saw breaking. This decodes
EVERY frame and measures the actual per-frame delta, including the wrap.

    python tools/motion_profile.py outputs/course-of-empire/coe_desolation.mp4

Reports:
  mean/p50/p95   per-frame delta. The spread is the real "is the speed even"
                 answer; a smooth drift has p95 close to p50.
  peak           the largest single-frame jump and WHERE it is. On a chained
                 render the usual culprit is the RIFE wrap pair, which has to
                 bridge the whole chain's accumulated drift in one segment.
  wrap           delta from the last frame back to the first, as a multiple of
                 the median. 1.0 means the loop point is indistinguishable from
                 any other frame. Above ~2 a viewer sees it.
  spikes         every frame whose delta exceeds 2x the median, which is what
                 reads as a fast blur transition.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np

W, H = 336, 192  # decode small; we are measuring motion, not texture


def frames(video: Path) -> np.ndarray:
    """Every frame, greyscale, downscaled, as (N, H, W) float32."""
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video),
         "-vf", f"scale={W}:{H},format=gray", "-f", "rawvideo", "-"],
        capture_output=True)
    buf = np.frombuffer(r.stdout, dtype=np.uint8)
    n = buf.size // (W * H)
    return buf[: n * W * H].reshape(n, H, W).astype(np.float32)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", nargs="+", type=Path)
    ap.add_argument("--spike-factor", type=float, default=2.0)
    args = ap.parse_args()

    # NOTE: report `wrap_abs` alongside `wrap`. The ratio is normalised by the
    # median, so a variant that slows the whole clip down reports a WORSE ratio
    # for an unchanged wrap gap. Comparing variants that differ in speed needs
    # the absolute number, otherwise you will reject the fix that worked.
    print(f"{'clip':30} {'n':>4} {'p50':>7} {'p95':>7} {'peak':>7} {'peak@':>6} "
          f"{'wrap':>6} {'wrapAbs':>8} {'spikes':>7}")
    print("-" * 96)

    for v in args.videos:
        a = frames(v)
        if len(a) < 3:
            print(f"{v.stem:30} UNREADABLE")
            continue
        d = np.abs(np.diff(a, axis=0)).mean(axis=(1, 2))       # consecutive
        wrap = float(np.abs(a[0] - a[-1]).mean())              # last -> first
        p50 = float(np.median(d))
        spikes = np.flatnonzero(d > args.spike_factor * p50)
        peak_i = int(np.argmax(d))
        print(f"{v.stem:30} {len(a):>4} {p50:>7.3f} {float(np.percentile(d,95)):>7.3f} "
              f"{float(d.max()):>7.3f} {peak_i:>6} {wrap/max(p50,1e-6):>6.2f} "
              f"{wrap:>8.3f} {len(spikes):>7}")
        if len(spikes):
            # Group contiguous spike runs so the report names events, not frames.
            runs, start = [], spikes[0]
            for i in range(1, len(spikes)):
                if spikes[i] != spikes[i - 1] + 1:
                    runs.append((start, spikes[i - 1])); start = spikes[i]
            runs.append((start, spikes[-1]))
            for s, e in runs[:6]:
                worst = d[s:e + 1].max() / p50
                print(f"{'':32}spike frames {s}-{e} ({s/30:.2f}s), {worst:.1f}x median")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
