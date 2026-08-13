# Dataset curation protocol (for agents)

You are an AI agent operating the universal image-collection protocol of this repo on behalf of a user. **This is the ONLY documented dataset-building protocol in this repo.** It applies to:

- LoRA training sets (Renoir florals, Thomas Cole landscapes, Casa del Suono frescoes, future domains).
- Reference image sets (Soutine figures for the Compositing workstream, any style-conditioning corpus).
- Validation hold-outs (5-image sets pulled out before training).
- Synthetic-data corpora (e.g., the ~80 Nano-Banana-generated Soutine figure images for the Compositing LoRA).
- Any other operation that requires sourcing, auditing, cropping, captioning, and curating an image collection.

If you find yourself about to write source / dedup / gallery / caption scripts from scratch, **stop**. Copy the existing scripts under `datasets/renoir-flowers/*.py` to `datasets/<your-name>/`, adapt the slot vocabularies + keyword lists, run. Surface to the user when you make non-default slot choices. Do NOT build a parallel system.

The user's role varies. In a workshop context they are a student who walks the gallery. In a research context (e.g. Compositing reference gathering) they are the operator who runs CivitAI and answers your narrow questions. In every case YOU run the protocol; the user supplies subject choice, slot approvals, and the manual gallery walk in Phase 3.

The output is a CivitAI-ready training ZIP plus metadata, captions, audit trail. If your downstream use is not LoRA training (e.g. a reference set for prompt-conditioning), skip Phase 5's ZIP packaging; the metadata + captions + curated `raw/` folder are still useful intact.

This page is your instruction manual. Read it once before starting. The companion tool reference is [gallery.md](gallery.md), which describes the only human-in-the-loop step (Phase 3) and the JSON contract the user hands back to you.

The Renoir floral dataset under [../../datasets/renoir-flowers/](../../datasets/renoir-flowers/) is the canonical worked example. Every script you copy from it already implements the protocol; your job is to adapt slot vocabularies and keyword lists, not to re-derive the plumbing. The Soutine figures dataset under `datasets/soutine-figures/` is the second worked example (Compositing workstream, 2026-05-18).

## What this protocol assumes

- The collection target is 5 to 200 source images, depending on use (5 to 10 for a reference set, 80 to 200 for a LoRA training set).
- The user can run the gallery in a browser, click `×` and `✂`, and trust you with everything else. They cannot edit Python scripts.
- You have shell access, file-system write access under `datasets/<name>/`, and outbound network access for sourcing.
- You have a `GOOGLE_API_KEY` environment variable for Gemini calls. If you do not, ask the user to set one before Phase 2.

If any of these assumptions does not hold, stop and clarify with the user.

## The five phases

| Phase | What you do | Student involvement |
|---|---|---|
| 1. Source | Scrape canonical origin, filter, download | Confirms subject definition; approves keep / reject token lists if you ask |
| 2. Audit + crop | Run Gemini vision audit, apply auto-crops, perceptual-hash dedup | None |
| 3. Human review | Stand up gallery server; instruct student; wait | Walks the mosaic; removes off-topic; manual-crops borderlines; exports JSON |
| 4. Caption | Run rule-based caption generator; hand-fix fallbacks | None (you ask them to skim 3 to 5 sample captions before committing) |
| 5. Hand-off | Build training ZIP; pick validation hold-out; brief the student on training | Confirms final image count + trigger word; runs the upload themselves |

Walk these in order. Do not skip ahead.

## Phase 0: Bootstrap

Before any work, set up the dataset folder.

1. **Confirm the subject with the student.** Ask: subject family (one tight phrase), the artist or style label (if any), the intended target subject family at inference time (if different from the training subject; e.g. "I want to train on Renoir vases but generate flower fields"). The third question matters for Phase 3 review priorities.
2. **Pick a folder name and trigger word.** Folder: lowercase-kebab, e.g. `vermeer-interiors`. Trigger: 3 to 4 lowercase letters orthogonal to any real English / Italian / French word. Examples: `tcole` (Thomas Cole), `cds` (Casa del Suono), `rfl` (Renoir flowers), `vmr` (Vermeer). Run the trigger past the student before committing; they have to type it at inference time.
3. **Copy the Renoir scripts to the new folder.**
   ```bash
   mkdir -p datasets/<name>/{raw,raw_orig,rejected/{non-target,dupes,user-removed},validation,gallery-state.backups}
   cp datasets/renoir-flowers/{source_commons,gemini_review,gemini_review_pass2,apply_crops,apply_crops_pass2,apply_browser_crops,dedup,finalize_metadata,update_metadata_post_process,captions,build_gallery,serve,package_for_civitai}.py datasets/<name>/
   ```
4. **Edit `source_<origin>.py` for the new domain.** See Phase 1 below.
5. **Confirm `GOOGLE_API_KEY` is available.** Read it from `~/.env` or wherever the project keeps secrets. If missing, ask the student to set one before continuing.

## Phase 1: Source

The single most important decision in the whole protocol. A LoRA trained on bad scans cannot be saved by clever hyperparameters. Default to one canonical origin; mix only if under-delivered.

### Origin selection

| Domain | Default origin | Fallback |
|---|---|---|
| Public-domain paintings (pre-1929 artist) | Wikimedia Commons via MediaWiki API | WikiArt, Met / AIC / Cleveland APIs |
| Modern art (post-1929) | Skip; copyright issues. Ask the student for a licensed alternative. | n/a |
| Photographs (public-domain or CC0) | Wikimedia Commons; Library of Congress digital collections | Flickr Commons |
| Illustration / book covers | Internet Archive book scans | The student's own legally-sourced collection |
| Textures / surfaces | The student's own photo set | CC0 stock libraries |

Strong opinion: source from ONE high-quality origin first. The Renoir dataset is 100% Wikimedia and shipped at 110 keepers.

### Adapt `source_<origin>.py`

The Renoir script ([source_commons.py](../../datasets/renoir-flowers/source_commons.py)) is the template. Three things to change per domain:

1. **Search queries.** The Renoir list runs 21 floral keyword queries. Replace with the new subject's keyword set. Aim for 15 to 30 queries that vary phrasing without drifting off-topic.
2. **Keep tokens.** Tokens that, if present in an image title, qualify it for download. Renoir uses `bouquet`, `roses`, `vase`, `peonies`, etc.
3. **Reject tokens.** Tokens that, if present, exclude the image. Renoir uses `portrait`, `bather`, `nude`, `landscape`, `drawing`, `sketch`, `watercolour`. Always include `drawing`, `sketch`, `engraving`, `etching`, `study` unless you specifically want them; they introduce surface inconsistency.

Default resolution floor: 768 px on the short side absolute minimum, 1024 px preferred. Default JPEG quality on save: q=95 RGB.

### Run the source pass

```bash
py -3.11 datasets/<name>/source_<origin>.py
```

Expected output: 200 to 400 candidates in `datasets/<name>/raw/`. If you get under 150, the keyword set is too narrow; widen and re-run. If you get over 600, the keep tokens are too generous; tighten and re-run.

### Manual triage (a fast one, just for obvious failures)

Before the Gemini audit, glance at the filenames and remove obvious non-target leak-throughs (the Renoir pass found 217 wrong-artist Renoirs and 10 subject-mismatch Renoirs at this stage). Programmatically:

```bash
# Inspect filename distribution
ls datasets/<name>/raw/ | sort | head -50
# Remove obvious non-matches
mv datasets/<name>/raw/<wrong-file>.jpg datasets/<name>/rejected/non-target/
```

You may ask the student to scan the candidate list at this point if you are unsure about a domain. Otherwise proceed.

## Phase 2: Audit and crop

Two killers in public-domain scans: physical frames (gilded wood) and white-paper borders (book scans). Watermarks are softer but worth flagging. Gemini 2.5 Flash + strict-JSON prompt is the cheapest reliable audit.

### Run the audit

```bash
py -3.11 datasets/<name>/gemini_review.py
```

This writes `processed.json` with one record per image: `has_physical_frame`, `has_white_or_paper_border`, `has_watermark`, `painting_bbox_pct`, `needs_crop`.

Cost: about $0.001 per image. For 300 candidates: ~$0.30.

### Apply the auto-crops

```bash
py -3.11 datasets/<name>/apply_crops.py
```

Backs up originals to `raw_orig/`. Upscales with LANCZOS if the cropped short side falls below 768.

### Second pass on the worst offenders

The first pass over-includes (Gemini is conservative on bbox tightness). Re-audit the still-framed subset with tighter prompting:

```bash
py -3.11 datasets/<name>/gemini_review_pass2.py
py -3.11 datasets/<name>/apply_crops_pass2.py
```

### Dedup

Perceptual-hash dedup at Hamming threshold 8 (strict, deletion threshold).

```bash
py -3.11 datasets/<name>/dedup.py
```

Moves duplicates to `rejected/dupes/`. Keeps the highest-resolution copy of each cluster.

### Finalize metadata

```bash
py -3.11 datasets/<name>/finalize_metadata.py
```

Re-queries the source per surviving file, writes `metadata.csv` with title, year, collection, source URL, dimensions, license.

### Validation gate before Phase 3

Confirm before handing to the student:

- `raw/*.jpg` count between 100 and 200.
- `metadata.csv` row count equals file count.
- `processed.json` exists with one entry per file.

If the file count is below 100, return to Phase 1 with relaxed filters. Do not put the student in front of a thin gallery; they will lose patience.

## Phase 3: Human review (the gallery, the ONLY human-in-the-loop step)

This is the only phase you cannot complete yourself. The student must visually inspect the mosaic, remove off-topic images, manually crop borderline framings, and export their work. Your job is to set up the gallery, brief the student clearly, wait, and process their output.

### Set up

```bash
py -3.11 datasets/<name>/serve.py
```

That command rebuilds `gallery.html`, starts a local HTTP server on port 8765, and opens the default browser to the gallery URL. Leave the terminal running for as long as the student is reviewing.

### Brief the student

Hand them the exact text below (or paraphrase, keeping every concrete instruction):

> Your dataset gallery is open in the browser. Every painting in the candidate set is one card. Walk every card. For each:
>
> - If it should not be in the dataset, click the red `×` button (top-right of the card). The image is removed immediately; you have 5 seconds to undo via the toast at the bottom of the screen.
> - If the framing is off (visible frame, white margin, off-axis crop), click the green `✂` button. The cropper opens full-screen. Drag the rectangle inside the image, optionally rotate 90° with the `↺` / `↻` buttons, then click `Save crop`. The card updates to preview the new crop.
> - If you want to revisit a card later, click the amber `⚐` button to flag it for frame review.
> - Use the filter chips under the title to walk subsets: `Was framed`, `White background`, `Watermark`. Validate the audit's calls; remove what it missed.
> - Look for amber `dup N` pills on cards. Those are near-duplicates that have been pulled adjacent in the mosaic. Compare side by side and remove the worse copy.
>
> When done, click `Export flags + crops` in the toolbar (top-right area). A JSON file downloads. Send it back to me along with a one-line confirmation: "done, N cards left".
>
> Full tool reference if you get stuck: [docs/manual/gallery.md](gallery.md).

Plan for 60 to 90 minutes of student time on a 150-card dataset. Do not start any other work that depends on Phase 3 output until they confirm done.

### Process the returned JSON

The student hands you a `gallery-flags.json` file (downloaded to `~/Downloads/` by default) containing their flags and manual crops. Bake the manual crops onto the JPEG files:

```bash
py -3.11 datasets/<name>/apply_browser_crops.py
```

The script reads `~/Downloads/gallery-flags.json`, backs up originals to `raw_orig/`, applies bbox + rotation, upscales if needed, updates `processed.json`.

### Optional: full-field re-check in the Glance mosaic

For a fast second look at what survived the pass (removed images gone, crops
rendered), build the read-only dataset Glance mosaic per
[dataset-glance.md](dataset-glance.md). It is a view, not an action surface; do
not send the student back into it to review. Useful when you want to eyeball
the whole set at once or gather subsets by search (`crop-applied`, `dup`,
`watermark`) before committing to Phase 4.

### Validation gate before Phase 4

Confirm:

- `raw/*.jpg` count is now between 80 and 180. If under 80, ask the student whether they want to source more or accept the sparse set.
- No file in `raw/` lacks a corresponding `metadata.csv` entry. Regenerate metadata if so:
  ```bash
  py -3.11 datasets/<name>/finalize_metadata.py
  py -3.11 datasets/<name>/update_metadata_post_process.py
  ```

## Phase 4: Caption

Captions are the second-most-important decision after sourcing. SDXL learns the association between the trigger word + caption tokens and the visual content. Bad captions waste training capacity.

### Adapt `captions.py`

The Renoir version ([captions.py](../../datasets/renoir-flowers/captions.py)) uses a rule-based deterministic captioner with this template:

```
<trigger>, <subject>, <composition>, <palette / light>, <brushwork / surface>, <style suffix>
```

Edit three things per domain:

1. **Trigger word**, from Phase 0.
2. **Slot vocabularies** (subject keywords, composition cues, palette descriptors, brushwork patterns). The Renoir version has subject keywords like `roses`, `peonies`, `anemones`. Replace with the new domain's vocabulary.
3. **Style suffix.** Two or three tokens that re-appear in every caption and act as an anchor. Renoir: `oil painting, impressionist`. Vermeer: `oil painting, baroque interior`. A textile LoRA: `loom-woven, jacquard`. A photograph LoRA: `35mm film, kodachrome`.

Target: 30 to 60 words per caption. Aim for 33 to 45.

### Run the captioner

```bash
py -3.11 datasets/<name>/captions.py
```

Writes `captions.json` (structured records) and `captions.txt` (training-format, `filename\tcaption` per line).

### Audit fallback rate

A rule-based generator falls back to a generic caption when no subject keyword matches the filename + title. Count fallbacks:

```bash
py -3.11 -c "
caps = open('datasets/<name>/captions.txt', encoding='utf-8').readlines()
fallback_marker = '<the fallback phrase from your captions.py>'
fallbacks = [c for c in caps if fallback_marker in c]
print(f'fallbacks: {len(fallbacks)} / {len(caps)}')
for c in fallbacks: print(c.split(chr(9))[0])
"
```

Decision tree:

- **Under 5 fallbacks**: hand-rewrite them. Edit `captions.json` directly per image, regenerate `captions.txt` from it.
- **5 to 15 fallbacks**: run a one-shot Gemini Vision call on just those filenames; reshape the result into your caption template. Code pattern:
  ```python
  # Pseudocode, adapt to your setup
  for fn in fallback_filenames:
      response = gemini.call(image=fn, prompt="Describe this in 6 to 10 words for: subject, composition, palette, brushwork. JSON.")
      cap = f"{trigger}, {response['subject']}, {response['composition']}, {response['palette']}, {response['brushwork']}, {style_suffix}"
      update caption for fn
  ```
- **Over 15 fallbacks**: the subject-classifier in `captions.py` is too narrow for the dataset. Add more keywords to the slot vocabularies and re-run before falling back to Gemini.

Do not vision-caption the whole dataset. Vision-captioned style LoRAs absorb the captioner's quirks instead of the style. Rule-based for the bulk; vision only for the tail.

### Show 3 to 5 samples to the student

Before declaring captions done, paste 3 to 5 sample captions to the student. Ask: "do these read like reasonable descriptions to you?". If they push back, the slot vocabularies need adjustment. Iterate before shipping.

## Phase 5: Hand-off

### Pick the validation hold-out

Pull 5 images from the training set and reserve them as a visual yardstick. They should cover:

- 2 canonical / mainstream images. The "if the LoRA cannot reproduce these, training failed" baseline.
- 1 minority-subject image. Tests generalisation on sparse evidence.
- 1 cross-domain composition (a subject the LoRA saw rarely).
- 1 off-distribution case (a subject family the LoRA did NOT see, if applicable). Pulling this from training means the LoRA trains on zero examples of it; this tests extrapolation.

Move them to `validation/`:

```bash
mv datasets/<name>/raw/<file1>.jpg datasets/<name>/validation/
mv datasets/<name>/raw/<file2>.jpg datasets/<name>/validation/
# ... etc
```

Document the choices in the workstream's `docs/planning/workstreams/<name>/progress.md` as a hold-out table.

### Build the training ZIP

```bash
py -3.11 datasets/<name>/package_for_civitai.py
```

Writes `<name>-civitai.zip` with one `.jpg` + one `.txt` per training image. Verify the count = `raw/` count post-hold-out.

### Brief the student on training

The canonical training path is **Modal**, not CivitAI. Train via [`train-lora-on-modal.md`](train-lora-on-modal.md). Headline:

- No third-party vendor account required (no CivitAI, no fal.ai).
- ~$1.50 + ~45 min on L40S for the standard 80 to 110 image shape.
- Renoir cold-run validated 2026-05-18 by the Modal-trainer workstream. The Modal-trained Renoir LoRA matches CivitAI on bouquets and visibly outperforms on fields.

The protocol you walk after handing the ZIP to the student (or doing it yourself if no student is in the loop):

1. `modal run -m cloud.upload_dataset --src datasets/<name>/<name>-civitai.zip`
2. `cp examples/configs/training/_template.yaml examples/configs/training/<name>.yaml`, fill the 4 TODO fields (see [`train-lora-on-modal.md`](train-lora-on-modal.md) Step 3).
3. `cp examples/configs/validation/renoir.yaml examples/configs/validation/<family>.yaml`, edit the 11 prompts to exercise the new domain.
4. `modal run -m cloud.train_entrypoint --config examples/configs/training/<name>.yaml`
5. `modal run -m cloud.validate_lora --config examples/configs/validation/<family>.yaml --epoch 10` (repeat for epochs 1 and 5).
6. Open `outputs/validation/<family>/epoch-10/` and review against the 5 exit criteria in [`train-lora-on-modal.md`](train-lora-on-modal.md) "Exit criteria".

When training finishes, the Modal trainer's `publish` block auto-copies checkpoints to the top of the `slow-interp-loras` Modal volume as `<Family>_<Subject>_epoch_<N>.safetensors`. The renderer reads from that volume; nothing else needs doing for production rendering. For local dev / offline rendering: `modal volume get slow-interp-loras <Family>_<Subject>_epoch_<N>.safetensors models/loras/`.

CivitAI is now optional / archival. Use it only if Modal is down or the user explicitly requests a CivitAI A/B (see [`../findings/lora-training.md`](../findings/lora-training.md) for the engine comparison).

### Open a workstream progress doc

Create `docs/planning/workstreams/<name>/progress.md` if the student's project is non-trivial. Log:

- Dataset shape (file count, hold-out list, subject distribution).
- Audit + crop decisions (any unusual rejections).
- Caption fallback resolution notes.
- The training brief sent to the student.

This unblocks the parent chat (and you, on resume) from re-deriving context.

### Publish the final set as a Glance mosaic (recommended)

Build the dataset's read-only Glance mosaic ([dataset-glance.md](dataset-glance.md))
once the set is final, and log the rebuild command in the progress doc. It is
the browsable record of exactly what the LoRA trained on: finals only, crops as
trained, captions on the card, dup families adjacent. Anyone asking "what is in
the X dataset" gets a link instead of a folder listing.

## Failure modes and how you should react

| Symptom | Cause | Your action |
|---|---|---|
| Phase 1 returns under 100 candidates after filtering | Keep tokens too narrow OR domain genuinely thin | Widen keep tokens; if still thin, propose a mixed-origin strategy to the student |
| Gemini audit returns malformed JSON on >5% of calls | API rate limit OR prompt drift | Add a retry loop with strict-JSON re-prompting; cap at 3 retries |
| Student takes >2h on Phase 3 review | Dataset too big for one session OR ambiguous what to remove | Pause and ask. Offer to pre-filter another pass before they resume |
| Student returns `gallery-flags.json` with no flags / crops | They did not understand the workflow | Re-brief with a concrete example ("click `×` on these three") |
| Caption fallback rate over 15% | Slot vocabulary too narrow | Add domain keywords to `captions.py`; do NOT vision-caption the bulk |
| LoRA renders well in distribution but fails on the off-distribution prompt | Subject specificity correct; LoRA cannot extrapolate to subjects it never saw | Either accept and raise `lora_scale` per [../findings/lora-training.md](../findings/lora-training.md) §6, or source 15 to 25 examples of the off-distribution subject and retrain |
| Visible colour cast in outputs | Training data dominated by one origin's scan colour (auction catalogues are a common offender) | Pass 2 in kohya_ss with per-image repeats to down-weight the over-represented origin |
| Student asks for "synthetic data with Gemini / Nano-banana / FLUX" | Common request, almost always wrong | Refuse and explain: training on synthetic style-imitations distills the imitation, not the style. Source real images instead, even if fewer |

## File inventory you will produce

```
datasets/<name>/
  raw/                       <- training images, 80 to 200 JPEGs
  raw_orig/                  <- pre-crop backups (gitignored)
  rejected/
    non-target/              <- subject-mismatch removals
    dupes/                   <- perceptual-hash duplicates
    user-removed/            <- removed via gallery × button
  validation/                <- 5 hold-out images + their captions
  metadata.csv               <- one row per file in raw/ (TRACKED in git)
  captions.json              <- structured caption records
  captions.txt               <- training-format captions
  phashes.json               <- perceptual-hash cache
  processed.json             <- audit log of crops + upscales
  gallery.html               <- generated by build_gallery.py
  gallery-state.json         <- gallery flags + manual crops (gitignored)
  source_<origin>.py         <- sourcing script (you adapted)
  gemini_review.py           <- vision audit
  apply_crops.py             <- crop application
  apply_browser_crops.py     <- bakes manual crops from gallery
  dedup.py                   <- perceptual-hash dedup
  finalize_metadata.py       <- metadata regeneration
  captions.py                <- rule-based captioner (you adapted)
  build_gallery.py           <- gallery generator
  serve.py                   <- gallery HTTP server
  package_for_civitai.py     <- training ZIP builder
  <name>-civitai.zip         <- training payload (gitignored)
```

Gitignore: `raw/`, `raw_orig/`, `rejected/`, `validation/`, `*.zip`, `gallery-state.json`, `gallery-state.backups/`, `gallery-state.log.jsonl`, `processed.json`. Track `metadata.csv` and the scripts.

## Time budget

| Phase | Your time | Student time |
|---|---|---|
| 0. Bootstrap | 15 min | 2 min (confirm subject + trigger) |
| 1. Source | 30 to 60 min | 0 to 5 min (sanity check candidate list) |
| 2. Audit + crop | 20 min compute, 5 min review | 0 |
| 3. Human review | 5 min setup, then wait | 60 to 90 min |
| 4. Caption | 15 min | 5 min (sample review) |
| 5. Hand-off | 10 min | 30 to 90 min on CivitAI |

Total: half a day of your wall time, of which the student is engaged for 90 min to 2 h.

## What this protocol does not cover

- Character LoRAs (single face / outfit). Different captioning rules; see [../findings/lora-training-deep-dive.md](../findings/lora-training-deep-dive.md) §4.
- Multi-subject LoRAs. Almost always a bad idea; train separately, blend at inference.
- Live or online training. The protocol assumes one discrete training round.
- Synthetic data generation. Do not do this for style LoRAs (see failure modes table).
- Dataset versioning beyond `raw_orig/` backups. Layer git-LFS on top if the student needs it.

## When to stop and ask the student

Default to autonomy on script edits, API calls, file moves. Stop and ask when:

- Subject definition is ambiguous after Phase 0.
- Phase 1 candidate count is way outside 200 to 400.
- Caption fallback rate is over 15%.
- A reject decision in Phase 2 looks aesthetically borderline (frame is decorative not gilded; watermark is the artist's signature).
- The student's training target differs from the training subject (Phase 0 question 3). The dataset may need landscape / scene augmentation.
- Anything you would not do without supervision on a real client project.
