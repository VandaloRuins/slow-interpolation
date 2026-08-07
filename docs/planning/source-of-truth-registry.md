# Source-of-Truth Registry

> The canonical authority map for this repo. For every **fact-domain**, this registry names
> the ONE doc-type that wins when two documents disagree. `/kb-sync` MUST consult this file
> before proposing a write, so reconciliation never overwrites good data with stale data.
>
> Read this as prose, the way a human would. Nothing here is parsed by code.

Audience: you, the agent. This page tells you which document to believe when two of them
contradict each other, and which ones you are forbidden from writing at all.

---

## How to read this registry

- **Fact-domain** - a coherent category of truth (a pipeline parameter default, a
  workstream's status, a LoRA's trigger word).
- **Canonical doc-type** - the single authoritative source for that domain. When two docs
  disagree, the canonical one wins; the other is a reconciliation target.
- **Authority rule** - precisely who wins, and under what condition.
- **Guard tier** - some domains are marked `GUARD (route: <name>)`. You must NOT write
  these; route them to the owner named in `config.routes.<name>`, or FLAG them to Luca if
  that route is `null`.

The arrow of correction always points away from canon. Never edit the canonical doc to match
a downstream copy. If the evidence says canon itself is stale, that is a FLAG, not an
auto-write.

---

## Tier 0 - the universal rule (overrides everything below)

**DERIVED snapshots are NEVER authoritative.** They record what was true when written. They
are always reconciliation TARGETS, never sources. (These globs are
`config.scan_roots.snapshots`.)

| Derived snapshot doc-type | Path |
|---|---|
| Closed-phase history | `docs/planning/history/**` |
| The original kickoff brief | `docs/planning/kickoff-prompt.md` |
| One-off decision records | `docs/planning/pipeline-split-decision.md` |
| Release-prep plans | `docs/planning/private/v0.1-release-prep.md` |
| Deck / presentation drafts | `docs/planning/private/canva-*.md` |
| Superseded follow-up plans | `docs/planning/private/modal-followup-plan.md` |
| Phase acceptance records | `docs/phase-2-acceptance.md` |

Do NOT "fix" a stale snapshot by rewriting its body. It is a historical record. Either leave
it as correctly-dated history, or, if it is fully superseded AND actively misleading, PRUNE it
to `docs/planning/history/` with a forwarding pointer.

---

## Tier 1 - operations truth

The split in this tier is the one that matters most in this repo. `progress.md` and
`priorities.md` are **not** competing; they answer different questions. Do not let either
drift into the other's job.

| Fact-domain | Canonical doc-type | Authority rule |
|---|---|---|
| **Triage state**: what is due, what is blocked, what is awaiting a reply, escalation dates, Watching rows | `docs/planning/private/priorities.md` | Canonical for all *actionable* task state. Single-writer: `/todo`. Every other skill proposes. Gitignored, so it never reaches the public repo. |
| **Narrative record**: what happened, when, why, and the phase-level status table | `docs/planning/progress.md` | Canonical for the project's history and for the phase-level `Status at a glance` table. It is an append-oriented log. It is NOT a to-do list: never add an actionable row here, and never mark a `priorities.md` row done by editing this file. |
| Skill last-run / cadence state | `docs/planning/private/ops-state.md` | Each skill's own state note is authoritative for its last run. |
| Workstream routing (which tracker owns which backlog) | `docs/planning/workstream-registry.md` | Canonical for WHERE work is logged. Used by `/platform-ingest`. Routes work items, not data authority. |

**If a phase in `progress.md`'s status table conflicts with a `priorities.md` row:** the
priorities row wins for *what to do next*; the progress table wins for *what phase this is
and what shipped*. That is not a contradiction to resolve, it is the intended division. FLAG
only if the two disagree on a matter of fact (e.g. one says a LoRA published, the other says
it did not).

### Scope boundary - this repo's priorities file is PRODUCT-ONLY

`docs/planning/private/priorities.md` tracks **slow-interpolation product tasks only**: the
pipeline and technique, the code, the docs, the tooling, the repo's own releases and
packaging, and the infrastructure that runs them.

**Participation in festivals, shows, open calls, exhibitions, billboards, residencies and
commissions does NOT belong here.** That work is Luca's art practice, and its canonical
tracker is the `Ruins-agent` repo's own priorities file
(`Desktop/Ruins-agent`, buckets Applications / Productions / Commitments / Practice).

When a delta looks like participation, do not write it and do not translate it into a
product row. Note it in the close-out as `OUT-OF-SCOPE → Ruins-agent` and let Luca carry it
across. The reverse also holds: a Ruins-agent row that turns out to need a pipeline feature
becomes a product row **here**, describing the feature, never the show.

The grey zone is real and resolves on one question: *would this task still exist if the
show did not?* A `lora_scale` bug is a product task even when a show surfaced it. Preparing
a submission package is participation even when it uses the pipeline. Two such directories
lived under `docs/` until 2026-08-07 (`docs/imaf-2026/`, `docs/nyc-billboard-2026/`); both
were moved to `Ruins-agent`. Never open priorities rows from participation material, and if
any reappears in this tree, hand it off rather than committing it. See the workstream
registry's "Scope boundary" section, which is canonical for that routing.

---

## Tier 2 - technique and pipeline truth (the core KB)

| Fact-domain | Canonical doc-type | Authority rule |
|---|---|---|
| **Parameter defaults actually in force** | `src/slow_interpolation/**` (the dataclass / config field) | **The code wins over every doc.** A doc claiming `edge_crop=0` loses to the actual default in the source. When a doc disagrees with the code, the DOC is the reconciliation target. This is the single most common drift class in this repo. |
| Pipeline architecture, the four phases, the parameter spec | `docs/pipeline.md` | Canonical for how the pipeline is shaped and what each knob means. Defers to the code for the *current value* of any default. |
| Artistic framing, what the technique IS | `docs/technique.md` | Canonical. `README.md` is a derived summary of it. |
| Roadmap phases and their ordering | `docs/roadmap.md` | Canonical for intent. `progress.md` is canonical for what actually happened; a gap between them is a finding, not a conflict to flatten. |
| Distilled lesson from a closed workstream | `docs/findings/<topic>.md` | Canonical for that lesson. A finding supersedes any in-flight note in a workstream log that fed it. |
| How to perform a task, step by step | `docs/manual/<topic>.md` | Canonical operating procedure. `docs/manual/index.md` is a DERIVED dispatcher; if it disagrees, the page wins and the index is regenerated. |
| Environment setup and dependency versions | `docs/dev-setup.md`, `docs/dependencies.md` | Canonical, but defer to `pyproject.toml` / `requirements.txt` for the actual pinned versions. |
| What a specific render actually used | `examples/configs/**/*.yaml` | The config file is canonical for that render. Prose describing it is derived. |
| Published LoRA facts (HF repo id, trigger word, default scale, epoch) | the HuggingFace model card (EXTERNAL) | You cannot read HF from here. Treat in-repo mentions as derived, and when two in-repo docs disagree about a trigger or scale, **FLAG** rather than picking one. Verified against HF only by a human or a fetch. |
| Local model layout | `models/README.md` | Canonical for the on-disk convention. Contents are gitignored. |

---

## Tier 3 - workstream truth

| Fact-domain | Canonical doc-type | Authority rule |
|---|---|---|
| A workstream's own status, decisions, and open requests | `docs/planning/workstreams/<name>/progress.md`, or `docs/planning/private/<name>/progress.md` for the ones held private during a release | The workstream's own log is canonical for that workstream. `docs/planning/progress.md` carries a DERIVED roll-up row; if the roll-up disagrees, the workstream log wins and the roll-up is updated. |
| A workstream's design decisions before code | `<workstream>/design.md` | Canonical for intent within that workstream. Superseded by a `docs/findings/` page once the workstream closes. |
| Cross-workstream requests (REQUEST-N) | the requesting workstream's `progress.md` | Canonical for the ask. The owning chat executes and records completion in its own log. |

A workstream log that has been superseded by a shipped `docs/findings/` page is a PRUNE
candidate, not an ALIGN target. Move it to `docs/planning/history/` with a pointer.

---

## Tier 4 - cost and credit truth - **GUARD (route: `modal`)**

Modal credit is finite and it is the only money in this repo. You never write these figures.
Mark the delta `ROUTE_TO_modal` and hand it to the `modal` subagent.

| Fact-domain | Canonical doc-type | Authority rule |
|---|---|---|
| Modal credit balance and burn | (the Modal dashboard, external) | Route to `modal`. Never assert a balance from a doc; docs go stale within days. |
| Cost-per-render and wall-time figures | `docs/manual/modal-operations.md` + the per-render note in `progress.md` | Canonical for what a run COST when measured. A new measurement is a new data point, not a correction of the old one. Route disputes to `modal`. |
| Local-vs-cloud routing recommendation | `docs/manual/modal-operations.md` | Canonical. `docs/manual/hardware-routing.md` is the older surface it absorbed; if they disagree, `modal-operations.md` wins. |

---

## Tier 8 - structure and documentation truth - **dedupe is GUARD (route: `docs-curator`)**

| Fact-domain | Canonical doc-type | Authority rule |
|---|---|---|
| **Overlapping or duplicate docs; promotion, consolidation, reframing** | (structural op) | **GUARD (route: `docs-curator`).** Merging two docs is structural: pick the survivor, rewrite every cross-reference, fold the histories. FLAG it to `docs-curator`; never merge two docs yourself. |
| Docs tree structure, naming convention, maturity tiers | `docs/planning/docs-strategy.md` | Canonical for the intended tree. Disk disagreement is a structure finding, and Phase D2/D3 moves are still pending by design, so a file at `docs/<topic>.md` that the strategy says belongs in `reference/` is EXPECTED, not drift. |
| The docs tree map | `docs/README.md` | A DERIVED INDEX. If it disagrees with the tree, the tree wins and the index is regenerated. |
| Cross-reference integrity (relative markdown links) | the referenced file itself | A link is valid only if the target exists. Run `python tools/check_doc_links.py`. Known-good baseline is a small number of forward-refs to docs that land later; those are NOT hits. |
| Agent capability domains and their routing phrases | `CLAUDE.md` | Canonical for what each subagent owns and which phrases fire it. `AGENTS.md` is the public-facing derived view. |
| Documentation audience convention | `AGENTS.md` "Documentation audience convention" | Canonical. Everything under `docs/` addresses the agent in the second person; `README.md` is the only human-facing doc. |

---

## Conflict-resolution decision procedure

Given two docs A and B stating different things about fact F:

1. If either is a Tier 0 snapshot, the non-snapshot wins. If both are snapshots, neither is
   authoritative - FLAG.
2. If F is a parameter default and one side is source code, **the code wins**, always.
3. Else look up F's fact-domain above. The canonical doc-type wins. If it is a **guard tier**,
   do not write - route via `config.routes` (`budget` → `modal`, `dedupe` → `docs-curator`),
   or FLAG if the route is `null`.
4. The losing doc becomes a hit, classified **ALIGN / MERGE / PRUNE / FLAG**.
5. NEVER edit canon to match a non-canonical doc. If evidence suggests canon is wrong, FLAG.

### The "canon might be the stale one" caveat

This registry tells you which doc-type wins a tie, not which doc holds the freshest fact.
When a SESSION establishes new truth, that emergent truth propagates INTO canon first, then
outward. This is why `/kb-sync` is delta-driven from session truths, not a blind
canon-vs-non-canon diff.

---

## Deletion rule (hard constraint)

PRUNE means **move to `docs/planning/history/`**, preserving the file, and leave a one-line
forwarding pointer at the old location:
`RETIRED <date>, superseded by <canonical path>, archived to <archive path>`.

NEVER hard-delete docs content. NEVER `replace_all` on a multi-entity file (this registry,
`progress.md`, `docs/README.md`, `docs/manual/index.md`, the priorities file) - surgical
row-level edits only. Every PRUNE is reversible by moving the file back; hard-delete is not.

## Public-repo constraint (specific to this repo)

This repo is **public** (`github.com/VandaloRuins/slow-interpolation`) and workshop-facing.
Before you propose writing any fact into a tracked doc, check it is not one of the things the
repo deliberately keeps private: release timing, client and venue names, spend figures,
parallel-project references, and machine-specific paths. Those belong in `CLAUDE.local.md`,
`docs/context.local.md`, or `docs/planning/private/` - all gitignored. If a delta would put
one of them in a tracked file, FLAG it instead of writing.