"""Walk markdown files in the repo and report any broken relative links.

Catches the link rot you get after `git mv`-ing a doc. Not a full markdown
parser; it matches the `[text](path)` and `[text]: path` forms with a regex
and ignores everything anchored (`http://`, `https://`, `mailto:`, `#anchor`).
A path with a fragment (`docs/foo.md#section`) is checked for file existence,
the fragment is not validated.

Usage:

    python tools/check_doc_links.py          # walk the whole repo
    python tools/check_doc_links.py docs/    # walk a subtree
    python tools/check_doc_links.py --strict # exit 1 on any broken link

The default scan roots are the repo-root markdown files plus `docs/`, the
README files we ship, the CONTRIBUTING file, and AGENTS.md. Anything under
`legacy/` is intentionally skipped (read-only reference, broken links there
are not our problem).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

LINK_RE = re.compile(r"\[(?P<text>[^\]]*)\]\((?P<href>[^)\s]+)(?:\s+\"[^\"]*\")?\)")
REF_RE = re.compile(r"^\[(?P<label>[^\]]+)\]:\s+(?P<href>\S+)", re.MULTILINE)
ANCHORED = ("http://", "https://", "mailto:", "tel:", "#")

# Strip fenced code blocks (```...```) and inline code (`...`) before scanning
# for links. Path examples in code spans are documentation, not navigable links.
FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")

SKIP_DIRS = {"legacy", "node_modules", ".venv", "__pycache__", ".git", "outputs", "datasets", "private"}


def iter_markdown(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix.lower() == ".md":
            files.append(root)
        elif root.is_dir():
            for p in root.rglob("*.md"):
                if any(part in SKIP_DIRS for part in p.parts):
                    continue
                files.append(p)
    return sorted(set(files))


def extract_links(text: str) -> list[str]:
    # Strip code spans so example paths inside backticks are not link-checked.
    stripped = FENCE_RE.sub("", text)
    stripped = INLINE_CODE_RE.sub("", stripped)
    hrefs = [m.group("href") for m in LINK_RE.finditer(stripped)]
    hrefs.extend(m.group("href") for m in REF_RE.finditer(stripped))
    return [h for h in hrefs if not h.startswith(ANCHORED)]


def resolve_target(src: Path, href: str) -> Path:
    target = href.split("#", 1)[0]
    if not target:
        return src
    return (src.parent / target).resolve()


def check_file(path: Path, repo_root: Path) -> list[tuple[Path, str, Path]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    broken: list[tuple[Path, str, Path]] = []
    for href in extract_links(text):
        target = resolve_target(path, href)
        if not target.exists():
            broken.append((path.relative_to(repo_root), href, target))
    return broken


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("roots", nargs="*", help="files or directories to scan (default: repo)")
    parser.add_argument("--strict", action="store_true", help="exit 1 if any broken link found")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    if args.roots:
        roots = [Path(r).resolve() for r in args.roots]
    else:
        roots = [
            repo_root / "README.md",
            repo_root / "AGENTS.md",
            repo_root / "CONTRIBUTING.md",
            repo_root / "CLAUDE.md",
            repo_root / "docs",
            repo_root / "cloud",
            repo_root / "examples",
        ]

    files = iter_markdown(roots)
    total_broken = 0
    for f in files:
        broken = check_file(f, repo_root)
        for src_rel, href, target in broken:
            try:
                target_disp = target.relative_to(repo_root)
            except ValueError:
                target_disp = target
            print(f"{src_rel}: BROKEN  [{href}]  -> {target_disp}")
            total_broken += 1

    print()
    print(f"scanned {len(files)} files; {total_broken} broken link(s)")
    if total_broken and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
