# Project Registry (example — edit for your project)

> The routing table `/platform-ingest` reads (`config.project_registry`). It maps each
> code/platform sub-project to how work items reach the right tracker. `/platform-ingest`
> reads the `## Project Registry` section below as prose; it is not parsed by code, so a
> plain markdown table is exactly right.
>
> This ships as a worked example over a fictional project ("Acme"). **Replace the rows with
> your own sub-projects.** Keep the `(default)` row and the columns.

## Project Registry

| Project | Detection globs | Tracker home | Dialect | Owner | Ingest writes? | Status |
|---|---|---|---|---|---|---|
| web-app | `apps/web/**`, `packages/ui/**` | `apps/web/ROADMAP.md` | axis/roadmap items under `## Now / Next / Later`; shipped -> global Shipped Log | you | yes | (fill in) |
| api | `services/api/**`, `db/migrations/**` | `services/api/WORKING-DOC.md` | §0 task ledger: `- [x]` Done / `- [ ]` Open / `- [ ]` Blocked | you | yes | (fill in) |
| data-layer | `packages/graph/**` | `packages/graph/PROJECT-TRACKER.md` | (curation lane) | your graph/curation skill | **no** (hand off) | (fill in) |
| (default) | anything unmatched | `knowledge/operations/platform-dev.md` | flat rows: `Pending Verification` / `Active / In Progress` / `Deferred / Backlog` + global Shipped Log | you | yes | — |

### Columns
- **Detection globs** — the touched-path signal `/platform-ingest` matches session file
  changes against (primary classification input).
- **Tracker home** — where this project's backlog lives.
- **Dialect** — how to add an item to THAT tracker (each project keeps its own convention;
  the skill follows whatever the row says).
- **Owner** — who owns that tracker.
- **Ingest writes?** — `yes` = `/platform-ingest` may write it directly; **`no`** = it is
  owned by another skill (a data/curation lane); the skill emits a hand-off note instead of
  writing. Wire the hand-off target through `config.routes` where applicable.
- **Status** — a one-line current-state cell the skill updates each ingest.

## The global Shipped Log
Keep ONE cross-project audit trail in the `(default)` tracker (your flat backlog): a terse
`Date | Item | Commit | Notes` row for anything shipped-and-verified, tagged with the project.
Heavy projects also keep their own detailed "Done" entry; the global log gets the pointer row.

## Gitignored artifacts (never write or `git add`)
List the PII / build outputs this project must never commit, e.g. claimed-user data files,
`.deploy/` directories, media binaries, build output. `/platform-ingest` excludes these from
its scoped commit.