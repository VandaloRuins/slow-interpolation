"""Quantitative + visual analysis of a render sweep.

Eyeballing a poster frame tells you almost nothing about a 12.8 s drift. This
samples the WHOLE video and produces, per rung:

  1. A single analysis sheet PNG: a row of N frames across the full duration
     (the arc), plus two 1:1 crops (first and last frame, same region for every
     rung) so surface texture is comparable rather than impressionistic.
  2. A metrics row: detail, high-frequency energy, drift rate, loop closure.

Metrics, and what each is actually measuring:

  detail      variance of the Laplacian. Classic focus measure. High = crisp
              edges and visible mark-making. WARNING: it also rewards noise,
              so read it next to hf_ratio rather than alone.
  hf_ratio    fraction of FFT magnitude above a mid radius. Brushwork lives
              here. Less noise-sensitive than Laplacian variance.
  drift       mean absolute pixel delta between consecutive SAMPLED frames,
              normalised per second. This is the perceived speed of the piece.
  loop        absolute delta between the last frame and the first, expressed as
              a multiple of the typical consecutive delta. ~1.0 means the wrap
              is indistinguishable from any other step, i.e. a clean loop.
              Much above 1 is a visible seam.
  decay       detail(last) / detail(first) on the KEYFRAMES. Below 1.0 means
              the chain is losing surface as it runs, which a single still
              cannot show.

    python tools/analyse_ladder.py --dir outputs/step-ladder --samples 9
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

# Fixed crop region, identical for every rung so surface is directly
# comparable. Chosen off-centre to avoid the dead middle of the frame.
CROP = (330, 200, 330 + 430, 200 + 430)


def sample_frames(video: Path, n: int) -> list[Image.Image]:
    """N frames evenly spaced across the whole clip, decoded via ffmpeg."""
    total = int(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-count_frames", "-show_entries", "stream=nb_read_frames",
         "-of", "csv=p=0", str(video)],
        capture_output=True, text=True).stdout.strip() or 0)
    if total <= 0:
        return []
    idx = np.linspace(0, total - 1, n).astype(int)
    out: list[Image.Image] = []
    for i in idx:
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"select=eq(n\\,{i})",
             "-vsync", "0", "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
            capture_output=True)
        if r.stdout:
            import io
            out.append(Image.open(io.BytesIO(r.stdout)).convert("RGB"))
    return out


def detail(img: Image.Image) -> float:
    """Variance of the Laplacian on luminance."""
    a = np.asarray(img.convert("L"), dtype=np.float32)
    k = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
    # valid-region convolution without scipy
    v = (k[0, 1] * a[:-2, 1:-1] + k[1, 0] * a[1:-1, :-2] + k[1, 1] * a[1:-1, 1:-1]
         + k[1, 2] * a[1:-1, 2:] + k[2, 1] * a[2:, 1:-1])
    return float(v.var())


def hf_ratio(img: Image.Image) -> float:
    """Share of FFT magnitude outside a mid-frequency radius."""
    a = np.asarray(img.convert("L").resize((512, 512)), dtype=np.float32)
    f = np.abs(np.fft.fftshift(np.fft.fft2(a)))
    yy, xx = np.mgrid[0:512, 0:512]
    r = np.hypot(yy - 256, xx - 256)
    return float(f[r > 96].sum() / max(f.sum(), 1e-6))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="outputs/step-ladder")
    ap.add_argument("--samples", type=int, default=9)
    args = ap.parse_args()

    root = Path(args.dir)
    sheets = root / "_analysis"
    sheets.mkdir(parents=True, exist_ok=True)

    print(f"{'rung':24} {'detail':>9} {'hf_ratio':>9} {'drift':>8} {'loop':>7} {'decay':>7}")
    print("-" * 70)

    for video in sorted(root.glob("*.mp4")):
        name = video.stem.replace("ladder_", "")
        frames = sample_frames(video, args.samples)
        if not frames:
            print(f"{name:24} UNREADABLE")
            continue

        arr = [np.asarray(f.convert("L"), dtype=np.float32) for f in frames]
        deltas = [float(np.abs(arr[i] - arr[i - 1]).mean()) for i in range(1, len(arr))]
        typical = float(np.median(deltas)) if deltas else 0.0
        wrap = float(np.abs(arr[-1] - arr[0]).mean())

        d = float(np.mean([detail(f) for f in frames]))
        h = float(np.mean([hf_ratio(f) for f in frames]))
        dur = 384 / 30
        drift = (sum(deltas) / dur) if deltas else 0.0
        loop = (wrap / typical) if typical > 1e-6 else float("nan")

        # Chain survival, measured on the KEYFRAMES not the interpolated video.
        # Staging dirs are named after `output_name`, which may or may not carry
        # the video's own prefix. Match on the stem first, then the stripped name.
        kfs: list[Path] = []
        for cand in (video.stem, name):
            kf_dir = root / "staging" / cand
            if kf_dir.is_dir():
                kfs = sorted(kf_dir.rglob("*.png"))
                break
        decay = float("nan")
        if len(kfs) >= 2:
            d0, d6 = detail(Image.open(kfs[0])), detail(Image.open(kfs[-1]))
            decay = d6 / d0 if d0 > 0 else float("nan")

        print(f"{name:24} {d:>9.1f} {h:>9.4f} {drift:>8.2f} {loop:>7.2f} {decay:>7.2f}")

        # --- analysis sheet -------------------------------------------------
        tw = 300
        th = int(tw * frames[0].height / frames[0].width)
        strip = [f.resize((tw, th), Image.LANCZOS) for f in frames]
        crop_a = frames[0].crop(CROP)
        crop_b = frames[-1].crop(CROP)

        W = max(tw * len(strip), crop_a.width * 2 + 30)
        H = th + 26 + crop_a.height + 26
        sheet = Image.new("RGB", (W, H), (18, 16, 14))
        for i, f in enumerate(strip):
            sheet.paste(f, (i * tw, 22))
        sheet.paste(crop_a, (0, th + 48))
        sheet.paste(crop_b, (crop_a.width + 30, th + 48))

        dr = ImageDraw.Draw(sheet)
        dr.text((4, 6), f"{name}  |  arc across 12.8 s, {len(strip)} samples", fill=(230, 220, 200))
        dr.text((4, th + 30), "1:1 crop, FIRST frame", fill=(230, 200, 150))
        dr.text((crop_a.width + 34, th + 30), "1:1 crop, LAST frame", fill=(230, 200, 150))
        sheet.save(sheets / f"{name}.png")

    print(f"\nsheets -> {sheets}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
