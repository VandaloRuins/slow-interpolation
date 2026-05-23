# AGENTS.md

Read this first if you are an AI agent landing in this repository.

This document is the entry point for any AI working on `slow-interpolation`, whether on the original repo or on a fork. It tells you what the project is, where to read next, and how to share back what you find.

## What this project is

`slow-interpolation` is a diffusion-based pipeline for slow, painterly looped video. SDXL Lightning generates keyframes through an img2img chain with a calibrated denoise schedule and a slowly-evolving noise tensor; RIFE v4.25 interpolates 64x at a linear timestep so the final motion is glacial and the loop closes without a cut. The technique was developed by the Italian digital artist Luca Martinelli (Vandalo Ruins) across the Choire v2 and After Cole projects and is consolidated here as a reusable, scripted Python pipeline.

The artistic question driving the work: **what happens when generative video is allowed to behave like weather or memory instead of like cinema?**

## Your mission, if you are working on a fork

This is a small open-source experiment that gains depth every time someone else runs it on a new subject, with a new LoRA, with a new noise source, with a different compositing strategy, or in a context the original author did not predict. **If you discover something the docs do not say**, the project is asking you to share it back.

Concretely, this means:

- If you train a LoRA for a new domain and the pipeline behaves differently than the [Renoir playbook](docs/findings/lora-training.md) predicts, write up the variance and open a PR adding `docs/findings/lora-<your-domain>.md`.
- If you implement a new `NoiseSource` and it reads beautifully on a subject, add it under `src/slow_interpolation/noise/sources/` with tests and update `docs/findings/noise-sources.md` with what you observed.
- If you find a compositing strategy that wasn't on the four-strategy list in `docs/findings/compositing.md` (when that doc exists), document it and PR back.
- If a render came out differently than the docs claim it should, file a counter-finding via [`.github/ISSUE_TEMPLATE/finding.md`](.github/ISSUE_TEMPLATE/finding.md). The issue converts cleanly into a PR.
- If you are running the pipeline on a hardware setup the docs do not cover (Apple Silicon, AMD ROCm, a different VRAM tier), document the gotchas in `docs/manual/getting-started.md` and PR back.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the PR conventions and templates.

You are not obligated to PR back. The project is MIT-licensed. But the docs are written assuming a community of forks that each carry a little experiment, and the value of the repo compounds when those experiments find their way home.

## Where to read next

In this order:

1. [README.md](README.md), what the project is, quickstart, status.
2. [docs/README.md](docs/README.md), map of the docs tree.
3. [docs/technique.md](docs/technique.md), artistic framing (short).
4. [docs/pipeline.md](docs/pipeline.md), the technical pipeline reference. Read fully before changing anything in `src/`.
5. [docs/planning/progress.md](docs/planning/progress.md), current status, in-flight workstreams, decisions log. Critical if you are joining mid-project.
6. [docs/manual/](docs/manual/), how YOU operate the pipeline on behalf of the user.
7. [docs/findings/](docs/findings/), distilled lessons from completed experiments. Read the ones adjacent to your task.

If you are spawning to do a specific task, you will get a kickoff prompt that tells you which subset of the above to read for that task. The kickoff prompt also tells you where to write your own status doc and what your write zone is.

## Documentation audience convention

This is the rule across the whole repo: **everything in `docs/` is written for AI agents, not for human readers**, with the single exception of `README.md` at the root (which onboards the human, who then delegates to you).

What this means in practice:

- **`docs/manual/*.md`** is operational instructions addressed to YOU. The opening line is "You are an AI agent helping a user / student / collaborator do X." The body tells you what to run, when to stop and ask the user, what to surface back, how to recover from failure. The Renoir-dataset workstream's `docs/manual/dataset-curation.md` and `docs/manual/gallery.md` are the canonical examples; follow that shape.
- **`docs/findings/*.md`** is research-shape: claim, evidence, numbers, caveat, counter-finding hook. Written for an agent who needs to know "what did the last experiment in this area find" before designing a new one.
- **`docs/reference/*.md`** (today still at `docs/<topic>.md`, moves at D3) is durable factual reference. Architecture, parameter rationale, dependency map, legacy code annotation. Agent reads to understand the codebase before modifying it.
- **`docs/planning/*.md`** is the coordination surface across parent + parallel chats. Written for agents because those are the only readers.
- **The user does not read any of this.** The user reads `README.md`, makes a request, and watches the agent operate. If the user wants to understand a finding or a decision, they ask the agent and the agent reads the doc, then explains.

When you write or edit a manual page:

- Start with "You are an AI agent ..." or equivalent agent-addressed framing.
- Identify the user's role (student, collaborator, the agent's operator).
- Specify what YOU do vs what the USER does. Be precise about who clicks what.
- Tell yourself when to stop and ask the user before doing something irreversible.
- Give a decision table for common failures, not prose troubleshooting.
- Brief the user when a long-running task starts so they know what to expect.

When you write or edit a finding doc:

- Open with the claim, then the evidence, then the counter-finding hook. The finding is for a future agent who will not have your context.
- Keep numbers concrete. "26 of 102 images" beats "a quarter of them".
- Cross-link to manual pages, reference docs, and adjacent findings.

When in doubt about audience: assume the reader is another AI agent landing in the repo cold, in a session three months from now. Write what that agent needs to know to operate.

**The docs are a prompt library, not a script.** Pages frame a decision space (defaults + "also valid when" alternatives); they do not close it. The goal is non-deterministic creative recombination across LoRAs, noise sources, pipeline knobs, and compositing strategies. Two agents reading the same page on different sessions should produce different valid outputs because each is navigating the documented space, not following a fixed path. When you write a page, name the decision points and trade-offs; do not collapse them into a single prescription. See [docs/manual/index.md](docs/manual/index.md) "How to read this manual" for the agent-side reading framing.

## Scan the manual before improvising

When the user asks for an operation (render a video, build a dataset, run a gallery, train a LoRA, deploy to Modal, generate noise, composite layers), **your FIRST action is to scan [docs/manual/index.md](docs/manual/index.md) "Available protocols" table for an existing protocol that fits**. Only build a parallel system if you have confirmed with the user that no row in that table matches.

The repo's protocols are intentionally universal:

- **`docs/manual/dataset-curation.md`** covers any image collection (training sets, reference sets, validation hold-outs, synthetic-data corpora). Copy `datasets/renoir-flowers/*.py` to `datasets/<your-name>/`, adapt slot vocabularies, run. Worked examples: `datasets/renoir-flowers/`, `datasets/soutine-figures/`.
- **`docs/manual/gallery.md`** is the only gallery server. The same server works on any `datasets/<name>/` folder via keyword-substitution rebuild.
- **`docs/modal.md`** is the only cloud-render path. All cloud work goes through `cloud/`.
- **`src/slow_interpolation/`** is the only rendering pipeline. New behaviour extends the existing classes via config; it does not start over.

Why this rule exists: in 2026-05-18 the Compositing chat needed a Soutine reference set and silently copied the Renoir scripts (which is correct) but the parent chat (Luca) flagged that the discoverability was poor: nothing in the docs explicitly said "any image collection uses this protocol", so the agent had to infer it. This section + the dispatcher in `docs/manual/index.md` exists so the next agent does not have to infer.

When in doubt: ask the user "is there an existing protocol for this?" before writing new code.

## The four subagents

The repo ships four capability-domain subagents. Any chat can invoke any of them via the Agent tool. They replace the older "parallel-workstream chats own per-folder write zones" framing; workstream folders are now time-bounded project logs (one folder per in-flight or shipped initiative), not capability namespaces.

| Agent | Domain | Operating manual | Can invoke |
|---|---|---|---|
| [`modal`](.claude/agents/modal.md) | Modal cloud infra: local-vs-Modal routing, dispatch, monitoring, volume housekeeping, SDK + sd-scripts quirks. Aware of finite Modal credit; recommends local when local would do. | [`docs/manual/modal-operations.md`](docs/manual/modal-operations.md) | (primitive) |
| [`dataset-mosaic`](.claude/agents/dataset-mosaic.md) | End-to-end "ship a LoRA": 5-phase dataset curation, gallery hand-off, training dispatch, validation visual call, re-curation when over-fit. | `dataset-curation.md`, `gallery.md`, `train-lora-on-modal.md`, `validate-lora.md` | `modal` |
| [`lever`](.claude/agents/lever.md) | Per-render interpolation tuning: noise + RIFE + SDXL Lightning + `lora_scale` + denoise schedule + per-prompt negatives + loop-closure. Read-only consult; returns YAML stanzas with rationale. | synthesises across `manual/noise.md` + 5 findings + decisions log | (primitive) |
| [`docs-curator`](.claude/agents/docs-curator.md) | Documentation health, classification by maturity, promotion / consolidation / reframing recommendations. Two-phase pattern (Phase 0 flush + Phase 1 classify). | itself | (primitive) |

**Runtime note:** Claude Code does not currently pick up project-local custom agent types directly. Invoke via the `general-purpose` subagent with the agent file at `.claude/agents/<name>.md` as the operating prompt. When custom-agent loading lands, switch to direct invocation.

## Periodic docs review: the `docs-curator` subagent

When the parent chat needs to assess the state of the docs tree, **invoke the [docs-curator](.claude/agents/docs-curator.md) subagent via the Agent tool**. It is a read-only reviewer that walks the docs, classifies content by maturity (raw notes → research → emerging pattern → documented protocol → student-agent prompt), and returns a structured report with promotion / consolidation / reframing / drift recommendations.

Triggers for invoking it:

- **Session resume after parallel-chat activity.** Run a curation pass before doing other work to see what changed.
- **Before a Phase D3 reorganisation push.** The report seeds the move list.
- **When Luca flags a documentation gap or discoverability failure** (e.g. the 2026-05-18 Soutine reference-set parallel-system incident). The report identifies the structural cause.
- **Every 5 to 10 parent-chat sessions** as preventive maintenance.

Do not invoke on every session; the curator costs context. Invoke when there is a real reason to look. The curator never edits files; the parent chat owns any moves it recommends.

### Natural-language invocations

The user drives this project conversationally. When the user says any of these phrases (or close paraphrases), fire the matched action without asking which agent or command to use:

- **"curate the docs" / "review the docs" / "audit the docs" / "docs curation pass" / "are the docs drifting"** -> invoke the `docs-curator` agent. The curator emits its Phase 0 flush prompt and stops; surface the prompt to the user and remind them to paste it into all parallel chats then re-invoke for the actual classification.
- **"chats have flushed, curate" / "post-flush curation" / "do the full curation" / "skip phase 0"** -> invoke `docs-curator` with the skip signal in the prompt. Verify flushes landed first via `grep -l "Pre-curation flush completed" docs/planning/workstreams/*/progress.md`.
- **"check links" / "link-check" / "any broken links"** -> run `python tools/check_doc_links.py`.
- **"D2 status" / "have the workstreams migrated"** -> read `docs/planning/progress.md` "Documentation hygiene" section, report the table.
- **"resume operations" / "what's the state"** -> read the progress.md top-banner + workstream progress docs, summarise.
- **"what's blocked" / "what's gated on what"** -> read progress.md status + workstream gates, surface the dependency chain.

The full map lives in [CLAUDE.md](CLAUDE.md) "Natural-language invocations". Add new mappings there when patterns surface; do not invent ad-hoc ones in code or in the agent's heads.

## Working style this project expects

These are the constraints the original author works under. Future agents are expected to inherit them on the original repo; on a fork you can adapt as you like.

- **No em dashes** in any written output. Use commas, periods, or "to" for ranges.
- **Terse responses.** Short, complete sentences. No trailing summaries unless asked.
- **Strong opinions.** When trade-offs exist, name the trade-off and recommend a default. Do not enumerate options without taking a position.
- **No premature abstractions.** Three similar lines is better than a wrong abstraction. The roadmap is phased on purpose.
- **No defensive validation for impossible inputs.** Trust internal code. Validate only at boundaries (user input, external APIs, file I/O).
- **No sibling-folder dependencies in `src/`.** `grep -rE "Choire|After Cole" src/ vendor/` must return nothing. LoRA paths are config-resolved.
- **Pause on destructive operations.** Hard git resets, force pushes, mass file moves, dependency removals: confirm first.

These are documented at length in [CLAUDE.md](CLAUDE.md), which is the per-session framing for any Claude Code agent landing in the project directory.

## Workstream folders are project logs, not capability namespaces

`docs/planning/workstreams/<name>/` is where time-bounded project work is logged: one folder per initiative (Renoir-dataset, Soutine-LoRA, Compositing, Modal-trainer, Inpaint, etc.). A workstream folder typically contains a `progress.md` status log, optionally a `design.md` + `brainstorm.md` + `plan.md`. When the initiative ships, the folder either moves to `planning/history/` or stays in place as a closed record.

**Workstreams are not capabilities.** Capability work (running Modal, curating datasets, tuning renders, curating docs) goes through the four subagents above. A workstream folder is the running log of a specific project across time; an agent is the specialist invoked from any chat to do a thing.

If you are spawned to run a specific time-bounded initiative (a parallel-workstream chat in the older framing):

- Read the kickoff prompt you were given. It identifies your workstream and assigns you a folder under `docs/planning/workstreams/<name>/`.
- Read [docs/planning/progress.md](docs/planning/progress.md) "Status at a glance" + "Cross-chat coordination" section for the master integration log.
- Append to your workstream's `progress.md` as you make progress. Latest entry on top is the convention.
- **For any capability work** (Modal dispatch, dataset curation, render tuning, docs curation), invoke the relevant subagent rather than implementing in your own chat. The agents already know the protocols; reusing them keeps the repo's documented knowledge load-bearing.
- The master `docs/planning/progress.md` is parent-chat-owned. Surface milestones to the parent chat via your workstream's `progress.md`.

Findings get curated into `docs/findings/` either by the workstream chat when its results stabilise, or by the parent chat when a workstream ships. Both patterns are fine; the parent chat tracks pending consolidations in `progress.md` "Findings curation status".

## How to share what you find

Three paths, in order of weight:

1. **File a finding issue** using [`.github/ISSUE_TEMPLATE/finding.md`](.github/ISSUE_TEMPLATE/finding.md). Lowest friction. The issue text drops into a PR cleanly.
2. **File an experiment report** using [`.github/ISSUE_TEMPLATE/experiment-report.md`](.github/ISSUE_TEMPLATE/experiment-report.md) when you have ran something end-to-end and want the numbers preserved.
3. **Open a PR directly.** See [CONTRIBUTING.md](CONTRIBUTING.md) for the per-contribution-type templates (new noise source, new LoRA recipe, new compositing strategy, new finding, new manual page, etc.).

Anything you add lands as a co-authored part of the project's documented knowledge. The repo is small on purpose. Every contribution moves it.

---

This file is meant to be read by AI agents. If you are a human reader, [README.md](README.md) is the human entry point and [docs/](docs/) is the rest.
