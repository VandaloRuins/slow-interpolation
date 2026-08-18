#!/usr/bin/env python3
"""glance_unhide.py -- bring named assets back onto the field.

Hiding is reversible by design, but until now it was reversible only from a
signed-in browser: `glance_curate.js` posts the whole list to the edge function,
which gates on an editor session. That leaves two ways to un-hide, and both are
bad. The in-page "restore N hidden" button calls `hidden.clear()`, so it restores
EVERYTHING -- on 2026-08-18 that would have resurrected 19 chair pieces and 4
hands pieces that two standing culls had deliberately removed. The alternative
was hand-posting `replace: true` with a rebuilt list, where one wrong entry has
the same effect and no confirmation step.

So this does the narrow thing the edge function's own `unhide` branch does: a
DELETE on `glance_hidden` scoped to a collection and an explicit key list. It
reaches the table directly with the service-role key, which is the same client
the edge function uses internally (`admin`) and the same one
`glance_decisions_count.py` already reads this table with. What it does NOT do is
rebuild the list, so a key it was never asked about cannot move.

    py -3.11 tools/glance_unhide.py arendt/action_snow.mp4            # dry run
    py -3.11 tools/glance_unhide.py --apply arendt/action_snow.mp4

THE GUARD. Two culls in this project are standing artistic decisions, not
housekeeping: no chair (2026-08-14) and no human hands (2026-08-13). A key
matching either is refused unless --force is passed, because the whole reason
this tool exists is that the blunt instrument took them down by accident.

Verification reads the PUBLIC removals route afterwards, never the table, so
what gets reported is what a viewer of the field actually gets.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

COLLECTION = "ledwall"

# The two standing culls. Substring match on the key, deliberately broad: a
# near-miss that refuses costs one --force, a near-miss that proceeds is
# invisible until the founder sees a chair back on the field.
PROTECTED = ("chair", "polish", "hands", "dishes", "knead", "sweep")


def env(name: str) -> str | None:
    """Read one value from tools/.env without putting it on a command line."""
    try:
        for line in (ROOT / "tools" / ".env").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        return None
    return None


def fetch(url: str, headers: dict | None = None, data: bytes | None = None,
          method: str = "GET") -> dict | list:
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("keys", nargs="+", help="asset keys to un-hide, e.g. arendt/action_snow.mp4")
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("--collection", default=COLLECTION)
    ap.add_argument("--force", action="store_true",
                    help="allow a key matching a standing cull (chair / hands)")
    args = ap.parse_args()

    supa = env("SI_SUPABASE_URL") or env("SUPABASE_URL")
    srk = env("SI_SUPABASE_SERVICE_ROLE_KEY") or env("SUPABASE_SERVICE_ROLE_KEY")
    anon = env("SI_SUPABASE_ANON_KEY")
    if not (supa and srk and anon):
        print("missing SI_SUPABASE_* in tools/.env", file=sys.stderr)
        return 2
    admin = {"apikey": srk, "Authorization": f"Bearer {srk}",
             "Content-Type": "application/json"}

    want = list(dict.fromkeys(args.keys))

    blocked = [k for k in want if any(p in k.lower() for p in PROTECTED)]
    if blocked and not args.force:
        print("REFUSING: these match a standing cull (chair 2026-08-14 / hands 2026-08-13):",
              file=sys.stderr)
        for k in blocked:
            print(f"    {k}", file=sys.stderr)
        print("  pass --force only if that decision has actually been reversed.",
              file=sys.stderr)
        return 3

    hidden = fetch(f"{supa}/functions/v1/glance/api/removals"
                   f"?collection={args.collection}", {"apikey": anon})["hidden"]
    have = {h["key"] for h in hidden}

    present = [k for k in want if k in have]
    absent = [k for k in want if k not in have]

    print(f"collection {args.collection!r}   hidden now {len(hidden)}")
    for k in want:
        print(f"  {'un-hide ' if k in have else 'NOT HIDDEN (skip) '}{k}")
    if absent:
        print(f"\n  {len(absent)} key(s) are not in the hidden list; nothing to do for those.")
    if not present:
        print("\nNothing to do.")
        return 0
    print(f"\n  {len(hidden)} -> {len(hidden) - len(present)} hidden")

    if not args.apply:
        print("\nDRY RUN. Re-run with --apply to write.")
        return 0

    # The edge function's own `unhide` branch, done directly: a scoped delete of
    # exactly these keys. Nothing else in the list is read, rewritten or risked.
    quoted = ",".join('"' + k.replace('"', '\\"') + '"' for k in present)
    fetch(f"{supa}/rest/v1/glance_hidden"
          f"?collection=eq.{args.collection}&key=in.({quoted})",
          {**admin, "Prefer": "return=minimal"}, None, "DELETE")

    # Verify through the PUBLIC route, which is what a viewer of the field gets,
    # not the table, which is only what we believe we wrote.
    after = fetch(f"{supa}/functions/v1/glance/api/removals"
                  f"?collection={args.collection}", {"apikey": anon})["hidden"]
    still = {h["key"] for h in after}
    print(f"\nas the field now serves it: {len(after)} hidden")
    ok = True
    for k in present:
        good = k not in still
        ok = ok and good
        print(f"  {'RESTORED ' if good else 'STILL HIDDEN '}{k}")
    survived = sum(1 for k in still if any(p in k.lower() for p in PROTECTED))
    print(f"  standing culls still hidden: {survived}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
