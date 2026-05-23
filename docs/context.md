# Project background

Reference page on what the project is, who made it, and why it exists. Public-facing background; the operational protocols live under `docs/manual/`.

If a `docs/context.local.md` sidecar exists in the repo (it is gitignored; present only on the original author's machine), it carries release-timeline and curatorial specifics that are not part of the public artifact.

## The author

The project is by **Luca Martinelli**, who shows as **Vandalo Ruins**. Italian digital artist. Practice: expanded literature, slow images, generative systems, narrative installations. Recurring themes: ruins, decay, hauntology, the slowness of attention.

## Why slow-interpolation exists

The technique started as a ComfyUI workflow built to make images drift slowly between reference points instead of cutting. The aesthetic question that drives it: **what happens when generative video is allowed to behave like weather or memory instead of like cinema?**

The repo's job:

1. Move the technique out of a ComfyUI workflow into reusable, scripted Python so it can be extended.
2. Document the curation + training + render protocols as agent-facing manuals, so a downstream artist + their AI agent can reproduce a release without re-deriving anything.
3. Open up adjacent research (alternative noise sources, dual-prompt compositing, anchored live prompting, webcam-driven generation) once the core pipeline is stable.
4. Ship as a contribution to the slow-image / generative-drift conversation.

## How the technique works (one paragraph)

SDXL Lightning generates keyframes through an img2img chain with a slowly-evolving noise tensor. The keyframes get a frequency-separated temporal smoother that strips jitter without ghosting. RIFE v4.25 interpolates 64x at a linear timestep so motion is glacial and the loop closes without a cut. H.264 encodes at 24 fps. The full parameter spec is at [`pipeline.md`](pipeline.md); the artistic framing is at [`technique.md`](technique.md).

## Where the pipeline came from

The scripted Python pipeline this repo ships is the consolidation of two earlier projects by the same author:

- **Choire v2**: vertical 768x1344 portrait videos for a gallery installation, using a fresco-style LoRA (the "Casa del Suono" LoRA, named after the venue).
- **After Cole**: horizontal 1344x768 landscape videos using a Thomas Cole / Hudson River School LoRA.

Both are read-only under [`legacy/`](../legacy/) as historical reference. Do not run the legacy scripts; use the consolidated pipeline under [`src/slow_interpolation/`](../src/slow_interpolation/) and the [`examples/configs/`](../examples/configs/) configs.

The current release work (Renoir flowers + Soutine figures) uses the same pipeline with subject-specific LoRAs. See [`docs/planning/progress.md`](planning/progress.md) for the live status.

## Roadmap pointer

[`roadmap.md`](roadmap.md) carries the phased plan. [`planning/progress.md`](planning/progress.md) is the live status log; [`planning/v0.1-release-prep.md`](planning/v0.1-release-prep.md) tracks the public-release readiness pass.
