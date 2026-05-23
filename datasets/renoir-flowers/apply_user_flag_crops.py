"""Apply crops from review_userflags.json where Gemini gave a sensible bbox.

Skips degenerate (1x1) bboxes; those go to manual review separately.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
DATA = ROOT / "review_userflags.json"
LOG = ROOT / "processed.json"
TARGET_SHORT = 768
MIN_BBOX = 30.0


def main() -> int:
    Image.MAX_IMAGE_PIXELS = None
    data = json.loads(DATA.read_text(encoding="utf-8"))
    log = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else {}
    n_applied = 0
    for name, info in data.items():
        if not info.get("has_residual_margin"):
            continue
        bb = info.get("painting_bbox_pct", {})
        bw, bh = float(bb.get("w", 100)), float(bb.get("h", 100))
        bx, by = float(bb.get("x", 0)), float(bb.get("y", 0))
        # Skip degenerate; skip near-no-op (>=98% in both dims and tiny offset)
        if bw < MIN_BBOX or bh < MIN_BBOX:
            print(f"[skip-degenerate] {name}")
            continue
        if bw >= 99 and bh >= 99 and bx <= 1 and by <= 1:
            print(f"[skip-noop] {name}")
            continue
        fp = RAW / name
        if not fp.exists():
            print(f"[skip-missing] {name}")
            continue
        with Image.open(fp) as im:
            im.load()
            w, h = im.size
            px = int(round(bx / 100 * w))
            py = int(round(by / 100 * h))
            pw = int(round(bw / 100 * w))
            ph = int(round(bh / 100 * h))
            px2 = min(w, px + pw)
            py2 = min(h, py + ph)
            cropped = im.crop((px, py, px2, py2))
            cw, ch = cropped.size
            upscale = 1.0
            if min(cw, ch) < TARGET_SHORT:
                upscale = min(2.0, TARGET_SHORT / min(cw, ch))
                cropped = cropped.resize(
                    (int(cw * upscale), int(ch * upscale)), Image.LANCZOS
                )
            if cropped.mode != "RGB":
                cropped = cropped.convert("RGB")
            cropped.save(fp, format="JPEG", quality=95, optimize=True)
            fw, fh = cropped.size
        prior = log.get(name, {})
        prior["userflag_crop"] = {
            "before_w": w, "before_h": h,
            "after_w": fw, "after_h": fh,
            "bbox_pct": {"x": bx, "y": by, "w": bw, "h": bh},
            "margin_type": info.get("margin_type", ""),
            "upscale": round(upscale, 3),
        }
        prior["after_w"] = fw
        prior["after_h"] = fh
        log[name] = prior
        n_applied += 1
        print(f"[ok] {name}: {w}x{h} -> {fw}x{fh}  ({info.get('margin_type','')})")
    LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\napplied {n_applied} user-flag crops")
    return 0


if __name__ == "__main__":
    sys.exit(main())
