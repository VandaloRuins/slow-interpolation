"""archive_wave.py -- ingest a subtree into the R2 archive, one run per leaf directory.

    py -3.11 tools/archive_wave.py --source outputs/nyc-billboard --prefix nyc-billboard
    py -3.11 tools/archive_wave.py --source outputs/empire --prefix empire --dry-run

WHY THIS EXISTS RATHER THAN ONE ingest.py CALL
----------------------------------------------
`ingest.py` derives every key as `{prefix}/{media_type}/{filename}` from `path.name`
alone -- the subdirectory is discarded (see ingest.py, "rel" is computed and never used
in the key). It also walks with `rglob`. Point it at a parent and the entire subtree is
flattened into one prefix.

That is not theoretical. Measured on outputs/nyc-billboard 2026-08-12: 23 filenames
appear in more than one directory, and `0000.png` exists in 71 separate keyframes/
directories. A single recursive run puts 71 different images in a fight over one key.
The store's own dedupe/quarantine refuses the losers rather than corrupting anything --
1,410 quarantine events on the run that taught us this -- but 70 of those 71 files then
simply are not archived under a key that describes them.

So the directory structure is carried in the PREFIX, one ingest per leaf.

THE GUARD, WHICH IS THE POINT OF THIS FILE
------------------------------------------
The first version of this driver already did per-directory ingest and STILL flattened
132 objects, because it enumerated "directories that contain files" and two of those --
the tree root and `led/` -- contain files AND subdirectories. Handing such a directory
to a recursive ingest re-flattens everything beneath it.

`--strict` (default) REFUSES a mixed directory instead of trusting the operator to
notice. `--stage-mixed` handles it correctly by copying only that directory's DIRECT
files into a temp dir and ingesting that. An operator's attention is not a mechanism;
this is.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEDIA_EXT = {".mp4", ".mov", ".webm", ".gif", ".png", ".jpg", ".jpeg", ".webp"}
PY = [sys.executable] if sys.executable else ["py", "-3.11"]


def media_files(d: Path, recursive: bool = False):
    it = d.rglob("*") if recursive else d.iterdir()
    return [p for p in it if p.is_file() and p.suffix.lower() in MEDIA_EXT]


def classify(src: Path):
    """(dirs_with_direct_files, mixed_dirs). Mixed = direct files AND a subdir holding media."""
    direct, mixed = [], []
    for d in sorted({p.parent for p in media_files(src, recursive=True)}):
        if not media_files(d):
            continue
        direct.append(d)
        deeper = [p for p in media_files(d, recursive=True) if p.parent != d]
        if deeper:
            mixed.append(d)
    return direct, mixed


def event_of(d: Path, src: Path) -> str:
    """Cluster key for this directory. NEVER '.' -- an event tag of '.' is meaningless and
    is exactly what the flattening bug wrote onto 132 assets."""
    parts = [x for x in d.relative_to(src).as_posix().split("/") if x and x != "keyframes"]
    return parts[-1] if parts else src.name


def is_keyframes(d: Path, src: Path) -> bool:
    return "keyframes" in d.relative_to(src).as_posix().split("/")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, type=Path)
    ap.add_argument("--prefix", required=True, help="bucket key prefix root, e.g. nyc-billboard")
    ap.add_argument("--context", default=None, help="defaults to --prefix's first segment")
    ap.add_argument("--dry-run", action="store_true", help="plan only; ingest nothing")
    ap.add_argument("--stage-mixed", action="store_true",
                    help="handle a mixed directory by staging its DIRECT files, instead of refusing")
    ap.add_argument("--keyframes", choices=("include", "skip", "only"), default="include")
    args = ap.parse_args()

    src = (args.source if args.source.is_absolute() else ROOT / args.source).resolve()
    if not src.is_dir():
        print(f"no such directory: {src}")
        return 2
    context = args.context or args.prefix.split("/")[0]

    dirs, mixed = classify(src)
    if not dirs:
        print(f"no media under {src}")
        return 1

    if mixed and not args.stage_mixed:
        print("REFUSING: these directories hold files AND subdirectories, so a recursive")
        print("ingest would flatten everything beneath them into one prefix:")
        for d in mixed:
            n_direct = len(media_files(d))
            n_deep = len(media_files(d, recursive=True)) - n_direct
            rel = d.relative_to(src).as_posix() or "."
            print(f"   {rel:52} {n_direct:4} direct + {n_deep:5} deeper")
        print("\nRe-run with --stage-mixed to ingest each one's DIRECT files correctly.")
        return 3

    ordered = sorted(dirs, key=lambda d: (is_keyframes(d, src), d.as_posix()))
    if args.keyframes == "skip":
        ordered = [d for d in ordered if not is_keyframes(d, src)]
    elif args.keyframes == "only":
        ordered = [d for d in ordered if is_keyframes(d, src)]

    total_files = sum(len(media_files(d)) for d in ordered)
    print(f"wave: {len(ordered)} leaf dirs, {total_files} direct files, prefix '{args.prefix}'")
    print(f"  outputs   : {sum(1 for d in ordered if not is_keyframes(d, src))} dirs")
    print(f"  keyframes : {sum(1 for d in ordered if is_keyframes(d, src))} dirs")
    if mixed:
        print(f"  staged    : {len(mixed)} mixed dir(s) -> direct files only")
    print(flush=True)

    if args.dry_run:
        for d in ordered:
            rel = d.relative_to(src).as_posix()
            print(f"  {len(media_files(d)):4}f  {args.prefix}{'/' + rel if rel != '.' else ''}"
                  f"{'   [staged]' if d in mixed else ''}")
        print("\n(dry run -- nothing ingested)")
        return 0

    ok = fail = 0
    t0 = time.time()
    for i, d in enumerate(ordered, 1):
        rel = d.relative_to(src).as_posix()
        prefix = args.prefix + ("/" + rel if rel != "." else "")
        staged = None
        try:
            if d in mixed:
                # copy2 preserves mtime, which ingest.py uses to date an asset when no
                # manifest is present -- staging must not restamp everything to today
                staged = Path(tempfile.mkdtemp(prefix="wave-"))
                for p in media_files(d):
                    shutil.copy2(p, staged / p.name)
                source_arg = staged
            else:
                source_arg = d

            cmd = PY + ["tools/media-engine/ingest.py",
                        "--source", str(source_arg), "--prefix", prefix,
                        "--asset-class", "keyframe" if is_keyframes(d, src) else "render",
                        "--context", context, "--event", event_of(d, src), "--yes"]
            r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        finally:
            if staged:
                shutil.rmtree(staged, ignore_errors=True)

        ok, fail = (ok + 1, fail) if r.returncode == 0 else (ok, fail + 1)
        done = [ln for ln in (r.stdout or "").splitlines() if "[done]" in ln]
        print(f"[{i:3}/{len(ordered)}] {'ok  ' if r.returncode == 0 else 'FAIL'} "
              f"{len(media_files(d)):4}f {(time.time()-t0)/60:5.1f}m  {prefix}", flush=True)
        if done:
            print(f"          {done[-1].split('[done]')[-1].strip()}", flush=True)
        if r.returncode != 0:
            for ln in (r.stderr or r.stdout or "").strip().splitlines()[-3:]:
                print(f"          {ln[:160]}", flush=True)

    print(f"\nWAVE COMPLETE: {ok} ok, {fail} failed, {(time.time()-t0)/60:.1f} min", flush=True)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())