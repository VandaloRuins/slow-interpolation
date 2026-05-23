"""CLI entry point.

Usage:
    python -m slow_interpolation.run <config.yaml>

Loads the YAML, runs all four pipeline phases, prints the output path.
Per-phase progress is whatever the underlying modules emit (diffusers /
imageio progress bars on the relevant phases).

For partial runs (e.g. re-encoding existing keyframes), use the API directly:

    from slow_interpolation import Pipeline, load_pipeline_config
    p = Pipeline(load_pipeline_config(...))
    p.interpolate_and_encode()
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .config import load_pipeline_config
from .pipeline import Pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m slow_interpolation.run",
        description="Render a slow-interpolation clip from a YAML config.",
    )
    parser.add_argument("config", type=Path, help="path to a YAML pipeline config")
    parser.add_argument(
        "--skip-keyframes",
        action="store_true",
        help="reuse existing PNGs in the staging dir, run only smoothing + interpolation",
    )
    parser.add_argument(
        "--skip-smoothing",
        action="store_true",
        help="skip Phase A.5 temporal smoothing (debug)",
    )
    args = parser.parse_args(argv)

    cfg = load_pipeline_config(args.config)
    pipeline = Pipeline(cfg)

    print(f"[slow-interpolation] config: {args.config}")
    print(f"[slow-interpolation] subject: {cfg.subject.name}")
    print(f"[slow-interpolation] style:   {cfg.style.name} (LoRA scale {cfg.style.lora_scale})")
    print(f"[slow-interpolation] expected keyframes: {pipeline.expected_keyframe_count()}")
    print(f"[slow-interpolation] staging: {pipeline.keyframes_dir}")
    print(f"[slow-interpolation] output:  {pipeline.output_path}")

    t0 = time.perf_counter()

    if not args.skip_keyframes:
        print("[slow-interpolation] -- Phase A: keyframes --")
        tA = time.perf_counter()
        pipeline.generate_keyframes()
        print(f"[slow-interpolation]    Phase A: {time.perf_counter() - tA:.1f}s")

    if not args.skip_smoothing:
        print("[slow-interpolation] -- Phase A.5: temporal smoothing --")
        tS = time.perf_counter()
        pipeline.smooth_keyframes()
        print(f"[slow-interpolation]    Phase A.5: {time.perf_counter() - tS:.1f}s")

    print("[slow-interpolation] -- Phase C+D: RIFE + encode --")
    tC = time.perf_counter()
    out = pipeline.interpolate_and_encode()
    print(f"[slow-interpolation]    Phase C+D: {time.perf_counter() - tC:.1f}s")

    print(f"[slow-interpolation] TOTAL: {time.perf_counter() - t0:.1f}s")
    print(f"[slow-interpolation] wrote: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
