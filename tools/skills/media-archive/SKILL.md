---
name: media-archive
description: Search, retrieve, publish, and ingest media from the Slow Interpolation R2 archive (bucket slow-interpolation-media). SQL over the catalogue + knowledge joins, headless downloads, remote frame extraction, per-asset publishing with owner clearance, Library UI. Invoke with /media-archive or natural language ("find photos of...", "get the archive footage of...", "pull assets from the archive").
---

# /media-archive — Slow Interpolation Media Archive

**Store:** Cloudflare R2, bucket `slow-interpolation-media` (private master) + `slow-interpolation-media-public` (published assets only). Creds in `tools/.env` (`R2_*` + `R2_PUBLIC_*`). Zero egress cost — retrieve freely.
**Catalogue truth:** `{collection}/_catalogue.json` in-bucket (single source of truth; per-asset tags: event/group, date, artists, scene, caption, persons, artworks, public state). Default collection: `nyc-billboard`.
**Design doc:** `docs/media-archive-architecture.md` (Layers 1-3).
**Interpreter:** ALWAYS `py -3.11` (the PATH python may lack the deps).

## Ownership (custody split)
Fast verbs (`find`, `get`, `frames`, `publish`, `unpublish`, `browse`, `status`) run directly in the invoking session. **Custodial verbs (`ingest`, catalogue hygiene, tagging backfills, review-queue prep, KB-export refresh, collection migrations) belong to the `media-archivist` subagent** — when a session can spawn subagents, delegate those instead of running them inline (it enforces the single-writer check, provenance-doc-first, and ledger discipline consistently). Owner clearance for publishing applies on every surface.

## Modes

### `find` (default) — natural language to query
Translate the user's ask into one of:
```
py -3.11 tools/media_query.py --canned artist --slug <entity-slug>
py -3.11 tools/media_query.py --canned day --date YYYY-MM-DD
py -3.11 tools/media_query.py --canned scene --term <word>          # matches scene tags
py -3.11 tools/media_query.py --canned person-events --slug <slug>  # via KB event roles
py -3.11 tools/media_query.py --sql "SELECT ..."                    # freeform DuckDB SQL
```
SQL tables: `assets` (key, date, event, venue, context, asset_class, media_type, caption, artists[], scene[], public, public_url), plus `people` / `events` / `orgs` when a KB export exists (join on slug = `id`). Caption full-text: `caption ILIKE '%term%'`. Present results as a compact table (key tail + date + caption); offer download or publish next.

### `get` — retrieve files
```
py -3.11 tools/media_store.py download --key <key> --out <path>
py -3.11 tools/media_store.py download-batch (--prefix <p> | --keys-file <f>) --out <dir>   # many files, one session
```
Default output dir: the session scratchpad (never the repo — media stays out of git).

### `frames` — extract stills from video WITHOUT downloading it
```
py -3.11 tools/media_store.py frames --key <video-key> --times 0:03,1:10 --out <dir>   # specific moments
py -3.11 tools/media_store.py frames --key <video-key> --every 30 --out <dir>          # contact-sheet style
py -3.11 tools/media_store.py presign --key <key> [--ttl 3600]                         # raw seekable URL (ffmpeg-compatible)
```
ffmpeg seeks the presigned URL via HTTP range reads — grabbing 3 frames from a 900 MB clip transfers a few MB, not the file. This is the default way to preview/choose video content; only `download` a full original once chosen. Videos also carry poster frames (`thumbs/{key}` in-bucket, cached locally) and VLM captions + scene tags from ingest, so `find` works on videos the same as photos (e.g. `caption ILIKE '%screen%' AND media_type = 'video'`).

### `publish` / `unpublish` — public links (CLEARANCE-GATED)
Default-private posture. NEVER publish without an explicit owner request naming the asset(s) in the current conversation (same discipline as sending email).
```
py -3.11 tools/media_store.py publish --key <key>      # returns permanent public URL
py -3.11 tools/media_store.py unpublish --key <key>
py -3.11 tools/media_store.py published --edition nyc-billboard
```
Videos publish as a derived faststart copy under `web/{key}`; originals are never modified. Public URLs are permanent until unpublished. Requires the public bucket + `R2_PUBLIC_*` vars; without them this mode is unavailable (say so rather than improvising a workaround).

### `browse` — visual Library
```
py -3.11 tools/media-engine/serve.py    ->  http://127.0.0.1:8766
```
Engine Room tab = ingest pipeline; Library tab = grid + facets (day chips, artist, event, media type) + review queue + per-asset publish button + video scrubbing.

**The Glance adapter — feeding the far-LOD visual browser.** Glance is a SEPARATE
tool (`glance/` in the same repo): a WebGL field showing the whole archive at once,
clustered by event or date. It is backend-agnostic — it reads a declared data
contract and nothing else — and this archive ships the adapter that produces that
contract. Three derived artifacts, all built from the local thumbnail cache at zero
egress:
```
py -3.11 tools/media-engine/fetch_thumbs.py       # per-asset thumbnails into cache/
py -3.11 tools/media-engine/build_field.py        # layout seed + dominant color (cache/field-{collection}.json)
py -3.11 tools/media-engine/build_atlas.py        # packs thumbnails into texture-atlas sheets (cache/atlas/)
```
Re-run these after each ingest. All three write only under `cache/` (gitignored) and
never touch originals or the catalogue.

Then assemble the contract-shaped export and point Glance at it:
```
py -3.11 tools/media-engine/build_glance_dist.py [--out tools/media-engine/dist]
python <path-to>/glance/serve.py --data tools/media-engine/dist
```
The export is **fail-closed**: catalogue fields ship only if explicitly whitelisted,
and the build aborts if any internal marker leaks into the public JSON. `dist/` is a
build artifact (gitignored) — never commit it; it holds a full sanitized catalogue
snapshot and thumbnails meant for one public deploy, not for the source repo.

`serve_atlas.py` (`http://127.0.0.1:8767`) additionally answers the contract's tier 1
routes — sign-in and download of originals — against your bucket. It is read-only by
construction: it never mutates the catalogue. Downloads stream through that gated
route, never a direct bucket URL. Tier 1 also needs an auth provider configured on
the Glance side; without one Glance runs browse-only, which is a complete archive.

### `status` — archive health
```
py -3.11 tools/media_store.py manifest --edition nyc-billboard
py -3.11 tools/media_query.py --sql "SELECT asset_class, media_type, count(*) FROM assets GROUP BY 1, 2"
```

### `ingest` — add new media (propose-then-run)
For new deliverables (local folder, or Dropbox links via `fetch_dropbox.py`). PROPOSE the batch config first (source, key prefix, event/group slug, asset_class, artists) and get owner OK, then:
```
py -3.11 tools/media-engine/ingest.py --source <dir> --edition nyc-billboard --prefix <nyc-billboard/...> \
    --asset-class <event-photo|event-video|press-kit|original-work|document> [--event <slug>] [--artists <slugs>] --yes
```
Key convention: `{collection}/{group-slug}/{entity-slug}/{photo|video}/{file}` · day sets: `{collection}/day-YYYY-MM-DD/...` · previews: `{collection}/_preview/...`. Dropbox: fetch zips first via `tools/media-engine/fetch_dropbox.py --manifest <json> --staging <dir>`. After ingest, refresh KB exports if entities changed: `py -3.11 tools/media-engine/kb_export.py`.

Ledger invariant (enforced, shown in the UI): `discovered == catalogued + quarantined + duplicates + excluded + in_pipeline`. A run is only done when the ledger BALANCES. Re-running is safe and idempotent (sha256 dedupe) — that is how quarantines get swept.

## Hard rules
1. **Single writer.** Before ANY catalogue-writing action (ingest / publish / review), check no other ingest is running (`tools/media-engine/cache/run-state.json` phase must be idle/done/failed, and ask whether a parallel chat might be mid-ingest). Reads and downloads are always safe.
2. **Originals are immutable.** Never re-upload, transcode, or overwrite an archived original. Derived copies (`thumbs/`, `web/`) only.
3. **Publishing = owner clearance per asset**, named explicitly, in-conversation. No bulk publishes without a bulk clearance.
4. **Media never enters git.** Downloads go to scratchpad or explicitly-named local dirs; `_SOURCES.md` and the catalogue stay the tracked truth.
5. **Person tags**: only `status == confirmed` person tags may drive outward-facing content selection.

## Self-improvement
Log recurring query patterns worth promoting to canned queries, tagging gaps, and any failure modes in `tools/skills/media-archive/learnings.md`.
