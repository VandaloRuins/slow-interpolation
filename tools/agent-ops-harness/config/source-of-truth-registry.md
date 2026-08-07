# Source-of-Truth Registry (example — edit for your project)

> The canonical authority map for your knowledge base. For every **fact-domain**, this
> registry names the ONE doc-type that wins when two documents disagree. `kb-sync` (and any
> other reconciliation routine) MUST consult this registry before proposing a write, so
> automation never overwrites good data with stale data.
>
> This file ships as a worked example over a fictional project ("Acme"). **Replace the
> paths and fact-domains with your own.** Keep the tier structure and the guard-tier
> mechanism — those are what make reconciliation safe. `kb-sync` reads this file as prose;
> it is not parsed by code, so plain markdown tables are exactly right.

---

## How to read this registry

- **Fact-domain** — a coherent category of truth (a person's email, an event's date, a
  task's status).
- **Canonical doc-type** — the single authoritative doc-type for that domain. When two docs
  disagree, the canonical one wins; the other is a reconciliation target.
- **Authority rule** — precisely who wins, and under what condition.
- **Guard tier** — some domains are marked `GUARD (route: <name>)`. `kb-sync` must NOT
  write these; it routes them to the skill named in `config.routes.<name>`, or FLAGs them
  to the user if that route is `null`. Guard tiers are how you stop one skill from
  overreaching into another owner's data.

The arrow of correction always points away from canon: a reconciliation routine NEVER edits
the canonical doc to match a non-canonical one.

---

## Tier 0 — the universal rule (overrides everything below)

**DERIVED snapshots are NEVER authoritative.** They record what was true when written —
point-in-time reflections, not living truth. They are always reconciliation TARGETS, never
sources. A contradiction between a snapshot and any canonical doc resolves in favour of
canon, every time. (These globs are `config.scan_roots.snapshots`.)

| Derived snapshot doc-type | Path glob (example) |
|---|---|
| Handoffs / spawn prompts | `knowledge/operations/handoffs/**` |
| Brainstorming | `knowledge/operations/brainstorming/**` |
| Drafts (operational + outbound) | `knowledge/operations/drafts/**` |
| Dated audit / review snapshots | `knowledge/operations/*-audit-*.md` |

A snapshot that contradicts canon is a signal that canon may have moved on since it was
written. `kb-sync` does NOT "fix" a stale snapshot by rewriting its body (it is a historical
record). It either leaves it untouched (correctly-dated history) or, if it is fully
superseded and actively misleading, PRUNES it to the archive with a forwarding pointer.

---

## Tier 1 — operations truth

| Fact-domain | Canonical doc-type | Authority rule |
|---|---|---|
| Task / priority status, next-move, due, escalation, Watching, Completed | `config.paths.priorities_file` | The priorities file wins for all operational task state. Single-writer (`todo`); other skills propose. |
| Message / thread state (who owes a reply, send verification) | your mail store (via `config.hooks.mail_fetch`) | The mail source is authoritative for send/reply state. A priorities row is NOT authoritative for whether a message was sent — verify at the source. Read-only for skills. |
| Skill last-run / cadence state | `config.paths.state_file` | Each skill's own state note is authoritative for its last run. |

---

## Tier 2 — network knowledge truth (the wider KB this registry mainly governs)

| Fact-domain | Canonical doc-type | Authority rule |
|---|---|---|
| Person facts (name, contacts, roles, status, relationship, notes) | `knowledge/network/people/{slug}/{slug}.md` | The person's own profile is canonical for everything about that person. Any other doc referencing them is secondary. Interaction history is APPEND-ONLY. |
| Organization facts (category, status, relationship, key people, contacts) | `knowledge/network/organizations/{slug}/{slug}.md` | The org's own profile is canonical. Same append-only rule. |
| Event facts (date, time, venue, owner-of-record, participants, partners, status) | `knowledge/network/events/{slug}/{slug}.md` | The event profile is canonical. Programme/portfolio docs (Tier 3) are DERIVED VIEWS and lose any disagreement to the event profile, except where the conflict is itself the find (then FLAG). |
| Cross-reference integrity (slug links) | the referenced canonical profile/event file | A slug reference is valid only if the target file exists. Broken references are FLAG hits. |
| Master entity index | `knowledge/network/_index.md` | A DERIVED INDEX of the profile files. If it disagrees with a profile, the profile wins and the index is regenerated. |
| Connection / cluster prose | `knowledge/network/_connection-map.md` | Canonical for authored network-intelligence prose. Underlying relationship facts defer to the two profiles. |

---

## Tier 3 — programme / portfolio truth (adapt or delete)

| Fact-domain | Canonical doc-type | Authority rule |
|---|---|---|
| Programme day-grid + lineup narrative | `knowledge/programme/programme.md` | Canonical for the SHAPE of the programme (what is on when, the arc). Per-event hard facts defer to the event profile; a hard-fact conflict = FLAG toward the event profile. |
| Portfolio status roll-up | `knowledge/programme/portfolio-overview.md` | Canonical for the portfolio-level framing (status column, which events exist). Per-event detail defers to event profiles. |

---

## Tier 4 — finance truth — **GUARD (route: `budget`)**

`kb-sync` NEVER writes financial docs. A delta whose fact-domain is financial is marked
`ROUTE_TO_budget` and handed to `config.routes.budget` (or FLAGged if that route is `null`).

| Fact-domain | Canonical doc-type | Authority rule |
|---|---|---|
| Budget plan (forecast lines, pipeline income) | `knowledge/business/budget.md` | Canonical for what was INTENDED. A profile may NOTE a cost line but the planned figure of record lives here. Route conflicts to `budget`. |
| Actuals (money that moved, variance) | `knowledge/business/actuals.md` | Canonical for what HAPPENED. Plan vs actuals is NOT a conflict — the gap is the variance, a finding to record, not flatten. |

---

## Tier 6 — graph / visualisation data-layer — **GUARD (route: `graph`)**

If your project drives a network graph or visualisation from a curated data layer, its
controlled vocabulary and per-entity overrides are a guard tier. `kb-sync` NEVER writes
them; it routes to `config.routes.graph` (or FLAGs if `null`).

| Fact-domain | Canonical doc-type | Authority rule |
|---|---|---|
| Relation-type / role-class enums | `knowledge/graph/relation-taxonomy.md` | Controlled vocabulary; profiles must conform. |
| Per-entity graph overrides | `knowledge/graph/overrides/{slug}.yml` | SPECIAL: at render time the override wins for the graph, but the profile still wins for all non-graph purposes. Never "fix" a profile to match an override, or vice versa — do not collapse this distinction. |

*(Delete this whole tier if your project has no such graph layer, and set
`config.routes.graph: null`.)*

---

## Tier 8 — system / structure truth — **dedupe is GUARD (route: `dedupe`)**

| Fact-domain | Canonical doc-type | Authority rule |
|---|---|---|
| Duplicate-entity merges | (structural op) | **GUARD (route: `dedupe`).** Merging two live profiles is structural (choose the surviving slug, rewrite refs, fold histories). `kb-sync` FLAGs it to `config.routes.dedupe`; it never merges profiles itself. |
| Directory structure / schema spec | `knowledge/reference/kb-architecture.md` | Canonical for the intended tree. Disk disagreement is a structure finding. |
| Project work routing (which tracker owns which backlog) | `config.project_registry` → its `## Project Registry` section | Canonical for WHERE platform/code work is logged. Used by `platform-ingest`. Routes work items, not data authority. |

---

## Conflict-resolution decision procedure (for any reconciliation routine)

Given two docs A and B stating different things about fact F:

1. If either is a Tier 0 snapshot, the non-snapshot wins. If both are snapshots, neither is
   authoritative — FLAG.
2. Else look up F's fact-domain here. The canonical doc-type wins. If it is a **guard tier**,
   do not write — route via `config.routes` (or FLAG if the route is `null`).
3. The losing doc becomes a hit, classified **ALIGN / MERGE / PRUNE / FLAG** (see
   `kb-sync/SKILL.md` Step 5).
4. NEVER edit canon to match a non-canonical doc. If evidence suggests canon is wrong, that
   is a FLAG, not an auto-write.

### The "canon might be the stale one" caveat

A registry tells you which doc-type wins a tie, not which doc holds the freshest fact. When a
SESSION establishes new truth (a mid-conversation rename), the session's emergent truth is
what propagates INTO canon first, then outward. This is why `kb-sync` is delta-driven from
session truths, not a blind canon-vs-noncanon diff.

---

## Deletion rule (hard constraint)

PRUNE means **move to `config.paths.archive_dir`**, preserving the file, and leave a
one-line forwarding pointer at the old location:
`RETIRED <date>, superseded by <canonical path>, archived to <archive path>`.

NEVER hard-delete KB content. NEVER `replace_all` on a canonical multi-entity file during
reconciliation — surgical row-level edits only. Every PRUNE is reversible by moving the file
back; hard-delete is not. Default to reversible.