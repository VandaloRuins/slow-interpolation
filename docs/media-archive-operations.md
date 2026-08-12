# Media Archive — Operations

Everything here was learned running a ~900-asset / 51 GB archive over a consumer connection. Keep the rules that apply; delete the ones that don't.

## The hard rules

1. **Single writer.** The catalogue is one JSON object in the bucket — two concurrent writers means one of them loses data silently. Before any catalogue write (ingest, publish, review), check `tools/media-engine/cache/run-state.json`: `phase` must be `idle` / `done` / `failed`. Reads and downloads are always safe and need no check.
2. **Originals are immutable.** Never re-upload, transcode or overwrite an archived original. Derived copies go under `thumbs/` and `web/`.
3. **Publishing needs explicit per-asset clearance** from the project owner, naming the asset, in the current conversation. Same discipline as sending an email on someone's behalf. Default-private, forever.
4. **Media never enters git.** Downloads go to a scratch folder. The tracked truth is the catalogue, the provenance docs, and `_SOURCES.md`-style pointers.
5. **Record provenance BEFORE ingesting.** Write down who sent what, which link, and what it covered. Share links expire — that link rot is the entire reason to run an archive.
6. **Delete staging only after every file is sha-verified in the bucket.**

## Ingest recipe

```
1. Provenance doc      who / what / which link / what it covers        <- first, always
2. Propose the batch   source dir, key prefix, group slug, asset_class, artists, known artworks
3. Owner OK
4. Fetch               fetch_dropbox.py --manifest <json> --staging <dir>   (staging OFF any cloud-synced folder)
5. Dry run             ingest.py ... --sample 5                             <- eyeball tags before committing
6. Full run            ingest.py ... --yes
7. Ledger must BALANCE  discovered == catalogued + quarantined + duplicates + excluded + in_pipeline
8. Re-run to sweep quarantines (idempotent by sha256)
9. Delete staging
```

A run that stops printing is not a run that finished. **The balanced ledger is the only success criterion.**

## Failure modes seen in the wild

| Symptom | Cause | Response |
|---|---|---|
| Multi-minute uploads dying with SSL resets | Consumer upload line dropping long transfers | Already tuned: small multipart chunks, low concurrency, whole-file retries with fresh clients. Just re-run — dedupe skips what landed. |
| The same photo in two day-folders | Delivery zips overlap at day boundaries | sha256 dedupe handles it. Never dedupe by filename. |
| Dates off by one day | Camera clock drift; some sets have EXIF stripped entirely | Folder labels beat EXIF. Set `date_basis: folder-label`. |
| Videos invisible to search | Not captioned at ingest | Caption videos from their poster frame in the same pass as photos. Backfill from cached posters (`cache/thumbs/{sha16}.jpg`) — zero re-download. |
| Assets with `event: null` | Ingested under a prefix with no group slug | Review-queue prep; fix with a scripted single-pass catalogue edit, never manual JSON surgery. |

## Cost control

- Retrieval is free (zero egress). Pull as often as you like.
- The expensive operations are **your time and bandwidth**, not the bill. Prefer, in order: catalogue query → cached poster → `frames` over a presigned URL → full download.
- Captioning is the only per-asset money cost: roughly €1-3 per 3,000 images.
- The `_selftest/` prefix left by `media_archive_verify.py` is cleaned up automatically.

## Health checks

```
py -3.11 tools/media_store.py manifest --edition nyc-billboard
py -3.11 tools/media_query.py --sql "SELECT asset_class, media_type, count(*) FROM assets GROUP BY 1,2 ORDER BY 3 DESC"
py -3.11 tools/media_query.py --sql "SELECT count(*) FROM assets WHERE caption IS NULL OR caption = ''"
py -3.11 tools/media_query.py --sql "SELECT count(*) FROM assets WHERE event IS NULL"
py -3.11 tools/media_store.py published --edition nyc-billboard
```

## Starting a new collection

Everything is prefixed by collection, so a new one is just a new prefix: pass `--edition <new-collection> --prefix <new-collection>/...` to ingest. Nothing about the previous collection moves or changes. Generate proxies at ingest time while the files are still local — regenerating them later means re-downloading.
