"""
check_build_freshness.py -- refuse to deploy a Glance build that ships stale data.

WHY THIS EXISTS
---------------
The failure this pipeline actually produces is not a crash. It is a GREEN build that
serves old data, which reads as success everywhere you look. Measured 2026-07-30:
production served 1059 assets and a 1060-record field while R2 held 1133, and one event
cluster read 18 publicly against 91 in the archive. Every status check was 200. Nothing
in CI objected, because nothing was comparing the artifacts to each other.

So this asserts the invariant directly, against the assembled dist, before it deploys.

TWO SIGNALS, DELIBERATELY NOT TREATED THE SAME
----------------------------------------------
* A missing FIELD RECORD is staleness, always, and is fatal. build_field.py emits one
  record per catalogue asset whether or not a thumbnail exists, so records only go
  missing when the field was not rebuilt against the current catalogue -- and then they
  go missing in bulk.

* A missing ATLAS TILE is ambiguous, so it is fatal only in bulk. ingest.py's push of
  each thumbnail to R2 is best-effort -- wrapped in try/except, logs a warning, continues
  (ingest.py:477-480) -- so a single asset can legitimately reach the catalogue with no
  thumbnail in the bucket. Treating that as fatal would let ONE failed thumbnail upload
  block every future deploy, which trades a silent-staleness bug for a self-inflicted
  outage. An atlas that genuinely did not rebuild is missing a large FRACTION, not one.

Usage:
    python tools/media-engine/check_build_freshness.py --dist dist
"""

import argparse
import json
import sys
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dist", default="dist", help="assembled dist/ directory")
    p.add_argument("--tile-tolerance-pct", type=float, default=1.0,
                   help="missing tiles above this %% of public assets are fatal")
    p.add_argument("--tile-tolerance-min", type=int, default=3,
                   help="always tolerate at least this many missing tiles")
    args = p.parse_args()

    dist = Path(args.dist)
    cat = json.loads((dist / "data" / "catalogue.json").read_text(encoding="utf-8"))
    fld = json.loads((dist / "data" / "field.json").read_text(encoding="utf-8"))
    atl = json.loads((dist / "atlas" / "atlas-index.json").read_text(encoding="utf-8"))

    assets = cat.get("assets", [])
    field_sha = {r["sha"] for r in fld.get("assets", []) if r.get("sha")}
    tiles = set(atl.get("tiles", {}))

    missing_field, missing_tile = [], []
    for a in assets:
        sha = (a.get("sha256") or "")[:16]
        if not sha:
            continue
        if sha not in field_sha:
            missing_field.append(a.get("key"))
        elif a.get("thumb") and sha not in tiles:
            # claims a thumbnail but has no tile
            missing_tile.append(a.get("key"))

    tile_budget = max(args.tile_tolerance_min,
                      int(len(assets) * args.tile_tolerance_pct / 100))

    print(f"[freshness] public assets     : {len(assets)}")
    print(f"[freshness] field records     : {len(field_sha)}")
    print(f"[freshness] atlas tiles       : {len(tiles)}")
    print(f"[freshness] missing field rec : {len(missing_field)}  (any is fatal)")
    print(f"[freshness] missing atlas tile: {len(missing_tile)}  (fatal above {tile_budget})")

    fatal = []

    if missing_field:
        for k in missing_field[:10]:
            print(f"  STALE (no field record): {k}")
        if len(missing_field) > 10:
            print(f"  ... and {len(missing_field) - 10} more")
        fatal.append(
            f"{len(missing_field)} catalogue asset(s) have no field record -- the field "
            "was not rebuilt against the current catalogue"
        )

    if missing_tile:
        for k in missing_tile[:10]:
            print(f"  no atlas tile: {k}")
        if len(missing_tile) > 10:
            print(f"  ... and {len(missing_tile) - 10} more")
        if len(missing_tile) > tile_budget:
            fatal.append(
                f"{len(missing_tile)} asset(s) have no atlas tile, over the tolerance of "
                f"{tile_budget} -- that is an atlas that did not rebuild, not a few "
                "thumbnails that failed to upload"
            )
        else:
            # Worth surfacing in the run log: it means an ingest's best-effort thumbnail
            # push to R2 failed, and those assets will render blank in the field.
            print(f"::warning title=Glance thumbnails missing::{len(missing_tile)} asset(s) "
                  "have no thumbnail in R2 and will render blank. Within tolerance, "
                  "deploying anyway.")

    if fatal:
        sys.exit("FAIL: " + "; ".join(fatal))

    print(f"OK: field covers all {len(assets)} public assets.")


if __name__ == "__main__":
    main()
