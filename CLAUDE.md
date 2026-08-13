# slow-interpolation -- Claude Code context

This is the dev workspace for the `slow-interpolation` project. Read this file at session start.

If a `CLAUDE.local.md` sidecar exists in the repo root (it is gitignored; present only on the original author's machine), read it too. It carries personal context, parallel-project boundary notes, and machine-specific paths that are not shipped to the public repo.

## Who is the author

The project is by Luca Martinelli (Vandalo Ruins), an Italian digital artist with a theater-to-digital trajectory and an expanded-literature practice. He is technically fluent (Python, ComfyUI, training pipelines) but values strong opinions, terse responses, and clean structure. He hates em dashes in written output; use commas, periods, parentheses, or "to" for ranges.

## What this repo is

`slow-interpolation` codifies a diffusion-based slow drift technique that Luca has been developing as a ComfyUI workflow. The repo's job is to turn the workflow into reusable, scripted Python, then extend it with new noise sources, live webcam-driven generation, dual-prompt compositing, and anchored live prompting. The long-term plan is to open-source it on GitHub.

Read [README.md](README.md) and [docs/technique.md](docs/technique.md) before any creative discussion. Read [docs/roadmap.md](docs/roadmap.md) before any planning discussion. Read [docs/planning/progress.md](docs/planning/progress.md) before doing any code or planning work.

## What the technique actually is

The pipeline is **NOT** the ComfyUI workflow that lives in `legacy/comfy-archive/` (that's an unrelated earlier experiment). The real source is the scripted Python pipeline developed for Choire v2 (vertical fresco videos) and ported to After Cole (horizontal Hudson River School landscapes). It is now under `legacy/choire-v2/` and `legacy/after-cole/`, read-only reference.

Four-phase pipeline:

- **Phase A. Keyframes.** SDXL Lightning 4-step + a domain LoRA (Casa del Suono fresco, Thomas Cole, soon Renoir flowers) img2img-chained through a calibrated denoise schedule. Each clip is built from segments A/B/C/A-return with prompt-defined steady frames and SLERP-blended transitions.
- **Phase A.5. Temporal smoothing.** Frequency-separated smoother (low-freq blended across a window of 8 frames at sigma 1.5, high-freq from the center frame) to remove jitter without ghosting.
- **Phase B. Upscale.** Real-ESRGAN x2 is wired but currently disabled (it destroyed the fresco aesthetic). Decision is open for Renoir.
- **Phase C. Interpolation.** RIFE v4.25, 64x (6 passes), linear timestep (not recursive binary), skip-keyframes, skip-boundary 4. This is what makes the motion glacial without ever pausing.
- **Phase D. Encoding.** H.264, 24 fps.

See [docs/pipeline.md](docs/pipeline.md) for the full parameter spec and [docs/technique.md](docs/technique.md) for the artistic framing.

The Renoir release is the same pipeline with a freshly trained Renoir flowers SDXL LoRA in place of the Casa del Suono / Thomas Cole LoRA, plus a Renoir-specific subjects dict (A/B/C/A flower scenes).

## Working style preferences

- **No em dashes** (—). Ever. Use commas, periods, or "to" for ranges.
- **Terse responses.** Short answers, complete sentences, no trailing summaries unless asked.
- **Strong opinions.** When trade-offs exist, name the trade-off and recommend a default, do not list options without taking a position.
- **Don't over-engineer.** No premature abstractions, no scaffolding for hypothetical features. The roadmap is phased on purpose.
- **Pause on risky operations.** Destructive git, force-push, mass file moves, dependency removals: confirm first.
- **Trust internal code.** No defensive validation for impossible inputs. Validate only at boundaries (user input, external APIs, file I/O).

## Repo layout

```
slow-interpolation/
  src/slow_interpolation/   future scripted core (empty until Phase 2 of roadmap)
  legacy/
    after-cole/             Thomas Cole horizontal pipeline (scripts + docs). READ-ONLY.
    choire-v2/              Casa del Suono vertical pipeline (scripts + research). READ-ONLY.
    comfy-archive/          earlier unrelated Comfy experiment. Reference only.
  examples/outputs/         sample MP4s from both prior projects
  docs/                     technique, pipeline, inventory, roadmap, next-exploration-steps, dev-setup, kickoff-prompt
  datasets/                 gitignored (Renoir LoRA dataset will live here)
  outputs/                  gitignored
```

The first session in this repo ran the kickoff prompt at [docs/planning/kickoff-prompt.md](docs/planning/kickoff-prompt.md), which was a two-step plan: Step 1 consolidates and documents the legacy code, Step 2 reads [docs/next-exploration-steps.md](docs/next-exploration-steps.md) and proposes an exploration plan. Both steps are complete; the file is preserved for posterity.

## Decision authority

| Decision | Owner |
|----------|-------|
| Artistic direction, release content | Author |
| Code architecture, module boundaries | Agent proposes, author approves |
| Model / training hyperparameters | Author |
| Dataset curation | Author |
| Open-source license and publishing timing | Author |

## Documentation conventions

Read [docs/planning/docs-strategy.md](docs/planning/docs-strategy.md) before adding a new doc. Quick rules:

- **Workstream status log:** `progress.md` under `docs/planning/workstreams/<name>/`. While the migration is in progress (Phase D2 not yet executed), some workstream docs still live at `docs/*-progress.md` and `docs/*-design.md` and will be moved later.
- **Workstream design before code:** `design.md` under `docs/planning/workstreams/<name>/`.
- **Workstream pre-design brainstorm:** `brainstorm.md` under `docs/planning/workstreams/<name>/`.
- **Distilled lesson after a workstream ships:** `<topic>.md` under `docs/findings/`.
- **User manual page:** `<topic>.md` under `docs/manual/`.
- **Durable project reference:** `<topic>.md` under `docs/reference/` (today still at `docs/<topic>.md`; will move at Phase D3).

The master integration log is [docs/planning/progress.md](docs/planning/progress.md); only the parent chat writes to it. Each parallel workstream writes only inside its own folder. To change a file outside your write zone, post a request in your `progress.md` and the parent chat will execute the edit.

External-facing entry points (read these if you are unsure how the docs flow):

- [README.md](README.md) for humans landing on GitHub.
- [AGENTS.md](AGENTS.md) for AI agents picking up the repo.
- [CONTRIBUTING.md](CONTRIBUTING.md) for the contribute-back path.
- [docs/README.md](docs/README.md) for the docs tree map.

**Periodic docs curation**: the [docs-curator subagent](.claude/agents/docs-curator.md) reviews the docs tree and classifies content by maturity (raw notes → research → emerging pattern → documented protocol → student-agent prompt). Invoke via the Agent tool when resuming after parallel-chat activity, before D3 reorganisation, after a discoverability failure, or as periodic maintenance. Read-only; parent chat owns any moves the report suggests.

## The four subagents

Capability-domain specialists. Any chat can invoke any of them via the Agent tool. The framing replaces the older "parallel chats as pseudo-subagents" model (workstream chats that owned per-folder write zones); workstreams are now time-bounded project logs, not capability namespaces.

| Agent | Domain | Operating manual | Can invoke |
|---|---|---|---|
| [`modal`](.claude/agents/modal.md) | Modal cloud infra: routing decision, dispatch, monitoring, volume housekeeping, SDK quirks. Aware of finite Modal credit; recommends local when local would do. | [`docs/manual/modal-operations.md`](docs/manual/modal-operations.md) | (primitive; no agents) |
| [`dataset-mosaic`](.claude/agents/dataset-mosaic.md) | End-to-end "ship a LoRA": 5-phase curation, gallery hand-off, training dispatch, validation visual call, re-curation when over-fit. | [`docs/manual/dataset-curation.md`](docs/manual/dataset-curation.md), [`gallery.md`](docs/manual/gallery.md), [`train-lora-on-modal.md`](docs/manual/train-lora-on-modal.md), [`validate-lora.md`](docs/manual/validate-lora.md) | `modal` |
| [`lever`](.claude/agents/lever.md) | Per-render interpolation tuning: noise + RIFE + SDXL Lightning + `lora_scale` + denoise schedule + per-prompt negatives + loop-closure. Read-only consult; returns YAML stanzas with rationale. | synthesises across `manual/noise.md` + 5 findings + decisions log (no umbrella page yet) | (primitive; consults docs) |
| [`docs-curator`](.claude/agents/docs-curator.md) | Documentation health, classification by maturity, promotion / consolidation / reframing recommendations. Two-phase pattern (Phase 0 flush + Phase 1 classify). | itself | (primitive) |

**Runtime note:** Claude Code does not pick up project-local custom agent types directly. Invoke via the `general-purpose` subagent with the agent file at `.claude/agents/<name>.md` as the operating prompt. We verified this pattern works for `docs-curator`; same pattern applies to the others. When Claude Code adds custom-agent-type loading, switch to direct invocation.

## Natural-language invocations

The user (Luca) drives this project through natural language. When he says any of the phrases below, fire the matched action immediately. Do NOT ask "which agent / which command" first; the mapping is unambiguous.

| Phrase family (any close paraphrase counts) | Action |
|---|---|
| **docs-curator** | |
| "curate the docs", "review the docs", "audit the docs", "do a docs curation pass", "what needs documenting", "are the docs drifting", "check the docs tree" | Invoke `docs-curator` via the Agent tool. Phase 0 emits the parallel-chat flush prompt; surface it to the user and remind them to paste it into active workstream chats. |
| "chats have flushed, curate the docs", "post-flush curation", "skip phase 0", "do the full curation", "workstreams are caught up, curate" | Invoke `docs-curator` with the explicit skip signal. Verify flushes first via `grep -l "Pre-curation flush completed" docs/planning/workstreams/*/progress.md`. |
| "spawn a curator", "send the curator", "ask the curator", "what protocols are emerging", "any new patterns" | Same as "curate the docs". |
| **modal** | |
| "dispatch this to Modal", "run this on Modal", "render on Modal", "send X to Modal" | Invoke `modal` with the task. Modal will run pre-flight + routing first if needed. |
| "local or Modal for this", "where should this render", "what's the cost vs local", "should I burn modal credit on this" | Invoke `modal` for a routing-only recommendation. Modal returns wall + cost both ways, recommends one. |
| "modal pre-flight", "check modal", "modal hardware check", "what GPU do I have" | Invoke `modal` to run / re-run the pre-flight cache. |
| "smoke test modal", "modal smoke", "is modal working" | Invoke `modal` to run `cloud/smoke.py`. |
| "build a modal app for X", "add a modal capability for X", "extend cloud/Y" | Invoke `modal` to author or extend `cloud/*.py`. |
| "monitor the modal job", "where's the modal job", "modal dashboard" | Invoke `modal` to extract dashboard URL + log tail; surface to user. |
| "what's on the modal volumes", "modal volume size", "clean up modal staging", "modal volume gc" | Invoke `modal` to run `cloud/volume_admin.py` operations. |
| "modal is broken", "modal error: X", "I got a NotFoundError on modal" | Invoke `modal` to diagnose against the SDK + sd-scripts quirk libraries. |
| **dataset-mosaic** | |
| "build a dataset for X", "curate a dataset for X", "dataset mosaic for X" | Invoke `dataset-mosaic` to walk Phase 0 to 5 of the curation protocol. |
| "ship a LoRA for X", "train a LoRA for X", "I want a Y LoRA" | Invoke `dataset-mosaic` for the full curate → train → validate arc. It calls `modal` for training and validation dispatch. |
| "validate the X LoRA", "compare epochs of the X LoRA", "is the X LoRA over-fit" | Invoke `dataset-mosaic` for the validation pass + visual checklist walk. |
| "the X LoRA over-fit, re-curate", "fix the X dataset", "re-audit the X dataset" | Invoke `dataset-mosaic` for the targeted re-curation. |
| "what's the state of the X dataset", "where is the Y dataset" | Invoke `dataset-mosaic` to report. |
| "package X for training", "build the training ZIP for X" | Invoke `dataset-mosaic` Phase 5. |
| "browse the X dataset", "glance mosaic for X", "dataset mosaic link for X", "show the final X set with crops" | Build + serve the read-only dataset Glance mosaic per [docs/manual/dataset-glance.md](docs/manual/dataset-glance.md). Main session can do it directly (reads `datasets/<name>/`, writes only `tools/mosaic-glance/`). NOT the Phase 3 review surface; student actions stay in the curation gallery. |
| **lever** | |
| "what settings for X", "what knobs for this Y render", "tune this clip", "tune this YAML" | Invoke `lever` for a YAML stanza or diff with rationale. |
| "pick noise for X", "what noise source for X", "tune the noise for this clip" | Invoke `lever` for the noise-decision walk. |
| "this clip is too smooth, what should I bump", "this looks under-tuned", "what's wrong with this render" | Invoke `lever` for a diagnostic. Returns "bump X, here's why" or "this is upstream, talk to dataset-mosaic". |
| "what lora_scale for X", "what epoch + scale for the Y render" | Invoke `lever` to consult the per-LoRA decisions-log entries. |
| "is edge_crop: 0 safe for this LoRA", "should I crop borders for X" | Invoke `lever` for the per-LoRA risk check. |
| "give me an expressionist preset", "give me a Renoir field preset", "show me the Y tuning cluster" | Invoke `lever` for a documented preset. |
| **session orchestration (agent-ops harness)** | |
| "what's on the list", "what should I work on", "check the todo", "priorities", "what's hot" | Invoke `/todo`. Sole writer of `docs/planning/private/priorities.md`. Propose, gate, apply: it never writes without an approved diff. |
| "ingest this session", "capture what we did", "log this session", "close out the session" | Invoke `/ingest` (session close, Phase 1). Reconciles the priorities file against what this session established, then emits a `kb-sync-delta` block. |
| "sync the docs", "propagate this everywhere", "we renamed X, fix the references", "the rest of the docs still say the old thing" | Invoke `/kb-sync` (session close, Phase 2). Consumes the delta block, propagates canon-first via `docs/planning/source-of-truth-registry.md`. **Separate approval from `/ingest`, never one bundled yes.** |
| "log the code work", "route this to the right workstream", "which tracker owns this", "update the workstream logs" | Invoke `/platform-ingest`. Routes work items to the tracker named in `docs/planning/workstream-registry.md`. |
| "commit this", "push this", "land this", "ship it" | `python tools/agent-ops-harness/shared/ship.py commit --paths <files> -m "msg" --push`. Never `git add -A`. Never name a directory in `--paths`. See "Landing work" below. |
| **utility** | |
| "check links", "link-check", "any broken links", "lint the docs links", "validate cross-references" | Run `python tools/check_doc_links.py` via Bash. Summarise count + categorise. |
| "what's blocked", "what's gated on what", "what's waiting on X" | Read `docs/planning/private/priorities.md` FIRST (it owns blocked/awaiting state), then `docs/planning/progress.md` "Status at a glance" + workstream progress docs for the phase picture. Summarise the dependency chain. |
| "resume operations", "let's resume", "what's the state" | Run the resume protocol: read progress.md top banner, list since-last-resume changes, surface pending parent-chat actions. |

If a phrase plausibly matches more than one row, pick the row that fires the most specific action. If a phrase is genuinely ambiguous (rare), ask the user to disambiguate before acting. Do not pre-emptively fire if the user is mid-explanation; wait for a clear request.

New invocations get added here as patterns surface. The user can extend this map at any time by saying "from now on when I say X, do Y" or similar.

**Audience convention for everything under `docs/`:** written for AI agents, not for human readers. README.md is the only human-facing doc; humans read it, then delegate to their agent. When you (or any parallel chat) writes a manual page, a finding, a reference, or a plan, address the agent in the second person, name what YOU (the agent) do vs what the USER does, and prefer operational decision tables over prose troubleshooting. The canonical examples are `docs/manual/dataset-curation.md` and `docs/manual/gallery.md`. Full rule in [AGENTS.md](AGENTS.md) "Documentation audience convention" + [docs/planning/docs-strategy.md](docs/planning/docs-strategy.md) "Audiences" section.

## Session orchestration (agent-ops harness)

Installed 2026-08-07 at `tools/agent-ops-harness/`, config at `agent-ops-harness.config.json`. Four skills plus a parallel-git gate. They are prose instruction sets; every project fact they need lives in the config, never in the prose.

**Two files, two jobs, and they must not drift into each other:**

| File | Owns | Never holds |
|---|---|---|
| `docs/planning/private/priorities.md` (gitignored) | Triage. What is due, what is blocked, what is awaiting a reply, escalation dates. Sole writer: `/todo`. | Narrative history. Phase-level status. |
| `docs/planning/progress.md` (tracked) | The narrative record and the phase-level `Status at a glance` table. | Actionable rows. Never mark a priorities row done by editing this file. |

**Scope: product only.** The priorities file tracks the pipeline, technique, code, docs, tooling, packaging and infrastructure. Festivals, shows, open calls, exhibitions, billboards, residencies and commissions belong to the `Ruins-agent` repo, which has its own priorities file. The test is *would this task still exist if the show did not?* A bug a show surfaced is product work; a submission package that uses the pipeline is not. Two participation directories lived under `docs/` until 2026-08-07 and were moved to `Ruins-agent`; if any reappears here, hand it off rather than committing it. This repo is public, so a client spec landing under `docs/` is a disclosure risk as well as a scope error.

**Session close is two phases and two approvals.** `/ingest` reconciles the priorities file and emits a delta block; `/kb-sync` consumes that block and propagates each truth into the wider docs tree, canon-first, via `docs/planning/source-of-truth-registry.md`. The two approvals are never bundled into one yes: you may approve the ops rows and decline the docs cascade.

**The two registries are the safety spine.** [source-of-truth-registry.md](docs/planning/source-of-truth-registry.md) says which document wins when two disagree, and which you are forbidden from writing (`budget` routes to the `modal` subagent, `dedupe` routes to `docs-curator`). [workstream-registry.md](docs/planning/workstream-registry.md) says which tracker owns which backlog. Read the relevant one before proposing a write.

**One rule specific to a code repo:** for a parameter default, `src/slow_interpolation/**` wins over every doc. A doc claiming a default that the dataclass contradicts is the reconciliation target, never the other way round.

**Public-repo constraint.** This repo is public and workshop-facing. Release timing, client and venue names, spend figures, parallel-project references and machine paths stay in `CLAUDE.local.md`, `docs/context.local.md` or `docs/planning/private/`, all gitignored. If a delta would put one of them in a tracked file, FLAG it instead of writing.

### Landing work

Trunk is `origin/main`. Close the loop with the ship gate, not plain git:

```
python tools/agent-ops-harness/shared/ship.py commit --paths <files> -m "msg" --push
```

It builds the commit on a temporary index parented on a freshly fetched trunk, so it never touches the working tree and cannot collide with a parallel chat. It informs rather than blocks, with one exception: a secret scan that exits 3 and commits nothing.

- Land the moment approved edits are applied, same turn. Uncommitted edits in a shared tree are how two chats deadlock on one file.
- Never `git add -A`. Name files in `--paths`, never directories, and read the `--dry-run` list first.
- You do not need to be on `main` to commit to `main`.
- `ship untracked` lists real content nobody ever committed; `ship contested` lists files carrying another chat's hunks. `ship rules` prints the full standard.

The session hooks live in `.claude/settings.local.json` (gitignored), so they fire on the maintainer's machine only and a student cloning the repo inherits nothing.

## Verify the way the user will experience it

Standing rule, from the 2026-08-08 render session. Before telling Luca something is
ready, check it through the path he will actually use, not the path that produced it.

On that day the agent said "it's live" or "it's fixed" five times when it was not, and
**every failure was silent**: a command exited zero having written nothing, a page
contained the right markup but had never been rebuilt, a security test passed against a
different application, a server returned 200 to a range request it had ignored, and a
sharpness verdict came from a montage that discarded two thirds of the resolution.

Concretely:

- A code change is not a page change. Rebuild, then check the **served** artefact.
- An exit code is not a result. Check the artefact exists and has the expected size or count.
- Never report a fix from the same measurement that motivated it.
- If the user reports something you cannot reproduce, suspect the **viewing path** first:
  a compressed proxy, a downscaled sheet, a cached page, a stale build.

The four skills in `.claude/skills/` encode the specific traps per workflow.

## Memory Doctrine

Memory has three surfaces here and they are not interchangeable. The failure mode is writing *status* into memory, where it goes stale invisibly and no reconciliation routine can see it.

| Surface | Location | Holds | Does NOT hold |
|---|---|---|---|
| Auto-memory | `~/.claude/projects/…-slow-interpolation/memory/` | Who Luca is, how he wants work done, standing facts about the project and its constraints, pointers to external resources. Loaded every session via `MEMORY.md`. | Task status, deadlines-as-todos, anything `priorities.md` owns. |
| The docs tree | `docs/**` | Everything about the technique, pipeline, findings, manuals, workstreams. The durable record. | Session-scoped scratch. |
| The code | `src/`, `cloud/`, `examples/configs/` | What the pipeline actually does and what a render actually used. | Intent and rationale, which belong in docs. |

**Rules**

1. **Status belongs in `priorities.md`, never in memory.** A memory saying "deadline 12 Aug" cannot be reconciled, will not be marked done, and will still read as urgent in November. Write the standing fact to memory and the dated obligation to the priorities file. This is not hypothetical: on 2026-08-07 the `Ruins-agent` repo was found holding three live dated obligations in auto-memory and in no tracked file at all.
2. **One fact per file**, with frontmatter (`name`, `description`, `metadata.type` of `user` / `feedback` / `project` / `reference`). Add a one-line pointer to `MEMORY.md`. Never put memory content in `MEMORY.md` itself; it is an index.
3. **Convert relative dates to absolute** before writing.
4. **Check before you add.** Update the existing file rather than creating a near-duplicate; delete a memory that turns out to be wrong.
5. **Do not save what the repo already records.** The pipeline spec belongs in `docs/pipeline.md`, a tuning lesson in `docs/findings/`. If asked to remember one of those, ask what was non-obvious about it and save that instead.
6. **`/kb-sync` never writes memory.** It may FLAG a memory that contradicts canon; editing one is Luca's call.
7. **Link liberally** with `[[name]]`. A link to a memory that does not exist yet marks something worth writing, not an error.
