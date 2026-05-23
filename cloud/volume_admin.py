"""Volume admin: project-specific wrapper over Modal volume operations.

Encapsulates the three volume names (loras, outputs, hf-cache) plus a
handful of operations Modal's native CLI either lacks or makes verbose.

Subcommands:

    list                                List all three volumes with item counts.
    size                                Total bytes per volume + cost/month.
    rm <volume> <pattern>               Pattern-based delete (e.g. "*.png").
    gc-staging                          Wipe outputs/staging/* (one-time backlog cleanup).
    download <volume> <pattern> <local> Bulk download by pattern.
    inspect outputs <output_name>       Show mp4 + manifest + (optional) staging for one render.

Usage (module mode required because `cloud/` uses relative imports):

    python -m cloud.volume_admin list
    python -m cloud.volume_admin size
    python -m cloud.volume_admin rm outputs "*.png"
    python -m cloud.volume_admin gc-staging
    python -m cloud.volume_admin download outputs "*.mp4" ./outputs/from-modal/
    python -m cloud.volume_admin inspect outputs tcole_valley

Run with plain `python -m`, not `modal run`. The Modal SDK is imported
locally; volume operations are network calls that don't need a container.
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import sys
from pathlib import Path

import modal

from .app import (
    HF_CACHE_VOLUME_NAME,
    LORAS_VOLUME_NAME,
    OUTPUTS_VOLUME_NAME,
)


VOLUME_NAMES = {
    "loras": LORAS_VOLUME_NAME,
    "outputs": OUTPUTS_VOLUME_NAME,
    "hf-cache": HF_CACHE_VOLUME_NAME,
}

# Modal published per-GB-month storage cost. Approximate; check Modal's
# pricing page for current numbers.
USD_PER_GB_MONTH = 0.02


# ---------------------------------------------------------------------------
# Public subcommands
# ---------------------------------------------------------------------------


def cmd_list() -> int:
    print("Volumes:")
    for alias, name in VOLUME_NAMES.items():
        try:
            vol = modal.Volume.from_name(name, create_if_missing=False)
            bytes_, n_files = _walk(vol, "/")
            print(
                f"  {alias:<10} {name:<24} {_fmt_size(bytes_):>12}  ({n_files} files)"
            )
        except Exception as exc:
            print(f"  {alias:<10} {name:<24} (unavailable: {exc!r})")
    return 0


def cmd_size() -> int:
    print(f"{'volume':<10} {'name':<24} {'size':>12} {'$/month':>10} {'files':>7}")
    print("-" * 66)
    total_bytes = 0
    for alias, name in VOLUME_NAMES.items():
        try:
            vol = modal.Volume.from_name(name, create_if_missing=False)
            bytes_, n_files = _walk(vol, "/")
        except Exception as exc:
            print(f"{alias:<10} {name:<24}  unavailable: {exc!r}")
            continue
        gb = bytes_ / 1024**3
        monthly = gb * USD_PER_GB_MONTH
        total_bytes += bytes_
        print(
            f"{alias:<10} {name:<24} {_fmt_size(bytes_):>12} "
            f"{'$' + format(monthly, '.3f'):>10} {n_files:>7}"
        )
    print("-" * 66)
    total_gb = total_bytes / 1024**3
    total_monthly = total_gb * USD_PER_GB_MONTH
    print(
        f"{'TOTAL':<10} {'':<24} {_fmt_size(total_bytes):>12} "
        f"{'$' + format(total_monthly, '.3f'):>10}"
    )
    return 0


def cmd_rm(volume_alias: str, pattern: str, *, dry_run: bool = False) -> int:
    name = _resolve_alias(volume_alias)
    vol = modal.Volume.from_name(name, create_if_missing=False)

    matches = _matching_paths(vol, "/", pattern)
    if not matches:
        print(f"No paths in volume {name} match {pattern!r}.")
        return 0

    print(f"{len(matches)} path(s) match {pattern!r} in volume {name}:")
    for p in matches[:20]:
        print(f"  - {p}")
    if len(matches) > 20:
        print(f"  ... and {len(matches) - 20} more.")

    if dry_run:
        print("[dry-run] not deleting.")
        return 0

    confirm = input(f"DELETE all {len(matches)} matching path(s)? [y/N]: ")
    if confirm.strip().lower() != "y":
        print("Aborted.")
        return 1

    for p in matches:
        try:
            vol.remove_file(p, recursive=True)
        except Exception as exc:
            print(f"  failed to remove {p}: {exc!r}")
    print(f"Removed {len(matches)} path(s).")
    return 0


def cmd_gc_staging() -> int:
    """Wipe outputs/staging/*. Complement to T1#3's per-render cleanup."""
    name = OUTPUTS_VOLUME_NAME
    vol = modal.Volume.from_name(name, create_if_missing=False)

    try:
        entries = list(vol.iterdir("/staging"))
    except Exception:
        entries = []

    if not entries:
        print(f"No /staging directory in {name}. Nothing to clean.")
        return 0

    print(f"Will delete /staging from {name} ({len(entries)} top-level entries).")
    confirm = input("Confirm? [y/N]: ")
    if confirm.strip().lower() != "y":
        print("Aborted.")
        return 1

    try:
        vol.remove_file("/staging", recursive=True)
        print("Deleted /staging.")
    except Exception as exc:
        print(f"Failed: {exc!r}")
        return 1
    return 0


def cmd_download(volume_alias: str, pattern: str, local_dir: str) -> int:
    name = _resolve_alias(volume_alias)
    vol = modal.Volume.from_name(name, create_if_missing=False)

    matches = _matching_paths(vol, "/", pattern, files_only=True)
    if not matches:
        print(f"No files in volume {name} match {pattern!r}.")
        return 0

    local_root = Path(local_dir).resolve()
    local_root.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {len(matches)} file(s) from {name} to {local_root}/")
    for remote in matches:
        rel = remote.lstrip("/")
        local_path = local_root / rel
        local_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with local_path.open("wb") as f:
                for chunk in vol.read_file(remote):
                    f.write(chunk)
            size = local_path.stat().st_size
            print(f"  {remote} -> {local_path}  ({_fmt_size(size)})")
        except Exception as exc:
            print(f"  failed to download {remote}: {exc!r}")
    return 0


def cmd_inspect(output_name: str) -> int:
    """Show mp4 + manifest + (optional) staging for one render."""
    name = OUTPUTS_VOLUME_NAME
    vol = modal.Volume.from_name(name, create_if_missing=False)

    expected = {
        "mp4": f"/{output_name}.mp4",
        "manifest": f"/{output_name}.manifest.json",
        "staging_root": f"/staging/{output_name}",
    }

    print(f"Inspecting {output_name!r} in volume {name}:")
    for label, path in expected.items():
        info = _stat(vol, path)
        if info is None:
            print(f"  {label:<14} {path:<60} (absent)")
        elif info["is_dir"]:
            try:
                staging_bytes, staging_n = _walk(vol, path)
            except Exception:
                staging_bytes, staging_n = 0, 0
            print(
                f"  {label:<14} {path:<60} "
                f"DIR  {_fmt_size(staging_bytes)}  ({staging_n} files)"
            )
        else:
            print(
                f"  {label:<14} {path:<60} "
                f"FILE  {_fmt_size(info['size'])}"
            )
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_alias(alias_or_name: str) -> str:
    if alias_or_name in VOLUME_NAMES:
        return VOLUME_NAMES[alias_or_name]
    if alias_or_name in VOLUME_NAMES.values():
        return alias_or_name
    raise SystemExit(
        f"Unknown volume {alias_or_name!r}. "
        f"Aliases: {list(VOLUME_NAMES)}. Names: {list(VOLUME_NAMES.values())}"
    )


def _walk(vol, root: str) -> tuple[int, int]:
    """Recursively sum byte size + file count under `root`."""
    total_bytes = 0
    n_files = 0
    try:
        entries = list(vol.iterdir(root))
    except Exception:
        return 0, 0

    for e in entries:
        t = str(getattr(e, "type", "")).upper()
        size = getattr(e, "size", 0) or 0
        path = getattr(e, "path", "")
        is_file = "FILE" in t and "DIR" not in t
        if is_file:
            total_bytes += size
            n_files += 1
        elif "DIR" in t or path.endswith("/"):
            sub_bytes, sub_n = _walk(vol, path)
            total_bytes += sub_bytes
            n_files += sub_n
        else:
            total_bytes += size
            if size > 0:
                n_files += 1
    return total_bytes, n_files


def _matching_paths(
    vol, root: str, pattern: str, *, files_only: bool = False
) -> list[str]:
    """Recursively list all paths matching a glob pattern."""
    matches: list[str] = []

    def walk(path: str) -> None:
        try:
            entries = list(vol.iterdir(path))
        except Exception:
            return
        for e in entries:
            t = str(getattr(e, "type", "")).upper()
            ep = getattr(e, "path", "")
            is_dir = "DIR" in t and "FILE" not in t
            if fnmatch.fnmatch(Path(ep).name, pattern) or fnmatch.fnmatch(
                ep.lstrip("/"), pattern
            ):
                if files_only and is_dir:
                    pass
                else:
                    matches.append(ep)
            if is_dir:
                walk(ep)

    walk(root)
    return matches


def _stat(vol, path: str) -> dict | None:
    """Return {size, is_dir} for `path` or None if absent."""
    parent = str(Path(path).parent).replace("\\", "/")
    if parent == ".":
        parent = "/"
    name = Path(path).name
    try:
        entries = list(vol.iterdir(parent))
    except Exception:
        return None
    for e in entries:
        ep = getattr(e, "path", "")
        if Path(ep).name == name:
            t = str(getattr(e, "type", "")).upper()
            return {
                "size": getattr(e, "size", 0) or 0,
                "is_dir": "DIR" in t and "FILE" not in t,
            }
    return None


def _fmt_size(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    if b < 1024**2:
        return f"{b/1024:.1f} KB"
    if b < 1024**3:
        return f"{b/1024**2:.1f} MB"
    return f"{b/1024**3:.2f} GB"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python cloud/volume_admin.py",
        description="Project-specific wrapper over Modal volume operations.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List all three volumes with item counts.")
    sub.add_parser("size", help="Total bytes per volume + estimated cost/month.")

    p_rm = sub.add_parser(
        "rm", help="Pattern-based delete (e.g. 'rm outputs *.png')."
    )
    p_rm.add_argument("volume", help="Volume alias or full name")
    p_rm.add_argument("pattern", help="fnmatch pattern (e.g. '*.png')")
    p_rm.add_argument("--dry-run", action="store_true", help="Show matches, don't delete")

    sub.add_parser(
        "gc-staging",
        help="Wipe outputs/staging/* (one-time backlog cleanup; complements T1#3).",
    )

    p_dl = sub.add_parser(
        "download", help="Bulk download files matching a pattern."
    )
    p_dl.add_argument("volume", help="Volume alias or full name")
    p_dl.add_argument("pattern", help="fnmatch pattern (e.g. '*.mp4')")
    p_dl.add_argument("local_dir", help="Local destination directory")

    p_in = sub.add_parser(
        "inspect", help="Show mp4 + manifest + (optional) staging for one render."
    )
    p_in.add_argument("volume", help="Volume alias (typically 'outputs')")
    p_in.add_argument("output_name", help="Render output_name to inspect")

    args = parser.parse_args()

    if args.cmd == "list":
        return cmd_list()
    if args.cmd == "size":
        return cmd_size()
    if args.cmd == "rm":
        return cmd_rm(args.volume, args.pattern, dry_run=args.dry_run)
    if args.cmd == "gc-staging":
        return cmd_gc_staging()
    if args.cmd == "download":
        return cmd_download(args.volume, args.pattern, args.local_dir)
    if args.cmd == "inspect":
        if args.volume not in ("outputs", OUTPUTS_VOLUME_NAME):
            print("inspect currently only supports the outputs volume.")
            return 1
        return cmd_inspect(args.output_name)
    return 1


if __name__ == "__main__":
    sys.exit(main())
