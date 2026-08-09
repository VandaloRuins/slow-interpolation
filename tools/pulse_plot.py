"""Draw the sharpness-over-time curve of a render, so the blur pulse is visible.

Frame-average sharpness hides the thing a viewer actually notices: sharpness
rises at every keyframe and falls between them, so the image breathes in and out
of focus. A single number per clip averages that away completely. This plots it.

    python tools/pulse_plot.py outputs/empire/empire_v6_sharp.mp4 outputs/empire/empire_v7_flat.mp4

Writes a PNG into outputs/_analysis/, which means it shows up in the gallery as a
stills card and can be read on a phone.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
W, H = 448, 256


def sharpness(video: Path) -> np.ndarray:
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video),
         "-vf", f"scale={W}:{H},format=gray", "-f", "rawvideo", "-"],
        capture_output=True)
    a = np.frombuffer(r.stdout, dtype=np.uint8)
    n = a.size // (W * H)
    if n == 0:
        return np.array([])
    a = a[: n * W * H].reshape(n, H, W).astype(np.float32)
    lap = (a[:, :-2, 1:-1] + a[:, 1:-1, :-2] - 4 * a[:, 1:-1, 1:-1]
           + a[:, 1:-1, 2:] + a[:, 2:, 1:-1])
    return lap.reshape(n, -1).var(axis=1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", nargs="+", type=Path)
    ap.add_argument("--seconds", type=float, default=8.0, help="window to plot")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--start", type=float, default=40.0, help="offset into the clip")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "outputs" / "_analysis" / "sharpness_pulse.png")
    args = ap.parse_args()

    series = []
    for v in args.videos:
        s = sharpness(v)
        if s.size:
            series.append((v.stem, s))
        else:
            print(f"unreadable: {v}", file=sys.stderr)
    if not series:
        return 1

    PW, PH, PAD = 1240, 170, 54
    img = Image.new("RGB", (PW + PAD * 2, (PH + 46) * len(series) + 40), (18, 16, 14))
    d = ImageDraw.Draw(img)
    n = int(args.seconds * args.fps)
    off = int(args.start * args.fps)

    for i, (name, s) in enumerate(series):
        seg = s[off:off + n] if off + n <= len(s) else s[:n]
        y0 = 30 + i * (PH + 46)
        # Normalise each clip to ITS OWN mean, so this reads as "how much does it
        # swing", not "which is sharper overall". Those are different questions
        # and conflating them is what hid this problem for so long.
        m = seg.mean()
        norm = seg / m
        lo, hi = 0.45, 1.55
        d.rectangle([PAD, y0, PAD + PW, y0 + PH], fill=(24, 21, 18))
        for frac, lbl in [(1.0, "mean"), (0.7, "-30%"), (1.3, "+30%")]:
            yy = y0 + PH - int((frac - lo) / (hi - lo) * PH)
            d.line([(PAD, yy), (PAD + PW, yy)], fill=(52, 45, 38))
            d.text((PAD + PW + 6, yy - 6), lbl, fill=(120, 108, 94))
        pts = [(PAD + int(j / max(1, len(norm) - 1) * PW),
                y0 + PH - int((min(max(v, lo), hi) - lo) / (hi - lo) * PH))
               for j, v in enumerate(norm)]
        d.line(pts, fill=(224, 145, 63), width=2)
        swing = 100 * seg.std() / m
        d.text((PAD, y0 - 20),
               f"{name}   swing {swing:.1f}% of mean   "
               f"({args.start:.0f}s to {args.start + args.seconds:.0f}s)",
               fill=(238, 224, 208))

    d.text((PAD, img.height - 26),
           "Each peak is a keyframe, each trough is RIFE's midpoint. "
           "A flatter line means the image stops breathing in and out of focus.",
           fill=(150, 136, 120))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    img.save(args.out)
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
