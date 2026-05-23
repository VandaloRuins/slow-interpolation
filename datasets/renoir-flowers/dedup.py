"""Perceptual-hash dedup of raw/. Near-duplicate pairs are reported; the
larger-resolution version is kept, the smaller is moved to rejected/dupes/.
"""
from __future__ import annotations
from pathlib import Path
import shutil
from PIL import Image
import imagehash

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
DUPES = ROOT / "rejected" / "dupes"
DUPES.mkdir(parents=True, exist_ok=True)

THRESHOLD = 8  # hamming distance for "same image"

files = sorted(RAW.glob("*.jpg"))
print(f"hashing {len(files)} files")

records = []
for fp in files:
    try:
        with Image.open(fp) as im:
            h = imagehash.phash(im)
            records.append((fp, h, im.width * im.height))
    except Exception as e:
        print(f"[skip] {fp.name}: {e}")

# Find near-duplicates
seen = set()
groups = []
for i, (fp1, h1, _) in enumerate(records):
    if fp1 in seen:
        continue
    grp = [(fp1, h1, records[i][2])]
    for fp2, h2, sz2 in records[i + 1 :]:
        if fp2 in seen:
            continue
        if h1 - h2 <= THRESHOLD:
            grp.append((fp2, h2, sz2))
            seen.add(fp2)
    if len(grp) > 1:
        groups.append(grp)
        seen.add(fp1)

print(f"\nfound {len(groups)} duplicate groups")
moved = 0
for grp in groups:
    grp.sort(key=lambda r: -r[2])  # largest first
    keep = grp[0][0]
    print(f"  keep: {keep.name}")
    for fp, _, sz in grp[1:]:
        print(f"   dup -> {fp.name} ({sz} px)")
        shutil.move(str(fp), str(DUPES / fp.name))
        moved += 1

print(f"\nmoved {moved} duplicate(s) to {DUPES}")
print(f"remaining in raw/: {len(list(RAW.glob('*.jpg')))}")
