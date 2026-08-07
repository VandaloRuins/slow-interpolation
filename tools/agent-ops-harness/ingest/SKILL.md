---
name: ingest
description: Session-close Phase 1. From inside a working chat, reconcile the priorities file against what this session established (self-apply, no paste-back), then emit a machine-readable delta block that kb-sync (Phase 2) consumes. Reads project facts from agent-ops-harness.config.json. Invoke with /ingest.
---

# /ingest — session-close self-apply (Phase 1)

> Part of the **agent-ops harness**. The sibling of `/todo`: where `/todo full` sweeps the KB
> and mail store, `/ingest` reconciles the priorities file from THIS chat's own conversation
> context (no re-scan, no paste-back to a main chat). Reads its facts from
> `agent-ops-harness.config.json`; obeys `shared/doctrine.md`; emits the delta block defined
> in `shared/delta-contract.md`.

**Purpose:** a working chat applies its own row updates to `config.paths.priorities_file`
directly, under the same propose-and-wait discipline as `/todo` — only the chat surface
differs. Then it hands the knowledge-layer truths to Phase 2 (`/kb-sync`) via a delta block.

## Triggers
`/ingest`, or "ingest this here", "wrap up and apply", "apply the changes from this chat",
"no need to send back, do it here".

## MANDATORY GATE — read first
Before calling ANY Edit on the priorities file, emit the full structured diff outline
(STATUS FLIPS / UPDATE STATUS / NEW WATCHING / NEW TODO / RETIRE) and receive explicit user
approval **in this turn**. If you are about to Edit and cannot point to an approval message
authorising that exact diff, STOP and re-present the outline. A spawn brief's
"self-apply authorization" authorises the INVOCATION of `/ingest`, never unilateral writes.
Soft signals ("go ahead", "looks good") do not count unless they name the diff. No exceptions.

## Sequence
1. **Self-context scan** — read this chat end-to-end. Identify: what was produced, what was
   sent (outbound), what was decided (status changes), what is owed downstream.
2. **Verify send claims at the source.** For any outbound claim, verify via
   `config.hooks.mail_fetch` + the sent store (`config.paths.mail_sent`) BEFORE encoding a
   SENT flip — never ask "did you send this?". For non-mail channels, do not encode SENT
   without an explicit verbal confirmation in the conversation.
3. **Read the priorities file fresh** — locate rows intersecting this work (by id, slug,
   topic). Build the intersection scope.
4. **Build the diff outline** in `/todo`'s structured shape:
   ```
   Proposed edits to the priorities file (from this chat's work):
   STATUS FLIPS (N):   - #X — STATUS_A -> STATUS_B because <reason>
   UPDATE STATUS (N):  - #Y — context appended with <what was learned/produced>
   NEW WATCHING (N):   - <slug> — <scope>, esc YYYY-MM-DD
   NEW TODO (N):       - <slug> — <scope>, due YYYY-MM-DD
   ARCHIVE / RETIRE / DORMANT (N): - #Z — <reason>
   Approve all? Selectively? Walk through one-by-one?
   ```
5. **Present the outline. STOP. Wait for explicit approval** (see the gate). A question or
   partial signal means NOT YET APPROVED — address it, re-present.
6. **Apply approved edits one at a time.** Re-read the priorities file immediately before
   each Edit (concurrency safety — other chats may be writing it); if a row changed since the
   scan, rebuild that row's diff and re-prompt. Never `replace_all`.
7. **Stamp a `last_direct_edit` note** in the frontmatter (timestamp + what this pass applied).
8. **Optional courtesy summary** — a 2-4 sentence paragraph the user can share in the main
   chat for awareness only (NOT for re-ingestion, which would double-write).
9. **Emit the delta block + offer Phase 2.** Scan the same conversation for KNOWLEDGE-layer
   truths that did NOT map to a priorities row (entity renames, role/venue changes, owner-of-
   record changes, retirements, status changes). Emit a fenced `kb-sync-delta` block
   (`shared/delta-contract.md`) — each `{fact_domain, entity, old_value, new_value,
   canonical_doc, evidence}` + a `touched_slugs` set. Then offer: "N knowledge-truth deltas
   detected. Run /kb-sync to propagate to the wider KB? (separate approval.)" If none, skip
   silently. If the user declines, log the block to the state file's `## kb-sync deferred
   deltas` section so it is not lost.

## Close the loop (after apply)
**Land the moment the approved edits are applied — same turn, not at session end**
(`shared/doctrine.md` §6: the window in which a sibling can collide with you is exactly
how long you leave an edit unlanded). Land exactly the files this ingest wrote, through
the ship gate — **never** `git add`:
```
python tools/agent-ops-harness/shared/ship.py commit --paths <priorities file> -m "ingest: ..." --dry-run
python tools/agent-ops-harness/shared/ship.py commit --paths <priorities file> -m "ingest: ..." --push
```
Read the `--dry-run` file list before pushing. Name files, never directories (a directory
silently includes everything beneath it). The gate never touches the shared working tree, so
it cannot disrupt a sibling; it re-parents and retries if trunk moves, and asserts against
the REMOTE before reporting success.
**Contested-file guard:** if the priorities file's working-tree diff mixes another session's
uncommitted edits with yours, land ONLY your hunks (`ship hunks <file>` then
`ship commit --replay <file> --hunks 2,3`). If you cannot tell which are yours, do NOT
commit — flag it and leave it for the owning session (`shared/doctrine.md` §6,
`shared/parallel-git.md`).

## What /ingest does NOT do
- No KB sweep and no mail fetch beyond send-claim verification (this chat already lived the
  work; context comes from the conversation, not a re-scan).
- No stale Q&A batch and no Fire summary (those are `/todo` main-session views).
- No spawn offer (working chats don't spawn more chats).
- **No wider-KB writes.** `/ingest` only EMITS the delta block (Step 9); it never writes event
  files, profiles, indices, or snapshots. That propagation is `/kb-sync`'s job, behind its
  own separate gate. The two approvals are never bundled into one yes.