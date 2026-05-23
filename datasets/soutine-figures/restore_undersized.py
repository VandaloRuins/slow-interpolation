"""Restore originals where the Gemini-driven crop produced an undersized result.

Detection: a "good" crop has short side >= 600 px (a deliberate margin below
the 768 LoRA-training target, to catch cases where Gemini bbox was clearly
wrong). When a crop drops below this, the most likely cause is a Gemini
bbox misread; restoring the original is safer than training on a
thumbnail.

Files restored stay in raw/ (so they remain candidates) but are flagged in
review.json with `crop_pass1_failed = true`. A subsequent pass-2 review can
re-prompt those specifically.

Reads:
    review.json
    processed.json
    raw_orig/<name>.jpg

Writes:
    raw/<name>.jpg (restored from raw_orig)
    review.json (with crop_pass1_failed flag)
    processed.json (status updated to "reverted")
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

MIN_SHORT = 600


def main() -> int:
    if not LOG.exists():
        sys.exit("processed.json missing")
    log = json.loads(LOG.read_text(encoding="utf-8"))
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    reverted = 0

    for name, entry in sorted(log.items()):
        if entry.get("status") != "done":
            continue
        short = min(entry.get("after_w", 0), entry.get("after_h", 0))
        if short >= MIN_SHORT:
            continue
        # Restore
        backup = ORIG / name
        dest = RAW / name
        if not backup.exists():
            print(f"[skip] {name}: no backup at raw_orig/")
            continue
        shutil.copy2(backup, dest)
        with Image.open(dest) as im:
            ow, oh = im.size
        log[name]["status"] = "reverted"
        log[name]["reverted_reason"] = f"crop produced {entry['after_w']}x{entry['after_h']}, restored to {ow}x{oh}"
        if name in review:
            review[name]["crop_pass1_failed"] = True
        reverted += 1
        print(f"[revert] {name}: {entry['after_w']}x{entry['after_h']} -> {ow}x{oh}")

    LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    REVIEW.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nreverted {reverted} undersized crops; queued for pass-2 review")
    return 0


if __name__ == "__main__":
    sys.exit(main())
