---
name: todo
description: Work orchestrator and sole writer of your priorities file. Auto-sweeps the KB (and, if configured, your mail store) for task movement, surfaces stale items for a batch Q&A, proposes edits for approval, then applies and can spawn parallel work with a send-back contract. Reads every project fact from agent-ops-harness.config.json. Invoke with /todo.
modes: ["full", "fire", "capture", "cross-check", "spawn"]
---

# /todo — Work Orchestrator

> Part of the **agent-ops harness**. Reads its project facts (priorities-file path, bucket
> schema, mail hook, git rules) from the runtime config (`agent-ops-harness.config.json`,
> loaded via `shared/config_loader.py`). Obeys `shared/doctrine.md`. Nothing below is
> project-specific — the buckets, paths, and hooks all come from config.

**Source of truth:** `config.paths.priorities_file` (sections = `config.buckets`, plus the
standing `Watching` / `Dormant` / `Completed` sections).
**Sole writer:** this skill. Other skills/agents PROPOSE; `/todo` applies.
**Autonomy posture:** propose-only. Every write needs explicit user approval of the outline.

## Natural-language triggers
"check the todo list", "what's on the list", "what's hot", "what should I work on",
"what fires today", "priorities", "what moved", "anything new", "end of session capture",
"give me the prompts", "spawn the work". If no mode hint, default to `full`.

(Session-close self-apply — "ingest this here", "apply changes from this chat" — and
wider-KB propagation — "sync the KB", "we renamed X fix it everywhere" — are the sibling
skills **`ingest`** and **`kb-sync`**.)

## Modes

| Mode | Default? | Writes? | What it does |
|------|----------|---------|--------------|
| `full` (bare `/todo`) | YES | proposes | KB sweep + mail sweep (if configured) + stale Q&A + proposed edits + approval + apply + Fire summary + spawn offer. |
| `fire` | no | no | Read-only fast hot list (due/escalation within the horizon). Skips the sweep. |
| `capture` | no | proposes | End-of-session: surface commitments made today (git diff + conversation), propose new rows + Watching entries. |
| `cross-check` | no | no | For each Watching row, check the mail store / interaction logs for a missed reply. Read-only. |
| `spawn` | no | no | Emit structured briefs (new-chat / main-session / agent-team) for selected items, each with a send-back contract. Auto-offered at the end of `full`. |

---

## Mode: `full` (default)

### Sequence
1. Auto-sweep the KB.  2. Auto-sweep the mail store (skips if no mail hook).
3. Stale Q&A batch.  4. Emit proposed-edits outline.  5. Apply on approval.
6. Emit Fire summary.  7. Offer spawn.

### Step 1 — Auto-sweep the KB
For each active row (in every `config.buckets` section + Watching):
1. Extract `objective`, `desired_result`, `next_move`; build a keyword set (entity slugs,
   deliverable nouns).
2. Grep those keywords against, under `config.paths.kb_root`:
   - `knowledge/network/{people,organizations,events}/**` for interaction-log entries dated
     after the row's last action,
   - `config.paths.drafts_dir` for new draft files matching keywords,
   - `git log --since="<last_sweep>"` for commits mentioning keywords.
3. Classify each row: **MOVED** (new evidence), **NO_CHANGE**, or **OBSTACLE** (blocker
   keyword: "blocked", "stuck", "rejected", "declined", "stepped back").

### Step 2 — Auto-sweep the mail store (INBOUND-ANCHORED)
**Self-skip if `config.hooks.mail_fetch` is null** (the adopter has no mail integration) —
jump to Step 3.

Otherwise, inbound-driven (a single message can resolve/mention multiple rows):
1. **Fetch.** Run `config.hooks.mail_fetch` with `days = max(7, days_since_last_sweep + 2)`
   (the hook string takes a `{days}` placeholder). Reconcile the whole window
   `[last_sweep, now]` every time — a "+0 new" fetch result is NOT a signal that everything
   is already folded into rows (a fetch may have run earlier today without reconciling).
2. Build a `{keyword -> [row_id,...]}` index from every active row.
3. List every new file in `config.paths.mail_inbox` and `config.paths.mail_sent` with a
   timestamp after `last_sweep`. Sent matters too (outbound from another session may have
   resolved a row).
4. **Read the FULL BODY of each new file.** Do not trust a spam classifier blindly
   (payment/receipt notifications are often mis-flagged yet carry the most important data).
   Record `(file, matched_keyword, row_id, excerpt)` for every hit; a real inbound with
   ZERO matches is **POTENTIALLY_UNTRACKED** (may need a new row).
5. Classify each row MOVED / NO_CHANGE / OBSTACLE from the hits.
6. Cross-reference the reply-owed queue (`config.paths.threads_index`, if set) as a final
   sanity check — flag any row whose thread is reply-owed but got no MOVED classification.

### Step 2.5 — Active-threads / deadline worklist
This catches what the keyword scan misses: brand-new threads, dormant re-emergence, the
"they already replied but the row still says awaiting" drift, and **overdue deliverables /
awaiting-reply silences that no mail scan can see**.

- **If `config.hooks.active_threads` is set**, run it to generate the worklist
  deterministically (it should emit: reply-owed-in-window, aged-reply-owed, drift
  candidates, unmatched reply-owed, Watching cross-check; plus overdue actions, awaiting
  past escalation, due-soon, and stale-hygiene).
- **If not**, derive the same worklist by hand: parse every row's `due`/`escalation`, and
  (if mail is configured) walk the reply-owed queue.

Then **disposition every reply-owed thread** (RESOLVED_CLOSE / DRIFT_UPDATE /
GENUINELY_AWAITING / UNTRACKED_NEW) and **every overdue/awaiting-silent row**
(STILL_OPEN_ON_TRACK / NEEDS_ACTION_NOW / NUDGE / RESOLVED_CLOSE). One line each; this feeds
Step 4.

**Missing-row critic:** scan for any material commitment (a confirmed participant, a venue,
a deliverable, a payment) referenced only inside another row's prose with NO row of its own.
Propose creating one — a commitment with no row cannot fire.

### Step 2.6 — Data-rights request detection (OPTIONAL)
If your project receives data-subject requests (e.g. GDPR), scan the same inbound bodies for
first-person rights signals ("delete my data", "remove me", "opt out", "right to be
forgotten", plus your locale's equivalents). On a hit, PROPOSE (never auto-action) a new row
in your operations bucket with a legal response-window due date. Detection + proposal only;
the actual edit/removal is always manual and supervised. *(Delete this step if not
applicable.)*

### Step 3 — Stale Q&A (one batch)
Collect NO_CHANGE rows past `escalation`. Emit ONE batch ("Stale items past escalation — any
non-mail movement? 1… 2… reply free-form"). Parse the reply; classify each as MOVED or
CONFIRMED_STALE.

### Step 4 — Propose-edits outline
Group by action type: PROMOTE TO FIRE / UPDATE STATUS / ARCHIVE TO COMPLETED / DEMOTE TO
DORMANT / NEW WATCHING / OBSTACLES, plus an **"Active Threads Check"** sub-section (every
reply-owed thread with its disposition) and a **"Fire / escalation check"** sub-section
(every overdue/awaiting row with its disposition). End: "Approve all? Selectively? Walk
through one-by-one?"

**Completeness gate (MANDATORY):** the outline is incomplete if any reply-owed thread or any
overdue/awaiting row lacks a disposition. Do not proceed to Step 5 until each has one (a
one-line "STILL_OPEN_ON_TRACK" / "RESOLVED_CLOSE, nothing owed" is valid).

### Step 5 — Apply on approval
Read the priorities file fresh. Apply each approved edit surgically (never `replace_all` —
`shared/doctrine.md` §2). Update `last_sweep` + `updated` frontmatter. Report applied count.
**Close the loop** (`shared/doctrine.md` §6) — **land the moment the approved edits are
applied, same turn, not at session end** (the collision window is exactly how long you
leave an edit unlanded) — via the ship gate, never `git add`:
```
python tools/agent-ops-harness/shared/ship.py commit --paths <priorities file> -m "todo: ..." --push
```
It commits on a temporary index parented on a fresh trunk, so it never touches the shared
working tree and cannot sweep in a sibling's half-written hunks. If the priorities file
carries another session's edits mixed with yours, land only your hunks
(`ship hunks <file>` → `commit --replay <file> --hunks ...`); if you cannot tell which are
yours, FLAG it and leave it. See `shared/parallel-git.md`.

### Step 6 — Fire summary
Render the hot list (rows with `due <= today+2` or `escalation <= today`), grouped by
bucket, sorted by due. Stay under ~20 lines.

### Step 7 — Offer structured briefs
Every workload item the user picks gets the SAME structured brief regardless of channel
(comms tasks are not more deserving of structure than internal ones). If a task is too broad
for one brief, that is a signal to **decompose**, not to give less structure. If mail is
configured, re-fetch a 1-day window first (inbounds may have landed during a long sweep).
Then: "Emit structured briefs for any of these? Reply with IDs." If yes -> `spawn`.

### Rules
- NEVER write without explicit approval of the Step 4 outline.
- Legacy prose row with no `objective`/`desired_result`/`next_move`: flag it, offer to
  propose structured fields; do not auto-sweep it.
- **NEVER ask the user whether a message was sent or a reply landed.** Verify at the source
  (run `config.hooks.mail_fetch`, check `mail_sent`/`mail_inbox`). Only after that may you
  ask about non-mail resolution paths (in-person / call / chat).
- **NEVER ask the user to confirm today's date** — check via `date` / recent timestamps / git log.

---

## Mode: `fire` (read-only hot list)
1. If `config.hooks.active_threads` is set, run it in fire-only mode; else parse rows'
   `due`/`escalation` by hand.  2. Surface overdue + awaiting-past-escalation + due-soon,
   closest first; note the stale count.  3. Up to 3 decision points. 4. Stop — no writes, no
   sweep. If `last_sweep` > 24h old, say so and suggest bare `/todo`.

## Mode: `capture` (end of session)
1. `git diff` since session start over `config.paths.kb_root`. 2. Scan the conversation for
   commitment phrases ("I'll send", "follow up by", outbound sends, confirmations). 3. For
   each, propose a row (bucket, objective, desired_result, next_move, due, status, channel) +
   a Watching row with escalation if it's an outbound. 4. Apply on approval.

## Mode: `cross-check` (read-only audit)
1. Refresh the mail store (if configured). 2. For each Watching row, check the linked
   thread's latest message date + direction **at the source, not from row prose**; flag if an
   inbound exists after our last outbound but the row still says "awaiting". If a row claims a
   send with no matching sent file, flag it as unverifiable (ask about non-mail paths — never
   "did you send it?"). 3. Emit the hit list. No writes.

## Mode: `spawn` (structured brief emission)
**Parity of preparation:** every item gets the same brief format regardless of channel.
**Decomposition rule (before drafting):** can one brief carry it end-to-end in <=2h? If not,
decompose into 2-5 sub-tasks, each with a timeline anchor; surface obstacles ("depends on Y's
reply", "needs decision Z") as their own sub-tasks, not footnotes.

**Route each brief** to NEW CHAT (outbound comms, multi-turn drafting, tool access beyond a
subagent, long fresh-context work), MAIN SESSION (user does it with cross-domain context
loaded, a single decision block), or AGENT TEAM (bounded read/research, single deliverable,
no mid-task input). The format is identical; only the destination header changes.

### Universal brief template
```
# [<id>: <title>] — Structured brief

## For you (pre-flight — read before approving)
- What the receiver will do autonomously: <2-4 plain bullets>
- What to verify before approving: <2-4 bullets on baked-in assumptions to redirect>
- Approval checkpoints during execution: <pause points the receiver will hit>
- Execution channel: <NEW CHAT / MAIN SESSION / AGENT TEAM>
- Time estimate: <n ± range>   Reversibility: <HIGH / MEDIUM / LOW>

## Context / Objective / Desired result
<why it matters now; verbatim objective + desired_result from the row>

## Decomposed sub-tasks
<sub-tasks with timeline anchor + obstacle path, or "Atomic, no decomposition">

## Next move (first action after approval)
## Resources
- Row: <bucket / id in the priorities file>
- Profiles / threads / draft folder / related KB nodes

## Tools the chat may need
## Constraints (apply to all output + actions)
- No outbound without explicit per-message clearance
- No assumed completions (mark DONE only on explicit confirmation)
- <your house style + card-protection scopes + task-specific limits>

## Completion contract
1. Update the relevant rows (statuses + timestamps + Watching entries)
2. Update interaction logs / profiles / event files / drafts touched
3. Write a handoff report summarising decisions + files changed
4. PREFERRED: invoke /ingest at session close to apply the row updates directly (still
   behind its mandatory diff-outline gate — invocation does not bypass approval)
5. LEGACY (read-only agents): end with a fenced SEND-BACK PROMPT the user can paste into
   the main /todo chat (which id, what was done, what KB files changed, what to update)
```

**Agent-team variant:** wrap the same template (including the pre-flight section) in an
`Agent({description, subagent_type, prompt})` call; the report returns as the agent result.

**Send-back ingestion (legacy):** when a user pastes a SEND-BACK PROMPT, parse it, confirm
light-touch, apply the row edits, move to Completed if applicable.

---

## Schema: the priorities file
See `templates/priorities.template.md` for the starting scaffold. Frontmatter carries
`updated`, `last_sweep`, `schema_version`. Sections are the `config.buckets` labels, then
`## Watching` (sent, awaiting replies), `## Dormant` (paused, door open), `## Completed —
last 30 days`, `## Archive`. Row columns:

`id | item | objective | desired_result | next_move | due | escalation | status | channel | thread`

- `status`: DRAFT / SENT / WAITING / OBSTACLE / DONE / DEFERRED
- `channel`: email / chat / call / internal / multi
- `thread`: path to the thread file or interaction log, or `--`

## State file (`config.paths.state_file`)
Records: last sweep date + outcome counts; recent spawn history; recent send-back
ingestions; `## kb-sync runs` and `## kb-sync deferred deltas` notes (written by `kb-sync`);
`## active-threads runs` (worklist outcome per sweep). Create-if-missing on first write.

## Integration
Other skills that touch the priorities file (a budget/funding/programming review, etc.)
should end their report with a "Proposed priorities changes" section; the user runs `/todo`
to ingest. `/todo` is the ONLY skill that writes the priorities file directly.
