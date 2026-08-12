"""
Slow Interpolation Media Query -- SQL over the media catalogue + KB (Layer 3, Obstacle 1).

DuckDB reads the catalogue FRESH from the bucket each run (zero sync drift:
the in-bucket _catalogue.json stays the single source of truth) and joins the
KB parquet export (tools/media-engine/kb_export.py) by slug.

Tables/views available in SQL:
    assets   -- one row per catalogued asset (see columns below)
    people   -- KB people (id = person-slug, category, roles, ...)
    events   -- KB events (id = event-slug, artists[], curators[], dates, ...)
    orgs     -- KB organizations

assets columns: key, bytes, sha256, media_type, source, ingested, edition,
    event, venue, context, date, date_basis, asset_class, caption,
    artists (list), scene (list), artworks_json, persons_json,
    public (bool), public_url.

Usage:
    py -3.11 tools/media_query.py --sql "SELECT count(*) FROM assets"
    py -3.11 tools/media_query.py --canned artist --slug example-artist
    py -3.11 tools/media_query.py --canned day --date 2026-01-15
    py -3.11 tools/media_query.py --canned person-events --slug example-curator
    py -3.11 tools/media_query.py --canned scene --term talk

Requires: duckdb, pandas (py -3.11), R2 creds in tools/.env, and a KB export
(run kb_export.py first; falls back gracefully if parquets are missing).
"""

import argparse
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

import media_store  # noqa: E402
import usage_log  # noqa: E402  (append-only usage log; agent-side query capture, T8)

KB_DIR = TOOLS_DIR / "data" / "kb-export"

CANNED = {
    "artist": """
        SELECT key, media_type, asset_class, coalesce(event, context, '') AS where_from,
               date, caption
        FROM assets
        WHERE list_contains(artists, ?)
        ORDER BY date, key
    """,
    "day": """
        SELECT key, media_type, coalesce(event, context, '') AS where_from, caption
        FROM assets
        WHERE date = ?
        ORDER BY key
    """,
    "person-events": """
        SELECT a.key, a.date, e.label AS event_label, a.caption
        FROM assets a
        JOIN events e ON a.event = e.id
        WHERE list_contains(e.artists, ?) OR list_contains(e.curators, ?)
        ORDER BY a.date, a.key
    """,
    "scene": """
        SELECT key, date, coalesce(event, context, '') AS where_from, caption
        FROM assets
        WHERE len(list_filter(scene, s -> s ILIKE '%' || ? || '%')) > 0
        ORDER BY date, key
    """,
}


def build_assets_frame(editions):
    import pandas as pd
    rows = []
    for edition in editions:
        catalogue = media_store.read_catalogue(edition)
        # VENUE IS DERIVED FROM THE EVENT (founder rule 2026-08-06), so build the lookup
        # once per edition and resolve it per asset below. This column used to read the
        # raw `tags.venue`, which broke the moment the stored copies were stripped:
        # `WHERE venue = 'Example Venue'` started returning 0 rows for an event with 96 assets.
        # Deriving is also STRICTLY BETTER than the old behaviour -- it answers for the
        # 287 assets that never carried a stored tag at all (anything from ingest, which
        # has never had a --venue flag), which the raw read could never do.
        venue_by_event = {
            e.get("slug"): e.get("venue")
            for e in catalogue.get("events", []) if isinstance(e, dict)
        }
        for rec in catalogue.get("assets", []):
            t = rec.get("tags", {})
            rows.append({
                "key": rec.get("key"),
                "bytes": rec.get("bytes"),
                "sha256": rec.get("sha256"),
                "media_type": t.get("media_type") or rec.get("media_type"),
                "source": rec.get("source"),
                "ingested": rec.get("ingested"),
                "edition": t.get("edition") or edition,
                "event": t.get("event"),
                "venue": venue_by_event.get(t.get("event")) or t.get("venue"),
                "context": t.get("context"),
                "date": t.get("date"),
                "date_basis": t.get("date_basis"),
                "asset_class": t.get("asset_class"),
                "caption": t.get("caption"),
                "artists": [str(a) for a in (t.get("artists") or [])],
                "scene": [str(s) for s in (t.get("scene") or [])],
                "artworks_json": __import__("json").dumps(t.get("artworks") or []),
                "persons_json": __import__("json").dumps(t.get("persons") or []),
                "public": bool(t.get("public")),
                "public_url": t.get("public_url"),
            })
    return pd.DataFrame(rows)


def connect(editions):
    import duckdb
    con = duckdb.connect()
    frame = build_assets_frame(editions)
    con.register("assets_df", frame)
    con.execute("CREATE VIEW assets AS SELECT * FROM assets_df")
    for view, fname in (("people", "kb_people.parquet"),
                        ("events", "kb_events.parquet"),
                        ("orgs", "kb_orgs.parquet")):
        path = KB_DIR / fname
        if path.is_file():
            con.execute(f"CREATE VIEW {view} AS SELECT * FROM read_parquet('{path.as_posix()}')")
        else:
            print(f"-- note: {fname} missing (run tools/media-engine/kb_export.py); '{view}' view unavailable")
    return con, len(frame)


def main():
    p = argparse.ArgumentParser(description="SQL over the Slow Interpolation media catalogue + KB")
    p.add_argument("--sql", help="freeform SQL")
    p.add_argument("--canned", choices=sorted(CANNED.keys()))
    p.add_argument("--slug", help="person/artist slug for canned queries")
    p.add_argument("--date", help="YYYY-MM-DD for canned day query")
    p.add_argument("--term", help="scene term for canned scene query")
    p.add_argument("--editions", default="nyc-billboard", help="comma-separated editions")
    p.add_argument("--limit", type=int, default=100)
    args = p.parse_args()

    editions = [e.strip() for e in args.editions.split(",") if e.strip()]
    con, n = connect(editions)
    print(f"-- assets loaded: {n} (editions: {', '.join(editions)})")

    if args.sql:
        result = con.execute(args.sql).fetchdf()
    elif args.canned:
        param = {"artist": args.slug, "day": args.date,
                 "person-events": args.slug, "scene": args.term}[args.canned]
        if not param:
            sys.exit(f"--canned {args.canned} needs its parameter (--slug/--date/--term)")
        params = [param, param] if args.canned == "person-events" else [param]
        result = con.execute(CANNED[args.canned], params).fetchdf()
    else:
        sys.exit("provide --sql or --canned (see --help)")

    # T8 usage logging: capture every CLI query (agent-side) into the same
    # append-only log the browser (human) UI writes to, tagged distinctly.
    usage_log.append({
        "source": "agent-cli", "type": "cli-query",
        "canned": args.canned, "sql": bool(args.sql),
        "slug": args.slug, "date": args.date, "term": args.term,
        "editions": editions, "rows": int(len(result)),
    })

    with __import__("pandas").option_context("display.max_rows", args.limit,
                                             "display.width", 200,
                                             "display.max_colwidth", 60):
        print(result.head(args.limit).to_string(index=False))
    print(f"-- {len(result)} rows")


if __name__ == "__main__":
    main()
