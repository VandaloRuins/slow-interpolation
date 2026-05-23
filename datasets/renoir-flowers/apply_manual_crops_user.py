"""Apply the manual_crops_user.json micro-crops verified by visual inspection."""
from __future__ import annotations
import json, sys
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
SPEC = ROOT / "manual_crops_user.json"
LOG = ROOT / "processed.json"
TARGET_SHORT = 768


def main() -> int:
    Image.MAX_IMAGE_PIXELS = None
    data = json.loads(SPEC.read_text(encoding="utf-8"))
    log = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else {}
    for name, info in data.items():
        if name.startswith("_"):
            continue
        fp = RAW / name
        if not fp.exists():
            print(f"[skip-missing] {name}")
            continue
        bb = info["bbox_pct"]
        with Image.open(fp) as im:
            im.load()
            w, h = im.size
            px = int(round(bb["x"]/100*w))
            py = int(round(bb["y"]/100*h))
            pw = int(round(bb["w"]/100*w))
            ph = int(round(bb["h"]/100*h))
            px2 = min(w, px+pw)
            py2 = min(h, py+ph)
            cropped = im.crop((px, py, px2, py2))
            cw, ch = cropped.size
            upscale = 1.0
            if min(cw, ch) < TARGET_SHORT:
                upscale = min(2.0, TARGET_SHORT/min(cw, ch))
                cropped = cropped.resize((int(cw*upscale), int(ch*upscale)), Image.LANCZOS)
            if cropped.mode != "RGB":
                cropped = cropped.convert("RGB")
            cropped.save(fp, "JPEG", quality=95, optimize=True)
            fw, fh = cropped.size
        prior = log.get(name, {})
        prior["manual_user"] = {
            "before_w": w, "before_h": h,
            "after_w": fw, "after_h": fh,
            "bbox_pct": bb, "upscale": round(upscale, 3),
            "reason": info["reason"],
        }
        prior["after_w"] = fw
        prior["after_h"] = fh
        log[name] = prior
        print(f"[ok] {name}: {w}x{h} -> {fw}x{fh}")
    LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
