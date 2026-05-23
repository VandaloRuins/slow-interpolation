"""Apply Gemini-determined crops + upscale where needed.

Reads review.json. For every image flagged with needs_crop=true:
  1. Crops to painting_bbox_pct (with a small inset/outset for safety).
  2. If the cropped short side falls below TARGET_SHORT, upscales with PIL
     LANCZOS to TARGET_SHORT (capped at 2x — anything beyond 2x looks
     synthetic).
  3. Saves over raw/<file>.jpg at JPEG q=95.
  4. Moves the original to raw_orig/<file>.jpg if not already backed up.

Updates an audit log at processed.json with before/after dimensions and
the operations applied per file.

Idempotent: rerunning on an already-processed image is a no-op (review.json
needs_crop is reset only by deleting and re-reviewing).
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
ORIG = ROOT / "raw_orig"
REVIEW = ROOT / "review.json"
LOG = ROOT / "processed.json"

TARGET_SHORT = 768
MAX_UPSCALE = 2.0

# Safety margins. Gemini bboxes are good but ~conservative; pad slightly
# outward when the painting fills most of the frame, and trust the bbox when
# the painting is small in a large catalogue field.
PAD_FRAME_PCT = 1.0  # additional outward pad in percentage of bbox when the bbox is large
PAD_CATALOGUE_PCT = 2.0  # additional outward pad when the bbox is small (auction catalogue)


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def main() -> int:
    Image.MAX_IMAGE_PIXELS = None  # tolerate the 154 MP Cleveland scan
    if not REVIEW.exists():
        sys.exit("review.json missing; run gemini_review.py first")
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    log = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else {}
    ORIG.mkdir(exist_ok=True)

    flagged = [(n, v) for n, v in review.items() if v.get("needs_crop")]
    print(f"{len(flagged)} flagged images")

    for name, info in sorted(flagged):
        fp = RAW / name
        if not fp.exists():
            print(f"[skip] {name}: not in raw/")
            continue
        # Already processed?
        if log.get(name, {}).get("status") == "done":
            print(f"[done] {name}: already processed, skipping")
            continue

        try:
            with Image.open(fp) as im:
                im.load()
                w, h = im.size
                bb = info.get("painting_bbox_pct", {})
                x = float(bb.get("x", 0))
                y = float(bb.get("y", 0))
                bw = float(bb.get("w", 100))
                bh = float(bb.get("h", 100))

                # No-op guard
                if bw >= 99 and bh >= 99 and x <= 1 and y <= 1:
                    log[name] = {"status": "skipped", "reason": "bbox covers full image"}
                    continue

                # Choose pad based on whether painting fills the frame
                is_catalogue = bw < 70 or bh < 70
                pad = PAD_CATALOGUE_PCT if is_catalogue else PAD_FRAME_PCT
                x_pad = clamp(x - pad, 0, 100)
                y_pad = clamp(y - pad, 0, 100)
                w_pad = clamp(bw + 2 * pad, 0, 100 - x_pad)
                h_pad = clamp(bh + 2 * pad, 0, 100 - y_pad)

                # Pixel coords
                px = int(round(x_pad / 100 * w))
                py = int(round(y_pad / 100 * h))
                pw = int(round(w_pad / 100 * w))
                ph = int(round(h_pad / 100 * h))
                px2 = min(w, px + pw)
                py2 = min(h, py + ph)

                cropped = im.crop((px, py, px2, py2))
                cw, ch = cropped.size
                short = min(cw, ch)

                upscale_factor = 1.0
                if short < TARGET_SHORT:
                    upscale_factor = min(MAX_UPSCALE, TARGET_SHORT / short)
                    new_w = int(round(cw * upscale_factor))
                    new_h = int(round(ch * upscale_factor))
                    cropped = cropped.resize((new_w, new_h), Image.LANCZOS)

                # Convert and save
                if cropped.mode != "RGB":
                    cropped = cropped.convert("RGB")

                # Back up original first
                backup = ORIG / name
                if not backup.exists():
                    shutil.copy2(fp, backup)

                cropped.save(fp, format="JPEG", quality=95, optimize=True)
                fw, fh = cropped.size
                ops = []
                if (bw, bh) != (100, 100) or (x, y) != (0, 0):
                    ops.append(f"crop ({px},{py}) {px2-px}x{py2-py}")
                if upscale_factor > 1.001:
                    ops.append(f"upscale {upscale_factor:.2f}x to {fw}x{fh}")

                log[name] = {
                    "status": "done",
                    "before_w": w,
                    "before_h": h,
                    "after_w": fw,
                    "after_h": fh,
                    "bbox_pct": {"x": x, "y": y, "w": bw, "h": bh},
                    "pad_pct": pad,
                    "upscale_factor": round(upscale_factor, 3),
                    "operations": ops,
                    "flags": {
                        "frame": info.get("has_physical_frame", False),
                        "white_bg": info.get("has_white_or_paper_border", False),
                        "watermark": info.get("has_watermark", False),
                    },
                    "notes": info.get("notes", ""),
                }
                print(f"[ok] {name}: {w}x{h} -> {fw}x{fh}  ({', '.join(ops)})")
        except Exception as e:
            log[name] = {"status": "error", "reason": str(e)[:200]}
            print(f"[err] {name}: {e}")

    LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    n_done = sum(1 for v in log.values() if v.get("status") == "done")
    n_err = sum(1 for v in log.values() if v.get("status") == "error")
    print(f"\nfinal: done={n_done} err={n_err}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
