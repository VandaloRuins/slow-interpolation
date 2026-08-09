"""Pull everything new off the Modal outputs volume, then rebuild the gallery.

One command instead of three, because the three-step version silently lost a
render's keyframes once already: `modal volume get` fails if the destination's
parent directory does not exist, and its error on Windows is a cp1252 encoding
crash on its own checkmark, which is easy to swallow with `2>/dev/null`.

    python tools/sync_outputs.py                 # sync + rebuild gallery
    python tools/sync_outputs.py --open          # ... and open it
    python tools/sync_outputs.py --prefix coe_   # only matching artifacts

Local layout mirrors each config's `output_dir`, resolved by matching the
artifact name back to the YAML that produced it. Volume layout is FLAT: renders
land at the root as `<output_name>.mp4`, keyframes under `staging/<output_name>/`.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
VOLUME = "slow-interp-outputs"
CONFIGS = ROOT / "examples" / "configs"


def modal(*args: str) -> tuple[int, str]:
    r = subprocess.run(["modal", *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=900)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def volume_root() -> list[str]:
    code, out = modal("volume", "ls", VOLUME)
    if code != 0:
        print("could not list volume", file=sys.stderr)
        return []
    return [l.strip() for l in out.splitlines()
            if l.strip() and not l.startswith(("+", "|", "-"))]


def output_dirs() -> dict[str, Path]:
    """Map output_name -> local output_dir, read from the configs."""
    m: dict[str, Path] = {}
    for p in CONFIGS.rglob("*.yaml"):
        try:
            cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(cfg, dict):
            continue
        name = cfg.get("output_name") or (cfg.get("subject") or {}).get("name")
        if name:
            m.setdefault(str(name), ROOT / cfg.get("output_dir", "outputs"))
    return m


def fetch(remote: str, dest_dir: Path) -> bool:
    dest_dir.mkdir(parents=True, exist_ok=True)   # the bug that ate a render
    code, out = modal("volume", "get", "--force", VOLUME, remote, str(dest_dir))
    # modal exits non-zero on the Windows codepage crash even when the transfer
    # succeeded, so trust the filesystem rather than the exit code.
    return code == 0 or "charmap" in out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="", help="only sync artifacts starting with this")
    ap.add_argument("--open", action="store_true", help="open the gallery afterwards")
    ap.add_argument("--no-gallery", action="store_true")
    args = ap.parse_args()

    dirs = output_dirs()
    mp4s = [e for e in volume_root()
            if e.endswith(".mp4") and e.startswith(args.prefix)]
    if not mp4s:
        print("nothing on the volume matches")
        return 0

    new = 0
    for mp4 in sorted(mp4s):
        name = mp4[:-4]
        dest = dirs.get(name, ROOT / "outputs" / "from-modal")
        if not (dest / mp4).exists():
            fetch(mp4, dest); new += 1
            print(f"  + {mp4}  ->  {dest.relative_to(ROOT)}")
        fetch(f"{name}.manifest.json", dest)
        staging = dest / "staging"
        if not (staging / name).exists():
            fetch(f"staging/{name}", staging)

    print(f"\n{new} new render(s), {len(mp4s)} checked")

    if args.no_gallery:
        # Deliberately no escape sequences in this block. Passing an escaped
        # newline through a patch script is how a literal line break ended up
        # inside a string twice today, once here and once in gallery.py.
        print("")
        print("!! --no-gallery: the page was NOT rebuilt, so these renders are")
        print("!! NOT visible in the gallery yet. Run: python tools/gallery.py")
        print("!! before telling anyone to look.")
    else:
        print("rebuilding gallery...")
        cmd = [sys.executable, str(ROOT / "tools" / "gallery.py")]
        if args.open:
            cmd.append("--open")
        subprocess.run(cmd, cwd=ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
