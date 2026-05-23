"""Update metadata.csv with post-processing dimensions and flags.

Reads the current pixel size of every raw/*.jpg, merges with processed.json
to add columns:
  saved_width, saved_height       — current dimensions on disk
  processed                       — bool, true if cropped or upscaled
  processed_ops                   — comma-separated list of ops applied
  flags_frame / flags_white_bg / flags_watermark — bool, Gemini flags
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
META = ROOT / "metadata.csv"
RAW = ROOT / "raw"
LOG = ROOT / "processed.json"
REVIEW = ROOT / "review.json"


def main() -> int:
    Image.MAX_IMAGE_PIXELS = None
    rows = list(csv.DictReader(META.open(encoding="utf-8")))
    log = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else {}
    review = json.loads(REVIEW.read_text(encoding="utf-8")) if REVIEW.exists() else {}

    new_rows = []
    for r in rows:
        name = r["filename"]
        fp = RAW / name
        if fp.exists():
            with Image.open(fp) as im:
                sw, sh = im.size
        else:
            sw, sh = "", ""
        info = log.get(name, {})
        rv = review.get(name, {})
        ops = []
        if "operations" in info:
            ops.extend(info["operations"])
        if "pass2" in info and "operations" in info["pass2"]:
            ops.extend(info["pass2"]["operations"])
        if "manual" in info:
            ops.append("manual-crop")
        processed = info.get("status") == "done" or "manual" in info
        r["saved_width"] = sw
        r["saved_height"] = sh
        r["processed"] = "yes" if processed else "no"
        r["processed_ops"] = "; ".join(ops)
        r["flags_frame"] = "yes" if rv.get("has_physical_frame") else "no"
        r["flags_white_bg"] = "yes" if rv.get("has_white_or_paper_border") else "no"
        r["flags_watermark"] = "yes" if rv.get("has_watermark") else "no"
        r["review_notes"] = rv.get("notes", "")
        new_rows.append(r)

    # Reorder columns: keep originals first, then new fields at end
    cols = list(new_rows[0].keys())
    fieldnames = []
    for c in ["filename", "title", "year", "collection", "source_url",
              "original_width", "original_height", "saved_width", "saved_height",
              "processed", "processed_ops",
              "flags_frame", "flags_white_bg", "flags_watermark",
              "public_domain_status", "direct_url", "sha1", "license_short",
              "artist_recorded", "credit_line", "review_notes"]:
        if c in cols and c not in fieldnames:
            fieldnames.append(c)
    for c in cols:
        if c not in fieldnames:
            fieldnames.append(c)

    with META.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(new_rows)
    print(f"updated {META} with {len(new_rows)} rows")

    # Quick stats
    n_proc = sum(1 for r in new_rows if r["processed"] == "yes")
    n_frame = sum(1 for r in new_rows if r["flags_frame"] == "yes")
    n_bg = sum(1 for r in new_rows if r["flags_white_bg"] == "yes")
    n_wm = sum(1 for r in new_rows if r["flags_watermark"] == "yes")
    print(f"processed: {n_proc} / {len(new_rows)}")
    print(f"flags: frame={n_frame} white-bg={n_bg} watermark={n_wm}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
