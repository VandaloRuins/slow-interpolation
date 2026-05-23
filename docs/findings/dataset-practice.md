# Dataset creation practice for LoRA training

What we have learned, end to end, building the Renoir flowers dataset from scratch. This is the recipe to follow for the next domain LoRA (Cézanne, Bonnard, Casa del Suono v2, whatever).

Companion docs:
- [lora-training.md](lora-training.md) — the CivitAI training playbook, written for the Renoir case but parameterised.
- [lora-training-deep-dive.md](lora-training-deep-dive.md) — theory + hands-on tools beyond CivitAI (kohya_ss, OneTrainer, AI Toolkit), objective-specific recipes, validation protocol, failure-mode diagnostics. Read this when you want to understand the *why* behind a parameter, or want more control than CivitAI's wizard.
- [renoir-dataset-progress.md](../planning/workstreams/renoir-dataset/progress.md) — the operational log of the actual Renoir build, with concrete numbers.
- [inpainting-options.md](inpainting-options.md) — solutions for masking out signatures, watermarks, and non-target subjects with style-aware AI fill.

Read this file before starting a new dataset. Read [lora-training.md](lora-training.md) for the training-time settings. Read the progress doc when you want a worked example with numbers.

## The shape of a Renoir-grade dataset

| Stat | Range we target | Renoir actuals |
|---|---|---|
| Image count | 80 to 200 | 118 keepers from 363 candidates |
| Short side, min | >= 768 px | 768 px after crop and upscale |
| Short side, median | >= 1500 px | ~1900 px |
| File format | JPEG q=95 RGB, sRGB | enforced |
| Subject dominance | target subject is dominant or notable | 96 still life + 22 scenes-with-flowers |
| Public domain status | PD-old or CC-BY at minimum | 100% PD-old, 17% CC-tagged reproduction photos |
| Trained captions | natural language, 30 to 60 words | rule-based, 33 to 39 words |
| Trigger word | 3 to 4 lowercase letters, orthogonal to real words | `rfl` (parallels `tcole`, `cds`) |
| Validation hold-out | 5 images, never in training | yes |

Below this volume the LoRA under-fits and starts hallucinating subjects. Above 250 the marginal gain flattens and the auction-catalogue colour cast risks dominating; the constraint is curation time, not data hunger.

## The five-phase recipe

Each phase is a script that lives next to the dataset under `datasets/<name>/`. Naming convention matters: every new LoRA gets the same script names so the workflow is muscle memory.

### Phase A — Source

Goal: download every plausible candidate, broadly. Filter on the title first (cheap), then on resolution from imageinfo (also cheap). Don't open the bytes until the candidate has cleared both.

**Sources, in this priority order:**

1. **Wikimedia Commons MediaWiki API** — `action=query&list=categorymembers` to walk an artist category, plus `action=query&list=search&srnamespace=6` for keyword searches. Commons aggregates the same museum scans the other APIs serve and gives you a single metadata schema. This was the only source we ended up using for Renoir.
2. **Wikimedia Commons category sub-walks** — `Category:Paintings by <artist> by subject`, `Category:Still life paintings by <artist>`. Catalogue-style filtering, lower noise than search.
3. **Art Institute of Chicago API** — open access, JSON, well-curated, high-res. Use when a specific painting is too low-res on Commons.
4. **Cleveland Museum of Art API** — similar profile to AIC.
5. **Met Museum API** — broader collection, occasional low-res scans, always cross-check `isPublicDomain=true`.
6. **WikiArt** — useful for "what does this artist paint" planning, but CDN images are typically 1000 to 1500 px short side. Skip unless filling specific gaps.
7. **Museum-specific pages, manual download** — only for the canonical paintings that demand the best scan available.

**Title filter pattern** (see [source_commons.py](../../datasets/renoir-flowers/source_commons.py)):

```python
# KEEP if any token from FLORAL_TOKENS appears in the title
# REJECT if any token from REJECT_TOKENS appears in the title (and not a stronger FLORAL match)
# REJECT obvious non-paintings: drawings, sketches, watercolours,
#   ceramics, photographs, manuscripts, etchings, lithographs
```

The reject list should explicitly include every subject family that is NOT the LoRA target. For Renoir flowers we rejected `portrait`, `bather`, `landscape`, `pheasant`, `onion`, `peach`, `pomegranate`, etc. (subjects that turn up in keyword searches because Renoir also painted them).

**Resolution filter:** 768 px short side. Below that, SDXL training will bucket the image into a smaller bucket and the data is mostly wasted.

**Subject scope decision (critical, decide at Phase A):**

- **Strict:** floral subject is dominant. Rejects scenes-with-flowers like garden landscapes or figures with bouquets. Produces a tighter LoRA with a narrower vocabulary.
- **Broad:** any composition that prominently features the target subject. Includes scenes-with-flowers, figures, gardens. Produces a more flexible LoRA at the cost of subject specificity.

For Renoir we ran a Phase A (strict) and then a Phase A.6 (broad expansion) on top. Decision should be made up front next time. **Recommendation:** start broad. The training playbook explains how to filter to the strict subset by `subject` field if the broad LoRA over-generalises.

### Phase A.5 — Vision audit + crop

A web-scraped dataset always contains: frames, mats, museum-conservation strips, auction-catalogue white margins, watermarks, low-light gallery photos, false positives (photos of the museum building, modern bouquets, paintings by other artists with the LoRA artist's name in the upload metadata). All of those hurt training. None of them are detectable from the title.

**Use a vision model.** Gemini 2.5 Flash with a strict-JSON prompt is the right tool: cheap, fast, structured output, accurate at detecting frames and borders. Cost per image is in the cent range. See [gemini_review.py](../../datasets/renoir-flowers/gemini_review.py) for the prompt template.

The audit asks per image:
- `is_painting` (rejects photographs, ceramics, sculpture in museum grounds)
- `by_<artist>` (rejects work by other artists in the same museum / category)
- `flowers_visible` (or whatever the subject criterion is)
- `has_physical_frame` / `has_white_or_paper_border` / `has_watermark`
- `painting_bbox_pct` — the smallest rectangle containing only the painted canvas

**Crop strategy: three passes.**

1. **Pass 1** — apply the Gemini bbox with a small outward pad (1 % for frame-fills-frame; 2 % for catalogue-style small-painting-on-big-paper). This handles ~80 % of cases cleanly.
2. **Pass 2** — re-run Gemini on the post-crop result with a tighter prompt that explicitly asks for the smallest bbox containing only painted canvas. This catches the cases where pass 1 left a 5 to 10 % decorative frame sliver.
3. **Manual fallback** — for the 5 to 10 % where Gemini returns a degenerate `(0, 0, 1, 1)` bbox (it sees a frame but cannot box it), or where Gemini says "clean" but the human eye sees a residual: visually inspect, write a manual bbox in `manual_crops.json`, apply.

Upscale with PIL LANCZOS to 768 px short side when crop drops below. Cap upscale at 2x; beyond that the synthetic detail is too obvious. Back up originals to `raw_orig/` before overwriting.

### Phase A.7 / A.8 — Human-in-the-loop refinement

After the automated passes, open a static-HTML mosaic gallery of every image and let the human curator drive the last 5 to 10 %.

[build_gallery.py](../../datasets/renoir-flowers/build_gallery.py) emits a self-contained `gallery.html`:

- CSS-column-count masonry, no library, opens directly via `file://`.
- Click a card to flip and read the training caption.
- Per-card buttons: `×` mark for removal, `⚐` flag for review, `✂` open the manual cropper modal.
- The manual cropper modal supports:
  - Drag the crop rectangle by any of 8 handles or the middle.
  - 90 CW / 90 CCW rotation buttons (the rotated image is rendered into an HTML canvas and used as the cropper source; bbox resets on rotation since the coordinate frame changes).
  - Live readout of cropped pixel dimensions at native resolution.
  - Reset / clear-saved / save / cancel.
- All decisions persist in `localStorage`. Flags and crop bboxes are exportable as a single `gallery-flags.json` via the toolbar `Export flags + crops` button.
- Filter chips at the top let the curator narrow the view to one category at a time (`My: remove`, `My: review frame`, `My: cropped`, plus the automated flags).
- Keyboard shortcuts while hovering a card: `R` toggle remove, `F` toggle review, `C` open cropper.

The server-side applier [apply_browser_crops.py](../../datasets/renoir-flowers/apply_browser_crops.py) reads the exported JSON, rotates each flagged image (PIL clockwise rotation with `expand=True`), then applies the crop bbox in the rotated coordinate frame, upscales if needed, and writes an audit record per file.

**Why the browser pass matters:** in our Renoir build, 21 of the 102 first-pass-cleaned images still had a residual that Luca caught but Gemini's first prompt missed. Sitting with a human at a real screen catches things prompts will not. The browser tool keeps the curator's attention on the image, not on terminal output.

### Phase B — Caption

**Trigger word.**

- 3 to 4 lowercase letters.
- Orthogonal to real English words. The SDXL text encoder must not already have a strong association for it.
- Distinct across all your LoRAs (`tcole`, `cds`, `rfl`, etc.) so you can stack two LoRAs in the same prompt without aliasing.
- First token in every caption. Always.

**Caption template** (Renoir example, generalise the slots):

```
<trigger>, <subject>, <composition>, <palette / light>, <brushwork / surface>, <fixed style suffix>
```

For Renoir: `rfl, a porcelain vase of roses, centered still life on a table, soft natural daylight blush pinks and ivory against a slate-grey background, visible brushstrokes layered impasto petals, oil painting, impressionist`.

The four-slot version (without brushwork) produced 25 to 27 word captions, below the 30-60 word brief window. The five-slot version landed every caption inside 33 to 39 words. **For SDXL style LoRAs, target 30 to 50 words per caption.** Below 25 is too sparse; above 60 the model learns the captions instead of the style.

**Two paths for caption generation:**

1. **Rule-based, deterministic, offline** — what we used for Renoir. A `captions.py` script parses the title and filename for subject keywords, picks a composition from aspect ratio and subject family, samples palette and brushwork from a small vocabulary biased by inferred subject. Re-runs are byte-identical. Cheap, debuggable, the right starting point.
2. **Vision-language pass** — use Gemini 2.5 Pro or Claude with vision to caption from the pixels. Higher accuracy on the 20 to 30 % of titles that are vague ("Bouquet de fleurs"). Slower, costlier, less debuggable. **Run as a second pass on top of rule-based** if the first-training-pass LoRA shows specific failure modes (e.g. it cannot distinguish anemones from roses).

**Caption suffix discipline:** the last 2 to 3 words of every caption should be the same exact tokens. For Renoir, `oil painting, impressionist`. The text encoder will learn this as a "style invocation" attached to the trigger. At inference time, the same suffix on the user prompt activates the LoRA's style strongly.

**Do not shuffle captions** at training time. Caption-tag dropout 0. The structure (trigger first, suffix last) is what we want the model to learn.

### Phase C — Hand-off package

Deliverable for CivitAI training is a single ZIP:

```
renoir-flowers-civitai.zip
  filename1.jpg
  filename1.txt    # caption for filename1
  filename2.jpg
  filename2.txt
  ...
```

[package_for_civitai.py](../../datasets/renoir-flowers/package_for_civitai.py) does this end to end:

- Cross-checks that every `raw/*.jpg` has a row in `captions.txt`.
- Pulls 5 validation hold-out images into `validation/` (paths are listed in the training playbook).
- Writes `<basename>.txt` next to each `<basename>.jpg`.
- Zips with `ZIP_STORED` (no compression — JPEGs do not compress further and CivitAI's upload is faster with stored).

**Validation hold-out: 5 images, picked for visual diversity.** The hold-out is never in training. At every epoch checkpoint, prompt-by-prompt rerender the 5 validation paintings and grade subjectively. If the LoRA cannot reproduce the canonical painting at strong scale, it has not learned the style. If it cannot generalise to the off-distribution validation case (we used a potted geraniums-in-a-copper-basin for Renoir), it has overfit.

Pick at least one canonical case, at least one off-distribution case, and at least one minority-subject case (a subject family with <= 5 training images).

## Common failure modes and their fix

| Failure | Cause | Fix |
|---|---|---|
| LoRA paints decorative frames at high scale | Training data contains paintings still showing physical frames | Re-crop more aggressively. See the EDGE_CROP=0 + Renoir border probe in [lora-training.md](lora-training.md) section 7. |
| Auction-catalogue colour cast | Sotheby's / Christie's scans dominate the set | Down-weight catalogue-source images at training time, or split into a separate concept group. The Renoir set has 46 catalogue images of 118; we track them via `collection` in `metadata.csv`. |
| LoRA hallucinates subjects on neutral prompts | Captions over-specified or trigger word too generic | Tighten captions, change trigger word to a more orthogonal string. |
| LoRA disappears on cross-domain prompts | Subject distance: LoRA scale calibrated for in-distribution, too weak for off-distribution | Scale UP, not down. See the subject-distance note in [lora-training.md](lora-training.md) section 6. This is the most counter-intuitive fix in the playbook. |
| Training mode collapse to one composition | Composition vocabulary in captions too repetitive | Add more composition phrases. Renoir's `composition_for()` function has 11 distinct phrasings; Cole's has 5 and shows mode collapse on long generations. |
| Text encoder ate the captions | Trained text encoder LR > 0 | Always train UNet-only. SDXL Kohya LoRAs intended for stack-with-other-LoRAs inference must NOT update the text encoder. |

## What we changed mid-project and why

For future-Luca and future-Claude reading this:

1. **Subject scope expanded mid-build (Phase A.6).** Started strict-floral, then broadened to "scenes with flowers". Result: 96 still-life + 22 scenes-with-flowers in 118 total. Cost a Phase A.6 sourcing pass; gained compositional variety the artist wanted.
2. **Caption template grew from 4 slots to 5.** Brushwork / surface slot was added to lift word count into the 30-60 window. Worth doing for any style LoRA where the surface (impasto, broken colour, scumble) is part of the signal.
3. **Browser flag UI added.** Originally I planned to do everything from the terminal; the user flagged 21 cases the automated audit missed, which justified adding the gallery flagging UI and then the manual cropper. **The lesson: build the human-in-the-loop UI early, even for "automated" pipelines.** Catching the last 10 % of artefacts requires eyes on the dataset.
4. **Rotation in the cropper added late.** Some scans (catalogues mostly) ship sideways. The cropper now exposes 90 CW / 90 CCW buttons that rotate the canvas-rendered image inside the cropper; the bbox resets on rotation; rotation is persisted in `CROPS[fn].rotation` and applied server-side with `PIL.Image.rotate(-deg_cw, expand=True)`. Bake this into the v1 cropper next time.
5. **Gemini false-positives on canvas edge texture.** A few "WATERMARK" flags turned out to be the canvas grain near the painting edge. Always include a visual sanity-check pass on a sample of flagged images before mass-cropping. The pass-2 prompt should explicitly say "do not treat canvas-edge texture or signature as a watermark".

## File inventory pattern

For a new dataset under `datasets/<name>/`, mirror this layout (gitignore everything except `metadata.csv`, `captions.txt`, `captions.json`, the scripts, and the local `.gitignore`):

```
datasets/<name>/
  .gitignore                  local rules
  raw/                        keepers, JPEG q=95
  raw_orig/                   backups of pre-crop versions
  rejected/<reason>/          audit, kept on disk

  source_commons.py           Phase A: Commons sourcing
  source_commons_expand.py    Phase A.6 expansion (if scope broadens)
  dedup.py                    perceptual-hash dedup
  finalize_metadata.py        build metadata.csv from extmetadata
  update_metadata_post_process.py   merge processing flags into metadata.csv

  gemini_review.py            Phase A.5 vision audit (frame/bg/watermark)
  gemini_review_pass2.py      tighter prompt re-inspection
  gemini_review_userflags.py  Phase A.7 re-inspect user-flagged cases
  gemini_triage_new.py        Phase A.6 triage (is_painting, by_artist, target_visible)
  apply_crops.py              Phase A.5 pass-1 crop driver
  apply_crops_pass2.py        Phase A.5 pass-2 crop driver
  apply_manual_crops.py       manual bboxes from manual_crops.json
  apply_manual_crops_user.py  Phase A.7 micro-crops
  manual_crops.json           hand-written bboxes for Gemini failures
  manual_crops_user.json      user-flagged manual bboxes

  captions.py                 Phase B caption generator
  build_gallery.py            Phase A.7 + A.8 browser gallery + flagger + cropper
  apply_browser_crops.py      Phase A.8 server-side applier for browser crops
  package_for_civitai.py      Phase C ZIP packager

  metadata.csv                tracked, the source of truth
  captions.txt                tracked, one line per image: filename<TAB>caption
  captions.json               tracked, structured per-image caption fields
  gallery.html                generated, gitignored
  review.json                 Gemini Phase-A.5 audit, gitignored
  processed.json              full crop audit trail, gitignored
  user-flags-YYYY-MM-DD.json  archived browser exports
```

The script names are stable on purpose. When you start the next LoRA, copy this folder structure and replace the sourcing keywords; everything downstream just works.


---
*Did you reproduce this and observe something different? Counter-findings welcome. See [CONTRIBUTING.md](../../CONTRIBUTING.md) shape 4 and the [finding issue template](../../.github/ISSUE_TEMPLATE/finding.md).*
