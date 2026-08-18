"""Measure ONE edit in a region the edit did not name. The PL17 Q1 instrument.

Judging a whole frame is useless when comparing edit models, because most of the
frame changes for legitimate reasons. What separates candidates is what happens
to the parts nobody asked about: everything that moves in an UNTOUCHED region is
collateral damage.

PL17 measured exactly this on a 704x384 crop and it decided the bake-off. It also
forecast the chain collapse from a single call, which is the cheapest predictor
this project has:

    nano banana   ssim 0.870   lapvar 1.21   warmth  +7.4   -> chain ends at 0.88x
    firered       ssim 0.703   lapvar 1.38   warmth  +6.4   -> compounded to 11.19x
    mageflow      ssim 0.631   lapvar 2.88   warmth +11.3   -> died at edit one
    klein         ssim 0.487   lapvar 2.15   warmth +28.3   -> died at edit one

The instrument did not survive as a tool and had to be rebuilt on 2026-08-18. It
lives here now because PL20 Phase 2 must compare a LoRA-conditioned klein against
klein's bare 0.487 with the identical measurement.

    lapvar   Laplacian variance AFTER divided by BEFORE. The edge-crispening axis.
             1.0 means the surface is as soft as it started. 2.0 means the model
             doubled the high-frequency energy of a region it was not asked to
             touch. Compounds: 1.38 over six edits is 5.5x, and 11.19x was measured.
    warmth   mean(R) - mean(B), after minus before. The yellow-cast axis. Both Qwen
             and Kontext show a per-edit warm shift on artistic material.
    chroma   mean Lab (a,b) distance. Structure r and SSIM are computed on
             GRAYSCALE and are blind to this: a pair scored 0.985 structurally
             while carrying a hue rotation that broke the render. Under ~11 is
             clean, 22.9 mottles.

Read it against the ladder above, not against zero.

    python tools/crop_stats.py --before a/0000.png --after b/0001.png --box 0,384,704,768
    python tools/crop_stats.py --before a/0000.png --after b/0001.png --box 0,384,704,768 --save-crops out/
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import laplace
from skimage.color import rgb2lab
from skimage.metrics import structural_similarity as ssim


def load(path: Path, box: tuple[int, int, int, int] | None) -> Image.Image:
    im = Image.open(path).convert("RGB")
    return im.crop(box) if box else im


def measure(before: Image.Image, after: Image.Image) -> dict[str, float]:
    a = np.asarray(before, dtype=np.float64) / 255.0
    b = np.asarray(after, dtype=np.float64) / 255.0

    ga = np.asarray(before.convert("L"), dtype=np.float64) / 255.0
    gb = np.asarray(after.convert("L"), dtype=np.float64) / 255.0

    lab_a, lab_b = rgb2lab(a), rgb2lab(b)
    chroma = float(np.hypot(lab_b[..., 1] - lab_a[..., 1],
                            lab_b[..., 2] - lab_a[..., 2]).mean())

    va, vb = float(laplace(ga).var()), float(laplace(gb).var())
    warm_a = float((a[..., 0] - a[..., 2]).mean() * 255.0)
    warm_b = float((b[..., 0] - b[..., 2]).mean() * 255.0)

    return {
        "ssim": float(ssim(ga, gb, data_range=1.0)),
        "lapvar": vb / (va + 1e-12),
        "warmth": warm_b - warm_a,
        "chroma": chroma,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True, help="the state the edit started from")
    ap.add_argument("--after", required=True, help="the state the edit produced")
    ap.add_argument("--box", help="crop as left,top,right,bottom. A region the edit "
                                  "did NOT name. Omit to measure the whole frame, "
                                  "which is a much weaker test.")
    ap.add_argument("--label", default="", help="printed with the row, e.g. the model name")
    ap.add_argument("--save-crops", help="dir to write the two 1:1 crops for the eye pass. "
                                         "Every defect that mattered on 2026-08-08 was found "
                                         "at native resolution and missed by the numbers.")
    a = ap.parse_args()

    box = tuple(int(v) for v in a.box.split(",")) if a.box else None
    if box and len(box) != 4:
        raise SystemExit("--box needs exactly four ints: left,top,right,bottom")

    before, after = load(Path(a.before), box), load(Path(a.after), box)
    if before.size != after.size:
        raise SystemExit(f"size mismatch: {before.size} vs {after.size}. The candidate "
                         f"bucket-snapped; resize to the reference before measuring.")

    m = measure(before, after)

    if a.save_crops:
        d = Path(a.save_crops)
        d.mkdir(parents=True, exist_ok=True)
        tag = a.label or "crop"
        before.save(d / f"{tag}_before.png")
        after.save(d / f"{tag}_after.png")

    region = f"{before.size[0]}x{before.size[1]}" + (f" at {a.box}" if a.box else " (FULL FRAME)")
    print(f"{a.label or Path(a.after).name}   region {region}")
    print(f"  ssim    {m['ssim']:.3f}   (nano banana reference 0.870; below 0.80 is a fail)")
    print(f"  lapvar  {m['lapvar']:.2f}     (1.21 banana, 2.15 klein bare; compounds per edit)")
    print(f"  warmth  {m['warmth']:+.1f}     (+7.4 banana, +38.3 klein bare)")
    print(f"  chroma  {m['chroma']:.1f}     (under ~11 clean, 22.9 mottles)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
