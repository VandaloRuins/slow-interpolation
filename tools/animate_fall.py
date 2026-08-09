"""Composite a downward water cycle into a rendered waterfall, outside diffusion.

Why this exists. Five in-diffusion mechanisms for directional water were built
and measured (2026-08-09, quality-first log): displaced pixels are discarded by
the img2img chain (median 0.00 px of an intended 154), and animated conditioning
is out-shouted by the input image (phase-following 2/20 at r=0.05). The
conclusion was structural: the feedback loop re-derives texture from what it is
conditioned on and inherits its own history over any injectable signal. So the
descent cannot be asked from diffusion. It is applied here instead, as pixel
arithmetic on the rendered frames, where speed is exact, the rock provably
cannot move, and the loop closes by construction.

What it does, per output frame n of N:

  1. WATER MASK, from the painted appearance, not the control map. The model
     paints rock outcrops INSIDE the map's channel, so a geometry mask would
     advect rock. Water is what is bright and desaturated across the clip's
     median: (L > lum_thresh) & (S < sat_thresh), confined to the map channel's
     columns, feathered.
  2. BAND-PASS the frame: blur(lo) - blur(hi). The envelope and the rock's
     large forms live below the band and cannot move; grain the chain reinvents
     anyway lives above it. The advected band is the streaks and foam.
  3. ROLL the band down WITHIN EACH COLUMN'S OWN MASKED RUN. A full-frame
     roll was tried first and pulled band content from d pixels above
     regardless of what lived there, so mid-tier water received ROCK texture
     whenever the roll distance exceeded a mask segment. Instead, each
     column's masked pixels form a closed 1D loop: texture leaving the bottom
     of a column's water re-enters at its top, passes instantly behind rock
     between tiers (which is what a real fall does), and NEVER samples
     anything that is not water. Per column, the shift is round(n * m / N)
     of its own run length m, so every column completes exactly one cycle
     over the loop and frame N is congruent to frame 0 column by column.
  4. Re-composite through the mask. Outside the mask the frame is untouched,
     so the rocks are not merely likely to stay still, they are incapable of
     moving.

The underlying render's slow painterly churn remains beneath the moving band,
which is what keeps this from reading as a sliding sheet.

    python tools/animate_fall.py --src outputs/nyc-billboard/led/led9_a_fall.mp4 \\
        --map outputs/_anchors/led9-a-fall-p00.png --edge-crop 8

Writes <src stem>_flow.mp4 beside the source, same size and frame count, and a
mask preview PNG for the eye. Conform afterwards as usual.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


def read_frames(src: Path) -> tuple[list[np.ndarray], float]:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate", "-of", "csv=p=0", str(src)],
        capture_output=True, text=True, check=True).stdout.strip().split(",")
    w, h = int(probe[0]), int(probe[1])
    num, _, den = probe[2].partition("/")
    fps = float(num) / float(den or 1)
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(src), "-f", "rawvideo",
         "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True).stdout
    n = len(raw) // (w * h * 3)
    frames = np.frombuffer(raw, np.uint8)[: n * w * h * 3].reshape(n, h, w, 3)
    return [frames[i].copy() for i in range(n)], fps


def write_frames(frames: list[np.ndarray], fps: float, out: Path, crf: int = 12) -> None:
    h, w = frames[0].shape[:2]
    p = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{w}x{h}", "-r", f"{fps}", "-i", "-",
         "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(out)],
        stdin=subprocess.PIPE)
    for f in frames:
        p.stdin.write(f.tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("ffmpeg encode failed")


def water_mask(frames: list[np.ndarray], chan_cols: np.ndarray,
               warmth_pct: float, lum_pct: float, feather: int,
               top_guard: int) -> np.ndarray:
    """Water = the COOL, bright fraction of the median frame, inside the channel.

    Absolute luminance/saturation thresholds failed on the first real render:
    the painted fall sits at lum 65 to 104, overlapping the rock at 72 to 87, so
    luminance cannot separate them. What separates them is COLOUR TEMPERATURE:
    the fall is grey-white (r - b small) while Cole rock is brown (r - b large).
    Thresholds are percentiles of the median frame itself, so the rule adapts to
    each render's palette instead of hardcoding one frame's numbers.

    `top_guard` zeroes the mask above the lip: a sky vista painted above the
    gorge is also cool and bright, and without the guard the wrap would crawl
    streak texture down the sky.

    The median across sampled frames rather than any single frame: the fall's
    bright streaks wander, and the median keeps the region water occupies most
    of the time while dropping one-frame specular flicker on wet rock.
    """
    sample = frames[:: max(1, len(frames) // 40)]
    med = np.median(np.stack(sample), axis=0).astype(np.float32)
    warmth = med[..., 0] - med[..., 2]
    lum = med.mean(axis=2)
    m = ((warmth < np.percentile(warmth, warmth_pct))
         & (lum > np.percentile(lum, lum_pct))
         & chan_cols[None, :])
    m[:top_guard] = False
    mask = Image.fromarray((m * 255).astype(np.uint8))
    mask = mask.filter(ImageFilter.MaxFilter(9))          # close pinholes
    mask = mask.filter(ImageFilter.GaussianBlur(feather))
    out = np.asarray(mask, np.float32)[..., None] / 255.0
    out[:top_guard] *= np.linspace(0, 1, top_guard)[:, None, None] * 0 +         np.asarray(out[:top_guard])  # keep post-blur bleed above guard soft
    out[:max(0, top_guard - feather)] = 0.0
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--map", type=Path, required=True,
                    help="phase-0 control map; its dark region's COLUMNS bound the water")
    ap.add_argument("--edge-crop", type=int, default=8,
                    help="edge_crop the render applied, to align the map")
    ap.add_argument("--band-lo", type=float, default=10.0)
    ap.add_argument("--band-hi", type=float, default=90.0)
    ap.add_argument("--warmth-pct", type=float, default=35.0,
                    help="water = warmth below this percentile of the median frame")
    ap.add_argument("--lum-pct", type=float, default=60.0,
                    help="and luminance above this percentile")
    ap.add_argument("--top-guard", type=int, default=120,
                    help="zero the mask above this row (the lip; excludes sky)")
    ap.add_argument("--feather", type=int, default=18)
    ap.add_argument("--gain", type=float, default=1.5,
                    help="amplify the moved band inside the mask. Measured on the "
                         "first composite: the moved band correlates 0.60 at the "
                         "designed shift but static sub-band grain correlates 0.91, "
                         "so at gain 1.0 the eye locks onto what does NOT move.")
    ap.add_argument("--damp-fine", type=float, default=0.5,
                    help="suppress static detail finer than band-lo inside the mask "
                         "by this fraction; frozen grain on moving water reads as a "
                         "dirty window in front of the fall")
    ap.add_argument("--cycles", type=int, default=1,
                    help="full texture traversals per loop; must stay an integer "
                         "or the wrap seam returns")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    frames, fps = read_frames(args.src)
    n, (h, w) = len(frames), frames[0].shape[:2]
    print(f"src         : {w}x{h}, {n} frames @ {fps:g}")

    ec = args.edge_crop
    g = Image.open(args.map).convert("L")
    if ec:
        g = g.crop((ec, ec, g.width - ec, g.height - ec))
    g = g.resize((w, h), Image.LANCZOS)
    chan_cols = (np.asarray(g, np.float32) < 60).mean(axis=0) > 0.35

    mask = water_mask(frames, chan_cols, args.warmth_pct, args.lum_pct,
                      args.feather, args.top_guard)
    cover = float(mask.mean())
    print(f"water mask  : {100 * cover:.1f}% of frame "
          f"({100 * float((mask > 0.5).mean()):.1f}% hard)")
    if not 0.015 < cover < 0.45:
        print("mask coverage outside sanity range; tune --warmth-pct/--lum-pct",
              file=sys.stderr)
        return 1
    mp = args.src.with_name(args.src.stem + "_flowmask.png")
    Image.fromarray((mask[..., 0] * 255).astype(np.uint8)).save(mp)

    # Precompute the per-column gather structure over the HARD mask. For each
    # masked pixel: its column, its rank within the column's masked run, and
    # the run's length. Per frame, rank -> (rank - shift) mod run_length is a
    # single vectorised fancy-index over all masked pixels.
    hard = mask[..., 0] > 0.5
    ys, xs = np.nonzero(hard)
    order = np.lexsort((ys, xs))
    ys, xs = ys[order], xs[order]
    run_len = np.bincount(xs, minlength=w)
    col_start = np.concatenate(([0], np.cumsum(run_len)))[:-1]
    rank = np.arange(len(xs)) - col_start[xs]
    m_col = run_len[xs]                       # each pixel's own run length
    flat = ys * w + xs

    out_frames = []
    for i, f in enumerate(frames):
        a = f.astype(np.float32)
        img = Image.fromarray(f)
        lo = np.asarray(img.filter(ImageFilter.GaussianBlur(args.band_lo)), np.float32)
        hi = np.asarray(img.filter(ImageFilter.GaussianBlur(args.band_hi)), np.float32)
        band = lo - hi
        fine = a - lo          # static grain finer than the moving band
        # shift = round(n * m / N) per pixel via its column's run length:
        # every column completes exactly `cycles` full cycles over the loop.
        shift = (i * args.cycles * m_col) // n
        src_rank = (rank - shift) % np.maximum(m_col, 1)
        src_flat = flat[col_start[xs] + src_rank]
        band2 = band.reshape(-1, 3)
        moved = band2[src_flat]
        delta = np.zeros_like(band2)
        delta[flat] = moved - band2[flat]
        out = (a - fine * (args.damp_fine * mask)
               + delta.reshape(h, w, 3) * (args.gain * mask))
        out_frames.append(np.clip(out, 0, 255).astype(np.uint8))
        if i % 100 == 0:
            print(f"  frame {i}/{n}")

    out = args.out or args.src.with_name(args.src.stem + "_flow.mp4")
    write_frames(out_frames, fps, out)
    print(f"wrote       : {out}")
    print(f"loop        : every column completes exactly {args.cycles} cycle(s) of its "
          f"own masked run over {n} frames; closure is per column by construction")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
