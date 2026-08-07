---
name: platform-ingest
description: Project-aware platform ingest. Scans the session for code/platform/deploy/infra work and routes each item to the right per-project tracker via a project registry you define. The platform counterpart to /ingest. Propose-then-apply with a mandatory approval gate. Reads its routing from agent-ops-harness.config.json. Invoke with /platform-ingest.
modes: ["ingest", "status"]
---

# /platform-ingest — Project-Aware Platform Ingest

> Part of the **agent-ops harness**. Where `/ingest` reconciles the operations file,
> `/platform-ingest` routes CODE / platform work across several per-project trackers via a
> **project registry** you define (`config.project_registry`). Same propose-gate-apply
> discipline; obeys `shared/doctrine.md`.

**Source of routing truth:** the `## Project Registry` section of `config.project_registry`
(a markdown table you maintain: Project | Detection globs | Tracker home | Dialect | Owner |
Ingest writes?). A generic example ships at
`tools/agent-ops-harness/config/project-registry.md`.

**Scope:** code / platform / deploy / infra / database work. Non-code operational work
(partner comms, planning, funding) routes to `/todo` / `/ingest`, NOT here. If unsure, ask
which lane.

Why it exists: platform work spreads across a flat backlog AND several deeper per-project
trackers (a roadmap here, a working-doc there). A plain "append to the backlog" ingest lets
those deep trackers drift. This skill reads the registry, detects which project(s) the
session touched, and writes each delta to that project's tracker **in its own dialect**.

## Triggers
"platform ingest", "dev ingest", "ingest the dev work", "log the website/platform work",
"update the platform tracker", "reconcile the platform backlog".

---

## Mode: ingest (default)

Context comes from THIS conversation (the session lived the work), not a KB re-scan. No mail
fetch, no stale Q&A — mirror `/ingest`'s discipline.

### Sequence
**1. Self-context scan.** Read this chat end-to-end; tag each platform item **built/shipped**,
**decided**, or **deferred/owed**. Run `git diff --name-only` (+ `--staged`, + note untracked
new files) — the **touched-path signal** is the primary classification input.

> **A SESSION THAT SHIPPED VIA THE SHIP GATE HAS AN EMPTY WORKING-TREE SIGNAL.**
> `ship commit` builds in a temporary index and **never touches the shared working tree** —
> that is the entire point of it (`shared/parallel-git.md`). So for any session that landed
> work that way, `git diff --name-only` shows only *other* sessions' dirt and none of your
> own, and this ingest would classify the session as having done **nothing**. Always
> cross-check against the session's own commits:
>
> ```bash
> git log --oneline origin/<trunk> -25     # find this session's shas
> git show --stat <sha>                    # touched paths per commit
> ```
>
> Treat the **union** of (working-tree diff) and (this session's commits) as the
> touched-path signal. The working tree alone is sufficient only for sessions that used raw
> `git add`, which the ship gate exists to discourage.

**2. Classify each item -> project** via the registry:
- **Primary:** match touched paths against each project's *Detection globs*.
- **Secondary:** ALL-CAPS / topic tags in the discussion when paths are ambiguous or no file
  was touched.
- **Fall-through:** anything unmatched -> the `(default)` row (your flat backlog). Never
  silently drop an item.
- **Boundary check:** if an item is really non-code ops, set it aside for a `/todo` handoff
  (step 8).

**3. Read each touched tracker fresh** (the ones that got >=1 item), so the diff is built
against current content (concurrency safety).

**4. Build a per-project diff outline, grouped by project, in each tracker's native dialect.**
One outline covering all touched projects. Each registry row declares its dialect; follow it.
A project whose registry row says **Ingest writes? = no** is a **hand-off, not a write**:
emit a "route to `<owner skill>`" note (step 8), do not edit its tracker.

**CROSS-TRACKER FINALIZE IS NOT OPTIONAL (the most-skipped step).** When work routes into a
project's own tracker it is tempting to stop there. But every touched project ALSO owes, in
this same outline:
1. a **registry `Status`-cell** update (always, for any touched project), and
2. a **global Shipped Log** pointer row in your flat backlog (whenever anything shipped this
   session — the project keeps the detail in its tracker; the global log gets the terse row,
   so the flat backlog stays the single cross-project audit trail).

**Pre-gate self-check:** for each touched project confirm the outline has (a) its tracker
delta, (b) a registry status line, and (c) a global Shipped Log row if anything shipped. Any
missing -> the outline is INCOMPLETE; add it before the gate.

Example outline shape:
```
### <project A> -> <its tracker home>  (<dialect>)
DONE (1)
- [x] <item> (<detail>)
OPEN (1)
- [ ] <item>
### <flat backlog>  (light / cross-cutting)
Shipped Log (1)
- YYYY-MM-DD | <item> | `<commit>` | <notes>
### Registry status updates
- <project A> -> "<new one-line status>"

Approve all? Selectively? Walk through one-by-one?
```

**5. MANDATORY APPROVAL GATE — NO EXCEPTIONS.** Before ANY Edit/Write on ANY tracker, emit
the full grouped outline, STOP, wait for explicit approval **in this turn** that names the
diff. Soft signals ("go ahead", "ok") do not count unless they reference the outline. Being
invoked authorises running the skill, NOT unilateral writes.

**6. Apply surgically.** On approval, one edit at a time. Re-read each target immediately
before its Edit (parallel chats edit the shared tree concurrently); if a section changed
since step 3, rebuild that delta and re-confirm. **Never `replace_all`.**

**7. Finalize.** Update touched projects' registry `Status` cells; append the global Shipped
Log rows; bump the flat backlog's `updated:` frontmatter and prepend a `last_ingest:` note
(date + projects touched) — **but skip that frontmatter bump if it already carries another
session's uncommitted edit** (frontmatter is the most-contested block; the Shipped Log row is
the durable record, the note is convenience). Say in the summary when it was skipped.

**8. Emit handoffs (do NOT act on them here).**
- Any project whose registry row is **Ingest writes? = no** -> "Run `<owner skill>` to fold
  this in: <summary>." (e.g. a data/curation lane owned by another skill via `config.routes`.)
- Any non-code ops item -> "Route to `/todo`: <summary>."
- A new sub-project with no tracker -> propose adding a registry row + a tracker home rather
  than dumping it in the default bucket.

### Git safety + close the loop
- Never write or `git add` gitignored PII / build artifacts (claimed-user data, `.deploy/`
  dirs, media binaries, build output). List the exclusions your project cares about in the
  registry's notes.
- **Close the loop** (`shared/doctrine.md` §6): **land each tracker the moment its approved
  edits are applied — same turn, not at session end.** Tracker files are the most-contested
  files in the repo, so the collision window (exactly how long you leave an edit unlanded)
  matters most here. Land exactly the tracker files this ingest wrote through the ship
  gate — never `git add`:
  `python tools/agent-ops-harness/shared/ship.py commit --paths <trackers> -m "..." --dry-run`,
  read the file list, then re-run with `--push`.
- **Check the blast radius first.** This skill routes CODE work, so its commits are the ones
  most likely to deploy: `ship blast --paths <trackers>`. INERT → push straight to trunk.
  DEPLOYS → flag-gate it or take a `ship worktree`, and run `ship verify` afterwards. Pushed,
  built, promoted and live are four different states.
- **Contested-file guard:** tracker files are the most-contested files in the repo (the
  frontmatter block especially). If one mixes another session's uncommitted edits with yours,
  land ONLY your hunks: `ship hunks <file>` then `ship commit --replay <file> --hunks 2,3` —
  unselected regions are taken verbatim from trunk, so the other session's work is neither
  committed nor destroyed. If you cannot tell which hunks are yours, do NOT commit it; flag
  it and leave it for the owning session. See `shared/parallel-git.md`.

---

## Mode: status
Read-only. No writes, no gate.
1. Read the `## Project Registry` from `config.project_registry`.
2. Print the registry table (Project | Tracker home | Owner | Ingest writes? | Status).
3. For each project, optionally read its tracker home and surface the top 2-3 Open/Blocked items.
4. **Registry drift check:** flag any project whose tracker-home path does not resolve.

Answers "what's the platform picture" / "where does X work get logged" without touching anything.

---

## Relationship to the other lanes
- `/ingest` -> the priorities file (non-code ops). The sibling lane, same gate discipline.
- `/kb-sync` -> wider KB knowledge truth via the source-of-truth registry (content deltas,
  not platform code).
- A project marked **Ingest writes? = no** is owned by another skill (named in the registry
  row / `config.routes`); this skill hands off to it, never writes it.

## Self-improvement
If a run reveals a detection miss (work landed in the wrong bucket), a stale dialect, or a
new project needing a registry row, propose the registry fix at the end of the run
(propose-then-apply). Keep `config.project_registry` the single source of routing truth.