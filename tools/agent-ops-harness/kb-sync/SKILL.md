---
name: kb-sync
description: Propagate a session's established truths into the wider knowledge base. Delta-driven, registry-resolved, canon-first. Reconciles derived views/indices/profiles when a canonical fact changes (a rename, a role change, a venue move, a retirement), behind a mandatory diff-outline approval gate. Phase 2 of the two-phase session close (Phase 1 = ingest). Invoke with /kb-sync.
---

# kb-sync — wider-KB reconciliation against session-emergent truth

> Part of the **agent-ops harness**. Reads its project facts from the config
> (`tools/agent-ops-harness.config.json`, loaded via `shared/config_loader.py`) and its
> canonical-doc map from the **source-of-truth registry** at `config.registry.source_of_truth`.
> Obeys `shared/doctrine.md`. Consumes the delta block defined in `shared/delta-contract.md`.
> Nothing below is project-specific; every path, route, and scan root comes from config.

## What it is for

`ingest` reconciles the **operations** layer (task rows in the priorities file) against
what a session established as true. `kb-sync` does the same job for the **wider knowledge**
layer: when a session establishes a new canonical truth (an event was renamed, a person
changed roles, a venue moved, a partner stepped back), the wider KB still carries the OLD
value in event files, programme/portfolio docs, profiles, indices, and stale snapshots.

`kb-sync` takes the structured set of truths that emerged this session, resolves each to
its canonical doc via the registry, writes canon first, then bounded-greps for every
downstream doc that still carries the old value and **aligns / merges / prunes / flags**
each hit — all behind a single MANDATORY diff-outline approval gate that is SEPARATE from
the ops-row approval.

It is **DELTA-DRIVEN, never a full KB scan.** The session tells it what changed; it only
touches docs that reference the old/stale value or the touched slugs.

## Trigger and invocation

`kb-sync` is invoked, never auto-fired on a cadence (it has none; it is delta-driven).

- `/kb-sync` — consume the delta block emitted by a prior `ingest` run in the same chat.
- `/kb-sync --from-session` — re-derive the delta set from the conversation itself
  (fallback, lower-trust; see `shared/delta-contract.md`).
- Natural language: "sync the KB", "propagate this to the KB", "we renamed X, fix it
  everywhere", "the rest of the KB still says the old name".
- If invoked with no delta block in scope AND no `--from-session`, ASK the user which
  truths to propagate rather than guessing.

## The two-phase session close

```
PHASE 1: ingest
  - reconciles the priorities file (OPS truth), own approval gate  -> batch #1
  - emits a machine-readable kb-sync-delta block (shared/delta-contract.md)
  - offers Phase 2 ("N knowledge-truth deltas detected, run /kb-sync?")

PHASE 2: kb-sync   (separate invocation, separate approval)
  - intakes the delta block (or re-derives via --from-session)
  - registry resolution -> bounded grep -> classify -> diff outline
  - MANDATORY GATE: explicit user approval                          -> batch #2
  - writes canon first, then aligns / prunes / flags downstream
```

**The two approvals are NEVER bundled into one yes.** The user can approve the ops-row
flips (Phase 1) and decline or defer the KB cascade (Phase 2), or vice versa. Non-negotiable.

---

## The full sequence

### Step 1 — Delta intake
- Read the `kb-sync-delta` block from the current chat (emitted by Phase 1), OR
- `--from-session`: re-derive deltas and confirm EACH with the user before proceeding, OR
- If a logged-but-deferred block exists in the state file (`config.paths.state_file`):
  re-read it and confirm it is still the intent.
- Result: a list of deltas + a `touched_slugs` set. If empty, STOP ("no knowledge-truth
  deltas to propagate").

### Step 2 — Registry resolution (re-resolve; do not trust the upstream guess)
Load the registry at `config.registry.source_of_truth`. For each delta:
1. Look up `fact_domain` in the registry.
2. Resolve the canonical doc-type and the concrete canonical path for `entity`.
3. **Guard-tier check.** If the registry marks this `fact_domain` as a guard tier, do NOT
   proceed to write it. Look up the matching `config.routes` entry:
   - route configured -> mark the delta `ROUTE_TO_<target>`, remove from the write plan.
   - route is `null` -> mark `FLAG` (surface to the user; never write it silently).
   (See `shared/doctrine.md` §5. Typical guard tiers: graph data-layer fields,
   financial docs, duplicate-entity merges.)
4. **Canon-might-be-stale check.** Confirm `new_value` is the SESSION's emergent truth
   (the value that should become canonical) and `old_value` is what canon/downstream
   currently carry. The session decides the new canonical value; `kb-sync` writes it INTO
   canon first. If it is genuinely ambiguous which is correct, FLAG rather than guess.

### Step 3 — Write canon first
For each delta that survived Step 2 guards:
1. Re-read the canonical doc fresh (concurrency rule).
2. If canon already carries `new_value`: mark `ALREADY_CURRENT`, no canon write, proceed
   downstream (Phase 1 may have updated it, or the change happened in canon directly).
3. Else: surgical edit of canon's frontmatter/body to `new_value`. Append (never
   overwrite) a change-note / interaction-log line where the doc-type has one. This canon
   write is the FIRST item in the apply batch (Step 6), in dependency order.

**The arrow of correction always points away from canon.** `kb-sync` NEVER edits canon to
match a downstream hit.

### Step 4 — Bounded grep (delta-driven, never full-scan)
For each delta, build the search scope from TWO sources only:
1. The `old_value` string (and obvious variants: the retired name, old role title, old
   venue name).
2. The `touched_slugs` set (cross-reference fields pointing at the touched entities).

Run bounded greps (NOT a KB-wide sweep) against the globs in `config.scan_roots`:
- `scan_roots.living` — event files, profiles, programme/portfolio docs (living docs that
  may be ALIGNED).
- `scan_roots.derived_indices` — indices/connection maps (surgical row edits only).
- `scan_roots.snapshots` — timestamped snapshots (handoffs, drafts, brainstorming).
  Scanned ONLY to classify as PRUNE-or-leave, NEVER to ALIGN. You never rewrite a
  snapshot body to make it current.

Each hit = `(file_path, matched_string, one-line excerpt, tier-from-registry)`.

### Step 5 — Classify each hit (ALIGN / MERGE / PRUNE / FLAG)
Apply the registry's conflict-resolution procedure to every hit:

- **ALIGN** — a non-canonical LIVING doc (event file, programme/portfolio doc, profile,
  index) carrying `old_value`. Propose a surgical edit to `new_value`.
- **MERGE** — the hit holds UNIQUE good info absent from canon (a legacy/duplicate entry
  with a fact canon lacks). Propose folding the unique info INTO canon (append-only), then
  align the rest. **Live duplicate PROFILES are NOT merged here — they FLAG to the dedupe
  route** (`config.routes.dedupe`, or the user if null). MERGE is only for non-profile
  unique-info folds.
- **PRUNE** — a snapshot (or fully-superseded living doc) that is now ACTIVELY MISLEADING
  because it carries `old_value` as if current. Propose moving to `config.paths.archive_dir`
  with a forwarding pointer. NEVER hard-delete. NEVER rewrite a snapshot body. A snapshot
  that merely RECORDS the old value as correctly-dated history is LEFT UNTOUCHED.
- **FLAG** — ambiguous; or the conflict itself is the finding (canon may be the stale one);
  or resolution needs a user-only decision; or the hit is a guard-tier doc `kb-sync` must
  not write; or a broken cross-reference (target canonical file does not exist). Surface as
  a question; propose nothing silently.

### Step 6 — Diff outline (MANDATORY GATE)
Emit the outline (format below), STOP, wait for explicit approval that names the diff.

### Step 7 — Gated apply (dependency order, concurrency-safe)
Only after explicit approval, apply in this order:
1. **Canon writes first** — frontmatter + body + append-only change note.
2. **ALIGN downstream living docs** — cross-links, profiles, programme/portfolio docs.
3. **Indices** — surgical row edits, NEVER `replace_all`.
4. **MERGE folds** — non-profile unique-info into canon, append-only.
5. **PRUNE** — move-to-archive + forwarding pointer.
6. **FLAG items are NOT applied** — surfaced for the user / routed elsewhere.

Concurrency: re-read each file immediately before its Edit; if it changed since the Step 4
scan, rebuild that hit's diff and re-prompt. Never `replace_all` on a multi-entity file.

### Step 8 — Close-out + state note
- Emit a "KB-sync Complete" summary (files changed, pruned-with-pointer, flagged,
  routed-out).
- Append a one-line note to `config.paths.state_file`:
  `kb-sync run <ISO-timestamp> — N deltas, M aligned, P pruned, F flagged, R routed`.
- Surface any route/FLAG hand-offs explicitly so they are not lost.
- **Close the loop** (`shared/doctrine.md` §6): **land the moment the approved edits are
  applied — same turn, not at session end** (the collision window is exactly how long you
  leave an edit unlanded; a kb-sync pass touching many files is the most exposed of all).
  Land the files this pass wrote through the ship gate, never `git add` —
  `python tools/agent-ops-harness/shared/ship.py commit --paths <files> -m "kb-sync: ..." --push`.
  A kb-sync pass often writes many files across the KB, so run `--dry-run` first and read
  the list. Any file carrying another session's hunks: land only yours via
  `ship hunks` / `commit --replay`, or leave it and FLAG it (`shared/parallel-git.md`).

---

## Diff-outline format

```
Proposed KB-sync cascade (from this session's emergent truths):

CANON WRITES (N) — written FIRST:
  - <canonical file> — <fact_domain> "<old>" -> "<new>" (frontmatter + heading + change note)

ALIGN — downstream living docs (M):
  - <programme/portfolio doc> — <row> "<old>" -> "<new>"
  - <index> — entity title align
  - <profile> — relationship prose align

MERGE — unique-info folds into canon (K):
  - (none) | OR: <legacy doc> holds <detail canon lost> -> fold into canon body

PRUNE — move to archive/ with forwarding pointer (P):
  - <superseded snapshot still naming the old value as current> -> archive + pointer

FLAG — needs your call / routed elsewhere (F):
  - DUPLICATE PROFILE: <slug-a> vs <slug-b> -> route to dedupe (kb-sync does not merge live profiles)
  - GUARD TIER: <entity>.<field> -> route to <config.routes.*> (or, if null: your call)
  - BROKEN REF: <doc> links [[<slug>]] but no such canonical file -> confirm target

LEFT UNTOUCHED (history, correctly recorded):
  - <snapshot recording the old value as dated history, not as current> -> leave

Approve all? Approve selectively? Walk through one-by-one?
```

### MANDATORY GATE language (non-negotiable)

> Before calling ANY Edit / move operation for the KB-sync cascade, emit the full diff
> outline and receive explicit user approval IN THIS TURN that names the diff or its
> components. If you are about to call Edit and cannot point to a specific approval message
> in this conversation authorising that exact diff, STOP and re-present the outline. The
> Phase 1 `ingest` approval does NOT carry forward to Phase 2 — this is a SEPARATE approval
> batch. Soft signals ("go ahead", "looks good") mid-discussion do NOT count unless they
> explicitly reference this diff outline. No exceptions, no "obvious" cases.

---

## MERGE adjudication for live duplicate profiles

`kb-sync` NEVER merges live duplicate profiles. Merging two profiles is a **structural**
operation (choose which slug survives, rewrite every cross-reference, fold histories
append-only, update indices, choose a canonical name). That belongs to the dedupe owner
(`config.routes.dedupe`), or, if the adopter has no such skill, to the user.

When Step 5 detects two live canonical profiles for one entity, `kb-sync`:
1. Classifies BOTH as one `FLAG: DUPLICATE PROFILE` (picks no winner, writes neither).
2. Lists in the outline: `FLAG -> dedupe: <slug-a> vs <slug-b>, fields in conflict: <list>,
   suspected canonical: <hint only>`.
3. Surfaces an explicit follow-up in Step 8.
4. Does NOT propagate the delta into the duplicate pair until dedupe is resolved (that
   would entrench the duplication). The delta is re-logged in the state file for re-run.

MERGE is therefore reserved for NON-profile unique-info folds (a legacy programme note, a
derived doc holding a fact canon lost) — a safe append into a single canonical doc.

---

## What kb-sync does NOT do

- No KB cadence sweep (delta-driven only).
- No priorities-file row edits (that is `ingest`'s job, Phase 1; separate approval batch).
- No writes to guard-tier docs (registry guard tiers -> route via `config.routes` or FLAG).
- No live duplicate-profile merges (-> dedupe route / FLAG).
- No editing of canon to match a downstream hit.
- No hard-delete, ever.

---

## Worked example (event-rename cascade)

Mid-session the user renames an event from **"Spring Mixer"** to **"Spring Showcase"** and
confirms it moved venue from "The Annex" to "Warehouse 4". `ingest` ran first, flipped the
relevant priorities rows, and emitted:

````
```kb-sync-delta
session: 2026-01-15
touched_slugs: [acme-spring-showcase, acme-warehouse-venue]
deltas:
  - fact_domain: event-title
    entity: acme-spring-showcase
    old_value: "Spring Mixer"
    new_value: "Spring Showcase"
    canonical_doc: knowledge/network/events/acme-spring-showcase/acme-spring-showcase.md
    evidence: "user rename mid-session 2026-01-15"
```
````

- **Step 2 (registry):** `event-title` -> event tier, canonical = the event profile. No
  guard tier trips.
- **Step 3 (canon first):** re-read the event profile. Frontmatter `title` already =
  "Spring Showcase" -> `ALREADY_CURRENT`, proceed downstream. (If it still said "Spring
  Mixer", canon would be the first write.)
- **Step 4 (bounded grep):** scope = "Spring Mixer" + touched slugs. Hits:
  1. `programme.md` — a row reads "Spring Mixer" (living derived view).
  2. `_index.md` — entity title "Spring Mixer".
  3. `warehouse-venue` org profile — `associated_events` prose "Spring Mixer".
  4. event profile body — a `## History` line "formerly Spring Mixer" (correctly historical).
  5. `handoffs/2026-01-02-spring-mixer-brief.md` — a superseded brief titled/bodied as the
     current event.
  6. `brainstorming/2026-01-01-naming.md` — lists "Spring Mixer" as a discarded candidate,
     timestamped.
- **Step 5 (classify):** 1,2,3 -> ALIGN. 4 -> LEFT UNTOUCHED (canon's own dated note).
  5 -> PRUNE (superseded snapshot naming the old value as current). 6 -> LEFT UNTOUCHED
  (correctly-dated history). Plus a synthesized FLAG if `_index.md` also holds a stale
  "spring-mixer" row pointing at a missing file (orphan / broken ref).
- **Step 6:** emit the outline, STOP for approval (separate from Phase 1).
- **Step 7 (on approval):** canon (none) -> ALIGN 3 docs (re-read, surgical) -> indices ->
  PRUNE hit 5 (move + pointer). FLAG handled per the user's answer.
- **Step 8:** "KB-sync Complete" summary + state note + `ship commit --paths ... --push`.

This shows canon-first (or ALREADY_CURRENT), one PRUNE of a stale brief (archive + pointer,
body untouched), one FLAG (orphan index row, user decision), and two LEFT-UNTOUCHED history
docs that a naive "fix every mention" routine would have wrongly rewritten.