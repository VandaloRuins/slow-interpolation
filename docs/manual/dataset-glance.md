# Dataset Glance mosaic (for agents)

**Not the curation gallery, and not the render gallery.** This repo now has three
display surfaces whose names overlap. Route by job:

| You need to | Use | Doc |
|---|---|---|
| Let a **student** ACT on dataset candidates (remove, crop, flag, export) | the dataset-curation gallery, `datasets/<name>/serve.py`, port 8765 | [gallery.md](gallery.md) |
| Show finished **renders** to the **maintainer** | `tools/gallery.py` over `outputs/`, or the outputs Glance view | [render-gallery.md](render-gallery.md) |
| **Browse, triage, or share the current state of a dataset**, read-only: finals only, staged crops applied, searchable audit and curation tags | the dataset Glance mosaic, `tools/mosaic-glance/` | this page |

The mosaic is a tier 0 Glance archive (the same viewer the render gallery uses,
resolved via `$GLANCE_HOME`, treated as a released dependency).
It is a *view* of `datasets/<name>/`, never a writer of it: the builder reads the
dataset's own truth and writes only under `tools/mosaic-glance/`.

## When you reach for it

- A quick full-field look at what the training set currently IS, with the
  student's staged crops rendered and the removed images gone.
- Triage before or after a curation pass: search gathers audit subsets
  (`watermark`, `was-framed`), curation state (`my-cropped`, `crop-applied`),
  dup families (`dup`), museums, years. Near-duplicate families also sit
  adjacent on the field.
- The browsable record of a finished dataset for the workstream progress doc.
- **Never for Phase 3 itself.** The mosaic has no verbs: no remove, no cropper,
  no flags, no export. The Glance data contract is read-only at tier 0 and the
  student must do their pass in the curation gallery. Do not brief them into
  the mosaic for review work.

## Stand it up

```bash
py -3.11 tools/mosaic-glance/build_mosaic_archive.py --dataset <name> --out tools/mosaic-glance/site-<name>
python -m http.server -d tools/mosaic-glance/site-<name> 8769
```

One site directory per dataset (`site-<name>`), so multiple mosaics can serve at
once. Port convention: 8765 is the curation gallery, 8767 is the Glance repo's
own demo server, use 8768+ for mosaics. First time for a new dataset, install
the viewer payload into the site directory before building:

```bash
python "$GLANCE_HOME/install.py" \
  --target tools/mosaic-glance/site-<name> --config tools/mosaic-glance/glance-config-<name>.json
```

(copy `glance-config-hammershoi.json`, change the `collection` chip). Existing
sites: `site/` is renoir-flowers, `site-hammershoi/` is hammershoi.

## What the build encodes

- **Finals only.** It reads `raw/` (so anything in `rejected/` is already out)
  and additionally excludes files with a pending `remove` flag in
  `gallery-state.json`.
- **Crops applied.** Staged crops from `gallery-state.json` are rendered into
  the archive copies at build time (rotate then bbox, same semantics as
  `apply_browser_crops.py`), unless `processed.json` shows the crop was already
  baked into `raw/`. The dataset files are never modified. Applied files carry
  the `crop-applied` tag.
- **Clusters** = audit status from `metadata.csv` (`clean` / `was-framed` /
  `white-border` / `watermark`, exclusive by precedence watermark > frame >
  border). A dataset with no audit flags renders as one `clean` cluster; that
  is honest, not broken.
- **Dup families** = phash union-find at Hamming <= 10 (same threshold as
  `build_gallery.py`), carried as `dup-N` tags and as the viewer's `subgroup`,
  which packs family members adjacent.
- **Card** = title + year + Phase 4 training caption, artist chip, tag chips,
  sha256 provenance. Dates are file mtime (honestly badged FILE TIME) since
  museum scans carry no EXIF.
- The build self-verifies twice (the importer's join check, then a re-check
  after tag enrichment) and exits non-zero on failure. A clean exit means the
  join is intact.

## Rebuild triggers

Rebuild after ANY curation change you want reflected: crops saved, images
removed, a re-audit, new captions. The build is deterministic from the dataset
files and takes under a minute; there is no incremental mode and no need for
one.

## Verify before you hand over a link

Do not report success from a 200. Load the page and check:

- resting count equals `raw/` count minus pending removes
- console clean (a favicon 404 is the browser, ignore it)
- zero `/api/*` requests (tier 0 gating working)
- search `crop-applied` rings exactly the applied-crop count
- tap one tile, the card shows the right record

## Sharing

`http://127.0.0.1:<port>/` works on this machine only. For a link someone else
can open, use the workshop's ephemeral-tunnel pattern (see `tunnel-url.txt`
history), and get the maintainer's go-ahead first: a tunnel exposes the full
image set publicly for its lifetime.

## Known limits (by contract, not by bug)

The Glance data contract has no verbs for mutating a local dataset at any tier,
so the curation gallery remains the only action surface. The full gap analysis
and the proposed contract extension live in the 2026-08-12 friction report;
tool-level detail in [`tools/mosaic-glance/README.md`](../../tools/mosaic-glance/README.md).
