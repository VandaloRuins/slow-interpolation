"""Close a keyframe chain into a loop, RIFE it locally, encode to exactly 300 frames.

Local and free: no Modal, no diffusion. Takes the authored states from
`banana_keyframes.py`, interpolates every pair INCLUDING the wrap, and encodes a
10 s / 300-frame loop.

Two things it does that a hand-rolled ffmpeg call does not, both of which caught a
real defect on 2026-08-14:

1. **It makes the closure choice explicit.** Palindrome is correct for an
   ACCUMULATION, where the return leg reuses the forward states in reverse and the
   seam is therefore pixel-exact. It is WRONG for a chain that already returns to
   its own frame 0 (an ivy that grows AND withers inside the loop): palindroming
   that replays the whole arc backwards and doubles the piece. That shipped once
   and was caught only by the frame count. Pass `--no-palindrome` for a
   self-closing chain. Full taxonomy: docs/findings/loop-closure-taxonomy.md.

2. **It prints the retime ratio BEFORE encoding.** Frame-drop ratios near 1.5 are
   the documented judder; duplication is invisible. A 15-state chain at 5 passes
   produced 448 frames, a 1.49x drop sitting exactly on the threshold; dropping to
   4 passes gave 224 frames and a 1.34x duplication instead. Read the line, then
   choose `--passes`.

Arithmetic: pairs = states (closed loop, wrap included), or `2 * states - 2` under
palindrome. Frames per pair = `2 ** passes`.

    python tools/loop_render.py --accum outputs/arendt/<name>/accum \
        --out outputs/arendt/<name>.mp4 --width 1408 --height 768 --passes 5
"""
from __future__ import annotations

import argparse
import glob
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
VENDOR = ROOT / "vendor" / "rife_v425"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--accum", required=True, help="dir of authored states (PNGs)")
    ap.add_argument("--out", required=True, help="output mp4")
    ap.add_argument("--width", type=int, required=True, help="RIFE working width, %%64")
    ap.add_argument("--height", type=int, required=True, help="RIFE working height, %%64")
    ap.add_argument("--passes", type=int, default=5,
                    help="RIFE passes; each pair yields 2**passes frames")
    ap.add_argument("--no-palindrome", dest="palindrome", action="store_false",
                    default=True,
                    help="the states already form a closed loop (self-erasing or "
                         "already-returning arc). Without this the arc is replayed "
                         "backwards and the piece doubles.")
    ap.add_argument("--keep-frames", action="store_true",
                    help="keep the intermediate PNG directory")
    a = ap.parse_args()

    if a.width % 64 or a.height % 64:
        print(f"RIFE needs w,h % 64 == 0; got {a.width}x{a.height}", file=sys.stderr)
        return 1

    from slow_interpolation.interpolation.rife import RIFEInterpolator

    paths = sorted(glob.glob(str(Path(a.accum) / "*.png")))
    if not paths:
        print(f"no PNGs in {a.accum}", file=sys.stderr)
        return 1
    states = [Image.open(p).convert("RGB").resize((a.width, a.height), Image.LANCZOS)
              for p in paths]
    k = len(states)
    seq = list(range(k)) + (list(range(k - 2, 0, -1)) if a.palindrome else [])
    print(f"{k} states -> {len(seq)} loop positions, {len(seq)} pairs incl. wrap "
          f"({'palindrome' if a.palindrome else 'already closed'})")

    frames: list[np.ndarray] = []
    with RIFEInterpolator(VENDOR, n_passes=a.passes, skip_boundary=0, edge_crop=0) as rife:
        for i, si in enumerate(seq):
            nxt = seq[(i + 1) % len(seq)]
            frames.append(np.array(states[si]))
            frames.extend(rife.interpolate_pair(states[si], states[nxt]))
            print(f"  pair {i + 1}/{len(seq)}  ({si} -> {nxt})  total {len(frames)}",
                  flush=True)

    total = len(frames)
    ratio = total / 300
    verdict = f"DROP {ratio:.2f}x" if ratio > 1 else f"DUPLICATE {1 / ratio:.2f}x"
    flag = "  <-- near the 1.5 judder threshold, prefer fewer passes" if ratio >= 1.45 else ""
    print(f"\n{total} frames -> 300 : {verdict}{flag}")

    tmp = Path(a.out).with_suffix(".frames")
    tmp.mkdir(parents=True, exist_ok=True)
    for i, f in enumerate(frames):
        Image.fromarray(f).save(tmp / f"{i:05d}.png")

    cmd = ["ffmpeg", "-y", "-v", "error", "-framerate", f"{total / 10:.4f}",
           "-i", str(tmp / "%05d.png"), "-vf", "fps=30", "-frames:v", "300",
           "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(a.out)]
    if subprocess.run(cmd).returncode != 0:
        print("ffmpeg FAILED", file=sys.stderr)
        return 1

    if not a.keep_frames:
        for p in tmp.glob("*.png"):
            p.unlink()
        tmp.rmdir()

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
         "-show_entries", "stream=width,height,nb_read_frames", "-of", "csv=p=0",
         str(a.out)], capture_output=True, text=True).stdout.strip()
    print(f"verified: {probe}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
