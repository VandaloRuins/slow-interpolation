# slow-interpolation manual (for agents)

This manual is for AI agents operating the `slow-interpolation` repository on behalf of a user. The user lands on [../../README.md](../../README.md), decides they want to run something, and delegates to you. From that point on, you read the docs and run the tools; the user observes, confirms, and answers narrow questions when you ask.

If you are a human reader who somehow ended up here: the README is the human entry point. The pages in this directory will read strangely because they are written for the agent, not for you. The agent uses them to operate the repo on your behalf.

## How to read this manual

Treat these pages as a **prompt library, not a script**. Each page sets up context, frames a decision space, names defaults and trade-offs, and points at adjacent pages. Your job is not to execute a page top-to-bottom; it is to load the parts of it that fit the user's request, then make calls inside the decision space the page lays out.

What this means in practice:

- **Read what is relevant; skip the rest.** A user asking "render the Renoir LoRA with Perlin noise" loads parts of `getting-started.md` (only if env not yet set up), the noise-source paragraph of `pipeline.md`, and `findings/noise-sources.md` for the Perlin verdict. Reading every page is wrong and slow.
- **Defaults are starting points, not commands.** Where a page says "Strong opinion: default to X. Y is also valid when Z.", that is a decision space, not a rule. The user's intent decides which branch you take. If the user did not specify, ask before committing to a non-default.
- **Two agents reading the same page on different sessions should produce different outputs.** The repo's value is in non-deterministic creative recombination across LoRAs, noise sources, pipeline knobs, and compositing strategies. The manual frames the space; the agent navigates it.
- **When you make a call the user did not specify, surface it before acting.** "Defaulting to Perlin noise at `feature_size: 48`. Override?" beats silent commitment.
- **Failure modes are decision tables, not flowcharts.** Match the symptom, run the suggested action, escalate to the user only if it does not resolve. If the symptom is not on the table, do not improvise; check `docs/findings/` first.

The Renoir-dataset workstream's `dataset-curation.md` and `gallery.md` are the canonical examples of this framing. When you write or edit a manual page, match their shape.

## Available protocols (read this BEFORE improvising)

When the user asks for an operation that looks like one of these shapes, **the protocol below already exists in this repo**. Use it. Do not build a parallel system unless you have confirmed with the user that no existing protocol fits.

| User asked for | Protocol page | Notes |
|---|---|---|
| Decide where to render (local vs Modal vs hybrid) | [hardware-routing.md](hardware-routing.md) | **Run BEFORE any render.** Pre-flight detects hardware via `nvidia-smi` + torch + disk free + GPU busy. Decision table routes by render type + local capability. Default: local first; Modal when local insufficient or parallelism is worth the cost. |
| Render a video, run the pipeline, generate a clip | [getting-started.md](getting-started.md) + [../pipeline.md](../pipeline.md) | Bootstrap + run. Routing decided by `hardware-routing.md`. |
| Run on cloud GPU, batch renders, dispatch to A100 / L40S | [../modal.md](../modal.md) + [hardware-routing.md](hardware-routing.md) | All cloud work goes through `cloud/` package. Includes cost estimator and batch fan-out. Routing decision lives in `hardware-routing.md`; this page is the Modal command surface. |
| **Build any image collection** (training set, reference set, validation hold-out, curation pile) | [dataset-curation.md](dataset-curation.md) | **Universal.** The same five-phase protocol covers LoRA training sets, figure-reference collections, synthetic-data audit, anything image-shaped. Do NOT improvise; copy `datasets/renoir-flowers/*.py` to `datasets/<your-name>/`, adapt slot vocabularies, run. |
| Stand up a gallery to visually QA images | [gallery.md](gallery.md) | Same gallery server works on any `datasets/<name>/` folder. The HTML rebuild is keyword-substitution on the Renoir template. |
| Train a LoRA on CivitAI | [../findings/lora-training.md](../findings/lora-training.md) | The Renoir worked example. Future generic recipe lands at `findings/lora-pipeline.md` post-Renoir-training export. |
| **Validate a freshly trained LoRA** (epoch comparison, engine bake-off, over-fit check) | [validate-lora.md](validate-lora.md) | Family-agnostic. Drives [`cloud/validate_lora.py`](../../cloud/validate_lora.py) via per-family YAML at `examples/configs/validation/<family>.yaml`. Five-phase: author YAML, route to Modal, dispatch one run per epoch, assemble comparison HTML, walk the user through the 5-signal checklist. Outputs at `outputs/validation/<family>/epoch-<N>/`. |
| Pick a noise source for a subject | [noise.md](noise.md), with deeper rationale in [../findings/noise-sources.md](../findings/noise-sources.md) | Decision table indexed on motion character. Spatial frequency is the primary axis; pick high-frequency (`evolved`, small `feature_size`, high `cell_density`) for fine-brushwork LoRAs, low-frequency for bold regional shifts. |

If your task does not match any row, scan the workstream progress logs under [../planning/workstreams/](../planning/workstreams/) for adjacent work before building. The repo's value compounds when agents reuse the documented protocols and contribute back; it degrades when each new task spawns a parallel implementation.

## Reading order (agents)

Read what is relevant to your task. Do not read every page on every session.

1. **Before ANY render: pick a render target.** [hardware-routing.md](hardware-routing.md). Pre-flight hardware detection, decision table for local vs Modal vs hybrid, cost trade-offs, dispatch commands. Run this first so you know where the work goes.
2. **First time setting up the repo:** [getting-started.md](getting-started.md). Bootstrap protocol from a fresh clone to a first MP4 render. Includes platform notes, install order, troubleshooting decision tree.
3. **Running a render or modifying a config:** [../pipeline.md](../pipeline.md). Technical reference for the four-phase pipeline. Source of truth for parameters, callbacks, micro-conditioning.
4. **Running on cloud GPU (after routing decided you should):** [../modal.md](../modal.md). Modal.com command surface. Cost expectations, variant recipe.
5. **Building a LoRA training set with a workshop student:** [dataset-curation.md](dataset-curation.md). Five-phase protocol. You run Phases 1, 2, 4, 5; the student walks the gallery in Phase 3.
6. **Operating the dataset-curation gallery tool:** [gallery.md](gallery.md). How you stand the gallery up, brief the student, and process the JSON they hand back.
7. **Picking a noise source for a subject:** [noise.md](noise.md). Decision table for the seven-source palette; spatial-frequency lever as the primary axis.
8. **Validating a freshly trained LoRA:** [validate-lora.md](validate-lora.md). Family-agnostic epoch / engine comparison protocol; assembles a side-by-side HTML the user opens to make the visual call.

## Slated for Phase D3 (not yet written)

- `configs.md`, agent-facing YAML schema reference.
- `training-loras.md`, generic LoRA training recipe. Authored when the Renoir LoRA training round closes and the recipe stabilises. Tracks [docs/planning/progress.md](../planning/progress.md) "LoRA pipeline export plan".
- `compositing.md`, dual-LoRA compositing path. Post-ship.

Until those are written, [../findings/](../findings/) is your source of truth for the same topics in research-doc shape.

## What this manual is

Operational instructions for you. Each page tells you what to do, what the user does, what to ask the user before doing anything irreversible, and how to recover when something goes wrong.

Manual pages are stable. They are written once, edited rarely. If the pipeline behaves in a way that contradicts what a manual page says, the page is wrong; open a counter-finding per [../../CONTRIBUTING.md](../../CONTRIBUTING.md) shape 4.

## What this manual is not

- Not a tutorial for human readers. Humans read README.md, then delegate.
- Not the place for in-flight design discussion or experimental results. Those live in [../planning/](../planning/) (active work) and [../findings/](../findings/) (closed-out experiments).
- Not a substitute for reading [../pipeline.md](../pipeline.md) before changing parameters in `src/`.
