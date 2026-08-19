# Dataset Mosaic on Glance (read-only dataset viewer)

A rebuild of the dataset-curation gallery's *display* on the Glance WebGL viewer
(resolved via `$GLANCE_HOME`, treated as a released dependency and
never modified). The curation gallery at `datasets/<name>/gallery.html` +
`serve.py` keeps working unchanged and remains the only ACTION surface; nothing
under `datasets/` is ever written by this tool.

**Routing and protocol doc: [`docs/manual/dataset-glance.md`](../../docs/manual/dataset-glance.md).**
That page says which of the repo's three display surfaces to reach for; this
README is the tool-level reference.

## Run it

One site directory per dataset. Existing sites: `site/` (renoir-flowers, port
8768), `site-hammershoi/` (hammershoi, port 8769).

```bash
# rebuild an existing site after any curation change
py -3.11 tools/mosaic-glance/build_mosaic_archive.py --dataset hammershoi --out tools/mosaic-glance/site-hammershoi
python -m http.server -d tools/mosaic-glance/site-hammershoi 8769

# first time for a NEW dataset: install the viewer payload, then build
printf '{\n "title": "Dataset Mosaic",\n "collection": "<name>",\n "tier": 0\n}\n' > tools/mosaic-glance/glance-config-<name>.json
python <path-to>/Ruins-Harness_Tools-for-Agents/glance/install.py --target tools/mosaic-glance/site-<name> --config tools/mosaic-glance/glance-config-<name>.json
py -3.11 tools/mosaic-glance/build_mosaic_archive.py --dataset <name> --out tools/mosaic-glance/site-<name>
```

The build is deterministic from the dataset's own files and self-verifies the
sha16 join twice (the stock importer's gate, then again after tag enrichment);
it exits non-zero on failure.

## What the build encodes

- **Finals only.** Reads `raw/` (rejected images are already outside it) and
  additionally excludes files with a pending `remove` flag in
  `gallery-state.json`.
- **Staged crops applied.** Crops from `gallery-state.json` are rendered into
  the archive copies at stage time (rotate then bbox, mirroring
  `apply_browser_crops.py`), skipped when `processed.json` shows the crop was
  already baked into `raw/`. Dataset files are untouched; mtimes are preserved
  so the card's FILE TIME date stays honest. Applied files carry the
  `crop-applied` tag.
- **Clusters** = audit status from `metadata.csv` (`clean` / `was-framed` /
  `white-border` / `watermark`, exclusive by precedence watermark > frame >
  border). No audit flags means one `clean` cluster, which is honest, not
  broken.
- **Search** (literal substring, not tokenized): cluster names ring confident;
  a tag tail folded into the caption makes everything else findable as
  uncertain: `processed`, `my-cropped`, `my-flagged`, `crop-applied`, `dup`,
  `dup-N`, museum slugs, years.
- **Dup families** (phash union-find, Hamming <= 10, same threshold as
  `build_gallery.py`) become `dup-N` tags *and* the viewer's `subgroup`, which
  packs family members adjacent inside their cluster, the old page's
  dup-adjacency. hammershoi has 2 families; renoir-flowers has none left (min
  pairwise distance 12 after its dedup passes).
- **Card** = painting title + year + Phase-4 training caption, artist chip,
  tag chips, sha256/key/bytes provenance.

## What this tool deliberately does NOT do

The Glance data contract has **no verbs for mutating a local dataset** at any
tier it ships. The curation gallery's actions are not reproduced here:

| Curation gallery verb | Status here |
|---|---|
| `x` remove image (raw/ -> rejected/) | not in the contract at any tier |
| `crop` full-screen cropper -> staged crop | not in the contract (staged crops are RENDERED read-only at build time) |
| `flag for frame review` | not in the contract (surfaced read-only as `my-` tags) |
| `Export flags + crops` JSON | nothing to export; the viewer is read-only |

Stated per the integration brief: where the contract does not support an
action, say so rather than invent a workaround. The 2026-08-12 friction report
proposes a tier-0 "local annotation" contract extension if this view is ever to
fully retire the curation gallery.

## Files

- `build_mosaic_archive.py` -- stages `datasets/<name>/raw/` into an
  audit-status folder tree with `.txt` sidecar captions, applies un-baked
  staged crops, runs the STOCK `make_archive.py`, enriches
  `data/catalogue.json` (tags, subgroup, caption tail), re-verifies.
- `glance-config.json`, `glance-config-hammershoi.json` -- the configs
  `install.py` was given (tier 0, per-dataset `collection` chip).
- `site/`, `site-hammershoi/` -- installed Glance payload + built archive
  (`data/`, `atlas/`, `thumbs/`). Regenerated freely; never hand-edit
  `site*/data/`.
