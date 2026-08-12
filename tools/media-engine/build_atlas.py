"""
build_atlas.py -- pack local thumbnails into a texture atlas for Glance.

Reads the derived field (`cache/field-{edition}.json`) for the set of assets that
have a local thumbnail, packs each thumbnail (aspect-preserved) into fixed grid
cells on one or more 4096x4096 JPEG sheets, and emits an index mapping each
16-char sha to its {sheet, x, y, w, h, aspect} rect. The WebGL field renders
every tile from this single texture in one instanced draw call; focused/lifted
tiles later swap to their full 512px /thumbs/{sha}.jpg.

DERIVED ARTIFACT: written under cache/atlas/ (gitignored). Reads thumbs only;
never touches originals; never writes the catalogue. Re-run after each ingest
(after build_field.py).

Usage:
    py -3.11 tools/media-engine/build_atlas.py [--edition nyc-billboard] [--cell 96]
"""

import argparse
import json
import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE_DIR))

from PIL import Image  # noqa: E402

CACHE_DIR = ENGINE_DIR / "cache"
THUMBS_DIR = CACHE_DIR / "thumbs"
ATLAS_DIR = CACHE_DIR / "atlas"
SHEET = 4096
PAD = 2


def build(edition, cell, thumbs_dir=None, atlas_dir=None, field_path=None):
    thumbs_dir = thumbs_dir or THUMBS_DIR
    atlas_dir = atlas_dir or ATLAS_DIR
    field_path = field_path or (CACHE_DIR / f"field-{edition}.json")
    if not field_path.is_file():
        sys.exit(f"field data missing: {field_path.name} -- run build_field.py first")
    field = json.loads(field_path.read_text(encoding="utf-8"))
    records = [r for r in field.get("assets", []) if r.get("has_thumb") and r.get("sha")]

    cols = SHEET // cell
    per_sheet = cols * cols
    inner = cell - 2 * PAD

    atlas_dir.mkdir(parents=True, exist_ok=True)
    for old in atlas_dir.glob("sheet-*.jpg"):
        old.unlink()

    index = {}
    sheet_img = None
    sheet_no = -1
    placed = 0
    missing = 0

    def flush(img, n):
        if img is not None:
            img.save(atlas_dir / f"sheet-{n}.jpg", "JPEG", quality=82, optimize=True)

    for i, rec in enumerate(records):
        sha = rec["sha"]
        tp = thumbs_dir / f"{sha}.jpg"
        if not tp.is_file():
            missing += 1
            continue
        target_sheet = i // per_sheet
        if target_sheet != sheet_no:
            flush(sheet_img, sheet_no)
            sheet_no = target_sheet
            sheet_img = Image.new("RGB", (SHEET, SHEET), (244, 241, 238))  # warm off-white
        slot = i % per_sheet
        col, row = slot % cols, slot // cols
        cx, cy = col * cell + PAD, row * cell + PAD
        try:
            with Image.open(tp) as im:
                im = im.convert("RGB")
                w, h = im.size
                scale = inner / max(w, h)
                nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
                im = im.resize((nw, nh), Image.LANCZOS)
        except Exception:
            missing += 1
            continue
        # center within the inner box
        ox = cx + (inner - nw) // 2
        oy = cy + (inner - nh) // 2
        sheet_img.paste(im, (ox, oy))
        index[sha] = {"sheet": sheet_no, "x": ox, "y": oy, "w": nw, "h": nh,
                      "aspect": round(nw / nh, 4)}
        placed += 1

    flush(sheet_img, sheet_no)

    manifest = {
        "edition": edition,
        "sheet_size": SHEET,
        "cell": cell,
        "sheets": sheet_no + 1,
        "count": placed,
        "tiles": index,
    }
    (atlas_dir / "atlas-index.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return manifest, len(records), placed, missing


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--edition", default="nyc-billboard")
    p.add_argument("--cell", type=int, default=96, help="atlas cell size in px")
    p.add_argument("--thumbs-dir", default=None,
                   help="directory of {sha[:16]}.jpg thumbnails (default the local ingest "
                        "cache; CI passes one materialised from R2 by fetch_thumbs.py)")
    p.add_argument("--atlas-dir", default=None,
                   help="output directory for sheet-*.jpg + atlas-index.json "
                        "(default cache/atlas)")
    p.add_argument("--field", default=None,
                   help="path to field-{edition}.json (default cache/field-{edition}.json)")
    args = p.parse_args()

    thumbs_dir = Path(args.thumbs_dir) if args.thumbs_dir else THUMBS_DIR
    atlas_dir = Path(args.atlas_dir) if args.atlas_dir else ATLAS_DIR
    field_path = Path(args.field) if args.field else None

    manifest, n_records, placed, missing = build(
        args.edition, args.cell, thumbs_dir, atlas_dir, field_path)
    cols = SHEET // args.cell
    idx_kb = (atlas_dir / "atlas-index.json").stat().st_size / 1024
    sheet_mb = sum(f.stat().st_size for f in atlas_dir.glob("sheet-*.jpg")) / (1024 * 1024)
    print(f"[build_atlas] edition={args.edition} cell={args.cell}px  ({cols}x{cols}={cols*cols}/sheet)")
    print(f"[build_atlas] thumbs dir            : {thumbs_dir}")
    print(f"[build_atlas] thumb-bearing records : {n_records}")
    print(f"[build_atlas] tiles placed          : {placed}")
    print(f"[build_atlas] missing/failed         : {missing}")
    print(f"[build_atlas] sheets                 : {manifest['sheets']}")
    print(f"[build_atlas] wrote {atlas_dir}  (sheets {sheet_mb:.1f} MB, index {idx_kb:.1f} KB)")


if __name__ == "__main__":
    main()
