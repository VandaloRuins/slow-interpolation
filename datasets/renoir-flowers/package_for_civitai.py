"""Package raw/ + captions.txt into a CivitAI-ready ZIP.

Output: renoir-flowers-civitai.zip in this directory. Each image is paired
with a sibling .txt of the same basename, content = the caption for that
image. The 5 validation hold-out images named in
docs/findings/lora-training.md are moved into validation/ and excluded
from the training ZIP.

Idempotent. Re-running rebuilds the ZIP from scratch.
"""
from __future__ import annotations

import csv
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
CAPTIONS = ROOT / "captions.txt"
STAGING = ROOT / "_civitai_staging"
VAL = ROOT / "validation"
ZIP_OUT = ROOT / "renoir-flowers-civitai.zip"

VALIDATION = {
    "pierre-auguste-renoir-roses-in-a-vase-1941-14-cleveland-museum-of-art.jpg",
    "pierre-auguste-renoir-mixed-flowers-in-an-earthenware-pot-google-art-project.jpg",
    "pierre-auguste-renoir-anemones-an-mones-bf1167-barnes-foundation.jpg",
    "pierre-auguste-renoir-chrysanthemums-1933-1173-art-institute-of-chicago.jpg",
    "pierre-auguste-renoir-geraniums-in-a-copper-basin-11521194565.jpg",
}


def main() -> int:
    # Load captions
    caps: dict[str, str] = {}
    with CAPTIONS.open(encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            name, cap = line.split("\t", 1)
            caps[name] = cap

    # Cross-check: every raw/*.jpg has a caption
    raws = sorted(p.name for p in RAW.glob("*.jpg"))
    missing = [r for r in raws if r not in caps]
    if missing:
        print(f"[error] {len(missing)} images have no caption row:", file=sys.stderr)
        for m in missing[:10]:
            print(f"   {m}", file=sys.stderr)
        return 1

    # Reset staging dirs
    if STAGING.exists():
        shutil.rmtree(STAGING)
    STAGING.mkdir()
    VAL.mkdir(exist_ok=True)
    # Clear any stale validation files
    for p in VAL.glob("*"):
        if p.is_file():
            p.unlink()

    # Materialise pairs, splitting train vs validation
    train_count = 0
    val_count = 0
    for name in raws:
        stem = Path(name).stem
        src_img = RAW / name
        cap_text = caps[name]
        if name in VALIDATION:
            shutil.copy2(src_img, VAL / name)
            (VAL / f"{stem}.txt").write_text(cap_text, encoding="utf-8")
            val_count += 1
        else:
            shutil.copy2(src_img, STAGING / name)
            (STAGING / f"{stem}.txt").write_text(cap_text, encoding="utf-8")
            train_count += 1

    # Write the ZIP
    if ZIP_OUT.exists():
        ZIP_OUT.unlink()
    with zipfile.ZipFile(ZIP_OUT, "w", zipfile.ZIP_STORED) as zf:
        for p in sorted(STAGING.iterdir()):
            zf.write(p, arcname=p.name)

    size_mb = ZIP_OUT.stat().st_size / (1024 * 1024)
    print(f"training pairs: {train_count}")
    print(f"validation pairs: {val_count} (in validation/)")
    print(f"ZIP: {ZIP_OUT.name} ({size_mb:.1f} MB)")

    not_found = [v for v in VALIDATION if not (VAL / v).exists()]
    if not_found:
        print(f"[warn] {len(not_found)} validation images not in raw/:", file=sys.stderr)
        for n in not_found:
            print(f"   {n}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
