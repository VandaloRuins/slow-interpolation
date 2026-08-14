"""Apply user-defined crops from the browser export.

Reads `gallery-flags.json` (the file the gallery's "Export flags + crops"
button downloads) from Downloads or a path passed on argv. For each entry
in `crops`, applies the percentage bbox to raw/<filename>, backing up the
pre-crop version to raw_orig/ if not already backed up, and upscaling with
LANCZOS if the cropped short side falls below 768 px.

Usage:
    py -3.11 datasets/renoir-flowers/apply_browser_crops.py \
        <path-to-downloads>/gallery-flags.json
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
ORIG = ROOT / "raw_orig"
LOG = ROOT / "processed.json"
DEFAULT_INPUT = Path.home() / "Downloads" / "gallery-flags.json"
TARGET_SHORT = 768
MAX_UPSCALE = 2.0


def main() -> int:
    Image.MAX_IMAGE_PIXELS = None
    src_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT
    if not src_path.exists():
        sys.exit(f"input not found: {src_path}")
    data = json.loads(src_path.read_text(encoding="utf-8"))
    crops = data.get("crops", {})
    if not crops:
        print(f"no crops in {src_path}")
        return 0
    log = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else {}
    ORIG.mkdir(exist_ok=True)
    archive = ROOT / f"user-crops-applied-{datetime.now():%Y-%m-%d}.json"

    applied = {}
    for name, bb in crops.items():
        fp = RAW / name
        if not fp.exists():
            print(f"[skip-missing] {name}")
            continue
        try:
            x = float(bb["x"]); y = float(bb["y"])
            w = float(bb["w"]); h = float(bb["h"])
        except (KeyError, TypeError, ValueError):
            print(f"[skip-bad-bbox] {name}: {bb}")
            continue
        # Sanity: at least 5% in both dims, fully inside [0,100]
        if not (0 <= x <= 100 and 0 <= y <= 100 and 5 <= w and 5 <= h and x + w <= 100.5 and y + h <= 100.5):
            print(f"[skip-out-of-range] {name}: {bb}")
            continue
        if w >= 99.5 and h >= 99.5 and x <= 0.5 and y <= 0.5:
            print(f"[skip-noop] {name}: full-image bbox")
            continue
        with Image.open(fp) as im:
            im.load()
            # Rotation in the browser cropper is CLOCKWISE in degrees
            # (0/90/180/270). PIL's Image.rotate is counter-clockwise, so
            # we pass the negative. expand=True so the canvas grows to fit.
            rot_cw = int(bb.get("rotation", 0)) % 360
            if rot_cw:
                im = im.rotate(-rot_cw, expand=True, resample=Image.BICUBIC)
            iw, ih = im.size
            px = int(round(x / 100 * iw))
            py = int(round(y / 100 * ih))
            pw = int(round(w / 100 * iw))
            ph = int(round(h / 100 * ih))
            px2 = min(iw, px + pw)
            py2 = min(ih, py + ph)
            cropped = im.crop((px, py, px2, py2))
            cw, ch = cropped.size
            upscale = 1.0
            if min(cw, ch) < TARGET_SHORT:
                upscale = min(MAX_UPSCALE, TARGET_SHORT / min(cw, ch))
                cropped = cropped.resize(
                    (int(cw * upscale), int(ch * upscale)), Image.LANCZOS
                )
            if cropped.mode != "RGB":
                cropped = cropped.convert("RGB")
            backup = ORIG / name
            if not backup.exists():
                shutil.copy2(fp, backup)
            cropped.save(fp, format="JPEG", quality=95, optimize=True)
            fw, fh = cropped.size
        prior = log.get(name, {})
        prior["browser_crop"] = {
            "before_w": iw, "before_h": ih,
            "after_w": fw, "after_h": fh,
            "bbox_pct": {"x": x, "y": y, "w": w, "h": h},
            "rotation_cw_deg": int(bb.get("rotation", 0)) % 360,
            "upscale": round(upscale, 3),
            "exported_at": data.get("exported_at", ""),
        }
        prior["after_w"] = fw
        prior["after_h"] = fh
        log[name] = prior
        applied[name] = prior["browser_crop"]
        print(f"[ok] {name}: {iw}x{ih} -> {fw}x{fh}  (upscale {upscale:.2f}x)")

    LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    archive.write_text(json.dumps({"source": str(src_path), "applied": applied},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\napplied {len(applied)} browser crops; audit at {archive.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
