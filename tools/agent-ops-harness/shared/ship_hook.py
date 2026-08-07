"""
ship gate -- hooks (optional but strongly recommended).
=======================================================

Delivery mechanism for `shared/ship.py`. The gate is worthless if a session has
to remember it exists, because agent sessions are ephemeral and have no memory of
the conversation that established the rule.

That experiment has already been run and lost: the harness's own
`platform-ingest/SKILL.md` has always carried the correct scoped-add discipline,
and feature-work sessions never open it. A convention that depends on being
remembered is not a control.

So the facts are PUSHED to the session, at the two moments they matter:

  SessionStart  -> branch lineage, divergence, orphans, live claims from siblings
  PreToolUse    -> before a git commit / push / merge / checkout, the blast radius
                   of what is about to move, plus overlapping claims

This hook NEVER blocks. It exits 0 always. That is deliberate: a blocked
ephemeral session with no human present has no recourse except `--no-verify`,
which teaches sessions to route around safety. Informing is strictly better when
the actor is capable but blind, and blindness is the actual failure here. (The one
irreversible failure -- committing a secret -- IS blocked, but inside `ship
commit`, not here.)

INSTALL (Claude Code): add to `.claude/settings.json` in the target repo --

  {
    "hooks": {
      "SessionStart": [
        { "hooks": [ { "type": "command",
            "command": "python tools/agent-ops-harness/shared/ship_hook.py" } ] }
      ],
      "PreToolUse": [
        { "matcher": "Bash", "hooks": [ { "type": "command",
            "command": "python tools/agent-ops-harness/shared/ship_hook.py" } ] }
      ]
    }
  }

One install covers every session on that machine, linked worktrees included.
For other agent runtimes, call this script with the same JSON payload shape on
stdin; it prints a `hookSpecificOutput.additionalContext` string and exits 0.

Part of the Agent-Ops Harness. Built by Ruins (Luca Martinelli). MIT.
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def _repo_root():
    try:
        p = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, encoding="utf-8", cwd=str(HERE), timeout=10,
        )
        if p.returncode == 0 and p.stdout.strip():
            return Path(p.stdout.strip())
    except Exception:
        pass
    return HERE.parent.parent.parent


ROOT = _repo_root()

try:
    SELF_REL = HERE.relative_to(ROOT).as_posix()
except Exception:
    SELF_REL = "tools/agent-ops-harness/shared"
SHIP_REL = f"{SELF_REL}/ship.py"
SHIP = f"python {SHIP_REL}"

# Cheap pre-filter: PreToolUse fires on EVERY Bash call, so bail out before
# importing or shelling out to git unless the command is actually a git write.
#
# The verb must be attached to an actual `git` invocation. Matching the bare word
# anywhere in the command string is not good enough: `python .../ship.py commit
# --push` contains both "git" (in a path) and "commit", and mis-fired on the
# gate's own dogfooding run.
# The `{0,4}?` span absorbs global options that take a value, e.g.
# `git -c core.quotepath=false push`, which a `-\S+` alternation alone misses.
GIT_WRITE_RE = re.compile(
    r"(?:^|[;&|(\s])git\s+(?:\S+\s+){0,4}?"
    r"(commit|push|merge|checkout|switch|rebase|cherry-pick|pull)\b"
)

# Verb detection must NOT read commit messages. Caught in the source system within
# one commit: adding `pull` to the verbs above made the hook fire its pull warning
# on `ship commit -m "...git's hint says use git pull..."` -- prose ABOUT git, not a
# git command. Alarm fatigue is the failure mode this whole gate keeps paying for,
# so strip -m/-F payloads first. Deliberately narrow: only message/file arguments,
# so a real verb outside the quotes is still seen.
MSG_ARG_RE = re.compile(
    r"""(?:-m|-F|--message|--file)(?:=|\s+)(?:"(?:[^"\\]|\\.)*"|'[^']*'|\S+)""",
    re.S,
)

HOOK_EVENT = "SessionStart"

# The tree a command will actually touch. Set per-invocation; defaults to the
# shared tree only when nothing better is known.
_CWD = None
_TRUNK = None
_TRUNK_BRANCH = None


def emit(context):
    """Non-blocking context injection."""
    if context:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": HOOK_EVENT,
                        "additionalContext": context,
                    }
                }
            )
        )
    sys.exit(0)


def run(*args, timeout=20):
    try:
        p = subprocess.run(
            ["git", "-c", "core.quotepath=false", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=_CWD or str(ROOT),
            timeout=timeout,
        )
        return p.stdout.strip() if p.returncode == 0 else ""
    except Exception:
        return ""


def trunk():
    """`origin/<default branch>` -- asked of the remote, never assumed."""
    global _TRUNK, _TRUNK_BRANCH
    if _TRUNK is None:
        head = run("symbolic-ref", "--quiet", "refs/remotes/origin/HEAD", timeout=8)
        if head.startswith("refs/remotes/"):
            _TRUNK = head[len("refs/remotes/"):]
        elif run("rev-parse", "--verify", "--quiet", "origin/main", timeout=8):
            _TRUNK = "origin/main"
        else:
            _TRUNK = "origin/master"
        _TRUNK_BRANCH = _TRUNK.partition("/")[2]
    return _TRUNK


def trunk_branch():
    trunk()
    return _TRUNK_BRANCH


def _session_state_path(session_id):
    """Per-session memo, kept beside the claims in the SHARED git dir.

    Measured in the source system: a session's start context named one branch, a
    sibling switched the shared tree mid-session, and the session only found out
    when a push reported a different name. Sessions cannot notice that on their
    own, so the last-seen branch is remembered here and compared on every git
    command.
    """
    common = run("rev-parse", "--git-common-dir") or str(ROOT / ".git")
    p = Path(common)
    if not p.is_absolute():
        p = ROOT / p
    d = p.resolve() / "ship-sessions"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None
    # Keyed per (session, TREE). A session that touches both the shared tree and a
    # worktree legitimately sees two different branches; keying on session alone
    # made every switch between them look like "the branch changed under you" --
    # the same alarm-fatigue class this file keeps guarding against.
    safe = re.sub(r"[^A-Za-z0-9_-]", "", session_id or "anon")[:48] or "anon"
    tree = re.sub(r"[^A-Za-z0-9_-]", "", Path(_CWD or ROOT).name)[:24] or "root"
    return d / f"{safe}--{tree}.json"


def load_session_state(session_id):
    p = _session_state_path(session_id)
    if not p or not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_session_state(session_id, state):
    p = _session_state_path(session_id)
    if not p:
        return
    try:
        p.write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        pass


_CD_RE = re.compile(r'^\s*cd\s+"?([^"&;|]+?)"?\s*(?:&&|;|$)')


def resolve_cwd(payload):
    """Which working tree will this command actually run in?

    Measured: the hook reported the SHARED tree's 1192 dirty files on every git
    call made inside a CLEAN worktree, ~12 times, each correctly ignored. A gate
    that cries wolf trains the operator to dismiss it, and the one message that
    mattered arrived through the same channel. Reporting the wrong tree was the
    single biggest thing degrading this gate.

    Order: an explicit `cd <path> && ...` prefix in the command, then the session's
    cwd from the hook payload, then the shared tree.
    """
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    m = _CD_RE.match(cmd)
    for cand in (m.group(1).strip() if m else None, payload.get("cwd")):
        if not cand:
            continue
        try:
            p = Path(cand).expanduser()
            if p.is_dir():
                return str(p.resolve())
        except Exception:
            continue
    return str(ROOT)


def dirty_set():
    """Paths dirty in the tree this command touches."""
    out = run("status", "--porcelain", "-z", timeout=12)
    return {e[3:] for e in out.split("\0") if len(e) > 3}


def held_work(state, now):
    """Work THIS session has accumulated and not landed.

    If sessions share one commit identity, git carries no session information, so
    nothing can say which dirty file belongs to whom. But a session CAN snapshot
    the dirty set on first contact and watch what appears AFTER: those entries are
    almost certainly its own. That turns "uncommitted work is the fragile state"
    from a stopwatch nobody can enforce into a computed signal.

    Returns (count, minutes_since_first_appeared) or (0, 0).
    """
    try:
        current = dirty_set()
    except Exception:
        return 0, 0
    baseline = state.get("dirty_baseline")
    if baseline is None:
        state["dirty_baseline"] = sorted(current)
        state["dirty_since"] = now
        return 0, 0
    new = current - set(baseline)
    if not new:
        return 0, 0
    if not state.get("held_since"):
        state["held_since"] = now
    return len(new), int((now - state["held_since"]) / 60)


def tree_label():
    """Name the tree we are reporting on, so the message is unambiguous."""
    top = run("rev-parse", "--show-toplevel", timeout=8)
    if not top:
        return "(unknown tree)", False
    top = Path(top)
    is_shared = top.resolve() == ROOT.resolve()
    return (("the SHARED tree" if is_shared else f"worktree `{top.name}`"), is_shared)


def load_ship():
    """The gate module, falling back to TRUNK's copy when the working one is broken.

    Measured in the source system: a sibling editing ship.py mid-session took down
    BOTH the safe commit path AND this hook -- for every live session at once,
    because the guard rail lives in the shared tree with everything else. Observed:
    a SyntaxError from a half-written line, then `ValueError: source code string
    cannot contain null bytes`. The single tool that prevents a destructive push
    had no redundancy.

    Trunk's copy is always syntactically whole: it had to import to get committed.
    So when the working copy will not import, use trunk's. Returns (module, stale);
    stale=True means the numbers come from trunk's version rather than the file on
    disk, which the caller MUST disclose.

    A write-guard blocking edits to ship.py is the wrong shape: it would block the
    session fixing the breakage, and this gate blocks in exactly one place (the
    secret scan) because that failure is irreversible. Redundancy achieves the same
    end without a block.
    """
    try:
        import ship
        return ship, False
    except Exception:
        pass
    try:
        import importlib.util
        import tempfile

        blob = subprocess.run(
            ["git", "show", f"{trunk()}:{SHIP_REL}"],
            capture_output=True, cwd=str(ROOT), timeout=20,
        )
        if blob.returncode != 0 or not blob.stdout:
            return None, True
        tmp = Path(tempfile.gettempdir()) / "ship_trunk_fallback.py"
        tmp.write_bytes(blob.stdout)
        spec = importlib.util.spec_from_file_location("ship_trunk", tmp)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod, True
    except Exception:
        return None, True


def gate_down():
    return (
        "SHIP gate: GATE DOWN -- DO NOT TRUST ANY OUTPUT FROM IT RIGHT NOW.\n"
        f"  {SHIP_REL} will not import (a sibling is probably mid-edit) and trunk's\n"
        "  copy could not be loaded either, so no deploy verdict and no counts are\n"
        "  computed. A broken gate that prints confident numbers is worse than one that\n"
        f"  is silent: verify by hand -- `git diff --stat {trunk()}..HEAD`."
    )


def stale_gate():
    return (
        f"  NOTE: {SHIP_REL} on disk will not import, so this used TRUNK's copy. The\n"
        "  numbers are trustworthy; the working file is broken and needs fixing."
    )


def session_start(session_id=""):
    ship, ship_stale = load_ship()
    if ship is None:
        return gate_down()

    lines = ["SHIP gate (parallel-session git state):"]
    if ship_stale:
        lines.append(stale_gate())

    run("fetch", "--quiet", "origin", trunk_branch(), timeout=25)
    branch = run("rev-parse", "--abbrev-ref", "HEAD") or "?"
    now = time.time()
    # `warned` is set here too: SessionStart already states the violation in full,
    # so the throttled PreToolUse notice must not repeat it a minute later.
    save_session_state(session_id, {"branch": branch, "seen": now, "warned": now})
    counts = run("rev-list", "--left-right", "--count", f"{trunk()}...HEAD").split()
    if len(counts) == 2:
        lines.append(
            f"  branch {branch}: {counts[1]} ahead / {counts[0]} behind {trunk()}"
        )
    else:
        lines.append(f"  branch {branch}")

    if branch != trunk_branch():
        mb = run("merge-base", trunk(), "HEAD")
        hint = run("config", "--get", f"branch.{branch}.vscode-merge-base")
        if hint and hint != trunk():
            lines.append(
                f"  WARNING: this branch was cut from {hint}, NOT {trunk()}. It carries"
            )
            lines.append(
                f"  that branch's unlanded work as inherited baggage. Run `{SHIP} status`."
            )
        elif mb:
            desc = run("log", "-1", "--format=%h %ad", "--date=short", mb)
            lines.append(f"  forked from trunk at {desc}")

    try:
        only_branch, only_trunk = ship._orphan_sets()
        if only_branch or only_trunk:
            lines.append(
                f"  orphans: {len(only_branch)} file(s) exist ONLY on this branch, "
                f"{len(only_trunk)} only on trunk"
            )
            if only_trunk:
                lines.append(
                    "  a naive merge of this branch would DELETE those trunk-only files."
                )
    except Exception:
        pass

    try:
        claims = ship.load_claims()
        if claims:
            lines.append(f"  {len(claims)} path claim(s) held by other sessions:")
            for c in claims[:6]:
                lines.append(
                    f"    {c['id']} {', '.join(c['globs'])} [{c['branch']}] "
                    f"{c['intent'] or '(no intent)'} ({ship._age(c['created'])})"
                )
            lines.append("  Do NOT edit claimed paths without coordinating.")
        else:
            lines.append("  no path claims held. Claim before sustained work on a subtree:")
            lines.append(f'    {SHIP} claim "<glob>" -l "<intent>"')
    except Exception:
        pass

    dirty = len([l for l in run("status", "--porcelain").splitlines() if l])
    if dirty > 50:
        lines.append(
            f"  working tree holds {dirty} dirty entries from parallel sessions -- "
            "NEVER `git add -A`."
        )

    # The decisive fact, stated at the top of every session. A session that knows
    # only this one thing cannot repeat the measured failure: eight commits of pure
    # knowledge-base work stranded on a feature branch the session never chose,
    # purely because that was what the shared tree happened to be on.
    if branch != trunk_branch():
        tb = trunk_branch()
        lines.append("")
        lines.append(
            f"  YOU DO NOT NEED TO BE ON {tb} TO COMMIT TO {tb}. From this branch:"
        )
        lines.append(f'    {SHIP} commit --paths <p>... -m "msg" --push')
        lines.append(
            f"  lands on {trunk()} without switching and without touching the shared"
        )
        lines.append(
            "  tree. If this session is content-only (knowledge files, drafts, trackers,"
        )
        lines.append(
            "  one-off scripts), that is where it belongs -- do not let the checked-out"
        )
        lines.append(f"  branch decide. `{SHIP} rules` for the standard.")

    return "\n".join(lines)


def pre_tool_use(payload):
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    if "git" not in cmd:
        return ""

    session_id = payload.get("session_id") or ""
    cmd_s = MSG_ARG_RE.sub(" ", cmd)      # never match a verb inside a message
    verbs = set(GIT_WRITE_RE.findall(cmd_s))
    lines = []

    ship, ship_stale = load_ship()
    if ship is None:
        return gate_down()
    if ship_stale:
        lines.append(stale_gate())
    label, is_shared = tree_label()
    dirty = len([l for l in run("status", "--porcelain", timeout=10).splitlines() if l])
    branch = run("rev-parse", "--abbrev-ref", "HEAD", timeout=8)
    tb = trunk_branch()
    if os.environ.get("SHIP_HOOK_DEBUG"):
        print(f"[trace] cwd={_CWD} label={label} shared={is_shared} "
              f"dirty={dirty} branch={branch} verbs={verbs}", file=sys.stderr)

    # --- branch identity, checked on FIRST git contact, not the first write ----
    state = load_session_state(session_id)
    last = state.get("branch")
    now = time.time()
    if branch and last and branch != last:
        lines.append(
            f"SHIP gate: THE BRANCH CHANGED UNDER YOU. This session last saw "
            f"`{last}`, {label} is now on `{branch}`."
        )
        lines.append("  A sibling switched it. Re-check where your work will land.")
    if branch and branch != last:
        state["branch"] = branch
        state["seen"] = now
        save_session_state(session_id, state)

    # --- rule 1: only meaningful for the SHARED tree -------------------------
    if is_shared and branch and branch != tb:
        if now - state.get("warned", 0) > 1800:
            state["warned"] = now
            save_session_state(session_id, state)
            lines.append(
                f"SHIP gate: the shared tree is on `{branch}`, not {tb}. You do NOT "
                f"need to switch to land on {tb}:"
            )
            lines.append(f'    {SHIP} commit --paths <p>... -m "msg" --push')

    # --- held work: the fragile state, measured rather than nagged about -------
    held_n, held_min = held_work(state, now)
    save_session_state(session_id, state)
    if held_n >= 5 and held_min >= 20 and now - state.get("held_warned", 0) > 1800:
        state["held_warned"] = now
        save_session_state(session_id, state)
        lines.append(
            f"SHIP gate: {held_n} file(s) have gone uncommitted since this session "
            f"started, oldest ~{held_min}m ago, in {label}."
        )
        lines.append(
            "  Uncommitted work in a shared tree is the state most exposed to a "
            "sibling switching HEAD under you. If you cannot ship it right now, pick "
            "one deliberately:"
        )
        lines.append(f"    NOT DONE yet -> {SHIP} worktree <name> --claim ...")
        lines.append(
            "    DONE, but a dependency is not live -> ship it DARK behind a capability "
            "probe and land it now"
        )

    if not verbs:
        return "\n".join(lines)

    # --- destructive-in-a-dirty-tree: ONLY when this tree is actually dirty ---
    # Previously this fired from the shared tree's state no matter which tree the
    # command ran in, so a clean worktree got a 1192-dirty-file alarm.
    #
    # `git pull` is the one git ADVISES and it is close to the worst move available
    # here. A non-fast-forward rejection prints "hint: use 'git pull' before pushing
    # again", which is authoritative-looking and wrong in a shared tree carrying a
    # thousand siblings' dirty entries: pull merges into that tree. git cannot know
    # about `ship commit`, so the hook says it.
    if "pull" in verbs:
        lines.append(
            f"SHIP gate: `git pull` in {label}. If you got here from a non-fast-forward "
            "rejection, git's own hint is WRONG for this repo."
        )
        lines.append(
            "  A pull merges trunk into a shared tree holding other sessions' "
            "uncommitted work. To land your paths on a moved trunk WITHOUT merging:"
        )
        lines.append(f'    {SHIP} commit --paths <p>... -m "msg" --push')
        lines.append(f"  It re-parents on a freshly fetched {trunk()} by design.")

    if verbs & {"checkout", "switch", "merge", "rebase", "pull"}:
        if dirty > 50:
            lines.append(
                f"SHIP gate: {label} holds {dirty} dirty entries from parallel sessions."
            )
            lines.append(
                "  A checkout / merge / rebase here disrupts other live sessions. To "
                "LAND work without touching it:"
            )
            lines.append(f"    {SHIP} commit --paths <paths> -m <msg> --push")
        elif not is_shared:
            lines.append(
                f"SHIP gate: you are in {label} (clean, branch `{branch}`) -- this is "
                "isolated, nothing here can disrupt a sibling session."
            )

    # --- staging: scoped and unscoped are NOT the same thing ------------------
    if "commit" in verbs:
        unscoped = (
            bool(re.search(r"git\s+add\s+(-A|--all|\.|-u)\b", cmd_s))
            or bool(re.search(r"git\s+commit\s+-[a-zA-Z]*a|git\s+commit\s+--all\b", cmd_s))
        )
        if os.environ.get("SHIP_HOOK_DEBUG"):
            print(f"[trace] unscoped={unscoped} lines_so_far={len(lines)}", file=sys.stderr)
        if unscoped and dirty > 50:
            lines.append(
                f"SHIP gate: unscoped staging in {label} ({dirty} dirty entries). "
                "`git add -A` / `commit -a` sweeps other sessions' unfinished work into "
                "your commit. Stage explicit paths instead."
            )
        staged = [p for p in run("diff", "--cached", "--name-only", "-z").split("\0") if p]
        if staged:
            hits = ship.compute_blast(staged)
            if hits:
                lines.append(
                    f"SHIP gate: these {len(staged)} staged path(s) DEPLOY production:"
                )
                for h in hits:
                    lines.append(f"    * {h['surface']}")
            claims = [c for c in ship.load_claims()
                      if ship._globs_overlap(c["globs"], staged)]
            for c in claims:
                lines.append(
                    f"  NOTE: another session claims {', '.join(c['globs'])} "
                    f"[{c['branch']}] {c['intent']} ({ship._age(c['created'])})"
                )

    # --- push: blast from what is ACTUALLY being pushed -----------------------
    if "push" in verbs:
        # Measured: a single markdown file drew a 3-deploy-surface warning and then
        # fired zero workflows. Cause: the range was computed against a STALE local
        # trunk ref, inflating it to the branch's whole divergence. Fetch first.
        run("fetch", "--quiet", "origin", tb, timeout=25)

        # The worst near-miss on record: a session authored ONE markdown file,
        # pushed, and the push would have REVERTED ten files from other sessions --
        # including two brand-new docs -- and fired two deploys, because local HEAD
        # was 16 commits behind trunk. Nothing in `git commit` or `git push` output
        # hints at this, and a bare changed-path count does not either: it says "N
        # changed paths" without distinguishing what you ADD from what you UNDO.
        behind = run("rev-list", "--count", f"HEAD..{trunk()}") or "0"
        if behind.isdigit() and int(behind) > 0:
            undo = [p for p in run("diff", "--name-only", "-z",
                                   "HEAD", trunk()).split("\0") if p]
            lines.append(
                f"SHIP gate: HEAD is {behind} commit(s) BEHIND {trunk()}. This push "
                "will be REJECTED as non-fast-forward."
            )
            lines.append(
                f"  Forcing it would REVERT {len(undo)} file(s) that trunk has and your "
                "HEAD does not -- other sessions' landed work."
            )
            lines.append(
                "  git will advise `git pull`. Do NOT: it merges trunk into a shared "
                "tree full of siblings' uncommitted work. Land your own paths instead:"
            )
            lines.append(f'    {SHIP} commit --paths <p>... -m "msg" --push')

        names = [p for p in run("diff", "--name-only", "-z",
                                f"{trunk()}..HEAD").split("\0") if p]
        if names:
            hits = ship.compute_blast(names)
            if hits:
                lines.append(
                    f"SHIP gate: this push lands {len(names)} changed path(s) and WILL "
                    "deploy production:"
                )
                # Tags MUST match `ship blast`. In the source system they did not for a
                # while: the hook kept delivering a superseded verdict to every session
                # at push time, which is the exact failure the standard exists to
                # prevent -- a wrong verdict the next reader trusts.
                for h in hits:
                    if h.get("forced"):
                        tag = "[FORCED] "
                    elif h.get("vercel"):
                        tag = "[BRANCH!]"
                    else:
                        tag = "[JOB]    "
                    lines.append(f"    * {tag} {h['surface']}")
                if any(h.get("vercel") and not h.get("forced") for h in hits):
                    lines.append(
                        "  [BRANCH!] promotion is BRANCH-TRIGGERED: a green build means "
                        "SOMETHING built, and says NOTHING about what is live. Run "
                        f"`{SHIP} verify` and assert on something UNIQUE to the change "
                        "-- a 200 on the homepage proves nothing."
                    )
                lines.append("  Push IS the release step here. Verify before, not after.")
            else:
                lines.append(
                    f"SHIP gate: this push lands {len(names)} changed path(s) and "
                    "deploys NOTHING."
                )
        if is_shared and branch != tb:
            hint = run("config", "--get", f"branch.{branch}.vscode-merge-base")
            if hint and hint != trunk():
                lines.append(
                    f"SHIP gate: branch {branch} was cut from {hint}, not {trunk()}. "
                    f"It carries inherited baggage. `{SHIP} status` for detail."
                )

    return "\n".join(lines)


def main():
    global HOOK_EVENT, _CWD
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    HOOK_EVENT = payload.get("hook_event_name") or "SessionStart"
    # Report on the tree the command will ACTUALLY touch, not on the shared one.
    _CWD = resolve_cwd(payload)

    try:
        if HOOK_EVENT == "PreToolUse":
            emit(pre_tool_use(payload))
        else:
            emit(session_start(payload.get("session_id") or ""))
    except Exception as exc:
        # The gate must never break a session: fail open, never block. But it must
        # not fail SILENT either -- a swallowed exception here is indistinguishable
        # from "nothing to warn about", which is exactly how a broken gate goes
        # unnoticed. Surface the failure as context so it gets fixed.
        if os.environ.get("SHIP_HOOK_DEBUG"):
            import traceback
            traceback.print_exc(file=sys.stderr)
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": HOOK_EVENT,
            "additionalContext": f"SHIP gate: hook errored ({type(exc).__name__}: "
                                 f"{str(exc)[:160]}). Its warnings are NOT reliable "
                                 f"right now -- re-run with SHIP_HOOK_DEBUG=1 to see "
                                 f"the traceback.",
        }}))
        sys.exit(0)


if __name__ == "__main__":
    main()