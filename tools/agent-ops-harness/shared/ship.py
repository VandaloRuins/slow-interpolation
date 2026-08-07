"""
ship -- the parallel-git gate for the agent-ops harness.
========================================================

WHY THIS EXISTS
---------------
The rest of this harness assumes many agent sessions run against ONE repo. Its
skills already handle that for FILE edits (re-read before every edit, never
`replace_all`, flag contested files). They did not handle it for GIT, and the
original `shared/doctrine.md` §6 told every skill to finish with:

    git add <touched files> && git commit && git push

That instruction is safe with one session and actively harmful with several. It
was measured wrong in the source system it came from, and this file is the fix.

Four things break when parallel sessions each run that sequence:

  1. THE WORKING TREE IS SHARED. Sessions do not get their own checkout. The tree
     routinely holds hundreds of dirty files belonging to other sessions, so
     `git status` is noise and `git add -A` is a live hazard. Even a scoped
     `git add <file>` sweeps in whatever ELSE a sibling has half-written in that
     same file.
  2. ONE TREE HAS ONE HEAD. `git checkout -b mine` does not give a session its
     own branch, it moves EVERY session attached to that tree onto the new
     branch. Per-session branches are incoherent; isolation can only come from a
     `git worktree`.
  3. PUSHES RACE. Two sessions pushing within the same second means one is a
     non-fast-forward and git rejects it. A rejected push writes to stderr and
     leaves stdout empty, so a wrapper that does not CHECK reports success for a
     commit that never landed. In the source system this silently discarded a
     292-file commit and was found hours later, by accident.
  4. NOBODY CAN SEE WHAT A PUSH DEPLOYS. If the repo has CI that deploys on
     push, whether a given change ships production is deterministic from the
     changed paths plus the workflow `paths:` filters -- but no session computes
     it, so sessions either deploy blind or (far more common) park work on a
     hedge branch "until we know", and nobody ever resolves the branch. Measured
     on one such branch: 38% of its commits deployed nothing at all and were
     quarantined for days anyway.

So this tool does not block (with ONE principled exception, below). It makes the
cheaply-computable facts visible and gives a safe way to act on them:

    rules      the standard itself, readable from any branch
    blast      what would this push actually deploy?         (INERT / DEPLOYS)
    status     lineage, divergence, orphans, claims          (fork-off-a-branch detection)
    claim      advisory path lease shared across sessions
    claims     what other sessions are working on right now
    release    drop a lease
    worktree   isolation done correctly (cut from a fresh trunk)
    close      how to END a branch: landable / contested / dead
    orphans    what exists on a branch and nowhere else
    untracked  real content that exists ONLY in the working tree
    contested  tracked files carrying other sessions' unfinished edits
    hunks      list a contested file's hunks (headless `git add -p`)
    commit     ship a path-scoped commit without touching the working tree
    verify     walk the deploy ladder (pushed / built / promoted / live)

`commit` is the important one. It is a git-plumbing pattern -- temporary index,
read-tree, update-index, commit-tree, parented on a freshly fetched trunk, pushed
as a bare ref -- that never checks out, never merges, never stages into the shared
index, and therefore cannot disrupt a sibling session. It also cannot be disrupted
BY one: if trunk moves mid-operation it re-parents and retries, then asks the
REMOTE whether the sha actually landed before claiming success.

THE ONE PLACE IT BLOCKS is the secret scan in `commit`. Everything else informs,
because a blocked unattended session with no human present just learns to work
around the block. The exception is principled: a leaked credential is
IRREVERSIBLE. Git history is permanent, rewriting it across live parallel
sessions is worse than the leak, and the only remedy afterwards is rotating the
credential.

CONFIG
------
Reads the harness runtime config (`agent-ops-harness.config.json`) if present,
under the `git` key -- see `config.example.json`. Everything has a working
default, so this file also runs standalone in a repo that has no harness config.

    "git": {
      "trunk": "auto",                    // or "origin/main", "origin/master"
      "commit_email": null,               // pin an identity, or null = repo default
      "commit_name": null,
      "claims_ttl_hours": 6,
      "extra_deploy_surfaces": [],        // [["glob", "label"], ...] deploys with no workflow
      "untracked_noise": [],              // dirs whose untracked files are scratch
      "secret_value_files": [".env", "tools/.env"],
      "secret_scan_skip": []
    }

REQUIREMENTS
------------
Python 3.8+, git. `pyyaml` only for `blast`/`commit`/`verify` in a repo that has
`.github/workflows/` (without it those commands say so and exit). `verify` uses
the `gh` CLI for rungs 2-3 if it is installed.

Usage:
    python tools/agent-ops-harness/shared/ship.py rules
    python tools/agent-ops-harness/shared/ship.py status
    python tools/agent-ops-harness/shared/ship.py blast --staged
    python tools/agent-ops-harness/shared/ship.py commit --paths <p>... -m "msg" --dry-run
    python tools/agent-ops-harness/shared/ship.py commit --paths <p>... -m "msg" --push

NOTE: `commit` targets trunk from ANY checked-out branch. You never need to switch
branches to land on trunk, and content-only work should not sit on a feature branch
just because that is what the tree happened to be on.

Part of the Agent-Ops Harness. Built by Ruins (Luca Martinelli). MIT.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

# Windows consoles default to cp1252, which cannot encode most knowledge-base
# content (arrows, accented names, dashes). Printing a hunk of a tracker file
# crashed on a single U+2192. Reconfigure once, replace rather than raise: a
# diagnostic tool must never die on the content it is describing.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# -- config -------------------------------------------------------------------

CONFIG_NAMES = ("agent-ops-harness.config.json",)
_CFG = None


def cfg():
    """The `git` block of the harness runtime config, or {} if there is none.

    Deliberately tolerant: this tool must work in a repo that has the harness,
    a repo that has only this file, and a repo mid-install.
    """
    global _CFG
    if _CFG is None:
        _CFG = {}
        env = os.environ.get("AGENT_OPS_CONFIG")
        candidates = [Path(env)] if env else []
        candidates += [repo_root() / name for name in CONFIG_NAMES]
        for c in candidates:
            try:
                if c.is_file():
                    _CFG = json.loads(c.read_text(encoding="utf-8")).get("git", {}) or {}
                    break
            except Exception:
                continue
    return _CFG


def _detect_trunk():
    """The integration branch. Configured value wins; otherwise ask the remote."""
    want = cfg().get("trunk")
    if want and want != "auto":
        return want
    head = git("symbolic-ref", "--quiet", "refs/remotes/origin/HEAD", check=False).strip()
    if head.startswith("refs/remotes/"):
        return head[len("refs/remotes/"):]
    for guess in ("origin/main", "origin/master"):
        if rev(guess):
            return guess
    return "origin/main"


_TRUNK = None


def trunk():
    global _TRUNK
    if _TRUNK is None:
        _TRUNK = _detect_trunk()
    return _TRUNK


def invoke():
    """How to spell this script on the command line, for the hints it prints.

    Computed rather than hardcoded: the harness installs at
    tools/agent-ops-harness/shared/, but an adopter may put it anywhere.
    """
    try:
        rel = Path(__file__).resolve().relative_to(repo_root()).as_posix()
    except Exception:
        rel = "ship.py"
    return f"python {rel}"


def default_ttl():
    # Sessions are ephemeral and frequently die without releasing, so leases MUST
    # expire on their own.
    try:
        return float(cfg().get("claims_ttl_hours", 6))
    except (TypeError, ValueError):
        return 6.0


def extra_deploy_surfaces():
    """Deploy targets NOT expressed as a workflow `paths:` filter -- i.e. ones
    nobody in the repo can prove ran. [[glob, label], ...]

    Keep this EMPTY unless you truly have one. A phantom surface listed next to a
    real one is worse than silence: it double-counts, and stale entries teach
    sessions to ignore the whole report.
    """
    out = []
    for item in cfg().get("extra_deploy_surfaces") or []:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            out.append((item[0], item[1]))
    return out


# -- git helpers --------------------------------------------------------------


def git(*args, check=True, env=None, cwd=None):
    """Run git and return stdout. Never uses a shell (paths here contain spaces
    and non-ASCII characters)."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    proc = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=full_env,
        cwd=cwd or str(repo_root()),
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed ({proc.returncode}):\n{proc.stderr.strip()}"
        )
    return proc.stdout


def git_ok(*args):
    """True if the command succeeds, for boolean questions like --is-ancestor."""
    proc = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=str(repo_root()),
    )
    return proc.returncode == 0


_ROOT = None


def repo_root():
    global _ROOT
    if _ROOT is None:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if proc.returncode != 0:
            print("not inside a git repository", file=sys.stderr)
            sys.exit(1)
        _ROOT = Path(proc.stdout.strip())
    return _ROOT


def git_common_dir():
    """The SHARED .git directory. In a linked worktree, `--git-dir` points at
    .git/worktrees/<name> which is private to that worktree; `--git-common-dir`
    is the one all worktrees share. Claims must live in the shared one or an
    isolated worktree would never see the primary tree's claims."""
    out = git("rev-parse", "--git-common-dir").strip()
    p = Path(out)
    if not p.is_absolute():
        p = repo_root() / p
    return p.resolve()


def current_branch():
    return git("rev-parse", "--abbrev-ref", "HEAD").strip()


def rev(ref):
    try:
        return git("rev-parse", "--verify", "--quiet", ref, check=False).strip() or None
    except RuntimeError:
        return None


def fetch_trunk(quiet=True):
    remote, _, branch = trunk().partition("/")
    args = ["fetch", remote, branch]
    if quiet:
        args.insert(1, "--quiet")
    git(*args, check=False)


def ls_tree_paths(ref):
    out = git("ls-tree", "-r", "--name-only", "-z", ref)
    return {p for p in out.split("\0") if p}


def ls_tree_map(ref):
    """path -> blob sha, so `close` can tell identical content from divergent."""
    out = git("ls-tree", "-r", "-z", ref)
    m = {}
    for entry in out.split("\0"):
        if not entry:
            continue
        meta, _, path = entry.partition("\t")
        parts = meta.split(" ")
        if len(parts) == 3 and parts[1] == "blob":
            m[path] = parts[2]
    return m


def is_primary_worktree():
    """True in the shared working tree, False in a linked worktree.

    This matters more than it looks. One working tree has ONE HEAD, so every
    session attached to it is on the same branch simultaneously. Per-session
    branches are incoherent here: isolation can only come from a worktree.
    """
    gd = Path(git("rev-parse", "--absolute-git-dir").strip()).resolve()
    return gd == git_common_dir()


def on_trunk_branch():
    remote, _, name = trunk().partition("/")
    return current_branch() == name


# -- glob matching (GitHub Actions `paths:` semantics) ------------------------


def glob_to_regex(pattern):
    """Translate a GitHub Actions path filter into a regex.

    `**` crosses separators, `*` does not, `?` is one non-separator character.
    A pattern with no wildcard is an exact file match.
    """
    out = ["^"]
    i = 0
    n = len(pattern)
    while i < n:
        c = pattern[i]
        if c == "*":
            if pattern[i : i + 3] == "**/":
                out.append("(?:.*/)?")
                i += 3
                continue
            if pattern[i : i + 2] == "**":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
            i += 1
            continue
        if c == "?":
            out.append("[^/]")
            i += 1
            continue
        out.append(re.escape(c))
        i += 1
    out.append("$")
    return re.compile("".join(out))


def matches_any(path, patterns):
    return [p for p in patterns if glob_to_regex(p).match(path)]


# -- workflow parsing ---------------------------------------------------------

# PROMOTION MODE. The risk axis is not who owns the deploy, it is HOW production
# promotion happens:
#   forced           -- the provider CLI is invoked with a production flag from CI.
#                       It never consults the project's production-branch setting,
#                       so no dashboard config can divert the release into a
#                       preview. A green run means production changed.
#   branch-triggered -- the provider promotes only from ITS configured production
#                       branch. A green run means SOMETHING was built and says
#                       NOTHING about what is live.
# Only branch-triggered can be green-but-not-live. Observed in the source system:
# a site built every push as a PREVIEW for 20+ minutes while production 404'd, and
# the provider reported success the whole time.
#
# Detected from the workflow text, never declared, so it cannot drift.
FORCED_PROMOTION_RE = re.compile(r"(?:vercel|netlify)\b[^\n]*--prod")
PREVIEW_PROVIDER_RE = re.compile(r"vercel|netlify", re.I)


def load_workflows():
    """Parse .github/workflows/*.yml for trunk-push triggers and their path
    filters. Returns [{name, file, paths, paths_ignore, always, forced, vercel}].

    `always` = triggers on every trunk push regardless of path (no `paths:`
    filter), which is the dangerous case to surface.
    """
    wf_dir = repo_root() / ".github" / "workflows"
    results = []
    if not wf_dir.is_dir():
        return results

    try:
        import yaml
    except ImportError:
        print(
            "ship: pyyaml is required to read .github/workflows/ "
            "(pip install pyyaml). Treating deploy risk as UNKNOWN.",
            file=sys.stderr,
        )
        return [
            {
                "name": "(workflows unread: pyyaml missing)",
                "file": "*",
                "paths": [],
                "paths_ignore": [],
                "always": True,
                "forced": False,
                "vercel": False,
            }
        ]

    _, _, trunk_name = trunk().partition("/")
    for f in sorted(wf_dir.glob("*.yml")) + sorted(wf_dir.glob("*.yaml")):
        text = f.read_text(encoding="utf-8", errors="replace")
        try:
            doc = yaml.safe_load(text) or {}
        except Exception as exc:  # a malformed workflow must not break the gate
            results.append(
                {
                    "name": f.name,
                    "file": f.name,
                    "paths": [],
                    "paths_ignore": [],
                    "always": False,
                    "error": str(exc),
                }
            )
            continue

        # YAML 1.1 parses the bare key `on` as the boolean True. Handle both.
        on = doc.get("on", doc.get(True, {}))
        if not isinstance(on, dict):
            continue
        push = on.get("push")
        if not isinstance(push, dict):
            continue
        branches = push.get("branches") or []
        if isinstance(branches, str):
            branches = [branches]
        if branches and not any(
            b in (trunk_name, "main", "master", "**", "*") for b in branches
        ):
            continue

        paths = push.get("paths") or []
        if isinstance(paths, str):
            paths = [paths]
        paths_ignore = push.get("paths-ignore") or []
        if isinstance(paths_ignore, str):
            paths_ignore = [paths_ignore]

        results.append(
            {
                "name": doc.get("name") or f.name,
                "file": f.name,
                "paths": paths,
                "paths_ignore": paths_ignore,
                "always": not paths,
                "forced": bool(FORCED_PROMOTION_RE.search(text)),
                # Three cases, not two. A workflow that publishes to a database or
                # a bucket has no production alias at all, so calling it
                # "branch-triggered" would be a false accusation. Only a workflow
                # that invokes a preview-capable provider WITHOUT the production
                # flag is exposed to the silent-preview failure.
                "vercel": bool(PREVIEW_PROVIDER_RE.search(text)),
            }
        )
    return results


# -- blast --------------------------------------------------------------------


def compute_blast(paths):
    """Which deploy surfaces would a trunk push of `paths` actually trigger?"""
    hits = []
    for wf in load_workflows():
        if wf.get("error"):
            hits.append(
                {
                    "surface": f"{wf['file']} (UNPARSEABLE: {wf['error'][:80]})",
                    "why": ["could not read trigger; treat as DEPLOYS"],
                }
            )
            continue
        if wf["always"]:
            hits.append(
                {
                    "surface": f"{wf['name']} [{wf['file']}]",
                    "why": ["fires on EVERY trunk push (no paths: filter)"],
                    "forced": wf.get("forced", False),
                    "vercel": wf.get("vercel", False),
                }
            )
            continue
        why = []
        for p in paths:
            if wf["paths_ignore"] and matches_any(p, wf["paths_ignore"]):
                continue
            m = matches_any(p, wf["paths"])
            if m:
                why.append(f"{p}  ~  {m[0]}")
        if why:
            hits.append(
                {
                    "surface": f"{wf['name']} [{wf['file']}]",
                    "why": why,
                    "forced": wf.get("forced", False),
                    "vercel": wf.get("vercel", False),
                }
            )

    for pattern, label in extra_deploy_surfaces():
        why = [f"{p}  ~  {pattern}" for p in paths if glob_to_regex(pattern).match(p)]
        if why:
            hits.append(
                {"surface": label, "why": why, "webhook": True,
                 "forced": False, "vercel": True}
            )

    return hits


def staged_paths():
    out = git("diff", "--cached", "--name-only", "-z")
    return [p for p in out.split("\0") if p]


_HUNK_HDR_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _staged_hunk_map(base_tree, tree):
    """[(path, [line numbers])] for staged files carrying >1 hunk vs the base.

    Answers the question `--paths` silently skips: this commit is about to replace
    a whole file blob -- WHICH REGIONS of it is it actually changing? A count is not
    enough; the line numbers are what a session can match against the contested lines
    it just looked up.

    `-U0` so each changed region is its own hunk header. Tree-to-tree, so it never
    touches the working tree and costs nothing on a large commit. Single-hunk files
    are omitted on purpose -- they cannot mix two sessions' edits, and listing every
    file would bury the one that matters.
    """
    out = []
    for path in [p for p in git("diff", "--name-only", "-z", base_tree,
                                tree).split("\0") if p]:
        # Only files that already exist on the base can carry a foreign hunk; a
        # newly added file is entirely this session's by construction.
        if not git_ok("cat-file", "-e", f"{base_tree}:{path}"):
            continue
        d = git("diff", "-U0", "--ignore-cr-at-eol", base_tree, tree, "--", path,
                check=False)
        lines = [int(m.group(1)) for m in
                 (_HUNK_HDR_RE.match(l) for l in d.splitlines()) if m]
        if len(lines) > 1:
            out.append((path, lines))
    return out


def cmd_blast(args):
    if args.staged:
        paths = staged_paths()
        source = "staged files"
    elif args.range:
        out = git("diff", "--name-only", "-z", args.range)
        paths = [p for p in out.split("\0") if p]
        source = f"range {args.range}"
    else:
        paths = list(args.paths or [])
        source = "given paths"

    if not paths:
        print(f"SHIP blast: no paths ({source} is empty). Nothing to assess.")
        return 0

    hits = compute_blast(paths)
    print(f"SHIP blast  ({len(paths)} path(s) from {source})")
    if not hits:
        print("  verdict: INERT -- this push deploys NOTHING.")
        print(f"  -> push straight to {trunk()}. A branch would only defer the merge.")
        return 0

    forced = [h for h in hits if h.get("forced")]
    branchy = [h for h in hits if h.get("vercel") and not h.get("forced")]
    other = [h for h in hits if not h.get("vercel")]

    def show(group, tag):
        for h in group:
            print(f"    * {tag} {h['surface']}")
            for w in h["why"][:4]:
                print(f"        {' ' * len(tag)}{w}")
            if len(h["why"]) > 4:
                print(f"        {' ' * len(tag)}... and {len(h['why']) - 4} more")

    print("  verdict: DEPLOYS -- this push ships production:")
    show(forced, "[FORCED]  ")
    show(branchy, "[BRANCH!] ")
    show(other, "[JOB]     ")

    if forced:
        print("  [FORCED] runs the provider CLI with a production flag from CI. A forced")
        print("      promotion never consults the project's production-branch setting, so")
        print("      no dashboard config can divert it into a preview. Green == prod changed.")
    if branchy:
        print("  [BRANCH!] promotion is BRANCH-TRIGGERED. A green build means SOMETHING was")
        print("      built and says NOTHING about what is live: the provider promotes only")
        print("      from its configured production branch, and a mismatch silently ships a")
        print("      PREVIEW instead. Observed in the source system: every push built fine,")
        print("      the provider reported success, and production 404'd for 20+ minutes.")
        print("      A LIVE ASSERTION IS MANDATORY. Do not stop at the build being green:")
        print("        1. production alias      2. the git-branch alias      3. custom domain")
        print("      If they disagree, the deploy was never promoted. Then assert on")
        print("      something UNIQUE to your change (an asset hash, a new string) --")
        print("      a 200 on the homepage proves nothing.")
    if other:
        print("  [JOB] not a preview-capable provider (e.g. a database publish). No")
        print("      production alias, so no promotion step; green means the job ran.")
    print("  Pushed / built / promoted / live are FOUR states. See `ship verify`.")
    print(f"  -> ship to {trunk()} if flag-gated or verified; otherwise a SHORT-LIVED")
    print(f"     branch cut from {trunk()} (never from another branch) + a claim.")
    return 0


# -- claims (advisory path leases) --------------------------------------------


def claims_dir():
    d = git_common_dir() / "ship-claims"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_claims(include_expired=False):
    out = []
    now = time.time()
    for f in sorted(claims_dir().glob("*.json")):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        rec["_file"] = f
        rec["_expired"] = now > rec.get("expires", 0)
        if rec["_expired"] and not include_expired:
            continue
        out.append(rec)
    return out


def cmd_claim(args):
    cid = args.id or uuid.uuid4().hex[:8]
    now = time.time()
    ttl = args.ttl if args.ttl is not None else default_ttl()
    rec = {
        "id": cid,
        "globs": args.globs,
        "intent": args.label or "",
        "branch": current_branch(),
        "pid": os.getpid(),
        "created": now,
        "expires": now + ttl * 3600,
        "ttl_hours": ttl,
    }
    (claims_dir() / f"{cid}.json").write_text(
        json.dumps(rec, indent=1), encoding="utf-8"
    )

    conflicts = [
        c
        for c in load_claims()
        if c["id"] != cid and _globs_overlap(c["globs"], args.globs)
    ]
    print(f"SHIP claim {cid}: {', '.join(args.globs)}  (ttl {ttl}h)")
    if conflicts:
        print("  NOTE -- overlapping claims already held:")
        for c in conflicts:
            print(
                f"    {c['id']}  {', '.join(c['globs'])}  "
                f"[{c['branch']}] {c['intent']}  ({_age(c['created'])} old)"
            )
        print("  Claims are ADVISORY. Coordinate before editing the same paths.")
    print(f"  release with: {invoke()} release --id {cid}")
    return 0


def _globs_overlap(a, b):
    """Cheap, deliberately over-eager overlap test: shared literal prefix. A
    false positive costs one line of output; a false negative costs a silent
    collision, so bias toward reporting."""
    for x in a:
        for y in b:
            px = x.split("*")[0].rstrip("/")
            py = y.split("*")[0].rstrip("/")
            if not px or not py:
                return True
            if px.startswith(py) or py.startswith(px):
                return True
    return False


def _age(ts):
    secs = int(time.time() - ts)
    if secs < 3600:
        return f"{secs // 60}m"
    if secs < 86400:
        return f"{secs // 3600}h{(secs % 3600) // 60:02d}m"
    return f"{secs // 86400}d"


def cmd_claims(args):
    if args.clean:
        n = 0
        for c in load_claims(include_expired=True):
            if c["_expired"]:
                c["_file"].unlink(missing_ok=True)
                n += 1
        print(f"SHIP claims: purged {n} expired lease(s).")

    active = load_claims()
    if not active:
        print("SHIP claims: none held.")
        return 0
    print(f"SHIP claims: {len(active)} held")
    for c in active:
        left = int((c["expires"] - time.time()) / 60)
        print(
            f"  {c['id']}  {', '.join(c['globs'])}\n"
            f"        [{c['branch']}] {c['intent'] or '(no intent given)'}  "
            f"held {_age(c['created'])}, expires in {left}m"
        )
    return 0


def cmd_release(args):
    removed = []
    for c in load_claims(include_expired=True):
        if args.id and c["id"] == args.id:
            removed.append(c)
        elif args.globs and _globs_overlap(c["globs"], args.globs):
            removed.append(c)
    for c in removed:
        c["_file"].unlink(missing_ok=True)
    if not removed:
        print("SHIP release: nothing matched.")
        return 1
    for c in removed:
        print(f"SHIP release: dropped {c['id']} ({', '.join(c['globs'])})")
    return 0


# -- registry (path -> owner, read from the harness Project Registry) ---------


def registry_file():
    """The Project Registry `platform-ingest` already maintains. Ownership is NOT
    invented here -- it is read from the table that already has `Detection globs`
    and `Owner` columns, so there is only ever one source of truth for it."""
    env = os.environ.get("AGENT_OPS_CONFIG")
    candidates = [Path(env)] if env else []
    candidates += [repo_root() / name for name in CONFIG_NAMES]
    for c in candidates:
        try:
            if c.is_file():
                raw = json.loads(c.read_text(encoding="utf-8"))
                pr = raw.get("project_registry")
                if pr:
                    return pr
        except Exception:
            continue
    return "tools/agent-ops-harness/config/project-registry.md"


def load_registry():
    f = repo_root() / registry_file()
    if not f.is_file():
        return []
    rows = []
    in_table = False
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("| Project ") and "Detection globs" in line:
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                break
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 6 or set(cells[0]) <= set("-: "):
                continue
            globs = [
                g.strip().strip("`")
                for g in cells[2].split(",")
                if "`" in g or "/" in g
            ]
            rows.append(
                {
                    "project": cells[0],
                    "slug": cells[1].strip("`"),
                    "globs": [g for g in globs if g],
                    "tracker": cells[3],
                    "owner": cells[5],
                }
            )
    return rows


def owners_for(paths):
    reg = load_registry()
    found = {}
    for p in paths:
        for row in reg:
            if matches_any(p, row["globs"]):
                found.setdefault(
                    (row["project"], row["owner"], row["tracker"]), []
                ).append(p)
                break
    return found


# -- status -------------------------------------------------------------------


def cmd_status(args):
    if not args.no_fetch:
        fetch_trunk()

    branch = current_branch()
    trunk_sha = rev(trunk())
    print(f"SHIP status  branch={branch}")

    if not trunk_sha:
        print(f"  {trunk()} not found; cannot assess.")
        return 1

    ahead_behind = git(
        "rev-list", "--left-right", "--count", f"{trunk()}...HEAD"
    ).split()
    behind, ahead = ahead_behind[0], ahead_behind[1]
    print(f"  vs {trunk()}: {ahead} ahead, {behind} behind")

    on_tr = on_trunk_branch()
    primary = is_primary_worktree()
    print(f"  working tree: {'SHARED (primary)' if primary else 'isolated worktree'}")

    if primary and not on_tr:
        print("  VIOLATION -- the SHARED tree is on a feature branch.")
        print("    One tree has one HEAD, so EVERY session attached to it is on this")
        print("    branch right now. Unrelated workstreams will pile onto it and it")
        print(f"    will become a graveyard. The shared tree must live on {trunk()}.")
        print("    Isolation comes from a worktree, never from a branch:")
        print(f'      {invoke()} worktree <name> --claim "<glob>"')

    if not on_tr:
        mb = git("merge-base", trunk(), "HEAD").strip()
        mb_desc = git("log", "-1", "--format=%h %ad %s", "--date=short", mb).strip()
        print(f"  merge-base with trunk: {mb_desc}")

        # THE rule. Detect a branch cut from another branch rather than trunk: if
        # HEAD shares history with some other branch BEYOND its merge-base with
        # trunk, it inherited that branch's unlanded work as baggage. In the source
        # system this is what put a stale vendored library on an unrelated feature
        # branch and blocked it for days -- the session that got blocked had never
        # touched that file.
        suspects = []
        refs = [
            r.strip()
            for r in git(
                "for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes"
            ).splitlines()
            if r.strip()
        ]
        for r in refs:
            if r in (branch, trunk(), "origin", "origin/HEAD") or r.endswith("/" + branch):
                continue
            other_mb = git("merge-base", r, "HEAD", check=False).strip()
            if not other_mb or other_mb == mb:
                continue
            # other_mb is strictly newer than mb => shared post-trunk history
            if git_ok("merge-base", "--is-ancestor", mb, other_mb):
                suspects.append((r, other_mb))
        if suspects:
            print("  WARNING -- this branch was cut from another BRANCH, not trunk.")
            print("    It carries that branch's unlanded work as inherited baggage,")
            print("    which will surface later as a conflict you did not create.")
            for r, omb in suspects[:4]:
                d = git("log", "-1", "--format=%h %ad %s", "--date=short", omb).strip()
                print(f"      shares post-trunk history with {r} at {d}")
        else:
            print("  lineage: OK (forked from trunk)")

        only_branch, only_trunk = _orphan_sets()
        if only_branch or only_trunk:
            print(
                f"  orphans: {len(only_branch)} file(s) only here, "
                f"{len(only_trunk)} only on trunk"
            )
            if only_trunk:
                print("    a naive merge of this branch would DELETE the trunk-only files:")
                for p in sorted(only_trunk)[:5]:
                    print(f"      - {p}")

    active = load_claims()
    if active:
        print(f"  claims held by sessions: {len(active)}")
        for c in active:
            print(
                f"    {c['id']}  {', '.join(c['globs'])}  "
                f"[{c['branch']}] {c['intent']}  ({_age(c['created'])})"
            )
    else:
        print("  claims held by sessions: none")

    dirty = len([l for l in git("status", "--porcelain").splitlines() if l])
    if dirty > 50:
        print(
            f"  working tree: {dirty} dirty entries from parallel sessions. "
            "NEVER `git add -A`;"
        )
        print(f"    use `{invoke()} commit --paths ...` to ship scoped.")
    return 0


def _orphan_sets(branch_ref="HEAD"):
    b = ls_tree_paths(branch_ref)
    t = ls_tree_paths(trunk())
    return b - t, t - b


def cmd_orphans(args):
    if not args.no_fetch:
        fetch_trunk()
    ref = args.branch or "HEAD"
    only_branch, only_trunk = _orphan_sets(ref)
    print(f"SHIP orphans  {ref} vs {trunk()}")
    print(f"  only on {ref}: {len(only_branch)}")
    for p in sorted(only_branch):
        print(f"    + {p}")
    print(f"  only on {trunk()}: {len(only_trunk)}")
    for p in sorted(only_trunk):
        print(f"    - {p}   <-- merging {ref} as-is would DELETE this")
    if only_branch:
        own = owners_for(sorted(only_branch))
        if own:
            print("  owners (from the Project Registry):")
            for (proj, owner, tracker), ps in own.items():
                print(f"    {proj} -> {owner}  ({len(ps)} file(s))  tracker: {tracker}")
    return 0


# -- rules (the standard, readable from anywhere) ----------------------------


def cmd_rules(args):
    t = trunk()
    inv = invoke()
    print(f"""\
PARALLEL GIT STANDARD (the ship gate) -- the five rules

 0. YOU DO NOT NEED TO BE ON {t.split('/', 1)[1]} TO COMMIT TO IT.
      {inv} commit --paths <p>... -m "msg" --push
    lands on {t} from ANY checked-out branch, without switching, without
    touching the shared working tree. If your work is content-only (knowledge
    files, drafts, trackers, one-off scripts), this is almost always what you
    want. Do not let the checked-out branch decide where your work goes.

 1. The shared working tree lives on {t.split('/', 1)[1]}.
    One tree has ONE HEAD: every session attached to it is on the same branch at
    the same time, and a sibling can change it under you mid-session.

 2. Isolation comes from a WORKTREE, never from a branch.
      {inv} worktree <name> --claim "<glob>" -l "<intent>"
    cuts from a freshly fetched {t}. `git checkout -b` in the shared tree
    moves EVERY live session onto your branch.

 3. Deploy risk is COMPUTED, never remembered.
      {inv} blast --staged
    INERT -> push straight to trunk. DEPLOYS -> flag-gate it, or take a worktree.

 4. Never resolve a conflict in a file you do not own.
    Ship your own paths (`{inv} hunks <file>` then `commit --replay`);
    file the rest as a blocked row on the owner's tracker via /platform-ingest.

Never `git add -A`. Never checkout/merge/rebase in the shared tree.
Never cut a branch from another branch -- always from {t}.
Full standard: shared/parallel-git.md
""")
    return 0


# -- untracked real content ---------------------------------------------------

# Directories whose untracked files are working noise, not content at risk.
# Extend via config `git.untracked_noise`.
DEFAULT_UNTRACKED_NOISE = (
    "node_modules/",
    ".venv/",
    "venv/",
    "__pycache__/",
    "dist/",
    "build/",
    ".next/",
    ".cache/",
    ".deploy/",
)


def untracked_noise():
    return tuple(DEFAULT_UNTRACKED_NOISE) + tuple(cfg().get("untracked_noise") or [])


# Hand-authored content. Untracked binaries are nearly always scratch (candidate
# images, downloads), and burying the 20 files that matter under 800 that do not
# is how a report gets ignored. `--all` bypasses this.
CONTENT_EXTS = {
    ".md", ".py", ".json", ".js", ".ts", ".tsx", ".jsx", ".css", ".html",
    ".yml", ".yaml", ".sql", ".sh", ".txt", ".toml", ".glsl",
}


def cmd_untracked(args):
    """Find real content that exists ONLY in the shared working tree.

    A file nobody has ever committed is one `git clean` or one bad checkout from
    gone. These are ADDITIONS, not contested files: landing them is safe, and the
    risk is in NOT landing them.
    """
    if not args.no_fetch:
        fetch_trunk()
    out = git("ls-files", "--others", "--exclude-standard", "-z")
    paths = [p for p in out.split("\0") if p]
    root = repo_root()

    # CRITICAL: `git ls-files --others` reports a file as untracked when it is
    # merely absent from the CURRENT branch's index. On a branch that lags trunk,
    # that wrongly flags committed trunk files as "never committed". Those are a
    # different problem (a stale branch), and claiming otherwise would be a lie in
    # the one report whose whole purpose is telling you what is at risk of loss.
    on_tr = ls_tree_paths(trunk())

    keep = []
    noise = untracked_noise()
    for p in paths:
        if p in on_tr:
            continue
        if any(p.startswith(n) or f"/{n}" in p for n in noise):
            continue
        if not args.all and Path(p).suffix.lower() not in CONTENT_EXTS:
            continue
        try:
            size = (root / p).stat().st_size
        except OSError:
            continue
        if size < args.min_bytes:
            continue
        keep.append((p, size))

    if not keep:
        print("SHIP untracked: no substantial uncommitted content found.")
        return 0

    print(
        f"SHIP untracked: {len(keep)} file(s) exist ONLY in the shared working tree.\n"
        "  Nobody has ever committed these. They are additions, not contested files:\n"
        "  landing them is safe, and the risk is in leaving them."
    )
    groups = {}
    for p, size in sorted(keep):
        key = ("(unrouted)", "main")
        for row in load_registry():
            if matches_any(p, row["globs"]):
                key = (row["project"], row["owner"])
                break
        groups.setdefault(key, []).append((p, size))

    for (proj, owner), items in sorted(groups.items()):
        ps = [p for p, _ in items]
        hits = compute_blast(ps)
        print(
            f"\n  {proj}  (owner: {owner})  {len(items)} file(s)  "
            f"[{'DEPLOYS' if hits else 'INERT'}]"
        )
        for p, size in items[:8]:
            print(f"      {p}  ({size // 1024}k)" if size >= 1024 else f"      {p}")
        if len(items) > 8:
            print(f"      ... and {len(items) - 8} more")
        print(
            f'      -> {invoke()} commit --paths {" ".join(ps[:3])}'
            f'{" ..." if len(ps) > 3 else ""} -m "..." --push'
        )
    return 0


# -- contested (tracked files carrying foreign hunks) ------------------------


def cmd_contested(args):
    """Tracked files whose working-tree diff vs trunk is bigger than one session's
    work, i.e. they carry other sessions' unfinished edits mixed with yours.

    `git add -p` is unavailable non-interactively, so hunk-splitting by hand is
    not an option. The defined move is in the output.
    """
    out = git("diff", "--numstat", "-z", trunk(), "--")
    entries = [e for e in out.split("\0") if e]

    # `git diff <trunk> --` is commit -> index/worktree, and the INDEX decides what
    # counts as tracked. On a branch behind trunk, every file trunk gained since is
    # absent from the index and reports as a whole-file DELETION -- churn equal to
    # its length, with a confident owner attached. Measured in the source system: a
    # file listed at "173 changed lines" while byte-identical to trunk. Counted and
    # reported, never silently cut.
    tracked = {p for p in git("ls-files", "-z").split("\0") if p}

    rows, stale = [], []
    for e in entries:
        parts = e.split("\t")
        if len(parts) < 3:
            continue
        add, dele, path = parts[0], parts[1], parts[2]
        if add == "-" or dele == "-":
            continue
        churn = int(add) + int(dele)
        (rows if path in tracked else stale).append((churn, path))
    rows = [r for r in rows if r[0] >= args.min_lines]
    stale = [r for r in stale if r[0] >= args.min_lines]
    rows.sort(reverse=True)

    def _stale_note():
        if not stale:
            return
        print(
            f"\n  ({len(stale)} path(s) skipped: on {trunk()} but absent from this "
            f"branch's index.\n   A stale local branch, not contested work -- the "
            f"content is already on trunk.\n   Run `git fetch` / see `ship status` "
            f"for the divergence.)"
        )

    if not rows:
        print("SHIP contested: no tracked file differs from trunk by that much.")
        _stale_note()
        return 0

    print(
        f"SHIP contested: {len(rows)} tracked file(s) differ from trunk by "
        f">= {args.min_lines} changed lines."
    )
    print("  Some of that is probably another session's unfinished work.\n")
    for churn, path in rows[: args.limit]:
        owner = "(unrouted)"
        for row in load_registry():
            if matches_any(path, row["globs"]):
                owner = row["owner"]
                break
        print(f"  {path}   ({churn} changed lines, owner: {owner})")
    if len(rows) > args.limit:
        print(f"  ... and {len(rows) - args.limit} more")
    _stale_note()

    print(
        "\n  THE DEFINED MOVE (`git add -p` needs a TTY, but --replay does not):\n"
        "   1. Land ONLY your own hunks. This is the correct default:\n"
        f"        {invoke()} hunks <file>\n"
        f"        {invoke()} commit --replay <file> --hunks 2,3 -m \"...\" --push\n"
        "      Unselected regions are taken verbatim from trunk, so the other\n"
        "      sessions' work is neither committed nor destroyed.\n"
        "   2. If you cannot tell which hunks are yours, do NOT commit the file.\n"
        "      Flag it in your run summary and leave it for the owning session.\n"
        "   3. Only commit wholesale on EXPLICIT human authorisation, and when you\n"
        "      do, say so in the commit message: name the foreign content you are\n"
        "      sweeping and who authorised it. If your sessions share one commit\n"
        "      identity, the message is the ONLY attribution channel that exists."
    )
    return 0


# -- worktree (the ONLY correct way to get isolation here) -------------------


def cmd_worktree(args):
    """Create an isolated worktree cut from a freshly fetched trunk.

    This is the enforcement of the one hard rule. `git checkout -b` in the shared
    tree does not give a session its own branch: it moves EVERY session attached
    to that tree onto the new branch. And `git worktree add` defaulting to HEAD
    would fork off whatever branch the tree happens to be on, inheriting its
    unlanded work. Both failures become unreachable by always cutting from a
    just-fetched trunk, explicitly.
    """
    fetch_trunk(quiet=False)
    base = rev(trunk())
    if not base:
        print(f"SHIP worktree: {trunk()} not found.", file=sys.stderr)
        return 2

    name = args.name
    branch = args.branch or f"wt/{name}"
    path = Path(args.path) if args.path else Path(
        os.environ.get("TEMP") or os.environ.get("TMPDIR") or "/tmp"
    ) / f"wt-{name}"

    if path.exists():
        print(f"SHIP worktree: {path} already exists.", file=sys.stderr)
        return 2

    out = git("worktree", "add", "-b", branch, str(path), base, check=False)
    print(out.rstrip())
    print(f"SHIP worktree: {branch} at {path}")
    print(f"  cut from {trunk()} @ {base[:9]} (NOT from the shared tree's HEAD)")
    print("  the shared working tree is untouched; other sessions are unaffected.")
    if args.claim:
        print()
        sub = argparse.Namespace(
            globs=args.claim, label=args.label or name, ttl=default_ttl(), id=None
        )
        cmd_claim(sub)
    print()
    print(f"  when done:  {invoke()} close --branch {branch}")
    return 0


# -- close (the missing lifecycle verb) --------------------------------------


def cmd_close(args):
    """Tell a session how to END a branch, instead of leaving it to rot.

    If nothing in a repo ever opens, ages or closes a branch, branches become
    graveyards. This splits a branch into the three things it can actually
    contain and proposes the exact commands for each. It never executes.
    """
    if not args.no_fetch:
        fetch_trunk()
    ref = args.branch or "HEAD"
    if not rev(ref):
        print(f"SHIP close: ref {ref} not found.", file=sys.stderr)
        return 2

    b = ls_tree_map(ref)
    t = ls_tree_map(trunk())

    only_branch = sorted(set(b) - set(t))
    only_trunk = sorted(set(t) - set(b))
    shared = set(b) & set(t)
    divergent = sorted(p for p in shared if b[p] != t[p])
    identical = len(shared) - len(divergent)

    mb = git("merge-base", trunk(), ref).strip()
    mb_date = git("log", "-1", "--format=%ad", "--date=short", mb).strip()
    ahead = git("rev-list", "--count", f"{trunk()}..{ref}").strip()

    print(f"SHIP close  {ref}  ({ahead} commits ahead, forked {mb_date})")
    print(f"  already identical to trunk: {identical} file(s) -- nothing to do")
    print(f"  only on this branch:        {len(only_branch)} file(s)")
    print(f"  divergent on both:          {len(divergent)} file(s)")
    print(f"  only on trunk:              {len(only_trunk)} file(s)")

    if only_trunk:
        print()
        print("  DANGER -- a plain merge of this branch would DELETE these:")
        for p in only_trunk:
            print(f"    - {p}")
        print("    Never `git merge` this branch. Land it path-scoped instead.")

    if only_branch:
        print()
        print("  LANDABLE (additions; no trunk content is at risk):")
        groups = {}
        for p in only_branch:
            key = ("(unrouted)", "main", "")
            for row in load_registry():
                if matches_any(p, row["globs"]):
                    key = (row["project"], row["owner"], row["tracker"])
                    break
            groups.setdefault(key, []).append(p)
        for (proj, owner, _tracker), ps in sorted(groups.items()):
            hits = compute_blast(ps)
            verdict = "DEPLOYS" if hits else "INERT"
            print(f"    {proj}  (owner: {owner})  {len(ps)} file(s)  [{verdict}]")
            for p in ps[:3]:
                print(f"        {p}")
            if len(ps) > 3:
                print(f"        ... and {len(ps) - 3} more")
            sample = " ".join(ps[:3]) + (" ..." if len(ps) > 3 else "")
            print(
                f"      -> {invoke()} commit --from {ref} "
                f'--paths {sample} -m "..." --push'
            )

    if divergent:
        print()
        print("  CONTESTED (exists on both, content differs -- do NOT resolve if")
        print("  you do not own it; file a blocked row on the owner's tracker):")
        for p in divergent[:20]:
            owner = "(unrouted)"
            tracker = ""
            for row in load_registry():
                if matches_any(p, row["globs"]):
                    owner, tracker = row["owner"], row["tracker"]
                    break
            bl = len(git("show", f"{ref}:{p}", check=False).splitlines())
            tl = len(git("show", f"{trunk()}:{p}", check=False).splitlines())
            print(f"    {p}")
            print(f"        branch {bl} lines vs trunk {tl} lines   owner: {owner}")
            if tracker:
                print(f"        tracker: {tracker}")
        if len(divergent) > 20:
            print(f"    ... and {len(divergent) - 20} more")

    print()
    if not only_branch and not divergent:
        print("  This branch carries nothing trunk lacks. Safe to delete:")
        print(f"    git branch -D {ref}    (and `git push origin --delete {ref}`)")
    else:
        print("  Land the LANDABLE groups above, hand the CONTESTED ones to their")
        print("  owners via /platform-ingest, then delete the branch. Do not merge it.")
    return 0


# -- commit (path-scoped, plumbing, never touches the working tree) -----------


def cmd_commit(args):
    if getattr(args, "message_file", None):
        mf = Path(args.message_file)
        if not mf.is_file():
            raise RuntimeError(f"--message-file not found: {args.message_file}")
        args.message = mf.read_text(encoding="utf-8")
        if not args.message.strip():
            raise RuntimeError(f"--message-file is empty: {args.message_file}")

    onto = args.onto or trunk()

    paths = list(args.paths or [])
    if args.rm and not paths and not args.paths_from:
        paths = []          # removal-only commit is legitimate
    if args.paths_from:
        # Rescue commits run to 100+ scattered paths, which is past what a Windows
        # command line comfortably takes.
        paths += [
            l.strip()
            for l in Path(args.paths_from).read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")
        ]
    if args.replay and not paths:
        paths = [args.replay]
    if args.content and not paths:
        paths = [c.partition("=")[0] for c in args.content]
    if not paths and not args.rm:
        print("SHIP commit: --paths, --paths-from or --rm is required.", file=sys.stderr)
        return 2

    fetch_trunk(quiet=False)
    base = rev(onto)
    if not base:
        print(f"SHIP commit: base ref {onto} not found.", file=sys.stderr)
        return 2

    root = repo_root()
    tmp_index = git_common_dir() / f"ship-index-{uuid.uuid4().hex[:8]}"
    env = {"GIT_INDEX_FILE": str(tmp_index)}

    try:
        # Start from the base tree, NOT from the shared index. This is the whole
        # point: the shared index belongs to other sessions.
        git("read-tree", base, env=env)

        if args.from_ref and args.merge3:
            # Branch-ahead reconciliation. Taking the branch version wholesale would
            # REVERT whatever trunk gained since the fork; taking trunk's would drop
            # the branch's work. A real 3-way merge (base = merge-base) is what git
            # would compute anyway, and it is mechanical rather than a judgment call,
            # so it is safe to automate. Conflicts are NOT auto-resolved: a
            # conflicted file is skipped and reported, because resolving someone
            # else's overlap is exactly what the standard forbids.
            src = rev(args.from_ref)
            base_ref = git("merge-base", onto, args.from_ref).strip()
            merged, conflicted, skipped = [], [], []
            import tempfile

            def blob_bytes(ref, path):
                """Raw bytes, NOT text. subprocess(text=True) applies universal-newline
                translation, which silently rewrites CRLF to LF and makes every line of
                a CRLF file look changed. Merging must be byte-exact."""
                pr = subprocess.run(
                    ["git", "show", f"{ref}:{path}"],
                    capture_output=True, cwd=str(root),
                )
                return pr.stdout if pr.returncode == 0 else None

            for p in paths:
                ours = blob_bytes(src, p)
                theirs = blob_bytes(onto, p)
                common = blob_bytes(base_ref, p)
                if ours is None:
                    skipped.append(p)
                    continue
                if theirs is None:                   # trunk lacks it: plain addition
                    content = ours
                else:
                    tmpd = Path(tempfile.mkdtemp())
                    fo, fb, ft = tmpd / "o", tmpd / "b", tmpd / "t"
                    fo.write_bytes(ours)
                    fb.write_bytes(common if common is not None else b"")
                    ft.write_bytes(theirs)
                    pr = subprocess.run(
                        ["git", "merge-file", "--stdout", "-L", "branch",
                         "-L", "base", "-L", "trunk", str(fo), str(fb), str(ft)],
                        capture_output=True,
                    )
                    if pr.returncode != 0:
                        conflicted.append(p)
                        continue
                    content = pr.stdout
                blob = subprocess.run(
                    ["git", "hash-object", "-w", "--stdin"],
                    input=content, capture_output=True, cwd=str(root),
                ).stdout.decode().strip()
                git("update-index", "--add", "--cacheinfo",
                    f"100644,{blob},{p}", env=env)
                merged.append(p)

            print(f"  3-way merged: {len(merged)}  conflicted(skipped): {len(conflicted)}"
                  f"  absent-on-branch(skipped): {len(skipped)}")
            for p in conflicted:
                print(f"    CONFLICT, left for its owner: {p}")
            for p in skipped:
                print(f"    not on {args.from_ref}: {p}")
            if not merged:
                print("SHIP commit: nothing merged cleanly.", file=sys.stderr)
                return 2
        elif args.from_ref:
            # Take content from a ref (reconciling a branch's files onto trunk)
            # rather than from the working tree.
            src = rev(args.from_ref)
            if not src:
                print(f"SHIP commit: --from ref {args.from_ref} not found.", file=sys.stderr)
                return 2
            added = 0
            for p in paths:
                listing = git("ls-tree", "-r", "-z", src, "--", p, check=False)
                for entry in listing.split("\0"):
                    if not entry:
                        continue
                    meta, _, fpath = entry.partition("\t")
                    mode, _, rest = meta.partition(" ")
                    otype, _, sha = rest.partition(" ")
                    if otype != "blob":
                        continue
                    git(
                        "update-index", "--add", "--cacheinfo",
                        f"{mode},{sha},{fpath}", env=env,
                    )
                    added += 1
            if not added:
                print(
                    f"SHIP commit: no blobs matched {paths} in {args.from_ref}.",
                    file=sys.stderr,
                )
                return 2
        elif args.content:
            # COMMIT EXACT CONTENT FOR A PATH, from a file prepared outside the
            # working tree. The case that forces this: trunk moves while your edits
            # are being made, so your working-tree copy is based on a stale version
            # AND still carries a third session's hunk. Committing it would revert
            # the sibling's work; --replay cannot split it because the staleness
            # merges everything into one enormous hunk.
            #
            # The fix is to rebase YOUR edits onto trunk's CURRENT version in a
            # scratch file and commit that. The working tree is left completely
            # untouched, so the other session's hunk survives.
            for spec in args.content:
                if "=" not in spec:
                    print(f"SHIP commit: --content needs repopath=localfile, got {spec}",
                          file=sys.stderr)
                    return 2
                repopath, _, local = spec.partition("=")
                src = Path(local)
                if not src.is_file():
                    print(f"SHIP commit: no such file: {local}", file=sys.stderr)
                    return 2
                blob = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                                      input=src.read_bytes(), capture_output=True,
                                      cwd=str(root)).stdout.decode().strip()
                git("update-index", "--add", "--cacheinfo",
                    f"100644,{blob},{repopath}", env=env)
                print(f"  content for {repopath} taken from {local} "
                      "(working tree untouched)")
            for p in [x for x in paths if x not in
                      {s.partition('=')[0] for s in args.content}]:
                git("add", "-A", "--", p, env=env)
        elif args.replay:
            # THE CONTESTED-FILE PATH. Build trunk's version plus only the hunks the
            # session says are its own, so the other sessions' uncommitted edits are
            # neither committed nor destroyed. This is the "re-apply your own edit on
            # trunk's version" rule, made reachable headlessly.
            if not args.hunks:
                print(f"SHIP commit: --replay needs --hunks (see `{invoke()} hunks <file>`).",
                      file=sys.stderr)
                return 2
            content = _replay_blob(args.replay, args.hunks, onto)
            blob = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                                  input=content, capture_output=True,
                                  cwd=str(root)).stdout.decode().strip()
            git("update-index", "--add", "--cacheinfo",
                f"100644,{blob},{args.replay}", env=env)
            print(f"  replayed hunks {args.hunks} of {args.replay} onto {onto}'s "
                  "version (the working tree is untouched)")
            for p in [x for x in paths if x != args.replay]:
                git("add", "-A", "--", p, env=env)
        else:
            # Content from the working tree. `-A` is SCOPED to the given paths,
            # so deletions register but nothing outside the scope is touched.
            #
            # TRAP: a DIRECTORY given here silently includes everything beneath it.
            # That is how a live API key once reached a remote while the commit
            # message claimed to exclude it. Name files, and READ the --dry-run list.
            for p in paths:
                if not (root / p).exists() and not git(
                    "ls-files", "--", p, check=False
                ).strip():
                    print(f"SHIP commit: path not found and not tracked: {p}", file=sys.stderr)
                    return 2
                git("add", "-A", "--", p, env=env)

        # Un-shipping. A gate that can only add is half a gate: the first thing it
        # took to land a file it should not have was a way to take it back, and
        # `git rm` needs the working tree, which is exactly what we must not touch.
        for p in args.rm or []:
            listing = git("ls-tree", "-r", "-z", base, "--", p, check=False)
            removed = 0
            for entry in listing.split("\0"):
                if not entry:
                    continue
                _, _, fpath = entry.partition("\t")
                git("update-index", "--force-remove", "--", fpath, env=env)
                removed += 1
            if not removed:
                print(f"SHIP commit: --rm path not on {onto}: {p}", file=sys.stderr)
                return 2

        tree = git("write-tree", env=env).strip()

        base_tree = git("rev-parse", f"{base}^{{tree}}").strip()
        if tree == base_tree:
            print("SHIP commit: nothing to do -- tree is identical to the base.")
            return 0

        # --- THE SECRET GATE: the one place this tool blocks --------------------
        # Everything else here informs and never blocks, because a blocked
        # unattended session with no human present just learns to work around it.
        # This is the exception, and the exception is principled: the failure is
        # IRREVERSIBLE. Git history is permanent, rewriting it across live parallel
        # sessions is worse than the leak, and the only remedy left afterwards is
        # rotating the credential. In the source system a live API key reached the
        # remote because a directory-level --paths swept in a file the commit
        # message claimed to exclude. The documented countermeasure was "read the
        # dry-run list" -- a convention, and it failed the first time it was tested.
        # This converts it into a gate.
        changed_now = [p for p in git("diff", "--name-only", "-z", base_tree,
                                      tree).split("\0") if p]
        leaks = scan_tree_for_secrets(tree, only_paths=changed_now)
        if leaks:
            print(f"\nSHIP commit: BLOCKED -- {len(leaks)} possible secret(s) in the "
                  f"staged tree:", file=sys.stderr)
            for path, what in leaks:
                print(f"    {path}  ({what})", file=sys.stderr)
            print(
                "\n  Nothing was committed or pushed. History is permanent: if this "
                "reaches\n  the remote the only remedy left is rotating the credential.\n"
                "  Move the value into a gitignored env file and read it from there,\n"
                "  then retry.\n"
                "  If this is genuinely a false positive, re-run with "
                "--i-verified-no-secrets\n  and say in the commit message WHAT you "
                "checked and how.",
                file=sys.stderr,
            )
            if not args.i_verified_no_secrets:
                return 3
            print("  OVERRIDDEN by --i-verified-no-secrets; proceeding.", file=sys.stderr)

        diff = git("diff", "--stat", base_tree, tree)
        names = [
            p for p in git("diff", "--name-only", "-z", base_tree, tree).split("\0") if p
        ]

        print(f"SHIP commit  base={onto} ({base[:9]})  files={len(names)}")
        print(diff.rstrip())

        hits = compute_blast(names)
        if hits:
            print("  blast: DEPLOYS --")
            for h in hits:
                print(f"    * {h['surface']}")
        else:
            print("  blast: INERT (deploys nothing)")

        # --- HUNK DISCLOSURE --------------------------------------------------
        # The contested-file guard answers "which LINES are contested". `--paths`
        # stages the whole BLOB. Nothing bridged the two, so a session that had
        # correctly identified three lines of a shared tracker as a sibling's, and
        # said so in its own commit message, shipped all three anyway.
        #
        # Deliberately a DISCLOSURE, not a refusal. Two rejected alternatives:
        # requiring --hunks for every modified tracked file is friction on the
        # commonest operation and becomes reflexive; gating on "hot file" measured by
        # commit frequency does not discriminate (measured on the source repo: the
        # contested tracker 32 commits/14d, but two files edited only ever by one
        # session at a time scored 13 and 11 -- any threshold low enough to catch the
        # real case fires on solo work, which is the alarm fatigue this gate has
        # already paid for twice). The information was ALWAYS computable and simply
        # never shown; showing the LINE NUMBERS rather than a count is the whole fix,
        # because a session that just enumerated those lines cannot miss them here.
        #
        # Skipped for --replay/--content/--from: there the staged blob deliberately
        # is not the working-tree file, and the session has already claimed hunks.
        if not (args.replay or args.content or args.from_ref):
            multi = _staged_hunk_map(base_tree, tree)
            if multi:
                print("  hunk check -- these files were staged WHOLESALE and carry "
                      "more than one hunk:")
                for path, lines in multi:
                    shown = ", ".join(str(n) for n in lines[:12])
                    more = f" (+{len(lines) - 12} more)" if len(lines) > 12 else ""
                    print(f"    {path}   {len(lines)} hunks at line {shown}{more}")
                print("    If ANY hunk there is not yours, this commit sweeps in another")
                print("    session's work. Claim only your own instead:")
                print(f"      {invoke()} commit --replay {multi[0][0]} "
                      f"--hunks <n,...> -m \"...\" --push")

        overlapping = [c for c in load_claims() if _globs_overlap(c["globs"], names)]
        if overlapping:
            print("  NOTE -- these paths overlap live claims:")
            for c in overlapping:
                print(f"    {c['id']} [{c['branch']}] {c['intent']} ({_age(c['created'])})")

        if args.dry_run:
            print("  (dry run -- nothing committed or pushed)")
            return 0

        # Identity. If the adopter pinned one in config (some deploy providers
        # attribute builds by commit email), force it; otherwise let git use the
        # repo's own configured identity.
        gate_email = cfg().get("commit_email")
        gate_name = cfg().get("commit_name")
        ident = {}
        if not gate_email and not git("config", "--get", "user.email", check=False).strip():
            # Without this, git fails with a raw "unable to auto-detect email
            # address" from deep inside commit-tree, which reads like a bug in the
            # gate rather than a one-line fix in the adopter's repo.
            print(
                "SHIP commit: no commit identity. Either set one in git\n"
                '    git config user.email "you@example.com"\n'
                '    git config user.name  "Your Name"\n'
                "  or pin one for every session in agent-ops-harness.config.json:\n"
                '    "git": { "commit_email": "you@example.com", "commit_name": "Your Name" }\n'
                "  Nothing was committed.",
                file=sys.stderr,
            )
            return 2
        if gate_email:
            cfg_email = git("config", "--get", "user.email", check=False).strip()
            if cfg_email and cfg_email != gate_email:
                print(
                    f"  WARNING: user.email is {cfg_email}, config requires {gate_email}. "
                    "Forcing the configured identity on this commit."
                )
            ident = {
                "GIT_AUTHOR_EMAIL": gate_email,
                "GIT_COMMITTER_EMAIL": gate_email,
            }
            if gate_name:
                ident["GIT_AUTHOR_NAME"] = gate_name
                ident["GIT_COMMITTER_NAME"] = gate_name

        commit = git(
            "commit-tree", tree, "-p", base, "-m", args.message, env={**env, **ident}
        ).strip()
        print(f"  commit-tree -> {commit}")

        if args.push:
            remote, _, target = onto.partition("/")
            # A push here is racing every other live session. If one of them lands
            # a commit between our fetch and our push, this is a non-fast-forward
            # and git REJECTS it.
            #
            # This block must NEVER print success unconditionally: a rejected push
            # writes to stderr and leaves stdout empty. In the source system a
            # check=False version of this silently threw away a 292-file commit and
            # reported success; it was found hours later, by accident. A tool whose
            # whole purpose is safe shipping must never report a push it did not make.
            #
            # Rebuilding on the new tip is the correct response, not an error: the
            # commit is path-scoped and parent-independent by construction, which is
            # the entire point of the design. So retry, re-parented, and only give
            # up loudly.
            for attempt in range(1, 4):
                proc = subprocess.run(
                    ["git", "push", remote, f"{commit}:{target}"],
                    capture_output=True, text=True, encoding="utf-8",
                    errors="replace", cwd=str(root),
                )
                if proc.returncode == 0:
                    # INDEPENDENT ASSERTION AGAINST THE REMOTE. A zero exit code is
                    # the tool's own account of itself, and this tool has lied
                    # before. Ask the REMOTE what it has, and refuse to claim
                    # success otherwise. `git ls-remote` uses the same transport the
                    # push just used, so it needs no extra auth or CLI.
                    ls = git("ls-remote", remote, f"refs/heads/{target}", check=False)
                    remote_sha = ls.split()[0] if ls.split() else ""
                    if remote_sha == commit:
                        # Name the RUNG. "VERIFIED" alone invites exactly the
                        # conflation this costs the most: pushed / built / promoted
                        # / live are four states and this proves only the first.
                        print(f"  pushed {commit[:9]} -> {remote}/{target}  "
                              f"(rung 1/5 VERIFIED: the remote ref holds this sha)")
                        if compute_blast(names):
                            print("  NOT verified: built, promoted, or live. This push "
                                  f"deploys -- run `{invoke()} verify` next.")
                        break
                    print(
                        f"SHIP commit: push exited 0 but {remote}/{target} is at "
                        f"{remote_sha[:9] or '(unknown)'}, not {commit[:9]}.",
                        file=sys.stderr,
                    )
                    if not remote_sha:
                        print("  could not read the remote ref; treat this push as "
                              "UNPROVEN and check manually.", file=sys.stderr)
                        return 1
                    # The remote moved on: a sibling landed between our push and
                    # this read. Our commit may still be an ancestor -- that is a
                    # success, just not the tip.
                    if git_ok("merge-base", "--is-ancestor", commit, remote_sha):
                        print(f"  {commit[:9]} IS an ancestor of {remote_sha[:9]} -- "
                              "landed, a sibling pushed on top. VERIFIED.")
                        break
                    print("  and it is NOT an ancestor of the remote tip: this "
                          "commit did NOT land.", file=sys.stderr)
                    return 1
                print(f"  push REJECTED (attempt {attempt}/3): {remote}/{target} moved "
                      "under us. Re-parenting on the new tip and retrying.")
                git("fetch", "--quiet", remote, target, check=False)
                new_base = rev(onto)
                if not new_base or new_base == base:
                    print("SHIP commit: push failed and the base did not move.",
                          file=sys.stderr)
                    print(proc.stderr.strip()[:500], file=sys.stderr)
                    return 1
                # Re-apply this commit's tree changes onto the new tip.
                changed = [p for p in git("diff", "--name-only", "-z",
                                          base_tree, tree).split("\0") if p]
                git("read-tree", new_base, env=env)
                for p in changed:
                    entry = git("ls-tree", "-z", tree, "--", p, check=False)
                    if entry.strip():
                        meta, _, fpath = entry.split("\0")[0].partition("\t")
                        mode, _, restp = meta.partition(" ")
                        _otype, _, sha = restp.partition(" ")
                        git("update-index", "--add", "--cacheinfo",
                            f"{mode},{sha},{fpath}", env=env)
                    else:
                        git("update-index", "--force-remove", "--", p, env=env)
                tree = git("write-tree", env=env).strip()
                base = new_base
                base_tree = git("rev-parse", f"{new_base}^{{tree}}").strip()
                commit = git("commit-tree", tree, "-p", base, "-m", args.message,
                             env={**env, **ident}).strip()
                print(f"  re-parented -> {commit[:9]}")
            else:
                print("SHIP commit: push rejected 3 times; NOT pushed.", file=sys.stderr)
                return 1
            print(
                "  NOTE: your working tree and branch are UNCHANGED by design. "
                f"Run `git fetch {remote}` to see it."
            )
        else:
            remote, _, target = onto.partition("/")
            print(f"  not pushed. To ship: git push {remote} {commit}:{target}")
        return 0
    finally:
        try:
            tmp_index.unlink(missing_ok=True)
        except Exception:
            pass


# -- hunks + replay: the missing non-interactive `git add -p` ------------------
#
# "Re-apply your own edit on trunk's version" is the CORRECT DEFAULT for a
# contested file, and without this it is unreachable: --paths stages from the
# working tree (so it always carries the foreign hunks) and --from takes whole
# paths from a ref (so it cannot take a synthesized blob). Doing it by hand means
# checking trunk's version over the working file, which DESTROYS the other
# sessions' uncommitted edits -- precisely what the rule exists to prevent. So
# every session falls through to "do not commit" and edits pile up on disk.
#
# `git add -p` would solve it and needs a TTY no unattended session has. This is
# that, headless.


def _hunk_groups(path, base_ref=None):
    """(base_lines, work_lines, groups) for a contested file.

    Pure difflib, deliberately: an earlier version generated a unified diff and fed
    selected hunks to `git apply`, which failed on path prefixing and context
    matching. Reconstructing in-process removes the patch round-trip entirely and
    GUARANTEES that hunk N in `ship hunks` is hunk N in `--replay`.

    Lines are BYTES, so non-UTF8 content survives untouched.

    Line endings are normalised FOR THE COMPARISON ONLY. git normalises endings on
    commit, so a trunk blob here is LF while a Windows working copy is CRLF, and
    comparing raw bytes then makes EVERY line differ. Measured: one 3953-line hunk
    reported for a file `git diff --numstat` called identical. That is not merely
    noisy -- `--replay --hunks 1` on it would have written the working copy's
    endings into the blob, landing a whole-file line-ending rewrite on a contested
    file, produced by the one tool that exists to prevent sweeping.
    """
    import difflib

    base_ref = base_ref or trunk()
    root = repo_root()
    work = root / path
    if not work.is_file():
        raise RuntimeError(f"not a file in the working tree: {path}")
    blob = subprocess.run(["git", "cat-file", "blob", f"{base_ref}:{path}"],
                          capture_output=True, cwd=str(root))
    if blob.returncode != 0:
        raise RuntimeError(f"{path} does not exist on {base_ref}")
    a = blob.stdout.splitlines(keepends=True)
    b = work.read_bytes().splitlines(keepends=True)
    # Reconstruction re-terminates every emitted line with the BASE blob's own
    # convention, so a replay can never flip a file's line endings.
    b = [_retermed(ln, a) for ln in b]
    ak = [ln.rstrip(b"\r\n") for ln in a]
    bk = [ln.rstrip(b"\r\n") for ln in b]
    sm = difflib.SequenceMatcher(None, ak, bk, autojunk=False)
    return a, b, list(sm.get_grouped_opcodes(3))


def _retermed(line, base_lines):
    """`line` re-terminated with the line ending the base blob uses."""
    body = line.rstrip(b"\r\n")
    if body == line:            # last line, no terminator: leave it alone
        return line
    crlf = any(bl.endswith(b"\r\n") for bl in base_lines)
    return body + (b"\r\n" if crlf else b"\n")


def cmd_hunks(args):
    a, b, groups = _hunk_groups(args.path, args.base)
    base_ref = args.base or trunk()
    if not groups:
        print(f"SHIP hunks: {args.path} is identical to {base_ref}.")
        return 0
    print(f"SHIP hunks  {args.path}  vs {base_ref}  ({len(groups)} hunk(s))")
    print("  Decide which are YOURS, then land ONLY those:")
    print(f'    {invoke()} commit --replay {args.path} --hunks 1,3 -m "..." --push')
    for i, group in enumerate(groups, 1):
        changed = sum((op[2] - op[1]) + (op[4] - op[3])
                      for op in group if op[0] != "equal")
        a1, a2 = group[0][1], group[-1][2]
        print("")
        print(f"  --- hunk {i} ---  (around line {a1 + 1} of {base_ref}, "
              f"~{changed} changed line(s))")
        shown = 0
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                continue
            for ln in a[i1:i2]:
                if shown >= args.context:
                    break
                print(f"    -{ln.decode('utf-8', 'replace').rstrip()[:150]}")
                shown += 1
            for ln in b[j1:j2]:
                if shown >= args.context:
                    break
                print(f"    +{ln.decode('utf-8', 'replace').rstrip()[:150]}")
                shown += 1
        if shown >= args.context:
            print(f"    ... (truncated at --context {args.context})")
    return 0


def _parse_hunk_spec(spec, n):
    want = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            want.update(range(int(lo), int(hi) + 1))
        else:
            want.add(int(part))
    bad = sorted(x for x in want if x < 1 or x > n)
    if bad:
        raise RuntimeError(f"no such hunk(s): {bad} (file has {n})")
    return want


def _replay_blob(path, hunk_spec, base_ref=None):
    """base_ref's blob with ONLY the selected hunks applied. Returns bytes.

    Every unselected region is taken verbatim from base_ref, so another session's
    uncommitted hunks are neither committed nor destroyed.
    """
    a, b, groups = _hunk_groups(path, base_ref)
    if not groups:
        raise RuntimeError(f"{path} has no hunks vs {base_ref or trunk()}")
    want = _parse_hunk_spec(hunk_spec, len(groups))
    out, prev = [], 0
    for idx, group in enumerate(groups, 1):
        ga1, ga2 = group[0][1], group[-1][2]
        gb1, gb2 = group[0][3], group[-1][4]
        out.extend(a[prev:ga1])
        out.extend(b[gb1:gb2] if idx in want else a[ga1:ga2])
        prev = ga2
    out.extend(a[prev:])
    return b"".join(out)


# -- secret gate (the ONLY place this tool blocks) ---------------------------

# Pattern-based: catches credentials HARDCODED in source, which is the common
# case. Value-based scanning (looking for known values from a local .env) is
# necessary but insufficient on its own, because a key pasted straight into
# source was never in .env. Both run below.
SECRET_PATTERNS = [
    (re.compile(rb"AIza[0-9A-Za-z_\-]{35}"), "Google API key"),
    (re.compile(rb"sk-[A-Za-z0-9]{32,}"), "OpenAI-style key"),
    (re.compile(rb"sk-ant-[A-Za-z0-9_\-]{24,}"), "Anthropic API key"),
    (re.compile(rb"ghp_[A-Za-z0-9]{36}"), "GitHub PAT"),
    (re.compile(rb"github_pat_[A-Za-z0-9_]{40,}"), "GitHub fine-grained PAT"),
    (re.compile(rb"AKIA[0-9A-Z]{16}"), "AWS access key id"),
    (re.compile(rb"xox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
    (re.compile(rb"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}"),
     "JWT"),
    (re.compile(rb"""(?i:pass(word|wd)|secret|api[_-]?key|token)\s*[:=]\s*['"][^'"\s]{12,}['"]"""),
     "hardcoded credential assignment"),
]

DEFAULT_SECRET_VALUE_FILES = [".env", "tools/.env", ".env.local"]


def secret_value_files():
    v = cfg().get("secret_value_files")
    return list(v) if v else list(DEFAULT_SECRET_VALUE_FILES)


def secret_scan_skip():
    """Never scan our own pattern table, or a doc that quotes example secrets."""
    try:
        me = Path(__file__).resolve().relative_to(repo_root()).as_posix()
    except Exception:
        me = "shared/ship.py"
    return {me} | set(cfg().get("secret_scan_skip") or [])


# An .env holds plenty of NON-secret config (folder ids, project ids, org ids)
# that legitimately appears in tracked source. Matching on those produces a
# false-positive storm, which is the alarm-fatigue failure that makes a gate get
# ignored. Only treat a value as secret if its KEY says so.
_SECRET_KEY_RE = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)", re.I)


def _known_secret_values():
    """Values from the local credential stores. Value-based half of the gate."""
    vals = set()
    for rel in secret_value_files():
        f = repo_root() / rel
        if not f.is_file():
            continue
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            k, v = line.split("=", 1)
            v = v.strip().strip("'\"")
            if len(v) >= 20 and _SECRET_KEY_RE.search(k):
                vals.add(v.encode())
    return vals


def scan_tree_for_secrets(tree, only_paths=None):
    """Scan the EXACT blob set about to be committed.

    On the staged tree, never the working tree: a naive `grep -r` over a tree with
    hundreds of dirty entries plus media times out, and a prescribed scan that does
    not finish is a scan that gets skipped.

    Returns [(path, what)].
    """
    findings = []
    values = _known_secret_values()
    skip = secret_scan_skip()
    # ONLY the paths this commit changes. Scanning the whole tree flags every
    # pre-existing file and buries the one that matters.
    scope = set(only_paths) if only_paths is not None else None
    out = git("ls-tree", "-r", "-z", tree)
    for entry in out.split("\0"):
        if not entry:
            continue
        meta, _, path = entry.partition("\t")
        parts = meta.split(" ")
        if len(parts) != 3 or parts[1] != "blob":
            continue
        if path in skip:
            continue
        if scope is not None and path not in scope:
            continue
        sha = parts[2]
        size = subprocess.run(["git", "cat-file", "-s", sha], capture_output=True,
                              text=True, cwd=str(repo_root())).stdout.strip()
        try:
            if int(size) > 2_000_000:      # binaries/media: not where secrets hide
                continue
        except ValueError:
            continue
        blob = subprocess.run(["git", "cat-file", "blob", sha], capture_output=True,
                              cwd=str(repo_root())).stdout
        for rx, what in SECRET_PATTERNS:
            if rx.search(blob):
                findings.append((path, what))
                break
        else:
            for v in values:
                if v in blob:
                    findings.append((path, "a value from your local .env"))
                    break
    return findings


# -- verify (the deploy ladder) ----------------------------------------------


def _repo_slug():
    url = git("remote", "get-url", "origin", check=False).strip()
    m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$", url)
    return m.group(1) if m else ""


def _gh(path, jq=None):
    args = ["gh", "api", path]
    if jq:
        args += ["--jq", jq]
    try:
        p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=str(repo_root()))
    except FileNotFoundError:
        return ""
    return p.stdout.strip() if p.returncode == 0 else ""


def cmd_verify(args):
    """Walk the deploy ladder. Rung 4 is the one everybody skips.

    Observed in the source system: a page 404'd in production for 20+ minutes
    while the commit was on the remote, the provider had received it, and the
    build was GREEN. It had been built as a PREVIEW and never promoted. "CI green"
    and "deployed" are not the same state, and the gap between them is rung 4.
    """
    slug = _repo_slug()
    fetch_trunk()
    # Normalise to the full sha: a short one would never string-compare equal to
    # what ls-remote returns, and the ladder's first rung would read wrong.
    sha = rev(args.sha) if args.sha else rev(trunk())
    if not sha:
        print("SHIP verify: cannot resolve a sha.", file=sys.stderr)
        return 2
    print(f"SHIP verify  {sha[:9]}  ({slug or 'unknown repo'})")

    # --- rung 1: is the commit on the remote? --------------------------------
    remote, _, target = trunk().partition("/")
    ls = git("ls-remote", remote, f"refs/heads/{target}", check=False)
    tip = ls.split()[0] if ls.split() else ""
    on_remote = tip == sha or (tip and git_ok("merge-base", "--is-ancestor", sha, tip))
    print(f"  1. on the remote      : {'YES' if on_remote else 'NO'}"
          f"{'' if tip == sha else f'  (tip is {tip[:9]})'}")
    if not on_remote:
        print("     STOP. Nothing downstream can be true. Re-push.")
        return 1

    names = [p for p in git("diff", "--name-only", "-z", f"{sha}^", sha,
                            check=False).split("\0") if p]
    hits = compute_blast(names) if names else []
    if not hits:
        print("  this commit deploys nothing -- rungs 2-5 do not apply. Done.")
        return 0

    if not slug:
        print("  cannot read the repo slug; rungs 2-4 need it.", file=sys.stderr)
        return 1

    # --- rungs 2 + 3: did the provider receive it, and did it build? ---------
    statuses = _gh(f"repos/{slug}/commits/{sha}/status",
                   '.statuses[]? | .context + " | " + .state + " | " + (.target_url // "-")')
    checks = _gh(f"repos/{slug}/commits/{sha}/check-runs",
                 '.check_runs[]? | .name + " | " + .status + " | " + (.conclusion // "-")')
    print("  2. provider received it:")
    for line in (statuses.splitlines() + checks.splitlines()) or [
        "     (nothing reported -- is the `gh` CLI installed and authenticated?)"
    ]:
        print(f"       {line}")
    # Scan BOTH channels. Reading `checks` only made rung 3 print "no failures
    # reported" immediately below a rung-2 line reading "Vercel | failure" -- the
    # provider's own verdict, displayed and then contradicted one line later.
    # Statuses and check-runs are different GitHub APIs and a deploy provider may
    # report through either; a ladder that ignores one states a confident wrong
    # verdict, which is the single failure mode this gate exists to prevent.
    bad = [l for l in (checks.splitlines() + statuses.splitlines())
           if "failure" in l or "cancelled" in l or "error" in l]
    print(f"  3. it built            : {'FAILURES PRESENT' if bad else 'no failures reported'}")
    for b in bad:
        print(f"       {b}")

    # --- rung 4: was it PROMOTED? -------------------------------------------
    print("  4. promoted to production:")
    for h in hits:
        if h.get("forced"):
            print(f"       [FORCED]  {h['surface']}")
            print("                 derived: a green forced run PROMOTED it (a CLI")
            print("                 production flag ignores the branch setting).")
        elif h.get("vercel"):
            print(f"       [BRANCH!] {h['surface']}")
            print("                 UNKNOWN from here. Branch-triggered promotion can")
            print("                 silently build a PREVIEW instead. Compare all three:")
            print("                   curl -sS -o /dev/null -w '%{http_code} %{url_effective}\\n' \\")
            print("                     <production-alias>/<path> <git-branch-alias>/<path> "
                  "<custom-domain>/<path>")
            print("                 Disagreement means it was never promoted.")
        else:
            print(f"       [JOB]     {h['surface']}  -- no production alias; n/a.")

    # --- rung 5: is the LIVE artifact the new one? --------------------------
    print("  5. live artifact is the new one: CANNOT be asserted generically.")
    print("       Assert on something UNIQUE to this change -- a built asset hash, or a")
    print("       string only the new version contains. A 200 on the homepage proves")
    print("       nothing.")
    return 0


# -- CLI ----------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser(
        prog="ship",
        description="ship gate: see what a push deploys, then ship it safely "
                    "from a repo shared by parallel agent sessions.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("blast", help="what would a trunk push of these paths deploy?")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--staged", action="store_true", help="assess the staged index")
    g.add_argument("--range", help="assess a diff range, e.g. origin/main..HEAD")
    p.add_argument("--paths", nargs="*", help="explicit paths")
    p.set_defaults(func=cmd_blast)

    p = sub.add_parser("status", help="branch lineage, divergence, orphans, claims")
    p.add_argument("--no-fetch", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("claim", help="take an advisory lease on paths")
    p.add_argument("globs", nargs="+")
    p.add_argument("-l", "--label", help="what you are doing")
    p.add_argument("--ttl", type=float, default=None)
    p.add_argument("--id", help="explicit id (hooks pass the session id)")
    p.set_defaults(func=cmd_claim)

    p = sub.add_parser("claims", help="list live claims")
    p.add_argument("--clean", action="store_true", help="purge expired leases")
    p.set_defaults(func=cmd_claims)

    p = sub.add_parser("release", help="drop a lease")
    p.add_argument("globs", nargs="*")
    p.add_argument("--id")
    p.set_defaults(func=cmd_release)

    p = sub.add_parser(
        "hunks", help="list the numbered hunks of a contested file (headless git add -p)"
    )
    p.add_argument("path")
    p.add_argument("--base", help="ref to diff against (default: trunk)")
    p.add_argument("--context", type=int, default=14, help="lines shown per hunk")
    p.set_defaults(func=cmd_hunks)

    p = sub.add_parser(
        "verify", help="walk the deploy ladder (rung 4 is the skipped one)"
    )
    p.add_argument("sha", nargs="?", help="commit to verify (default: trunk tip)")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("rules", help="print the standard (readable from any branch)")
    p.set_defaults(func=cmd_rules)

    p = sub.add_parser(
        "untracked", help="real content that exists ONLY in the shared working tree"
    )
    p.add_argument("--min-bytes", type=int, default=2000)
    p.add_argument("--all", action="store_true", help="include binaries/scratch too")
    p.add_argument("--no-fetch", action="store_true")
    p.set_defaults(func=cmd_untracked)

    p = sub.add_parser(
        "contested", help="tracked files carrying other sessions' unfinished edits"
    )
    p.add_argument("--min-lines", type=int, default=40)
    p.add_argument("--limit", type=int, default=25)
    p.set_defaults(func=cmd_contested)

    p = sub.add_parser(
        "worktree", help="create an isolated worktree cut from a fresh trunk"
    )
    p.add_argument("name")
    p.add_argument("--branch", help="branch name (default wt/<name>)")
    p.add_argument("--path", help="worktree path (default <temp>/wt-<name>)")
    p.add_argument("--claim", nargs="*", help="paths to claim for this worktree")
    p.add_argument("-l", "--label", help="intent for the claim")
    p.set_defaults(func=cmd_worktree)

    p = sub.add_parser("close", help="how to END a branch: landable / contested / dead")
    p.add_argument("--branch", help="ref to close (default HEAD)")
    p.add_argument("--no-fetch", action="store_true")
    p.set_defaults(func=cmd_close)

    p = sub.add_parser("orphans", help="files on a branch and nowhere else")
    p.add_argument("--branch", help="ref to compare (default HEAD)")
    p.add_argument("--no-fetch", action="store_true")
    p.set_defaults(func=cmd_orphans)

    p = sub.add_parser(
        "commit", help="path-scoped commit via plumbing; never touches the working tree"
    )
    p.add_argument("--paths", nargs="*")
    p.add_argument("--paths-from", help="file with one path per line")
    p.add_argument("--rm", nargs="*", help="paths to REMOVE from the target branch")
    # -F exists because building a long message as a shell string is genuinely
    # dangerous: backticks inside a double-quoted -m are COMMAND SUBSTITUTION, so a
    # message describing a deploy command once EXECUTED that deploy command against
    # the repo root. A message file cannot do that.
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("-m", "--message")
    g.add_argument("-F", "--message-file",
                   help="read the commit message from a file (safe for backticks, "
                        "quotes and newlines)")
    p.add_argument("--onto", default=None, help="target ref (default: trunk)")
    p.add_argument("--from", dest="from_ref",
                   help="take content from this ref, not the worktree")
    p.add_argument("--merge3", action="store_true",
                   help="3-way merge each path (base=merge-base) instead of taking "
                        "--from wholesale")
    p.add_argument("--push", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--content", nargs="*",
                   help="repopath=localfile: commit exact content, worktree untouched")
    p.add_argument("--replay", help="contested file: take trunk's blob + only --hunks")
    p.add_argument("--hunks", help="hunk numbers for --replay, e.g. 1,3 or 2-4")
    p.add_argument("--i-verified-no-secrets", action="store_true",
                   help="override the secret gate; say what you checked in the message")
    p.set_defaults(func=cmd_commit)

    args = ap.parse_args()
    try:
        return args.func(args)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())