"""
build_glance_dist.py -- assemble the static PUBLIC bundle for glance.yourdomain.com.

Glance's permanent home is a static frontend on Vercel + Supabase Edge Functions for the
gated dynamic endpoints (see the deploy plan). This script bakes the CDN-served static
tree: the frontend, a SANITIZED catalogue, the field layout, atlas sheets, and thumbnails.
It writes a `vercel.json` whose rewrites keep the frontend's existing `/api/*` URLs working
(static paths served locally; the gated endpoints proxied to the Edge Functions base).

SAFETY: the whole archive is publicly viewable, so the catalogue ships to the browser -- but
it is whitelisted to display-safe fields only. Internal provenance (`source` local paths,
`face_pass` processing notes, event `actor`) is stripped, and a fail-closed guard aborts the
build if any known-internal marker survives. Originals never ship here; only the gated Edge
Function streams them from private R2.

Usage:
    py -3.11 tools/media-engine/build_glance_dist.py [--edition nyc-billboard]
                 [--functions-base https://<ref>.supabase.co/functions/v1/glance]
                 [--out tools/media-engine/dist]
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
TOOLS_DIR = ENGINE_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(ENGINE_DIR))

import media_store  # noqa: E402

CACHE_DIR = ENGINE_DIR / "cache"
GLANCE_DIR = ENGINE_DIR / "glance"
REPO_ROOT = TOOLS_DIR.parent
FUNCTION_TS = REPO_ROOT / "packages" / "site" / "supabase" / "functions" / "glance" / "index.ts"

# Route segments the Edge Function accepts as ALIASES of a canonical route, and which
# therefore deliberately have no rewrite of their own. The function derives its route
# from the LAST path segment, so /api/event/bulk -> "bulk" and /api/event/create ->
# "create" are accepted alongside the canonical "event-bulk" / "event-create" that the
# rewrite destinations actually use. Anything NOT listed here must be reachable.
ROUTE_ALIASES = {"bulk", "create"}

# --- catalogue sanitize: WHITELIST of fields that are safe to expose publicly ---
ASSET_KEEP = ("key", "bytes", "sha256", "media_type", "ingested", "thumb")
TAG_KEEP = ("edition", "event", "venue", "context", "date", "date_basis",
            "media_type", "asset_class", "artists", "artworks", "persons",
            "scene", "caption",
            # Contributor credit, PUBLIC by founder decision 2026-07-31: someone invited
            # to contribute should be named on the photo they gave, and an uncredited
            # contribution is a worse deal than anyone expects.
            #
            # ONLY the display name. `contributed_by` (the auth uid) and
            # `contribution_source` stay editor-only and must never be added here --
            # a user id is an identifier for correlating someone across systems, not a
            # credit. This whitelist is fail-closed, so their absence is what keeps them
            # private.
            #
            # The consent text says the name is published, because it is.
            "contributed_name")
EVENT_KEEP = ("slug", "label", "venue", "date", "description", "kind",
              "group", "order", "near")

# fail-closed guard: if any of these substrings appears anywhere in the sanitized JSON,
# something internal leaked -> abort the build (never ship it).
LEAK_MARKERS = ("local:", "knowledge/", "face_pass", "/drafts/", "C:\\", "actor")


def sanitize_catalogue(cat):
    out = {"edition": cat.get("edition"), "generated": cat.get("generated"), "assets": [], "events": []}
    for a in cat.get("assets", []):
        tags = a.get("tags") or {}
        # Archived = hidden from the public field. `archived` is not in TAG_KEEP, so it
        # used to be STRIPPED here -- which meant the client-side filter in glance.js
        # ("if tg.archived: continue") never fired publicly and the asset stayed visible.
        # Drop the record entirely instead: an asset the founder hid should not ship its
        # metadata publicly, and dropping it also keeps it out of the Edge Function's
        # key-guard, so it cannot be downloaded either. Editors still see archived assets
        # via the gated /catalogue-live route, which keeps the flag so they can unhide.
        if tags.get("archived"):
            continue
        rec = {k: a[k] for k in ASSET_KEEP if k in a}
        rec["tags"] = {k: tags[k] for k in TAG_KEEP if k in tags}
        out["assets"].append(rec)
    for e in cat.get("events", []):
        out["events"].append({k: e[k] for k in EVENT_KEEP if k in e})
    return out


def assert_no_leak(obj):
    blob = json.dumps(obj, ensure_ascii=False)
    hits = [m for m in LEAK_MARKERS if m in blob]
    if hits:
        raise SystemExit(f"[build] ABORT: internal marker(s) leaked into public catalogue: {hits}")


def copytree(src: Path, dst: Path):
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)


# --- rewrite audit: every function route must be reachable from the browser ---------
# This has bitten twice, both times SILENTLY. A route exists in the Edge Function but has
# no `vercel.json` rewrite, so the path falls through to the static site and the frontend
# gets HTML where it expected JSON. For /api/events the consequence was the ENTIRE edit UI
# never activating, with nothing in the console, because write.js boots with
# `if (!r.ok) return`. A hand-kept checklist did not survive contact with new routes, so
# the build now derives both sides and refuses to ship a mismatch.

def function_route_segs(ts_path: Path):
    """Route segments the Edge Function answers, read out of its source.

    Two shapes are used there and both are matched:
      * `if (seg === "presign")`            -- one route per literal
      * `const WRITE_SEGS = ["event", ...]` -- a list of write routes
    """
    if not ts_path.is_file():
        raise SystemExit(
            f"[build] ABORT: cannot audit rewrites, Edge Function source not found at {ts_path}. "
            "Skipping the audit is exactly the failure this check exists to prevent."
        )
    src = ts_path.read_text(encoding="utf-8")
    segs = set(re.findall(r'seg\s*===\s*"([a-z0-9-]+)"', src))
    for block in re.findall(r"WRITE_SEGS\s*=\s*\[(.*?)\]", src, re.S):
        segs.update(re.findall(r'"([a-z0-9-]+)"', block))
    return segs


def audit_rewrites(rewrites, functions_base: str, ts_path: Path = FUNCTION_TS,
                   clean_urls: bool = True):
    """Abort the build unless the rewrites and the function agree, both directions."""
    fb = functions_base.rstrip("/")

    # 0. cleanUrls makes /index.html a 308 redirect to /, so a rewrite that points at
    #    the explicit filename resolves to a redirect and the source path 404s. This
    #    shipped once: every /s/<token> share link was dead on arrival while the build
    #    looked perfectly correct. Static destinations are not covered by the
    #    function-route checks below, so they get their own rule.
    if clean_urls:
        bad_html = [r["source"] for r in rewrites
                    if r["destination"].endswith("/index.html")]
        if bad_html:
            raise SystemExit(
                f"[build] ABORT: rewrite(s) {bad_html} point at '/index.html' while "
                "cleanUrls is on, which 308-redirects it. Use '/' as the destination."
            )
    routed = {}                      # function route seg -> the /api/* source that reaches it
    for r in rewrites:
        dest = r["destination"]
        if not dest.startswith(fb + "/"):
            continue                 # static destination (/data/*.json), not a function route
        routed[dest.rsplit("/", 1)[-1]] = r["source"]

    answered = function_route_segs(ts_path)

    # 1. A rewrite pointing at a route the function does not answer -> a typo that
    #    would 404 in production while looking correct in the diff.
    dead = sorted(set(routed) - answered)
    if dead:
        raise SystemExit(f"[build] ABORT: rewrite(s) point at unknown function route(s): {dead}")

    # 2. THE one that has actually broken production: a route with no way to reach it.
    unreachable = sorted(answered - set(routed) - ROUTE_ALIASES)
    if unreachable:
        raise SystemExit(
            f"[build] ABORT: function route(s) with no vercel.json rewrite: {unreachable}. "
            "Add a rewrite, or list the segment in ROUTE_ALIASES if it is an accepted "
            "alias of a canonical route."
        )

    # 3. Vercel matches rewrites in order, so a source that is a path-prefix of another
    #    must not be able to shadow it (/api/event before /api/event/bulk).
    sources = [r["source"] for r in rewrites]
    for i, a in enumerate(sources):
        for b in sources[i + 1:]:
            if b.startswith(a.rstrip("/") + "/"):
                raise SystemExit(
                    f"[build] ABORT: rewrite '{a}' precedes '{b}' and can shadow it. "
                    "Vercel matches in order: put the more specific source first."
                )

    print(f"[build]   rewrites audited: {len(rewrites)} total, "
          f"{len(routed)} function routes, all reachable.")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--edition", default="nyc-billboard")
    p.add_argument("--functions-base", default="__FUNCTIONS_BASE__",
                   help="Supabase Edge Functions base for the gated endpoints, e.g. "
                        "https:///functions/v1/glance")
    p.add_argument("--out", default=str(ENGINE_DIR / "dist"))
    p.add_argument("--bundle-from", default=None,
                   help="Directory holding the pre-built data bundle (field-<edition>.json, "
                        "atlas/, thumbs/). Used by CI, which pulls it from R2 glance-build/ "
                        "instead of the local cache. Defaults to the local cache/.")
    args = p.parse_args()

    # field/atlas/thumbs come from the local cache in dev, or a pulled bundle in CI.
    # The catalogue is ALWAYS read live from R2 + sanitized (keeps the fail-closed guard
    # in the build path regardless of source).
    data_src = Path(args.bundle_from) if args.bundle_from else CACHE_DIR

    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    (out / "data").mkdir(parents=True, exist_ok=True)

    # 1) frontend -> dist root (served at / and /glance/*) ------------------------
    # the frontend references /glance/... absolute paths, so keep it under /glance too
    #
    # The bundled frontend is OPTIONAL. copytree() already no-ops on a missing source,
    # but the index.html copy did not, so an absent frontend killed the whole run before
    # a single data artifact was written -- even though steps 2-4 need no frontend at all.
    # That is reachable now: in the white-label copy of this tool Glance is a separately
    # installed sibling and this directory is excluded by design. The data artifacts are
    # the contract; the frontend is a convenience, so its absence must not be fatal.
    copytree(GLANCE_DIR, out / "glance")
    if (GLANCE_DIR / "index.html").is_file():
        shutil.copy2(GLANCE_DIR / "index.html", out / "index.html")
    else:
        print(f"  note: no bundled frontend at {GLANCE_DIR} -- emitting data artifacts only")

    # 2) sanitized catalogue -> /data/catalogue.json ------------------------------
    cat = media_store.read_catalogue(args.edition)
    clean = sanitize_catalogue(cat)
    assert_no_leak(clean)
    (out / "data" / "catalogue.json").write_text(json.dumps(clean, ensure_ascii=False), encoding="utf-8")
    n_assets = len(clean["assets"])

    # 3) field layout -> /data/field.json -----------------------------------------
    field = data_src / f"field-{args.edition}.json"
    if field.is_file():
        shutil.copy2(field, out / "data" / "field.json")
    else:
        print(f"[build] WARNING: {field.name} missing (run build_field.py)")

    # 4) atlas sheets + thumbnails (static) ---------------------------------------
    copytree(data_src / "atlas", out / "atlas")
    copytree(data_src / "thumbs", out / "thumbs")
    n_thumbs = len(list((out / "thumbs").glob("*.jpg"))) if (out / "thumbs").is_dir() else 0

    # 5) vercel.json: keep the frontend's /api/* URLs working ---------------------
    fb = args.functions_base.rstrip("/")
    vercel = {
        "cleanUrls": True,
        "rewrites": [
            {"source": "/api/catalogue", "destination": "/data/catalogue.json"},
            {"source": "/api/field", "destination": "/data/field.json"},
            {"source": "/api/presign", "destination": f"{fb}/presign"},
            {"source": "/api/download", "destination": f"{fb}/download"},
            {"source": "/api/download-zip", "destination": f"{fb}/download-zip"},
            {"source": "/api/log", "destination": f"{fb}/log"},
            # --- live edit (E3.1), all editor-gated server-side ---
            # write.js already fetches these /api/* paths, so porting it needs no URL
            # changes. The function derives its route from the LAST path segment, hence
            # /api/event/bulk -> "bulk" and /api/event/create -> "create" (both accepted).
            {"source": "/api/catalogue-live", "destination": f"{fb}/catalogue-live"},
            # /api/events (plural) is the registry the write layer boots from -- it MUST come
            # before /api/event and must exist at all: without it the path falls through to the
            # static site, write.js's boot() fetch gets HTML, and the edit UI silently never
            # activates (no error, just no affordances).
            {"source": "/api/events", "destination": f"{fb}/events"},
            {"source": "/api/publish-status", "destination": f"{fb}/publish-status"},
            {"source": "/api/publish", "destination": f"{fb}/publish"},
            {"source": "/api/event/bulk", "destination": f"{fb}/event-bulk"},
            {"source": "/api/event/create", "destination": f"{fb}/event-create"},
            {"source": "/api/event", "destination": f"{fb}/event"},
            {"source": "/api/venue", "destination": f"{fb}/venue"},
            {"source": "/api/archive", "destination": f"{fb}/archive"},
            # --- curated share links (S3) ---
            # /api/shares (plural, the editor's manage list) MUST precede /api/share
            # for the same reason /api/events precedes /api/event.
            {"source": "/api/shares", "destination": f"{fb}/shares"},
            {"source": "/api/share-create", "destination": f"{fb}/share-create"},
            {"source": "/api/share-revoke", "destination": f"{fb}/share-revoke"},
            {"source": "/api/share", "destination": f"{fb}/share"},
            # --- contributor upload (C1) ---
            # /api/upload-init answers GET (public capability probe + limits) and POST
            # (signs the batch). Bytes never pass through the function: the browser PUTs
            # straight to R2 with a presigned URL, so a 2 GB video costs one signature.
            # Neither source is a path-prefix of the other, so their order is free --
            # but never add a bare "/api/upload", which would shadow both.
            {"source": "/api/upload-init", "destination": f"{fb}/upload-init"},
            {"source": "/api/upload-complete", "destination": f"{fb}/upload-complete"},
            {"source": "/api/upload-multipart", "destination": f"{fb}/upload-multipart"},
            # --- contribution review (C2), editor-gated ---
            # /api/contributions (plural) MUST precede nothing in particular here, but note
            # neither is a prefix of the other, so order among them is free.
            {"source": "/api/contributions", "destination": f"{fb}/contributions"},
            {"source": "/api/contribution-decide", "destination": f"{fb}/contribution-decide"},
            {"source": "/api/contribution-purge", "destination": f"{fb}/contribution-purge"},
            # Signs an INBOX key so review can show the original, not the contributor's
            # 512px poster. /api/presign cannot: it is public and gated on membership of
            # the public catalogue, which a pending file deliberately is not in.
            {"source": "/api/contribution-presign", "destination": f"{fb}/contribution-presign"},
            # --- contributor invitations (C3), editor-gated ---
            # /api/invites (plural, the list) MUST precede /api/invite for the same reason
            # /api/events precedes /api/event: Vercel matches in order.
            {"source": "/api/invites", "destination": f"{fb}/invites"},
            {"source": "/api/invite", "destination": f"{fb}/invite"},
            # The shareable link itself: glance.yourdomain.com/s/<token> serves
            # the ordinary app shell, which reads the token from its own path and
            # resolves it through /api/share. A rewrite (not a redirect) so the token
            # stays in the address bar and the link survives being forwarded.
            # Destination is "/" and NOT "/index.html": cleanUrls is on above, which
            # makes /index.html a 308 redirect to /, so a rewrite pointing at the
            # explicit filename resolves to a redirect and every /s/<token> 404s.
            # Caught in production on the first deploy; audit_rewrites now rejects it.
            {"source": "/s/:token", "destination": "/"},
            # Optional: lets the backend greet a first-time arrival.
            {"source": "/api/profile-hello", "destination": f"{fb}/profile-hello"},
        ],
    }
    audit_rewrites(vercel["rewrites"], fb)
    (out / "vercel.json").write_text(json.dumps(vercel, indent=2), encoding="utf-8")

    print(f"[build] dist ready at {out}")
    print(f"[build]   assets(sanitized)={n_assets}  thumbs={n_thumbs}  "
          f"field={'yes' if field.is_file() else 'MISSING'}")
    print(f"[build]   functions-base={fb}")
    if fb == "__FUNCTIONS_BASE__":
        print("[build]   NOTE: pass --functions-base once the Edge Functions are deployed.")


if __name__ == "__main__":
    main()
