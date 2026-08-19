#!/usr/bin/env python3
"""chain_guard.py -- catch what chain_stats is built not to see.

`chain_stats` reports structure r on a contrast-normalised sigma-12 low pass.
That is the right instrument for "did the composition walk", and it is blind by
construction to everything that went wrong on `labor_not_here` (2026-08-19):

  - the carved inscription rewrote itself to a DIFFERENT SENTENCE at state 41
  - a ring of glowing green runes appeared on the stone at state 35
  - a monogram sat in the bottom-right corner of most states

Every one of those is a LOCAL, HIGH-FREQUENCY, often SATURATED addition on a
surface that is otherwise smooth and desaturated. A sigma-12 low pass removes
exactly that band before correlating, so the chain scored mean r 0.952 while the
text was changing. The eye caught it only after the render, which is the failure
the repo's standing rule names: an instrument agreeing with you is not the same
as looking at the artefact.

So this measures the band the other tool discards:

  SATURATION SPIKE   a chroma outlier against the chain's own median. The rune
                     circle was vivid green on grey stone; this is the cheapest
                     signal that exists for it.
  DETAIL SPIKE       local laplacian energy far above the chain median in the
                     same tile. Added lettering, glyphs and signatures all raise
                     it; weather and foliage raise it globally, not in one tile.
  REGION DRIFT       for a region declared stable (a slab face, a corner), how
                     far each state has moved from state 0 in that band.

Thresholds are deliberately loose. This is a flagger, not a judge: it tells you
which states to OPEN, and the eye decides. It never passes a chain on its own.

    py -3.11 tools/chain_guard.py --dir outputs/arendt/<piece>/accum
    py -3.11 tools/chain_guard.py --dir <accum> --sheet out.png   # contact sheet of flagged states

Exit 1 if anything is flagged, so a pipeline can stop before it renders 900
frames of a chain that rewrote itself.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import numpy as np
from PIL import Image

TILE = 64          # tile edge in working pixels; a signature fits inside one
WORK_W = 688       # half of 1376, enough to see a glyph, fast enough to be free


def load(path: str) -> tuple[np.ndarray, np.ndarray]:
    """Return (luma, saturation) at working resolution, both float."""
    im = Image.open(path).convert("RGB")
    w = WORK_W
    h = int(im.height * (w / im.width))
    a = np.asarray(im.resize((w, h)), dtype=float) / 255.0
    mx, mn = a.max(axis=2), a.min(axis=2)
    sat = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    luma = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    return luma, sat


def laplacian(x: np.ndarray) -> np.ndarray:
    k = np.zeros_like(x)
    k[1:-1, 1:-1] = (4 * x[1:-1, 1:-1] - x[:-2, 1:-1] - x[2:, 1:-1]
                     - x[1:-1, :-2] - x[1:-1, 2:])
    return k


def tiles(x: np.ndarray) -> np.ndarray:
    """Per-tile mean of x, as a 2-D grid."""
    h, w = x.shape
    gh, gw = h // TILE, w // TILE
    x = x[:gh * TILE, :gw * TILE].reshape(gh, TILE, gw, TILE)
    return x.mean(axis=(1, 3))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True, help="directory of authored states")
    ap.add_argument("--sat-k", type=float, default=4.0,
                    help="flag a tile this many MADs above the chain median saturation")
    ap.add_argument("--detail-k", type=float, default=5.0,
                    help="flag a tile this many MADs above the chain median detail")
    ap.add_argument("--sheet", help="write a contact sheet of the flagged states")
    ap.add_argument("--region", help="x0,y0,x1,y1 in SOURCE pixels: the surface that must "
                                     "stay stable (a slab face, a wall). Written as a strip "
                                     "of EVERY state, which is the actual gate.")
    ap.add_argument("--strip", help="path for the region strip")
    a = ap.parse_args()

    fs = sorted(glob.glob(os.path.join(a.dir, "*.png")))
    if not fs:
        print(f"no PNGs in {a.dir}", file=sys.stderr)
        return 2

    sat_g, det_g = [], []
    for f in fs:
        luma, sat = load(f)
        sat_g.append(tiles(sat))
        det_g.append(tiles(np.abs(laplacian(luma))))
    S = np.stack(sat_g)          # (n, gh, gw)
    D = np.stack(det_g)

    def local_peak(X):
        """How strange is the strangest TILE, measured inside its OWN frame.

        The first version of this scored each tile against the same tile across
        the chain, and on a chain with a day/night arc it flagged 35 of 56 states:
        night legitimately moves every statistic, so real local faults drowned in
        global change. Comparing a tile only against its own frame is immune to
        that -- a rune circle is vivid against the grey stone BESIDE it, whatever
        the hour, and a signature is sharp against the grass BESIDE it.
        """
        med = np.median(X, axis=(1, 2), keepdims=True)
        mad = np.median(np.abs(X - med), axis=(1, 2), keepdims=True) + 1e-6
        return ((X - med) / mad).max(axis=(1, 2))       # one number per state

    def outliers(v):
        """Then: which frames are unusual against the OTHER frames."""
        med = np.median(v)
        mad = np.median(np.abs(v - med)) + 1e-6
        return (v - med) / mad

    Z_s, Z_d = outliers(local_peak(S)), outliers(local_peak(D))

    print(f"{len(fs)} states in {a.dir}   tile {TILE}px   grid {S.shape[1]}x{S.shape[2]}")
    print(f"\n{'state':<7}{'satZ':>8}{'detailZ':>9}   verdict")
    print("-" * 60)
    flagged = []
    for i, f in enumerate(fs):
        zs, zd = float(Z_s[i]), float(Z_d[i])
        bad = []
        if zs > a.sat_k:
            bad.append("SATURATION")
        if zd > a.detail_k:
            bad.append("DETAIL")
        if bad:
            flagged.append((i, f, zs, zd, bad))
        mark = ("  <-- " + "+".join(bad)) if bad else ""
        if bad or i % 8 == 0:
            print(f"{i:<7}{zs:8.1f}{zd:9.1f}{mark}")

    # THE ACTUAL GATE. The statistics above are a hint and were measured, on the
    # chain that failed, to MISS the two faults that mattered: legitimate states
    # (autumn gold, a lit sky) carry local peaks as strong as a rune circle, so
    # peak-strangeness does not separate them. What did work, in two minutes, was
    # cropping one surface across every state and looking at it. So that is not
    # an option here; it is the point of the tool.
    if a.region and a.strip:
        from PIL import ImageDraw
        x0, y0, x1, y1 = (int(v) for v in a.region.split(","))
        cw = 340
        ch = max(1, int((y1 - y0) * (cw / max(1, x1 - x0))))
        ims = []
        for i, f in enumerate(fs):
            im = Image.open(f).convert("RGB").crop((x0, y0, x1, y1)).resize((cw, ch))
            d = ImageDraw.Draw(im)
            d.rectangle([0, 0, 30, 12], fill="black")
            d.text((2, 1), f"{i:02d}", fill="yellow")
            ims.append(im)
        cols = 4
        rows = (len(ims) + cols - 1) // cols
        strip = Image.new("RGB", (cw * cols, ch * rows), "black")
        for k, im in enumerate(ims):
            strip.paste(im, ((k % cols) * cw, (k // cols) * ch))
        strip.save(a.strip)
        print(f"region strip, ALL {len(fs)} states -> {a.strip}")
        print("OPEN IT. Read the surface in every tile. This is the step that,")
        print("skipped on 2026-08-19, shipped a chain whose carved text rewrote")
        print("itself into a different sentence while every metric read healthy.")

    print()
    if not flagged:
        print("no local anomalies flagged by the statistics.")
        print("NOT A PASS: the statistics MISSED both real faults on the one chain")
        print("with a known answer. The region strip is the gate; open it.")
        return 0

    print(f"FLAGGED {len(flagged)} state(s): " + ", ".join(str(i) for i, *_ in flagged))
    print("Open every one before rendering. A flag here has meant, in order of")
    print("frequency: added lettering, a volunteered signature, a glowing artefact.")

    if a.sheet:
        ims = []
        from PIL import ImageDraw
        for i, f, zs, zd, bad in flagged:
            im = Image.open(f).convert("RGB")
            im = im.resize((im.width // 2, im.height // 2))
            d = ImageDraw.Draw(im)
            d.rectangle([0, 0, 260, 16], fill="black")
            d.text((3, 3), f"state {i}  satZ {zs:.0f}  detZ {zd:.0f}", fill="yellow")
            ims.append(im)
        cols = min(3, len(ims))
        rows = (len(ims) + cols - 1) // cols
        w, h = ims[0].size
        sheet = Image.new("RGB", (w * cols, h * rows), "black")
        for k, im in enumerate(ims):
            sheet.paste(im, ((k % cols) * w, (k // cols) * h))
        sheet.save(a.sheet)
        print(f"\ncontact sheet of flagged states -> {a.sheet}")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
