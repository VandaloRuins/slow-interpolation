"""Apply second-pass crops from review_pass2.json.

Only acts on images where review_pass2 returned a sensible bbox
(painting_bbox_pct width and height both >= 30 percent and frame still
present). Degenerate bboxes (1x1) are skipped — these are handled
separately by manual inspection.
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
PASS2 = ROOT / "review_pass2.json"
LOG = ROOT / "processed.json"

TARGET_SHORT = 768
MAX_UPSCALE = 2.0
MIN_BBOX = 30.0  # below this we treat as a degenerate Gemini response


def main() -> int:
    Image.MAX_IMAGE_PIXELS = None
    data = json.loads(PASS2.read_text(encoding="utf-8"))
    log = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else {}

    flagged = [(n, v) for n, v in data.items() if v.get("frame_still_present")]
    print(f"{len(flagged)} pass-2 flagged")

    for name, info in sorted(flagged):
        fp = RAW / name
        bb = info.get("painting_bbox_pct", {})
        bw, bh = float(bb.get("w", 100)), float(bb.get("h", 100))
        if bw < MIN_BBOX or bh < MIN_BBOX:
            print(f"[skip-degenerate] {name}: bbox {bw:.0f}x{bh:.0f}")
            continue

        try:
            with Image.open(fp) as im:
                im.load()
                w, h = im.size
                x = float(bb.get("x", 0))
                y = float(bb.get("y", 0))
                # Pass-2 is meant to be tight. No outward pad.
                px = int(round(x / 100 * w))
                py = int(round(y / 100 * h))
                pw = int(round(bw / 100 * w))
                ph = int(round(bh / 100 * h))
                px2 = min(w, px + pw)
                py2 = min(h, py + ph)
                cropped = im.crop((px, py, px2, py2))
                cw, ch = cropped.size
                short = min(cw, ch)
                upscale = 1.0
                if short < TARGET_SHORT:
                    upscale = min(MAX_UPSCALE, TARGET_SHORT / short)
                    cropped = cropped.resize(
                        (int(cw * upscale), int(ch * upscale)), Image.LANCZOS
                    )
                if cropped.mode != "RGB":
                    cropped = cropped.convert("RGB")
                cropped.save(fp, format="JPEG", quality=95, optimize=True)
                fw, fh = cropped.size
                ops = [f"pass2-crop ({px},{py}) {px2-px}x{py2-py}"]
                if upscale > 1.001:
                    ops.append(f"upscale {upscale:.2f}x")
                prior = log.get(name, {})
                prior["pass2"] = {
                    "before_w": w, "before_h": h,
                    "after_w": fw, "after_h": fh,
                    "bbox_pct": {"x": x, "y": y, "w": bw, "h": bh},
                    "operations": ops,
                }
                prior["after_w"] = fw
                prior["after_h"] = fh
                log[name] = prior
                print(f"[ok] {name}: {w}x{h} -> {fw}x{fh}  ({', '.join(ops)})")
        except Exception as e:
            print(f"[err] {name}: {e}")

    LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
