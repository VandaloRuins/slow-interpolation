# The Parallel-Git Standard (the ship gate)

> **This supersedes the old `doctrine.md` §6.** If you installed this harness before
> the ship gate shipped, your skills were told to finish with `git add <files> &&
> git commit && git push`. That is safe with one session and harmful with several.
> See [`../../UPGRADE.md`](../../UPGRADE.md) for what to change.

Everything here is enforced or computed by `shared/ship.py`. Read it once; after
that, run `python tools/agent-ops-harness/shared/ship.py rules` from any branch.

---

## Why the naive advice breaks

The harness assumes several agent sessions run against one repo. Its skills
already handle that for **file edits** (re-read before every Edit, never
`replace_all`, flag contested files — `doctrine.md` §2). They did not handle it
for **git**, and git is where the damage is permanent.

Four independent failures, all measured in the system this harness was extracted
from:

**1. The working tree is shared.** Sessions do not get their own checkout. The
tree routinely holds hundreds of dirty files belonging to siblings, so `git
status` is noise and `git add -A` is a live hazard. Even a *scoped* `git add
<file>` sweeps in whatever else a sibling has half-written **in that same file**.

**2. One tree has one HEAD.** `git checkout -b mine` does not give a session its
own branch — it moves **every** session attached to that tree onto the new branch.
Per-session branches are incoherent here. Isolation can only come from a
`git worktree`.

**3. Pushes race.** Two sessions pushing in the same second means one is a
non-fast-forward, and git rejects it. A rejected push writes to stderr and leaves
stdout empty, so a wrapper that does not *check* reports success for a commit
that never landed. This silently discarded a 292-file commit; it was found hours
later, by accident.

**4. Nobody can see what a push deploys.** If CI deploys on push, whether a change
ships production is deterministic from the changed paths plus the workflow
`paths:` filters — but no session computes it. So sessions either deploy blind or,
far more often, park work on a hedge branch "until we know", and nobody ever
resolves the branch. Measured on one such branch: **38% of its commits deployed
nothing at all** and were quarantined for days anyway.

Note what the actual failure was. Not sessions doing reckless things — sessions
being **over-cautious while blind**. A branch here is an unresolved decision with
no owner, wearing a git costume.

---

## The five rules

### Rule 0 — you do NOT need to be on trunk to commit to trunk

```bash
python tools/agent-ops-harness/shared/ship.py commit --paths <p>... -m "msg" --push
```

Lands on `origin/<trunk>` from **any** checked-out branch, without switching and
without touching the shared working tree. Content-only work (knowledge files,
drafts, trackers, one-off scripts) belongs on trunk.

**Do not let the checked-out branch decide where your work goes.** One session
lost eight commits of pure knowledge-base work onto an unrelated feature branch
purely because that was what the tree happened to be on when it started.

### Rule 1 — the shared working tree lives on trunk

Every session attached to it is on the same branch at the same time, and a sibling
can change it under you mid-session. The hook detects exactly this and tells you
("THE BRANCH CHANGED UNDER YOU").

### Rule 2 — isolation comes from a WORKTREE, never from a branch

```bash
python tools/agent-ops-harness/shared/ship.py worktree <name> --claim "<glob>" -l "<intent>"
```

Cuts from a **freshly fetched trunk**, explicitly. Two failures become unreachable
that way: `git checkout -b` moving every live session, and `git worktree add`
defaulting to HEAD and inheriting whatever the tree was carrying.

**THE ONE HARD RULE: never cut a branch from another branch.** That is what put a
stale vendored library on an unrelated feature branch and blocked it for days —
the session that got blocked had never touched that file. `ship status` detects
this lineage and warns.

### Rule 3 — deploy risk is COMPUTED, never remembered

```bash
python tools/agent-ops-harness/shared/ship.py blast --staged
```

- **INERT** → push straight to trunk. A branch would only defer the merge.
- **DEPLOYS** → trunk if flag-gated or verified; otherwise a **short-lived**
  branch cut from trunk, plus a claim.

Do not eyeball this. Workflow `paths:` filters routinely cover more than people
remember — in the source system, editing a skill file deployed a website.

### Rule 4 — never resolve a conflict in a file you do not own

Ship your own paths; file the residue as a blocked row on the owning project's
tracker via `/platform-ingest`. `ship orphans` and `ship close` print the owner
from the Project Registry.

**Never** `git add -A`. **Never** checkout / merge / rebase in the shared tree.

---

## Contested files: land only YOUR hunks

`git add -p` needs a TTY no unattended session has, which is why "just commit your
own changes" had no implementation for a long time and every session fell through
to "do not commit" while edits piled up on disk.

```bash
python .../ship.py hunks <file>                                   # numbered hunks vs trunk
python .../ship.py commit --replay <file> --hunks 2,3 -m "..." --push
```

Unselected regions are taken **verbatim from trunk**, so the other sessions' work
is neither committed nor destroyed.

If you cannot tell which hunks are yours, **do not commit the file.** Flag it in
your run summary and leave it. Commit wholesale only on explicit human
authorisation — and when you do, **say so in the commit message**, naming the
foreign content and who authorised it. If your sessions share one commit identity,
the message is the only attribution channel that exists.

If trunk moved while you were editing (so the diff is one enormous hunk that
`--replay` cannot split), rebase your edit onto trunk's current version in a
scratch file and:

```bash
python .../ship.py commit --content <repopath>=<scratchfile> -m "..." --push
```

---

## Untracked vs contested — different problems, opposite answers

| | What it is | What to do |
|---|---|---|
| `ship untracked` | Real content **nobody has ever committed**. One `git clean` from gone. | These are ADDITIONS. **Land them.** The risk is in *not* landing them. |
| `ship contested` | **Tracked** files carrying other sessions' hunks mixed with yours. | Re-apply your edit on trunk's version, or leave it. Never sweep. |

---

## The secret gate — the one place this blocks

`ship commit` scans the staged blob set before writing and **exits 3 on a hit,
committing nothing.** Everything else in this gate informs and never blocks,
because a blocked unattended session with no human present just learns to work
around the block.

Blocking is right here and nowhere else because the failure is **irreversible**:
git history is permanent, rewriting it across live parallel sessions is worse than
the leak, and the only remedy afterwards is rotating the credential.

Two traps, both already bit:

- **Directory-level `--paths`** silently includes everything beneath it. This is
  how a live API key reached a remote while the commit message claimed to exclude
  it. **Name files, and READ the `--dry-run` list.**
- **Nested git repos** are listed by git as one trailing-slash entry; committing
  one creates a broken gitlink. Check `ls -d <dir>/.git` first.

Override with `--i-verified-no-secrets` only when you state in the commit message
what you checked and how.

---

## Pushed / built / promoted / live are FOUR states

`blast` computes the promotion mode from the workflow text:

| Tag | Meaning |
|---|---|
| `[FORCED]` | The provider CLI runs with a production flag from CI. It never consults the project's production-branch setting, so no dashboard config can divert it. **Green run == production changed.** |
| `[BRANCH!]` | Branch-triggered promotion. A green run means *something* built and says **nothing** about what is live. |
| `[JOB]` | No production alias at all (a database publish, a bucket sync). Green means the job ran. |

Only `[BRANCH!]` can be green-but-not-live. Observed: every push built fine, the
provider reported success, and production 404'd for **20+ minutes** — because the
deploys were previews that were never promoted.

After any deploying push:

```bash
python tools/agent-ops-harness/shared/ship.py verify
```

It walks the ladder — on remote → received → built → **promoted** → live. Rung 4
is the one everybody skips. Rung 5 it cannot do for you: **assert on something
unique to the change.** A 200 on the homepage proves nothing.

---

## Commit messages carry evidence, not verdicts

If sessions share one commit identity, `git log`, `blame` and `shortlog` carry
**zero** session information. The message is the only channel for reasoning that
exists.

- If a message asserts a cause, it must carry one line of output supporting it.
- An unconfirmed diagnosis must say **"hypothesis"**. A bare verdict cost a later
  session two pushes and twenty minutes when it inherited a wrong conclusion.
- Backticks inside a double-quoted `-m` are **command substitution**. A message
  describing a deploy command once *executed* that deploy command. Use
  `-F <file>` for anything long.

**A no-op is a valid terminal state.** If the tool says there is nothing to do,
report that. Never synthesize a sha to satisfy a verify step.

---

## Command reference

| Command | What it answers |
|---|---|
| `ship rules` | The standard, readable from any branch |
| `ship status` | Lineage, divergence, orphans, live claims |
| `ship blast --staged` | Would this push deploy anything? |
| `ship commit --paths ... -m "..." --push` | Land scoped work on trunk from anywhere |
| `ship hunks <file>` / `commit --replay` | Land only your own hunks of a contested file |
| `ship untracked` | Content that exists only in the working tree |
| `ship contested` | Tracked files carrying foreign hunks |
| `ship claim "<glob>" -l "<intent>"` / `claims` / `release` | Advisory cross-session leases |
| `ship worktree <name>` | Isolation, done correctly |
| `ship close --branch <ref>` | How to END a branch: landable / contested / dead |
| `ship orphans` | Files on a branch and nowhere else |
| `ship verify [sha]` | Walk the deploy ladder |

Every command is read-only except `commit` (writes a commit), `claim`/`release`
(writes a lease file) and `worktree` (creates a worktree). None of them ever
touch the shared working tree's contents.

---

*Part of the Agent-Ops Harness. Built by Ruins (Luca Martinelli). MIT.*