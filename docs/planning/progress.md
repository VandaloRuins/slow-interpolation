# Progress

Pre-curation flush completed 2026-05-18 [mode B] (re-flushed end-of-day after Soutine bake-off + REQUEST-0 ownership clarification + duplicate-trainer lesson; re-flushed again 2026-05-18 evening after narrative-arc drift work shipped per-prompt negative_prompt schema extension + loop-closure-tuning finding).

Living document. Tracks what is done, what is in flight, what is next, and the key decisions made along the way. Updated whenever a milestone closes or a decision changes.

Last updated: 2026-05-19.

**Parent-chat session (2026-05-19, public push): slow-interpolation v0.1 went public on GitHub.** Repo live at https://github.com/VandaloRuins/slow-interpolation (handle: VandaloRuins, the maintainer's existing GitHub identity; the HF handle stays VRuins for the LoRAs). One initial commit (`8fcaf8f`) with 211 files, MIT-licensed. GitHub Releases v0.1 published at https://github.com/VandaloRuins/slow-interpolation/releases/tag/v0.1 with three reference MP4 attachments (Casa del Suono lake hero, Cole cloudship, Cole valley quickstart smoke). Pre-push pass: sensitive-content sweep (Anika mentions, parallel-project mentions, specific dates all redacted across ~10 files); gitignore extended to exclude bulk dataset content (image bytes, ZIPs, manifests, gallery state), pitch-materials/, local-spot-check/, train-artifacts/, .playwright-mcp/, root-level Playwright PNGs; two heavy-redaction files (`v0.1-release-prep.md`, `modal/followup-plan.md`) moved to `docs/planning/private/`; build_gallery.py de-personalised (dropped embedded objkt-labs label). Push auth via short-lived PAT with repo+workflow scopes; token stripped from remote URL post-push (now plain HTTPS); Luca to revoke both tokens at github.com/settings/tokens. The Modal smoke render `outputs/tcole_valley_smoke_v01.mp4` (84.2 s wall, $0.05 on L40S) verifies the HF Hub auto-download chain end-to-end inside a Modal container with the `hf:VRuins/thomas-cole-sdxl-lora` syntax. Local quickstart end-to-end test still pending visual inspection.

**Parent-chat session (2026-05-19, late night extension): Casa del Suono LoRA published to HF Hub + first-runs tutorial restructured.** Casa del Suono Fresco SDXL LoRA live at https://huggingface.co/VRuins/casa-del-suono-sdxl-lora (handle: VRuins, MIT, no trigger word, descriptive prefix `"Italian fresco on aged plaster, warm chiaroscuro, visible brushwork, terracotta and ochre palette,"`, scale 0.35 default, 228 MB fp16, epoch 4). Model card carries quick-use code snippet, sample image + clip from the Choire v2 E14 lake render, training-data attribution (corrected from "photographs by author" to "synthetic dataset generated from study of online reference material; no photographs shipped"), provenance, license, citation, related-work pointers. Commit: `2e558303`. First-runs tutorial at `docs/tutorial-first-runs.md` restructured per Luca's spec: Step 1 (Casa del Suono) now generates an image + a slow loop with student-chosen subject; Step 2 (Cole) shares the painter's vocabulary (American wilderness, Hudson River School, atmospheric perspective) and invites the student to pick an evocative natural subject before rendering image + loop. Four sub-steps total tracked in `~/.cache/slow-interpolation/tutorial-status.json`. Modal pricing claim corrected across all docs ($30/mo free credit requires card on file at signup as identity verification; not charged unless upgraded). "Hard guarantees" reframed in `modal-operations.md` as default-deny with consent escalation (agent stops at OAuth + ToS by default; can escalate with per-session student consent; never retain credentials across sessions).

**Parent-chat session (2026-05-19, late night): HF Hub auto-download wired into the pipeline.** `StyleConfig.lora_path` now accepts either a local filesystem path OR a `hf:<user>/<repo>` HuggingFace Hub reference; `keyframes._resolve_lora_path` calls `hf_hub_download` on the HF case and caches normally. `StyleConfig` gained an optional `lora_filename` field for repos whose internal filename differs from `<repo>.safetensors`. `examples/configs/tcole_valley.yaml` now references `hf:VRuins/thomas-cole-sdxl-lora` (was `models/loras/Thomas_Cole_epoch_10.safetensors`). Smoke-tested end-to-end: config loads, resolver downloads + caches, file size matches (228 MB). README quickstart updated to name the auto-download behaviour. All 55 tests pass. Link-check stable at 9 broken (expected forward-refs only).

**Parent-chat session (2026-05-19, night): v0.1 release-prep pass shipped + Thomas Cole LoRA published to HuggingFace Hub.** Release-prep plan at `docs/planning/v0.1-release-prep.md`. Sensitive-content sidecar pattern in place (`CLAUDE.local.md` + `docs/context.local.md`, gitignored). Five in-progress workstreams moved to `docs/planning/private/` (gitignored), three shipped-milestone workstreams stay public. README rewritten with Casa del Suono lake video as hero + workshop framing. New `docs/workshop-kickoff.md` carrying the paste-able prompt for workshop students to give to their AI agent. ~25 broken refs to now-private workstreams swept across findings + manual + CONTRIBUTING + docs/README + planning/progress. Link-check: 46 → 9 broken (all 9 are expected forward-refs to `findings/lora-pipeline.md` and `manual/pipeline.md` which land later). **Thomas Cole SDXL LoRA shipped to HuggingFace Hub:** https://huggingface.co/VRuins/thomas-cole-sdxl-lora (handle: VRuins, MIT, trigger `tcole`, scale 0.75 default, 228 MB fp16, model card carries quick-use snippet + training data attribution + training settings + provenance + citation + related-work pointers to v0.2 LoRAs).

**Parent-chat session (2026-05-19, evening): subagent-architecture pivot landed. Three new subagents shipped at `.claude/agents/{modal,dataset-mosaic,lever}.md` alongside the existing `docs-curator.md`. New umbrella manual page `docs/manual/modal-operations.md` synthesises the routing-decision-plus-dispatch-plus-quirks knowledge into modal-agent's operating brief. `CLAUDE.md` natural-language map extended with 25+ phrase rows routing to the four agents. `AGENTS.md` + `docs/planning/docs-strategy.md` reframed to separate "workstream initiatives" (time-bounded project logs) from "subagents" (capability-domain specialists callable from any chat). modal owns the local-vs-Modal routing decision + cost-vs-time framing (Luca confirmed Modal-agent absorbs hardware-routing.md responsibilities and surfaces credit awareness). dataset-mosaic owns the full curate -> train -> validate -> ship arc and calls modal for cloud dispatch. lever is the per-render-tuning specialist (evolution of the noise role: noise + RIFE + SDXL + lora_scale + denoise + per-prompt negatives + loop-closure), read-only consult returning YAML stanzas with rationale; synthesises from the existing findings, no umbrella manual page yet (deferred until tuning patterns stabilise). docs-curator unchanged. Runtime workaround: invoke via `general-purpose` with the agent file as operating prompt (Claude Code does not yet pick up project-local custom agent types).**

**Today's parent-chat session (2026-05-19): second docs-curator pass landed (flush coverage 4/8, classification proceeded with partial flag); new agent-facing manual page `docs/manual/validate-lora.md` shipped (family-agnostic LoRA validation protocol, drives `cloud/validate_lora.py`, 5-phase shape, registered in `manual/index.md` dispatcher); Soutine validation-grid path bug verified end-to-end (the grid markdown references `outputs/validation/soutine-epoch-{N}/` while the renderer writes `outputs/validation/soutine-{civitai,modal-v2}/epoch-{N}/`; image bytes exist on disk; doc-side rewrite owned by soutine-lora workstream).**

The 2026-05-19 docs-curator pass classified 65 markdown files (41 planning, 18 findings, 7 manual, plus tier-2 reference at root). Three promotions identified (compositing.md, inpaint.md, narrative-arc-renders.md), all deferred until their underlying workstreams stabilise. Two consolidations remain queued from 2026-05-18 (Job 1 lora-pipeline.md, Job 2 dataset-hygiene merge). The 45 → 46 link-check baseline jump is the new `validate-lora.md` adding one forward-ref to the still-pending `lora-pipeline.md`; 30 of the 46 concentrate in `compositing/soutine-validation-grid.md` (path-schema bug, soutine-lora owns the rewrite). Five docs flagged as already subagent-shaped (`manual/train-lora-on-modal.md`, the `dataset-curation.md` + `gallery.md` pair, `manual/hardware-routing.md`, `manual/noise.md`, post-impl `manual/inpaint.md`); this informs the next parent-chat workstream: pivoting from parallel-chats-as-pseudo-subagents to real Claude Code subagents callable from any chat.

**Today's parent-chat session (2026-05-18): Renoir LoRA trained, validation grid shipped, Modal-trainer chat dispatched, first 60s flower-field clip rendered, Soutine LoRA trained on both engines (Modal wins second bake-off; CivitAI shelved as production trainer; compositing fully unblocked).**

The Renoir LoRA was trained on civitai.red (yellow Buzz, AI Toolkit engine, 500 Buzz, ~19 min wall) and three keeper checkpoints (epoch 1, 5, 10) are at `models/loras/Renoir_Flowers_epoch_{1,5,10}.safetensors`, uploaded to Modal volume `slow-interp-loras`. A new `cloud/validation_renoir.py` (Modal app, mirrors `cloud/app.py`) rendered 33 keyframes at 1216×832 seed 42 scale 0.85 across the three checkpoints; markdown grid at [workstreams/renoir-dataset/validation-grid.md](workstreams/renoir-dataset/validation-grid.md), browser visualiser at `outputs/validation/index.html`. Headline read: **epoch 10 is the canonical strong-Renoir for vases/bouquets; epoch 1 is the better default for outdoor flower fields** (epoch 10 over-fit the auction-catalogue "photo of a painting" surface, suppressing painterly atmosphere on outdoor subjects). All epoch-10 renders have baked-in signatures in the corner (48 of 105 training images were auction scans). `inpaint-plan.md` rewritten as v2, with Phase 1 default now **Stability AI Erase** (purpose-built, no prompt, $0.03/image); Gemini Nano Banana ruled out (no pixel-mask support). Modal-trainer parallel chat dispatched with an updated kickoff (workstream log private during v0.1); its cold-run, when validated, closes the workshop-on-Modal-only story (no CivitAI, no fal.ai) and unblocks inpaint Phase 3 (Modal SDXL Inpaint + the trained LoRA).

**Production-scale validation:** new config `examples/configs/renoir/flower_field_60s.yaml` rendered on Modal L40S at 84.6s wall / $0.046, output `outputs/renoir_wildflower_field.mp4` (1344×768, 24 fps, 7.5 MB). Epoch 1 + scale 0.85 + wildflower A/B/C/A drift, with `signature, watermark, text` added to the negative prompt as a cheap inference-time mitigation pending the inpaint workstream. This validates the LoRA at full Phase A → A.5 → C → D pipeline scale on the actual release target subject; the Renoir content path is unblocked pending Luca's visual review.

**Soutine LoRA, second civitai-vs-Modal bake-off (Modal wins again, two-confirmation rule fires).** The Soutine_Figures LoRA was first trained on civitai.red 2026-05-18 (model 2632407, AI Toolkit, 500 Yellow Buzz, 54 min wall). Parent chat retrieved the three keepers (epoch 1, 5, 10) via Playwright on civitai.red by extracting presigned `modelUrl`s from `__NEXT_DATA__.trainingResults.epochs[]` and curl-ing directly (faster than browser downloads, picks only the keepers). The Modal-trainer parallel chat ran the parallel Modal training (sd-scripts / Kohya, `examples/configs/training/soutine_figures.yaml`). Modal-trained Soutine keepers now occupy `models/loras/Soutine_Figures_epoch_{1,5,10}.safetensors` (170 MB Kohya format). CivitAI Soutine baseline archived at `models/loras/archive/civitai-soutine-2026-05-18/`; full Modal training output (10 epochs) archived at `models/loras/archive/modal-soutine-v1-2026-05-18/`. **Two-confirmation rule met:** Modal won on Renoir (2026-05-17) AND Soutine (2026-05-18). Per the compositing decisions log policy, Modal is now the production training engine for all future LoRAs (Cézanne, Bonnard, future domains). CivitAI is shelved as the production trainer; remains documented as an optional alternative for students who already have a Civitai account.

**Compositing fully unblocked.** Both LoRAs needed for the Renoir + Soutine release are in hand and on the Modal `slow-interp-loras` volume. The compositing parallel chat shipped `workstreams/compositing/layering-study.md` with the concrete 5-scene contact-sheet test plan (~3h end-to-end). The parent-chat-owned dependency is REQUEST 0 from `workstreams/compositing/dual-lora-proposal.md`: extend `PipelineConfig` with `extra_styles: list[StyleConfig]` so two domain LoRAs can fuse simultaneously. ~1-2 h. After REQUEST 0, the compositing chat can build `FigureSource` + the first dual-LoRA contact-sheet render against gesture #1 or #2 from `workstreams/compositing/gesture-catalogue.md`.

**Narrative-arc creative test (rose lifecycle), schema extension shipped, loop-closure tuning finding shipped (2026-05-18 evening).** Luca opened a standalone creative test: a 1-minute Renoir-LoRA video where a vase of pink roses cycles bare stems -> full bloom -> withered dead -> bare stems, looping cleanly. Six iterations on Modal L40S surfaced three durable insights, documented in [docs/findings/narrative-arc-drift.md](../findings/narrative-arc-drift.md). Finding 1: the Renoir LoRA's full-bloom training distribution dominates the warmup-as-text2img first frame regardless of positive prompt language; per-prompt CFG negatives on A and A-return are the lever. **Schema extension shipped**: `PromptConfig` gained an optional `negative_prompt: str | None = None` field that overrides `style.negative_prompt` per segment; [keyframes.generate_keyframes](../../src/slow_interpolation/keyframes.py) uses it with style-level fallback. Backwards-compatible (verified by re-loading v1-v4 configs after the change). Finding 2: the loop-closure defaults (`return_pixel_blend_max: 0.20`, `return_strength_end: 0.60`, `frames.return_: 4`) are tuned for palette drift on stable composition; narrative-arc / content-drift loops need ~`0.55 / 0.45 / 10` to close smoothly (Luca verdict on v5: "loop now reads much more smooth"). Defaults stay; content-drift configs override. Finding 3 (in flight): v6 with `banded_renoir_tuned` noise + `frames.transition 5 -> 7` is dispatched to test whether banded noise can recover detail through SLERP-blended transition frames; verdict pending. Total Modal spend through v5 + smoke ~$0.30; v6 expected ~$0.80-1.00 (dense Worley). Configs at [examples/configs/renoir/roses_bloom_cycle_60s{,_v2,_v3,_v4,_v5,_v6}.yaml](../../examples/configs/renoir/); outputs at [outputs/creative-tests/roses-bloom-cycle/](../../outputs/creative-tests/roses-bloom-cycle/).

## Status at a glance

| Phase | Scope | Status | Owner | Notes |
|---|---|---|---|---|
| Kickoff Step 1 | Consolidate + document legacy code | **Done** | this chat | [inventory.md](../inventory.md), [pipeline.md](../pipeline.md), [outputs.md](../outputs.md), [dependencies.md](../dependencies.md) |
| Kickoff Step 2 | Read next-exploration-steps, propose plan | **Done** | this chat | This document is the proposal surface |
| Roadmap Phase 2 | Port the legacy pipeline | **Done** | this chat | See "Phase 2 deliverables" below |
| **Phase 3** | **Renoir LoRA release for objkt labs** | **In flight** | mixed | LoRA baseline trained 2026-05-17 (3 keepers), validation grid shipped 2026-05-18, first 60s flower-field clip rendered 2026-05-18 (`outputs/renoir_wildflower_field.mp4`, $0.046, 84.6s wall, epoch 1 + signature negative prompt). Next milestone: visual review of the clip, then either expand variant set or pivot to inpaint Phase 1. Modal-trainer cold-run still gates workshop-only-on-Modal story. |
| Phase 3.5 | Modal cloud-render infrastructure (general purpose) | **Done 2026-05-18 (followup plan shipped; release-day Tier 1 + Tier 2 closed; Tier 3 cluster gated on Renoir LoRA arrival)** | parallel chat | Package at `cloud/`. Cold-run 2026-05-17 at 0.07 USD per 60s on L40S. Status: [workstreams/modal/progress.md](workstreams/modal/progress.md). |
| Phase 3-Renoir-dataset | Renoir floral dataset curation + LoRA training + validation | **Done 2026-05-18** | parallel chat | 105 cropped paintings, captions, CivitAI ZIP, LoRA trained 2026-05-17 (3 keepers in `models/loras/`), 33-render validation grid + browser visualiser shipped 2026-05-18. Status: [workstreams/renoir-dataset/progress.md](workstreams/renoir-dataset/progress.md). Headline: epoch 10 for vases, **epoch 1 for fields** (counter to original prediction; epoch 10 over-fit auction-catalogue surface). Visible signatures on epoch 10 (predicted from 48/105 auction scans). |
| Phase 3-Modal-trainer | Modal-hosted SDXL LoRA trainer | **In flight** | parallel chat | Kickoff v2 dispatched 2026-05-18. Cold-run target: re-train the Renoir LoRA on Modal (sd-scripts / Kohya, spec hyperparameters from `lora-training.md` §3) and validate against the CivitAI baseline using `cloud/validation_renoir.py`. When done, the workshop runs on Modal only (no CivitAI account needed). Workstream log is private during v0.1; surfaces publicly in v0.2 once the cold-run validates. |
| Phase 3-Inpaint | Dataset-curation gallery inpainting (signature / watermark / subject removal) | **Design in iteration (pre-impl)** | parent chat (this session) | Workstream opened 2026-05-18 with a 5-phase impl plan (I1 Modal app, I2 gallery endpoint, I3 brush UI, I4 manual page, I5 real-pass retrain). Background plan (backend ranking, Phase 1-4 menu) lives at [workstreams/renoir-dataset/inpaint-plan.md](workstreams/renoir-dataset/inpaint-plan.md). Workstream log is private during v0.1; surfaces publicly in v0.2 once implementation closes. |
| Phase 3-Noise | Noise sources research (offline) | **Done; wired into PipelineConfig** | parallel chat | 6 sources + ABC + harness + 49 tests landed. Status: [workstreams/noise/progress.md](workstreams/noise/progress.md). Parent chat wired `render.noise` (kind + params, walk_rate inherited) on 2026-05-17; ready for GPU contact-sheet renders against `tcole_valley.yaml` and Renoir configs. |
| Phase 3-Border-test | EDGE_CROP=0 probe | **Done; default applied** | this chat | Verdict: drop the crop. See [docs/findings/border-crop.md](../findings/border-crop.md). `RIFEConfig.edge_crop=0` default landed 2026-05-17; `tcole_valley.yaml` carries an explicit `edge_crop: 0` line for clarity. |
| Phase 3-Compositing | Dual-prompt offline compositing prototype | **Fully unblocked; compositing chat owns REQUEST 0 + downstream** | parallel chat (compositing) | All gating deps landed: NoiseSource API (2026-05-17), Renoir LoRA (2026-05-17), **Soutine LoRA (2026-05-18, Modal-trained)**. Compositing chat shipped a 5-scene contact-sheet plan. REQUEST 0 (`PipelineConfig.extra_styles` + `keyframes.load_sdxl_pipeline()` LoRA stacking) is owned by the compositing chat per Luca's 2026-05-18 redirect; parent chat does not pursue. Workstream log is private during v0.1; surfaces publicly in v0.2 as `docs/manual/compositing.md`. |
| Phase 4.2 | Webcam depth-as-noise (live) | **Deferred** | TBD | Post-release |
| Phase 4.4 | Anchored live prompting | **Deferred** | TBD | Post-release |

## Pending parent-chat actions (next-up)

The three originally-queued items are CLOSED (done 2026-05-17). Optional follow-ups remain queued; pick them up when Luca redirects or the gating conditions land.

Closed today:

1. ~~Wire `noise:` field into PipelineConfig + Pipeline.~~ **Done 2026-05-17.** `NoiseConfig` dataclass on `RenderProfile.noise`. YAML shape: `render.noise.kind` (`evolved` / `perlin` / `worley` / `simplex` / `fbm` / `image_derived` / `frequency_banded`) + `render.noise.params`. `walk_rate` inherits from `RenderProfile.noise_walk_rate` when not supplied in params. Factory `build_noise_source(config)` in [src/slow_interpolation/noise/__init__.py](../../src/slow_interpolation/noise/__init__.py); recursive sub-source support for `frequency_banded` (params.sources is a list of `{kind, params}` dicts). `Pipeline.generate_keyframes()` calls the factory.
2. ~~Bump `RIFEConfig.edge_crop` default 8 → 0.~~ **Done 2026-05-17.** Default flipped in [src/slow_interpolation/config.py](../../src/slow_interpolation/config.py); [examples/configs/tcole_valley.yaml](../../examples/configs/tcole_valley.yaml) carries an explicit `edge_crop: 0` line with a comment pointing at the [border-crop finding](../findings/border-crop.md).
3. ~~Scaffold `examples/configs/renoir/`.~~ **Done 2026-05-17.** Four templates landed: `roses_vase_60s.yaml`, `anemones_60s.yaml`, `mixed_bouquet_60s.yaml` (calm profile), `peony_closeup_portrait_60s.yaml` (transposed 768x1344 portrait). Trigger `rfl`, lora_scale 0.80, edge_crop 0, negative_prompt scaffold from `lora-training.md` section 8. All four parse green. LoRA path placeholder `models/loras/Renoir_Flowers_epoch_10.safetensors` (update once training drops the actual filename). README at [examples/configs/renoir/README.md](../../examples/configs/renoir/README.md) documents the swap procedure.

Open optional follow-ups:

4. **Plan compositing workstream as `docs/compositing-design.md`**, most useful once Renoir LoRA exists + noise sources wired (noise side now done). ~45 min.
5. **GPU contact-sheet renders for the noise palette**, the Noise chat is unblocked: run `harness.py --full-pipeline --noise-set structured` against `tcole_valley.yaml`, then against a `renoir/*.yaml` once the LoRA lands. Owned by the Noise parallel chat now that the wiring is in.
6. **LoRA training pipeline export**, when Luca finishes the Renoir LoRA training on CivitAI in the other chat, ask that chat to export the strategy + pipeline as a reusable recipe for future LoRAs. Land it in [docs/findings/lora-training.md](../findings/lora-training.md) (Renoir specifics) AND a new [docs/findings/lora-pipeline.md](../findings/lora-pipeline.md) (generic recipe) that future domain LoRAs follow without re-deriving. See "LoRA pipeline export plan" section below.

## Phase 2 deliverables (port, done)

Source tree:

- [src/slow_interpolation/](../../src/slow_interpolation/), package: `config`, `pipeline`, `keyframes`, `smoothing`, `borders`, `prompts`, `encoding`, `run`, `noise/evolved_walk`, `interpolation/rife`.
- [vendor/rife_v425/](../../vendor/rife_v425/), re-vendored RIFE v4.25 inference code (24 MB, MIT).
- [examples/configs/tcole_valley.yaml](../../examples/configs/tcole_valley.yaml), reference port-acceptance config.
- [tests/test_evolved_walk.py](../../tests/test_evolved_walk.py), 6 unit tests, all green.

Acceptance:

- 2A (foundation, no GPU): config loads, evolved_walk tests pass.
- 2B (Phase A keyframes, GPU): 26 PNGs at 1344x768, 24 min wall time, no border artifacts, Cole LoRA active.
- 2C (Phase C+D RIFE + H.264, GPU): `outputs/tcole_valley.mp4`, 1328x752, 24 fps, 1429 frames, 59.54 s, 6.8 MB, 919 kbps. Envelope matches legacy samples exactly.

CLI: `python -m slow_interpolation.run examples/configs/tcole_valley.yaml`.

## Cross-chat coordination

Four workstreams run in parallel against this repo. To avoid merge conflicts, each workstream writes its own progress sub-doc; this `progress.md` is the master integration surface and is owned only by the parent chat.

### File ownership matrix

| Workstream | Status doc | Writes (free) | Reads only | Coordination on (request-and-wait) |
|---|---|---|---|---|
| Phase 3.5 Modal infra | [workstreams/modal/progress.md](workstreams/modal/progress.md) | `cloud/*`, `docs/modal.md`, `tests/test_modal_*.py` | `src/*`, `docs/pipeline.md`, `docs/dependencies.md`, `docs/inventory.md`, `docs/outputs.md`, `vendor/*` | extending `src/slow_interpolation/encoding.py` for upscale, or any other change in `src/` |
| Phase 3 Renoir dataset | [docs/renoir-dataset-progress.md](workstreams/renoir-dataset/progress.md) | `datasets/renoir-flowers/*` (gitignored), `docs/findings/lora-training.md` | most of the repo | nothing (research-only) |
| Phase 3 Noise research | [workstreams/noise/progress.md](workstreams/noise/progress.md) | `src/slow_interpolation/noise/sources/*` (new), `src/slow_interpolation/noise/base.py` (new), `src/slow_interpolation/noise/harness.py` (new), `docs/findings/noise-sources.md`, `tests/test_noise_sources.py` | most of the repo | wiring NoiseSource selector into `keyframes.py` / `pipeline.py` / `config.py` (done 2026-05-17) |
| **Parent (this chat)** | this `docs/planning/progress.md` | `docs/planning/progress.md`, the master `docs/findings/*`, anything not claimed above | the sub-progress docs | nothing |

Rules:

- A workstream NEVER edits `docs/planning/progress.md` directly. It updates its own sub-progress doc. The parent chat integrates milestones into this file.
- If a workstream needs to modify a file outside its writes list, it posts a request in its sub-progress doc and pauses. The parent chat makes the edit.
- If two workstreams need the same coordination edit, the parent chat sequences them.
- The parent chat watches the sub-progress docs and lifts notable decisions into the **Decisions log** below.

### Parallel chat launch prompts

Three prompts are drafted and ready to paste into separate chats. They are not stored in this repo (they are session-launching inputs, not artifacts); they live in the conversation history that produced this commit. Re-derive them from this `progress.md` + [docs/next-exploration-steps.md](../next-exploration-steps.md) + [docs/pipeline.md](../pipeline.md) if needed.

## LoRA pipeline export plan

The Renoir dataset workstream produced a working end-to-end LoRA dataset pipeline (source → triage → dedup → caption → Gemini-driven cleanup + crop → CivitAI ZIP), captured in [docs/renoir-dataset-progress.md](workstreams/renoir-dataset/progress.md) and [docs/findings/lora-training.md](../findings/lora-training.md). Luca is currently running the actual training on CivitAI in a separate chat.

**When training completes**, Luca will ask that chat to export a reusable LoRA pipeline strategy so future domain LoRAs (after Renoir: floral / Cézanne / others) can be trained without re-deriving the recipe. Two output documents:

- [docs/findings/lora-pipeline.md](../findings/lora-pipeline.md) (NEW, generic recipe), the abstracted strategy: source-priority order, subject-filter convention, dedup approach, captioning template (trigger word + slot vocabulary), Gemini-audit + multi-pass crop, CivitAI training settings as a starting point, validation hold-out design, expected-outcome grading. Subject-agnostic; just shows the recipe.
- [docs/findings/lora-training.md](../findings/lora-training.md) (EXISTING, Renoir-specific), keep as the worked example. Cross-link from `lora-pipeline.md` so a future LoRA workstream can read the recipe and then see how it was applied for Renoir.

Also produce / refresh:
- [docs/findings/dataset-hygiene.md](../findings/dataset-hygiene.md) (NEW), narrower than `lora-pipeline.md`. Focuses on the Gemini-driven multi-pass crop pipeline as a reusable utility. Used by any LoRA workstream, regardless of subject domain. Scripts already exist under `datasets/renoir-flowers/{gemini_review,apply_crops}*.py`; the doc generalises them.

Parent chat is responsible for receiving the LoRA pipeline export, integrating it into these docs, and updating [docs/planning/progress.md](progress.md) Phase 3 status to "Renoir LoRA trained + checkpoints in `models/loras/`, future LoRA pipeline documented".

## Decisions log

Permanent decisions worth remembering, with the why.

- **Subagent architecture pivot** (2026-05-19): four capability-domain subagents (modal, dataset-mosaic, lever, docs-curator) replace the older "parallel-workstream chats own per-folder write zones" framing for capability work. Workstreams are now time-bounded project logs (one folder per in-flight or shipped initiative under `docs/planning/workstreams/`); capability work (Modal dispatch, dataset curation, render tuning, docs curation) is invoked from any chat via the Agent tool. Workstream chats in flight keep their write-zone discipline as before; new capability work routes through subagents. Operating manuals: modal -> `docs/manual/modal-operations.md`; dataset-mosaic -> `dataset-curation.md` + `gallery.md` + `train-lora-on-modal.md` + `validate-lora.md`; lever -> synthesis across `manual/noise.md` + 5 findings + decisions log (no umbrella manual yet, deferred until patterns stabilise); docs-curator -> the agent file itself. Routing decision (local vs Modal) lives inside the modal agent with cost-vs-time awareness; hardware-routing.md feeds modal-agent's brief rather than being a separate page anyone reads pre-invocation. Validation lives inside dataset-mosaic's "ship a LoRA" arc; `validate-lora.md` also stands alone as an independently-callable manual page for re-validation outside the curation-to-train loop. Runtime caveat: Claude Code does not currently load project-local custom agent types; invoke via `general-purpose` with the agent file as operating prompt (verified pattern from `docs-curator`).

- **No sibling-folder dependencies** (2026-05-14): `grep -rE "Choire|After Cole" src/ vendor/` must return nothing. RIFE re-vendored; LoRA paths config-resolved.
- **RIFE v4.25 pinned** (not v4.26): better non-video flicker behavior, looser resolution-divisibility (32 vs 64).
- **diffusers 0.30 to <0.40 pinned**: 0.31+ has a Kohya-LoRA text-encoder regression handled by the UNet-only fallback in `keyframes.py`.
- **UNet-only LoRA loader fallback**: catches the `IndexError: list index out of range` in `get_peft_kwargs` for Kohya-format text-encoder LoRA keys. Style LoRAs live ~95% in UNet; this is style-equivalent.
- **Frame-for-frame match is NOT a port acceptance criterion**: the evolved noise walk is not seed-controlled and SDXL Lightning sampling is non-deterministic. Visual equivalence + no artifact regressions is the bar.
- **2 GB of LoRA checkpoints copied to `models/loras/`** (gitignored): Cole epochs 1 + 10, Casa del Suono epoch 4. Repo self-contained for the active LoRAs.
- **Phase 4.2 + 4.4 deferred until after the Renoir release** ([docs/next-exploration-steps.md](../next-exploration-steps.md) line 100 policy, re-affirmed 2026-05-15).
- **Phase 3 scope expanded** (2026-05-15): not just "swap LoRA + new subjects", but also folds in offline-scope noise research (was Phase 4.1) and offline dual-prompt compositing (was Phase 4.3). Live versions remain deferred.
- **Phase 3.5 Modal targets the port, not the legacy** (2026-05-16): the legacy can't actually run in a container without re-creating the sibling Choire folder layout. The port handles config-driven runs cleanly. Modal wraps `python -m slow_interpolation.run <config.yaml>`.
- **1920x1080 upscale-target resolution path: render at 1344x768 native, upscale post-RIFE pre-encode** (2026-05-16): SDXL's 16:9 training bucket is 1344x768. Rendering native 1920x1080 reintroduces border artifacts. Upscale in the encoder stage. Superseded by the 2026-05-18 1536x896 + A100-80GB finding below for any 1920x1080+ upscale target.
- **EDGE_CROP=0 is the new default for SDXL training-bucket renders** (2026-05-16, code change 2026-05-17): empirical test on tcole and Casa del Suono (the historically worst LoRA for arch artifacts) showed zero border artifacts at `edge_crop=0`. The two upstream mitigations (`crops_coords_top_left` + `edge_suppression_callback`) handle suppression. See [docs/findings/border-crop.md](../findings/border-crop.md). `RIFEConfig.edge_crop=0` default applied 2026-05-17; per-LoRA regression risk for Renoir is flagged in `lora-training.md` section 7.
- **NoiseSource selector schema** (2026-05-17): `render.noise = {kind, params}`, with `walk_rate` inherited from `RenderProfile.noise_walk_rate` for the WalkingNoiseSource family. `frequency_banded` carries recursive sub-source specs via `params.sources` (list of `{kind, params}`). Schema chosen over alternatives (sibling-of-render, flat `noise_kind`+`noise_params`) because rendering profile + walk rate live together on `RenderProfile`, so the noise selector belongs there too. Default kind `evolved` preserves the legacy behavior.
- **Modal infra shipped at 0.07 USD per 60s loop on L40S** (2026-05-17): the conservative 5 USD ceiling has 70x headroom. Renoir can plan against ~0.10 to 0.50 USD per render, not the original ~1 to 5 USD estimate.
- **1536x896 + A100-80GB is the new source-resolution path for 1920x1080+ upscale targets** (2026-05-18): supersedes the 1344x768 + lanczos plan from 2026-05-16. See [findings/upscale-source-resolution.md](../findings/upscale-source-resolution.md). Renoir release inherits pending a Renoir-LoRA-specific re-probe alongside Modal T1#2.
- **SCI_ART BC 2026 application dropped** (2026-05-18): Luca pulled out of the SCI_ART residency application. Phase SCI_ART removed from the active plan. The workstream's docs (`workstreams/sci-art/`) were deleted. Technical findings produced during the brainstorm (the 1920x1080 upscale-target path, the 1536x896 source-resolution probe) survive in their generic form and continue to feed the Renoir release.
- **Civitai payment system is split across two domains** (2026-05-17, learned during the Renoir LoRA training submission): yellow Buzz (crypto-purchased, the legacy unrestricted currency) lives on civitai.red; green Buzz (credit-card purchased) lives on civitai.com; blue Buzz (engagement-earned) works on both. The split happened because payment processors (Visa, Mastercard, PayPal) refused to process for the NSFW-tolerant front. For SFW work like the Renoir LoRA either side works; the choice is "which currency do you already have". Source: [civitai.com/articles/28369](https://civitai.com/articles/28369/two-front-doors-civitaicom-civitaired-and-whats-next). Document this in `docs/findings/lora-training.md` so the next student knows.
- **Civitai's default training engine is AI Toolkit, not Kohya** (2026-05-17): the Renoir LoRA baseline used AI Toolkit (Network Dim 32, Alpha 32, UNet LR 5e-4, Adafactor, 2 repeats) per Civitai's new defaults. The lora-training.md §3 spec targets Kohya (Dim 16, Alpha 8, 3e-5, AdamW8bit, 6 repeats). They produce different LoRAs. The Modal trainer is built around Kohya / sd-scripts per the canonical spec; the CivitAI baseline is treated as one valid output, not THE reference. Future LoRA workstreams pick engine per workflow (CivitAI = AI Toolkit defaults; Modal trainer = Kohya spec).
- **Epoch 1 is the better default for outdoor / field renders on the Renoir LoRA, NOT epoch 10** (2026-05-18, from the validation grid): empirical result. The auction-catalogue cast (48 of 105 training images) caused epoch 10 to over-fit a "photo of a painting" surface that suppresses painterly atmosphere on outdoor subjects. Epoch 1 (light) preserves impressionist atmosphere for fields better than epoch 10 (strong). For vase/bouquet still life the original spec holds: epoch 10 at scale 0.75 to 0.85. The `examples/configs/renoir/*.yaml` currently scaffold epoch 10; a new `flower_field_60s.yaml` should target epoch 1 instead. Documented in [workstreams/renoir-dataset/validation-grid.md](workstreams/renoir-dataset/validation-grid.md).
- **Before dispatching any Modal training, `modal app list` first** (2026-05-18, parent-chat operational protocol). The parent chat launched a duplicate Soutine trainer (`ap-mHXl8zSwIOUCWc4iYKQsQj` at 15:53) while the modal-trainer parallel chat already had one running (`ap-cXqidg0QpqWA4bcTp68J2M` at 15:46). Caught early, stopped, ~$0 wasted (image-build phase only). Going forward, parent chat runs `modal app list | grep ephemeral` before any `modal run -m cloud.train_*` dispatch and confirms with Luca if an existing trainer app is on the same family/dataset. Cost of the check: ~3 seconds. Cost of the duplicate caught late: 45 min wall + ~$1.50.
- **`modal app stop` requires `--yes` for non-interactive use** (2026-05-18, minor SDK quirk). Without it, the CLI prompts `Are you sure...? [y/N]` and aborts when stdin is non-interactive. Piping `echo y` does NOT satisfy it. Use `modal app stop <app-id> --yes`. Worth a single-line addition to [findings/modal-sdk-quirks.md](../findings/modal-sdk-quirks.md) (modal-trainer chat's write zone); filed as a passive note here since the quirk is small.
- **Modal is the production training engine for slow-interpolation; CivitAI is shelved** (2026-05-18, two-confirmation rule fires). Renoir bake-off 2026-05-17 (Modal beat CivitAI on the validation grid). Soutine bake-off 2026-05-18 (Modal beat CivitAI again per modal-trainer parallel chat verdict; formal entry pending in their `progress.md`). Two consecutive subject families with Modal winning closes the comparison loop. Going forward, all new domain LoRAs (Cézanne, Bonnard, future) train on Modal via `cloud/train_entrypoint.py` + `examples/configs/training/<family>.yaml`. CivitAI remains documented as an optional alternative in `docs/manual/dataset-curation.md` Phase 5 for students who already have a CivitAI account; not required. Workshop-on-Modal-only ToS is now durable.
- **CivitAI presigned download URLs live in `__NEXT_DATA__.trainingResults.epochs[]`** (2026-05-18, learned while retrieving the CivitAI Soutine baseline). The wizard page exposes per-epoch `modelUrl`s (presigned, 7-day expiry) directly in the Next.js page data. Curling these is ~10× faster than browser-mediated downloads and lets you cherry-pick keepers (epoch 1, 5, 10) instead of pulling all 10. Source: `civitai.red/models/<id>/wizard?step=1&modelVersionId=<v>`, Playwright `evaluate` walking `__NEXT_DATA__`. Promote to a finding doc after the third confirmed use; for now documented inline here so the next dataset workstream agent doesn't re-derive it.
- **First 60s flower-field clip renders at $0.046 on L40S** (2026-05-18): new `examples/configs/renoir/flower_field_60s.yaml` against the CivitAI epoch-1 baseline produced `outputs/renoir_wildflower_field.mp4` in 84.6s wall (A 39s, A.5 16s, C+D 27s). Confirms the 0.07 USD cost envelope from the Modal cold-run holds for Renoir at 1344x768. Inference-time negative prompt extended to include `signature, watermark, text` as the cheap pre-inpaint mitigation. The clip is the first production-scale evidence that the CivitAI baseline is shippable for the objkt labs release on flower-field subjects, pending Luca's visual sign-off.
- **Default render target is local, Modal opt-in when local is insufficient or parallelism is worth the cost** (2026-05-18). Reframes the noise workstream's 2026-05-17 "Modal is default for multi-variant tests" decision. The new universal protocol is at [`manual/hardware-routing.md`](../manual/hardware-routing.md): pre-flight detects hardware (`nvidia-smi`, torch CUDA, HF cache disk free, GPU busy), decision table routes by render-type + local-capability, trade-offs named, dispatch commands given, cache at `outputs/_hardware.json` skips re-detection within 30 days. Modal credit is finite; reserve for work that genuinely needs cloud (large batches, A100/H100 tiers, parallel sweeps, GPU-occupied local). The local-iterate / Modal-release hybrid is the recommended default for multi-render projects. [`findings/monitoring-long-cloud-jobs.md`](../findings/monitoring-long-cloud-jobs.md) is now positioned as the Modal-branch operating playbook downstream of the routing decision. Cross-notice posted to [`workstreams/noise/progress.md`](workstreams/noise/progress.md) to reframe their local decision-log entry on next session.
- **Border-arch artefact concern is Casa-del-Suono-LoRA-specific, not generic** (2026-05-18, Luca empirical call): no border artefacts observed on the first 60s Renoir flower-field clip at `edge_crop: 0`. The historical failure mode came from the Casa del Suono LoRA's fresco-lunette training data (hard architectural framing). The Renoir LoRA training set has no framed paintings, so the failure mode does not transfer. **Modal T1#2 "Renoir border probe" is cancelled.** Going forward, border-arch is a per-LoRA risk indexed by training-data framing (auction-catalogue scans, fresco panels, religious-icon panels), not a generic concern requiring a per-release probe. Recorded in [findings/border-crop.md](../findings/border-crop.md) Caveats section.
- **Renoir+Soutine compositing: A/B/C/A field backgrounds stay subject-locked** (2026-05-18): the standalone Renoir flower-field test clip drifted meadow → poppies → cornflowers across A/B/C, which reads correctly for a standalone Renoir piece but competes with the foreground figure in the compositing project. Compositing background configs must keep a single floral species across the loop; the A/B/C drift dimensions are time-of-day, light direction, palette key, ground-tone, weather, not species. Standalone Renoir configs (no figure foreground) are exempt. Constraint recorded in the compositing workstream log (private during v0.1; surfaces in v0.2).
- **Impressionist read on epoch 1 + scale 0.85 is too thin for a Renoir release** (2026-05-18, Luca visual call on the first 60s clip): brushwork insufficiently abstracted, especially across grass passages. Re-render v2 at `examples/configs/renoir/flower_field_60s_v2.yaml` (epoch 5, scale 1.0, prompts leading with `impasto, palette-knife passages, broken color, abstracted forms`, negative extended with `smooth, detailed, fine`) shipped as `outputs/renoir_wildflower_field_v2.mp4` in 78.1s wall / $0.04. Updates the validation-grid "Practical recommendation" table: for outdoor/field renders **at full pipeline scale** (not just keyframe grading), epoch 5 at scale 1.0 supersedes epoch 1 at scale 0.85 as the default. Epoch 1 stays the right call for keyframe grading because it preserves atmosphere on a single render, but at 60s loop scale the LoRA influence needs to be stronger to read painterly.
- **Workshop-on-Modal-only is the workshop ToS** (2026-05-18): the modal-trainer cold-run, when validated, will close the story (curate locally → train on Modal → inpaint on Modal → render on Modal, no third-party vendor accounts). Until then CivitAI is the documented fallback for LoRA training and fal.ai is the documented fallback for inpainting; both are mentioned but not required. Inpaint Phase 3 (Modal SDXL Inpaint + the trained LoRA) is the canonical inpaint path; Phase 1 / 2 (Stability Erase, fal.ai FLUX Fill) are documented alternatives for students who want them.
- **`PromptConfig.negative_prompt` per-segment override shipped** (2026-05-18 evening, narrative-arc drift work). New optional field on [`PromptConfig`](../../src/slow_interpolation/config.py), with [`keyframes.py`](../../src/slow_interpolation/keyframes.py) using it on encode with `style.negative_prompt` as fallback. Backwards-compatible. Motivated by the rose lifecycle test (v5): a flowers LoRA whose training centres on full-bloom paintings dominates the warmup-as-text2img first frame regardless of positive prompt language. Per-prompt CFG negatives on A and A-return ("roses, blooms, full bloom, open petals, flowers, petals, floral, blossoms, buds, pink") suppress the bias without weakening B and C, which keep the style-level negative. Documented in [`docs/findings/narrative-arc-drift.md`](../findings/narrative-arc-drift.md) Finding 1. Per-prompt `lora_scale` override is **not** part of this change; deferred to an unfuse/refuse cycle if v6 banded-noise test does not close the remaining prompt-change blur.
- **Loop-closure defaults are palette-drift tuned, content-drift loops override in YAML** (2026-05-18 evening). The defaults `return_pixel_blend_max: 0.20`, `return_strength_end: 0.60`, `frames.return_: 4` were tuned on Choire v2 and After Cole reference loops where the A/B/C/A arc is a palette / light drift on stable composition. Narrative-arc loops (subject identity or biological-state change between A and C) under-converge at these defaults and produce a visible hard cut at the wraparound. Override starting point from rose lifecycle v5 (Luca verdict: "loop now reads much more smooth"): `return_pixel_blend_max: 0.55`, `return_strength_end: 0.45`, `frames.return_: 10`. Tune `pixel_blend_max` 0.40-0.65, `return_` 8-14, `strength_end` 0.40-0.50. Defaults stay; content-drift configs declare overrides. Documented in [`docs/findings/narrative-arc-drift.md`](../findings/narrative-arc-drift.md) Finding 2.

## Phase 3: the expanded plan (working draft)

Goal: ship the Renoir series for the objkt labs Spring 2026 residency, with a more loaded technique than "same pipeline, new LoRA". Pure offline rendering. No live work in this phase.

Four parallel-ish workstreams:

1. **Renoir LoRA training and best practices.** Owner: parallel chat (Phase 3 Renoir dataset).
   - Dataset: 80 to 200 Renoir flower/floral paintings from WikiArt + museum public-domain. Captioning template "rfl, ..." (Kohya-style trigger word).
   - Training: SDXL on CivitAI by Luca, same playbook as Thomas Cole. Findings doc co-authored by the parallel chat.
   - Two checkpoints minimum (light + strong).
   - Border-artifact probe (per the [border-crop](../findings/border-crop.md) caveats) before locking the EDGE_CROP=0 default for Renoir.

2. **Renoir subject suite.** Owner: this chat (after LoRA is trained).
   - 3 to 7 A/B/C/A subjects appropriate to Renoir's vocabulary (flower vases, bouquets, garden close-ups, single blooms).
   - YAML configs under `examples/configs/renoir/`.
   - Render at 1344x768 native (or transpose to portrait, decision pending with the release curator).

3. **Noise as authoring surface (offline).** Owner: parallel chat (Phase 3 Noise).
   - `NoiseSource` interface in `src/slow_interpolation/noise/`.
   - Implementations: structured (Perlin / Worley / simplex / FBM), image-derived, frequency-banded.
   - Comparison harness: render the same A/B/C subject across 5+ noise sources, contact sheet.
   - Goal: identify a noise palette specific to Renoir florals.

4. **Dual-prompt, dual-noise compositing (offline).** Owner: TBD, currently deferred.
   - Background path: flower hills + grasslands, Renoir LoRA, soft / impressionist.
   - Foreground path: human silhouettes, different LoRA or style prefix.
   - Mask source: TBD (see open questions below).
   - Two parallel diffusion paths composited in latent space with a feathered mask.
   - Speed differential: background drifts at standard pace; foreground evolves at a different effective rate.

Open questions to resolve before workstream 4 can start:

- **Silhouette source.** Pre-recorded performer video with depth/segmentation extracted offline, hand-painted static silhouettes that drift via the standard segment structure, silhouettes drawn from adjacent GAN-based projects, or procedural (Perlin-thresholded). Default lean: pre-recorded performer video if available, otherwise procedural.
- **Speed differential mechanism.** Different RIFE pass counts per layer, different keyframe densities per layer, or different denoise schedules per layer. Default lean: different denoise schedules (cleanest within existing pipeline).
- **Foreground LoRA / style.** Renoir LoRA (visually unified) or contrasting LoRA (figurative drawing, woodcut, charcoal). Default lean: contrasting.

## Phase 3.5: Modal cloud-render infrastructure (general purpose)

Goal: a documented, reusable Modal.com deployment that wraps `src/slow_interpolation/` so GPU-heavy work runs in the cloud, with reproducible runs, downloadable artifacts, and clear documentation that future projects can build on. **Infrastructure only.** Downstream consumers (Renoir release, future compositing prototype) are separate workstreams.

Owner: parallel chat. Status doc: [workstreams/modal/progress.md](workstreams/modal/progress.md).

Exit criterion: a Modal run against `examples/configs/tcole_valley.yaml` produces visually equivalent output to the Phase 2C local reference (`outputs/tcole_valley.mp4`) plus a run-manifest JSON, downloadable from the Modal volume. `docs/modal.md` lets a fresh reader run an arbitrary config end-to-end. Cost stays under 5 USD per 60s loop.

See the "Cross-chat coordination" section above for file ownership rules.

## Phase 3: working timeline (provisional)

Pinned to the objkt labs schedule.

| Window | Activity |
|---|---|
| W1 | Release-curator call: lock release date, edition, length, pricing. Modal infra in progress. Renoir dataset curation in progress. Noise research in progress. |
| W2 | First Renoir LoRA training pass. Noise sources prototype. |
| W3 | Second Renoir LoRA training pass (refined). First Renoir A/B/C renders. Compositing workstream spawnable. |
| W4 | First full Renoir + dual-layer renders. |
| W5 onward | Release-cut renders. Hand-off to the curator. |

This is illustrative. The curator's lock-in call resets the windows.

## Findings docs

Per [next-exploration-steps.md](../next-exploration-steps.md) cross-cutting concern about composability:

- [docs/findings/border-crop.md](../findings/border-crop.md), EDGE_CROP=0 empirical test, done 2026-05-16.
- `docs/findings/lora-training.md`, written by the Renoir-dataset parallel chat.
- `docs/findings/noise-sources.md`, written by the Noise-research parallel chat.
- [docs/findings/narrative-arc-drift.md](../findings/narrative-arc-drift.md), narrative-arc slow drift on off-distribution endpoints, written by this parent-chat session 2026-05-18 (rose lifecycle test). Ships the per-prompt `negative_prompt` schema extension and the loop-closure tuning for content-drift loops. Finding 3 (banded noise as transition-blur antidote) is in flight pending v6 verdict.
- `docs/findings/compositing.md`, written later, after compositing workstream spawns.

## Post-release backlog

- Phase 4.2 (webcam depth-as-noise live).
- Phase 4.4 (anchored live prompting).
- Both are gated on the Renoir release going out and on StreamDiffusion's SDXL support being confirmed mature enough on 8 GB VRAM.
- Open-source release on GitHub: cleanup pass after the live work has informed the right abstractions.

## Documentation hygiene

Tracker for the docs-tree migration. Strategy: [docs-strategy.md](docs-strategy.md). Reframed 2026-05-17 from "close-and-consolidate" to "pause-and-self-migrate".

### Phase D1 (shipped 2026-05-17)

Entry-point docs landed. README.md rewritten, AGENTS.md and CONTRIBUTING.md added at root, docs/README.md as the docs-tree map, docs/manual/{index,getting-started}.md as the user-manual seed, .github/ISSUE_TEMPLATE/{finding,experiment-report}.md as the contribution funnels, contribute-back footer appended to every `docs/findings/*.md`.

### Phase D2 prep (shipped 2026-05-17)

- `docs/progress.md` -> `docs/planning/progress.md`. Internal relative links fixed.
- `docs/kickoff-prompt.md` -> `docs/planning/kickoff-prompt.md`.
- `tools/check_doc_links.py` added. Walks markdown and reports broken relative links.
- Self-migration instruction blocks embedded in each of the in-flight workstreams' `*-progress.md` (modal, noise, renoir-dataset, compositing).
- Strategy doc updated: D2 reframed to "self-migrate on next active session", with a copy-paste playbook each chat follows.

### Phase D2 firing (rolling, per chat)

Status per workstream. Updated when each chat self-migrates.

| Workstream | Migration block embedded | Self-migration done | New path |
|---|---|---|---|
| Modal | yes (2026-05-17) | **done 2026-05-18** | `docs/planning/workstreams/modal/` (progress + followup-plan + release-batch) |
| Noise | yes (2026-05-17) | **done 2026-05-18** | `docs/planning/workstreams/noise/` |
| Renoir-dataset | yes (2026-05-17) | **done 2026-05-18** | `docs/planning/workstreams/renoir-dataset/` (progress + gallery-manual-notes + inpaint-plan) |
| Compositing | yes (2026-05-17) | **done 2026-05-18** | `docs/planning/workstreams/compositing/` (progress + design) |

### Link-check baseline

`python tools/check_doc_links.py` reports **8 broken relative links** as of 2026-05-18 (the link-checker skips paths inside backtick code spans). Categorisation:

- **6 forward-references** to docs that do not yet exist: 5x `findings/lora-pipeline.md` (lands at the Renoir LoRA export) + 1x `manual/pipeline.md` (lands at D3, see [pipeline-split-decision.md](pipeline-split-decision.md)). Acceptable.
- **1 forward-reference** to `planning/workstreams/compositing/design.md` from CONTRIBUTING.md, now real (compositing migrated 2026-05-18; this should green on next run).
- **1 self-migration leftover** in `findings/lora-training.md` (renoir-dataset-owned, will green when Renoir-dataset chat does its findings-link sweep).

Expectation: 1 broken after the next migration commit settles, then 0 once the lora-pipeline.md and manual/pipeline.md targets land.

Historical: 23 broken pre-D2 (2026-05-17 evening), 14 mid-D2 (workstream chats partially migrated), 8 post-D2 (all four workstream self-migrations done 2026-05-18; the SCI_ART workstream was killed 2026-05-18 and its docs removed).

## Findings curation status

Tracker for `docs/findings/` consolidations. Findings docs live independently of workstreams; consolidation is rolling, not gated on any phase.

### Pending consolidations (approved 2026-05-18 after docs-curator pass)

1. **LoRA cluster -> `lora-pipeline.md` + refined `lora-training.md`.** APPROVED 2026-05-18. Coordination request posted to [workstreams/renoir-dataset/progress.md](workstreams/renoir-dataset/progress.md) "Job 1" + cross-notice to the Modal-trainer workstream (private during v0.1) for engine-section review. Sources: `findings/lora-training.md` (310 lines, Renoir-specific), `findings/lora-training-deep-dive.md` (397 lines, modal-trainer authored), `findings/kohya-vs-ai-toolkit-renoir.md` (113 lines, modal-trainer authored), `findings/style-vs-subject-lora.md` (107 lines, Compositing authored). Target shape: `findings/lora-pipeline.md` (NEW, generic recipe) + `findings/lora-training.md` (refined to Renoir-specific worked example; filename retained to avoid 26-file ref-fix-up unless Renoir-dataset chat takes the rename atomically). Sequencing in the coordination request. ETA: next Renoir-dataset session.
2. **`dataset-hygiene.md` -> `dataset-practice.md` merge.** APPROVED 2026-05-18. Coordination request posted to [workstreams/renoir-dataset/progress.md](workstreams/renoir-dataset/progress.md) "Job 2". The 45-line placeholder folds into `dataset-practice.md` as a new "Gemini audit + multi-pass crop" section. Delete the placeholder after merge. ETA: next Renoir-dataset session.

### Recently shipped (2026-05-19 docs-curator pass)

- `docs/manual/validate-lora.md` (NEW). Family-agnostic agent-facing LoRA validation protocol. 5-phase shape (author YAML, route, dispatch one Modal run per epoch, build comparison viewer, walk user through 5-signal checklist, record verdict). Crystallised from the Renoir + Soutine validation grids and `cloud/validate_lora.py` (which already de-Renoir-hardcoded itself; the protocol was operationally proven across both families). Registered in `docs/manual/index.md` "Available protocols" dispatcher + reading order. Promoted from the curator's "Coverage gaps" list.
- `docs/manual/index.md`. Added validate-lora row to "Available protocols" + reading-order item 8.
- Verified the Soutine validation-grid path bug (30 of 46 link-check breaks). Image bytes exist on disk at `outputs/validation/soutine-{civitai,modal-v2}/epoch-{1,5,10}/<slug>.png`; the grid markdown uses an obsolete flat schema `outputs/validation/soutine-epoch-{N}/`. Coordination request posted at the top of `workstreams/soutine-lora/progress.md`.

### Recently shipped (2026-05-18 docs-curator pass)

- `docs/manual/noise.md` (NEW). Agent-facing decision-table protocol crystallised from `findings/noise-sources.md`. Spatial-frequency lever as primary axis, 6-row decision table indexed on motion character, troubleshooting table. Findings doc retained as deep reference.
- `docs/findings/lora-training.md`. Banner added flagging Modal as canonical training path; CivitAI section archival.
- `docs/training.md`. Trimmed from 344 lines to ~20-line pointer at `manual/train-lora-on-modal.md`.
- `docs/planning/workstreams/renoir-dataset/gallery-manual-notes.md`. Deleted; content lives at `manual/gallery.md`.
- `docs/planning/workstreams/modal-trainer/kickoff.md`. Fixed doubled-path link to `../renoir-dataset/validation-grid.md`.

### Recently shipped findings (pre-2026-05-18)

- `docs/findings/border-crop.md` (2026-05-16). EDGE_CROP=0 empirical probe. Verdict applied as default.
- `docs/findings/noise-sources.md` (2026-05-16 to 2026-05-17). 7-source catalog + visual readings + spatial-frequency lever discovery. Now also surfaced as `manual/noise.md`.
- `docs/findings/inpainting-options.md` (2026-05-17). Ranked inpainting providers for dataset cleanup; FLUX [dev] LoRA on fal.ai recommended.
- `docs/findings/lora-training-deep-dive.md` (2026-05-18). Theory + objectives + hyperparameters + tools beyond CivitAI. Pending consolidation into `lora-pipeline.md`.
- `docs/findings/kohya-vs-ai-toolkit-renoir.md` (2026-05-18). Engine head-to-head with measured numbers. Verdict feeds `lora-pipeline.md`.
- `docs/findings/style-vs-subject-lora.md` (2026-05-18). Dataset composition determines LoRA regime. Pending consolidation into `lora-pipeline.md`.
