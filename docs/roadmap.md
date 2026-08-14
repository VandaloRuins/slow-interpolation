# Roadmap

A phased plan, rewritten now that the pipeline is correctly understood (SDXL Lightning + img2img chain + temporal smoothing + RIFE v4.25 64x, inherited from Choire v2 / After Cole).

> **Status (2026-05-17):** Phases 0, 1, 2 are **done**. Phase 3 (Renoir LoRA release) is in flight via five parallel workstreams; see [docs/planning/progress.md](planning/progress.md) for live status. Phase 4 (live work) stays deferred until after the Renoir release ships. This file is preserved for historical framing; the live truth is in `planning/progress.md`.

## Phase 0. Repo setup (done, 2026-05-14)

- New repo at `Desktop/slow-interpolation/`.
- Source scripts cloned from After Cole and Choire v2 into [legacy/](../legacy/).
- Sample outputs cloned into [examples/outputs/](../examples/outputs/).
- Comfy archive moved to [legacy/comfy-archive/](../legacy/comfy-archive/) with a note that it is unrelated to this technique.
- Package skeleton at `src/slow_interpolation/` (now populated; Phase 2 shipped 2026-05-16).
- MIT license, gitignore, pyproject.

## Phase 1. Consolidation and documentation (done, 2026-05-14 to 2026-05-15)

Before writing any new code, the next session inventories and documents what we have.

- Read every legacy script line by line. Produce per-file notes in [inventory.md](inventory.md) for each one, describing what it does, what its key parameters are, and how it relates to the others.
- Verify [pipeline.md](pipeline.md) against the actual code. Correct any discrepancies (the pipeline doc was written from the Choire v2 research doc, not from the code itself).
- Watch the sample outputs in [examples/outputs/](../examples/outputs/) and write [docs/outputs.md](outputs.md) (TBD), a brief annotated catalog of what each sample demonstrates technically and aesthetically.
- Map every external dependency the legacy scripts touch and decide re-vendor vs. config-resolve. **DONE** in [dependencies.md](dependencies.md): RIFE train_log re-vendored; `evolved_noise_blend` absorbed (function body in [pipeline.md appendix](pipeline.md#appendix-evolved_noise_blend-the-production-noise-path)); LoRA paths config-resolved with no sibling-folder fallback; ESRGAN dropped until Renoir testing demands it.

Exit criteria: a reader new to the project can understand the existing pipeline end-to-end from the docs alone, without reading the legacy code.

## Phase 2. Port the pipeline into `src/slow_interpolation/` (done, 2026-05-15 to 2026-05-16)

A clean, configurable, reusable Python package that reproduces the legacy behavior with a better interface.

- `core/Pipeline` class with phase-by-phase methods.
- Config-driven paths (no hard-coded Choire `visuals/` references).
- After-Cole-style LoRA + subject swapping via plain object construction, not monkey-patching.
- One reproducible reference run that matches a legacy output frame-for-frame close.

Exit criteria: `python -m slow_interpolation.run examples/configs/tcole_valley.yaml` produces output visually equivalent to `legacy/after-cole/`'s `tcole_valley_horizontal.mp4` (same composition family, same palette and surface, no regressions on border / pulse / loop-closure artifacts). Frame-for-frame match is not a goal: the legacy noise walk and SDXL Lightning sampling are not seed-controlled, so re-rolls of the same config produce different specific frames even before any port (see the `v1` / `v2` pairs in [outputs.md](outputs.md)).

## Phase 3. Renoir flowers LoRA + expanded scope (in flight, 2026-05-15 onward)

The first new body of work. Scope expanded 2026-05-15 to include offline-scope noise research (formerly Phase 4.1) and offline dual-prompt compositing (formerly Phase 4.3). Live work stays in Phase 4.

**Which style carries the first release is an open question.** Renoir flowers was the original direction and the LoRA is trained and validated, but the release subject is under exploration rather than settled. This phase's deliverables (the LoRA, the dataset protocol, the noise work, the configs) stand on their own regardless of which style ships.

> **Settled 2026-08-12:** the release direction for both the NYC billboard and the objkt labs release is the **Arendt Vita Activa series**: three clusters of 10-second loops (Labor / Work / Action), edited side by side into the long delivery file. The Renoir family is **parked** as release direction (its deliverables stand). Concept and time doctrine: the Arendt Vita Activa series research doc (held in the private studio repo); production state: [quality-first progress](planning/workstreams/quality-first/progress.md) L38 onward.

- Build dataset under `datasets/renoir-flowers/` (102 paintings curated, captioned, CivitAI ZIP ready as of 2026-05-17).
- Train the LoRA on CivitAI, same playbook as Thomas Cole. In flight in a separate chat.
- Define 3 to 7 subjects (A/B/C/A prompts). Four templates scaffolded under `examples/configs/renoir/` as of 2026-05-17.
- Noise sources research: six implementations + ABC + harness + 49 tests landed; wired into `PipelineConfig.render.noise`.
- Modal cloud infrastructure: cold-run validated at 0.07 USD per 60s render.
- Compositing design: dual-LoRA strategy (Renoir + Soutine), AI-generated figure videos as silhouette source.
- Render the release series.

See [docs/planning/progress.md](planning/progress.md) for live status across all five Phase 3 workstreams.

Exit criteria: the Renoir series is rendered and ready to ship to the release curator.

## Phase 4 onward. Explorations

These are the new directions Luca wants to pursue once the consolidation and port are done. They live in their own document so the next session can read them as a single brief: [next-exploration-steps.md](next-exploration-steps.md).

- Noise pattern exploration.
- Webcam depth as noise during live generation.
- Two-layer noise compositing (background prompt + depth-masked subject prompt).
- Anchored live prompting (drift while landmarks survive).
