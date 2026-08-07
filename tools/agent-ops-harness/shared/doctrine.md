# Agent-Ops Harness — Shared Doctrine

Every skill in this bundle (`todo`, `ingest`, `kb-sync`, `platform-ingest`) obeys the
rules below. They are written once here so the individual `SKILL.md` files can say
"follow shared doctrine" instead of repeating them. Nothing here is project-specific;
all project facts come from the config (see `config.example.json`).

---

## 1. Propose → Gate → Apply

No skill in this bundle writes a tracked file (priorities, KB canon, a project tracker)
without first emitting a **diff outline** and receiving **explicit user approval in the
same turn that names that diff**.

- The outline lists every intended change grouped by kind (STATUS FLIP / UPDATE / NEW /
  RETIRE / ALIGN / PRUNE / FLAG, depending on the skill).
- Then the skill STOPS and waits.
- Soft signals mid-discussion ("go ahead", "looks good", "sounds right") do **not**
  authorise an apply unless they explicitly reference the outline. If you are about to
  call an edit tool and cannot point to an approval message in this conversation that
  authorises that exact diff, STOP and re-present the outline.
- No exceptions, no shortcuts, no "obvious" cases.

Where a skill produces **two** batches (e.g. `ingest` reconciling the ops file, then
`kb-sync` reconciling the wider KB), the two approvals are **never bundled into one yes**.
The user may approve the first and decline or defer the second.

## 2. Concurrency safety

Sibling chats and background jobs may touch the same files.

- **Re-read every file immediately before you Edit it.** The Read+Edit tooling errors if
  the file changed since your last Read; treat that error as a signal to rebuild that
  hit's diff and re-prompt, not to retry blindly.
- **Never `replace_all` on a multi-entity file** (the priorities file, any index, any
  registry, any programme/portfolio doc). A value that appears 8 times is 8 surgical,
  re-read edits — not one sweep.
- Check on-disk state before proposing: a sibling chat may already have done the work.

This section covers FILE edits. The same problem in **git** is worse, because there the
damage is permanent — see §6 and [`parallel-git.md`](parallel-git.md).

## 3. Canon-first, arrow-of-correction

(Primarily `kb-sync`, but the principle is bundle-wide.)

- When a fact changes, write the **canonical** document first, then propagate outward to
  derived/living docs, then indices.
- **The arrow of correction always points away from canon.** Never edit canon to match a
  downstream copy. If a downstream doc contradicts the session's established truth, the
  downstream doc is the target — unless the finding *is* that canon is stale, in which
  case FLAG it for a human decision rather than guessing.

## 4. Never hard-delete

- Retiring a document = **move it to the archive dir** (`paths.archive_dir`) and leave a
  one-line forwarding pointer at the old location:
  `RETIRED <date>, superseded by <canonical path>, archived to <archive path>`.
- Never rewrite a timestamped snapshot's body to "make it current." A snapshot is either
  left as correctly-dated history or pruned-with-pointer — never edited into a false
  present.
- Every retirement is reversible by moving the file back.

## 5. Guard tiers (route out, don't overreach)

The source-of-truth registry marks certain fact-domains as **guard tiers** a skill must
not write — they belong to another owner. For each, the config's `routes` map names the
target skill:

- `routes.graph` — graph/visualisation data-layer fields.
- `routes.budget` — financial docs (budget, deal tracker, funding).
- `routes.dedupe` — duplicate-entity merges (a structural operation).

When a delta lands in a guard tier:
- If the route is configured (non-null), mark it `ROUTE_TO_<target>`, remove it from the
  write plan, and surface the hand-off in the close-out.
- If the route is `null` (the adopter has no such skill), **FLAG it to the user** — never
  write it silently.

## 6. Close the loop (via the ship gate, NOT via `git add`)

An ops pass that leaves its own edits uncommitted is not done. But **how** it commits
is not a detail — with parallel sessions, plain `git add && git commit && git push`
is actively destructive.

**LAND THE MOMENT THE APPROVED EDITS ARE APPLIED — same turn, not at session end.**
This is a hard rule, not tidiness. Uncommitted edits in a shared tree are the raw
material of a deadlock: two sessions edit the same markdown, neither can isolate its
own hunks non-interactively (`git add -p` needs a TTY no agent session has), so both
leave it, and the file accumulates on disk indefinitely, one bad checkout from gone.
Measured in the source system: one tracker carried a contested restructure across
**three** sessions before anyone could land it. **The window in which a sibling can
collide with you is exactly however long you leave your edit unlanded — so make it
small.** Landing early also means a later failure costs you one file, not a session.

> **This section changed.** It used to say "scoped `git add` the touched files, commit,
> push". That is safe with one session and harmful with several: a scoped add still
> sweeps a sibling's half-written hunks **in the same file**, a rejected push reports
> success while landing nothing, and neither `git` nor the skill knows whether the push
> deploys production. If you installed this harness before the ship gate shipped, read
> [`../../UPGRADE.md`](../../UPGRADE.md).

**The one command:**

```
python tools/agent-ops-harness/shared/ship.py commit --paths <files> -m "msg" --push
```

It builds the commit with git plumbing on a temporary index parented on a freshly
fetched trunk, so it **never touches the shared working tree**, cannot disrupt a
sibling session, re-parents and retries if trunk moves under it, and asks the REMOTE
whether the sha actually landed before claiming success.

Rules that follow from it:

- **Never `git add -A`/`-u`/`.`** and never `git commit -a`. Never `git checkout`,
  `merge`, `rebase` or `pull` in the shared tree.
- **You do not need to be on trunk to commit to trunk.** Content-only work belongs on
  trunk regardless of what branch the tree happens to be on. Isolation, when you need
  it, comes from `ship worktree`, never from a branch.
- **Check the blast radius first** (`ship blast --staged`). INERT means push straight to
  trunk. DEPLOYS means flag-gate it or take a worktree — and run `ship verify` after.
- **Contested-file guard:** if a file you touched also carries another session's
  uncommitted edits, land ONLY your hunks (`ship hunks <file>`, then
  `commit --replay <file> --hunks 2,3`). If you cannot tell which are yours, FLAG it and
  leave it uncommitted — never sweep in someone else's work.
- **Name files, never directories,** in `--paths`, and read the `--dry-run` list before
  pushing. A directory silently includes everything beneath it.
- `git.commit_email` in the config still applies: set it to pin an identity (some deploy
  providers attribute builds by commit email), or leave it `null` to use the repo's own.

Full standard, with the measured evidence behind each rule:
[`parallel-git.md`](parallel-git.md), or `ship rules` from any branch.

## 7. Watching + escalation

Every outbound action that expects a reply becomes a tracked "Watching" row with an
escalation date, so nothing that needs a follow-up is silently dropped. (See `todo`.)

## 8. Config, not hardcode

If a skill needs a path, a bucket name, a mail command, a registry location, or a route
target, it reads it from the config via `shared/config_loader.py`. If you find yourself
about to hardcode a project-specific string into skill prose, put it in the config
instead — that is the entire point of this bundle.
