# Dataset-curation gallery (for agents)

**Not the render gallery.** This page is `tools/gallery_server.py` over
`datasets/<name>/`, where a student keeps or cuts LoRA training candidates. If
you are showing finished MP4s or keyframe PNGs to the maintainer, you want
[render-gallery.md](render-gallery.md) and `tools/gallery.py` instead.

You are an AI agent helping a student build a LoRA dataset per the protocol in [dataset-curation.md](dataset-curation.md). The gallery is the only step you cannot run yourself: the student must visually walk every candidate image, remove off-topic content, and hand-crop borderlines. Your job is to stand the gallery up, brief the student, and process the JSON they hand back.

This page documents:

1. How to stand the gallery up.
2. What the student sees and clicks (so you can brief them accurately).
3. The contract for the JSON they export to you, and how you process it.
4. What to do when things break.

## How you stand it up

```bash
py -3.11 datasets/<name>/serve.py
```

The command:
1. Regenerates `gallery.html` from current `metadata.csv` + `captions.json` + `raw/` filesystem.
2. Starts a local HTTP server on `127.0.0.1:8765`.
3. Opens the default browser to `http://localhost:8765/gallery.html`.

Leave the process running for as long as the student is reviewing. Do not Ctrl-C it; the student's saves write to disk via the server within 300 ms of each click.

Custom port: `py -3.11 datasets/<name>/serve.py 9000`.
Skip the rebuild (just serve what is on disk): `py -3.11 datasets/<name>/serve.py --no-build`.

### Verify the server is healthy

Before briefing the student, probe:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8765/gallery.html
```

Expect `200`. If you get `000` or `connection refused`, the server did not start; check the terminal output for port conflicts (something else on 8765) or import errors. Use a different port and re-launch.

## What the student sees (your briefing crib sheet)

Use the briefing text in [dataset-curation.md](dataset-curation.md) Phase 3. The detail below is so you can answer questions if the student asks.

### The sync badge

Top-left of the sticky toolbar. The student should see **SYNCED (green)** within a second of the page loading. If they see:

- **LOCAL-ONLY (amber)**: they opened `gallery.html` by double-clicking (`file://` origin). Tell them to close the tab and open `http://localhost:8765/gallery.html` in the browser. The amber banner at the top of the page also offers a "Switch to synced version" button if you are running on the same machine.
- **SYNC ERROR (red)**: the server died or they lost network on localhost. Restart `serve.py` and tell them to click the "Reconnect" button.

Local-only mode keeps the student's work in browser localStorage, which means it does NOT come back to you when they export. They must be in SYNCED mode.

### Per-card buttons

Top-right of every card:

| Button | What it does |
|---|---|
| `✂` green | Opens the cropper full-screen for that image. |
| `⚐` amber | Toggles a "flag for frame review" marker. Card gets an amber ring. Non-destructive note. |
| `×` red | Removes the image immediately. File moves from `raw/` to `rejected/user-removed/`. 5-second undo toast. |

### Card badges (read-only)

Top-left of every card, from your Phase 2 audit:

- `dup N` amber: near-duplicate cluster of N images. Pulled adjacent in mosaic by perceptual hash.
- `cropped` gold: file already passed through auto-crop or upscale.
- `frame` orange: Gemini flagged a physical frame.
- `white-bg` blue: Gemini flagged a white / paper border.
- `watermark` rose: Gemini flagged a watermark.

### Filter chips (under the title)

`All`, `Cropped / upscaled`, `Was framed`, `White background`, `Watermark`, `My: review frame`, `My: cropped`.

Tell the student to walk `Was framed` first, then `White background`, then `Watermark`, then `All`. The audit subsets are the highest-value attention targets.

### Manual cropper

Opens full-screen when the student clicks `✂`.

- 4 corner handles, 4 edge handles, draggable middle.
- `↺` / `↻` buttons rotate 90° counter-clockwise / clockwise. Current rotation shows in a pill between the buttons.
- `Reset` returns to default 90% rectangle at current rotation.
- `Clear saved` forgets any saved crop for this file.
- `Save crop` persists the bbox + rotation (saved to `localStorage` AND to disk via the server within 300 ms).
- `Cancel` closes without saving.

Live pixel readout in the top bar shows the cropped dimensions at the image's native resolution.

After save: the gallery card behind the modal immediately previews the crop with a green ring and a `PREVIEW` pill. The underlying JPEG in `raw/` is NOT changed yet; the crop is staged. You bake it during Phase 3 cleanup with `apply_browser_crops.py`.

### Keyboard shortcuts

Tell the student (or do not; they are nice-to-have, not essential):

- `R` removes the hovered card.
- `F` toggles frame-review flag on the hovered card.
- `C` opens cropper for the hovered card.
- `Esc` cancels the cropper.

## The JSON contract you receive back

When the student clicks `Export flags + crops` in the toolbar, a file `gallery-flags.json` downloads to their default Downloads folder (typically `~/Downloads/` on Windows / macOS / Linux). Shape:

```json
{
  "version": 1,
  "updated_at": "2026-05-17T10:01:32.832559Z",
  "flags": {
    "<filename>.jpg": "review_frame"
  },
  "crops": {
    "<filename>.jpg": {
      "x": 5.0,
      "y": 5.0,
      "w": 90.0,
      "h": 90.0,
      "rotation_cw_deg": 0
    }
  }
}
```

- `flags`: filename -> flag-name. Currently only `review_frame` is emitted; if a student clicks `×`, the file has already moved on disk and is not in `flags`.
- `crops`: filename -> bbox in percentages of image dimensions, plus rotation. `x` and `y` are top-left of the rectangle; `w` and `h` are width and height. `rotation_cw_deg` is 0, 90, 180, or 270.

If the student is on the same machine you are running on, you can also read the server's live state directly:

```bash
cat datasets/<name>/gallery-state.json
```

This is the canonical source; `gallery-flags.json` (the download) is a snapshot of it.

## How you process the returned JSON

```bash
py -3.11 datasets/<name>/apply_browser_crops.py
```

The script reads `~/Downloads/gallery-flags.json` by default. It:

1. Loads each crop record.
2. Backs up the original to `raw_orig/` if not already backed up.
3. Rotates the image first (`im.rotate(-rotation_cw_deg, expand=True, resample=BICUBIC)`), then crops to the bbox.
4. Upscales with LANCZOS if the short side drops below 768.
5. Updates `processed.json` with the `browser_crop` op.

Validate after:

```bash
# All raw/ files should still have metadata
py -3.11 -c "
import csv, os
files = set(os.listdir('datasets/<name>/raw'))
meta = {row['filename'] for row in csv.DictReader(open('datasets/<name>/metadata.csv', encoding='utf-8'))}
print('orphan files:', files - meta)
print('orphan rows :', meta - files)
"
```

Any orphan files: re-run `finalize_metadata.py`. Any orphan rows: the student removed those files via `×`; you can ignore them, or run `finalize_metadata.py` to drop them from the metadata.

## Persistence (so you can answer "is my work safe?")

The student's flags + crops are durable:

- `datasets/<name>/gallery-state.json`: source of truth. Atomic-written. UTF-8.
- `datasets/<name>/gallery-state.log.jsonl`: append-only event log (every change, timestamped).
- `datasets/<name>/gallery-state.backups/gallery-state-YYYYMMDD-HH.json`: one rotating backup per hour.

If a `serve.py` crash corrupts the state file, restore from the most recent backup:

```bash
ls datasets/<name>/gallery-state.backups/
cp datasets/<name>/gallery-state.backups/gallery-state-YYYYMMDD-HH.json datasets/<name>/gallery-state.json
```

If the student accidentally removed an image they wanted, the file is in `datasets/<name>/rejected/user-removed/<filename>.jpg`. Restore either by moving the file back or via the running server's API:

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"filename":"<filename>.jpg"}' \
  http://localhost:8765/api/restore
```

Tell the student to refresh the gallery after either restore path.

## Card ordering you should know about

Cards are NOT alphabetical or chronological. They are arranged so near-duplicates land adjacent:

1. Perceptual hash (`phash`) of every JPEG in `raw/`. Cached to `phashes.json` keyed by `(filesize, mtime)`.
2. Union-find: any two files at Hamming distance <= 10 are merged into one cluster.
3. Within each cluster, members alphabetical. Clusters ordered by their first member's filename.
4. Cards in clusters of size >= 2 carry an amber `dup N` pill. The last card in a multi-member cluster gets extra bottom margin.

Threshold lives at `DUP_THRESHOLD = 10` at the top of `build_gallery.py`. Lower is stricter; higher clusters cousin paintings together.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Server starts but `gallery.html` shows "broken image" placeholders | `raw/` is empty | Re-check Phase 1 actually downloaded into `raw/` |
| Student says cropper opens with a single dot in the top-left | First-load layout race; harmless if they click "Reset" | Race condition fixed in current code; if it persists, refresh the page |
| Student says "rotation render failed" | They opened the gallery via `file://`; browser blocks canvas readback | Tell them to use the `http://localhost:8765` URL, not the file path |
| `apply_browser_crops.py` ignores half the saved crops | The student did not click `Export flags + crops` after saving | Ask them to click Export, then re-download |
| `gallery-state.json` has crops for files no longer in `raw/` | Files were removed via `×` after the crop was saved | Harmless; `apply_browser_crops.py` skips missing files |
| Sync badge stays amber even with server running | Page was loaded via `file://` | Use the localhost URL |
| Port 8765 is taken | Another process bound first | Launch on a different port: `serve.py 9000`. Tell the student the new URL. |

## What the gallery does NOT do

- It is not a training UI. No "send to CivitAI" button; you build the ZIP in Phase 5.
- It is not a captioning tool. Captions are rule-based and generated server-side in Phase 4.
- It does not support free-angle rotation, only 90° increments.
- It does not support brush-mask inpainting yet. Plan for fal.ai FLUX integration tracked at `docs/planning/workstreams/renoir-dataset/inpaint-plan.md`.

## When to write a counter-finding

If, while using the gallery on a real dataset, you discover behavior that contradicts this doc or the protocol, log it as a finding under `docs/findings/<topic>.md` per the convention in [../README.md](../README.md). Examples worth writing up:

- A new failure mode the troubleshooting table does not cover.
- A workflow optimisation (e.g. the student is faster if they walk filter chips in a specific order).
- A domain-specific gallery configuration (e.g. for character LoRAs you might want a different `DUP_THRESHOLD`).

The repo gets better when agents that find new things write them down.
