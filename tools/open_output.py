"""Cross-platform open-file helper for the slow-interpolation pipeline.

After a render completes, the agent calls this to surface the artifact to the
student without making them hunt through the file tree. Supports two modes:

    python tools/open_output.py <path>            # open the file or folder
    python tools/open_output.py --folder <path>   # open the containing folder

A single file opens with the OS default application (MP4 in the default media
player or browser, PNG in the image viewer). A folder opens in the OS file
explorer (Finder on macOS, Explorer on Windows, the default file manager on
Linux). The helper is intentionally tiny so the agent can call it without
ceremony; it does not log, does not block, does not interpret the user's
intent. If you need a richer viewer, build a separate tool.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def open_path(path: Path) -> None:
    """Open `path` with the OS default handler. `path` may be a file or folder."""
    if not path.exists():
        raise FileNotFoundError(f"No such file or directory: {path}")

    if sys.platform == "win32":
        # os.startfile dispatches via the Windows shell with the same semantics
        # as double-clicking the file in Explorer. Cleaner than subprocess.
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=True)
    else:
        subprocess.run(["xdg-open", str(path)], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Open a render output (file or folder) in the OS default handler.",
    )
    parser.add_argument("path", type=Path, help="File or folder to open.")
    parser.add_argument(
        "--folder",
        action="store_true",
        help="If `path` is a file, open its containing folder instead.",
    )
    args = parser.parse_args()

    target = args.path.resolve()
    if args.folder and target.is_file():
        target = target.parent

    open_path(target)
    print(f"Opened: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
