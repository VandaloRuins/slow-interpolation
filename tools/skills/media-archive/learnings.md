# /media-archive — learnings (data-rules + usage history)

Append durable data-rules, tagging conventions, and failure modes here after every custodial session.
Seeded with rules carried over from the reference implementation — keep the ones that hold, delete the ones that don't apply here.

## Inherited data rules (proven on a large production archive)
- **Folder labels beat camera EXIF.** Observed clock drift of a full day on one camera and EXIF stripped entirely on other sets. When a delivery folder is labelled with a date, record `date_basis: folder-label` and let it override EXIF.
- **Delivery folders overlap.** The same file routinely appears in two day-folders (a shoot spilling into the next zip). sha256 dedupe is what keeps the archive canonical — never dedupe by filename.
- **Consumer upload lines drop long transfers.** At ~1-2 MB/s the uploader must use small multipart chunks (2 x 32 MB, low concurrency) plus whole-file retries with fresh clients. Parallel 64 MB parts died mid-multipart with SSL resets. Re-runs are normal; a BALANCED ledger is the only success criterion.
- **Record provenance BEFORE ingesting.** Share links (Dropbox/WeTransfer) expire — that link rot is the reason this archive exists. Write the source doc (who sent what, which link, what it covered) first, ingest second.
- **Delete staging only after every file is sha-verified in the bucket.**

## Video handling (learned the hard way)
- Videos were second-class until fixed: caption them from their poster frame in the same VLM pass as photos, or they end up untagged and invisible to `find`.
- Backfilling captions from cached posters (`tools/media-engine/cache/thumbs/{sha16}.jpg`) costs zero re-download.
- `presign` + `frames` (ffmpeg over HTTP range reads) is the default way to inspect video. Downloading a 900 MB original to look at three frames is a mistake.

## Glance viewer UI learnings
Moved. The front-end rules from building the far-LOD viewer now live with the viewer
itself, in `glance/docs/engineering-notes.md` — d3-force accessor caching, iOS `dvh`
for bottom sheets, camera clamping during retrieval, `SO_REUSEADDR` masking a stale dev
server, presigned Range GETs for video scrubbing, and instrumenting read paths
off the hot path. They apply to anything built on that field, not just to this archive.

## Log new learnings below
