"""Answer "is the Modal work actually finished?" deterministically.

A `modal run` exiting 0 is a weak signal. It can exit 0 on a partially failed
batch, and a dropped local connection returns the shell while the remote app
keeps burning GPU. The only trustworthy answer combines two server-side facts:

  1. No app of ours is still RUNNING (server-side, not inferred from the shell).
  2. The artifacts we expected actually exist on the outputs volume.

Both are cheap reads. Neither costs GPU.

    python tools/modal_status.py                      # are any of our apps live?
    python tools/modal_status.py --expect ladder_r0_control.mp4,ladder_ra_steps12.mp4
    python tools/modal_status.py --expect-dir staging --contains ladder_ --count 8

IMPORTANT, and it cost a false alarm the first time this script ran: `output_dir`
in a pipeline YAML is a LOCAL path. It does NOT create a subdirectory on the
Modal volume. Renders land FLAT at the volume root as `<output_name>.mp4` plus
`<output_name>.manifest.json`, and preserved keyframes land under
`staging/<output_name>/`. Do not pass an `--expect` path derived from
`output_dir`; use the bare filename.

Exit codes:
    0  nothing running AND every expected artifact present
    1  something is still running
    2  nothing running but artifacts are missing (a silent partial failure)

Run it under the interpreter that has `modal` importable, or rely on the CLI
path: this script shells out to `modal`, so the repo's own interpreter is fine
even though `import modal` fails there.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

APP_PREFIX = "slow-interp"
OUTPUTS_VOLUME = "slow-interp-outputs"
LIVE_STATES = {"running", "ephemeral", "deploying"}


def _modal(*args: str) -> str:
    """Run a modal CLI command and return stdout, or '' if it failed."""
    try:
        r = subprocess.run(
            ["modal", *args],
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
            errors="replace",
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"modal CLI unavailable: {exc}", file=sys.stderr)
        return ""
    return r.stdout or ""


def live_apps() -> list[str]:
    """App IDs of ours that are still in a live state, server-side."""
    out = _modal("app", "list")
    live: list[str] = []
    for line in out.splitlines():
        if APP_PREFIX not in line:
            continue
        low = line.lower()
        if any(s in low for s in LIVE_STATES):
            parts = [p.strip() for p in line.split("|") if p.strip()]
            live.append(parts[0] if parts else line.strip())
    return live


def volume_files(prefix: str) -> set[str]:
    """Filenames present under `prefix` on the outputs volume."""
    out = _modal("volume", "ls", OUTPUTS_VOLUME, prefix)
    names: set[str] = set()
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith(("+", "|", "-")):
            continue
        names.add(line.split("/")[-1])
    return names


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect", default="", help="comma-separated volume paths that must exist")
    ap.add_argument("--expect-dir", default="/", help="volume directory to check")
    ap.add_argument("--contains", default="", help="only count entries containing this substring")
    ap.add_argument("--count", type=int, default=0, help="how many entries --expect-dir must hold")
    args = ap.parse_args()

    running = live_apps()
    if running:
        print(f"RUNNING: {len(running)} app(s) still live")
        for a in running:
            print(f"  {a}")
        return 1
    print("no slow-interp app is running (server-side)")

    missing: list[str] = []
    if args.expect:
        for path in (p.strip() for p in args.expect.split(",") if p.strip()):
            head, _, tail = path.rpartition("/")
            if tail not in volume_files(head or "/"):
                missing.append(path)
    if args.count:
        found = volume_files(args.expect_dir)
        if args.contains:
            found = {f for f in found if args.contains in f}
        label = f"{args.expect_dir} matching '{args.contains}'" if args.contains else args.expect_dir
        print(f"{label}: {len(found)} entr(ies) on the volume")
        if len(found) < args.count:
            missing.append(f"{label} has {len(found)}, expected {args.count}")

    if missing:
        print("\nINCOMPLETE. Nothing is running, but these are absent:")
        for m in missing:
            print(f"  {m}")
        print("\nThat is a silent partial failure, not a success.")
        return 2

    print("DONE: nothing running, every expected artifact present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
