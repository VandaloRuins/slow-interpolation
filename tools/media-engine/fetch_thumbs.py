"""
fetch_thumbs.py -- materialise the thumbnail set from R2 into the sha-named layout
that build_field.py and build_atlas.py read.

WHY THIS EXISTS
---------------
The field and atlas builders only ever read a LOCAL cache keyed by sha
(cache/thumbs/{sha256[:16]}.jpg), which is why the whole Glance rebuild could only run on
the machine that ran the ingest -- and why media contributed server-side could never appear.

But the thumbnails were never actually missing from R2. `ingest.py` already uploads every
one on both the photo path (:477) and the video-poster path (:448), keyed by ASSET KEY at
`thumbs/<key>`. Measured 2026-07-30: 1132 objects covering 1132 of 1133 catalogue assets,
33.1 MB total (the single gap is a .docx, which correctly has no thumbnail).

The catalogue carries both `key` and `sha256` per asset, so the key -> sha mapping needed to
rename them into the builders' expected layout is already available. That makes this a pure
download-and-rename step: no ingest change, no dual-write to a second prefix, no backfill.

DERIVED ARTIFACT: writes only thumbnails into the directory it is given. Reads the catalogue,
never writes it; never touches originals.

Usage:
    py -3.11 tools/media-engine/fetch_thumbs.py --out glance-bundle/thumbs
    py -3.11 tools/media-engine/fetch_thumbs.py --out glance-bundle/thumbs --force
"""

import argparse
import concurrent.futures as cf
import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
TOOLS_DIR = ENGINE_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))

import media_store  # noqa: E402

PREFIX = "thumbs/"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--edition", default="nyc-billboard")
    p.add_argument("--out", required=True, help="directory to write {sha[:16]}.jpg into")
    p.add_argument("--force", action="store_true", help="re-download files already present")
    p.add_argument("--workers", type=int, default=16)
    args = p.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    env = media_store.load_env()
    client = media_store.r2_client(env)
    bucket = media_store.bucket_name(env)

    catalogue = media_store.read_catalogue(args.edition)
    assets = catalogue.get("assets", [])

    # One LIST instead of a HEAD/GET per asset: most of the catalogue has a thumbnail, but
    # documents legitimately do not, and probing each one would turn a normal build into
    # ~1k pointless 404s.
    remote = {o["key"] for o in media_store.list_objects(PREFIX, client, env)}

    todo, no_thumb, cached = [], [], 0
    for a in assets:
        sha, key = a.get("sha256"), a.get("key")
        if not sha or not key:
            continue
        if PREFIX + key not in remote:
            no_thumb.append(key)
            continue
        dst = out / f"{sha[:16]}.jpg"
        if dst.is_file() and not args.force:
            cached += 1
            continue
        todo.append((PREFIX + key, dst))

    print(f"[fetch_thumbs] edition={args.edition}")
    print(f"[fetch_thumbs] catalogue assets   : {len(assets)}")
    print(f"[fetch_thumbs] thumbs in R2       : {len(remote)}")
    print(f"[fetch_thumbs] already local      : {cached}")
    print(f"[fetch_thumbs] to download        : {len(todo)}")
    print(f"[fetch_thumbs] assets w/o thumb   : {len(no_thumb)}")
    for k in no_thumb[:5]:
        print(f"[fetch_thumbs]   no thumb: {k}")
    if len(no_thumb) > 5:
        print(f"[fetch_thumbs]   ... and {len(no_thumb) - 5} more")

    failed = []

    def dl(item):
        key, dst = item
        try:
            client.download_file(bucket, key, str(dst))
        except Exception as e:  # noqa: BLE001
            failed.append((key, str(e)[:90]))

    if todo:
        with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
            list(ex.map(dl, todo))

    have = len(list(out.glob("*.jpg")))
    print(f"[fetch_thumbs] downloaded         : {len(todo) - len(failed)}")
    if failed:
        print(f"[fetch_thumbs] FAILED             : {len(failed)}")
        for k, e in failed[:5]:
            print(f"[fetch_thumbs]   {k}: {e}")
    print(f"[fetch_thumbs] thumbs in {out}: {have}")

    # Fail loudly rather than silently shipping a field full of colourless tiles.
    if failed:
        sys.exit(f"FAIL: {len(failed)} thumbnail(s) could not be downloaded.")


if __name__ == "__main__":
    main()
