"""Fold Luca's curation posts into one exclusion list, and refuse to skip one.

WHY THIS EXISTS. On 2026-08-11 Luca curated the field at 16:53. The removal list
landed in `outputs/_glance-inbox/latest.json` as designed. The agent was deep in
other work, never looked at the inbox again, and every rebuild for the next six
hours used a `cumulative.json` built at 15:10 that predated the list. All 25 of
his removals stayed on the field. He had to notice and ask.

Nothing was restored. The list was simply never picked up, which from the other
side of the screen is the same thing. Building the union by hand each time is
what made that possible, so it is a tool now, and `--check` is designed to be
run before every export.

    python tools/curation_sync.py --check     # exit 1 if a post is unapplied
    python tools/curation_sync.py --apply     # fold latest.json in, archive it

THE RULE, from Luca 2026-08-11: `--exclude-file` is NOT cumulative. The union is
`applied/applied-*.json` plus `latest.json`. Posts in `audit/` are deliberately
NEVER folded in: they are superseded or withdrawn snapshots, and re-applying one
would re-remove a card that was restored on purpose.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / "outputs" / "_glance-inbox"
LATEST = INBOX / "latest.json"
CUMULATIVE = INBOX / "cumulative.json"
AGENT = INBOX / "agent-excluded.json"


def keys_of(p: Path) -> list[dict]:
    try:
        return [e for e in json.loads(p.read_text(encoding="utf-8")).get("exclude", [])
                if e.get("key")]
    except Exception:
        return []


def build_union() -> list[dict]:
    """applied/* plus agent-excluded. NEVER audit/, see the module docstring."""
    seen, out = set(), []
    for p in sorted(INBOX.glob("applied/applied-*.json")) + [AGENT]:
        if not p.exists():
            continue
        for e in keys_of(p):
            if e["key"] not in seen:
                seen.add(e["key"])
                out.append(e)
    return out


def unapplied() -> list[str]:
    """Keys in latest.json that the current cumulative does not carry."""
    if not LATEST.exists():
        return []
    have = {e["key"] for e in keys_of(CUMULATIVE)} if CUMULATIVE.exists() else set()
    return sorted({e["key"] for e in keys_of(LATEST)} - have)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if a curation post has not been folded in")
    ap.add_argument("--apply", action="store_true",
                    help="archive latest.json into applied/ and rebuild cumulative")
    a = ap.parse_args()

    missing = unapplied()
    if a.check and not a.apply:
        if missing:
            print(f"UNAPPLIED CURATION: {len(missing)} removal(s) in latest.json are not "
                  f"in cumulative.json.")
            for k in missing:
                print(f"   {k}")
            print("\nRun `python tools/curation_sync.py --apply`, then re-export. "
                  "Do NOT export before doing so, or the field will keep serving "
                  "cards that were removed.")
            return 1
        print("curation is in sync; nothing unapplied.")
        return 0

    if a.apply:
        if LATEST.exists() and missing:
            stamp = datetime.now(timezone.utc).strftime("applied-%Y%m%dT%H%MZ-latest.json")
            (INBOX / "applied" / stamp).write_text(
                LATEST.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"archived latest.json -> applied/{stamp}  ({len(missing)} new)")
        elif LATEST.exists():
            print("latest.json already folded in; nothing to archive")
        out = build_union()
        CUMULATIVE.write_text(json.dumps(
            {"action": "exclude-from-curated-field", "collection": "ledwall",
             "exclude": out}, indent=1), encoding="utf-8")
        print(f"cumulative.json rebuilt: {len(out)} exclusions")
        return 0

    print(f"latest.json: {'present' if LATEST.exists() else 'absent'}   "
          f"unapplied: {len(missing)}   cumulative: {len(keys_of(CUMULATIVE))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
