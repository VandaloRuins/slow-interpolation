# Dataset hygiene utility (placeholder)

**Status: placeholder, to be expanded.**

The Renoir-dataset workstream produced a reusable VLM-driven dataset-cleanup pipeline (Gemini 2.5 Flash inspection -> first-pass crop -> tighter pass-2 -> manual fallback). This document is the future home for the generalised recipe so the next LoRA workstream does not re-derive it.

## What exists today

Worked example in [datasets/renoir-flowers/](../../datasets/renoir-flowers/), driven by these scripts:

- `gemini_review.py` — first-pass VLM audit. Inspects each image at 1024 px, returns strict JSON: `has_physical_frame`, `has_white_or_paper_border`, `has_watermark`, `painting_bbox_pct`, `needs_crop`, `notes`. Idempotent + resumable.
- `apply_crops.py` — first-pass crop with conservative outward padding (1-2 %), LANCZOS upscale capped at 2x if cropped short side falls below the SDXL bucket floor (768 px). Originals preserved in `raw_orig/`.
- `gemini_review_pass2.py` — re-inspects previously-framed images with a tighter prompt.
- `apply_crops_pass2.py` — applies pass-2 bboxes where Gemini returned valid bbox (degenerate 1x1 responses skipped for manual).
- `manual_crops.json` + `apply_manual_crops.py` — manual bboxes for the cases Gemini could not bbox cleanly.
- `update_metadata_post_process.py` — refreshes `metadata.csv` with `saved_width/height, processed, processed_ops, flags_frame, flags_white_bg, flags_watermark, review_notes`.

Numbers from the Renoir pass: 26 of 102 images needed cropping. 4 required manual bboxes. 1 upscale. Resolution floor preserved (768 px short side, all in SDXL bucket).

## What the generalisation needs

When the Renoir LoRA training round closes, the Renoir chat (or its successor) should expand this document into:

1. **The audit JSON schema**, fully written out (currently inferred from `gemini_review.py`).
2. **The VLM prompt template**, abstracted from the Renoir-specific subject keywords.
3. **The crop-pipeline state machine**, written generically (first-pass -> pass-2 -> manual fallback decision criteria).
4. **The "what counts as needs-crop"** rules, lifted from the Renoir-specific framing rules.
5. **A re-run recipe** for any new dataset (parallels the Renoir re-run gate at the bottom of [docs/renoir-dataset-progress.md](../planning/workstreams/renoir-dataset/progress.md)).
6. **Cost notes** — Gemini Flash 2.5 calls per image, total cost for a 100-image dataset, time budget.

## Cross-references

Pulled into this document when written:

- [docs/findings/lora-pipeline.md](lora-pipeline.md) (will exist post-Renoir-training): the generic LoRA recipe, of which dataset-hygiene is the cleanup stage.
- [docs/findings/lora-training.md](lora-training.md): the Renoir-specific worked example.
- [docs/findings/border-crop.md](border-crop.md): why the SDXL bucket floor (768 px) is the hard lower bound for the upscale-on-cleanup logic.

## Why now

Capturing this as a placeholder now (2026-05-17) so the pattern is named and the Renoir chat knows where to land its export when training closes. The actual content fills in later.


---
*Did you reproduce this and observe something different? Counter-findings welcome. See [CONTRIBUTING.md](../../CONTRIBUTING.md) shape 4 and the [finding issue template](../../.github/ISSUE_TEMPLATE/finding.md).*
