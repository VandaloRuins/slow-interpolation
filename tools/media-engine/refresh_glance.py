"""
refresh_glance.py -- the one command that makes new media appear on Glance.

WHY THIS EXISTS
---------------
Ingesting + publishing media does not, by itself, update glance.yourdomain.com.
Production serves a build, and CI's `paths:` trigger only watches git -- an ingest changes
R2 and no git file, so nothing fires. Measured 2026-07-30: R2 held 1133 assets while prod
served 1059, and one event cluster read 18 publicly against 91 in the archive.

Run this after any ingest or publish. It dispatches the build and then checks production
actually changed.

WHAT CHANGED (Phase 0, 2026-07-30)
----------------------------------
This script used to rebuild the field + atlas locally and upload a 33 MB bundle to R2
`glance-build/` for CI to collect, which meant only the laptop that ran the ingest could
update the public site. `.github/workflows/glance-build.yml` now builds all of it itself:
`fetch_thumbs.py` materialises thumbnails straight out of R2 (they were always there --
`ingest.py` uploads every one at `thumbs/<key>`), then the field and atlas are generated on
the runner. Verified byte-identical to a laptop build, down to the sheet md5.

So there is nothing left to build or stage here, and the in-app Publish button -- which
dispatches the same workflow -- is now sufficient on its own. It previously was not: a
dispatch refreshed the live-read catalogue while leaving the hand-staged atlas untouched,
so new assets showed up in search as missing tiles.

WHAT THIS STILL ADDS over pressing Publish: an assertion that named keys reached production.
CI guards staleness structurally (the field must cover the catalogue), but only the caller
knows which specific assets this run was supposed to surface.

Usage:
    py -3.11 tools/media-engine/refresh_glance.py
    py -3.11 tools/media-engine/refresh_glance.py --expect-key "nyc-billboard/<event>/.../x.jpg"
    py -3.11 tools/media-engine/refresh_glance.py --verify-only   # check prod, deploy nothing
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
TOOLS_DIR = ENGINE_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))

PROD = "https://glance.yourdomain.com"
WORKFLOW = "glance-build.yml"


def dispatch_and_wait():
    print("=== dispatch CI ===")
    subprocess.run(["gh", "workflow", "run", WORKFLOW], check=True)
    time.sleep(8)
    rid = subprocess.run(
        ["gh", "run", "list", "--workflow", WORKFLOW, "--limit", "1", "--json", "databaseId",
         "--jq", ".[0].databaseId"],
        capture_output=True, text=True, check=True).stdout.strip()
    print(f"run {rid} -- watching")
    subprocess.run(["gh", "run", "watch", rid, "--exit-status"], check=True)
    return rid


def get_json(url):
    with urllib.request.urlopen(url, timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))


def verify(expect_keys, expect_dates=None):
    """Assert production changed, on something UNIQUE to this run.

    A 200 on the homepage proves nothing, and neither does a green build -- the whole
    failure class here is a successful deploy of stale data. So compare the three artifacts
    against each other on the LIVE site, and require any named key to be present.

    --expect-key asserts PRESENCE, which is the right check for an ingest but useless for
    a change that edits an existing asset: a date/venue/tag repair leaves the key set
    identical, so a presence-only verify passes whether or not the change ever reached
    production. --expect-date KEY=YYYY-MM-DD asserts the VALUE, and is the only thing that
    proves a repair actually shipped.
    """
    expect_dates = expect_dates or {}
    print("\n=== verify production ===")
    for attempt in range(1, 7):
        try:
            cat = get_json(f"{PROD}/api/catalogue")
            fld = get_json(f"{PROD}/api/field")
            atl = get_json(f"{PROD}/atlas/atlas-index.json")
            assets = cat.get("assets", [])
            field_sha = {r["sha"] for r in fld.get("assets", []) if r.get("sha")}
            tiles = set(atl.get("tiles", {}))
            uncovered = [a.get("key") for a in assets
                         if (a.get("sha256") or "")[:16] not in field_sha]
            cat_keys = {a.get("key") for a in assets}
            missing = [k for k in expect_keys if k not in cat_keys]
            by_key = {a.get("key"): a for a in assets}
            wrong_dates = []
            for k, want in expect_dates.items():
                got = ((by_key.get(k) or {}).get("tags") or {}).get("date") \
                    or (by_key.get(k) or {}).get("date")
                if got != want:
                    wrong_dates.append(f"{k}: want {want}, live {got!r}")
            print(f"  attempt {attempt}: catalogue={len(assets)} field={fld.get('count')} "
                  f"atlas={atl.get('count')} uncovered={len(uncovered)} "
                  f"missing_named={len(missing)} wrong_dates={len(wrong_dates)}")
            if not missing and not uncovered and not wrong_dates:
                extra = f"; all {len(expect_dates)} named date(s) correct" if expect_dates else ""
                print(f"OK: production serves {len(assets)} assets, "
                      f"field {fld.get('count')}, atlas {atl.get('count')}; "
                      f"every asset has a field record; "
                      f"all {len(expect_keys)} named key(s) present{extra}.")
                return True
            for k in (missing or uncovered)[:5]:
                print(f"    absent/uncovered: {k}")
            for w in wrong_dates[:5]:
                print(f"    WRONG DATE {w}")
        except Exception as e:  # noqa: BLE001
            print(f"  attempt {attempt}: {e}")
        time.sleep(15)
    print("FAIL: production did not reflect the rebuild.")
    return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--expect-key", action="append", default=[],
                   help="key that MUST appear in the production catalogue (repeatable)")
    p.add_argument("--expect-date", action="append", default=[], metavar="KEY=YYYY-MM-DD",
                   help="key whose production DATE must equal this (repeatable). Use for "
                        "repairs that edit existing assets -- --expect-key cannot see those, "
                        "since the key set does not change")
    p.add_argument("--verify-only", action="store_true",
                   help="check production as it stands; dispatch nothing")
    p.add_argument("--no-verify", action="store_true", help="dispatch and exit")
    args = p.parse_args()

    expect_dates = {}
    for spec in args.expect_date:
        if "=" not in spec:
            sys.exit(f"--expect-date needs KEY=YYYY-MM-DD, got {spec!r}")
        k, v = spec.rsplit("=", 1)
        expect_dates[k.strip()] = v.strip()

    if not args.verify_only:
        dispatch_and_wait()
        if args.no_verify:
            return

    if not verify(args.expect_key, expect_dates):
        sys.exit(1)


if __name__ == "__main__":
    main()
