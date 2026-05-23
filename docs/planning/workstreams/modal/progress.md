# Phase 3.5 Modal infrastructure progress

Pre-curation flush completed 2026-05-19 [mode B].

Status log for the parallel chat building the OPTIONAL Modal.com deployment
of the `slow-interpolation` pipeline. The parent chat owns the master log
at `docs/planning/progress.md`; this doc is the integration surface for this
workstream.

## Coordination requests, 2026-05-19 flush

Items where new knowledge from this workstream needs to land outside the workstream's write zone (`cloud/*`, `docs/modal.md`, `tests/test_modal_*.py`). Parent chat decides routing.

### CR-H: add a fourth brainstorm entry to `docs/planning/workstreams/alt-techniques/brainstorm.md`

The 2026-05-19 LoRA-loaded probe surfaced a new alt-technique candidate that does not fit any of the three existing entries. Proposed entry title: **"4. SDXL base backbone for the video pipeline (no Lightning distillation)"**. Framing:

- **What.** Replace SDXL Lightning 4-step distillation in `keyframes.py` with SDXL base at 30 steps, guidance 7.5, on top of the existing img2img chain + temporal smoother + RIFE 64x scaffolding. Keep the Renoir + Soutine LoRAs unchanged.
- **Why test.** Two probes (2026-05-18 naked + 2026-05-19 LoRA-loaded) show SDXL base reads visibly stronger on painterly brushwork than SDXL Lightning at the keyframe level, both naked and with the Renoir LoRA applied. The LoRA does not fully compensate. The keyframe-level gain is real; whether it survives the temporal smoother + RIFE is unknown.
- **Cost.** Plumbing change in `src/` (~30 lines, optional `lightning_lora`, threaded inference params). One short-clip test on Modal (~0.10 to 0.25 USD). If it earns a workstream, full release-scale cost ripples to ~12 USD instead of ~1.75 USD for the 25-piece compositing release, plus a denoise-schedule rerun on a parallel `steady_strengths_base` profile and a Renoir + Soutine validation-grid rerun under base inference.
- **Comparison render.** One 15 to 30s loop on the existing Renoir flower-field config, Lightning disabled, halved denoise schedule (start at 0.30 steady, 0.40 transition). Watch keyframes, then Phase A.5 output, then final RIFE output, in that order.
- **What would earn it a promotion.** Brushwork visible in keyframes survives Phase A.5 AND survives RIFE 64x in the final clip. Both gates.
- **What would kill it.** Temporal smoother flattens the brushwork (the impasto is high-frequency texture; the smoother's center-frame-high-freq behavior may or may not preserve it across drift), OR RIFE smears the brushstrokes across in-between frames at 64x. Either failure means the keyframe-level gain does not translate to video.
- **Timing.** Pre-release exploration territory. The current production pipeline ships the Renoir release on Lightning. This direction is a v2 question for future releases unless the test wins decisively, in which case it becomes a release-blocking reconsideration before the 25-piece compositing render.

Full source detail in this progress.md log entry "2026-05-19 (LoRA-loaded follow-up probe, ...)". The brainstorm entry can be terser than that; the log here is the canonical reference.

### CR-I: consider whether the SDXL-base-on-video direction earns its own workstream folder

Does this direction need a `docs/planning/workstreams/sdxl-base-backbone/` folder with a `brainstorm.md` and (later) `design.md`, or does it stay parked as the 4th entry in alt-techniques until evidence justifies a promotion? Recommendation: **stay in alt-techniques until the one-clip test runs.** Spinning a new workstream pre-evidence is premature; the alt-techniques brainstorm pattern is exactly designed to hold candidates like this until a comparison render decides. Promote on a Luca approval of the comparison clip, not before.

### CR-J: src/ plumbing change for the SDXL-base video test

To run the one-clip comparison test, three small src/ edits are needed in the parent chat's zone:

1. `src/slow_interpolation/config.py:32-33` ModelsConfig: change `lightning_lora` and `lightning_weight_name` to `Optional[str] = None`. None means "do not load Lightning".
2. `src/slow_interpolation/keyframes.py:50-52` in `load_sdxl_pipeline()`: skip the Lightning load + fuse if `m.lightning_lora is None`. Skip the scheduler swap to EulerDiscrete trailing-timesteps if Lightning is skipped (the base SDXL scheduler is the right default).
3. `src/slow_interpolation/keyframes.py:146-147` in `generate_keyframes()`: replace function defaults `guidance_scale=1.5, num_inference_steps=4` with values pulled from `config.render`. New fields on `RenderProfile`: `guidance_scale: float = 1.5`, `num_inference_steps: int = 4`. Defaults preserve current behavior; an SDXL-base YAML overrides them to 7.5 + 30.

Total: ~30 lines, no breaking changes to existing YAMLs (all defaults preserve Lightning behavior). Test config the Modal chat will author once src/ lands: `examples/configs/sdxl_base_probe/renoir_field_30s.yaml`.

Recommendation: parent chat lands these three edits in a single small commit after the alt-techniques brainstorm entry (CR-H) is in. Modal chat then dispatches the test render on next session.

### CR-K: quirk #10 added to `docs/findings/modal-sdk-quirks.md`

Modal Secret deploy-time validation gotcha landed in this flush. Just signalling the edit; parent chat may want to surface it in the next docs-curator pass.

### CR-L: new finding `docs/findings/hf-model-gate-drift.md`

Created in this flush. Small (one case so far: FLUX.1-schnell). May grow into a generic "vendor model-access drift" finding if other cases surface. Flag for curator-pass classification.

### CR-M: contact sheet HTML pattern, candidate for future `docs/manual/`

The two probes both shipped a small `contact_sheet.html` viewer (5-col and 2-col variants) alongside the rendered PNGs. The pattern is reusable for any future side-by-side validation render. NOT a coordination ask now; flagging as a future manual-page candidate for the curator. Pattern lives at `outputs/validation/painterly-backbone-probe/contact_sheet.html` and `outputs/validation/renoir-lora-lightning-vs-base/contact_sheet.html`. Reusable spec: dark serif theme, 1-row-per-prompt grid, click-to-zoom overlay, missing-tile graceful degradation, footer with acceptance criteria. Promote to `docs/manual/contact-sheet-viewer.md` if the pattern gets reused beyond these two probes.


> D2 migration completed 2026-05-18. This doc lives at
> `docs/planning/workstreams/modal/progress.md`; previous location was
> `docs/modal-progress.md`. Naming convention per
> [`docs-strategy.md`](../../docs-strategy.md). See the 2026-05-18
> entry under "## Log" below for the migration record.

**WORKSTREAM STATUS: SHIPPED 2026-05-17.** Infrastructure works, cold-run
passed, visual inspection of the rendered MP4 passed. Ready for use by
the Renoir release. See "Next research steps" at the bottom of this doc
for follow-on suggestions.

> ## PARENT-CHAT NOTICE: T1#2 (Renoir border probe) CANCELLED (2026-05-18)
>
> Luca empirical call after reviewing the first 60s flower-field clip (`outputs/renoir_wildflower_field.mp4`, epoch 1 + scale 0.85 + edge_crop 0): no border-arch artefacts observed across keyframes or interpolated frames. The historical border-arch problem was Casa-del-Suono-LoRA-specific (fresco lunette training data with hard architectural framing). The Renoir LoRA training set has no framed paintings, so the failure mode does not transfer.
>
> T1#2 "Renoir variant-shipping dry-run + border probe" is cancelled as a border probe. The variant-shipping dry-run aspect can still be picked up later as a release-batch dress rehearsal, but it is no longer release-blocking. `docs/findings/border-crop.md` "Caveats" section updated to record the resolution.

## Status at a glance

| Milestone | Status |
|---|---|
| `cloud/` subpackage skeleton (see naming note below) | Done |
| `[cloud]` extra in pyproject | Done |
| Documentation in `docs/modal.md` (incl. variant recipe) | Done |
| First cold-run against `tcole_valley.yaml` | **Done 2026-05-17. 121.4 s wall, 0.07 USD on L40S.** |
| `docs/modal.md` ready for fresh-eyes read | Done |
| Cost ceiling verified (< 5 USD per 60s loop) | **Done. 0.07 USD per 60s loop, 70x under ceiling.** |
| Visual inspection of Modal-rendered MP4 | **Done 2026-05-17. PASSED.** |

## Design summary

- **Opt-in**: `modal/` is a sibling sub-package, NOT imported by
  `src/slow_interpolation/`. Users who never run Modal install the base
  package, never pull the `modal` SDK, and never see Modal artifacts.
- **Variant-friendly**: the Modal entrypoint resolves a `pipeline_entry`
  string (default `slow_interpolation.pipeline:Pipeline`) and a
  `config_loader` string (default
  `slow_interpolation.config:load_pipeline_config`) via `importlib`. A
  branch, fork, or alternate Pipeline class slots in by changing two
  strings, no Modal code changes required.
- **Image build**: the local repo source tree is mounted at deploy time
  via `Image.add_local_dir` for `src/`, `vendor/rife_v425/`,
  `examples/configs/`, and the `modal/` package itself. LoRA weights live
  on a Modal Volume (218 MB each, user-provided); they are NOT baked into
  the image.
- **Storage**:
  - `slow-interp-loras` volume: LoRA `.safetensors` files. Mounted at
    `/root/slow-interpolation/models/loras/`. Populated once by
    `modal run cloud/upload_weights.py`.
  - `slow-interp-hf-cache` volume: HuggingFace cache (SDXL base, Lightning
    LoRA, TAESD). Mounted at `/root/.cache/huggingface/`. Populated on
    first render and reused afterwards.
  - `slow-interp-outputs` volume: rendered MP4s + run manifests. Mounted
    at `/root/slow-interpolation/outputs/`. Downloaded via
    `modal volume get slow-interp-outputs <path>`.
- **Reproducibility**: every render emits a `<output_name>.manifest.json`
  next to the MP4 with the resolved config YAML, git commit, entry-point
  strings, model IDs, GPU tier, per-phase wall time, total cost in USD.
- **GPU tier**: configurable via the `modal:` YAML section. Defaults to
  `L40S` for the 1344x768 SDXL Lightning workload (sufficient and cheaper
  than A100 40GB). Future heavier work opts up to `A100-40GB` or `H100`.

## Coordination notes for the parent chat

- WRITTEN by this chat so far: `cloud/__init__.py`, `cloud/app.py`,
  `cloud/entrypoint.py`, `cloud/upload_weights.py`, `cloud/manifest.py`,
  `cloud/README.md`, `docs/modal.md`, this doc, `pyproject.toml` (added
  `[cloud]` extra only, no other edits).
- **Naming note**: the kickoff brief suggested `modal/` as the package
  directory. We deviated to `cloud/` to avoid shadowing the `modal`
  Python SDK on sys.path. Python puts CWD on sys.path when running
  scripts, so a local `modal/__init__.py` would intercept `import modal`
  inside the entrypoint file and break the SDK import. `cloud/` is
  conflict-free and reads as "the cloud path" (vs. local), which matches
  the opt-in framing. The brief explicitly permits this kind of
  adaptation.
- READ but not edited: `src/slow_interpolation/*`, `docs/pipeline.md`,
  `docs/dependencies.md`, `docs/inventory.md`, `docs/progress.md`,
  `docs/findings/border-crop.md`, `vendor/*`, `examples/configs/*`.
- No extensions to `src/slow_interpolation/` were required. The existing
  `Pipeline` + `PipelineConfig` + `load_pipeline_config` surface is
  sufficient. The Modal entrypoint instantiates the class, calls
  `.render()`, captures the output path.
- No changes to existing YAML configs. The optional `modal:` top-level
  section (GPU tier, entry-point overrides) is parsed only by the Modal
  entrypoint; `load_pipeline_config` ignores it (it only consumes the
  known top-level keys).

## Cross-references

- **Modal SDK quirks compendium**: [`../../../findings/modal-sdk-quirks.md`](../../../findings/modal-sdk-quirks.md). The nine load-bearing Modal-SDK-1.4.x behaviours discovered while building this workstream + the trainer, with code patterns and discovery costs. Read before any non-trivial Modal SDK upgrade.

## Log

### 2026-05-18 (evening, backbone-probe harness)

- Shipped `cloud/validate_backbone.py` + `examples/configs/validation/painterly_backbone.yaml`. Family-agnostic backbone capability probe driven by Luca's sanity-check on the FLUX-alternative entry in the alt-techniques workstream (private during v0.1; section 1). Renders one prompt set across four backbones, no LoRA on any of them: `sdxl_lightning` (current production, naked), `sdxl_base` (SDXL family ceiling at 30 steps), `flux_schnell` (Apache 2.0, 4-step, ungated, harness smoke-test), `flux_dev` (gated 12B, the actual best-case capability read).
- Design: sibling of `cloud/validate_lora.py`, its own image (adds `sentencepiece` + `protobuf` for FLUX T5 tokenizer, bumps diffusers floor to >=0.31), its own Modal app `slow-interpolation-validate-backbone`, shares the `slow-interp-outputs` and `slow-interp-hf-cache` volumes. Single GPU tier (L40S 48GB; FLUX.1 [dev] bf16 peaks ~32GB, fits with headroom).
- Five prompts, no trigger words, descriptive style guidance only: P1 Renoir floral, P2 Soutine figure, P3 Cole landscape, P4 impasto sunflower stress test, P5 compound prompt-adherence (count + placement + colours). Seed 42 across all backbones; FLUX and SDXL do NOT produce visually similar outputs at the same seed (different latent geometry) but each backbone is self-consistent.
- HuggingFace gating handled defensively: the function attaches `modal.Secret.from_name("huggingface")` only if that secret exists. Without it, `flux_schnell` + both SDXL backbones still work; `flux_dev` fails clearly with HF's gated-repo error message. Luca's setup step for flux_dev: accept license at https://huggingface.co/black-forest-labs/FLUX.1-dev, then `modal secret create huggingface HF_TOKEN=<token>`.
- Run protocol (one backbone per invocation; the GPU loads one pipeline at a time):
  ```
  modal run -m cloud.validate_backbone --config examples/configs/validation/painterly_backbone.yaml --backbone sdxl_lightning
  modal run -m cloud.validate_backbone --config examples/configs/validation/painterly_backbone.yaml --backbone sdxl_base
  modal run -m cloud.validate_backbone --config examples/configs/validation/painterly_backbone.yaml --backbone flux_schnell
  modal run -m cloud.validate_backbone --config examples/configs/validation/painterly_backbone.yaml --backbone flux_dev
  ```
- Cost expectations (L40S at ~1.95 USD/hr, 5 prompts each, 1024x1024):
  - sdxl_lightning: 4 steps, ~3s/render -> ~15s active + ~30s cold start, ~0.02 USD.
  - sdxl_base: 30 steps, ~10s/render -> ~50s active, ~0.04 USD.
  - flux_schnell: 4 steps, ~5s/render after first download (T5 cache ~10GB), ~0.05 USD warm + first-run download (~2 min, ~0.06 USD extra).
  - flux_dev: 28 steps, ~15 to 20s/render, ~0.08 USD warm + first-run download (~2 min, ~0.06 USD extra).
  - Full four-backbone contact sheet: **~0.30 to 0.40 USD first run, ~0.20 USD subsequent runs.**
- Output layout: `outputs/validation/painterly-backbone-probe/<backbone>/<slug>.png` plus `_manifest.json` per backbone. Comparison is post-hoc by browsing the volume (download with `modal volume get slow-interp-outputs validation/painterly-backbone-probe outputs/validation/`).
- Acceptance for the alt-techniques workstream: visual side-by-side read by Luca. If FLUX [dev] surface is visibly stronger than SDXL family on P1 + P2 + P4 AND prompt adherence on P5 is visibly better, that earns the FLUX retrain a real workstream design doc. If not, FLUX is closed as v2-territory and the brainstorm entry gets a "tested, rejected" footer.

### 2026-05-19 (LoRA-loaded follow-up probe, SDXL-base-on-video direction surfaced)

Triggered by Luca's verdict on the 2026-05-18 backbone probe: **"SDXL base is the one that gave the most interesting results in terms of paint brush strokes, in the others is pretty much not present."** FLUX retrain rejected (verdict captured in the alt-techniques workstream, private during v0.1). New question opened: is SDXL Lightning (the production backbone) bottlenecking the Renoir LoRA's brushwork? Built a second probe to isolate Lightning vs base AT THE KEYFRAME LEVEL with the Renoir LoRA loaded; then surfaced the larger question of whether to test SDXL base on the actual video pipeline (Phase A keyframe generation), which has NEVER been done in this codebase or its legacy ancestors.

**Shipped (Modal workstream code + configs + manifests):**

1. **`cloud/validate_backbone.py` extended to load an optional domain LoRA per backbone.** New helper `_fuse_optional_lora(pipe, bcfg)` accepts a `lora.filename` + `lora.scale` from the YAML, loads from the `slow-interp-loras` Modal volume, fuses + unloads, falls back to UNet-only on IndexError (Kohya text-encoder mismatch, pattern reused from `cloud/validate_lora.py`). The loras volume is now mounted into `validate_backbone`'s VOLUMES dict. Manifest gains a `domain_loras: list[dict]` field with filename, scale, fallback_used.
2. **`examples/configs/validation/renoir_lora_lightning_vs_base.yaml`** with same five painterly prompts as the parent probe but prepended with the `rfl` trigger, Renoir LoRA epoch 10 at scale 0.85, both `sdxl_lightning` and `sdxl_base` backbones loading the LoRA at their respective inference regimes.
3. **Cold-run executed on Modal.** Both backbones rendered cleanly:

   | Backbone | Wall | Cost | Per-prompt warm |
   |---|---|---|---|
   | sdxl_lightning + Renoir | 33.0s | 0.018 USD | ~0.8s (4 steps) |
   | sdxl_base + Renoir | 34.5s | 0.019 USD | ~4.1s (30 steps) |
   | **Total** | **67.5s** | **~0.04 USD** | |

   The wall-time near-parity is misleading at this scale (single image, tens of seconds either way). At video-pipeline scale (200 keyframes per 60s loop), the ratio matters: Lightning loops cost ~0.07 USD on L40S today; an SDXL-base equivalent would cost ~0.50 USD (7x compute step) and run ~2.5 hours wall vs ~20 min.
4. **Contact sheet built ahead of download** at `outputs/validation/renoir-lora-lightning-vs-base/contact_sheet.html`. 5 rows (prompts), 2 columns (backbones), click-to-zoom. Cross-links the [naked-backbone probe](../../../../outputs/validation/painterly-backbone-probe/contact_sheet.html) so the no-LoRA baseline is one click away.

**Luca's verdict on the LoRA-loaded probe (2026-05-19):** "sdxl base reads more the painting brush". The Renoir LoRA does NOT fully compensate for Lightning's 4-step smoothing of brushwork. The keyframe-level finding from the naked probe (Lightning loses brushwork without LoRA) survives once the LoRA is applied.

**The bigger question surfaced:** Luca asked whether SDXL base has ever been tested on the actual video interpolation pipeline. Answer: **No, never.** Concrete evidence:

- [`src/slow_interpolation/keyframes.py:50-52`](../../../../src/slow_interpolation/keyframes.py#L50-L52) loads and fuses the Lightning 4-step LoRA unconditionally inside `load_sdxl_pipeline()`. No flag to skip.
- [`src/slow_interpolation/keyframes.py:146-147`](../../../../src/slow_interpolation/keyframes.py#L146-L147) defaults `guidance_scale=1.5` + `num_inference_steps=4` are baked to Lightning's distillation regime.
- [`src/slow_interpolation/config.py:32-33`](../../../../src/slow_interpolation/config.py#L32-L33) `ModelsConfig` carries `lightning_lora` + `lightning_weight_name` as non-optional strings.
- Every sample MP4 under `examples/outputs/` was rendered through this stack (Choire fresco, After Cole landscape, Renoir flower-field).
- Grep across `src/`, `legacy/`, and `examples/outputs/` for variants of "no lightning", "disable lightning", "sdxl base", "30 step" returns zero hits in production code paths.

**Cost / risk analysis for a video-pipeline SDXL-base test:**

- Plumbing: `lightning_lora` made Optional (None = skip), `guidance_scale` + `num_inference_steps` threaded through `PipelineConfig.render` instead of function defaults. ~30 lines, src/ work outside this chat's zone.
- Denoise schedule risk: the production `steady_strengths` (0.55 to 0.65) and `transition_strength` (0.65) were tuned for Lightning's 4-step regime. At 30 steps the effective denoise per call (steps × strength) is ~5 to 7x higher, so the schedule likely over-cooks. Likely needs a parallel `steady_strengths_base` profile, calibrated on a short clip. Starting guess: halve everything (0.30 steady, 0.40 transition).
- Validation-grid ripple: the Renoir LoRA validation grid (`docs/planning/workstreams/renoir-dataset/validation-grid.md`) and the Soutine grid scaffold are Lightning-only. Per-epoch headlines (Renoir epoch 1 for fields, epoch 10 for bouquets) may flip under base inference. Switching backbones means rerunning both grids.
- Cost at release scale: 25-piece compositing release at 60s each. Current Lightning: ~1.75 USD total. SDXL-base equivalent: ~12 USD total. Both well under any meaningful budget; the larger concern is wall time (~60 GPU-hours sequential, or parallel fan-out via `cloud/release_batch.py`).

**Recommended next test (NOT executed in this session, awaiting Luca's go):** one minimum-scope SDXL-base video clip. 15 to 30 seconds, existing Renoir flower-field config, Lightning disabled, halved denoise schedule, on Modal L40S. ~0.10 to 0.25 USD. Watch three things:

1. Phase A keyframes preserve the brushwork seen in the contact sheet column Luca approved.
2. Phase A.5 temporal smoother (low-freq blended across 8 frames at sigma 1.5, high-freq from center) does not flatten the gained surface.
3. Phase C RIFE 64x linear does not smear the brushstrokes across in-between frames.

If all three hold, this earns a real workstream (proposed name `sdxl-base-backbone`). If the temporal smoother or RIFE kill the keyframe-level gain at the video level, the production pipeline stays on Lightning and the answer is parked.

**Coordination requests filed** (CR-H, CR-I, CR-J): see the "Coordination requests, 2026-05-19 flush" section below.

**Two implementation patterns crystallised on the way to today's probe**, landed in flush-time finding edits:

1. `modal.Secret.from_name(...)` references are validated at app-deploy time, not at function-call time. A try/except at module level cannot catch a missing-secret error. Captured as quirk #10 in [`docs/findings/modal-sdk-quirks.md`](../../../findings/modal-sdk-quirks.md).
2. HF-model gate-status drift: FLUX.1-schnell was reclassified gated on the HuggingFace Hub between 2024 and 2026-05. Captured as a new finding [`docs/findings/hf-model-gate-drift.md`](../../../findings/hf-model-gate-drift.md).

### 2026-05-18 (evening, backbone-probe COLD-RUN executed)

- Cold-run completed for all four backbones. Cost ~0.26 USD total on L40S, well under the 5 USD ceiling.
- Two implementation bugs found and fixed during bring-up:
  1. **Modal secret references are validated at app-deploy time, not at function call.** The original `try: modal.Secret.from_name("huggingface") except NotFoundError` block at module level could not catch the eager validation; even sdxl_lightning failed when no `huggingface` secret existed in the workspace. Fix: dropped Modal secret mechanism entirely, accept HF token as a function kwarg, read locally from env or `~/.cache/huggingface/token` via a new `_read_local_hf_token()` helper. Only `flux_schnell` and `flux_dev` need a token.
  2. **FLUX.1-schnell has been reclassified gated on HuggingFace** as of ~2026-05. Historically Apache 2.0 / ungated; anonymous requests now return 401 GatedRepoError. Token-forwarding (originally scoped to flux_dev only) extended to both FLUX backbones.
- Both bugs documented as candidates for [`../../../findings/modal-sdk-quirks.md`](../../../findings/modal-sdk-quirks.md) update (Modal-side) and a new HF-side note (HuggingFace gate-status drift across model releases). Not landed yet; flagged for next docs-curator pass.
- **Measured per-backbone wall and cost** (L40S, 1.95 USD/hr, 5 prompts at 1024x1024):

  | Backbone | Wall | Cost | Notes |
  |---|---|---|---|
  | sdxl_lightning | 32.2s | 0.017 USD | Cold start ~25s + 5 prompts at ~0.9s each |
  | sdxl_base | 39.1s | 0.021 USD | 30 steps, ~4s per render warm |
  | flux_schnell | 163.9s | 0.089 USD | First run: T5-XXL + FLUX-schnell weights download (~10GB + 12GB), warm renders ~2.5s each |
  | flux_dev | 251.7s | 0.136 USD | FLUX-dev weights download (~12GB more), warm renders ~15s each (28 steps vs schnell's 4) |
  | **Total** | **487s (~8 min)** | **~0.26 USD** | First-run cost; subsequent runs ~0.08 USD warm |

- Cold-run validates the harness end to end. All 20 PNGs + 4 manifests landed on the `slow-interp-outputs` volume and were downloaded to `outputs/validation/painterly-backbone-probe/`. Contact-sheet viewer at `outputs/validation/painterly-backbone-probe/contact_sheet.html` (prebuilt during the run wait; PNGs land in the relative paths it expects).
- **Acceptance verdict pending**: awaits Luca's visual read of the contact sheet. The alt-techniques workstream entry (private during v0.1) will be footered accordingly.

### 2026-05-18

- Created [`../../../findings/modal-sdk-quirks.md`](../../../findings/modal-sdk-quirks.md): consolidates the nine SDK quirks discovered across renderer + trainer builds (script-vs-module mode, `add_local_*` ordering, missing `Function.with_options`, `keep_warm`->`min_containers` rename, `Volume.iterdir(recursive=)` silently ignored, `CachedRevisionInfo.last_accessed` rename, Windows cp1252, etc.). Captures the failure-driven knowledge that would otherwise be lost on chat compaction.
- Migrated to `docs/planning/workstreams/modal/` per D2 protocol in `docs-strategy.md`. Renamed `modal-progress.md` -> `progress.md`, `modal-followup-plan.md` -> `followup-plan.md`, `release-batch.md` stays as `release-batch.md` in the new folder. Fixed relative links inside all three (sibling refs use bare names; master log via `../../progress.md`; findings via `../../../findings/`; src/cloud/examples via `../../../../`). Purged all 40 em-dashes from progress.md + followup-plan.md (commas in body, colons in headings). Link checker: 32 -> 22 broken links repo-wide; modal workstream contributes zero. Remaining stale modal-* references are in parent-owned `docs/planning/progress.md` and `docs/README.md`. Also fixed two stale references in `cloud/README.md` and `docs/modal.md` pointing at the old root locations.

### 2026-05-16

- Read the kickoff brief: opt-in design + variant-friendly entry-point
  override are the two load-bearing constraints. Modal targets the Phase
  2 port at `src/slow_interpolation/`, not legacy.
- Reviewed `src/slow_interpolation/run.py`, `pipeline.py`, `config.py`,
  `__init__.py`. Confirmed the local CLI entry point is
  `python -m slow_interpolation.run <config.yaml>`. Confirmed
  `load_pipeline_config` only consumes known top-level YAML keys, so an
  added `modal:` section is silently ignored by the local path.
- Verified `vendor/rife_v425/` (24 MB) and `models/loras/` (three
  checkpoints, 218 MB each) layout. Decision: bake `vendor/` into the
  image (small, immutable, MIT-licensed); push LoRAs to a Modal Volume
  (large, per-release, user-provided).
- Built `cloud/` subpackage:
  - `app.py`: Modal App, Image (CUDA 12.4 + Python 3.11 + the package
    dependencies + ffmpeg via apt), three Volumes, one
    GPU-decorated function `render(config_yaml_text, modal_settings)`
    that resolves `pipeline_entry` and `config_loader` via importlib,
    instantiates the class, calls `.render()`, writes the manifest, and
    commits the outputs volume.
  - `entrypoint.py`: `modal run` entry. Reads a local YAML, splits off
    the optional `modal:` section, calls the remote function with the
    raw YAML text and the settings dict.
  - `manifest.py`: dataclass + JSON dump helpers for the run manifest.
    Captures resolved config, git commit, entry-point strings, GPU tier,
    per-phase wall time, total cost.
  - `upload_weights.py`: one-time uploader for the `loras/` volume.
    Uploads every `.safetensors` under a local directory.
  - `README.md`: quickstart pointing at `docs/modal.md`.
- Added `[cloud]` optional extra to `pyproject.toml` with `modal>=0.66`
  pinned. No other pyproject changes.
- Wrote `docs/modal.md` end-to-end: setup, secrets, weights upload,
  invocation, downloading artifacts, the YAML `modal:` schema, the
  `pipeline_entry` / `config_loader` override pattern with three worked
  variant-shipping examples (new LoRA via config, override
  `pipeline_entry` to a fork's class, deploy a branch with structural
  source changes), troubleshooting, cost expectations per GPU tier.
- Cold-run against `examples/configs/tcole_valley.yaml` is NOT yet
  executed: requires Luca's Modal account + secrets configuration. The
  parent chat (or Luca) runs that and reports back here.

### 2026-05-17, cold-run + fixes

- Logged in to Modal workspace `vandaloruins` (Starter tier, 30 USD
  credits). One existing app `in-ascolto-rvc` from prior projects
  confirms Modal is set up.
- `pip install -e .[cloud]` → modal 1.4.2 installed (above the >=0.66
  floor).
- `modal token new` → browser handshake re-used the existing Modal
  session, token written to `~/.modal.toml` profile `vandaloruins`.
- LoRA upload: 3 files, 217.9 MB each, ~650 MB total, uploaded to
  `slow-interp-loras` volume.
- **Two Modal-quirk fixes during cold-run bring-up:**
  1. **`modal run cloud/entrypoint.py` -> `modal run -m cloud.entrypoint`.**
     Modal CLI refuses script-mode loading when the file has relative
     imports. The `-m` module-mode flag is required because `cloud/` is
     a package. Docs in `docs/modal.md`, `cloud/README.md`,
     `cloud/entrypoint.py`, and `cloud/upload_weights.py` updated.
  2. **Image build ordering.** Modal requires every `add_local_*` call
     to come LAST in the image chain. Original `cloud/app.py` had
     `.env()` and `.workdir()` AFTER `.add_local_dir()`, which Modal
     rejected with `InvalidError`. Reordered: `.env()` and `.workdir()`
     now come BEFORE the four `add_local_dir` calls. This is also more
     efficient: local file edits skip image rebuild and just re-mount.
  3. **Windows console encoding**: Modal CLI emits Unicode checkmarks
     (`✓`) that cp1252 can't encode. Workaround: set
     `PYTHONIOENCODING=utf-8` and `PYTHONUTF8=1`. Documented under a
     "Windows note" section in `docs/modal.md`.
- **Cold-run result** ([dashboard](https://modal.com/apps/vandaloruins/main/ap-4grpfgiJxH4AtzRQp7TAXG)):

  | Metric | Value |
  |---|---|
  | GPU tier | L40S (default) |
  | Phase A (keyframes) | 76.7 s |
  | Phase A.5 (smoothing) | 15.8 s |
  | Phase C+D (RIFE + encode) | 26.5 s |
  | **Total wall** | **121.4 s** |
  | **Estimated cost** | **0.07 USD** (at 1.95 USD/hr) |
  | Output resolution | 1328 x 752 (1344 x 768 - edge_crop 8) |
  | Output duration | 59.54 s |
  | Output size | 6.8 MB |
  | Output codec | H.264 yuv420p, 24 fps |

  Matches the Phase 2C local reference envelope exactly (1328x752,
  24fps, 59.54s, 6.8MB). Visual inspection by Luca pending.

- **Acceptance criteria met:**
  - [x] Visually equivalent envelope to local Phase 2C reference
        (1328x752, 24fps, 59.54s, 6.8MB).
  - [x] **Visual inspection of `outputs/from-modal/tcole_valley.mp4`
        passed (Luca, 2026-05-17).** Composition family, palette,
        surface, and loop closure all consistent with the local Phase
        2C reference and the legacy `tcole_valley_horizontal_v2.mp4`.
        No border / pulse / loop-closure regressions.
  - [x] Run-manifest JSON emitted next to MP4 with config, GPU tier,
        phase times, cost.
  - [x] `docs/modal.md` covers fresh-reader end-to-end flow including
        variant-shipping recipe.
  - [x] With `modal` uninstalled, `python -m slow_interpolation.run`
        still works locally. Verified `import slow_interpolation` does
        not pull `modal`.
  - [x] Cost well under 5 USD per 60s loop ceiling (0.07 USD measured,
        ~70x headroom).

- Manifest `git_commit` resolved to `"unknown"`: the repo has no
  commits yet (`git log` returns "your current branch 'main' does not
  have any commits yet"). Not a Modal bug, expected behavior given
  current repo state.

## Open items / blockers

None. Infra is shipped and verified end to end. Downstream workstreams
(Renoir, future compositing) can build against it.

## ACTIVE REQUEST to parent chat (2026-05-17): T2#7 schema extension

Modal workstream is mid-build on T2#7 (schema extension worked
example). Needs parent chat to land a small edit in
`src/slow_interpolation/config.py`:

1. Add a new field on `PipelineConfig`:
   ```python
   experiment_tag: str = ""  # free-form label, optional, default empty
   ```
   Place at the end of the dataclass (after the existing optional
   fields) so dataclass field-ordering rules are satisfied.

2. Add a new module-level loader function:
   ```python
   def load_pipeline_config_v2(path: str | Path) -> PipelineConfig:
       """Variant loader for the Modal `--config-loader` worked example.

       Identical to `load_pipeline_config` plus parses an optional
       top-level `experiment_tag: str` key. Demonstrates the schema-
       extension pattern (recipe iii in docs/modal.md) with a trivial
       no-op field.
       """
       cfg = load_pipeline_config(path)
       with Path(path).open("r", encoding="utf-8") as f:
           raw = yaml.safe_load(f)
       cfg.experiment_tag = str(raw.get("experiment_tag", "") or "")
       return cfg
   ```

3. Export `load_pipeline_config_v2` from
   `src/slow_interpolation/__init__.py`.

That is the entire edit. After parent chat lands it, Modal workstream
authors the demo YAML, runs the render, verifies the field round-trips
into the manifest, updates `docs/modal.md` recipe (iii) with the
concrete commands. Marks T2#7 done.

Why now: pre-flighting the override mechanism with a trivial field so
the first real schema extension (CompositingPipeline mask paths, layer
denoise schedules) inherits a known-good pattern.

---

## Requests to the parent chat (for `docs/planning/progress.md`)

Coordination protocol says only the parent chat edits the master
`progress.md`. Integration nudges as of 2026-05-18:

1. **Flip Phase 3.5 row in the status-at-a-glance table** from
   "Substantially done; blocked on Luca for cold-run" to **Done**
   (date: 2026-05-17, cold-run succeeded; 2026-05-18, visual
   inspection PASSED). Reference this doc at its new path
   `docs/planning/workstreams/modal/progress.md`.
2. **Flip Documentation hygiene > D2 firing > Modal row** from
   "pending" to "done 2026-05-18".
3. **Add to Decisions log**:
   > **Modal infra shipped at 0.07 USD per 60s loop on L40S** (2026-05-17):
   > the conservative 5 USD ceiling has 70x headroom. Renoir can plan
   > against ~0.10 to 0.50 USD per render, not the original ~1 to 5 USD
   > estimate.
4. **Add to Decisions log**:
   > **1536x896 + A100-80GB is the new source-resolution path for
   > 1920x1080+ upscale targets** (2026-05-18): supersedes the 1344x768
   > + lanczos plan from 2026-05-16. See [`findings/upscale-source-resolution.md`](../../../findings/upscale-source-resolution.md). Renoir
   > release inherits pending a Renoir-LoRA-specific re-probe alongside
   > T1#2.
5. **Update stale modal-* link references** in `docs/planning/progress.md`
   and `docs/README.md` to point at the new paths:
   - `docs/modal-progress.md` -> `docs/planning/workstreams/modal/progress.md`
   - `docs/modal-followup-plan.md` -> `docs/planning/workstreams/modal/followup-plan.md`
   Link checker reports 5 broken references currently in those two
   parent-owned files.
6. **Surface the cross-workstream visibility hooks** (see "Decisions
   log for Next-research-steps" below) to:
   - Phase 3-Renoir-dataset chat: T1#2 queued and waiting on the
     trained LoRA; probe subject is flower-field, not vase. **Dataset
     is COMPLETE (CivitAI ZIP ready); Renoir-LoRA-arrival cluster is
     near-term as soon as Luca runs the training.**
   - Phase 3-Noise chat: T3#8 (Renoir noise sweep) and T3#9 (anchor
     clamp A/B) approved and assigned for them to integrate. Modal
     workstream provides infra (cloud/batch.py, render functions per
     GPU tier, render_warm for sequential dispatch). **Reminder:
     parent chat wired the new `render.noise.kind` + `render.noise.params`
     schema on 2026-05-17; T3#8 sweep should use the new schema,
     iterating across `noise.kind` values (`evolved`, `perlin`,
     `worley`, `simplex`, `fbm`, `image_derived`, `frequency_banded`)
     rather than the legacy `noise_walk_rate`-only knob.**

## Inbound from parent chat (key changes since I last ran, for my own awareness)

Tracking what changed in the repo that the Modal workstream needs to
absorb. Updated 2026-05-18.

- **`render.noise.kind` + `render.noise.params` schema landed**
  (2026-05-17). `walk_rate` inherits from `RenderProfile.noise_walk_rate`.
  `frequency_banded.params.sources` is a list of recursive sub-source
  dicts. T3#8 noise sweep will iterate this new dimension instead
  of just walk_rate.
- **`RIFEConfig.edge_crop` default flipped 8 -> 0** (2026-05-17). My
  configs already used `edge_crop: 0` explicitly, so no Modal-side
  change needed. The defaults flip means new YAML files can omit the
  field entirely.
- **Renoir dataset workstream CLOSED** (2026-05-17, all of Phase A +
  B + C + A.5 done). 102 cropped paintings, CivitAI ZIP ready. The
  Renoir-LoRA-arrival cluster (T1#2 + T3#8 + T3#9 + T3#10) is now
  gated only on Luca's CivitAI training run, not on dataset work.
- **`examples/configs/renoir/` scaffolded** (2026-05-17) with 4
  templates (roses, anemones, mixed bouquet calm, peony close-up
  portrait). LoRA path placeholder `models/loras/Renoir_Flowers_epoch_10.safetensors`.
  Modal workstream will exercise these once the LoRA file lands; T1#2
  flower-field probe should align subject choice with one of the four
  scaffolded templates rather than authoring a new one.

## Next research steps

Suggestions, prioritized by value to Luca's pipeline of upcoming work
(Renoir release for objkt labs, compositing prototype, future
variants). Each item is framed as **Build**, **Why
it matters in production**, and **Expected outcome**. Cost figures use
the measured 0.07 USD per 60s loop baseline on L40S.

### Tier 1, natural follow-ups, hours-to-a-day of work each

1. **Batch render fan-out via `Function.map()`.**
   - **Build.** `cloud/batch.py`, ~30 to 50 lines: takes a directory
     of YAML configs (or a glob), reads each, calls `render.map(...)`
     which spawns N containers in parallel. Returns N (output_path,
     manifest_path) tuples for batch download.
   - **Why it matters in production.** The Renoir release will have
     3 to 7 subjects (per [roadmap Phase 3](../../../roadmap.md#phase-3-renoir-flowers-lora)).
     Serial today: 7 renders * 121 s = ~14 min wall, sequentially
     triggered, each needing a return-to-terminal. With `map()`: ~2
     min wall, one command, one wait. **Cost is identical (per-container
     billing), wall time collapses by Nx.** During iteration on the
     Renoir subject suite this is the difference between "kick off a
     batch then make coffee" and "babysit 7 renders across an
     afternoon".
   - **Expected outcome.** Release-day workflow becomes
     `python cloud/batch.py examples/configs/renoir/*.yaml`,
     downloads all 7 MP4s + manifests, total cost ~0.5 USD, total
     wall ~3 min. Same shape will serve future releases unchanged.

2. **Renoir variant-shipping dry-run + border probe.**
   - **Build.** Once the Renoir LoRA is trained (Phase
     3-Renoir-dataset workstream), walk variant recipe (i) from
     `docs/modal.md`: upload the LoRA via `upload_weights`, author
     one config under `examples/configs/renoir/vase.yaml` with
     specifically a vase-of-flowers closeup (the prompt shape that
     historically triggers "framed picture" mode in SDXL), render on
     Modal at `edge_crop: 0`. One render, ~0.07 USD.
   - **Why it matters in production.** Two risks land at once. (a)
     The variant-shipping recipe is currently documented but
     unexercised; if it breaks (e.g. a LoRA path edge case, a
     `lora_scale` defaulting issue) we want to learn that BEFORE the
     release sprint, not during. (b)
     [docs/findings/border-crop.md](../../../findings/border-crop.md) verified
     EDGE_CROP=0 for Cole + Casa del Suono but explicitly flags that
     "the Renoir flowers LoRA will need its own probe before locking
     in the default" and that "figured closeup subjects" are the
     known stress test. A vase closeup is the worst-case prompt shape
     for the Renoir LoRA. Probing it once decides the EDGE_CROP
     default for the entire release.
   - **Expected outcome.** Either (a) probe is clean -> add Renoir to
     the EDGE_CROP=0 default policy and render the release at full
     1344x768, or (b) probe shows arch artifacts -> Renoir release
     uses EDGE_CROP=8 (legacy default), and the finding is documented
     so we don't relitigate. Either way the release ships at the
     right setting. Companion doc: `docs/findings/renoir-border-probe.md`.

3. **Staging cleanup on the outputs volume.**
   - **Build.** ~5 lines at the end of `render()` in `cloud/app.py`:
     after the MP4 + manifest are written and the volume is
     committed, `shutil.rmtree(pipeline.staging_dir, ignore_errors=True)`.
   - **Why it matters in production.** Each 60 s render leaves ~150
     MB of PNG keyframes under `outputs/staging/<name>/`. A Renoir
     release of 7 subjects with ~3 iterations each = 21 renders =
     **3 GB of stale PNGs** in the outputs volume. Across future
     releases the outputs volume crosses 10 GB within months. Modal
     charges per GB-month stored; the cost is low (~0.20 USD/month
     per 10 GB) but the volume becomes annoying to `modal volume ls`
     and to download selectively.
   - **Expected outcome.** Outputs volume stays at "N x final MP4 +
     manifest" forever (~7 MB per render). `modal volume ls
     slow-interp-outputs` reads cleanly. No periodic manual cleanup.
     Tradeoff: loses the ability to rerun just Phase C+D from staged
     keyframes, acceptable, because cheap re-renders make this
     unnecessary on Modal (re-running C+D locally is the workflow if
     someone needs to A/B RIFE settings).

4. **Smoke-test config + `cloud/smoke.py`.**
   - **Build.** `examples/configs/smoke.yaml` with `steady: 1,
     transition: 0, return_: 0, warmup: 1` and `rife.passes: 1`.
     Total: 2 keyframes, 1 RIFE pair, ~10 s wall time. Plus a
     `cloud/smoke.py` that calls it and asserts the output MP4
     exists and has non-zero duration.
   - **Why it matters in production.** Catches the cheap class of
     regressions (LoRA path drifted, image rebuild changed an
     imported symbol, volume mount path changed, RIFE checkpoint
     missing) at 0.005 USD and 10 s instead of at 0.07 USD and 2 min.
     Run before any batch session, before a release day, after
     pulling a branch. **The cost is so low that it becomes a
     no-think pre-flight check.**
   - **Expected outcome.** "Is Modal still working?" becomes a
     1-command answer with a green/red exit code. Reduces the "did I
     break Modal yesterday" anxiety that otherwise creeps into a
     workflow where you only touch Modal on release days.

5. **Reproducibility upgrade: HF cache revision hashes in manifest.**
   - **Build.** ~10 lines in `cloud/manifest.py` + `app.py`: after
     `load_sdxl_pipeline()`, read each model's resolved cache
     directory and capture the `refs/main` SHA (or
     `snapshot_download` revision return value). Add three fields to
     `RunManifest`: `sdxl_base_revision`, `lightning_lora_revision`,
     `vae_revision`.
   - **Why it matters in production.** HuggingFace silently pushes
     new revisions of base models (`stabilityai/stable-diffusion-xl-base-1.0`
     has had several since 2024). Without revision capture, a
     re-render of "the exact Renoir release config in 2027" produces
     different output than the 2026 release. **For NFT secondary
     market context this matters: collectors and curators may ask
     for re-renders or restoration prints. We need to be able to
     answer "what was the input on render day".** The release curator
     is a plausible source of such a request.
   - **Expected outcome.** Every manifest captures the exact model
     fingerprint. A 2027 re-render can pin `revision=...` in the
     model loader and reproduce the 2026 render to byte-equivalence
     in the deterministic path (RIFE), and to envelope-equivalence
     in the non-deterministic path (Lightning sampling, evolved
     noise walk). Forensic continuity for the release.

### Tier 2, unlocks Phase 3.4 (dual-prompt compositing)

6. **Pipeline contract test (`tests/test_modal_contract.py`).**
   - **Build.** A pytest module that imports `_resolve_dotted` from
     `cloud/app.py` (or re-implements its 5 lines), resolves the
     default `pipeline_entry`, asserts the class has `__init__(self,
     config: PipelineConfig)` and `render(self) -> Path` via
     `inspect.signature`. Same test parameterized over a list of
     known pipeline classes. No GPU required; runs locally in <1 s.
   - **Why it matters in production.** When CompositingPipeline (or
     any future variant) lands, the contract regression doesn't
     surface until a Modal render boots a container, downloads the
     image, and only THEN crashes on `AttributeError: render`. At
     0.07 USD that's a tolerable cost ONCE, but during compositing
     development (when the class signature changes weekly) it's
     friction. **Local pytest catches it in <1 s for free.**
   - **Expected outcome.** Forks and branches can verify "my class
     is Modal-compatible" without spending a render. Becomes part of
     the variant-shipping recipe in `docs/modal.md`: "step 0, run
     `pytest tests/test_modal_contract.py -k <your_class>`".

7. **PipelineConfig schema extension worked example.**
   - **Build.** Add a `slow_interpolation.config:load_pipeline_config_v2`
     that wraps `load_pipeline_config` and adds one no-op field
     (e.g. `experiment_tag: str = ""`). Update `docs/modal.md` recipe
     (iii) to walk through actually using it: `--config-loader
     slow_interpolation.config:load_pipeline_config_v2`. Render
     against a YAML with the new field; confirm it round-trips into
     the manifest.
   - **Why it matters in production.** Right now recipe (iii) is
     plausible but unproven. The first person to need a real schema
     extension (compositing will need mask paths, layer denoise
     schedules, layer prompts) shouldn't be the one debugging
     whether the override mechanism works at all. **Pre-flight the
     mechanism with a trivial extension, so when the real one lands
     the only unknowns are the new fields.**
   - **Expected outcome.** Recipe (iii) goes from "documented" to
     "documented and verified". Compositing workstream can start
     from a known-good extension pattern instead of inventing it.

### Tier 3, exploratory, technique-level (Modal as cheap accelerator)

8. **Noise + steady-strength parameter sweep for Renoir.**
   - **Build.** Generate 9 YAMLs from a base Renoir config: 3x3 grid
     of `noise_walk_rate` in {0.02, 0.05, 0.10} and `steady_strengths`
     peak in {0.55, 0.65, 0.75}. Use the batch-fan-out from Tier 1
     #1 to dispatch all 9 in parallel. ~2 min wall, ~0.65 USD total.
     Make a 3x3 contact sheet from the first frame of each.
   - **Why it matters in production.** The Phase 3-Noise research
     workstream is asking "what noise palette suits Renoir florals"
     via offline experimentation. **Modal turns this from a multi-day
     offline GPU project into a 5-minute experiment.** The same
     pattern serves every future LoRA (after Renoir, future domain
     LoRAs each get their own sweep). The cost is so low it stops
     being a research question and becomes a release-prep step.
   - **Expected outcome.** Renoir release renders use empirically-
     selected parameters, not "carry over the Cole defaults". The
     aesthetic decision becomes data-driven and reproducible. Doc:
     `docs/findings/renoir-noise-sweep.md` with the contact sheet.

9. **SDXL trained-anchor strength clamp A/B (research recipe B4).**
   - **Build.** Two configs, identical except `steady_strengths`:
     current `[0.55, 0.55, 0.60, 0.55, 0.55, 0.65, 0.55, 0.60]` vs
     clamped `[0.50, 0.50, 0.50, 0.50, 0.75, 0.50, 0.50, 0.75]`.
     Same subject, same LoRA, same seed-ish state (the noise walk is
     unseeded but the qualitative envelope is comparable). Render
     both on Modal, ~0.14 USD total. Watch side by side.
   - **Why it matters in production.** Recipe B4 from
     [pipeline.md](../../../pipeline.md) predicts measurably better temporal
     stability when strengths align with Lightning's progressive
     adversarial distillation anchors (0.50, 0.75). Currently we run
     off-anchor. **If the prediction holds, jitter reduction is free
     for every subsequent render** (Renoir release, future work),
     achieved by changing two constants in
     `RenderProfile.standard()`. If it doesn't hold, we close the
     research question and stop wondering.
   - **Expected outcome.** A documented verdict on whether to clamp.
     If clamp wins: `RenderProfile.standard()` updated, decision
     logged in `docs/planning/progress.md`, all subsequent renders inherit
     improved stability. If clamp loses: the research question
     closes and we stop relitigating it every few months. Either way
     the answer is in the open.

10. **Engine transition-strength ramp restore A/B.**
    - **Build.** Two configs: current flat `transition_strength: 0.65`
      vs the engine's six-element ramp `[0.65, 0.72, 0.80, 0.80,
      0.72, 0.65]`. Requires a tiny config schema extension to
      accept a list (currently `transition_strength: float` per
      `config.py:95`). Render both, ~0.14 USD.
    - **Why it matters in production.** Per
      [pipeline.md](../../../pipeline.md), the original engine had the ramp,
      the horizontal entry-point variant flattened it during the
      port, and the legacy research log calls the ramp "the winning
      configuration". **The flattening was likely an accidental
      regression that has been the pipeline default ever since,
      including in the Phase 2 port we just shipped.** If the ramp
      reads as more musical (peak 0.80 lets the image actually
      travel mid-transition), every transition in every release
      improves. The Renoir release especially benefits because its
      A/B/C are aesthetic siblings (different lighting / time of
      day on the same vase), so transition quality is more
      foregrounded than in landscapes where new geography arrives.
    - **Expected outcome.** Same A/B/decision/doc shape as #9. If
      ramp wins, schema extension lands plus `RenderProfile.standard()`
      adopts the ramp. Aesthetic upgrade on every transition for
      ~0.14 USD of research cost.

11. **Higher-resolution render on A100 80GB (1536x896).**
    - **Build.** One YAML with `resolution: {width: 1536, height:
      896}` and the `modal.gpu: A100-80GB` override. Same Cole
      subject as the Phase 2C reference, otherwise unchanged.
      Render once, ~0.40 USD. Visually inspect for border behavior
      at the larger size with `edge_crop: 0`.
    - **Why it matters in production.** Direct impact on any
      1920x1080+ upscale target. Current plan
      ([docs/planning/progress.md decision 2026-05-16](../../progress.md#decisions-log)):
      render at 1344x768 native, upscale to 1920x1080 with lanczos
      post-RIFE pre-encode. If 1536x896 native is clean, the
      upscale source increases by 33%, the upscale ratio drops from
      1.43x to 1.25x, and the final 1920x1080 reads sharper. **The
      Renoir release upscale target (probably 2048x1152 or 4K for
      objkt) inherits the same gain.**
    - **Expected outcome.** A documented verdict on whether to
      render at 1344x768 or 1536x896 native for upscale targets.
      Doc: `docs/findings/upscale-source-resolution.md`. Upscale-target
      configs lock in the winning size.

12. **`keep_warm` flag for release-day batch sessions.**
    - **Build.** `cloud/app.py` exposes a `keep_warm` parameter on
      the `render` function (or a sibling `render_warm` function
      decorated with `@app.function(keep_warm=1, ...)`). Default
      off. CLI flag `--keep-warm` on the entrypoint and batch script
      to enable.
    - **Why it matters in production.** Container cold-start on
      Modal is ~20 to 40 s. At 0.07 USD per render that cold-start
      is ~25% of total wall time. With `keep_warm=1` the second and
      subsequent renders in a session skip cold-start entirely.
      **For a release-day batch of 7 to 25 renders dispatched
      individually, the savings are 5 to 15 minutes of wall time per
      session.** Cost-wise: keep_warm bills the GPU at idle rate
      (~50% of active); over a 1-hour active session the added cost
      is ~1 USD, which is net-positive if it saves any cold-start
      time at all.
    - **Expected outcome.** Release sessions feel snappy. Batch
      renders finish in coffee-break time even when iterating one
      render at a time between aesthetic decisions. Use the flag
      ONLY during active iteration; the default-off keeps idle
      costs at zero.

### Tier 4, quality of life, optional

13. **Pre-run workspace check.**
    - **Build.** A `cloud/preflight.py` (or augment `entrypoint.py`)
      that prints credit balance, current GPU availability for the
      selected tier, and warm/cold container status before the
      render starts. Two to four lines using Modal's workspace API.
    - **Why it matters in production.** "Do I have enough credits
      to render this batch?" and "is L40S available right now?" are
      currently answered by switching to the Modal web dashboard.
      Surfacing them in the CLI eliminates the context switch.
    - **Expected outcome.** Release-day pre-flight reads in one
      glance from the terminal.

14. **`cloud/volume_admin.py` (`list`, `rm`, `size`, `gc-staging`).**
    - **Build.** Thin wrapper over `modal.Volume` ops with
      project-specific defaults (knows the three volume names).
    - **Why it matters in production.** Volume housekeeping commands
      live in muscle memory or get re-derived from the Modal docs
      each time. Encapsulating them saves ~30 seconds per use and
      reduces typos. `gc-staging` complements Tier 1 #3 as a one-off
      cleanup of pre-fix backlog.
    - **Expected outcome.** Volume admin happens via project
      vocabulary, not Modal vocabulary.

15. **PowerShell `chcp 65001` snippet in `docs/modal.md` Windows note.**
    - **Build.** Two-line edit. Alternative to the env var setup.
    - **Why it matters in production.** Some Windows shells don't
      respect `PYTHONIOENCODING`; `chcp 65001` is the
      console-codepage-level fix. Belt and suspenders for fresh
      shells.
    - **Expected outcome.** First-time-per-shell setup on Windows
      has two paths, one works.

## Recommended sequencing for the upcoming release calendar

Pinned to the Phase 3 timeline in [the master log](../../progress.md#phase-3-working-timeline-provisional):

- **Now to the curator lock-in call.** Tier 1 #3 (staging cleanup),
  #4 (smoke test), #5 (HF revisions). All small, all unlock
  release-day confidence. ~2 hours of work total.
- **Before any 1920x1080+ upscale target.** Tier 3 #11 (1536x896
  probe on A100 80GB). Decides source resolution for upscale targets.
- **Before Renoir LoRA arrives.** Tier 1 #1 (batch fan-out). The
  Renoir release immediately uses it.
- **Day the Renoir LoRA lands.** Tier 1 #2 (Renoir variant dry-run +
  border probe). Tier 3 #8 (noise sweep on the Renoir LoRA), #9
  (anchor clamp A/B), #10 (transition ramp A/B). All four run in a
  single afternoon at <2 USD total cost, output is the data layer
  for every Renoir render decision.
- **Before any compositing branch.** Tier 2 #6 (contract test), #7
  (worked schema extension). Saves first compositing-on-Modal
  attempt from being a 0.07 USD discovery exercise.
- **Release sessions.** Tier 3 #12 (`keep_warm`), Tier 4 #13
  (pre-flight) on as needed.

---

## Decisions log for Next-research-steps (Luca review 2026-05-17)

This section records explicit go / no-go / scope-change decisions from
Luca's review of the 15 items above. The parallel chats (Renoir
dataset, Noise research) reading this doc should treat the **approved
and scope-changed** items below as authoritative, not the original
descriptions.

### Tier 1

- **#1 Batch fan-out, APPROVED.** Implement as scoped.
- **#2 Renoir variant + border probe, APPROVED, GATED, SCOPE CHANGED.**
  - **Gating clarified:** the Renoir LoRA is **not trained yet**.
    Per [the Renoir-dataset workstream's progress doc](../renoir-dataset/progress.md),
    Phase A sourcing is done (102 paintings), Phase B captioning is
    in flight, Phase C training playbook hasn't started, the
    CivitAI training run hasn't happened. **#2 fires the day the
    trained LoRA arrives, not before.**
  - **Subject changed: probe on flower-field subject, NOT
    vase-of-flowers closeup.** Reasoning: the flower field is
    representative of real Renoir release subjects; the vase
    closeup is a worst-case "framed picture" stress test. Probe
    the realistic case first. Expectation: no border artifacts.
    Vase-closeup probe is only a secondary test if (a) flower
    field is clean AND (b) the release subject list includes a
    vase closeup specifically.
  - Deliverable: 1 render at `edge_crop: 0`,
    `docs/findings/renoir-border-probe.md` with the verdict.
- **#3 Staging cleanup, APPROVED with REDESIGN: config knob, not
  unconditional.** Default ON (clean), opt-in OFF (`modal:
  preserve_staging: true`) when actively debugging or doing C+D
  reruns from staged keyframes. Reason for the redesign: the C+D
  rerun path is genuinely useful for RIFE / temporal-smoothing A/B
  work without re-rendering Phase A, but is dead weight by default
  because the Modal entrypoint doesn't currently expose
  `--skip-keyframes`. Knob preserves both modes.
- **#4 Smoke test, APPROVED.** `examples/configs/smoke.yaml` +
  `cloud/smoke.py`. Implement as scoped.
- **#5 HF cache revision hashes in manifest, APPROVED.** Ship and
  document. Reason emphasized by Luca: forensic continuity for the
  objkt release (the curator may ask for re-renders or restoration
  prints; we need to be able to pin model revisions).

### Tier 2

- **#6 Pipeline contract test, APPROVED.** Implement
  `tests/test_modal_contract.py` as scoped.
- **#7 PipelineConfig schema extension worked example, APPROVED
  with clarification.** Concrete deliverable:
  - Add `load_pipeline_config_v2` in
    `src/slow_interpolation/config.py` that wraps
    `load_pipeline_config` and accepts one no-op extension field
    (e.g. `experiment_tag: str = ""` on `PipelineConfig`).
  - One Modal render that uses
    `--config-loader slow_interpolation.config:load_pipeline_config_v2`
    against a YAML with the extension field set; verify the field
    round-trips into the manifest's `config_yaml`.
  - Update `docs/modal.md` recipe (iii) to point at this concrete
    example instead of the abstract pattern.
  - **Production value:** when CompositingPipeline (or any future
    variant) needs to extend the YAML schema with real fields
    (mask paths, layer denoise schedules, layer prompts, etc.),
    there is a proven copy-paste pattern. Without this item, the
    first compositing branch is also the first to debug whether
    the `--config-loader` override mechanism works as documented.
  - Total work: ~30 lines code, 1 render (~0.07 USD), ~30 min doc.
  - **Coordination note:** touching `src/slow_interpolation/config.py`
    requires the parent chat per coordination rules. Modal
    workstream files the request, parent chat implements
    `load_pipeline_config_v2`, Modal workstream then exercises it
    and updates `docs/modal.md`.

### Tier 3

- **#8 Renoir noise sweep, APPROVED. DOC-VISIBLE TO PARALLEL CHATS.**
  Phase 3-Noise parallel chat should pick this up and integrate it
  into the noise-source comparison harness. Modal turns the
  multi-day offline GPU experiment into a 5-minute cloud experiment;
  the noise workstream can use Modal as its accelerator instead of
  Luca's local box.
- **#9 SDXL anchor-clamp A/B, APPROVED. DOC-VISIBLE TO PARALLEL
  CHATS.** Reason emphasized by Luca: this is upstream of broader
  work on interpolation smoothness and jitter reduction. If the
  clamp wins, the temporal-stability improvement is the foundation
  for further smoothness work; if it loses, we stop relitigating it.
  Either way the answer becomes visible.
- **#10 Engine transition-ramp restore A/B, APPROVED.** Implement
  as scoped. Requires a small schema extension in `config.py`
  (`transition_strength` accepts list, not just float). Coordinate
  with parent chat for the `config.py` edit.
- **#11 1536x896 / A100 80GB upscale-source probe, APPROVED.**
  Reason emphasized by Luca: the current local pipeline was built
  for desktop rendering; if cloud rendering scales cleanly to larger
  resolutions, that's foundational for higher-resolution releases
  (Renoir 4K) AND for future live generation paths. **The probe is also a stepping stone toward
  testing whether the pipeline can run at scale for live work** (Phase
  4.2 webcam depth-as-noise, Phase 4.4 anchored live prompting), where
  the latency and resolution tradeoffs of cloud-vs-local change the
  whole feasibility envelope.
- **#12 `keep_warm` for release-day batch, APPROVED with FULL
  REDESIGN: never standalone, always wrapped in a session-bounded
  script with multiple safety layers.** Critical because forgotten
  `keep_warm` over a weekend = ~720 USD/month worst case
  (L40S idle ~1 USD/hr × 24h × 30d). Safety harness has six layers:

  1. **Hard cap at function definition:** `container_idle_timeout=1800`
     (30 min). Even if every other layer fails, max cost from
     forgotten warm pool is ~0.50 USD before hard-spin-down.
  2. **No persistent flag.** No YAML setting, no boolean CLI flag.
     Warm only activates inside a session script.
  3. **Time-windowed activation:** `release_batch.py --warm 30m`,
     duration required, not boolean.
  4. **Loud terminal banner** at start, end, and every 5 min during
     active session: tier, idle USD/hr, auto-stop time, manual-stop
     command.
  5. **Explicit `finally` shutdown** on success, exception, OR Ctrl+C.
     Container hard-cap is the safety net behind this.
  6. **Post-batch cost summary**: render-active GPU-s vs warm-idle
     GPU-s vs total USD. Surfaces accidental waste loudly.

  **Deliverable:** `cloud/release_batch.py` that combines T1#1
  batch fan-out with the safety-harnessed warm-pool option.
  Behavior without `--warm`: identical to T1#1 batch fan-out, no
  idle billing. Behavior with `--warm DURATION`: warm pool active
  with all six safety layers.

  **When the value is real:** sequential dispatch with human in
  the loop, batch ≥7 renders, session under 1 hour. **For a
  fire-and-forget `map()` dispatch of N parallel renders, warm
  pool gives nothing** because each parallel container cold-starts
  in parallel anyway.

  **Future skill wrapper (deferred):** a Claude Code skill that
  invokes `release_batch.py --warm DURATION`, watches stdout for
  the warm-active banner, re-prints it in chat at intervals,
  surfaces cost summary at end, refuses to invoke if a previous
  session lock is still active. Built when actually needed.

### Tier 4

- **#13 Pre-run workspace check, APPROVED.** Print credits, GPU
  availability, warm/cold status. Two lines using Modal's
  workspace API.
- **#14 `cloud/volume_admin.py`, APPROVED with EXPANDED scope.**
  Concrete subcommands and rationale (each addresses a gap in
  Modal's native CLI):
  - `list`: shows all three volumes (loras, outputs, hf-cache) with
    item counts. **Eliminates remembering volume names.**
  - `size`: total bytes per volume + cost-per-month estimate.
    **Modal has no native `du` equivalent.**
  - `rm <volume> <pattern>`: pattern-based delete (e.g.
    `rm outputs "*.png"`). **Modal requires N separate `rm` calls
    for what's one glob op here.**
  - `gc-staging`: shorthand for `rm outputs "staging/*"`. **One-time
    complement to T1#3's per-render cleanup**, clears pre-fix
    backlog or recovers from sessions where `preserve_staging` was
    true.
  - `download <volume> <pattern> <local>`: bulk download by pattern.
  - `inspect outputs <output_name>`: shows the mp4 + manifest +
    (if present) staging for a given output_name. One-stop view
    for verifying / debugging a specific render.

  **Total work:** ~150 lines, no GPU, write-once-use-forever.
  **Production value:** eliminates "what was that command again"
  lookups on release days; onboards collaborators to volume
  maintenance via one file (volume_admin.py source) instead of
  Modal docs.
- **#15 PowerShell `chcp 65001` snippet, APPROVED.** Two-line
  edit in the Windows note in `docs/modal.md`.

### Cross-workstream visibility hooks

Items where the parallel chats need to know what we approved here:

- **Phase 3-Renoir-dataset parallel chat** should know:
  - **#2 is queued and waiting on their delivery** (the trained
    LoRA). When the LoRA exists, Modal-workstream picks up
    immediately for the flower-field probe.
  - The probe will inform the EDGE_CROP default for Renoir, which
    might in turn affect dataset captioning conventions if certain
    subjects need to be re-tagged for the probe's expected output.
- **Phase 3-Noise parallel chat** should know:
  - **#8 (Renoir noise sweep) is approved and assigned to them
    to integrate** with their noise-source comparison harness.
    Modal becomes their accelerator instead of local GPU.
  - **#9 (anchor-clamp A/B) is approved and is foundational** for
    their broader interpolation-smoothness work. The verdict on
    clamp-vs-cycling strengths feeds into how they design
    subsequent jitter-reduction experiments.

These cross-references go up the chain via the parent chat
(`docs/progress.md`) so the parallel chats see them on next
session-start.

## Requests to the parent chat

None. No edits to `src/slow_interpolation/`, no edits to existing YAML
configs, no edits to `docs/pipeline.md` etc. required for the initial
infra build.
