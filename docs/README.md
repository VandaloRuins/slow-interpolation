# docs/

Map of the documentation tree. Read this to find a doc by purpose.

The tree is organised into four tiers; the structure and naming convention is documented in [planning/docs-strategy.md](planning/docs-strategy.md). The migration to the full four-tier layout is phased; some files still live at the root of `docs/` and will move into `manual/` or `reference/` once they stabilise (Phase D2 / D3 in the strategy doc).

## Quick navigation by purpose

| I want to | Go to |
|---|---|
| Understand what the technique IS, artistically | [technique.md](technique.md) |
| Understand the pipeline architecture | [pipeline.md](pipeline.md) |
| Set up the environment | [dev-setup.md](dev-setup.md) |
| Run my first render | [manual/getting-started.md](manual/getting-started.md) |
| Run on Modal.com cloud GPUs | [modal.md](modal.md) |
| Train a LoRA for a new domain | [findings/lora-training.md](findings/lora-training.md) + [findings/dataset-practice.md](findings/dataset-practice.md) |
| Pick a noise source | [findings/noise-sources.md](findings/noise-sources.md) |
| See current project status | [planning/progress.md](planning/progress.md) |
| See what's worth trying next | [next-exploration-steps.md](next-exploration-steps.md) |
| Contribute back a finding | [../CONTRIBUTING.md](../CONTRIBUTING.md) |

## TIER 1 - user manual (external-facing)

Lives under [manual/](manual/). Polished, tutorial-shaped. For downstream users (humans and AI agents) who want to USE the technique.

- [manual/index.md](manual/index.md) - entry point and reading order.
- [manual/getting-started.md](manual/getting-started.md) - install, first render, troubleshooting.

Pending promotion into the manual at Phase D3:

- `pipeline.md` -> `manual/pipeline.md`
- `modal.md` -> `manual/modal.md`
- `findings/lora-pipeline.md` (post-Renoir-export) will gain a sibling `manual/training-loras.md`.

Recent promotions (done):

- `gallery-manual-notes.md` -> `manual/gallery.md` (2026-05-18, original file deleted).
- `findings/noise-sources.md` -> `manual/noise.md` (2026-05-18; findings doc retained as deep reference).

## TIER 2 - durable project reference

Top-level `docs/*.md` for now; moves to `reference/` at Phase D3.

- [technique.md](technique.md) - artistic framing.
- [context.md](context.md) - artist + release background.
- [pipeline.md](pipeline.md) - technical pipeline reference (Phase D3 target: `manual/pipeline.md`).
- [inventory.md](inventory.md) - legacy code, file-by-file annotated map.
- [dependencies.md](dependencies.md) - external resources the repo depends on.
- [outputs.md](outputs.md) - sample MP4 catalog under `examples/outputs/`.
- [dev-setup.md](dev-setup.md) - environment bootstrap.
- [roadmap.md](roadmap.md) - phased plan.
- [next-exploration-steps.md](next-exploration-steps.md) - things worth trying (Phase D3 target: `planning/exploration-paths.md`, rewritten with PR-back targets).
- [modal.md](modal.md) - Modal.com deployment guide (Phase D3 target: `manual/modal.md`).
- [phase-2-acceptance.md](phase-2-acceptance.md) - port acceptance commands.

## TIER 3 - findings (distilled lessons)

Under [findings/](findings/). One file per claim; each is a stable artifact of a completed experiment.

- [findings/border-crop.md](findings/border-crop.md) - the EDGE_CROP=0 empirical probe.
- [findings/lora-training.md](findings/lora-training.md) - the Renoir LoRA worked example (Phase D3 target: rename to `lora-training-renoir.md`; the generic recipe `lora-pipeline.md` joins it post-export from Luca's Renoir-training chat).
- [findings/dataset-practice.md](findings/dataset-practice.md) - the recipe for building a LoRA dataset from scratch.
- [findings/dataset-hygiene.md](findings/dataset-hygiene.md) - the Gemini-driven crop pipeline (placeholder; will fold into `dataset-practice.md` at Phase D3).
- [findings/noise-sources.md](findings/noise-sources.md) - the noise-source catalog and visual readings.
- [findings/inpainting-options.md](findings/inpainting-options.md) - style-aware inpainting providers, ranked.

Every file in this tier carries a footer pointing at [CONTRIBUTING.md](../CONTRIBUTING.md) so that counter-findings can land cleanly.

## TIER 4 - planning (active workstreams + history)

Under [planning/](planning/). High-churn. Parent chat owns `progress.md`; each parallel workstream owns its folder under `workstreams/<name>/`.

- [planning/progress.md](planning/progress.md) - master integration log + decisions. Parent-chat-only writes.
- [planning/docs-strategy.md](planning/docs-strategy.md) - this strategy doc.

Public workstream folders (shipped-milestone case studies; readable end-to-end):

- [planning/workstreams/modal/](planning/workstreams/modal/) - Modal cloud infrastructure. [progress](planning/workstreams/modal/progress.md), [release-batch](planning/workstreams/modal/release-batch.md).
- [planning/workstreams/noise/](planning/workstreams/noise/) - Noise sources research. [progress](planning/workstreams/noise/progress.md).
- [planning/workstreams/renoir-dataset/](planning/workstreams/renoir-dataset/) - Renoir floral dataset + training playbook. [progress](planning/workstreams/renoir-dataset/progress.md), [validation-grid](planning/workstreams/renoir-dataset/validation-grid.md).

In-progress workstreams (compositing, inpaint, soutine-LoRA, modal-trainer, alt-techniques) live in the maintainer's private planning folder during v0.1 and surface publicly in v0.2 once their protocols stabilise. The findings docs reference them by name without inline links.

Other planning surfaces:

- [planning/kickoff-prompt.md](planning/kickoff-prompt.md) - parent-chat session opener.
- [planning/docs-strategy.md](planning/docs-strategy.md) - docs-tree strategy + naming convention.
- [planning/pipeline-split-decision.md](planning/pipeline-split-decision.md) - D3 prep decision on splitting `pipeline.md` into manual + reference.
- [planning/history/2026-05-phase-1-2-port.md](planning/history/2026-05-phase-1-2-port.md) - retrospective on the consolidation + port phases.

## What goes where, in one paragraph

If you are about to add a doc: a USER MANUAL page goes in `manual/`. A DURABLE REFERENCE about the project, artist, technique, or dependencies goes in `reference/` (today, at the root of `docs/`). A DISTILLED LESSON from a completed experiment goes in `findings/`. A WORKSTREAM PLAN or STATUS LOG goes in `planning/workstreams/<name>/`. If your doc does not match any of these, ask the parent chat in [planning/progress.md](planning/progress.md) before naming it.
