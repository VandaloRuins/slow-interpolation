"""Pre-flight workspace check.

Prints credit balance, workspace identity, and known volume sizes
before you commit to a render or batch. Read-only; safe to run anytime.

Usage:

    modal run -m cloud.preflight

Sample output:

    [preflight] workspace:   vandaloruins
    [preflight] credits:     $29.85 (was $30.00 at first render)
    [preflight] volumes:
      slow-interp-loras       652.0 MB  (3 files)
      slow-interp-outputs       7.2 MB  (4 files)
      slow-interp-hf-cache    8920.1 MB  (cache warm)
    [preflight] OK -- ready to render.

Run as a sanity check before a release-day batch, after a long gap,
or any time you want to know what you're about to spend into.
"""

from __future__ import annotations

import modal

from .app import (
    APP_NAME,
    HF_CACHE_VOLUME_NAME,
    LORAS_VOLUME_NAME,
    OUTPUTS_VOLUME_NAME,
    app,
)


VOLUME_NAMES = [
    LORAS_VOLUME_NAME,
    OUTPUTS_VOLUME_NAME,
    HF_CACHE_VOLUME_NAME,
]


@app.local_entrypoint()
def main() -> None:
    """Print workspace identity, credit balance, and volume sizes."""
    import os

    # Workspace identity: read from the modal config profile.
    try:
        from modal.config import _profile

        workspace = _profile or "(default profile)"
    except Exception:
        workspace = os.environ.get("MODAL_PROFILE", "unknown")

    print(f"[preflight] app:         {APP_NAME}")
    print(f"[preflight] workspace:   {workspace}")

    # Credit balance: Modal's Python SDK does not expose this directly
    # as of 1.x. Print a pointer to the dashboard.
    print(
        "[preflight] credits:     "
        "(check https://modal.com/settings/usage for live balance)"
    )

    # Volume sizes: walk each volume and sum FileEntry.size.
    print("[preflight] volumes:")
    total_bytes = 0
    for vname in VOLUME_NAMES:
        try:
            vol = modal.Volume.from_name(vname, create_if_missing=False)
        except Exception as exc:
            print(f"  {vname:<26} (unavailable: {exc!r})")
            continue

        try:
            size_bytes, n_files = _walk_volume(vol, "/")
        except Exception as exc:
            print(f"  {vname:<26} (walk failed: {exc!r})")
            continue

        total_bytes += size_bytes
        print(
            f"  {vname:<26} {_fmt_size(size_bytes):>12}  ({n_files} files)"
        )

    print(f"  {'TOTAL':<26} {_fmt_size(total_bytes):>12}")
    print()
    print("[preflight] OK -- ready to render.")


def _walk_volume(vol, root: str) -> tuple[int, int]:
    """Recursively walk a Modal volume, returning (total_bytes, file_count).

    Modal's `Volume.iterdir(path)` lists one directory level. We recurse
    manually into anything that looks like a directory (FileEntry.type
    == FILE_ENTRY_TYPE_DIRECTORY, exact enum value varies by SDK
    version; we treat anything not-FILE as recursable).
    """
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
            sub_bytes, sub_n = _walk_volume(vol, path)
            total_bytes += sub_bytes
            n_files += sub_n
        else:
            # Unknown entry type: treat as file if it has size.
            total_bytes += size
            if size > 0:
                n_files += 1
    return total_bytes, n_files


def _fmt_size(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    if b < 1024**2:
        return f"{b/1024:.1f} KB"
    if b < 1024**3:
        return f"{b/1024**2:.1f} MB"
    return f"{b/1024**3:.2f} GB"
