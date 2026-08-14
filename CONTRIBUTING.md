# Contributing to slow-interpolation

This is a small open-source experiment. Every fork is part of it. If you ran the pipeline, trained a LoRA, wrote a new noise source, or found something the docs do not say, the project is asking you to share it back.

This file is written for both human contributors and AI agents. The conventions are the same for both; agents should follow them as if a human reviewer would read the result.

## The five contribution shapes

| You did this | PR shape | Template |
|---|---|---|
| Trained a LoRA in a new domain and ran the pipeline against it | New findings doc | [§ LoRA-domain finding](#shape-1-lora-domain-finding) |
| Implemented a new `NoiseSource` | Code + tests + findings update | [§ Noise source](#shape-2-new-noise-source) |
| Tried a different compositing strategy | Findings doc + optional code | [§ Compositing strategy](#shape-3-compositing-strategy) |
| Got a different result than the docs claim | Counter-finding | [§ Counter-finding](#shape-4-counter-finding) |
| Improved the user manual or fixed a setup gotcha | Manual page edit | [§ Manual edit](#shape-5-manual-edit) |

If your contribution does not match one of these, open an issue first and we'll figure out where it lands.

## How to PR

1. **Fork** the repo on GitHub.
2. **Branch** from `main`. Branch name: `<shape>-<short-slug>`. Examples: `finding-cezanne-lora`, `noise-curl-2d`, `compositing-depth-prior`, `manual-amd-rocm`.
3. **Commit small.** One coherent change per commit. Commit messages: imperative present (`add Cezanne LoRA finding`, not `added` or `adding`).
4. **Tests pass.** `python -m pytest tests/ -q` is the bar. New code adds new tests; the existing 55 tests must stay green.
5. **No em dashes** in any text you write into the repo. Use commas, periods, or "to" for ranges. This is a stylistic constraint of the original author; it keeps the prose consistent across forks.
6. **No sibling-folder dependencies.** `python -m pytest tests/test_no_sibling_paths.py` must pass. It covers `src/`, `vendor/`, `tools/`, `datasets/`, `docs/`, `.github/` and `.claude/`, and bans absolute machine paths, live parallel-project names, and `Choire`/`After Cole` inside code directories. Documenting the lineage in `docs/` is fine.
7. **Update the docs map.** If you added a file under `docs/`, add it to `docs/README.md` in the same PR.
8. **Open the PR** against `main`. Reference any related issue. Describe what you tried, what you observed, and what changed.

PR review on the original repo aims for under one week.

## Per-shape templates

### Shape 1: LoRA-domain finding

You trained a LoRA in a domain other than the published ones (Thomas Cole, Casa del Suono, Renoir florals), ran the slow-interpolation pipeline against it, and have something to report.

**PR contents:**

- `docs/findings/lora-<your-domain>.md`. Use the same structure as [docs/findings/lora-training.md](docs/findings/lora-training.md): training run summary, recommended LoRA scale, prompt vocabulary, observed failure modes, border-artifact behavior. Be concrete with numbers.
- Optional: `examples/configs/<your-domain>/*.yaml` if you want to ship working configs alongside the finding.

**Do not** check in the LoRA `.safetensors` itself. `models/loras/` is gitignored. Reference where the weights live (CivitAI URL, HuggingFace model ID) in the finding.

### Shape 2: New noise source

You implemented a new `NoiseSource` and want it added to the catalog.

**PR contents:**

- `src/slow_interpolation/noise/sources/<your_source>.py`. Subclass `WalkingNoiseSource` for the standard walk-and-renormalize pattern, or `NoiseSource` directly if your source has bespoke temporal behavior.
- `src/slow_interpolation/noise/__init__.py` updated: import + add to `__all__` + add a kind to `_build_from_spec`.
- `tests/test_noise_sources.py` extended: interface compliance, drift behavior, source-specific edge cases. Match the coverage of the existing sources.
- `docs/findings/noise-sources.md` updated: add an entry describing the visual reading, parameter range, subjects that benefit from this source, subjects that do not.

If the source has a non-obvious math kernel, factor it into `src/slow_interpolation/noise/sources/_kernels.py` and add a unit test for the kernel directly.

### Shape 3: Compositing strategy

You tried a dual-prompt / dual-noise / multi-LoRA / depth-guided / mask-guided compositing strategy that is not already documented (the compositing workstream design will land at `docs/findings/compositing.md` in v0.2).

**PR contents:**

- `docs/findings/compositing-<strategy-name>.md`. Sections: strategy summary, where it slots into the pipeline, what you observed, comparison against the existing strategies (A, B, C, D in the design doc).
- Optional: code under `src/slow_interpolation/compositing/` if your strategy needs new abstractions.
- Optional: an MP4 reference linked from the finding (host it externally; do not commit large binaries).

### Shape 4: Counter-finding

You got a different result than a `docs/findings/*.md` file claims. Open this PR even if you are not sure why; the project values negative results.

**PR contents:**

- Edit the existing finding to add a "## Counter-findings" section at the bottom, OR add `docs/findings/<topic>-counter.md` if your variance is large enough to deserve its own file. Either is fine; the parent chat will consolidate at the next D2 pass.
- Concrete numbers. What config did you run, what hardware, what LoRA, what was the observed behavior, what did the doc predict.

### Shape 5: Manual edit

You hit a setup gotcha, improved a worked example, or wrote a clearer explanation of a part of the pipeline.

**PR contents:**

- Edit under `docs/manual/`. Stay on the existing structure (`getting-started.md`, `pipeline.md`, `configs.md`, etc.).
- If your gotcha is platform-specific (Apple Silicon, ROCm, a specific WSL configuration), add a section to `docs/manual/getting-started.md` rather than a new file. The manual is meant to stay small.

**Audience reminder:** every page under `docs/manual/` is written for AI agents operating the repo on behalf of a user, NOT for human readers directly. Your edit must preserve that framing. Specifically:

- Address the agent in the second person ("You are an AI agent ...", "You run X", "Brief the user when ...").
- Distinguish clearly between what the agent does and what the user does.
- Replace human-tutorial phrasing ("Plan for 30 minutes", "Don't worry if ...") with agent-operational phrasing ("Estimate 30 minutes for the user", "Surface the timing to the user").
- Use decision tables for failure modes rather than prose troubleshooting.

The canonical examples to match in shape: `docs/manual/dataset-curation.md` and `docs/manual/gallery.md`. If your edit drifts toward human-tutorial framing, the maintainer will ask you to reframe before merging.

**Prompt-library framing.** Manual pages are prompt fragments the agent draws on when reasoning about a user request. Frame a decision space, do not close it. "Strong opinion: default to X. Y is also valid when Z." beats single-prescription. Two agents reading your page on different sessions should be able to produce different valid outputs. See `docs/manual/index.md` "How to read this manual" for the consumption side; match that on the writing side.

## Code style

This is Python 3.11+. The package uses:

- `dataclasses` for configs (no Pydantic).
- `numpy` for numeric work, `PIL` for image I/O.
- `pytest` for tests. No `unittest`. No mocks for I/O; the existing tests run in <2 seconds without GPU.
- Type hints where they aid clarity. `from __future__ import annotations` at the top of every file.
- Black-compatible formatting (line length 100 acceptable). No formatter enforced; aim for clarity over uniformity.

Avoid:

- Comments that explain WHAT the code does. The code does that.
- Comments that say WHY only if the WHY is non-obvious. Documented constraints, weird workarounds, references to a specific finding.
- Defensive validation for inputs that can only come from internal code.
- Backward-compatibility shims when you can just change the code.

## Mission

The repo's value compounds when forks share back. If you are reading this on a fork that has discovered something the original repo does not say, please open a PR. The project is small on purpose. Every contribution moves it.

If you are an AI agent and you want a starting point: read [AGENTS.md](AGENTS.md), then the kickoff prompt your user gives you, then the file the prompt points at. The PR conventions in this file apply to you the same as they apply to a human.

Thank you for forking.
