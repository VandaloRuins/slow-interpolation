"""Package raw/ + captions.txt into a CivitAI-ready ZIP.

Mirror of datasets/renoir-flowers/package_for_civitai.py. Output:
soutine-figures-civitai.zip alongside this script. Five images held out as
validation set (named below; can be edited by Luca before training).

Idempotent. Re-running rebuilds the ZIP from scratch.
"""
from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
CAPTIONS = ROOT / "captions.txt"
STAGING = ROOT / "_civitai_staging"
VAL = ROOT / "validation"
ZIP_OUT = ROOT / "soutine-figures-civitai.zip"

# Validation hold-out. Five filenames picked for visual diversity across
# the Soutine corpus (standing male, seated female, choirboy, page boy,
# self-portrait). Manual selection; Luca edits this list before packaging
# the final ZIP if a piece reads as a stronger test case.
VALIDATION_HINTS = [
    "self-portrait",            # one self-portrait
    "femme-en-bleu",            # one seated female in dark dress
    "ragazzo-di-coro",          # one choirboy
    "ragazzo-ai-piani",         # one page boy
    "piccolo-pasticcere",       # one pastry cook
]


def pick_validation(raws: list[str]) -> set[str]:
    """First match per hint; supports the manual diversity criteria above."""
    picked: list[str] = []
    used = set()
    for hint in VALIDATION_HINTS:
        for r in raws:
            if r in used:
                continue
            if hint in r.lower():
                picked.append(r)
                used.add(r)
                break
    return set(picked)


def main() -> int:
    caps: dict[str, str] = {}
    with CAPTIONS.open(encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            name, cap = line.split("\t", 1)
            caps[name] = cap

    raws = sorted(p.name for p in RAW.glob("*.jpg"))
    missing = [r for r in raws if r not in caps]
    if missing:
        print(f"[error] {len(missing)} images have no caption row:", file=sys.stderr)
        for m in missing[:10]:
            print(f"   {m}", file=sys.stderr)
        return 1

    validation = pick_validation(raws)

    if STAGING.exists():
        shutil.rmtree(STAGING)
    STAGING.mkdir()
    VAL.mkdir(exist_ok=True)
    for p in VAL.glob("*"):
        if p.is_file():
            p.unlink()

    train_count = val_count = 0
    for name in raws:
        stem = Path(name).stem
        src_img = RAW / name
        cap_text = caps[name]
        if name in validation:
            shutil.copy2(src_img, VAL / name)
            (VAL / f"{stem}.txt").write_text(cap_text, encoding="utf-8")
            val_count += 1
        else:
            shutil.copy2(src_img, STAGING / name)
            (STAGING / f"{stem}.txt").write_text(cap_text, encoding="utf-8")
            train_count += 1

    if ZIP_OUT.exists():
        ZIP_OUT.unlink()
    with zipfile.ZipFile(ZIP_OUT, "w", zipfile.ZIP_STORED) as zf:
        for p in sorted(STAGING.iterdir()):
            zf.write(p, arcname=p.name)

    size_mb = ZIP_OUT.stat().st_size / (1024 * 1024)
    print(f"training pairs: {train_count}")
    print(f"validation pairs: {val_count} (in validation/)")
    print(f"ZIP: {ZIP_OUT.name} ({size_mb:.1f} MB)")
    if val_count < len(VALIDATION_HINTS):
        print(
            f"[warn] only {val_count} of {len(VALIDATION_HINTS)} validation hints matched.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
