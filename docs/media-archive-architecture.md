# Media Archive — Architecture

The stack that answers four different questions:

| Question | Layer | Component |
|---|---|---|
| "give me *this file*" | **1 — Store** | Cloudflare R2 + `tools/media_store.py` |
| "give me every asset showing *X*" | **2 — Catalogue** | in-bucket `_catalogue.json` + `tools/media-engine/ingest.py` (VLM captions, scene tags) |
| "give me assets matching *this relational condition*" | **3 — Query / share / play** | `tools/media_query.py` (DuckDB SQL), the two-bucket publish path, the local Library UI |
| "show me the whole archive at a glance" | **4 — Glance (far-LOD viz)** | `tools/media-engine/build_field.py` + `build_atlas.py` + `serve_atlas.py` + `glance/` (WebGL) |

---

## Layer 1 — the store

**Cloudflare R2**, S3-compatible, **zero egress**. That last property is the whole reason for the choice: an agent that re-pulls a hero video every time it drafts a post pays nothing to do so. Storage is ~$0.015/GB-month, so a 50 GB archive is around €1/month and a 500 GB archive around €7/month, egress included at zero.

It is a plain S3 API, so nothing here is locked in — swapping the endpoint points the same code at Backblaze B2 or AWS S3.

### Key convention

```
{collection}/{group-slug}/{entity-slug}/{photo|video}/{descriptive-name}.{ext}
{collection}/{group-slug}/_event/{photo|video}/...      # group-wide, no single entity
{collection}/day-YYYY-MM-DD/...                          # date-organised deliveries
{collection}/_preview/...                                # cross-group / promo
{collection}/_manifest.json                              # slim inventory
{collection}/_catalogue.json                             # inventory + per-asset tags  <- source of truth
thumbs/{key}                                             # derived poster frames
web/{key}                                                # derived faststart video copies
_kb/*.parquet                                            # entity export for SQL joins
```

`{collection}` is whatever partitions your archive over time — `nyc-billboard` here. Slugs should match whatever your project already uses as entity ids, so the catalogue joins to your knowledge base for free.

**Originals are immutable.** The sha256 recorded at upload is a permanent promise. Anything derived (posters, web copies) lives under its own prefix; nothing ever overwrites an archived original.

---

## Layer 2 — the catalogue

`{collection}/_catalogue.json` lives **inside the bucket, next to the bytes**, so tags and files can never drift apart. Per-asset record:

```jsonc
{
  "key": "nyc-billboard/some-group/some-entity/photo/install-wide-03.jpg",
  "bytes": 8421376, "sha256": "...", "source": "...", "ingested": "...",
  "tags": {
    "edition": "nyc-billboard",
    "event": "some-group",              // AUTO, from the ingest prefix
    "venue": "some-venue",              // AUTO
    "date": "2026-07-07",               // AUTO from folder label / EXIF
    "date_basis": "folder-label",       // which source won
    "media_type": "photo",
    "asset_class": "event-photo",       // event-photo | event-video | press-kit | original-work | document
    "artists": ["some-entity"],         // authorship, from the batch config
    "artworks": [{"slug": "...", "confidence": 0.98, "status": "confirmed", "basis": "filename"}],
    "persons":  [{"slug": "...", "confidence": 0.61, "status": "pending"}],
    "scene": ["install-shot", "wide"],  // AUTO, VLM
    "caption": "One factual sentence describing the frame.",   // AUTO, VLM
    "public": false, "public_url": null
  }
}
```

### What is trusted automatically, and what is not

| Tag class | Posture | Why |
|---|---|---|
| collection / group / date / media_type / asset_class | **AUTO** | Deterministic — derived from the ingest prefix and file metadata. No model risk. |
| scene tags, caption | **AUTO** | VLM (Gemini Flash). Low blast radius if imperfect. |
| artwork | **AUTO above high confidence, else review** | Filename match against known work slugs auto-applies; a model guess goes to the review queue. |
| person | **REVIEW unless very high confidence** | Mislabelling a person is worse than an untagged photo. Unknown faces stay untagged — never a cold identify of a stranger. |

The review queue is just tags carrying `"status": "pending"`. Agents selecting assets for anything outward-facing must filter `status == confirmed`.

**Face recognition is deliberately NOT part of this kit.** The reference design specifies self-hosted embeddings (InsightFace) matched only against an enrolled, project-internal gallery, precisely so no biometric template ever reaches a cloud API. If you add it, keep that posture: self-hosted, closed gallery, unknown = untagged, and check your own legal basis first.

---

## Layer 3 — query, sharing, playback

**Query.** `tools/media_query.py` builds a DuckDB view over the catalogue read **fresh from the bucket each run** (zero sync drift — there is no mirror database to keep in step) and joins optional parquet exports of your project's entities. Canned queries cover the common asks; `--sql` handles the rest.

**Sharing.** R2's public access is bucket-wide only, so a physically separate public bucket *is* the per-asset allowlist. `media_store.py publish` copies one asset across and records the permanent URL in the catalogue; `unpublish` deletes it. This fails safe: nothing is reachable unless someone deliberately copied it. Videos publish as a derived faststart copy so they stream instead of downloading first.

**Playback.** Agents and the local Library UI use short-TTL presigned URLs, which are seekable — ffmpeg can pull three frames out of a 900 MB clip over HTTP range reads, transferring a few megabytes instead of the file. That is `media_store.py frames`, and it is the default way to inspect video.

---

## Layer 4 — Glance (far-LOD visualization)

A second, zoom-out-first surface: every asset renders as one colored tile in a single instanced
WebGL draw call, clustered by event or date, resolving to real thumbnails as you zoom in. It is
read-only by construction — `serve_atlas.py` has no catalogue-mutation route.

**Build the two derived artifacts** (both read only from the local thumbnail cache — zero R2
egress), **then serve:**
```
<py> tools/media-engine/build_field.py    # per-asset layout seed + dominant color
<py> tools/media-engine/build_atlas.py    # packs thumbnails into texture-atlas sheets
<py> tools/media-engine/serve_atlas.py    -> http://127.0.0.1:8767
```
Re-run the two build steps after every ingest.

**Tap a tile** to open its metadata card: the full catalogue record (context / content /
provenance), tap-to-copy identifiers, and in-place video playback via a short-TTL presigned URL
(seekable — the browser scrubs directly off the store with no proxy).

**Optional sign-in layer** (`glance/auth.js`, `glance/login.js`, backed by Supabase Auth — email
one-time-code or Google OAuth): once configured, signed-in visitors get a **download** affordance
(`glance/download.js`) — a single "Download original" button on the card, or multi-select
(long-press / tap-to-select) → zip. Leave `supabase_domain` / `supabase_anon_key` unset at install
time and Glance runs happily in browse-only mode; the login bubble just becomes a quiet
sign-in prompt with downloads disabled.

**Publishing Glance publicly** (its own static site, separate from your working repo) is a
distinct step: `build_glance_dist.py` assembles a static bundle — the frontend plus a
**field-whitelisted** catalogue export (only display-safe columns; internal provenance, local
paths, and processing notes are stripped, and the build **aborts** if a fail-closed leak-marker
check finds anything internal in the sanitized output). The result lands in `tools/media-engine/dist/`
(gitignored — it is a per-deploy build artifact, not source) and is what you'd actually push to a
static host; anything requiring a mutation (if you build one) stays behind a **separate, gated
write origin** that is never part of this public bundle.

---

## File map

| File | Role |
|---|---|
| `tools/media_store.py` | Layer 1 + publish. Importable API and CLI: `check upload download list delete manifest tag presign frames download-batch publish unpublish published query` |
| `tools/media_query.py` | Layer 3 SQL. `--canned artist\|day\|scene\|person-events` or `--sql` |
| `tools/media_archive_verify.py` | Self-test: deps, creds, bucket, round-trip, catalogue |
| `tools/media-engine/ingest.py` | The pipeline: discover → checksum → dedupe → upload → verify → thumbnail → caption → embed → catalogue |
| `tools/media-engine/serve.py` | Local web server (Engine Room + Library) on 127.0.0.1:8766 |
| `tools/media-engine/engine.{html,css,js}` | The UI |
| `tools/media-engine/fetch_dropbox.py` | Pull shared-link deliveries into a staging folder |
| `tools/media-engine/kb_export.py` | Optional: your entities → parquet, for SQL joins |
| `tools/media-engine/build_field.py` | Glance: per-asset layout seed + dominant color |
| `tools/media-engine/build_atlas.py` | Glance: packs thumbnails into texture-atlas sheets |
| `tools/media-engine/serve_atlas.py` | Glance: read-only server on 127.0.0.1:8767 |
| `tools/media-engine/glance/` | Glance frontend: field view, metadata card, optional sign-in + download |
| `tools/media-engine/build_glance_dist.py` | Builds the static, sanitized public Glance bundle (`dist/`, gitignored) |
| `tools/skills/media-archive/SKILL.md` | The agent protocol (modes + hard rules) |
| `.claude/agents/media-archivist.md` | Custodian subagent for ingest and catalogue hygiene |

## The ingest ledger

Every run enforces:

```
discovered == catalogued + quarantined + duplicates + excluded + in_pipeline
```

A run is finished when that **balances** — not when it stops printing. Quarantined files are swept by simply re-running (the pipeline is idempotent by sha256). Treat an unbalanced ledger as a failed run.
