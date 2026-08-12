"""
build_field.py -- derive the far-LOD field data for the Media Archive Viz (v1).

Reads the R2 catalogue for an edition + the LOCAL thumbnail cache
(cache/thumbs/{sha256[:16]}.jpg) and emits a small `_field.json` holding one
lean record per asset: identity + layout keys (date/event) + a dominant colour
sampled from the thumbnail. This is the data the field renders as coloured
quads when zoomed out (no image loads at far LOD) -- ~300 B/asset.

DERIVED ARTIFACT: written under cache/ (gitignored). Reads thumbs only; never
touches originals; never writes the catalogue. Zero R2 egress beyond the one
small catalogue GET. Re-run after each ingest.

Usage:
    py -3.11 tools/media-engine/build_field.py [--edition nyc-billboard] [--out PATH]
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
TOOLS_DIR = ENGINE_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(ENGINE_DIR))

import media_store  # noqa: E402
from PIL import Image  # noqa: E402

CACHE_DIR = ENGINE_DIR / "cache"
THUMBS_DIR = CACHE_DIR / "thumbs"


def thumb_path_for(sha256, thumbs_dir=None):
    """Flat-hashed thumbnail path (matches ingest.py:431 convention).

    `thumbs_dir` defaults to the local ingest cache. CI passes a directory materialised
    from R2 by fetch_thumbs.py instead, which is what lets the rebuild run without the
    machine that did the ingest.
    """
    if not sha256:
        return None
    return (thumbs_dir or THUMBS_DIR) / f"{sha256[:16]}.jpg"


def dominant_color(path):
    """Average colour of the thumbnail as #rrggbb (1px downscale). None on failure."""
    try:
        with Image.open(path) as img:
            px = img.convert("RGB").resize((1, 1), Image.LANCZOS).getpixel((0, 0))
        return "#{:02x}{:02x}{:02x}".format(px[0], px[1], px[2])
    except Exception:
        return None


def build(edition, thumbs_dir=None):
    catalogue = media_store.read_catalogue(edition)
    assets = catalogue.get("assets", [])
    records = []
    no_thumb = 0
    no_color = 0
    for a in assets:
        sha = a.get("sha256")
        tags = a.get("tags", {}) or {}
        tp = thumb_path_for(sha, thumbs_dir)
        has_thumb = bool(tp and tp.is_file())
        color = dominant_color(tp) if has_thumb else None
        if not has_thumb:
            no_thumb += 1
        elif color is None:
            no_color += 1
        caption = (tags.get("caption") or "").strip()
        records.append({
            "sha": (sha or "")[:16],
            "key": a.get("key"),
            "date": tags.get("date"),
            "event": tags.get("event"),
            "context": tags.get("context"),
            "media_type": tags.get("media_type"),
            "asset_class": tags.get("asset_class"),
            "artists": tags.get("artists") or [],
            "public": bool(tags.get("public")),
            "caption_short": caption[:120],
            "color": color,
            "has_thumb": has_thumb,
        })
    return {
        "edition": edition,
        "generated": date.today().isoformat(),
        "count": len(records),
        "no_thumb": no_thumb,
        "no_color": no_color,
        "assets": records,
    }, len(assets), no_thumb, no_color


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--edition", default="nyc-billboard")
    p.add_argument("--out", default=None,
                   help="output path (default cache/field-{edition}.json)")
    p.add_argument("--thumbs-dir", default=None,
                   help="directory of {sha[:16]}.jpg thumbnails (default the local ingest "
                        "cache; CI passes one materialised from R2 by fetch_thumbs.py)")
    args = p.parse_args()

    out = Path(args.out) if args.out else CACHE_DIR / f"field-{args.edition}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    thumbs_dir = Path(args.thumbs_dir) if args.thumbs_dir else THUMBS_DIR

    field, n_assets, no_thumb, no_color = build(args.edition, thumbs_dir)
    out.write_text(json.dumps(field, ensure_ascii=False), encoding="utf-8")

    size_kb = out.stat().st_size / 1024
    print(f"[build_field] edition={args.edition}")
    print(f"[build_field] thumbs dir         : {thumbs_dir}")
    print(f"[build_field] assets in catalogue : {n_assets}")
    print(f"[build_field] field records       : {field['count']}")
    print(f"[build_field] without a thumb     : {no_thumb}")
    print(f"[build_field] thumb but no colour  : {no_color}")
    print(f"[build_field] with colour          : {field['count'] - no_thumb - no_color}")
    print(f"[build_field] wrote {out}  ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
