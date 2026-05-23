# Renoir flowers dataset — progress

Status log for the Renoir floral LoRA dataset + training-playbook workstream. Append-only; latest entry on top.

Owner: this chat (parallel to parent).
Scope: `datasets/renoir-flowers/*` (metadata.csv tracked, raw images gitignored), `docs/findings/lora-training.md`, this file, plus a few sibling docs noted below.
Out of scope: `docs/planning/progress.md`, `src/*`, `docs/pipeline.md`, `docs/inventory.md`, `docs/outputs.md`, `docs/dependencies.md`, `vendor/*`, `cloud/*`.

Reference: parent plan at `docs/planning/progress.md` "Phase 3-Renoir-dataset" row. Captioning + LoRA-usage template at [legacy/after-cole/LORA-USAGE.md](../../../../legacy/after-cole/LORA-USAGE.md). Border caveat for the Renoir LoRA probe at [docs/findings/border-crop.md](../../../findings/border-crop.md).

> ## PARENT-CHAT NOTICE: LoRA cluster consolidation + dataset-hygiene merge approved (2026-05-18)
>
> Luca approved two findings-consolidation jobs on 2026-05-18 after the docs-curator pass. Both land in this workstream's writes. Execute on next session.
>
> ### Job 1: LoRA cluster consolidation (high confidence, biggest payoff)
>
> Today's state: four overlapping LoRA-shaped findings, ~927 lines.
> - `findings/lora-training.md` (310 lines, Renoir-specific CivitAI recipe, archival).
> - `findings/lora-training-deep-dive.md` (397 lines, theory + objectives + hyperparameters + tools beyond CivitAI). Authored by modal-trainer chat originally.
> - `findings/kohya-vs-ai-toolkit-renoir.md` (113 lines, engine comparison with measured numbers). Authored by modal-trainer chat.
> - `findings/style-vs-subject-lora.md` (107 lines, dataset composition regime). Authored by Compositing chat.
>
> Target shape (2 files):
> - `findings/lora-pipeline.md` (NEW, generic, subject-agnostic). Absorbs the deep-dive (verbatim or near-verbatim), the style-vs-subject regime, and the engine-comparison verdict (just the verdict, the per-row numbers stay in `kohya-vs-ai-toolkit-renoir.md`). Cross-links to `manual/train-lora-on-modal.md` for the operational protocol.
> - `findings/lora-training.md` (refined; the Renoir-specific worked example). Strip overlap with the deep-dive; keep prompt vocabulary, validation grid, Renoir-specific observed failure modes. Keep filename to avoid 26-file ref-fix-up across the tree.
>
> Optional rename (your judgement): `findings/lora-training.md` -> `findings/lora-training-renoir.md`. **Cost: 26 files reference the old name across the tree** (workstream docs, manual pages, AGENTS.md, CLAUDE.md, etc.). If you take the rename, do it as part of a single PR that also updates all references. If you skip the rename, the existing banner at the top of `lora-training.md` ("CANONICAL TRAINING PATH UPDATED 2026-05-18") already disambiguates. Recommendation: skip the rename, do the merge.
>
> Cross-workstream coordination needed:
> - **modal-trainer chat** authored two of the four source files. The engine-comparison verdict in `lora-pipeline.md` should match their canonical position; their progress.md has been notified to review. Coordinate by posting a draft of the relevant `lora-pipeline.md` section in your progress.md and ping them.
> - **Compositing chat** authored `style-vs-subject-lora.md`. Less coordination needed; the content is self-contained and can move into `lora-pipeline.md` as a section.
>
> Sequencing:
> 1. Draft section-level boundaries in your progress.md (which section of which source file lands in which target file). Parent chat reviews.
> 2. Author `findings/lora-pipeline.md` with the consolidated content.
> 3. Refine `findings/lora-training.md` (strip overlap, keep Renoir specifics).
> 4. Fix the 5 forward-refs to `lora-pipeline.md` across the tree once the file exists (currently broken-link baseline).
> 5. Notify parent chat for the "Findings curation status" tracker update in `docs/planning/progress.md`.
>
> ### Job 2: dataset-hygiene -> dataset-practice merge (high confidence, smaller)
>
> Today's state:
> - `findings/dataset-hygiene.md` (45 lines, placeholder for the Gemini-driven multi-pass crop pipeline; defers content).
> - `findings/dataset-practice.md` (229 lines, real recipe).
>
> Target shape (1 file):
> - `findings/dataset-practice.md` gains a new "Gemini audit + multi-pass crop" subsection lifted from the placeholder + drawn from the actual scripts under `datasets/renoir-flowers/`. Delete the placeholder.
>
> Sequencing:
> 1. Read `dataset-hygiene.md` (it's a 45-line placeholder; the content is forward-promise).
> 2. Write a "Gemini audit + multi-pass crop" section in `dataset-practice.md` with the actual recipe (script names, JSON schema, multi-pass strategy, manual fallback).
> 3. Delete `findings/dataset-hygiene.md`.
> 4. Fix any inbound refs to `dataset-hygiene.md` (there are a few in `docs/README.md` and `docs/planning/progress.md`; parent chat handles those).
> 5. Notify parent chat for the tracker update.
>
> Both jobs are unblocked. Both Renoir dataset curation (Phase A+B+C+A.5) and Renoir LoRA training are done. The Modal trainer cold-run validated the canonical path. All four LoRA source findings are stable. Do these consolidations on your next session before any new dataset-shaped work.

> ## PARENT-CHAT NOTICE: dataset-curation.md scope broadened (2026-05-18)
>
> The parent chat edited the intro of [`docs/manual/dataset-curation.md`](../../../manual/dataset-curation.md) to explicitly cover any image collection (reference sets, validation hold-outs, synthetic-data corpora) and not just LoRA training sets. Trigger: the Compositing chat built a parallel Soutine reference-set system (`datasets/soutine-figures/references/MANIFEST.md`) instead of running the 10 references through the gallery protocol; the doc's narrow framing on "workshop student / LoRA training set" was the discoverability failure.
>
> Changes the parent made to your manual page:
>
> - Opening reframed: "the ONLY documented dataset-building protocol in this repo", covering training sets, reference sets, validation hold-outs, synthetic corpora.
> - Image-count assumption broadened: "5 to 200 source images, depending on use".
> - Added the Soutine dataset as a second worked example next to Renoir.
> - Removed the "workshop student" narrowing; the user role is now described as variable (student in workshop context, operator in research context).
>
> Phase content (Phase 1 to 5) unchanged. Your protocol design holds. The edit is intro-only.
>
> If you want to revise this on your next session (smooth the seam, add more examples of non-training uses, etc.), feel free; the parent edit is intentionally minimal. Flag if you object to the scope expansion.

> ## CROSS-WORKSTREAM VISIBILITY (from Modal chat, 2026-05-18)
>
> The Modal workstream shipped its release-day Tier 1 + Tier 2 followup plan on 2026-05-18 and is now blocked on Renoir LoRA arrival for its Tier 3 cluster. Three items concern this workstream:
>
> 1. **Modal T1#2 (Renoir flower-field border probe).** Queued and waiting on the trained Renoir LoRA. When the CivitAI training finishes and the `.safetensors` lands in `models/loras/`, Modal will run a flower-field-subject probe (NOT a vase-subject probe) to validate the EDGE_CROP=0 default for the Renoir LoRA. The Renoir release configs at `examples/configs/renoir/*.yaml` will inherit the verdict.
> 2. **1536x896 source-resolution path supersedes 1344x768.** Modal landed `findings/upscale-source-resolution.md` on 2026-05-18: on A100-80GB, 1536x896 native renders cleanly and upscales to 1920x1080 with less ratio than the previous plan. Renoir release inherits this resolution path pending a Renoir-LoRA-specific re-probe alongside T1#2. The four scaffolded configs at `examples/configs/renoir/*.yaml` may need their `resolution` block updated to 1536x896 after T1#2 confirms.
> 3. **Cost envelope: 0.07 USD per 60s render on L40S.** Renoir release renders can plan against ~0.10 to 0.50 USD per render, not the original ~1 to 5 USD estimate. Multi-variant or batch renders are now cheap enough to be exploratory.
>
> No action required from this workstream until the LoRA training closes. When it does, the Modal chat is ready to run T1#2 in parallel with the LoRA-pipeline export.

> ## D2 MIGRATION DUE NEXT SESSION + LoRA docs target structure ask
>
> The docs tree was reorganised on 2026-05-17 (Phase D1 + D2 prep). The full
> strategy is at [`../planning/docs-strategy.md`](../../docs-strategy.md).
> Your D2 self-migration playbook is in the same file under "D2 firing
> playbook". Execute it next time you resume.
>
> **What to do, in order, before the next dataset / curation push:**
>
> 1. Read [`../planning/docs-strategy.md`](../../docs-strategy.md) "D2 firing playbook" section.
> 2. `mkdir -p docs/planning/workstreams/renoir-dataset/`
> 3. Move and rename (this workstream owns more docs than the others):
>    - `docs/renoir-dataset-progress.md` -> `docs/planning/workstreams/renoir-dataset/progress.md`
>    - `docs/findings/dataset-practice.md` -> **stays at `docs/findings/`**. Findings are tier-3 and do not move with the workstream.
>    - `docs/findings/dataset-hygiene.md` -> **stays at `docs/findings/`** (placeholder; consolidation into `dataset-practice.md` is queued, see below).
>    - `docs/findings/lora-training.md` -> **stays at `docs/findings/`** (will be renamed at the LoRA-pipeline-export milestone, see below).
>    - `docs/findings/inpainting-options.md` -> **stays at `docs/findings/`**.
>    - `docs/plans/inpaint-implementation.md` -> `docs/planning/workstreams/renoir-dataset/inpaint-plan.md`. The `docs/plans/` folder can be removed once empty.
>    - `docs/gallery-manual-notes.md` -> if you judge it stable for external readers, promote to `docs/manual/gallery.md` (and update its content for tutorial framing). If still working-notes shape, move to `docs/planning/workstreams/renoir-dataset/gallery-manual-notes.md` for now and promote at the next stable moment.
> 4. Fix relative links inside all moved files (see playbook).
> 5. Run `python tools/check_doc_links.py` from repo root. Your moves should REDUCE the broken-link count.
> 6. Note the migration as a new top entry in `progress.md` ("Append-only; latest entry on top" pattern). One line: "2026-05-XX: Migrated to `docs/planning/workstreams/renoir-dataset/` per D2 protocol."
> 7. Continue dataset work from the new path.
>
> ## LoRA docs target structure (request from parent chat)
>
> Three current findings docs cover overlapping ground:
> - [`docs/findings/lora-training.md`](../../../findings/lora-training.md) (Renoir-specific worked example)
> - [`docs/findings/dataset-practice.md`](../../../findings/dataset-practice.md) (generic recipe, with Renoir numbers)
> - [`docs/findings/dataset-hygiene.md`](../../../findings/dataset-hygiene.md) (placeholder for the Gemini-crop pipeline)
>
> When training closes and Luca asks you to "export a reusable LoRA pipeline strategy", the target structure for the export is:
> - `docs/findings/lora-pipeline.md` (NEW, subject-agnostic generic recipe): source-priority ladder, subject-filter convention, dedup, captioning template, Gemini-audit + multi-pass crop, CivitAI training settings, validation hold-out, expected-outcome grading. Cross-links into the Renoir worked example for concrete numbers.
> - `docs/findings/lora-training-renoir.md` (rename of the current `lora-training.md`): the worked example. Stripped of generic content; kept as concrete Renoir-specific notes.
> - `docs/findings/dataset-practice.md`: absorbs the current `dataset-hygiene.md`. The Gemini-audit pipeline becomes a section of `dataset-practice.md`, not its own file.
>
> **Propose section-level boundaries** between these three files (which section of which current doc lands in which target file) and write the proposal into your migrated `progress.md` under a "## LoRA docs target structure" heading. Parent chat will review and either approve or counter-propose. This proposal needs to land BEFORE the LoRA-pipeline export, not after; the export then writes into the target structure directly.
>
> Do not move or merge the files yourself yet. Propose first.
>
> ## Context-handoff doc when workstream eventually closes
>
> Per Luca (2026-05-17): "we can close it when the dataset is curated and ready, but will need it to create extensive documentation so we do not lose context". Before this workstream formally closes, produce a comprehensive context-handoff document at `docs/planning/workstreams/renoir-dataset/handoff.md` covering: dataset shape, curation decisions (and rejected alternatives), gotchas encountered, the Gemini-crop pipeline as a reusable utility, where future Renoir-related questions get answered. Treat the handoff as the file a totally fresh agent would need if they had to pick up the Renoir workstream from scratch.

## 2026-05-18, brushwork tuning loop (v1 → v2), paused pending inpaint workstream design

Two field renders on `flower_field_60s*.yaml` against the CivitAI baseline. Visual feedback from Luca:

| Render | Config | Verdict |
|---|---|---|
| v1 | `flower_field_60s.yaml`, epoch 1, scale 0.85 | "Impressionist read small, brushwork too thin and delicate, especially the grass in between patches" |
| v2 | `flower_field_60s_v2.yaml`, epoch 5, scale 1.0, impasto-leading prompts, extended negative | "Blurry, lacking brushstroke details, more abstract (appreciated) but does not read as Renoir; composition is interesting but we lost the texture of the wide brushstrokes" |

Read: the tuning space is non-monotonic. v1 was too photographic, v2 overshot into Lightning-collapse (4-step + high LoRA scale + push-toward-abstraction prompts melted detail without recovering brushstroke texture).

Hypotheses to test on the next pass (NOT now, pending inpaint design):

1. **Epoch 5 at scale 0.85, no abstraction-push prompts.** The validation-grid mid-point at the validation-grid scale. Should sit between v1 and v2 on the painterly axis.
2. **Epoch 10 at scale 0.65 to 0.70.** Drop LoRA strength below the photographic-collapse threshold but keep the strong-Renoir surface. Closer to the F2 keyframe-grid read (where epoch 10 was "presentable but saturated"). Signatures expected.
3. **Add a Phase A.5 step count.** The temporal smoother may also be melting brushstroke micro-detail. Worth a controlled test (same config, smoother off) before more LoRA-scale searching.
4. **Re-evaluate after the inpaint workstream ships and the Modal-trainer retrain produces a less-overfit LoRA** (the auction-catalogue cast is the underlying problem; tuning around it is search in the wrong space).

Loop paused. Inpaint design doc is the next active item per Luca's redirect.

## 2026-05-18, first 60s flower-field clip rendered on Modal (epoch 1)

Production-scale validation of the Renoir LoRA, executed by the parent chat. Full Phase A → A.5 → C → D pipeline against `examples/configs/renoir/flower_field_60s.yaml` (new): epoch 1 LoRA at scale 0.85, 1344×768, A/B/C/A drift across wildflower meadow palettes (late-spring afternoon → poppy crimson → cornflower morning → return).

Modal L40S run. Wall: 84.6s (A 39s, A.5 16s, C+D 27s). Cost: $0.046. Output: `outputs/renoir_wildflower_field.mp4` (7.5 MB, 24 fps, libx264 q5). Manifest: `outputs/renoir_wildflower_field.manifest.json`.

Negative prompt extended to suppress `signature, watermark, text` at inference (cheap mitigation while inpaint Phase 1 is pending). Worth confirming visually whether the field renders escape the corner-signature artefact at epoch 1.

This closes Queued Next item (1) from the previous entry. Validates that the CivitAI baseline holds at full 60s pipeline scale on the actual target subject. If the visual read holds, the Renoir release content path is unblocked even before Modal-trainer ships; the Modal-trainer retrain becomes a "polish + signature-suppression" pass, not a "rescue" pass.

Next likely move depending on visual read: render 2-3 sibling configs (mixed palettes / portrait orientation) to build the release-cut variant set, or pivot to Option B (Stability Erase batch) if signatures still leak through.

## 2026-05-18, CivitAI baseline trained, validation grid shipped, Modal-trainer chat dispatched

End-to-end first-cut milestone closed. Three things happened in sequence.

**1. CivitAI training of the Renoir LoRA closed.** Submitted from civitai.red (yellow Buzz, the .red sister site of .com) via Playwright after discovering that civitai.com only accepts Green Buzz post-payment-processor-split. Cost: 500 yellow Buzz (~$0.50 equivalent), ~19 min wall (20:47 to 21:06 on 2026-05-17), AI Toolkit engine (Civitai's new default, not Kohya). Hyperparameters: Network Dim 32, Alpha 32, UNet LR 5e-4, Adafactor, 2 repeats. Ten epoch checkpoints downloaded; three keepers at `models/loras/Renoir_Flowers_epoch_{1,5,10}.safetensors` (228 MB each). All three uploaded to Modal volume `slow-interp-loras` via `cloud/upload_weights.py`. Filenames match the `lora-training.md` §4 convention so `examples/configs/renoir/*.yaml` load them without edits.

Implementation gotcha during submission: after dataset Reset on civitai.com, the upload dropzone is hidden until the Acknowledgement checkbox is ticked. Document this in `docs/manual/gallery.md` (not in the renoir-flowers gallery; in the broader Civitai-facing manual page, which doesn't exist yet). Lower-priority finding.

**2. Validation grid shipped.** New file `cloud/validation_renoir.py` (Modal app, mirrors `cloud/app.py` patterns) renders 11 prompts × 3 epoch checkpoints = 33 keyframes at 1216×832 (SDXL native 3:2 bucket), seed 42, lora_scale 0.85. Three Modal L40S invocations, total ~61 s GPU, ~$0.06 total cost. Outputs land at `outputs/validation/renoir-epoch-{1,5,10}/`. Browser visualiser at `outputs/validation/index.html` (filter chips, lightbox, recommended-epoch badges). Markdown grid at [validation-grid.md](validation-grid.md).

**Headline read:**
- Epoch 10 is the canonical "strong Renoir" checkpoint for vases and bouquets. The hold-out renders (V1 to V5) are convincing Renoir pastiche.
- **Epoch 1 is the better default for flower fields**, counter to the docs' prediction. Epoch 10 has over-fit the auction-catalogue "photo of a painting" surface, which suppresses painterly atmosphere on outdoor subjects. Epoch 1 preserves the impressionist atmosphere that fields need.
- Epoch 5 sits between, slightly closer to epoch 10 on vases.
- Every epoch-10 render has a baked-in signature in the bottom-right corner. Predicted from the 48 of 105 training images being auction-catalogue scans with visible Renoir signatures. Solvable via inpainting (see inpaint-plan.md v2) or inference-time negative prompts.

Practical recommendation now in [validation-grid.md](validation-grid.md):

| Render intent | Checkpoint | Scale |
|---|---|---|
| Vase / bouquet still life | epoch 10 | 0.75 to 0.85 |
| Flower field, garden, outdoor | **epoch 1** | 0.85 to 1.0 |
| Mixed scene with bouquet element | epoch 5 | 0.85 |

The four scaffolded configs at `examples/configs/renoir/*.yaml` (roses_vase, anemones, mixed_bouquet, peony_closeup) target epoch 10 by default; a new `flower_field_60s.yaml` should be added pointing at epoch 1.

**3. inpaint-plan.md rewritten as v2.** The original Phase 1 (fal.ai FLUX [pro] Fill for highlighting non-flower subjects) is now Phase 2. New Phase 1: **Stability AI Erase API** (purpose-built object removal, ~$0.03 per image, no prompt needed). Researched alternatives. Gemini Nano Banana is OUT for the signature-erase use case because it does not support pixel masks (only semantic natural-language masking) and tight corner edits need pixel precision. Sources cited in the doc. New Phase 3: **Modal SDXL Inpaint + the trained domain LoRA** as the canonical "no third-party API key" workshop-student path. Gated on the Modal-trainer cold-run.

**4. Modal-trainer parallel chat dispatched.** Kickoff prompt v2 shipped to the parallel chat (workstream log private during v0.1). The CivitAI baseline + validation grid are now the cold-run target. When the Modal trainer ships and validates, the workshop story closes: dataset (local gallery) → train (Modal) → inpaint (Modal) → render (Modal). No CivitAI, no fal.ai required at any step. CivitAI and fal.ai become "mentioned alternatives", not workshop dependencies.

### What's queued next (in priority order)

1. **Production-scale clip render.** Run a real 60s flower-field clip on the existing CivitAI epoch-1 LoRA at scale 0.85, against a new `examples/configs/renoir/flower_field_60s.yaml`. Validates the full Phase A → A.5 → C → D pipeline (not just keyframes) on the actual target subject. Cost: ~$0.07 on Modal L40S. This unblocks "the Renoir LoRA is good enough for the objkt labs release" or "we need the Modal-trainer or landscape augmentation first".
2. **Wait for Modal-trainer cold-run.** Independent of (1). Parent chat does not act until the modal-trainer chat reports back.
3. **Inpaint Phase 1 (Stability Erase batch).** Optional; defer if the Modal trainer's signature-suppression stretch goal works.
4. **Landscape augmentation re-sourcing.** Optional; defer to a Phase 2 LoRA retrain only if epoch-1 field renders at full clip scale underwhelm.

### Coordination requests

- Parent chat: please integrate the CivitAI baseline milestone into `docs/planning/progress.md` "Status at a glance" + "Decisions log". The Phase 3-Renoir-dataset row currently shows "Done (Phase A + B + C + A.5 cleanup all closed)" but the trained LoRA + validation grid are not yet captured there. Suggested decisions-log entries: "Renoir LoRA trained on civitai.red 2026-05-17, 500 yellow Buzz, AI Toolkit engine, baseline saved to slow-interp-loras volume", and "Yellow Buzz lives on civitai.red, Green Buzz on civitai.com — payment-processor split, document this for workshop students".
- Modal-trainer chat: cold-run criteria are in the kickoff. Validation grid (this workstream's `validation-grid.md`) is the comparison anchor.

## 2026-05-17, workshop protocol docs shipped (agent-facing rewrite)

Promoted the dataset-curation workflow to two manual pages. **Important framing**: per Luca's clarification, these docs are written for the AI agent that helps a workshop student, not for the student directly. The agent reads the protocol, executes Phases 1, 2, 4, 5 autonomously, and hands off to the student only for Phase 3 (gallery review) and the CivitAI upload. Voice throughout is imperative-to-an-agent.

- **`docs/manual/dataset-curation.md` (NEW).** Five-phase protocol: source, audit + crop, human review (gallery), caption, hand-off. Each phase includes: bootstrap commands, what-to-edit per domain, validation gates between phases, decision trees, and a "When to stop and ask the student" section. Includes a Phase 0 bootstrap (folder + trigger + script copy), explicit failure-mode table with agent-action column, a refusal stance on synthetic-data requests, and a time budget split between agent wall time and student engagement time.
- **`docs/manual/gallery.md` (NEW, rewrite of gallery-manual-notes.md for the agent reader).** Pre-authorised by the D2 migration block. Now contains: how the agent stands the server up, a "briefing crib sheet" so the agent can answer student questions accurately, the JSON contract for `gallery-flags.json` (the file the student exports back), how to process it with `apply_browser_crops.py`, troubleshooting table indexed by symptom + likely cause + fix.
- **`docs/manual/index.md`** updated to add the two new pages to the reading order. The "Phase D3 slated" sub-list now drops `gallery.md` (shipped) and keeps `training-loras.md` (awaits LoRA-pipeline export).
- **`gallery-manual-notes.md`** (this workstream) is now marked SUPERSEDED with a redirect header. Retained as in-flight notes scratchpad until workstream close.

Coordination note for parent chat: `docs/manual/` is outside this workstream's writes list per the parent's ownership matrix. The edits were directed by Luca in-session and pre-authorised by the D2 playbook for the gallery promotion. Flagging here so the parent integrates the manual addition into [docs/README.md](../../../README.md) and the master `docs/planning/progress.md` "Status at a glance" table at its next pass.

Decision Luca confirmed before the docs landed: training data is complete for pass 1. Landscape-augmentation deferred as a pass-2 contingency. Logic captured in the "Failure modes and their fixes" table of `dataset-curation.md` ("LoRA renders well in distribution but fails on the off-distribution prompt").

## 2026-05-17, pre-compact bookmark

Chat compacted at this point. The next session resumes here. Everything below this entry is durable state worth re-reading at session start.

### Dataset state right now

- `datasets/renoir-flowers/raw/` contains **114 keeper JPEGs**. Luca completed manual cropping; the set is now free of physical frames, white auction-catalogue borders, and visible institutional watermarks (per his confirmation 2026-05-17 evening). One last visual pass recommended before training.
- `datasets/renoir-flowers/rejected/user-removed/` holds files Luca pushed out via the gallery's `×` button. Two pre-existing rejects plus four removed during this session. Files preserved on disk; can be restored via `/api/restore`.
- `gallery-state.json` has **1 stale legacy flag** (`pierre-auguste-renoir-bouquet-in-un-vaso-1878.jpg` value `"remove"` from before Phase A.11's behaviour change) and **26 saved manual crops** (24 with rotation 0, 2 with rotation 270°). Bbox+rotation; baked into JPEGs by `apply_browser_crops.py`.
- `metadata.csv` lists 118 rows; `raw/` has 114. The 4-row drift is from user removals. `build_gallery.py` cross-checks against `raw/` so the gallery is correct, but metadata + captions are stale relative to disk and should be regenerated before the CivitAI ZIP build.
- `phashes.json` cache covers all 114 files. Near-duplicate clustering at Hamming threshold 10 finds **1 remaining pair**: `pierre-auguste-renoir-anemones-15462545083.jpg` / `renoir-an-mones-22-by-29-cm.jpg`. May or may not actually be duplicates at full resolution; needs a visual check.

### What's queued (immediate next-up, in order)

1. **Final visual pass on the 114 keepers.** Walk every card; resolve the dup-pair top first.
2. **Apply any pending browser crops to disk.** `py -3.11 datasets/renoir-flowers/apply_browser_crops.py` (after exporting `gallery-flags.json` from the toolbar). Skip if `gallery-state.json` crop count matches `processed.json` `browser_crop` count.
3. **Regenerate metadata + captions to match `raw/`.**
   ```
   py -3.11 datasets/renoir-flowers/finalize_metadata.py
   py -3.11 datasets/renoir-flowers/update_metadata_post_process.py
   py -3.11 datasets/renoir-flowers/captions.py
   py -3.11 datasets/renoir-flowers/build_gallery.py
   ```
4. **Pick the 5-image validation hold-out.** Per the list in `docs/findings/lora-training.md` §2. Verify all 5 are still in `raw/`; replace any that got removed with the same role.
5. **Build the CivitAI ZIP.** `py -3.11 datasets/renoir-flowers/package_for_civitai.py`.
6. **Train on CivitAI** per `docs/findings/lora-training.md` §3. Or kohya_ss locally per `lora-training-deep-dive.md` §6 if Luca wants more control.
7. **Validate** per `lora-training-deep-dive.md` §7. 30-image grid, score, save to `docs/planning/workstreams/renoir-dataset/validation-grid.md`.
8. **Export the LoRA-pipeline recipe** per the four-file proposal below.

### What's queued for a different chat

- **Inpaint feature ship** ([inpaint-plan.md](inpaint-plan.md)). 7.5h Phase 1 (fal.ai FLUX [pro] Fill).
- **Renoir subject suite YAML configs** at `examples/configs/renoir/*.yaml`. Parent chat owns this.

### Open items awaiting parent-chat decision

- **LoRA-docs target-structure proposal** below. Awaiting approve / counter / adjust.
- **Playbook typo fix** in Coordination requests above. Cosmetic.
- **Gallery manual promotion** to `docs/manual/gallery.md`. Deferred.

### Resume sequence for next session

1. Read this progress.md at `docs/planning/workstreams/renoir-dataset/progress.md` top to bottom.
2. Read parent's `docs/planning/progress.md` "Status at a glance" + "Decisions log" + "Today's parent-chat session" header.
3. `python tools/check_doc_links.py` for a health check.
4. Pick up at whichever next-up item Luca points at.

## 2026-05-17, D2 self-migration

Migrated to `docs/planning/workstreams/renoir-dataset/` per the D2 protocol in [`../../docs-strategy.md`](../../docs-strategy.md) "D2 firing playbook".

Files moved (3):

- `docs/renoir-dataset-progress.md` → `docs/planning/workstreams/renoir-dataset/progress.md`
- `docs/plans/inpaint-implementation.md` → `docs/planning/workstreams/renoir-dataset/inpaint-plan.md` (per the migration block's rename guidance); empty `docs/plans/` directory removed
- `docs/gallery-manual-notes.md` → `docs/planning/workstreams/renoir-dataset/gallery-manual-notes.md` (kept as working-notes shape; promote to `docs/manual/gallery.md` at the next stable moment per the consolidations tracker)

Files that stayed (per migration block):

- `docs/findings/dataset-practice.md`
- `docs/findings/dataset-hygiene.md`
- `docs/findings/lora-training.md`
- `docs/findings/lora-training-deep-dive.md` (added this session before the migration was due; tier-3 findings, stays at `docs/findings/` by convention)
- `docs/findings/inpainting-options.md`

Link-fix pass executed. Patterns rewritten across the 3 moved files:

| Old (from `docs/<thing>.md`) | New (from `docs/planning/workstreams/renoir-dataset/<thing>.md`) |
|---|---|
| `../datasets/...` | `../../../../datasets/...` |
| `../legacy/...` | `../../../../legacy/...` |
| `findings/<topic>.md` | `../../../findings/<topic>.md` |
| `planning/docs-strategy.md` or `../planning/docs-strategy.md` | `../../docs-strategy.md` |
| `plans/inpaint-implementation.md` | `inpaint-plan.md` (now a sibling) |
| `gallery-manual-notes.md` (linked from progress) | `gallery-manual-notes.md` (now a sibling) |

Inbound links to my old path also fixed (per playbook step "your migration should REDUCE the broken-link count"):

- `docs/findings/dataset-practice.md`, `dataset-hygiene.md`, `lora-training.md` — `../renoir-dataset-progress.md` → `../planning/workstreams/renoir-dataset/progress.md`
- `docs/planning/progress.md` — `../renoir-dataset-progress.md` → `workstreams/renoir-dataset/progress.md`
- `docs/README.md` — `renoir-dataset-progress.md` → `planning/workstreams/renoir-dataset/progress.md`; `plans/inpaint-implementation.md` → `planning/workstreams/renoir-dataset/inpaint-plan.md`

Link-check (`python tools/check_doc_links.py`): 49 broken links total after the migration. Zero involve my workstream's authored files. The one residual broken link mentioning `renoir-dataset-progress.md` is in `docs/planning/workstreams/compositing/progress.md` (`../../../renoir-dataset-progress.md`), which is the compositing chat's doc and not mine to fix; their self-migration will catch it.

## Coordination requests

(Per playbook: "If anything in the D2 playbook is ambiguous for your specific workstream, post the question in your new progress.md.")

1. **Playbook path math typo for `findings/` references.** The D2 firing playbook step 6 says:
   > Old `[label](findings/<topic>.md)` → `[label](../../findings/<topic>.md)`.
   That resolves to `docs/planning/findings/...` which does not exist. The correct rewrite from a file at `docs/planning/workstreams/<name>/` is `../../../findings/<topic>.md` (three ups, not two). I used the three-ups form. Suggest updating the playbook so the next workstream to migrate doesn't burn a link-check cycle on this.
2. **Compositing chat's inbound reference still broken.** Their `progress.md` links to my old path (`../../../renoir-dataset-progress.md`). Left for them to fix on their own self-migration. Flagging here so the parent's "after each migration, run check_doc_links and confirm no new breakage" pass doesn't blame this on me.

## LoRA docs target structure

Proposal in response to the migration block's request. Three current findings docs cover overlapping ground; the migration block proposes a three-way restructure on the LoRA-pipeline-export milestone. My proposed section-level boundaries below.

### Current state (4 docs, after I added the deep-dive in this session)

| Doc | Length | Scope | What it does well | What is generic vs Renoir-specific |
|---|---|---|---|---|
| `docs/findings/lora-training.md` | ~310 lines | Renoir CivitAI playbook | The push-button settings table (§3), expected outcomes per checkpoint (§5), subject-distance note (§6), inference notes for slow-interpolation (§8), sign-off checklist (§9) | Mostly Renoir-specific (every section calls Renoir paintings by name); about 25% is reusable generic guidance |
| `docs/findings/dataset-practice.md` | ~230 lines | Generic five-phase dataset recipe | The five-phase recipe (Source → Vision audit + crop → Human-in-the-loop refinement → Caption → Hand-off); failure-mode table; mid-project decision log | Almost entirely generic; "Renoir actuals" is one column in the headline table |
| `docs/findings/dataset-hygiene.md` | ~45 lines | Placeholder, needs filling | Currently a stub pointing at the Gemini crop pipeline | Empty of Renoir content; pure scaffolding |
| `docs/findings/lora-training-deep-dive.md` | ~280 lines | Generic theory + tools + objective-specific recipes | The four-objective frame; hyperparameter rationale per objective; kohya_ss / OneTrainer / AI Toolkit comparison; failure-mode diagnostics; cheat-sheet recipes per objective | Almost entirely generic |

### Proposed target structure (per the migration block)

After Luca's CivitAI training closes, run a three-way merge into the target structure named in the migration block, with these section-level boundaries:

**TARGET 1. `docs/findings/lora-pipeline.md` (NEW, generic recipe, subject-agnostic).** Source material:

- From `lora-training.md`:
  - §1 (trigger word and tagging convention) — generalised (3-4 lowercase letters, orthogonal to real words, convention with examples `tcole` / `rfl` / `cds`).
  - §2 (Dataset packaging for CivitAI) — verbatim except remove the Renoir-specific zip name in code blocks.
  - §3 (CivitAI training settings table) — generalised, with Renoir numbers as the worked-example column.
  - §4 (which checkpoints to keep) — generalised.
  - §5 (expected outcomes per checkpoint) — generalised to "light vs strong" framework.
  - §6 (subject-distance note) — verbatim; it is already generic.
  - §7 (border-artifact probe) — generalised to "always probe a new LoRA against the border-crop finding".
  - §9 (sign-off checklist) — generalised.
- From `dataset-practice.md`:
  - The five-phase recipe (§ "The five-phase recipe", subsections Phase A through Phase C). It is already generic.
  - The "shape of a Renoir-grade dataset" table — generalised to "shape of a target-grade dataset" with target ranges as columns.
- From `lora-training-deep-dive.md`:
  - §2 (Four LoRA objectives table). Goes in early as the framing.
  - §7 (Validation protocol) — pick 5 hold-outs, render grid, score, save.
  - §9 (Recipes per objective). The four cheat-sheet kohya_ss config blocks.
- From `dataset-hygiene.md`:
  - The Gemini-crop pipeline section becomes a section of `lora-pipeline.md` (§ "Vision audit + crop", absorbing the relevant Phase A.5 prose from `dataset-practice.md`).

Result: ~400 to 500 lines covering "how to build any domain LoRA for SDXL, end to end, recipe form, no Renoir specifics".

**TARGET 2. `docs/findings/lora-training-renoir.md` (RENAMED from `lora-training.md`, the worked example).** Source material:

- The Renoir-specific sections of the current `lora-training.md`: §8 (inference notes for slow-interpolation — concrete YAML config for `examples/configs/renoir/*.yaml`, recommended `lora_scale` values per render intent, prompt vocabulary list, negative-prompt boilerplate). These are Renoir-only.
- The Renoir validation hold-out list (5 named filenames) from §2.
- The Renoir-specific border-artifact probe config from §7.
- A short intro pointing at `lora-pipeline.md` for the generic recipe.
- The mid-project narrative from `progress.md` distilled into "What we learned training Renoir" (one section).

Result: ~150 to 200 lines, all Renoir, all concrete.

**TARGET 3. `docs/findings/dataset-practice.md` (KEPT, absorbs `dataset-hygiene.md`).** Source material:

- The current `dataset-practice.md` sections that don't move to `lora-pipeline.md`:
  - "What we changed mid-project and why" (decision log) — stays here.
  - "File inventory pattern" (the `datasets/<name>/` layout) — stays here.
  - "Common failure modes and their fix" — stays here.
- From `dataset-hygiene.md`: any content beyond the Gemini-crop pipeline (which moved to lora-pipeline.md).

Result: ~150 lines of "what to know when starting a new dataset that doesn't fit neatly into the recipe".

**TARGET 4. `docs/findings/lora-training-deep-dive.md` (KEEP AS-IS).** This already exists and is largely generic. Section reshuffling:

- §1 (What a LoRA actually does to SDXL) — stays.
- §2, §7, §9 — extracted/duplicated into `lora-pipeline.md` (see Target 1). The original copies in the deep-dive can either be removed (avoid duplication) or kept (deeper treatment). My preference: remove from the deep-dive, link to `lora-pipeline.md`. The deep-dive becomes the conceptual companion that explains *why*; the pipeline doc is the recipe.
- §3 (Dataset curation, by objective) — stays; deeper than the pipeline doc.
- §4 (Captioning, by objective) — stays.
- §5 (Hyperparameters that actually matter) — stays.
- §6 (Training tools beyond CivitAI) — stays; this is the unique value of this doc.
- §8 (Failure modes and their diagnostics) — could move to `lora-pipeline.md` as a recipe-level reference, but I prefer it here in the deep-dive (10-row table with diagnoses is a debugging tool, not a recipe step).

Result: ~200 to 250 lines after the de-duplication, focused on theory + tools + diagnostics.

### Cross-link plan

Once the four files settle into the target structure:

- `lora-pipeline.md` opens with a 1-line pointer to `lora-training-renoir.md` (the worked example) and `lora-training-deep-dive.md` (the theory).
- `lora-training-renoir.md` opens with "Generic recipe at [`lora-pipeline.md`](../../../findings/lora-pipeline.md). This file is the Renoir worked example."
- `dataset-practice.md` becomes a companion ("things to know about the dataset side beyond the recipe in `lora-pipeline.md`").
- `lora-training-deep-dive.md` keeps its companion role.

A reader's path: `lora-pipeline.md` is the canonical entry point for "I want to train a domain LoRA". They follow it. If they need to understand a parameter, they jump to `lora-training-deep-dive.md`. If they want a concrete example, they jump to `lora-training-renoir.md`. If they want to know "what could go wrong with the dataset", they jump to `dataset-practice.md`.

### Implementation order

When training closes and Luca asks for the export:

1. Write `lora-pipeline.md` first (the new generic recipe), drawing from all four current docs per the section-level map above.
2. Strip `lora-training.md` down to Renoir-only content. Rename to `lora-training-renoir.md`.
3. De-duplicate `lora-training-deep-dive.md` (drop §2, §7, §9; link to `lora-pipeline.md`).
4. Slim `dataset-practice.md`: move the recipe-shaped content to `lora-pipeline.md`, keep the decision log + failure-mode table + file inventory pattern + "what we changed mid-project" sections.
5. Delete `dataset-hygiene.md` (absorbed). Update the cross-references in `docs/README.md` and the master `docs/planning/progress.md`.
6. Single PR for the whole restructure, `git mv` where applicable so blame and history follow.

Parent chat: please review and either approve, counter-propose, or flag specific section assignments to adjust. The implementation work is on me; I'm just looking for sign-off on the section boundaries before I commit to writing four interlocked files.

## 2026-05-16, session start

- Read context: technique, roadmap, progress, context, after-cole LORA-USAGE, border-crop.
- Created directory skeleton: `datasets/renoir-flowers/{raw,rejected}/`, `docs/findings/` (already existed).
- Workstream split into three phases as briefed: A (sourcing), B (captioning), C (playbook).
- Trigger word locked: `rfl` (matches brief, parallels `tcole`).
- Caption convention locked: `rfl, [subject], [composition], [palette/light], oil painting, impressionist`. 30 to 60 words. No em dashes.

### Phase A sourcing plan

Source priority order:
1. **Wikimedia Commons** — Category:Flower paintings by Pierre-Auguste Renoir + Category:Still life paintings by Pierre-Auguste Renoir. Reliable PD status (Renoir died 1919, PD-old-100). MediaWiki API gives JSON.
2. **WikiArt** — `pierre-auguste-renoir/all-works/text-list` filtered to "Flowers and Still Life" genre. Higher resolution scans, sometimes only thumbnail-grade.
3. **Met Museum API** — `https://collectionapi.metmuseum.org/public/collection/v1/search?artistOrCulture=true&q=Renoir`, filter `isPublicDomain=true` + classification still life.
4. **Art Institute of Chicago API** — `https://api.artic.edu/api/v1/artworks/search?q=renoir flowers`.
5. **Cleveland Museum API** — `https://openaccess-api.clevelandart.org/api/artworks?artists=renoir`.

Subject filter (KEEP):
- Vases / bouquets / arrangements of flowers (roses, peonies, dahlias, chrysanthemums, anemones, gladioli).
- Garden flower close-ups, single blooms, fruit-and-flowers still lifes where flowers dominate.

Subject filter (REJECT):
- Portraits (even with bouquet in hand).
- Landscapes where flowers are scattered foreground detail.
- Bather / nude / figure scenes.
- Pure fruit still lifes with no flowers.
- Drawings, sketches, watercolours (we want the oil-on-canvas surface for the LoRA).

Resolution floor: 768 px on the short side. Skip yellowed scans and visible JPEG compression.

Target: 80 to 200 keeper images. Realistic ceiling given Renoir's actual flower-painting output is probably 120 to 150.

## 2026-05-16, Phase A complete

Final dataset: **102 unique Renoir floral paintings**, all from Wikimedia Commons. Single-source rather than the multi-source plan above. Justification: Commons aggregates the same museum scans the other APIs serve, the search-and-filter pipeline scaled cleanly across 21 floral-keyword queries, and the dataset hit a healthy size + resolution profile (median 2000 px short side, all >= 776 px) without needing to introduce a second source's metadata schema. Met / AIC / Cleveland left as upgrade paths if a specific painting turns up too low-res after CivitAI training feedback.

### Pipeline

1. [datasets/renoir-flowers/source_commons.py](../../../../datasets/renoir-flowers/source_commons.py) — search Commons across 21 floral queries, batch-fetch imageinfo, title-filter (keep on floral tokens, reject on portrait/figure/landscape/animal/fruit-only/object tokens), resolution-filter at 768 px short side, download as JPEG q=95.
2. Manual triage — pulled 217 non-Renoir leak-throughs (photos of real flowers, other artists' bouquets) to `rejected/non-renoir/`, then 10 subject-mismatch Renoirs (figure scenes, landscapes, one watercolor) to `rejected/subject-mismatch/`.
3. [datasets/renoir-flowers/dedup.py](../../../../datasets/renoir-flowers/dedup.py) — perceptual-hash dedup at Hamming threshold 8. Removed 10 near-duplicates (different scans of the same painting), keeping the largest of each group; moved to `rejected/dupes/`.
4. [datasets/renoir-flowers/finalize_metadata.py](../../../../datasets/renoir-flowers/finalize_metadata.py) — re-query Commons extmetadata per surviving file, parse year (clamped to Renoir's painting-active window 1862 to 1919 to filter accession numbers) and collection (regex over Credit + filename), write [metadata.csv](../../../../datasets/renoir-flowers/metadata.csv).

### Headline numbers

| Metric | Value |
|---|---|
| Total keepers | 102 |
| Short-side resolution: min / median / max | 776 / 2000 / 11973 px |
| Resolution >= 1024 px short side (SDXL native) | 94 / 102 |
| Years confidently extracted (1862 to 1919) | 66 / 102 |
| Undated (typical of auction-catalogue scans) | 36 / 102 |

### Sourcing breakdown by collection

Top institutional / catalogue sources:

| Source | Count | Notes |
|---|---|---|
| private collection (Sotheby's catalogue) | 31 | High-quality catalogue scans, PD-art for the underlying Renoir work |
| private collection (Christie's catalogue) | 15 | Same |
| unknown / unattributed | 32 | Commons file has no museum credit; underlying work still PD-old |
| Barnes Foundation | 9 | Highest-quality batch in the set; the canonical Renoir floral holdings |
| Clark Art Institute | 2 | |
| State Hermitage Museum | 2 | |
| Art Institute of Chicago, Cleveland Museum, Dallas Museum, Fogg Museum (Harvard), Foundation E.G. Bührle, Indianapolis Museum, Metropolitan Museum of Art, Musée de l'Orangerie, Musée des Beaux-Arts de Limoges, National Gallery of Art (Washington), Petit Palais Paris | 1 each | Single high-resolution institutional scan each |

The 47 auction-catalogue images (Sotheby's + Christie's) are flagged in `collection` so they can be reweighted or down-sampled at training time if the catalogue colour cast biases the LoRA.

### Public-domain status

All 102 underlying paintings are PD-old (Renoir died 1919, 100+ years). 81 of the Commons files carry an explicit `PD-Art` / `PD-old-100` / `CC0` tag — recorded as `public domain (Renoir d. 1919)`. 21 files carry a CC-BY / CC-BY-SA tag from the photographer's reproduction-photo claim — recorded as `underlying work PD; reproduction photo CC BY[-SA] ...`. Under US PD-art doctrine (Bridgeman v. Corel) faithful 2D reproductions of PD works are not separately copyrightable, so all 102 are usable for training; the CC tags are credit hints, not gatekeepers.

### Sourcing breakdown by subject (skim of titles)

| Subject family | Approximate count |
|---|---|
| Rose bouquets / roses in a vase | ~30 |
| Mixed flower bouquets in a vase | ~25 |
| Anemones (single subject) | ~12 |
| Chrysanthemums | 4 |
| Spring bouquets / mixed seasonal | ~6 |
| Tulips | 3 |
| Peonies | 3 |
| Dahlias, gladioli, narcissi | 5 |
| Geraniums in a pot | 1 |
| Lilacs | 1 |
| Garden / floral close-up | ~6 |
| Floral + fruit mixed still life (flowers dominant) | ~6 |

Approximate counts because some titles are vague ("fleurs", "bouquet de fleurs") and would require visual confirmation to subdivide.

### Rejected sources and why

- **Wikimedia Commons "Category:Flower paintings by Pierre-Auguste Renoir"** — exists but is empty. Renoir's florals are catalogued under "Still life paintings by ..." mixed with fruit, and search-by-keyword caught them more reliably than category-walk.
- **Wikimedia Commons "Category:Still life paintings by Pierre-Auguste Renoir"** — walked and inspected, but ~80 % is fruit/objects (onions, peaches, cauliflower, sugar bowls, pheasants). Search-based pulled the floral subset more cleanly.
- **WikiArt** — not queried in this pass. Their floral-genre filter would have added catalogue depth, but their CDN images are typically 1000 to 1500 px short side and lower than what Commons + Sotheby's catalogues already provided. Park for if a specific painting is missing.
- **Met Museum, Art Institute of Chicago, Cleveland Museum APIs** — not queried in this pass. The major holdings (Met "Bouquet of Chrysanthemums" 51.7, AIC 1933.1173, Cleveland 1941.14) all surfaced through Commons. Park for upgrade-pass if needed.
- **Live amateur photos under Miguel Hermoso Cuesta / Happiness2013** — kept (2 entries, "bouquet-renoir-01/02.jpg", "fleurs-pierre-auguste-renoir-1841-1919.jpg") with the CC reproduction-photo flag. Quality risk is glare/perspective; if visual review flags issues, drop to `rejected/quality/`.

### Deliverables (Phase A)

- [datasets/renoir-flowers/raw/](../../../../datasets/renoir-flowers/raw/) — 102 JPEGs (gitignored).
- [datasets/renoir-flowers/rejected/](../../../../datasets/renoir-flowers/rejected/) — 237 rejected files in `non-renoir/`, `subject-mismatch/`, `dupes/` (gitignored). Kept on disk for audit.
- [datasets/renoir-flowers/metadata.csv](../../../../datasets/renoir-flowers/metadata.csv) — 102 rows, tracked. Columns: `filename, title, year, collection, source_url, original_width, original_height, public_domain_status, direct_url, sha1, license_short, artist_recorded, credit_line`.
- [datasets/renoir-flowers/_commons_meta.csv](../../../../datasets/renoir-flowers/_commons_meta.csv) and [_commons_rejects.csv](../../../../datasets/renoir-flowers/_commons_rejects.csv) — intermediate audit trail from the sourcing script (untracked).

### Heads-up for Phase B

The 36 "undated" entries weaken any year-stratified train/val split. Mitigations:
- Caption template does not include year; year is metadata-only.
- Validation hold-out (5 images, see Phase C playbook) will be picked by visual diversity, not date.

The 47 auction-catalogue images skew the resolution-distribution heavy (median 2000 px) but introduce a subtle colour cast (typical Sotheby's/Christie's catalogue lighting). If the trained LoRA shows a colour bias toward warm-yellow auction-catalogue tonality, re-train with these 47 marked as a separate concept group or down-weighted.

## 2026-05-16, Phase B complete

Captions generated for all 102 images, deterministic and offline. No VLM call. Generator at [datasets/renoir-flowers/captions.py](../../../../datasets/renoir-flowers/captions.py); outputs [captions.txt](../../../../datasets/renoir-flowers/captions.txt) (one TAB-separated `filename<TAB>caption` line per image) and [captions.json](../../../../datasets/renoir-flowers/captions.json) (structured fields per image).

### Convention

```
rfl, [subject], [composition], [palette / light], [brushwork / surface], oil painting, impressionist
```

The `[brushwork / surface]` slot was added during Phase B to lift every caption into the brief's 30 to 60 word window (initial five-slot template produced 25 to 37 words; the four-slot template under-shot for half the dataset). The brushwork vocabulary stays inside Renoir-appropriate language ("broken colour", "wet-into-wet petal blending", "loose impressionist touch") so the LoRA picks up surface texture cues alongside style.

### Generator architecture

1. **Subject** parsed from a cleaned `title + filename` blob via ordered regex rules. Compound titles (e.g. "roses and peonies") resolve to a mixed-bouquet phrasing; single-flower titles to their single-family phrase. Fallback subject `a study of cut flowers on a table` is wired in but is never hit by the current 102 entries.
2. **Composition** picked from subject family + aspect ratio. Portrait, square, landscape buckets each get their own phrasing. Centered-vase, bouquet-laid-across, frieze-of-blooms, close-cropped-fragment, and potted-on-a-ledge are the five composition idioms.
3. **Palette / light** sampled deterministically from a 12-entry vocabulary, biased by inferred subject (white-flower titles bias toward cool / window-light palettes; crimson-rose titles toward warm impasto palettes; etc.). Even distribution across the dataset.
4. **Brushwork** sampled deterministically from an 8-entry vocabulary, hashed off the filename so distribution is even.

Word-count distribution after Phase B regen: all 102 in [30, 60]. Concrete spread: 33 to 39 words. Tight, but the brief's range allowed; broader spread would need more verb-noun variety in the rule vocab.

### Five-caption sample, stratified across subject families

```
[roses] auguste-renoir-roses-dans-un-vase-vert.jpg (37w)
rfl, a porcelain vase of roses, centered still life on a table, vase rising in the frame, rich impasto reds and crimsons against a tobacco-brown ground, loose painterly handling, broken colour across the petals, oil painting, impressionist

[anemones] pierre-auguste-renoir-anemones-14556446499.jpg (33w)
rfl, a study of anemones, close-cropped fragment, flowers filling the frame edge to edge, cool morning light, white petals against a celadon green wall, thick impasto highlights, soft scumbled background, oil painting, impressionist

[chrysanthemums] bouquet-of-chrysanthemums-and-a-japanese-fan-by-pierre-auguste-renoir.jpg (37w)
rfl, a bouquet of chrysanthemums, bouquet laid across the frame, fabric or table cloth in the foreground, ochre and umber backdrop, pale petals catching the front-light, feathered brushwork on the leaves, wet-into-wet petal blending, oil painting, impressionist

[mixed bouquet] bouquet-in-a-vase-renoir-indianapolis-museum-of-art-dsc00671.jpg (39w)
rfl, a bouquet of mixed flowers in a vase, centered still life on a table, vase rising in the frame, warm interior light, brick reds, terracotta and gilt, delicate broken brushwork, optical mixing in the petals, oil painting, impressionist

[geraniums] pierre-auguste-renoir-geraniums-in-a-copper-basin-11521194565.jpg (34w)
rfl, a planter of geraniums, potted plant on a window ledge, warm afternoon light, creamy whites and pinks against a deep rose ground, thinly painted ground, loaded brush on the blooms, oil painting, impressionist
```

### Subject-family distribution (post-Phase-B parse)

| Subject family | Count |
|---|---|
| Mixed-flower bouquets in a vase | 30 |
| Roses (vase / bouquet / study / cluster) | 28 |
| Anemones | 15 |
| Chrysanthemums | 5 |
| Tulips | 3 |
| Peonies | 2 |
| Lilacs | 2 |
| Geraniums in a copper basin | 1 |
| Other (study, dahlias, flowers-and-fruit, painterly study) | 16 |

The dataset is dominated by rose subjects and mixed bouquets, which matches Renoir's actual production. The training set therefore privileges those subjects at inference time, which is intentional for the objkt labs release subject vocabulary (the planned A/B/C subjects centre on rose bouquets and mixed-flower vases).

### Open question for Luca

The current generator is rule-based and deterministic. It does not look at the pixels. Two consequences:
- **Subject ambiguity in titles**: a Sotheby's "Bouquet de fleurs" tells us nothing about which flowers. The caption falls back to the generic "mixed flowers in a vase" phrasing for 30 of the 102 entries. A vision-language pass (Gemini 2.5 Pro or Claude with vision) could replace those 30 generic captions with subject-accurate ones. Worth doing if the first training pass shows the LoRA over-generalising into a "vague impressionist bouquet" rather than locking specific blooms.
- **Palette truth**: palette phrases are drawn from a small vocab and biased by title, not by image colour. They will be right on average and wrong in specifics. A second pass that reads the pixels (e.g. dominant-colour extraction with k-means) would make palette phrases image-truthful with no manual review.

Both are post-Phase-C improvements, gated on first-pass LoRA quality. The current captions are good enough to train a strong first checkpoint.

### Deliverables (Phase B)

- [datasets/renoir-flowers/captions.txt](../../../../datasets/renoir-flowers/captions.txt) — 102 lines, TAB-separated `filename<TAB>caption`. Tracked.
- [datasets/renoir-flowers/captions.json](../../../../datasets/renoir-flowers/captions.json) — 102 objects with structured fields (subject, composition, palette_light, brushwork, suffix, word_count, source_title, aspect_ratio). Tracked.
- [datasets/renoir-flowers/captions.py](../../../../datasets/renoir-flowers/captions.py) — generator. Re-run on metadata.csv changes. Deterministic.

### Next: Phase C

Training playbook at `docs/findings/lora-training.md`. The dataset, captions, and trigger word are now locked.

## 2026-05-16, Phase C complete

Training playbook drafted at [docs/findings/lora-training.md](../../../findings/lora-training.md). Push-button instructions, no judgement calls left for Luca at training time except the predictable visual grading at each epoch.

### Playbook structure (10 sections)

1. **Trigger word + tagging convention.** `rfl`. Caption template repeated from Phase B for reference.
2. **Dataset packaging for CivitAI.** ZIP format, image / caption sibling-pair layout, the 5-image validation hold-out moved to `validation/`.
3. **CivitAI training settings.** Concrete table: SDXL 1.0 base, rank 16, alpha 8, LR 3e-5 (lower than Cole), text-encoder off, batch 2, 6 repeats, 10 epochs. Each setting carries its rationale, not just the number.
4. **Which checkpoints to keep.** Two: epoch 1 (light) and epoch 10 (strong), matching the Cole / Casa del Suono release pattern.
5. **Expected outcomes per checkpoint.** Light = palette family without subject lock-in (scale 0.4 to 0.6). Strong = full pastiche (scale 0.7 to 0.9).
6. **Subject-distance note.** Carried over from `docs/findings/border-crop.md`. The most important caveat in the playbook: cross-domain renders need the LoRA scaled UP, not down. Pre-empts the intuitive-but-wrong fix of lowering scale when the LoRA disappears off-distribution.
7. **Border-artifact probe.** Renoir LoRA is the first since the EDGE_CROP=0 decision in [findings/border-crop.md](../../../findings/border-crop.md); spec'd config for the probe is included so the parent chat can run it directly.
8. **Inference notes for slow-interpolation.** File placement under `models/loras/`, YAML config skeleton for `examples/configs/renoir/*.yaml`, recommended `lora_scale` values per render intent, prompt vocabulary list, negative-prompt boilerplate.
9. **Sign-off checklist** before release renders.
10. **Out of scope**: the actual training, the per-piece configs, A/B/C subject locking (artist + release curator, on the locking call), VLM caption refinements (deferred).

### Supporting deliverables

- [datasets/renoir-flowers/package_for_civitai.py](../../../../datasets/renoir-flowers/package_for_civitai.py) — packages `raw/` + `captions.txt` into a CivitAI-ready ZIP. Separates the 5 validation images into `validation/`. Smoke-tested: 97 training pairs, 5 validation pairs, 329.8 MB ZIP.
- [datasets/renoir-flowers/.gitignore](../../../../datasets/renoir-flowers/.gitignore) — local gitignore covering `raw/`, `rejected/`, `validation/`, `_civitai_staging/`, `*.zip`, and the intermediate `_commons_*.csv` audit files. Keeps the tracked surface to: metadata, captions, scripts.

### Validation hold-out (5 images)

Picked for visual diversity across subject families and one off-distribution case:

1. `pierre-auguste-renoir-roses-in-a-vase-1941-14-cleveland-museum-of-art.jpg` — canonical roses-in-a-vase, Cleveland Museum.
2. `pierre-auguste-renoir-mixed-flowers-in-an-earthenware-pot-google-art-project.jpg` — Google Art Project archetypal mixed bouquet.
3. `pierre-auguste-renoir-anemones-an-mones-bf1167-barnes-foundation.jpg` — Barnes Foundation anemones.
4. `pierre-auguste-renoir-chrysanthemums-1933-1173-art-institute-of-chicago.jpg` — AIC chrysanthemums, small-family probe.
5. `pierre-auguste-renoir-geraniums-in-a-copper-basin-11521194565.jpg` — the only "potted plant" composition in the set, off-distribution probe.

### Final delivery surface

```
slow-interpolation/
  datasets/renoir-flowers/
    .gitignore                  (tracked) local rules
    source_commons.py           (tracked) sourcing script, idempotent
    dedup.py                    (tracked) perceptual-hash dedup script
    finalize_metadata.py        (tracked) extmetadata fetch + CSV build
    captions.py                 (tracked) caption generator, deterministic
    package_for_civitai.py      (tracked) ZIP packaging
    metadata.csv                (tracked) 102 rows, full provenance
    captions.txt                (tracked) 102 lines, filename<TAB>caption
    captions.json               (tracked) 102 objects, structured caption fields
    raw/                        (gitignored) 102 keeper JPEGs
    rejected/                   (gitignored) 237 audit files (non-renoir, subject-mismatch, dupes)
    validation/                 (gitignored) 5 hold-out images + .txt captions, created by package_for_civitai.py
    _civitai_staging/           (gitignored) 97 training pairs, created by package_for_civitai.py
    renoir-flowers-civitai.zip  (gitignored) 329.8 MB CivitAI-ready ZIP
    _commons_meta.csv           (gitignored) intermediate audit
    _commons_rejects.csv        (gitignored) intermediate audit

  docs/
    renoir-dataset-progress.md  (tracked) this file
    findings/
      lora-training.md          (tracked) the playbook
```

### What Luca does next

1. Run `python datasets/renoir-flowers/package_for_civitai.py` to produce the ZIP.
2. Upload `renoir-flowers-civitai.zip` to CivitAI.
3. Configure the training job per playbook section 3.
4. After 10 epochs, download `epoch_1.safetensors` and `epoch_10.safetensors`.
5. Visually grade against the 5 validation hold-out paintings.
6. Copy the two chosen checkpoints to `models/loras/` and notify the parent chat.

The parent chat takes over from step 6 to write `examples/configs/renoir/*.yaml` and run the release renders.

### Workstream closed.

## 2026-05-16, Phase A.5 — Gemini-driven image cleanup (re-opened)

Luca observed that some sourced images included physical frames, white auction-catalogue backgrounds, and museum-conservation watermarks. Re-opened Phase A to run a vision-model audit and clean the dataset before training.

### Pipeline

Three crop passes, each more aggressive than the last, plus a manual fallback for the cases the model could not handle:

1. **[gemini_review.py](../../../../datasets/renoir-flowers/gemini_review.py)** — Gemini 2.5 Flash inspects each of the 102 images downscaled to 1024 px. Returns strict JSON per image: `has_physical_frame`, `has_white_or_paper_border`, `has_watermark`, `painting_bbox_pct`, `needs_crop`, `notes`. Idempotent + resumable; output at [review.json](../../../../datasets/renoir-flowers/review.json).
2. **[apply_crops.py](../../../../datasets/renoir-flowers/apply_crops.py)** — first-pass crop using `painting_bbox_pct`, with conservative outward padding (1 % for "frame fills most" cases, 2 % for "small painting in catalogue field"). If the cropped short side falls below 768 px, upscale with PIL LANCZOS (capped at 2x). Originals backed up to `raw_orig/`; processed files overwrite `raw/`. Audit trail at [processed.json](../../../../datasets/renoir-flowers/processed.json).
3. **[gemini_review_pass2.py](../../../../datasets/renoir-flowers/gemini_review_pass2.py)** — re-inspects only the previously-framed images, with a tighter prompt that requires cutting inside the inner edge of any remaining frame. Output: [review_pass2.json](../../../../datasets/renoir-flowers/review_pass2.json).
4. **[apply_crops_pass2.py](../../../../datasets/renoir-flowers/apply_crops_pass2.py)** — applies the tighter pass-2 bboxes only where Gemini returned a valid bbox (>= 30 % in both dimensions; degenerate 1x1 responses are skipped for manual handling).
5. **[manual_crops.json](../../../../datasets/renoir-flowers/manual_crops.json)** + **[apply_manual_crops.py](../../../../datasets/renoir-flowers/apply_manual_crops.py)** — bbox dictated by visual inspection for the four images Gemini could not bbox cleanly in pass 2. Includes the Dallas Museum roses-and-peonies (full gilded frame with cream mat that needed an aggressive crop to (18,12) at 60x66 %).
6. **[update_metadata_post_process.py](../../../../datasets/renoir-flowers/update_metadata_post_process.py)** — re-reads every file's current dimensions, merges processing log + Gemini flags into [metadata.csv](../../../../datasets/renoir-flowers/metadata.csv) as new columns: `saved_width`, `saved_height`, `processed`, `processed_ops`, `flags_frame`, `flags_white_bg`, `flags_watermark`, `review_notes`.

### Numbers

| Stage | Count |
|---|---|
| Gemini-flagged: physical frame | 12 |
| Gemini-flagged: white / paper border | 13 |
| Gemini-flagged: watermark / museum tag | 4 |
| Distinct images needing some crop | 26 (one degenerate-bbox case skipped: bbox covered the full image so the crop would be a no-op) |
| Pass-1 crops applied | 26 |
| Pass-2 tighter crops applied | 8 |
| Manual crops applied | 4 |
| Upscales applied (cropped short side fell below 768) | 1 |

### Resolution distribution after cleanup

| Metric | Before Phase A.5 | After Phase A.5 |
|---|---|---|
| Min short side | 776 px | 768 px |
| Median short side | 2000 px | 2000 px |
| Max short side | 11973 px | 11973 px |
| Below 1024 px short side | 9 | unchanged |
| Below 768 px (out of SDXL bucket) | 0 | 0 |

Phase A.5 took the dataset from "mostly clean with edge-case framing" to "uniformly cropped to the painting, no decorative borders or watermarks". The crops reduced the median total pixel count by roughly 12 % but preserved the SDXL training bucket floor.

### Watermark cases

Four images carried burned-in watermarks. All handled correctly:

| File | Watermark type | Crop outcome |
|---|---|---|
| `pierre-auguste-renoir-bouquet-of-roses-1955-592-clark-art-institute.jpg` | Clark institutional text at top edge + color-calibration strip at bottom + side colour targets | Cropped to (6,8) at 89x83 %, all watermark gone |
| `pierre-auguste-renoir-peonies-1955-585-clark-art-institute.jpg` | Same as above | Cropped to (10,0) at 80x99 % |
| `pierre-auguste-renoir-roses-and-peonies-in-a-vase-2019-67-22-mcd-dallas-museum-of-art.jpg` | Combined frame + cream mat + accession-number watermark | Pass-2 degenerate → manual crop to (18,12) at 60x66 % |
| `renoir-roses-1917-88-167.jpg` | Faint Bridgeman / institutional border | Cropped to (3,2) at 95x96 % |

### Gallery changes

Regenerated [gallery.html](../../../../datasets/renoir-flowers/gallery.html) with:

- **Per-card badges** in the top-left corner: `cropped` (gold), `frame` (warm orange), `white-bg` (cool blue), `watermark` (rose). Visible at-a-glance to spot which images were touched and what the original issue was.
- **Filter buttons** in the header: `All / Cropped / Was framed / White background / Watermark`. Click to narrow the mosaic to one category.
- **Operations line** on the back of each cropped card: shows the actual crop coordinates and any upscale factor applied. Audit-friendly.
- **Source link** preserved on the flipped face: every back face links to the Wikimedia Commons file page, so the original-version provenance is one click away even after local processing.

### Notes / known minor residuals

- `pierre-auguste-renoir-bouquet-1900-ca.jpg`: a thin gold leaf at top + right edges still visible after pass-2. Frame is ~3 % of canvas; acceptable for training, would over-crop the painting if pushed further.
- `bouquet-in-a-vase-renoir-indianapolis-museum-of-art-dsc00671.jpg`: 1 to 2 px slivers of wood frame at top corners. Negligible.

If the trained LoRA shows any "draw a frame" tendency (unlikely given border-crop finding's evidence at 1.35x max gradient ratio), revisit those two specifically; otherwise treat as good.

### Deliverables (Phase A.5)

New tracked artefacts under `datasets/renoir-flowers/`:

- `gemini_review.py`, `gemini_review_pass2.py` — the audit scripts.
- `apply_crops.py`, `apply_crops_pass2.py`, `apply_manual_crops.py` — the crop pipeline.
- `update_metadata_post_process.py` — metadata refresh.
- `manual_crops.json` — the 4 manual bboxes.
- `review.json`, `review_pass2.json`, `processed.json` — audit trails (gitignored as data, not text-of-record).

Image deltas (gitignored):
- 26 files in `raw/` updated to cropped + optionally upscaled versions.
- 26 originals preserved in `raw_orig/`.

[metadata.csv](../../../../datasets/renoir-flowers/metadata.csv) now carries the full pre / post / flag triple for each image.

### Re-run gate

If a future audit pass wants to redo this:

```bash
# clear the audit artefacts and originals, then re-run end-to-end
rm datasets/renoir-flowers/review.json datasets/renoir-flowers/review_pass2.json datasets/renoir-flowers/processed.json
rm -rf datasets/renoir-flowers/raw && cp -r datasets/renoir-flowers/raw_orig datasets/renoir-flowers/raw
py -3.11 datasets/renoir-flowers/gemini_review.py
py -3.11 datasets/renoir-flowers/apply_crops.py
py -3.11 datasets/renoir-flowers/gemini_review_pass2.py
py -3.11 datasets/renoir-flowers/apply_crops_pass2.py
py -3.11 datasets/renoir-flowers/apply_manual_crops.py
py -3.11 datasets/renoir-flowers/update_metadata_post_process.py
py -3.11 datasets/renoir-flowers/build_gallery.py
```

### Workstream re-closed.

## 2026-05-16, Phase A.6 — Scope expanded to scenes WITH flowers + gallery flag UI

Luca asked to broaden the dataset beyond pure floral still life to any Renoir scene with flowers (garden landscapes, figures with bouquets, mother-and-child garden scenes), and to add browser-side flag buttons so he can mark images for removal or flag frame artefacts.

### Expanded sourcing

Restored 8 previously-rejected scene-with-flowers files from `rejected/subject-mismatch/`:
- `femme-cueillant-des-fleurs-by-pierre-auguste-renoir-c1874-oil-on-canvas.jpg`
- `pierre-auguste-renoir-fleurs-et-chats.jpg`
- `pierre-auguste-renoir-woman-gathering-flowers-femme-cueillant-des-fleurs-bf56-barnes-foundation.jpg` (later dropped by Gemini triage)
- `portrait-de-coco-et-fleurs-by-pierre-auguste-renoir.jpg`
- `renoir-paysage-avec-fleurs-et-fond-de-mer-1914.jpg`
- `renoir-paysage-fleurs-grimpantes-et-maisons-1900.jpg` (later dropped by Gemini triage)
- `renoir-vase-de-fleurs-et-femme-circa-1915.jpg`
- `renoir-woman-with-lilacs.jpg`

Then [source_commons_expand.py](../../../../datasets/renoir-flowers/source_commons_expand.py) ran 30 new search queries on Commons: "Renoir garden flowers", "Renoir picking flowers", "Renoir Cagnes garden", "Renoir wisteria", "Renoir hollyhocks", "Renoir straw hat flowers", and so on. After Renoir-token-required + floral-or-garden-token-required + reject-token-excluded title filters + 768 px short-side filter, downloaded 24 new candidate images.

### Gemini Phase-2 triage

The expanded search pulled in photographs of the Renoir Museum in Cagnes-sur-Mer and a couple of pure-landscape paintings without notable flowers. [gemini_triage_new.py](../../../../datasets/renoir-flowers/gemini_triage_new.py) asked Gemini 2.5 Flash to verify per file: `is_painting`, `by_renoir`, `flowers_visible`, `keep_for_dataset`. Strict prompt; the model flagged 14 of the 32 newly-added / restored files as drops (photos of the museum grounds, garden landscapes where flowers were "barely there", one "Square Auguste Renoir" street-view photograph, a tea-table-in-the-garden where the flowers were only suggested). All 14 moved to `rejected/expanded-mismatch/`.

Survivors: 18 new entries kept.

### Final dataset shape

| | Phase A | Phase A.6 |
|---|---|---|
| Total in `raw/` | 102 | **120** |
| Still-life-dominant subjects | 102 | 96 |
| Figure / portrait with flowers | 0 | 6 |
| Garden / landscape with flowers | 0 | 9 |
| Artist-in-garden scene | 0 | 1 (Renoir paints Monet at Argenteuil) |
| Mother / child in garden, child with vase | 0 | 2 |
| Coastal landscape with floral foreground | 0 | 1 |
| Still life with cats | 0 | 1 (`fleurs et chats`) |

Notable adds: Renoir painting Monet painting his garden at Argenteuil (a meta-painting), Camille Monet at her tapestry frame in the park, two girls picking flowers in a meadow (NGA), a coastal Cagnes garden, Coco with a vase of flowers (child portrait), Spring-bouquet-adjacent figure works.

### Cropping pass on new files

Re-ran the existing Gemini frame/bg/watermark review across only the 18 new entries (the previous 102 stayed cached). Two new white-background catalogue cases needed cropping:

- `renoir-all-e-du-jardin-des-collettes-1907.jpg` (Sotheby's catalogue scan)
- `renoir-paysage-avec-fleurs-et-fond-de-mer-1914.jpg` (Sotheby's catalogue scan)

One file (`renoir-girls-picking-flowers-in-a-meadow-about-1890.jpg`) was flagged WATERMARK but with a bbox covering the full image; on visual inspection the image is clean, so no crop applied. Gemini false-positive — kept as-is.

Updated cleanup totals across the full 120-image set: **frame=12, white-bg=15, watermark=5, processed=28**.

### Captioning extension

[captions.py](../../../../datasets/renoir-flowers/captions.py) gained 11 new subject rules and 9 new composition phrasings for the scene-with-flowers vocabulary. Concrete additions:

| Title hit | Subject phrase |
|---|---|
| `cueillette des fleurs` / `picking flowers` / `gathering flowers` | "a young woman gathering flowers in a sunlit meadow" |
| `jardin fontenay` / `jardin sorrente` / `garden landscape` | "a Mediterranean garden landscape with flowering plants in midday sun" |
| `claude monet painting in his garden` | "an artist at his easel painting in a flowering garden" |
| `camille monet` / `tapisserie dans le parc` | "a woman seated in a garden working at a tapestry frame surrounded by flowers" |
| `coco et fleurs` | "a small child with a vase of flowers on a table" |
| `woman with lilacs` | "a young woman holding a sprig of lilacs" |
| `fleurs et chats` | "a still life of mixed flowers in a vase with two cats curled at the table edge" |
| `paysage avec fleurs et fond de mer` | "a coastal landscape with a foreground of garden flowers and a sea horizon" |
| `in the garden` / `jeunes filles dans un jardin` | "two young figures in a sunlit garden with flowers" |

Compositions adapted to figure / garden / landscape orientations (portrait vs square vs landscape). All 120 captions stay inside the 30-60 word window (current spread 33-39).

### Gallery flag UI

[gallery.html](../../../../datasets/renoir-flowers/gallery.html) regenerated with interactive per-card flagging:

**Per-card controls** (top-right of each card, do not flip the card on click):
- `×` button: mark / unmark for removal. Card dims to charcoal with a "MARKED FOR REMOVAL" overlay.
- `⚐` button: flag for frame / artefact review. Card gets an amber 3 px ring.

**Toolbar** (sticky under the header):
- Live counts: "N marked for removal" / "N flagged for frame review".
- `Export flags JSON` button: downloads `gallery-flags.json` with `{exported_at, remove: [filenames], review_frame: [filenames]}` for Luca to send back to me.
- `Clear all flags` button (with confirm dialog).

**Filter buttons** (added to existing filter bar):
- `My: remove` — show only cards Luca marked for removal.
- `My: review frame` — show only cards Luca flagged for frame review.

**Keyboard shortcuts**:
- `R` while hovering a card: toggle "remove" flag.
- `F` while hovering a card: toggle "review frame" flag.

**Persistence**: state lives in `localStorage` under key `renoir-gallery-flags-v1`. Survives reload, browser restart, page rebuild. Cleared only by the `Clear all flags` button.

### Workflow for Luca

1. Browse the gallery, click `×` to mark removals or `⚐` to flag frame-review cases.
2. Use `My: remove` / `My: review frame` filters to revisit flagged cards.
3. Click `Export flags JSON`. Send `gallery-flags.json` back.
4. I'll process the file: actually move "remove" entries to `rejected/`, re-crop or re-source "review frame" entries.

### Deliverables (Phase A.6)

- [datasets/renoir-flowers/source_commons_expand.py](../../../../datasets/renoir-flowers/source_commons_expand.py) — expanded sourcing.
- [datasets/renoir-flowers/gemini_triage_new.py](../../../../datasets/renoir-flowers/gemini_triage_new.py) — Renoir-painting + flowers-visible triage.
- [datasets/renoir-flowers/captions.py](../../../../datasets/renoir-flowers/captions.py) — expanded with 11 new subject rules + 9 new composition phrasings.
- [datasets/renoir-flowers/build_gallery.py](../../../../datasets/renoir-flowers/build_gallery.py) — flag buttons, localStorage, export, keyboard shortcuts.
- [datasets/renoir-flowers/metadata.csv](../../../../datasets/renoir-flowers/metadata.csv) — 120 rows.
- [datasets/renoir-flowers/captions.txt](../../../../datasets/renoir-flowers/captions.txt) + [captions.json](../../../../datasets/renoir-flowers/captions.json) — 120 captions.
- [datasets/renoir-flowers/gallery.html](../../../../datasets/renoir-flowers/gallery.html) — regenerated with interactive flagging.

### Open question

The dataset is now a hybrid: 96 still-life-dominant + 24 scene-with-flowers. The LoRA will learn a broader Renoir "flowers" concept than the original pure-still-life version. Two consequences worth flagging at training-time:
- Caption-template subjects now span "porcelain vase of roses" through "woman picking flowers in a meadow". The trigger `rfl` will absorb both. At inference, prompts that don't specify a still-life setting may now generate figure-with-flowers compositions, which is intended.
- The 24 scene-with-flowers files are a minority. They will exert subtle compositional influence (broken outdoor light, figure mass in lower frame) without overwhelming the still-life signature.

If on first training pass the LoRA drifts toward "figure in a garden" too readily, restrict training to the 96-still-life subset (filter by `subject` field in `captions.json`) and re-train. The dataset is now split-friendly.

### Workstream re-closed (again).

## 2026-05-17, Phase A.7 — User flag round 1 processed

Luca worked through the gallery and exported [user-flags-2026-05-17.json](../../../../datasets/renoir-flowers/user-flags-2026-05-17.json): **2 marked for removal, 21 flagged for frame / artefact review**.

### Removals (2)

Moved to `rejected/user-removed/`:
- `pierre-auguste-renoir-still-life-with-bouquet-google-art-project.jpg`
- `renoir-roses-1917-88-167.jpg`

### Frame-review pass (21)

Two-step process for the 21 user-flagged files:

1. **[gemini_review_userflags.py](../../../../datasets/renoir-flowers/gemini_review_userflags.py)** — Gemini 2.5 Flash re-inspected each with a tighter prompt explicitly asking for the smallest bbox containing only painted canvas, considering white paper, cream catalogue mat, dark wall, gilded sliver, calibration strip, etc. Returns the most aggressive sensible bbox.
2. **[apply_user_flag_crops.py](../../../../datasets/renoir-flowers/apply_user_flag_crops.py)** — applied the 11 valid bboxes (each shrunk by 5 to 15 % per axis). The other 10 cases either returned a no-op bbox (Gemini said "clean") or a degenerate 1x1 (Gemini saw residual but could not box it).

Concrete crops applied in this pass:

| File | Margin type | Before | After |
|---|---|---|---|
| auguste-renoir-bouquet-de-narcisses-et-de-roses-...jpg | white_paper | 3710x4353 | 3599x4222 |
| pierre-auguste-renoir-bouquet-1900-ca.jpg | gilded_frame | 982x1165 | 864x1025 |
| pierre-auguste-renoir-bouquet-de-roses-01.jpg | gilded_frame | 1936x2005 | 1831x1897 |
| pierre-auguste-renoir-bouquet-in-un-vaso-1878.jpg | gilded_frame | 1243x1741 | 1181x1654 |
| renoir-all-e-du-jardin-des-collettes-1907.jpg | white_paper | 1120x1020 | 915x768 |
| renoir-bouquet-de-roses-35-by-38cm.jpg | white_paper | 1080x1080 | 1048x1048 |
| renoir-bouquet-de-roses-dans-un-vase-1900.jpg | white_paper | 1080x1080 | 1026x1026 |
| renoir-fleurs-17-2-by-19cm.jpg | white_paper | 960x960 | 768x768 |
| renoir-fleurs-18-1-by-15-cm.jpg | white_paper | 2000x2000 | 1900x1900 |
| renoir-paysage-avec-fleurs-et-fond-de-mer-1914.jpg | white_paper | 1480x1180 | 1317x1050 |
| renoir-vase-de-fleurs-38-7-by-50-5-cm.jpg | white_paper | 2000x1580 | 2000x1304 |

3. **Visual inspection of the 10 ambiguous cases** (5 degenerate Gemini bboxes + 5 Gemini-said-clean-but-Luca-flagged). Read each image directly. Found 3 with verified residual margins; the other 7 looked clean to me (Luca may have flagged precautionarily, or the residuals were too subtle to find at preview scale).

4. **[manual_crops_user.json](../../../../datasets/renoir-flowers/manual_crops_user.json) + [apply_manual_crops_user.py](../../../../datasets/renoir-flowers/apply_manual_crops_user.py)** — 3 micro-crops verified by direct read:

| File | Reason |
|---|---|
| renoir-roses-blanches.jpg | thin gold-ish frame/mat sliver on right edge and bottom-right corner |
| renoir-les-roses-rouges.jpg | thin off-white catalogue paper margin on the right edge |
| renoir-an-mones-20-by-20-8cm.jpg | slim cream/ochre paper margin all around the painting |

### 7 cases left untouched

The remaining 7 user-flagged files looked clean to me on visual inspection. The most likely explanation is precautionary flagging (Luca wanting to double-check at full resolution) rather than actual residual artefacts:

- `renoir-an-mones-33-6-by-21-cm.jpg`
- `renoir-an-mones-fragment-32-by-28-5cm.jpg`
- `renoir-bouquet-de-fleurs-51-by-40cm.jpg`
- `renoir-bouquet-de-fleurs-dans-un-vase-vert.jpg`
- `renoir-nature-morte-fleurs-et-fruits-1889.jpg`
- `renoir-vase-de-fleurs-32-7-by-27-5-cm.jpg`
- `renoir-vase-de-fleurs-41-6-by-51-4-cm.jpg`

If on the next gallery look Luca still sees an artefact in any of these, re-flagging them in the next round will surface them again and we can apply a manual bbox with Luca pointing out the specific edge.

### Final state

| | Phase A.6 end | Phase A.7 end |
|---|---|---|
| Total in `raw/` | 120 | **118** |
| Cropped / processed | 28 | 41 (the 11 Gemini-bbox + 3 manual on top of the pre-existing 27, minus the 2 removed) |
| Min short side | 768 | 768 |
| Median short side | ~2000 | ~1900 |

### Gallery + metadata

Everything regenerated: [metadata.csv](../../../../datasets/renoir-flowers/metadata.csv), [captions.txt](../../../../datasets/renoir-flowers/captions.txt), [captions.json](../../../../datasets/renoir-flowers/captions.json), [gallery.html](../../../../datasets/renoir-flowers/gallery.html). 118 cards in the mosaic.

The user's localStorage flags persist in the browser. The 2 removed cards are gone from the dataset (no card renders for them); the 21 review-frame cards still show the amber ring but now display the post-crop images, so Luca can verify the fix and clear the flag (click the ⚐ again to unflag) on each one as he confirms.

Re-flag any remaining issues, click `Export flags JSON`, and we go around again.

### Deliverables (Phase A.7)

- [datasets/renoir-flowers/user-flags-2026-05-17.json](../../../../datasets/renoir-flowers/user-flags-2026-05-17.json) — Luca's exported flags.
- `gemini_review_userflags.py` + `review_userflags.json` — Gemini second-look.
- `apply_user_flag_crops.py` — Gemini-bbox crop driver.
- `manual_crops_user.json` + `apply_manual_crops_user.py` — micro-crops from direct visual inspection.

### Workstream open: waiting for round-2 flags or sign-off.

## 2026-05-17, Phase A.8 — In-browser manual cropper

Confirmed: the gallery does NOT add white borders to images. CSS sets `width: 100%`, `display: block`, no padding, dark `--paper` background. Any white edges visible on a card are real residuals in the underlying JPEG.

Added an interactive manual cropper to [gallery.html](../../../../datasets/renoir-flowers/gallery.html) so Luca can dial crops himself when an automated pass under- or over-cuts.

### Per-card scissors button

Each card now has a third button in the top-right flag bar: `✂` (in addition to `⚐` review-frame and `×` remove). Click it (or press `C` while hovering a card) to open the full-screen cropper modal.

When a card has a saved manual crop bbox, it gets a green 3 px ring (parallel to the amber ring for review-frame).

### Cropper modal

- Full-screen dark backdrop, image rendered at fit-to-viewport size.
- Crop rectangle with rule-of-thirds overlay (dashed gold lines at 1/3 and 2/3 in both axes) and 8 round handles (4 corners + 4 edge midpoints) plus a draggable middle.
- Top bar: filename · live pixel dimensions of the crop (recomputed against the image's natural resolution) · `Reset` (back to 5%/5%/90%/90%) · `Clear saved` (forget the saved bbox for this file) · `Save crop` · `Cancel`.
- Mouse + touch drag supported on the rect and on every handle. Coordinates stored as percentages so they survive image-resolution changes.
- `Esc` closes the modal without saving.

### Storage + export

- Manual crop bboxes persist in `localStorage` under key `renoir-gallery-crops-v1` as `{filename: {x, y, w, h}}` (percentages, 2 decimals).
- The toolbar count `N manual crops` is live.
- `Export flags + crops` (renamed) downloads `gallery-flags.json` now with three sections:

```json
{
  "exported_at": "...",
  "remove": ["..."],
  "review_frame": ["..."],
  "crops": {
    "filename.jpg": {"x": 4.2, "y": 6.1, "w": 91.5, "h": 88.4},
    ...
  },
  "total_remove": N,
  "total_review": N,
  "total_crops": N
}
```

- `Clear all flags` button now also clears saved crops (with confirmation).
- New filter chip in the header: `My: cropped` (green) for quickly reviewing the cards with pending manual crops.

### Apply pipeline

After Luca exports the JSON, I run:

```bash
py -3.11 datasets/renoir-flowers/apply_browser_crops.py
# or pass an explicit path:
py -3.11 datasets/renoir-flowers/apply_browser_crops.py C:/path/to/gallery-flags.json
```

[apply_browser_crops.py](../../../../datasets/renoir-flowers/apply_browser_crops.py):
- Reads `gallery-flags.json` (defaults to `~/Downloads/gallery-flags.json`).
- Validates each bbox: must be inside `[0, 100]` per axis, w and h >= 5 %, and not a no-op full-image crop.
- Backs up the pre-crop version to `raw_orig/` if not already present.
- Applies the crop on the full-resolution image, upscales with LANCZOS if cropped short side falls below 768 px (capped 2x).
- Saves a dated audit archive `user-crops-applied-YYYY-MM-DD.json` next to the dataset.
- Updates [processed.json](../../../../datasets/renoir-flowers/processed.json) with `browser_crop` records per file.

After running it, regenerate metadata + captions + gallery:

```bash
py -3.11 datasets/renoir-flowers/finalize_metadata.py
py -3.11 datasets/renoir-flowers/update_metadata_post_process.py
py -3.11 datasets/renoir-flowers/captions.py
py -3.11 datasets/renoir-flowers/build_gallery.py
```

### Workflow summary

1. Click `✂` on a card (or hover + `C`).
2. Drag corners / edges / middle to the painting boundary.
3. `Save crop`. The card gets a green ring.
4. Repeat across cards.
5. `Export flags + crops`. The JSON downloads.
6. Tell me, I run `apply_browser_crops.py` and regenerate the gallery.

### Deliverables (Phase A.8)

- [datasets/renoir-flowers/build_gallery.py](../../../../datasets/renoir-flowers/build_gallery.py) — gallery generator now emits the cropper modal, scissors button, drag/resize logic, crop localStorage, expanded export, `My: cropped` filter.
- [datasets/renoir-flowers/apply_browser_crops.py](../../../../datasets/renoir-flowers/apply_browser_crops.py) — server-side applier.
- [datasets/renoir-flowers/gallery.html](../../../../datasets/renoir-flowers/gallery.html) — regenerated, ready to use.

## 2026-05-17, Phase A.9 — Rotation in cropper + practice documentation + inpainting research

Three changes.

### Rotation in the cropper

The cropper modal now exposes two new buttons in its top bar:

- `↺` rotate 90° counter-clockwise
- `↻` rotate 90° clockwise

Beside them, a small monospace pill shows the current rotation (`0°`, `90°`, `180°`, `270°`). Clicking either button:

1. Renders the image into an HTML canvas at the new rotation, generates a JPEG data URL, and sets it as the cropper image source. The rotated image fills the cropper stage with the correct aspect ratio.
2. Resets the crop bbox to the default 90 % rectangle (rotation changes the coordinate frame, so the previously-drawn bbox would no longer mean what it did).
3. Updates the live pixel readout in the top bar to reflect the rotated dimensions.

Rotated data URLs are cached in `Map<filename:deg, dataURL>` so repeated rotation toggles or gallery re-renders do not re-decode the source image every time.

When the user saves, the rotation is persisted in `CROPS[filename].rotation` (0, 90, 180, or 270). The gallery card's front face also swaps its `img.src` to the rotated data URL the moment the rotation is saved, so the live preview shows the rotated + cropped image immediately.

The server-side applier [apply_browser_crops.py](../../../../datasets/renoir-flowers/apply_browser_crops.py) handles rotation correctly: `PIL.Image.rotate(-rotation_cw_deg, expand=True, resample=BICUBIC)` before applying the crop. `processed.json` records `rotation_cw_deg` per file.

### Bug fix on the live preview

While adding rotation I had introduced a regression: the async `setSrcAndRun` path was no-op re-setting `img.src` to the same relative URL, which does not fire `load` reliably, so `apply()` ran with `naturalWidth = 0` and bailed silently. Cards showed the full uncropped image despite having a saved crop. Fixed by only swapping `img.src` when the desired source genuinely differs from the current one (rotation 0 keeps the raw URL, rotation != 0 swaps to the data URL).

### Practice documentation

Captured the end-to-end recipe in [docs/findings/dataset-practice.md](../../../findings/dataset-practice.md). The doc covers:

- The shape of a good dataset (counts, resolution, subject dominance, PD status).
- The five-phase recipe: Source → Vision audit + crop → Human-in-the-loop refinement → Caption → Hand-off package. For each phase: the rationale, the tools, the right vocabulary for filters.
- Common failure modes (frame painting, catalogue colour cast, mode collapse) and concrete fixes for each.
- The mid-project decisions we made on the Renoir build (scope expansion, 5-slot captions, browser flag UI, rotation, Gemini false-positives), so the next LoRA build does not re-derive them.
- A file inventory pattern so the next dataset's folder mirrors this one.

This is the canonical document to read before starting any new LoRA dataset.

### Inpainting research

[docs/findings/inpainting-options.md](../../../findings/inpainting-options.md) ranks 11 inpainting solutions for the dataset-cleanup use case (paint a mask, fill with Renoir-style content matching the surrounding pixels), with pros / cons / pricing / API ergonomics for each.

**Headline ranking** for this project's needs:

1. **fal.ai · FLUX.1 [dev] Inpainting with LoRAs** — once the Renoir LoRA exists, this is the answer. Native LoRA loading, $0.035 per megapixel, FLUX's SOTA edge blending. Default tier-1 choice.
2. **fal.ai · FLUX.1 [pro] Fill** — for the pre-Renoir-LoRA window (right now). No LoRA management, $0.05 per megapixel, same FLUX quality. Migrate to (1) after training.
3. **fal.ai · FLUX.1 Krea [dev] Inpainting with LoRAs** — painterly-biased FLUX variant, worth A/B-testing against (1).
4. **Replicate · `sdxl-controlnet-lora-inpaint`** — native SDXL compatibility with the LoRA we train, plus ControlNet for geometry lock. One generation behind FLUX on edge blending.
5. **fal.ai · Juggernaut FLUX LoRA Inpaint** — richer-colour FLUX variant.

Local options (ComfyUI BrushNet, ComfyUI FLUX Fill local) are recommended for the 3 to 5 release-grade paintings where reproducibility and zero per-call cost matter.

The findings doc includes a recommended phasing:
- **Phase 1 (now):** wire FLUX [pro] Fill into the cropper modal as a "paint mask + run inpaint" button.
- **Phase 2 (post-LoRA):** swap endpoint to FLUX [dev] LoRA Inpaint, prompts now lead with `rfl, ...`.
- **Phase 3 (release polish):** local ComfyUI for the canonical paintings.

A gallery integration sketch is included in the doc but not built yet (the cropper alone covers the artefact-at-edge cases; inpainting becomes essential when the artefact is INSIDE the painting).

### Deliverables (Phase A.9)

- Cropper rotation buttons + canvas-based rotation + rotation persisted in localStorage + applied server-side: [build_gallery.py](../../../../datasets/renoir-flowers/build_gallery.py), [apply_browser_crops.py](../../../../datasets/renoir-flowers/apply_browser_crops.py).
- [docs/findings/dataset-practice.md](../../../findings/dataset-practice.md) — the end-to-end recipe for any future LoRA dataset.
- [docs/findings/inpainting-options.md](../../../findings/inpainting-options.md) — ranked inpainting solutions with pros / cons.
- [docs/plans/inpaint-implementation.md](inpaint-plan.md) — implementation plan for the next ship: brush-mask inpainting wired through the cropper into fal.ai FLUX Fill (Phase 1) then FLUX LoRA Inpaint (Phase 2 after the Renoir LoRA returns from CivitAI).
- [gallery.html](../../../../datasets/renoir-flowers/gallery.html) — regenerated with rotation UI + live-preview bug fix.
- [datasets/renoir-flowers/serve.py](../../../../datasets/renoir-flowers/serve.py) — small local HTTP server. Required for canvas-based rotation to work (browsers block canvas readback on file://).

## 2026-05-17, Phase A.10 — Durable state: every save lands on disk

Luca's requirement: crops and rotations must survive browser refreshes, browser cache wipes, origin changes (file:// vs http://localhost:8765), and any future regeneration of `gallery.html`.

Risk we were running: localStorage is scoped to origin. The gallery had been used across both `file://...gallery.html` and `http://localhost:8765/gallery.html` URLs in the same session. Those are separate origins. Saved work on one was invisible from the other. Browser private mode, cache clears, or new browser installs would also drop it entirely.

### What changed

[serve.py](../../../../datasets/renoir-flowers/serve.py) now exposes:

- `GET /api/state` returns the current `gallery-state.json` snapshot.
- `POST /api/state` replaces the snapshot (full).
- `POST /api/state/patch` applies a single per-file change (used for incremental saves if we want them later; not currently used by the frontend).

On disk, in the dataset folder:

- `gallery-state.json` — the source of truth. Atomic-write via tmp+rename. UTF-8 pretty-printed for human readability.
- `gallery-state.log.jsonl` — append-only event log with timestamp + counts per change. Useful for auditing what was changed when, or replaying the entire history.
- `gallery-state.backups/gallery-state-YYYYMMDD-HH.json` — one rotating backup per hour, automatic. Saved me already in testing when I accidentally overwrote the live state with a curl smoke test — I just `curl -X POST -d @backup.json` to restore.

All three are gitignored (added to `datasets/renoir-flowers/.gitignore`).

### Frontend changes ([build_gallery.py](../../../../datasets/renoir-flowers/build_gallery.py))

The browser now does this on every save:

1. Update in-memory `FLAGS` / `CROPS`.
2. Write to `localStorage` (cache + offline fallback).
3. Debounced 300 ms POST `/api/state` with the full payload. The 300 ms debounce groups a flurry of clicks into one HTTP request.

On boot:

1. Load `FLAGS` / `CROPS` from localStorage (instant, no async wait).
2. Call `hydrateFromDisk()`:
   - GET `/api/state`.
   - If disk has any entries → adopt them as source of truth (overwrite localStorage).
   - If disk is empty but localStorage has data → one-shot push the localStorage state up to disk (migration aid for the first time a previously-file:// user opens the gallery via http://localhost). I verified the migration on Luca's real saved crops: the three crops he had saved before this change ended up on disk on first boot of the upgraded server.
   - If both empty → no-op.
3. Re-render all cards with the (possibly disk-overwritten) state.

A small status pill lives next to the counts in the sticky toolbar:

- `SYNCED` (green) — disk-backed, every save written to `gallery-state.json`.
- `SYNC ERROR` (red) — server unreachable since last save. Hover for the underlying error message.
- `LOCAL-ONLY (run serve.py)` (amber) — page loaded via `file://`. localStorage only, no disk persistence. Tooltip explains how to fix.

### What this fixes

- Browser refresh: state loads from disk on every reload, exactly as it was when last saved.
- Browser cache / private mode wipe: localStorage might be lost but disk file is intact. Next boot hydrates from disk.
- Origin change (`file://` ↔ `http://localhost:8765`): doesn't matter. Disk is the source of truth; both origins read the same file (via the server when on http, via localStorage as last-known cache when on file). The migration aid handles the first crossover automatically.
- Regenerating `gallery.html` from `build_gallery.py`: doesn't touch `gallery-state.json`. Reload picks up the same disk state.
- `LS_KEY` constant changing in the code: doesn't matter, disk file uses its own schema (`{flags, crops}`).

### What this does NOT fix

- Server not running: gallery falls back to localStorage. Saved work persists in the browser but won't transfer to other browsers / origins. Always run `py -3.11 datasets/renoir-flowers/serve.py` for durable state.
- Deleting `gallery-state.json` manually: it's gone. The hourly backup directory holds at most 24 to 48 hours of recovery; check `gallery-state.backups/` if it ever needs a manual restore.
- Editing the JSON by hand while the server is running: race-prone. The server holds a process-wide lock on writes but file-level read+modify+write by another process can interleave. Stop the server before manual edits.

### Recovery procedure

If the live state is wrong or got overwritten:

```bash
# pick a backup
ls datasets/renoir-flowers/gallery-state.backups/
# restore via the API
cat datasets/renoir-flowers/gallery-state.backups/gallery-state-YYYYMMDD-HH.json \
  | curl -s -X POST -H "Content-Type: application/json" -d @- \
    http://localhost:8765/api/state
# or copy the file directly (server must be stopped)
cp datasets/renoir-flowers/gallery-state.backups/gallery-state-YYYYMMDD-HH.json \
   datasets/renoir-flowers/gallery-state.json
```

### Smoke test that ran in the build

1. Started `serve.py` fresh.
2. GET `/api/state` returned the 3 crops that had been in Luca's localStorage from earlier sessions, automatically migrated on first boot.
3. POSTed a test payload, GET confirmed the round-trip.
4. Restored the original 3 crops from the hourly backup with `curl -d @backup.json`.

The system is durable across the four most likely failure modes (refresh / cache / origin / rebuild).

## 2026-05-17, Phase A.11 — Immediate removal + undo toast

Behaviour change: the `×` button on a card no longer marks for removal. It removes immediately. The file moves from `raw/` to `rejected/user-removed/` on disk, the card fades out of the mosaic, and a toast at the bottom of the screen offers a 5-second `Undo`.

### Rationale

The previous "mark for removal" state was a queue: nothing happened until the user exported the JSON and I ran an applier. That meant work was deferred and easy to forget. Immediate removal is simpler: click, gone. The `rejected/user-removed/` folder serves as a permanent undo (files are kept indefinitely; the gallery just stops listing them).

### Implementation

Server ([serve.py](../../../../datasets/renoir-flowers/serve.py)):

- `POST /api/remove` accepts `{filename}`. Validates the basename (no path traversal). Moves `raw/<filename>.jpg` to `rejected/user-removed/<filename>.jpg` (suffix-with-timestamp on collision). Drops any flags/crops for that file from `gallery-state.json`. Appends a `remove` event to the log. Returns `{status, moved_to}`.
- `POST /api/restore` accepts `{filename, moved_to}`. Validates the source path is inside `rejected/user-removed/` (no escape). Moves the file back to `raw/`. Refuses if `raw/<filename>` already exists. Appends a `restore` event.

Frontend ([build_gallery.py](../../../../datasets/renoir-flowers/build_gallery.py)):

- `×` button's handler now calls a new `removeCard(card, filename, title)` function: adds a `.removing` class (fade + scale animation), POSTs `/api/remove`, then collapses the card from layout. If the network call fails, it rolls back the animation and surfaces the error.
- An undo toast lives at the bottom of the page (CSS-animated, 5-second progress bar). Clicking `Undo` POSTs `/api/restore` and un-collapses the card.
- The `R` keyboard shortcut now triggers immediate removal too.
- Removed: the "MARKED FOR REMOVAL" card overlay, the `user-remove` CSS class, the `My: remove` filter chip, the `remove-count` toolbar counter, the `remove` array in the exported JSON. None of these are needed any more.

### Toast UX

The toast slides in from below with the painting's title, an `Undo` button, and a 5-second progress bar. Clicking elsewhere doesn't dismiss it; only the timer or the Undo click do.

### What this doesn't change

- `rejected/user-removed/` files are NOT deleted by anything. They live until you delete them manually. The 5-second undo is a convenience; manual restoration is always available via `curl -X POST /api/restore` or `mv` on the command line.
- The frame-review flag (`⚐`) still works the same way: it's a non-destructive bookmark, persisted to `gallery-state.json`, filterable.
- The manual cropper is unchanged.

### Documentation

`docs/gallery-manual-notes.md` (deleted 2026-05-18, content now at `docs/manual/gallery.md`) is now the working draft for a real user manual. Plain-language reference for every button, shortcut, persistence behaviour, and recovery procedure. Section "What changes when" tracks behaviour changes across phases. Will be polished into `docs/manuals/gallery.md` later.

### Deliverables (Phase A.11)

- [datasets/renoir-flowers/serve.py](../../../../datasets/renoir-flowers/serve.py) — new `/api/remove` and `/api/restore` endpoints.
- [datasets/renoir-flowers/build_gallery.py](../../../../datasets/renoir-flowers/build_gallery.py) — `×` rewired, undo toast added, "mark for removal" UI removed.
- `docs/gallery-manual-notes.md` (deleted 2026-05-18, content now at `docs/manual/gallery.md`) — user-manual working draft.
- [datasets/renoir-flowers/gallery.html](../../../../datasets/renoir-flowers/gallery.html) — regenerated.

## 2026-05-17, Phase A.12 — Perceptual-hash duplicate clustering in the gallery

Luca noticed near-duplicate images in the dataset and asked for them to land adjacent in the gallery as a native ordering, not a separate feature, so they are trivial to spot and trim.

### How it works

[build_gallery.py](../../../../datasets/renoir-flowers/build_gallery.py) now runs three new steps before emitting `gallery.html`:

1. **`compute_phashes(filenames)`** — calls `imagehash.phash(im)` on each JPEG in `raw/`. Results cached to [phashes.json](../../../../datasets/renoir-flowers/phashes.json) keyed by `(file size, mtime)`. Re-runs of `build_gallery.py` are near-instant unless the underlying bytes changed.
2. **`cluster_order(filenames, phashes)`** — union-find pass: any two files with Hamming distance `<= DUP_THRESHOLD` (currently 10, matching `dedup.py`) are merged into a cluster. Within each cluster, members are sorted alphabetically. Clusters are sorted by their first member's filename. The overall ordering looks like the alphabetical default with near-duplicates pulled together.
3. **Emit `CARDS` in cluster order**, passing `cluster_id` and `cluster_size` into each card record.

The gallery JS reads `cluster_size`: cards in clusters of size >= 2 get an amber `dup N` pill in the top-left badge bar. The last card in each multi-member cluster gets a small extra bottom margin (`data-cluster-end="1"` CSS rule) so the visual flow visibly groups them.

### Result on the current dataset

```
phash: 114 files (114 (re)computed)
clusters: 110 total, 4 with >1 member, 4 potential duplicates
```

The 4 near-duplicate pairs found:

| Cluster | Files |
|---|---|
| 1 | `auguste-renoir-picking-flowers-1875-nga-52205.jpg`, `pierre-auguste-renoir-la-cueillette-des-fleurs.jpg` |
| 14 | `pierre-auguste-renoir-anemones-15462545083.jpg`, `renoir-an-mones-22-by-29-cm.jpg` |
| 22 | `pierre-auguste-renoir-bouquet-de-roses-01.jpg`, `renoir-bouquet-de-roses-rf-1948-14.jpg` |
| 24 | `pierre-auguste-renoir-bouquet-in-un-vaso-1878.jpg`, `renoir-pierre-auguste-bouquet-in-a-vase-google-art-project.jpg` |

These are the survivors the original `dedup.py` perceptual-hash dedup pass missed because either the threshold was tighter at the time or because we sourced one half later in Phase A.6 (after the initial dedup run). With them now placed side-by-side in the gallery, you can flip both, pick the higher-resolution / cleaner version, and `×`-remove the other in one click.

### Bonus fix in the same change

`build_gallery.py` previously read filenames from `metadata.csv` and assumed they all existed in `raw/`. After Phase A.11's immediate-remove behaviour, `raw/` lags `metadata.csv` whenever the user removes a card without rerunning `update_metadata_post_process.py`. Cards for removed files would render with broken images.

Fixed by adding a filesystem cross-check: `meta = {fn: m for fn, m in meta.items() if (RAW / fn).exists()}`. Stale rows are skipped with a one-line warning at build time, so metadata.csv can lag the actual files indefinitely without breaking the gallery. The applier scripts (`apply_browser_crops.py`, `finalize_metadata.py`) handle catching metadata up when desired.

### Tuning

`DUP_THRESHOLD = 10` at the top of `build_gallery.py`. Lower (4-6) for strict identity; raise (12-16) to cluster cousin paintings together (e.g., the two Renoir "Spring Bouquet" versions which share composition but differ in palette).

### Deliverables (Phase A.12)

- [datasets/renoir-flowers/build_gallery.py](../../../../datasets/renoir-flowers/build_gallery.py) — perceptual-hash compute, union-find clustering, cluster-ordered card emission, filesystem cross-check.
- [datasets/renoir-flowers/phashes.json](../../../../datasets/renoir-flowers/phashes.json) — pHash cache, gitignored.
- `docs/gallery-manual-notes.md` (deleted 2026-05-18, content now at `docs/manual/gallery.md`) — new "Card ordering" section + updated badges table.

## 2026-05-17, Phase A.13 — One-command workflow + escape hatches for file:// and SYNC ERROR

Luca got LOCAL-ONLY again because the gallery file was opened via `file://` instead of `http://localhost:8765`. Two-part fix:

### One command does everything

`py -3.11 datasets/renoir-flowers/serve.py` now also rebuilds `gallery.html` before starting the HTTP server. That folds three previously-separate steps into one: build → serve → open. The user only ever needs that one command. Side effects:

- Pure-serve mode is still available via `--no-build` for the cases where you want to test changes to `gallery.html` directly without re-emitting it.
- The rebuild runs as a subprocess with a 120-second timeout; failures (missing deps, missing metadata) are non-fatal — the server starts with whatever `gallery.html` is already on disk.
- Build output is echoed inline (cluster counts, skipped stale rows, etc.) so the user sees the same info they'd see running `build_gallery.py` alone.

### `file://` banner is now active

The amber banner at the top of the page does a server-availability probe via `fetch(..., {mode: "no-cors"})` on `http://localhost:8765/api/state` with a 1.2-second timeout:

- **Server alive:** banner shows a green **"Switch to synced version →"** button. Click it; the tab navigates to the synced URL. One click to recover from any accidental `file://` open.
- **Server dead:** banner shows the `run serve.py` command and a **"Re-check"** button. Start the server in a terminal, click Re-check, the green button appears.

No more "I have to look up the URL, type it into the address bar, and reload."

### Reconnect button for mid-session SYNC ERROR

If the badge ever goes red because the server died (Ctrl-C, sleep, port collision), a red **"Reconnect"** button appears next to it. Click it to re-hydrate from disk and flush any pending in-memory state to the server.

### Why this is the permanent solution

The three failure modes are:
1. **`file://` open by mistake** — handled by the active banner with the green redirect button.
2. **Server not running** — handled by the banner's "Re-check" + the one-command workflow that auto-builds + auto-opens the right URL.
3. **Server dies mid-session** — handled by the Reconnect button next to the SYNC ERROR badge.

Together: there is no path through the UI where the user can lose work to a wrong-protocol or stale-state issue without the gallery actively pointing at the fix.

### Deliverables (Phase A.13)

- [datasets/renoir-flowers/serve.py](../../../../datasets/renoir-flowers/serve.py) — rebuilds `gallery.html` on startup; supports `--no-build`; threaded handler with `SO_REUSEADDR` (carried over from the earlier hang fix).
- [datasets/renoir-flowers/build_gallery.py](../../../../datasets/renoir-flowers/build_gallery.py) — active `file://` banner with server probe + "Switch to synced version" button + "Re-check" button; "Reconnect" button next to SYNC ERROR badge.
- `docs/gallery-manual-notes.md` (deleted 2026-05-18, content now at `docs/manual/gallery.md`) — refreshed "Start it up" section + new escape-hatch sections, new entry in "What changes when".

## 2026-05-17, Phase A.14 — Cropping pass complete + LoRA-training deep-dive doc

Luca completed the cropping work in the gallery. The dataset is now free of physical frames, white paper borders, and watermarks (subject to one final visual pass before training).

To prepare for training, wrote [docs/findings/lora-training-deep-dive.md](../../../findings/lora-training-deep-dive.md). This is the in-depth companion to the existing Renoir-specific playbook at [docs/findings/lora-training.md](../../../findings/lora-training.md). 9 sections covering:

1. **What a LoRA actually does to SDXL** — low-rank perturbation, why text-encoder is usually frozen, how LoRAs stack, why the base model is still the floor.
2. **Four LoRA objectives** — style, subject, character, concept. Each has characteristic dataset, captioning, and hyperparameter signatures; almost every later decision flows from this choice. The Renoir LoRA is a style LoRA; Casa del Suono was a subject+style hybrid (which explains its off-distribution erratic behaviour).
3. **Dataset curation, by objective** — what to put IN per objective. Style needs subject diversity; subject needs angle / lighting / distance diversity; character needs identity-cue diversity; concept needs compositional diversity.
4. **Captioning, by objective** — the counter-intuitive rule (describe everything except what you want the LoRA to memorise) and how it specialises per objective. Includes the trigger / suffix discipline we use.
5. **Hyperparameters that actually matter** — six knobs: network rank, alpha, learning rate, text-encoder LR, batch+repeats, epochs+saves. Concrete numbers per objective.
6. **Training tools beyond CivitAI** — comparison of kohya_ss + sd-scripts (the reference implementation, hands-on tool we'd use next), OneTrainer (cleaner UI, good first step beyond CivitAI), Ostris AI Toolkit (FLUX-first), Replicate / fal.ai (cloud-with-control). Recommendation: kohya_ss locally if the first CivitAI Renoir run is unsatisfactory.
7. **Validation protocol** — pick 5 hold-outs by role, render 30 grid images per training run, score subjectively, save the grading. Becomes invaluable for the next LoRA in the series.
8. **Failure modes and their diagnostics** — 10-row table from our experience: frame-painting tendency, auction-catalogue colour cast, cross-domain disappearance, over-painting collapse, trigger-word failure, blurry outputs (LR too high), under-fit (LR too low), identity drift (character), captions-instead-of-pixels (text encoder accidentally trained), validation/real-prompt gap.
9. **Concrete cheat-sheet recipes per objective** — full kohya_ss config snippets for style, subject, character, concept SDXL LoRAs.

Plus a Further Reading section with 6 canonical references and inline sources.

### How to use the docs together

| You want to | Read |
|---|---|
| Train the Renoir LoRA on CivitAI right now | [lora-training.md](../../../findings/lora-training.md) — push-button recipe, copy the settings. |
| Build the next dataset (Cézanne, Bonnard, etc.) | [dataset-practice.md](../../../findings/dataset-practice.md) — the five-phase recipe with the script-naming convention. |
| Understand why a parameter is the value it is | [lora-training-deep-dive.md](../../../findings/lora-training-deep-dive.md) — the theory + objective-specific recipes. |
| Train a LoRA that's NOT a style LoRA (e.g. a character LoRA of a specific person) | [lora-training-deep-dive.md](../../../findings/lora-training-deep-dive.md) §2 §3 §4 §9 — the cheat sheets are objective-specific. |
| Use kohya_ss locally instead of CivitAI | [lora-training-deep-dive.md](../../../findings/lora-training-deep-dive.md) §6 + the §9 cheat sheet for the relevant objective. |
| Diagnose a LoRA that came out wrong | [lora-training-deep-dive.md](../../../findings/lora-training-deep-dive.md) §8 (failure modes table). |

### What's next for the actual training

1. Run `package_for_civitai.py` on the now-cropped dataset to build the ZIP.
2. Upload to CivitAI, configure per [lora-training.md](../../../findings/lora-training.md) §3.
3. Validate per [lora-training-deep-dive.md](../../../findings/lora-training-deep-dive.md) §7 — 30-image validation grid, scored, written down.
4. If the result is good: copy to `models/loras/`, notify parent chat for inference work.
5. If the result is unsatisfactory: switch to kohya_ss locally per the deep-dive §6 recommendation, retrain with adjusted hyperparameters.

### Deliverables (Phase A.14)

- [docs/findings/lora-training-deep-dive.md](../../../findings/lora-training-deep-dive.md) — the new theory + tools + recipes doc.
- [docs/findings/lora-training.md](../../../findings/lora-training.md) — header updated with a pointer to the deep-dive.
- [docs/findings/dataset-practice.md](../../../findings/dataset-practice.md) — companion-docs list updated with the deep-dive reference.


