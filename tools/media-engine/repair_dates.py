"""Repair asset dates that were recorded as `mtime` -- i.e. the day we DOWNLOADED the
file, not the day it was shot.

Background: ingest.py falls back to file mtime when it cannot read a capture date. For a
delivery that arrived as a zip those are unrelated numbers, and two shipped bugs made the
fallback fire far more often than intended (Pillow >= 10 returning IFD0 only, and no video
container reader at all). Both are fixed FORWARD; this repairs what is already catalogued.

The true date is read back out of the originals in R2 WITHOUT downloading them:
  photos -- a 128 KB Range GET is enough for the JPEG APP1/EXIF block
  videos -- ffprobe over a presigned URL, which range-reads (~2 MB of a 1 GB file)
Measured: ~103 MB total instead of ~28.5 GB, about 283x less.

Usage (dry run is the DEFAULT; --apply additionally requires a --plan from a prior probe):
    py -3.11 tools/media-engine/repair_dates.py --probe
    py -3.11 tools/media-engine/repair_dates.py --plan <plan.json>
    py -3.11 tools/media-engine/repair_dates.py --plan <plan.json> --apply --tier A
    py -3.11 tools/media-engine/repair_dates.py --plan <plan.json> --verify

It NEVER touches object bytes. The only R2 write is the catalogue, via compare-and-swap.
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date as _date
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS_DIR))
import media_store  # noqa: E402

PHOTO_RANGE = 131071          # 128 KB: JPEG APP1 sits right after SOI
DAY_RE = re.compile(r"/day-(\d{4}-\d{2}-\d{2})/")
PLAUSIBLE_FROM = "2025-01-01"
MAX_EVENT_DRIFT_DAYS = 60


# ---------------------------------------------------------------- extraction

def photo_date(key, client, bucket):
    """EXIF capture date from a 128 KB range read. Same tag path as ingest.py:363-372."""
    try:
        resp = client.get_object(Bucket=bucket, Key=key, Range=f"bytes=0-{PHOTO_RANGE}")
        raw_bytes = resp["Body"].read()
        from PIL import Image
        with Image.open(io.BytesIO(raw_bytes)) as im:
            exif = im.getexif()
            raw = exif.get(36867) or exif.get(306)
            if not raw:
                try:
                    raw = exif.get_ifd(0x8769).get(36867)
                except Exception:
                    raw = None
            if raw:
                return str(raw)[:10].replace(":", "-"), None
        return None, "no EXIF date in the first 128 KB"
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:70]}"


def video_date(key):
    """Container creation_time via ffprobe over a presigned URL. Same keys as ingest.py:386-394."""
    try:
        url = media_store.presign(key, ttl=900)
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", url],
            capture_output=True, text=True, timeout=180)
        tags = (json.loads(probe.stdout).get("format", {}) or {}).get("tags", {}) or {}
        raw = tags.get("creation_time") or tags.get("com.apple.quicktime.creationdate")
        if raw:
            return str(raw)[:10], None
        return None, "no creation_time in container"
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:70]}"


# ---------------------------------------------------------------- classification

def event_date(catalogue, event):
    for e in catalogue.get("events", []):
        if isinstance(e, dict) and e.get("slug") == event:
            return e.get("date")
    return None


def days_between(a, b):
    try:
        ya, ma, da = (int(x) for x in a.split("-"))
        yb, mb, db = (int(x) for x in b.split("-"))
        return abs((_date(ya, ma, da) - _date(yb, mb, db)).days)
    except Exception:
        return None


def implausible(found, ev_date, today):
    if found < PLAUSIBLE_FROM or found > today:
        return f"outside [{PLAUSIBLE_FROM}, {today}]"
    if ev_date:
        d = days_between(found, ev_date)
        if d is not None and d > MAX_EVENT_DRIFT_DAYS:
            return f"{d}d from its event date {ev_date}"
    return None


def classify(rec, found, err, catalogue, today):
    """-> (tier, new_date, new_basis, note). Tiers: A1/A2 auto, C propose, D leave."""
    tags = rec.get("tags") or {}
    key = rec["key"]
    ev = tags.get("event")
    ev_date = event_date(catalogue, ev)
    folder = DAY_RE.search(key)
    folder_date = folder.group(1) if folder else None
    basis = "exif" if rec.get("media_type") == "photo" else "container"

    if found:
        bad = implausible(found, ev_date, today)
        if bad:
            return "FLAG", None, None, f"extracted {found} but {bad}"
        if folder_date and folder_date == found:
            return "A1", found, basis, f"embedded {found} == folder label"
        if folder_date and folder_date != found:
            # learnings.md: photographer folder labels beat camera EXIF. Contested -> propose.
            return "A3", folder_date, "folder-label", (
                f"CONTESTED: embedded {found} vs folder label {folder_date}; "
                "folder label wins per learnings.md, but this needs a human")
        note = f"embedded {found}"
        if ev_date and days_between(found, ev_date) not in (None, 0):
            note += f" ({days_between(found, ev_date)}d from event {ev_date})"
        return "A2", found, basis, note

    if folder_date:
        return "B", folder_date, "folder-label", f"no embedded date; folder label {folder_date} ({err})"
    if ev_date:
        return "C", ev_date, "inferred", f"no embedded date and no folder label; event {ev} is {ev_date} ({err})"
    return "D", None, None, f"no capture date recoverable and no event to infer from ({err})"


# ---------------------------------------------------------------- probe

def probe(edition, limit):
    env = media_store.load_env()
    client = media_store.r2_client(env)
    bucket = media_store.bucket_name(env)
    catalogue = media_store.read_catalogue(edition, client, env)
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    targets = [a for a in catalogue.get("assets", [])
               if (a.get("tags") or {}).get("date_basis") == "mtime"]
    if limit:
        targets = targets[:limit]
    print(f"-- {len(targets)} asset(s) with date_basis=mtime")

    proposals, bytes_read = [], 0
    for i, rec in enumerate(targets, 1):
        key = rec["key"]
        mt = rec.get("media_type")
        if mt == "photo":
            found, err = photo_date(key, client, bucket)
            bytes_read += PHOTO_RANGE if found or not err else 0
        elif mt == "video":
            found, err = video_date(key)
            bytes_read += 2_200_000 if found or not err else 0
        else:
            found, err = None, f"unsupported media_type {mt!r}"
        tier, new_date, new_basis, note = classify(rec, found, err, catalogue, today)
        tags = rec.get("tags") or {}
        proposals.append({
            "key": key, "media_type": mt, "event": tags.get("event"),
            "prev_date": tags.get("date"), "prev_basis": tags.get("date_basis"),
            "extracted": found, "tier": tier,
            "new_date": new_date, "new_basis": new_basis, "note": note,
        })
        if i % 20 == 0:
            print(f"   ...{i}/{len(targets)}")

    plan = {
        "edition": edition,
        "catalogue_assets": len(catalogue.get("assets", [])),
        "targets": len(targets),
        "bytes_read": bytes_read,
        "proposals": proposals,
    }
    return plan


def report(plan):
    props = plan["proposals"]
    by_prefix = defaultdict(list)
    for p in props:
        by_prefix["/".join(p["key"].split("/")[:-1])].append(p)
    for prefix, group in sorted(by_prefix.items(), key=lambda kv: -len(kv[1])):
        tiers = Counter(p["tier"] for p in group)
        events = Counter(p["event"] for p in group)
        print(f"\n=== {prefix}   n={len(group)}")
        print(f"    events: {dict(events)}")
        print(f"    tiers : {dict(tiers)}")
        for p in group[:3]:
            arrow = f"{p['prev_date']} {p['prev_basis']} -> {p['new_date']} {p['new_basis']}" \
                if p["new_date"] else f"{p['prev_date']} {p['prev_basis']} -> (unchanged)"
            print(f"      [{p['tier']}] {p['key'].split('/')[-1]}  {arrow}")
            print(f"            {p['note']}")
        if len(group) > 3:
            print(f"      ... and {len(group)-3} more")
    print()
    t = Counter(p["tier"] for p in props)
    print("-- tiers:", dict(t))
    print(f"-- bytes read: {plan['bytes_read']/1024/1024:.1f} MB")
    auto = [p for p in props if p["tier"] in ("A1", "A2")]
    print(f"-- tier A (auto-appliable): {len(auto)}")
    print("-- DRY RUN. Nothing written.")


# ---------------------------------------------------------------- apply

def apply_plan(plan, tiers_allowed, actor):
    edition = plan["edition"]
    chosen = [p for p in plan["proposals"]
              if p["tier"] in tiers_allowed and p["new_date"]]
    if not chosen:
        print("nothing to apply for the selected tier(s)")
        return 0
    print(f"applying {len(chosen)} change(s), tiers {sorted(tiers_allowed)}")

    skipped = []

    def mutate(catalogue):
        applied = 0
        for p in chosen:
            try:
                media_store.set_date(
                    edition, p["key"], p["new_date"], p["new_basis"],
                    actor=actor, reason=p["note"][:180],
                    expected_prev=p["prev_date"], catalogue=catalogue)
                applied += 1
            except media_store.Conflict as e:
                skipped.append((p["key"], str(e)[:110]))
            except KeyError:
                skipped.append((p["key"], "no longer in the catalogue"))
        return applied

    applied, new_etag = media_store.catalogue_rmw(edition, mutate)
    print(f"applied {applied}; skipped {len(skipped)}; new catalogue etag {new_etag}")
    for k, why in skipped:
        print(f"   SKIPPED {k}: {why}")
    return applied


def verify(plan, tiers_allowed):
    edition = plan["edition"]
    catalogue = media_store.read_catalogue(edition)
    by_key = {a["key"]: a for a in catalogue.get("assets", [])}
    expect = [p for p in plan["proposals"] if p["tier"] in tiers_allowed and p["new_date"]]
    ok = bad = 0
    for p in expect:
        rec = by_key.get(p["key"])
        tags = (rec or {}).get("tags") or {}
        if tags.get("date") == p["new_date"] and tags.get("date_basis") == p["new_basis"]:
            ok += 1
        else:
            bad += 1
            print(f"   MISMATCH {p['key']}: {tags.get('date')} {tags.get('date_basis')}")
    remaining = sum(1 for a in catalogue.get("assets", [])
                    if (a.get("tags") or {}).get("date_basis") == "mtime")
    print(f"verified {ok}/{len(expect)} applied correctly; {bad} mismatch(es)")
    print(f"catalogue assets: {len(catalogue.get('assets', []))} (plan saw {plan['catalogue_assets']})")
    print(f"remaining date_basis=mtime: {remaining} (was {plan['targets']})")
    return bad == 0


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edition", default="nyc-billboard")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--plan")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--tier", default="A", help="A (=A1+A2), or a comma list e.g. A1,A2,C")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--actor", default="repair-dates")
    ap.add_argument("--out")
    args = ap.parse_args()

    # hard rule #1: never write while an ingest is in flight
    if args.apply:
        rs = TOOLS_DIR / "media-engine" / "cache" / "run-state.json"
        if rs.exists():
            phase = json.loads(rs.read_text(encoding="utf-8")).get("phase")
            if phase not in ("idle", "done", "failed"):
                sys.exit(f"REFUSING: an ingest is in flight (run-state phase={phase!r})")

    tiers = {"A1", "A2"} if args.tier.upper() == "A" else {t.strip().upper() for t in args.tier.split(",")}

    if args.probe:
        plan = probe(args.edition, args.limit)
        out = Path(args.out) if args.out else (TOOLS_DIR / "media-engine" / "cache" / "date-repair-plan.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        report(plan)
        print(f"-- plan written to {out}")
        print(f"-- to apply: --plan {out} --apply --tier A")
        return

    if not args.plan:
        sys.exit("need --probe, or --plan <file> (+ --apply / --verify)")
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))

    if args.verify:
        sys.exit(0 if verify(plan, tiers) else 1)
    if args.apply:
        apply_plan(plan, tiers, args.actor)
        return
    report(plan)


if __name__ == "__main__":
    main()
