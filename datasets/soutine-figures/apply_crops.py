"""Apply Gemini review decisions: triage drops, crop keepers.

Mirror of datasets/renoir-flowers/apply_crops.py with an extra triage step
upfront: this script first MOVES every reject in review.json into
rejected/<reason>/ so the keeper set in raw/ is unambiguous. Then applies
crops (and upscale where needed) to keepers flagged needs_crop=true.

Idempotent on both stages.

Reads:
    datasets/soutine-figures/review.json

Writes:
    datasets/soutine-figures/raw/                  cropped + upscaled keepers
    datasets/soutine-figures/raw_orig/             backups of pre-crop versions
    datasets/soutine-figures/rejected/<reason>/    triaged drops
    datasets/soutine-figures/processed.json        per-file audit trail
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
REJECTED = ROOT / "rejected"
REVIEW = ROOT / "review.json"
LOG = ROOT / "processed.json"

TARGET_SHORT = 768
MAX_UPSCALE = 2.0
PAD_FRAME_PCT = 1.0
PAD_CATALOGUE_PCT = 2.0


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _safe_reason(reason: str) -> str:
    """Reason becomes a folder name; strip anything non-alphanumeric."""
    out = "".join(c if c.isalnum() or c == "_" else "_" for c in (reason or "unspecified"))
    return out.strip("_") or "unspecified"


def triage_drops(review: dict) -> int:
    """Move every reject into rejected/<reason>/. Returns count moved."""
    moved = 0
    for name, info in sorted(review.items()):
        if info.get("keep_for_training"):
            continue
        if "error" in info:
            continue
        reason = _safe_reason(info.get("rejection_reason", "unspecified"))
        src = RAW / name
        if not src.exists():
            continue
        dest_dir = REJECTED / reason
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / name
        if dest.exists():
            # Already triaged on a prior run; nothing to do
            try:
                src.unlink()
            except FileNotFoundError:
                pass
            continue
        shutil.move(str(src), str(dest))
        moved += 1
    return moved


def crop_keepers(review: dict, log: dict) -> tuple[int, int]:
    """Apply Gemini bboxes to flagged keepers. Returns (done, errored)."""
    done = errored = 0
    keepers = [(n, v) for n, v in review.items() if v.get("keep_for_training")]
    flagged = [(n, v) for n, v in keepers if v.get("needs_crop")]
    print(f"{len(keepers)} keepers, {len(flagged)} flagged needs_crop")

    for name, info in sorted(flagged):
        fp = RAW / name
        if not fp.exists():
            print(f"[skip] {name}: not in raw/ (triaged?)")
            continue
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

                if bw >= 99 and bh >= 99 and x <= 1 and y <= 1:
                    log[name] = {"status": "skipped", "reason": "bbox covers full image"}
                    continue

                is_catalogue = bw < 70 or bh < 70
                pad = PAD_CATALOGUE_PCT if is_catalogue else PAD_FRAME_PCT
                x_pad = clamp(x - pad, 0, 100)
                y_pad = clamp(y - pad, 0, 100)
                w_pad = clamp(bw + 2 * pad, 0, 100 - x_pad)
                h_pad = clamp(bh + 2 * pad, 0, 100 - y_pad)

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

                if cropped.mode != "RGB":
                    cropped = cropped.convert("RGB")

                ORIG.mkdir(exist_ok=True)
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
                    "subject_kind": info.get("subject_kind", ""),
                    "notes": info.get("notes", ""),
                }
                done += 1
                print(f"[ok] {name}: {w}x{h} -> {fw}x{fh}  ({', '.join(ops)})")
        except Exception as e:
            log[name] = {"status": "error", "reason": str(e)[:200]}
            errored += 1
            print(f"[err] {name}: {e}")

    return done, errored


def main() -> int:
    Image.MAX_IMAGE_PIXELS = None
    if not REVIEW.exists():
        sys.exit("review.json missing; run gemini_review.py first")

    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    log = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else {}

    print("=== Triage (move drops to rejected/<reason>/) ===")
    moved = triage_drops(review)
    print(f"moved {moved} files to rejected/")
    print()

    print("=== Crop keepers ===")
    done, errored = crop_keepers(review, log)
    LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nfinal: cropped={done} errored={errored}")

    # Final keeper count
    keeper_files = [p.name for p in RAW.glob("*.jpg")]
    print(f"keeper set in raw/: {len(keeper_files)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
