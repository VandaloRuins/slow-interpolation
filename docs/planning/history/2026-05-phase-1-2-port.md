# Phase 1 + 2: legacy consolidation and port (2026-05-14 to 2026-05-17)

Retrospective on the three-and-a-half-day push that took `slow-interpolation` from "empty repo with a kickoff prompt" to "scripted Python pipeline matching the legacy reference output, plus five live parallel workstreams". Written 2026-05-17 while context is fresh, intended as the durable record of what was built, why, and what was rejected.

## What shipped

### Phase 1: consolidate + document the legacy (Kickoff Steps 1 to 5)

The repo started with two parallel legacy pipelines in `legacy/`: Choire v2 (vertical fresco videos) and After Cole (horizontal Hudson River School landscapes). Both ran as standalone Python scripts that reached into a sibling Choire v1 folder (`$DESK/Choire/visuals/`) for LoRA weights, RIFE checkpoints, and a working ESRGAN venv. The same technique, two implementations, no single source of truth.

Step 1 (consolidation) produced:

- [docs/inventory.md](../../inventory.md): every file in `legacy/` annotated with what it does, what calls it, what it depends on.
- [docs/pipeline.md](../../pipeline.md): the technical reference, written against both legacy variants. Covers the four phases (A keyframes, A.5 smoothing, C+D RIFE+encode), every parameter, every callback, the SDXL micro-conditioning trick (`crops_coords_top_left`), the latent edge-suppression callback, the SLERP-of-embeddings transition, the evolved noise walk, and the wrap-around loop closure.
- [docs/outputs.md](../../outputs.md): catalogue of every MP4 under `examples/outputs/` with the config that produced it.
- [docs/dependencies.md](../../dependencies.md): the external-resource map. Crucial input for the port (the sibling-folder dependency on Choire v1 visuals was the load-bearing blocker; resolving it cleanly was a Phase 2 acceptance criterion).
- A long pass through [docs/next-exploration-steps.md](../../next-exploration-steps.md) to align on what Phase 3+ should chase.

Time: 2026-05-14 to 2026-05-15. About 1.5 days, mostly read-and-write.

### Phase 2: port the pipeline (Phase 2A + 2B + 2C)

The objective: turn the legacy scripts into a clean Python package at `src/slow_interpolation/` with zero sibling-folder dependencies. Run a config-driven CLI. Match the legacy reference output visually.

**Phase 2A (foundation, no GPU)** landed:

- `src/slow_interpolation/config.py`: `PipelineConfig` + `StyleConfig` + `RenderProfile` (with `.standard()` and `.calm()` factories) + `RIFEConfig` + `EncodingConfig` + `BorderSuppressionConfig` + `ModelsConfig` + `load_pipeline_config()`. Pure dataclasses, no Pydantic. YAML loader at the boundary.
- `src/slow_interpolation/noise/evolved_walk.py`: the persistent Gaussian noise walk extracted into a class (`EvolvedNoiseWalk`), with `reset()` + `blend()` API. Six unit tests covered drift, reset, shape-keyed restart.
- `src/slow_interpolation/{borders,prompts,smoothing,encoding}.py`: the supporting modules. SDXL micro-conditioning, SLERP of embeddings, frequency-separated smoothing (`sigma=1.5, window=8, blur_radius=16`), and the streaming H.264 writer.

**Phase 2B (Phase A keyframes, GPU)** landed:

- `src/slow_interpolation/keyframes.py`: `load_sdxl_pipeline()` + `generate_keyframes()`. The img2img chain with the calibrated denoise schedule, warmup, A/B/C/A-return segment loop, smoothstep-t SLERP transitions, anchor return with quadratic pixel blend.
- The diffusers 0.31+ Kohya-LoRA regression discovered: `get_peft_kwargs` crashes on empty per-key rank dicts when loading Kohya-format text-encoder LoRA keys. Fix: a UNet-only fallback in `_load_style_lora()` that catches the `IndexError` and reloads with `lora_te*` keys filtered out. Style LoRAs are ~95% UNet anyway.
- First full GPU run produced 26 keyframes at 1344x768 in 24 minutes. No border artifacts. Cole LoRA visibly active.

**Phase 2C (RIFE + encode, GPU)** landed:

- `vendor/rife_v425/`: re-vendored RIFE v4.25 (24 MB, MIT) into the repo so the sibling-folder dependency on Choire v1 was severed.
- `src/slow_interpolation/interpolation/rife.py`: `RIFEInterpolator` + `linear_interp()` (not recursive binary midpoint). 6 passes = 64x interpolation. `skip_boundary=4`. Wrap-around loop closure.
- `src/slow_interpolation/pipeline.py`: `Pipeline` orchestrator. `generate_keyframes()` -> `smooth_keyframes()` -> `interpolate_and_encode()`. `render()` runs all three.
- First end-to-end run produced `outputs/tcole_valley.mp4`: 1328 x 752, 24 fps, 1429 frames, 59.54 s, 6.8 MB, 919 kbps. Visually matched the legacy reference envelope exactly.

Time: 2026-05-15 to 2026-05-16. About 1.5 days, mostly debugging GPU loading + diffusers regressions.

### Phase 3 kickoff (2026-05-16 to 2026-05-17)

The scope expanded mid-port: not just "swap the LoRA + new subjects" but also fold in the previously-Phase-4 noise research (offline scope only) and offline dual-prompt compositing. Live-version work stayed deferred to post-release. Four parallel workstream chats launched:

1. **Modal cloud infrastructure** (general-purpose, opt-in, variant-friendly).
2. **Renoir floral LoRA dataset** (102 paintings curated, Gemini-driven cleanup pipeline, CivitAI ZIP ready).
3. **Noise sources research** (six implementations + ABC + harness + 49 tests).
4. **Compositing design** (dual-LoRA strategy, Soutine figure sub-workstream).

(A fifth SCI_ART BC 2026 brainstorm chat ran briefly during this window; the application was dropped 2026-05-18 and the workstream's docs were removed. The 1920x1080 upscale-target finding it surfaced survives in `findings/upscale-source-resolution.md`.)

Parent chat handled coordination: the cross-chat file ownership matrix, the integration into `docs/planning/progress.md` master log, the border-crop probe (EDGE_CROP=0 verdict), the noise YAML wiring (`render.noise.kind` + `params` + `walk_rate` inheritance, `build_noise_source(config)` factory), and the docs reorganisation (Phase D1 entry-point docs + D2 self-migration prep).

## Decisions worth preserving

- **No sibling-folder dependencies in `src/`.** Hard rule. `grep -rE "Choire|After Cole" src/ vendor/` must return nothing. LoRA paths resolved via YAML, RIFE re-vendored, the Choire v1 visuals folder is referenced only as a one-time copy source for the LoRA `.safetensors` (which then live under `models/loras/`, gitignored).
- **RIFE v4.25 pinned**, not v4.26. Better non-video flicker behaviour, looser resolution-divisibility (32 vs 64).
- **diffusers 0.30 to <0.40 pinned**, with the UNet-only LoRA fallback. Going to 0.31+ broke Kohya text-encoder LoRA keys; staying at 0.30 broke `FLAX_WEIGHTS_NAME` from transformers 5.x. The fallback was the cleanest exit.
- **Frame-for-frame match is NOT a port acceptance criterion.** The evolved noise walk is not seed-controlled and SDXL Lightning sampling is non-deterministic. Visual equivalence + no artifact regressions was the bar. Saved hours of trying to reproduce specific frames.
- **EDGE_CROP default 8 -> 0** after the 2026-05-16 empirical probe on tcole and Casa del Suono (the historically worst LoRA for arch artifacts). The two upstream mitigations (`crops_coords_top_left` micro-conditioning + the latent edge-suppression callback) handle border suppression on their own.
- **NoiseSource schema**: `render.noise.kind` + `params`, with `walk_rate` inherited from `RenderProfile.noise_walk_rate`. `frequency_banded` carries recursive sub-source specs. Default kind `evolved` preserves the legacy. Chosen over flat `noise_kind`+`noise_params` because the rendering profile + walk rate already live on `RenderProfile`.
- **Modal targets the port, not the legacy.** The legacy cannot run in a container without reproducing the Choire sibling-folder layout. The port handles config-driven runs cleanly; Modal wraps `python -m slow_interpolation.run <config.yaml>` plus a `modal:` YAML section for GPU tier and entry-point overrides.
- **`cloud/` package, not `modal/`.** Avoids sys.path shadowing of the Modal SDK on script-mode imports.
- **Docs reorganisation phased**, not all at once. D1 (entry-point docs) shipped 2026-05-17. D2 (per-workstream self-migration on next resume) shipped its prep the same day. D3 (the big post-Renoir-release reorg) waits until the release ships and all in-flight workstreams complete.

## What was rejected

- **Full upscale path enabled.** Real-ESRGAN x2 is wired in the legacy but destroys the fresco aesthetic. Disabled in the port. Decision parked for Renoir on a per-config basis.
- **Per-segment denoise schedule overrides.** Legacy had a 6-element ramp parameter that no entry-point script actually populated. Dropped from the dataclass surface.
- **`PromptConfig.denoising` field.** Present in legacy SUBJECTS dicts but never read. Dropped.
- **Multiple LoRAs at the style layer.** The dual-LoRA need for compositing belongs in the compositing-config surface, not the single-style API. Out of scope for the port.
- **A separate ComfyUI-compatible export.** The original Comfy workflow at `legacy/comfy-archive/` is an unrelated earlier experiment; carrying it forward would have wasted weeks and produced a worse codebase. Kept under `legacy/` as historical reference only.
- **CHANGELOG.md, formal CoC, GitHub Actions CI.** Considered for the docs reorg, rejected as premature for an experimental art repo at this scale.

## Open threads at the end of Phase 2

- The Renoir LoRA training run on CivitAI is in flight in a separate chat at the time of this writing. The four `examples/configs/renoir/*.yaml` templates are scaffolded with placeholder paths.
- The Noise chat is unblocked for GPU contact-sheet renders against the Renoir LoRA once it lands.
- Modal cold-run validated at 0.07 USD per 60s render on L40S. A 15-item Modal-followup-plan is actively shipping new features.
- Compositing chat has produced a substantial design doc (Soutine LoRA, dual-LoRA strategy, AI-generated figure videos). Implementation gated on Renoir LoRA + Soutine LoRA + figure-video generation.

## Lessons

- **Phased scope expansion is fine** as long as the master log captures it explicitly. The 2026-05-15 "Phase 3 scope expanded" decision was named in the decisions log, not silently merged in.
- **Parallel chat coordination needs a file-ownership matrix from day one.** Without one, the second parallel chat will inevitably want to touch a file the first claimed. The matrix in `docs/planning/progress.md` "Cross-chat coordination" section was load-bearing.
- **Findings docs decouple knowledge from workstreams.** `docs/findings/border-crop.md` outlives the border-test workstream. Closing a workstream doesn't lose the lesson.
- **Forward-references in docs are fine** if the target is named and gated. The `docs/findings/lora-pipeline.md` forward-references were placed before the file existed; the link-check baseline lists them as known-expected.
- **Self-migration beats parent-curated migration** when the parent chat is the only coordinator across many workstreams. Each chat that knows its own files migrates faster and more correctly than a parent chat doing it for everyone.

## Pointers for future readers

- For the current state: [docs/planning/progress.md](../progress.md).
- For the documentation tree: [docs/README.md](../../README.md) + [docs/planning/docs-strategy.md](../docs-strategy.md).
- For the technique: [docs/technique.md](../../technique.md) and [docs/pipeline.md](../../pipeline.md).
- For the open exploration list: [docs/next-exploration-steps.md](../../next-exploration-steps.md) (Phase D3 target: `docs/planning/exploration-paths.md`).
- For the contribute-back path: [CONTRIBUTING.md](../../../CONTRIBUTING.md).
