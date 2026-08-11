"""Conform a slow-interpolation render to a fixed delivery spec.

Written for an LED-wall placement, but the pattern is generic: render at a
validated SDXL bucket, crop to the delivery aspect, lanczos upscale to the
exact pixel size, then resample the loop to an exact frame count and fps.

Never render natively at an odd delivery resolution. Off-bucket resolutions
reintroduce the border artifacts that `edge_crop` was added to suppress; see
docs/findings/upscale-source-resolution.md.

The resample is deliberately a retime, not a truncation. The pipeline's wrap
pass closes the loop across the full source, so cutting the tail instead of
retiming would break the seamless loop on repeat plays.

Usage:
    python tools/conform.py --screen a   --src outputs/<render>.mp4
    python tools/conform.py --screen bc  --src outputs/<render>.mp4

--crop-x / --crop-y override the default centre crop when the composition
sits off centre (pick these by eye from a contact sheet, do not assume centre).
Top-aligning rather than centring is often correct: a centre band on an
extreme-ratio crop slices the top off tall subjects.

Add a SCREENS entry for each new delivery target.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Delivery specs per screen. Read these off the venue's own spec sheet and
# transcribe carefully: a spec written "2736px H x 912px W" is PORTRAIT, and
# reading it as landscape is the easiest way to ruin a deliverable.
SCREENS = {
    "a": {"w": 912, "h": 2736, "label": "screen A (portrait 1:3)"},
    "bc": {"w": 1728, "h": 540, "label": "screen B/C (landscape 16:5)"},
}

TARGET_FRAMES = 300
TARGET_FPS = 30


def probe(src: Path) -> tuple[int, int, int]:
    """Return (width, height, nb_frames) for the source video."""
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-count_frames",
            "-show_entries", "stream=width,height,nb_read_frames",
            "-of", "json", str(src),
        ],
        capture_output=True, text=True, check=True,
    ).stdout
    s = json.loads(out)["streams"][0]
    return int(s["width"]), int(s["height"]), int(s["nb_read_frames"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--screen", required=True, choices=sorted(SCREENS))
    ap.add_argument("--src", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--crop-x", type=int, default=None, help="left edge of crop; default centre")
    ap.add_argument("--crop-y", type=int, default=None, help="top edge of crop; default centre")
    ap.add_argument("--crf", type=int, default=16)
    args = ap.parse_args()

    spec = SCREENS[args.screen]
    tw, th = spec["w"], spec["h"]
    src = args.src
    if not src.exists():
        print(f"source not found: {src}", file=sys.stderr)
        return 1

    sw, sh, nframes = probe(src)
    if nframes < TARGET_FRAMES:
        print(
            f"refusing: source has {nframes} frames, fewer than the {TARGET_FRAMES} "
            f"required. Retiming up would invent motion. Re-render with more keyframes.",
            file=sys.stderr,
        )
        return 1

    # Largest crop of the target aspect ratio that fits inside the source.
    target_ar = tw / th
    if sw / sh > target_ar:
        ch = sh
        cw = int(round(sh * target_ar))
    else:
        cw = sw
        ch = int(round(sw / target_ar))
    cw -= cw % 2
    ch -= ch % 2

    cx = (sw - cw) // 2 if args.crop_x is None else args.crop_x
    cy = (sh - ch) // 2 if args.crop_y is None else args.crop_y
    cx = max(0, min(cx, sw - cw))
    cy = max(0, min(cy, sh - ch))

    out = args.out or src.with_name(f"{src.stem}__{args.screen}_{tw}x{th}.mp4")

    # Retime the whole loop into 10.000 s, then resample to 30 fps.
    pts_scale = TARGET_FRAMES / nframes
    vf = (
        f"crop={cw}:{ch}:{cx}:{cy},"
        f"scale={tw}:{th}:flags=lanczos,"
        f"setpts=PTS*{pts_scale:.10f},"
        f"fps={TARGET_FPS}"
    )

    print(f"screen      : {spec['label']}")
    print(f"source      : {sw}x{sh}, {nframes} frames")
    print(f"crop        : {cw}x{ch} at ({cx},{cy})")
    print(f"upscale     : {cw}x{ch} -> {tw}x{th}  ({tw / cw:.3f}x)")
    print(f"retime      : {nframes} -> {TARGET_FRAMES} frames @ {TARGET_FPS} fps (10.000 s)")

    cmd = [
        "ffmpeg", "-y", "-v", "error", "-i", str(src),
        "-vf", vf,
        "-frames:v", str(TARGET_FRAMES),
        "-r", str(TARGET_FPS),
        "-c:v", "libx264", "-profile:v", "high", "-preset", "slow",
        "-crf", str(args.crf), "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", "-an",
        str(out),
    ]
    subprocess.run(cmd, check=True)

    ow, oh, on = probe(out)
    ok = (ow, oh, on) == (tw, th, TARGET_FRAMES)
    print(f"wrote       : {out}")
    print(f"verified    : {ow}x{oh}, {on} frames, {on / TARGET_FPS:.3f} s  {'OK' if ok else 'MISMATCH'}")

    # Carry the run manifest forward onto the delivery file.
    #
    # PROVENANCE DIES AT THE COPY. A conformed file inherits none of the record of
    # what made it, so once it is renamed for a client -- which is exactly what
    # happens to a delivery, e.g. "VANDALO RUINS_..._NY1087A_090226.mp4" -- there is
    # no path back to the run at all. Measured 2026-08-11 while grouping the Glance
    # field by style LoRA: 13 of 30 assets could not name the LoRA that produced
    # them, and 9 of those were delivery copies. The suffix-stripping fallback in
    # glance_export only rescues files that still carry the conform suffix; a rename
    # defeats it, and a rename is the normal end of this pipeline.
    #
    # Writing a sibling manifest here fixes it at the only point that still knows.
    # `conformed_from` records the parent so the chain stays walkable even after the
    # file is renamed, as long as the manifest travels with it.
    src_man = None
    for cand in (src.with_name(src.stem + ".manifest.json"),):
        if cand.is_file():
            src_man = cand
            break
    if src_man:
        try:
            man = json.loads(src_man.read_text(encoding="utf-8"))
        except Exception:
            man = {}
        man["conformed_from"] = src.name
        man["conform_screen"] = args.screen
        man["conform_target"] = f"{tw}x{th}"
        out.with_name(out.stem + ".manifest.json").write_text(
            json.dumps(man, indent=2), encoding="utf-8")
        print(f"provenance  : {out.stem}.manifest.json (from {src_man.name})")
    else:
        # Say so rather than leaving a silent gap: an unprovenanced delivery is the
        # thing that later cannot be grouped, credited, or reproduced.
        print(f"provenance  : NONE -- {src.name} has no manifest, so {out.name} "
              f"carries no record of the run that made it")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())