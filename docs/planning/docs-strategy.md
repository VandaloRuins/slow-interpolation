# Documentation strategy

How docs in this repo are organised, named, and grown over time. Read this before adding a new doc, especially if you are a parallel chat. The objective: a `docs/` tree that is uniform, easy to navigate, ships as a useful artifact alongside the code, and quietly enrolls every agent who reads it into the project's experiment.

Status: live as of 2026-05-17. Phase D1 (entry-point docs + new directory skeleton) shipped. **Phase D2 reframed (2026-05-17)** from "parent moves files at workstream close" to **"each chat self-migrates on its next active session"**. Phase D3 (one-shot post-Renoir reorg) unchanged.

D2 prep ALSO shipped 2026-05-17: `docs/progress.md` and `docs/kickoff-prompt.md` moved into `docs/planning/`; link-check tool at `tools/check_doc_links.py`; self-migration instruction blocks embedded in each in-flight workstream's `*-progress.md`.

## Audiences

The docs tree serves four readers, in this rough order of frequency. **Everything in `docs/` is written for AI agents**, with the single exception that the root-level `README.md` onboards the human, who then delegates to the agent.

1. **The parent chat resuming this project** (any future Claude session inside `slow-interpolation/`). Needs the status, the decisions, the next-up list. Agent.
2. **Parallel-workstream chats** spawned to work in a corner of the project (Modal, Noise, Compositing, Renoir-dataset, future ones). Needs scope, ownership rules, what files it can write, where to place its docs. Agent.
3. **AI agents that a downstream user runs locally on a fork** to operate the repo on the user's behalf. Needs: project mission, entry point, where to start reading, operational manual pages, contribute-back hooks. Agent.
4. **Humans (Luca, eventually other artists / researchers) opening the repo on GitHub.** Read the `README.md` to decide whether to clone, then delegate to their agent. Only the README is in their lane; everything else reads strangely to them because it is addressed to the agent they will use.

The structure below is designed to keep audience 4 served by ONE file (README.md) and audiences 1, 2, 3 served by the rest of the tree. No duplication.

## Workstreams and subagents

Two separate concepts that older drafts of this strategy conflated.

- **Subagents** are capability-domain specialists callable from any chat via the Agent tool. Four exist today: [`modal`](../../.claude/agents/modal.md), [`dataset-mosaic`](../../.claude/agents/dataset-mosaic.md), [`lever`](../../.claude/agents/lever.md), [`docs-curator`](../../.claude/agents/docs-curator.md). Each is defined by an operating prompt at `.claude/agents/<name>.md` and a manual page (or synthesis across several) at `docs/manual/*.md`. They are durable and shared.

- **Workstreams** are time-bounded project initiatives (Renoir-dataset, Soutine-LoRA, Compositing, Modal-trainer, Inpaint, etc.). Each lives in `docs/planning/workstreams/<name>/`. A workstream is the log of work-across-time on one initiative; it ships, the folder either stays in place as a closed record or moves to `planning/history/`.

The older "parallel-workstream chats own per-folder write zones" framing has been **superseded** by the subagent model for capability work. Workstream chats that are still running parallel keep operating per their existing kickoff prompts (no in-flight disruption); new capability work goes through subagent invocation. The cross-write-zone protocol in `progress.md` "Cross-chat coordination" stays valid for in-flight workstreams and as a fallback when a capability does not yet have a subagent.

## The four-tier structure

```
slow-interpolation/
  README.md             GitHub front-page (audience 3 + 4)
  AGENTS.md             AI-agent entry point (audience 4 + 2)
  CONTRIBUTING.md       fork-and-share path (audience 4)
  CLAUDE.md             internal session framing (audience 1 + 2)

  docs/
    README.md           map of what is where

    manual/             TIER 1 - external-facing user manual
      index.md
      getting-started.md
      pipeline.md
      configs.md
      noise-sources.md
      training-loras.md
      modal.md
      gallery.md
      compositing.md

    reference/          TIER 2 - durable project reference
      technique.md      artistic framing
      context.md        artist + release background
      inventory.md      legacy code map
      dependencies.md   external resources
      outputs.md        sample MP4 catalog
      dev-setup.md
      roadmap.md

    findings/           TIER 3 - distilled lessons (durable knowledge)
      border-crop.md
      noise-sources.md
      lora-pipeline.md
      lora-training-renoir.md
      dataset-practice.md
      inpainting-options.md
      compositing.md

    planning/           TIER 4 - active planning + history
      progress.md             master integration, parent-owned
      docs-strategy.md        this file
      kickoff-prompt.md       parent-chat session opener
      exploration-paths.md    "things worth trying" funnel
      workstreams/
        modal/
          progress.md
          followup-plan.md
        noise/
          progress.md
        renoir-dataset/
          progress.md
        compositing/
          progress.md
          design.md
      history/                shipped milestones, closed-out
        2026-05-phase-1-2-port.md
```

### What goes where, by tier

- **TIER 1 manual/**. Operational instructions for AI agents operating the repository on behalf of a user. **Written for agents, not for human readers.** Each page opens with "You are an AI agent helping a [user role] do X" or equivalent agent-addressed framing, then tells the agent what to run, when to stop and ask the user, how to recover from failure. The user reads `README.md`, decides what they want, and delegates to the agent; the agent reads these pages and operates the repo. The canonical examples are `docs/manual/dataset-curation.md` and `docs/manual/gallery.md` (both by the Renoir-dataset chat); follow their shape. Pages are stable and rarely change. If a parallel chat produces a "user manual" draft, it gets polished into a `manual/<topic>.md` in agent-facing form once stable.

- **TIER 2 reference/**. Durable factual reference: what the technique IS artistically, what the code WAS in its legacy form, what external resources the repo depends on. Updated rarely, read often. Frame here is "this is true regardless of what's in flight".

- **TIER 3 findings/**. Distilled lessons from completed experiments. One file per claim. Carries a confidence section (what was tested, with what numbers, against what alternatives). Read by future workstreams to avoid re-deriving. The contribute-back footer (see below) belongs at the bottom of every file in this tier.

- **TIER 4 planning/**. Living planning surface. `progress.md` is the master integration log. Each parallel workstream gets its own folder under `workstreams/<name>/` with its `progress.md` and any `design.md` / `plan.md` / `brainstorm.md`. When a workstream ships, its planning docs either move to `planning/history/` or are partly distilled into `findings/`. The planning tier is high-churn; everything else is low-churn.

## Naming convention for workstream initiatives

Use these filenames so the tree stays navigable. If your doc does not match one of these slots, ask the parent chat before naming it something new. The convention applies whether the workstream is run by a dedicated parallel chat (the older pattern) or by a subagent invoked from any chat (the new pattern).

| Doc type | Filename | Lives at |
|---|---|---|
| Workstream status log | `progress.md` | `docs/planning/workstreams/<name>/` |
| Workstream design before code | `design.md` | `docs/planning/workstreams/<name>/` |
| Workstream pre-design brainstorm | `brainstorm.md` | `docs/planning/workstreams/<name>/` |
| Workstream implementation plan | `plan.md` | `docs/planning/workstreams/<name>/` |
| Workstream supplementary plan (followup, reference gathering, etc.) | `<descriptor>-plan.md` | `docs/planning/workstreams/<name>/` |
| Distilled lesson after workstream ships | `<topic>.md` | `docs/findings/` |
| Agent operating manual | `<topic>.md` | `docs/manual/` |
| Durable project reference | `<topic>.md` | `docs/reference/` |
| Subagent operating prompt | `<name>.md` | `.claude/agents/` |

In-flight workstreams that were spawned under the older parallel-chat model keep their write-zone discipline (see [`progress.md`](progress.md) "Cross-chat coordination"). New workstream-initiative work invokes the relevant subagent for capability tasks (Modal, dataset-mosaic, lever, docs-curator); the workstream chat's own role is logging the initiative, not implementing capabilities from scratch.

## Mission injection: how the docs enroll their readers

This repo is meant to be a small open-source experiment that other artists + agents can fork, extend, and PR back into. Five surfaces carry the contribute-back invitation:

1. **`AGENTS.md`** at root opens with the mission and the explicit ask: "your fork is part of this experiment; if you discover something, PR a finding back".
2. **`CONTRIBUTING.md`** at root names the PR conventions and gives templates for each contribution type (new noise source, new finding, new LoRA recipe, new compositing strategy).
3. **Footer on every `docs/findings/*.md`**: a one-line banner pointing at `CONTRIBUTING.md`. Findings are co-authored across forks; the footer makes that visible.
4. **`.github/ISSUE_TEMPLATE/finding.md`** and **`.github/ISSUE_TEMPLATE/experiment-report.md`**: structured prompts that match the `findings/*.md` schema. An agent that runs an experiment can drop the result into the template; the issue converts cleanly into a PR.
5. **`docs/planning/exploration-paths.md`**: every "things worth trying" entry ends with "if you try this and find it works, PR it back as `findings/<your-topic>.md`". The exploration list is also a contribution funnel.

Not used (rejected after design pass): a public `discoveries.md` ledger (premature; populate organically from real PRs), in-manual contribute-back footers (noisy; manual is for USING, not for contributing), a separate `MISSION.md` (folds into AGENTS.md cleanly).

## Migration plan

The parallel chats are mid-flight as of 2026-05-17. We can't move their files under them without breaking links in their working drafts. Migration is phased.

### Phase D1 - entry-point docs (2026-05-17, executed)

Adds on top of the current tree. No file moves. No mid-flight disruption.

- [x] `README.md` rewritten as a real GitHub front-page.
- [x] `AGENTS.md` at root.
- [x] `CONTRIBUTING.md` at root.
- [x] `docs/README.md` map.
- [x] `docs/planning/docs-strategy.md` (this file).
- [x] `docs/manual/index.md` + `docs/manual/getting-started.md` (manual seed).
- [x] `.github/ISSUE_TEMPLATE/finding.md` + `experiment-report.md`.
- [x] Naming convention pointer added to `CLAUDE.md` so future parallel chats land on the convention.
- [x] One-line contribute-back footer added to existing `docs/findings/*.md`.

### Phase D2 - per-workstream self-migration (rolling, as each chat resumes)

**Reframed 2026-05-17.** Workstreams do NOT need to "close" before D2 fires. Each parallel chat does its own move on its next active session, using an instruction block the parent chat embedded into its `*-progress.md`. The parent chat does not gate or schedule the move; it only:

- Provides the instruction block in each workstream's progress doc (done 2026-05-17).
- Reviews each migration once landed (cross-link spot check).
- Curates findings into `docs/findings/` as workstreams produce them (independent of migration).

**What each parallel chat does on resume**, per the embedded block:

1. Read `docs/planning/docs-strategy.md` (this file).
2. Create `docs/planning/workstreams/<name>/` and move its own docs into it. Rename per the convention (`*-progress.md` -> `progress.md`, `*-design.md` -> `design.md`, etc.).
3. Fix internal relative links inside the moved files. Master log is at `../../progress.md` (two levels up).
4. Note the migration in the new `progress.md`.
5. Continue working in the new structure.

**What the parent chat does after each migration:**

1. Run `python tools/check_doc_links.py` to confirm no new breakage.
2. Update `docs/README.md` map to reflect the new path.
3. Note the migration in `docs/planning/progress.md` "Documentation hygiene" section.

**Findings curation** is now decoupled from D2. Findings live in `docs/findings/` from day one (they already do). Consolidation passes (e.g. merging `dataset-hygiene.md` into `dataset-practice.md`) happen when the owning workstream produces enough context to make the merge clean, not at any fixed gate. The parent chat tracks "pending consolidation" items in `docs/planning/progress.md` "Findings curation status" section.

### Phase D3 - one-shot reorganisation (post-Renoir release)

After the objkt labs Renoir release ships and the in-flight workstreams have closed:

1. Move `docs/pipeline.md` -> `docs/manual/pipeline.md`. Polish for external read.
2. Move `docs/technique.md`, `docs/context.md`, `docs/inventory.md`, `docs/outputs.md`, `docs/dependencies.md`, `docs/dev-setup.md`, `docs/roadmap.md` -> `docs/reference/`.
3. Move `docs/modal.md` -> `docs/manual/modal.md`.
4. Promote `docs/gallery-manual-notes.md` -> `docs/manual/gallery.md`.
5. Consolidate `docs/findings/dataset-hygiene.md` + `docs/findings/dataset-practice.md` into a single `docs/findings/dataset-practice.md` once the Renoir LoRA training closes and the recipe stabilises.
6. Rename `docs/findings/lora-training.md` -> `docs/findings/lora-training-renoir.md` (worked example) and create `docs/findings/lora-pipeline.md` (generic recipe) from the export.
7. Write `docs/planning/history/2026-05-phase-1-2-port.md` summarising the consolidation + port phase.
8. Move `docs/next-exploration-steps.md` -> `docs/planning/exploration-paths.md`, rewrite each entry with a contribute-back PR target.
9. Move `docs/kickoff-prompt.md` -> `docs/planning/kickoff-prompt.md`.
10. One PR for the whole move, with `git mv` for every file so blame and history follow.

## Monitoring approach for parallel chats

Parent-chat responsibility every session resume. Before any other work:

1. Run `python tools/check_doc_links.py`. Baseline broken-link count tracked in `docs/planning/progress.md` "Documentation hygiene" section. Any new breakage is a regression to investigate.
2. List `docs/` and subdirectories. Diff against `docs/README.md` map. Any new files?
3. For each new file: which tier does it belong to? Does it follow the naming convention? Does it duplicate an existing doc?
4. If a workstream chat has self-migrated since last resume, spot-check the new folder structure and update `docs/README.md`.
5. **For deeper passes, invoke the [`docs-curator`](../../.claude/agents/docs-curator.md) subagent via the Agent tool.** It walks the tree, classifies content by maturity, and returns a structured report with promotion / consolidation / reframing / drift recommendations. Read-only; parent chat owns any moves the report suggests. Triggers: session resume after major parallel-chat activity, pre-D3 reorganisation, after a Luca-flagged discoverability failure, periodic preventive maintenance (every 5 to 10 parent sessions). Do not invoke on every session; it costs context.
5. If two new docs cover the same ground, flag the redundancy in `docs/planning/progress.md` "Findings curation status" section.
6. Do **not** edit a workstream's docs directly. Parallel chats own their folder.

## D2 firing playbook (per parallel chat, self-executed)

This is the runbook each parallel chat follows on its next active session. The parent chat has embedded a short pointer to this section in each `*-progress.md`.

**Pre-flight**

1. Confirm you are resuming a workstream whose docs still live at `docs/*-progress.md` (the old layout).
2. Read this section start to finish before making any moves.

**The move**

3. Create the target folder: `mkdir -p docs/planning/workstreams/<your-workstream-name>/`.
4. Move (not copy) your docs into it, renaming per the convention:
   - `<name>-progress.md` -> `progress.md`
   - `<name>-design.md` -> `design.md`
   - `<name>-brainstorm.md` -> `brainstorm.md`
   - `<name>-reference-plan.md` -> `reference-plan.md`
   - `<name>-followup-plan.md` -> `followup-plan.md`
   - Any other docs your workstream owns at `docs/<something>.md`: move to `docs/planning/workstreams/<your-name>/<something>.md`.
5. The repo has no git history yet (no commits), so use plain `mv`, not `git mv`. When the repo is eventually initialised as a real git history, the moves will already be in the tree.

**Fix internal links**

6. Update relative paths inside the moved files. The two patterns to watch:
   - Old `[label](progress.md)` (meaning the parent's master log at `docs/progress.md`) -> `[label](../../progress.md)`.
   - Old `[label](findings/<topic>.md)` -> `[label](../../findings/<topic>.md)`.
   - Old `[label](<sibling-progress>.md)` -> `[label](../<sibling-progress>/progress.md)` if the sibling has already migrated, OR `[label](../../<sibling-progress>.md)` if it has not yet. Easiest: assume sibling has migrated, leave a TODO comment if not.
   - Old `[label](../src/...)` or `(../examples/...)` -> add one more `../` (so `(../../src/...)`).

**Verify**

7. Run `python tools/check_doc_links.py`. Count broken links. Compare to the baseline tracked in `docs/planning/progress.md`. Your migration should REDUCE the broken-link count, not increase it.
8. Note the migration in your new `progress.md`. One line: "Migrated to `docs/planning/workstreams/<name>/` on <date>. Per D2 protocol in docs-strategy.md."

**Continue**

9. Continue your workstream from the new path. Any future docs you create live in your folder, not at `docs/` root.

**If anything in this playbook is ambiguous for your specific workstream**, post the question in your new `progress.md` and pause. The parent chat answers and updates this playbook.

## Update protocol

Any change to the tree structure, the naming convention, or the migration plan goes in this file first, then propagates: update `docs/README.md`, update `CLAUDE.md`'s naming-convention reference, update `AGENTS.md` if the agent-facing entry points changed. If you are a parallel chat and you want a structural change, post a request in your `progress.md` and the parent chat handles it.
