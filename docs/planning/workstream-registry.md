# Workstream Registry

> The routing table `/platform-ingest` reads (`config.project_registry`). It maps each area of
> code to the tracker that owns its backlog, so a session's work lands in the right log
> instead of all piling into the master integration log.
>
> Read the `## Project Registry` section below as prose. Nothing here is parsed by code.

Audience: you, the agent. When a session touches files, match the touched paths against the
**Detection globs** column, then write the delta into that row's **Tracker home**, in that
row's **Dialect**. When nothing matches, use the `(default)` row.

## Project Registry

| Project | Detection globs | Tracker home | Dialect | Owner | Ingest writes? | Status |
|---|---|---|---|---|---|---|
| modal-infra | `cloud/**` (except `train_*`, `inpaint*`), `docs/manual/modal-operations.md` | `docs/planning/workstreams/modal/progress.md` | dated session entry at the top, then update the status line; cost + wall-time figures go in the entry | `modal` subagent | yes | Phase 3.5 done; release-batch tier gated on LoRA arrival |
| modal-trainer | `cloud/train_*.py`, `examples/configs/training/**` | `docs/planning/private/modal-trainer/progress.md` | dated session entry + `next-session-plan.md` refresh | parallel chat | yes | **private during v0.1**; surfaces publicly in v0.2 once the cold-run validates |
| noise | `src/slow_interpolation/noise/**`, `tests/**noise**`, `docs/manual/noise.md` | `docs/planning/workstreams/noise/progress.md` | dated entry; new sources get a row in the source table | parallel chat | yes | Done and wired into `PipelineConfig` |
| renoir-dataset | `datasets/renoir*/**`, `examples/configs/renoir/**`, `cloud/validation_renoir.py` | `docs/planning/workstreams/renoir-dataset/progress.md` | dated entry; epoch/scale verdicts go in `validation-grid.md` | `dataset-mosaic` subagent | yes | LoRA trained, validation grid shipped |
| soutine-lora | `datasets/soutine*/**`, `models/loras/Soutine_*` | `docs/planning/private/soutine-lora/progress.md` | dated entry + design.md amendment | parallel chat | yes | **private during v0.1**; Modal-trained keepers in hand |
| compositing | `src/slow_interpolation/compositing/**`, `cloud/compositing_sketch.py`, dual-LoRA / `extra_styles` work | `docs/planning/private/compositing/progress.md` | dated entry; cross-workstream asks as `REQUEST-N` rows | parallel chat | yes | **private during v0.1**; fully unblocked, owns REQUEST 0 |
| inpaint | `cloud/inpaint*`, `tools/make_figure_mask.py`, `tools/gallery.py` gallery-brush work | `docs/planning/private/inpaint/design.md` | design doc has no progress log yet; append a dated `## Session` section, or open `progress.md` if the workstream goes active | parallel chat | yes | **private during v0.1**; design in iteration, pre-impl |
| alt-techniques | (exploratory, no code yet) | `docs/planning/private/alt-techniques/brainstorm.md` | freeform brainstorm; promote to a real workstream before writing code | Luca | yes | pre-workstream |
| core-pipeline | `src/slow_interpolation/{config,keyframes,pipeline,prompts,run,smoothing,encoding,borders}.py`, `src/slow_interpolation/{core,interpolation,loras,live}/**` | `docs/planning/progress.md` | parent-chat session paragraph + a row in `## Status at a glance` if it moves a phase | parent chat | yes | the pipeline itself; no separate tracker by design |
| docs-tree | `docs/README.md`, `docs/manual/index.md`, `docs/planning/docs-strategy.md`, cross-doc moves | (hand off) | - | `docs-curator` subagent | **no** (hand off) | structural moves are `docs-curator`'s call; emit a hand-off note |
| harness | `tools/agent-ops-harness/**`, `agent-ops-harness.config.json`, `docs/planning/*-registry.md` | `docs/planning/progress.md` | one-line entry under the current session paragraph | parent chat | yes | installed 2026-08-07 |
| festival / show participation | any open-call, exhibition, commission, billboard or residency material, wherever in the tree it appears | (hand off) | - | `Ruins-agent` repo | **no** (out of scope) | no such material in-repo as of 2026-08-07; see "Scope boundary" below |
| (default) | anything unmatched | `docs/planning/progress.md` | dated parent-chat session paragraph at the top of the narrative section | parent chat | yes | - |

### Columns
- **Detection globs** - the touched-path signal `/platform-ingest` matches session file
  changes against (primary classification input).
- **Tracker home** - where this area's backlog lives.
- **Dialect** - how to add an item to THAT tracker. Each log keeps its own convention;
  follow whatever the row says rather than imposing one format.
- **Owner** - who owns that tracker.
- **Ingest writes?** - `yes` = `/platform-ingest` may write it directly; **`no`** = another
  owner holds it; emit a hand-off note instead of writing.
- **Status** - a one-line current-state cell to update each ingest.

## Scope boundary - product work only

This registry routes **slow-interpolation product work**: pipeline, technique, code, docs,
tooling, packaging, infrastructure.

**Festival, show, open-call, exhibition, billboard, residency and commission participation
is out of scope.** It belongs to the `Ruins-agent` repo (`Desktop/Ruins-agent`), which has
its own priorities file and its own Applications / Productions / Commitments / Practice
buckets. Do not open a row for it here, and do not restate it as a product task.

Test: *would this task still exist if the show did not?* If yes, it is product work and
belongs here. If no, hand it off. A bug that a show surfaced is still a product task; a
submission package that uses the pipeline is still participation.

Two directories used to sit here on the participation side, `docs/imaf-2026/` and
`docs/nyc-billboard-2026/`. They were **moved out on 2026-08-07** to the `Ruins-agent` repo
under `knowledge/grants&opencalls/{italia-media-art-festival,one-love-nyc-billboard}/`. Before
the move, `conform.py` was promoted out of the billboard folder to `tools/conform.py` and
de-personalised, because the delivery-conform pattern is generic product tooling even though
the placement that produced it was not.

The durable rule, which is what this row is really for: **participation material that appears
in this repo gets handed off, not committed.** This repo is public, so a submission brief or a
client spec landing under `docs/` is both a scope error and a disclosure risk. Move it to
`Ruins-agent`, and keep only whatever generic tooling it produced.

## The public/private split

Five workstreams live under `docs/planning/private/` (gitignored) because they carry
release timing, parallel-project references, or unpublished results. **Never move a delta
from a private tracker into a public one without checking it against the public-repo
constraint** at the bottom of `source-of-truth-registry.md`. When a private workstream
surfaces publicly (planned for v0.2), that is a deliberate move Luca makes, not a
reconciliation you perform.

## The master integration log

`docs/planning/progress.md` is the cross-workstream audit trail and the narrative record.
Every workstream that ships something gets a pointer entry there, even when its detail lives
in its own log. It is **not** a to-do list: actionable state belongs in
`docs/planning/private/priorities.md`, written only by `/todo`.

## Gitignored artifacts (never write, never pass to `ship commit --paths`)

`outputs/`, `datasets/**` image bytes and ZIPs, `models/loras/*`, `models/hf-staging/`,
`train-artifacts/`, `local-spot-check/`, `pitch-materials/`, `.playwright-mcp/`,
`CLAUDE.local.md`, `docs/context.local.md`, `docs/planning/private/`, `.env`.

Two of these are the reason the rule exists: `docs/planning/private/` holds the priorities
file, and `.env` holds credentials. Name files explicitly in `--paths`; a directory pathspec
silently sweeps in everything beneath it.