#!/usr/bin/env python3
"""Build a Glance tier-0 archive from a Dataset Mosaic collection.

This is the data half of the Glance-based replacement for the dataset-curation
gallery (docs/manual/gallery.md). It never touches datasets/<name>/ except to
read; the old gallery keeps working unchanged.

Pipeline:
  1. Read the mosaic's own truth from datasets/<name>/:
       metadata.csv        audit flags (flags_frame / flags_white_bg / flags_watermark),
                           title, year, museum collection, processed marker
       captions.json       the Phase-4 training captions
       phashes.json        cached perceptual hashes (same cache build_gallery.py uses)
       gallery-state.json  the student's live flags + staged crops
  2. Stage raw/ into a sub-folder tree, one folder per audit-status cluster
     (watermark > was-framed > white-border > clean, in precedence order),
     with a `.txt` sidecar per image carrying the training caption. Both are
     conventions the stock importer reads natively.
  3. Run the STOCK Glance importer (make_archive.py, a released dependency,
     never modified) — sub-folders become field clusters, sidecars become
     captions, and it self-verifies the sha16 join before declaring success.
  4. Enrich data/catalogue.json — per the contract the catalogue is the live
     truth for clustering and search — with searchable scene tags:
     audit flags, near-duplicate families (dup, dup-N at Hamming <= 10, the
     same threshold as build_gallery.py), student state (my-flagged,
     my-cropped), processed marker, year; plus venue = museum collection,
     artists, and "Title, year." prefixed to the caption.
  5. Re-verify the join across all four artifacts after enrichment.

Usage:
  py -3.11 tools/mosaic-glance/build_mosaic_archive.py --dataset renoir-flowers
  py -3.11 tools/mosaic-glance/build_mosaic_archive.py --dataset soutine-figures --out <dir>
"""

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def glance_dir() -> Path:
    """Locate the glance viewer checkout (it holds make_archive.py).

    This is a public repo, so no machine path and no sibling checkout name is
    baked in. Set GLANCE_DIR. Resolved at use, not at import, so --help works
    without it.
    """
    d = os.environ.get("GLANCE_DIR")
    if not d:
        sys.exit("set GLANCE_DIR to the glance viewer checkout (it holds make_archive.py)")
    return Path(d)


DUP_THRESHOLD = 10  # matches DUP_THRESHOLD in datasets/<name>/build_gallery.py

CLUSTERS = ["watermark", "was-framed", "white-border", "clean"]  # precedence order


def slugify(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-") or "unknown"


def load_truth(ds):
    meta = {}
    with open(ds / "metadata.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            meta[row["filename"]] = row
    captions = {}
    cap_path = ds / "captions.json"
    if cap_path.exists():
        for rec in json.loads(cap_path.read_text(encoding="utf-8")):
            captions[rec["filename"]] = rec.get("caption", "")
    phashes = {}
    ph_path = ds / "phashes.json"
    if ph_path.exists():
        for fn, rec in json.loads(ph_path.read_text(encoding="utf-8")).items():
            if rec.get("phash"):
                phashes[fn] = rec["phash"]
    state = {"flags": {}, "crops": {}}
    st_path = ds / "gallery-state.json"
    if st_path.exists():
        st = json.loads(st_path.read_text(encoding="utf-8"))
        state["flags"] = st.get("flags", {}) or {}
        state["crops"] = st.get("crops", {}) or {}
    # A state crop is BAKED (already applied to raw/ by apply_browser_crops.py)
    # when the file's processed.json record mentions browser_crop. Baked crops
    # must not be applied a second time at stage time.
    baked = set()
    pr_path = ds / "processed.json"
    if pr_path.exists():
        for fn, rec in json.loads(pr_path.read_text(encoding="utf-8")).items():
            blob = json.dumps(rec) if not isinstance(rec, str) else rec
            if "browser_crop" in blob:
                baked.add(fn)
    return meta, captions, phashes, state, baked


def classify(row):
    """Exclusive cluster by precedence; every flag still lands in tags."""
    if not row:
        return "clean"
    if row.get("flags_watermark") == "yes":
        return "watermark"
    if row.get("flags_frame") == "yes":
        return "was-framed"
    if row.get("flags_white_bg") == "yes":
        return "white-border"
    return "clean"


def dup_families(files, phashes):
    """Union-find over Hamming distance of cached phashes, threshold <= 10.
    Returns {filename: family_index} for families of size >= 2 only."""
    hashed = [f for f in files if f in phashes]
    ints = {f: int(phashes[f], 16) for f in hashed}
    parent = {f: f for f in hashed}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, a in enumerate(hashed):
        for b in hashed[i + 1:]:
            if bin(ints[a] ^ ints[b]).count("1") <= DUP_THRESHOLD:
                parent[find(a)] = find(b)

    groups = {}
    for f in hashed:
        groups.setdefault(find(f), []).append(f)
    fams = sorted((sorted(g) for g in groups.values() if len(g) >= 2),
                  key=lambda g: g[0])
    return {f: i + 1 for i, g in enumerate(fams) for f in g}


def apply_crop(path, crop):
    """Stage-time render of one staged browser crop, mirroring
    apply_browser_crops.py: rotate first (90-degree steps), then crop the bbox
    stated in percentages of the rotated image's dimensions."""
    from PIL import Image
    st = path.stat()
    with Image.open(path) as im:
        rot = int(crop.get("rotation_cw_deg", 0) or 0)
        if rot:
            im = im.rotate(-rot, expand=True, resample=Image.BICUBIC)
        w_px, h_px = im.size
        x0 = round(crop["x"] / 100 * w_px)
        y0 = round(crop["y"] / 100 * h_px)
        x1 = round((crop["x"] + crop["w"]) / 100 * w_px)
        y1 = round((crop["y"] + crop["h"]) / 100 * h_px)
        im = im.crop((x0, y0, x1, y1))
        if path.suffix.lower() in {".jpg", ".jpeg"}:
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")  # some .jpg-named sources decode as RGBA
            params = {"quality": 95}
        else:
            params = {}
        im.save(path, **params)
    os.utime(path, (st.st_atime, st.st_mtime))  # keep the honest mtime date basis


def stage(ds, staging, meta, captions, state, baked):
    raw = ds / "raw"
    files = sorted(p.name for p in raw.iterdir()
                   if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})
    # A pending "remove" flag is a cut the student has decided but the old page
    # has not executed; a final-artworks view must not show it.
    removed = {fn for fn, v in state["flags"].items() if str(v) == "remove"}
    files = [fn for fn in files if fn not in removed]
    if removed:
        print(f"excluded {len(removed)} image(s) with a pending remove flag")
    for c in CLUSTERS:
        (staging / c).mkdir(parents=True, exist_ok=True)
    applied = set()
    for fn in files:
        cluster = classify(meta.get(fn))
        dest = staging / cluster / fn
        shutil.copy2(raw / fn, dest)  # copy2 keeps mtime, the importer's date fallback
        if fn in state["crops"] and fn not in baked:
            apply_crop(dest, state["crops"][fn])
            applied.add(fn)
        cap = captions.get(fn, "")
        if cap:
            dest.with_suffix(".txt").write_text(cap, encoding="utf-8")
    if applied:
        print(f"applied {len(applied)} staged crop(s) at stage time")
    return files, applied


def sha16_map(staging):
    out = {}
    for p in staging.rglob("*"):
        if p.is_file() and p.suffix.lower() != ".txt":
            out[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    return out


def enrich(out_dir, meta, state, fams, by_name, applied=frozenset()):
    cat_path = out_dir / "data" / "catalogue.json"
    cat = json.loads(cat_path.read_text(encoding="utf-8"))
    sha_to_name = {v: k for k, v in by_name.items()}
    touched = 0
    for asset in cat["assets"]:
        fn = sha_to_name.get(asset["sha256"][:16])
        if not fn:
            continue
        row = meta.get(fn, {})
        tags = asset["tags"]
        scene = []
        if row.get("flags_frame") == "yes":
            scene.append("was-framed")
        if row.get("flags_white_bg") == "yes":
            scene.append("white-border")
        if row.get("flags_watermark") == "yes":
            scene.append("watermark")
        if row.get("processed") == "yes":
            scene.append("processed")
        if fn in fams:
            scene += ["dup", f"dup-{fams[fn]}"]
            # subgroup is read by the viewer though absent from data-contract.md:
            # siblings sharing it pack adjacent within their cluster (layout.js)
            # and it is searched as a structural field (glance.js matchTile) --
            # both exactly the old gallery's dup-adjacency behaviour.
            tags["subgroup"] = f"dup-{fams[fn]}"
        if fn in state["crops"]:
            scene.append("my-cropped")
        if fn in applied:
            scene.append("crop-applied")  # the displayed image IS the cropped version
        if fn in state["flags"]:
            scene.append("my-" + slugify(str(state["flags"][fn])))
        year = (row.get("year") or "").strip()
        if year:
            scene.append(year)
        tags["scene"] = scene
        museum = (row.get("collection") or "").strip()
        if museum:
            # tags.venue is in the contract but the reference card renders the
            # EVENT registry's venue instead (card.js), and our events are audit
            # clusters -- so surface the museum as a searchable scene tag too.
            tags["venue"] = museum
            scene.append(slugify(museum))
        artist = (row.get("artist_recorded") or "").strip()
        if artist:
            tags["artists"] = [slugify(artist)]
        title = (row.get("title") or "").strip()
        if title:
            prefix = f"{title}, {year}." if year else f"{title}."
            tags["caption"] = f"{prefix} {tags.get('caption') or ''}".strip()
        if scene:
            # The reference search never indexes tags.scene (glance.js matchTile
            # reads event/context/date/spec/subgroup/artists/caption only), so
            # fold the tags into the caption tail to make them findable.
            tags["caption"] = f"{tags.get('caption') or ''} · tags: {' '.join(scene)}".strip()
        touched += 1
    cat_path.write_text(json.dumps(cat, ensure_ascii=False, indent=1), encoding="utf-8")
    return touched


def verify_join(out_dir):
    """The four assertions from docs/building-an-archive.md, re-run after enrichment."""
    data = out_dir / "data"
    atlas = out_dir / "atlas"
    field = json.loads((data / "field.json").read_text(encoding="utf-8"))
    cat = json.loads((data / "catalogue.json").read_text(encoding="utf-8"))
    idx = json.loads((atlas / "atlas-index.json").read_text(encoding="utf-8"))
    f_sha = {a["sha"] for a in field["assets"]}
    c_sha = {a["sha256"][:16] for a in cat["assets"]}
    t_sha = set(idx["tiles"].keys())
    d_sha = {p.stem for p in (out_dir / "thumbs").glob("*.jpg")}
    ok = f_sha == c_sha == t_sha == d_sha
    size = idx.get("sheet_size", 4096)
    inside = all(t["x"] + t["w"] <= size and t["y"] + t["h"] <= size
                 for t in idx["tiles"].values())
    hidden = [a["key"] for a in cat["assets"]
              if a["tags"].get("archived") or a["tags"].get("asset_class") == "press-kit"]
    if not ok:
        print("VERIFY FAILED: sha16 sets differ across the four artifacts", file=sys.stderr)
    if not inside:
        print("VERIFY FAILED: tile outside sheet bounds", file=sys.stderr)
    if hidden:
        print(f"VERIFY FAILED: {len(hidden)} assets would be filtered off the field", file=sys.stderr)
    return ok and inside and not hidden


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, help="name under datasets/, e.g. renoir-flowers")
    ap.add_argument("--out", default=None,
                    help="archive dir (default: tools/mosaic-glance/site, next to index.html)")
    args = ap.parse_args()

    ds = REPO / "datasets" / args.dataset
    if not (ds / "raw").is_dir():
        sys.exit(f"no raw/ under {ds}")
    out_dir = Path(args.out) if args.out else Path(__file__).resolve().parent / "site"
    out_dir.mkdir(parents=True, exist_ok=True)

    meta, captions, phashes, state, baked = load_truth(ds)
    staging = Path(tempfile.mkdtemp(prefix=f"mosaic-glance-{args.dataset}-"))
    try:
        files, applied = stage(ds, staging, meta, captions, state, baked)
        print(f"staged {len(files)} images into {len(CLUSTERS)} audit clusters")

        cmd = [sys.executable, str(glance_dir() / "make_archive.py"),
               "--src", str(staging), "--out", str(out_dir),
               "--collection", args.dataset, "--clean"]
        subprocess.run(cmd, check=True)  # its self-verify is the build gate

        fams = dup_families(files, phashes)
        by_name = sha16_map(staging)
        n = enrich(out_dir, meta, state, fams, by_name, applied)
        dup_count = len(fams)
        print(f"enriched {n} catalogue records "
              f"({dup_count} images in {len(set(fams.values()))} dup families)")

        if not verify_join(out_dir):
            sys.exit(2)
        print("VERIFY OK: join intact after enrichment")
    finally:
        shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    main()
