"""No sibling-repo references, machine paths, or foreign secret names in tracked files.

This repo is public. CLAUDE.md's "Public-repo constraint" already says that
parallel-project references and machine paths stay out of tracked files.
AGENTS.md and CONTRIBUTING.md carried that as a hand-run grep, but scoped to
`src/` and `vendor/` only, which is exactly where the problem never was.

In August 2026 six files under `tools/` and `datasets/` were resolving their
Gemini key by reading two sibling projects' `.env` files. Google bills the GCP
project that owns a key, not the code that calls it, so every one of those calls
was charged to a project that had nothing to do with this work: EUR 21 of
keyframe generation landed on one of them in two days. The hand-run grep could
not have caught it, because it never looked at those directories.

This test is that rule, enforced, over the directories where code actually lives.
It reads the tracked file list from git, so gitignored files (notably
`tools/.env`) are never opened.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# Where executable behaviour lives. A forbidden string here is a live defect.
CODE_DIRS = ("src", "vendor", "tools", "datasets", ".github")
# Everything tracked that ships, including prose.
ALL_DIRS = CODE_DIRS + ("tests", "docs", ".claude")

# Exact paths only. NEVER a glob: an exemption with a wildcard becomes the hole
# the rule was written to close. Every entry carries the reason it exists.
ALLOWED: dict[str, str] = {
    "tests/test_no_sibling_paths.py": "this file; it must name the forbidden strings to forbid them",
    "AGENTS.md": "states the rule, so it must quote the forbidden names",
    "CONTRIBUTING.md": "states the rule, so it must quote the forbidden names",
    "CLAUDE.md": "states the public-repo constraint, so it must quote the forbidden names",
}

# `legacy/` is a vendored snapshot of the previous project this one was ported
# from. Its directory is itself named after that project, so the rule cannot
# apply. Severing it is tracked separately; see AGENTS.md "No sibling-folder
# dependencies in src/".
EXEMPT_PREFIXES = ("legacy/",)

# Each pattern carries its own scope, because the two classes of name are not
# the same problem.
#
#   Choire / After Cole are this project's LINEAGE. It was ported from them, and
#   docs/ documents that history legitimately. The pre-existing rule in AGENTS.md
#   scoped them to src/ and vendor/ for exactly that reason. This test keeps that
#   scope and extends it to tools/ and datasets/, which is where the August 2026
#   leak actually was and where the old grep never looked.
#
#   RNMW-agent / Ruins-* are ACTIVE parallel projects, not lineage. Naming one
#   anywhere published discloses it, so those are banned in prose too.
PATTERNS: list[tuple[str, re.Pattern[str], str, tuple[str, ...]]] = [
    (
        "machine path",
        re.compile(r"[A-Za-z]:[\\/]Users[\\/]|/(?:home|Users)/[A-Za-z0-9._-]+/"),
        "absolute paths leak the author's username and break on every other machine",
        ALL_DIRS,
    ),
    (
        "active sibling project",
        re.compile(r"RNMW-agent|Ruins-Harness_Tools-for-Agents|Ruins-agent"),
        "naming a live parallel project in a public repo discloses it and couples the two",
        ALL_DIRS,
    ),
    (
        "legacy lineage in code",
        re.compile(r"Choire|After Cole"),
        "src/ and vendor/ must not depend on the projects this was ported from, and "
        "neither must tools/ or datasets/, which is where the key leak actually was. "
        "Documenting the lineage in docs/ is fine and deliberately not covered",
        CODE_DIRS,
    ),
    (
        "foreign secret name",
        re.compile(r"GOOGLE_AI_API_KEY|GEMINI_API_KEY_[A-Z]"),
        "these are another repo's variable names; this project uses a bare GEMINI_API_KEY",
        ALL_DIRS,
    ),
]


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [p for p in out.split("\0") if p]


def in_scope(rel: str, dirs: tuple[str, ...]) -> bool:
    if rel in ALLOWED or rel.startswith(EXEMPT_PREFIXES):
        return False
    return rel.startswith(tuple(d + "/" for d in dirs))


@pytest.mark.parametrize(
    "label,pattern,why,dirs", PATTERNS, ids=[p[0] for p in PATTERNS]
)
def test_no_forbidden_strings(
    label: str, pattern: re.Pattern[str], why: str, dirs: tuple[str, ...]
) -> None:
    hits: list[str] = []
    for rel in tracked_files():
        if not in_scope(rel, dirs):
            continue
        path = REPO / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, OSError):
            continue  # binary or a stale index entry; nothing to read
        for n, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                hits.append(f"  {rel}:{n}: {line.strip()[:120]}")

    assert not hits, (
        f"\n{len(hits)} {label} reference(s) in tracked files.\n"
        f"Why this is banned: {why}.\n\n" + "\n".join(hits) + "\n\n"
        "Fix the file. If a reference is genuinely unavoidable, add its EXACT\n"
        "path to ALLOWED in this test with a written reason. Never add a glob.\n"
    )


def test_allowlist_entries_still_exist() -> None:
    """An allowlist that outlives its files silently widens the rule."""
    missing = [p for p in ALLOWED if not (REPO / p).is_file()]
    assert not missing, (
        "ALLOWED names files that no longer exist; remove them: " + ", ".join(missing)
    )
