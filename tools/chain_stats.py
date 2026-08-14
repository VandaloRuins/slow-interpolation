"""Critique a keyframe chain BEFORE interpolating, with both instruments paired.

The doctrine has required this pairing since PL17 and nothing in the repo did it.
Consecutive SSIM measures STEP SIZE and is structurally blind to a monotonic walk
away from the original: in the PL17 bake-off a dying chain's consecutive SSIM went
UP as it detonated, and its mean BEAT nano banana's on a chain that was garbage.
So every number here comes in a pair, a consecutive one and a drift-against-frame-0
one, and neither is read alone.

    structure r   pearson on a contrast-normalised sigma-12 low pass, consecutive
    ssim          consecutive, half scale
    r0 / ssim0    the same two measures against FRAME 0, which is where drift shows
    surf/f0       laplacian variance as a RATIO to frame 0, per state

How to read it:

- Healthy consecutive structure r is roughly 0.9 and up. Bridge pairs below ~0.85.
- STOP bridging if a bridge comes back as a near-copy of an endpoint (r ~0.99 to
  one side): above that gap the ARC is wrong, not the density.
- A moving surface ratio is usually the SUBJECT. Foliage genuinely adds texture and
  bare earth genuinely removes it. The kill signal is a fast monotonic climb past
  about 3x WITH the consecutive ladder improving underneath it.
- Low ssim with high structure r is a light or texture event, not drift. A
  dusk-to-night piece measured ssim 0.39 to 0.47 at structure r 0.99.
- r0 collapsing on a strong LIGHT event is expected, because the sigma-12 low pass
  IS the light layout. Read it against the subject before calling it a fault.

What it caught on the day it was written (2026-08-14): a snow-on-steps chain whose
consecutive ladder degraded 0.835 / 0.657 / 0.621 while the staircase itself walked,
gaining treads and re-proportioning. The covering medium was hiding the geometric
reference it was supposed to preserve.

    python tools/chain_stats.py --dir outputs/arendt/<name>/accum
    python tools/chain_stats.py --dir outputs/arendt/<name>/accum --wrap
"""
from __future__ import annotations

import argparse
import glob
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, laplace
from skimage.metrics import structural_similarity as ssim


def gray(p: Path, scale: float = 1.0) -> np.ndarray:
    im = Image.open(p).convert("L")
    if scale != 1.0:
        im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
    return np.asarray(im, dtype=np.float64) / 255.0


def structure(g: np.ndarray, sigma: float = 12.0) -> np.ndarray:
    """Contrast-normalised low pass: the composition, with light level divided out."""
    lo = gaussian_filter(g, sigma)
    return (lo - lo.mean()) / (lo.std() + 1e-8)


def pearson(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.corrcoef(a.ravel(), b.ravel())[0, 1])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="dir of authored states (PNGs)")
    ap.add_argument("--wrap", action="store_true",
                    help="also measure last->first, for a SELF-CLOSING chain. Omit "
                         "for a palindrome chain, whose seam is pixel-exact by "
                         "construction and so is not worth measuring.")
    a = ap.parse_args()

    paths = [Path(p) for p in sorted(glob.glob(str(Path(a.dir) / "*.png")))]
    if not paths:
        print(f"no PNGs in {a.dir}")
        return 1

    full = [gray(p) for p in paths]
    half = [gray(p, 0.5) for p in paths]
    st = [structure(g) for g in full]
    surf = [float(laplace(g).var()) for g in full]

    print(f"{len(paths)} states in {a.dir}\n")
    print(f"{'pair':>10}  {'struct r':>9}  {'ssim':>6}   | "
          f"{'state':>6}  {'r0':>6}  {'ssim0':>6}  {'surf/f0':>8}")
    print("-" * 74)

    order = list(range(len(paths)))
    pairs = list(zip(order, order[1:])) + ([(order[-1], order[0])] if a.wrap else [])
    rows = [(f"{i}->{j}", pearson(st[i], st[j]),
             float(ssim(half[i], half[j], data_range=1.0))) for i, j in pairs]

    for k, (label, r, s) in enumerate(rows):
        idx = k + 1 if k + 1 < len(paths) else None
        right = ""
        if idx is not None:
            right = (f"| {idx:>6}  {pearson(st[0], st[idx]):>6.3f}  "
                     f"{float(ssim(half[0], half[idx], data_range=1.0)):>6.3f}  "
                     f"{surf[idx] / surf[0]:>8.2f}")
        flag = "  <-- BRIDGE" if r < 0.85 else ""
        print(f"{label:>10}  {r:>9.3f}  {s:>6.3f}   {right}{flag}")

    worst = min(rows, key=lambda t: t[1])
    print(f"\nmean struct r {np.mean([r for _, r, _ in rows]):.3f}   "
          f"worst pair {worst[0]} at {worst[1]:.3f}")
    print(f"surface ratio range {min(surf) / surf[0]:.2f}x to {max(surf) / surf[0]:.2f}x "
          f"(kill signal: fast monotonic climb past ~3x)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
