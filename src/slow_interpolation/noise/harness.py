"""Noise-source comparison harness.

Renders the same A/B/C subject across N noise sources and writes a contact
sheet for visual comparison. Not part of the production Pipeline. Lives in
`noise/` because it is the natural home for noise-research scaffolding.

Usage:

    python -m slow_interpolation.noise.harness <config.yaml> --noise-set structured
    python -m slow_interpolation.noise.harness <config.yaml> --noise-set full \
        --image-ref path/to/reference.jpg --contact-sheet

Outputs:

- `<output_dir>/staging/<subject>_<source_name>/keyframes/0000.png ...`
- `<output_dir>/staging/<subject>_contact_sheet_<noise_set>.png` (with --contact-sheet)
- `<output_dir>/staging/<subject>_noise_preview_<noise_set>.png` (with --preview)

The harness loads the SDXL stack once and reuses it across noise sources, so
the marginal cost of an extra source is one keyframe-render pass per subject
(not a full pipeline cold start).

The `--preview` flag produces a CPU-only contact sheet of the raw noise
patterns themselves (no diffusion), so you can sanity-check the source
configurations without burning GPU time. Use it first when adding a new
preset entry.
"""

from __future__ import annotations

import argparse
import dataclasses
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image, ImageDraw

from ..config import PipelineConfig, load_pipeline_config
from .base import NoiseSource
from .evolved_walk import EvolvedNoiseWalk
from .frequency_banded import FrequencyBandedNoise
from .image_derived import ImageDerivedNoise
from .sources import FBMNoise, PerlinNoise, SimplexNoise, WorleyNoise


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------


def build_preset(
    name: str,
    walk_rate: float,
    image_ref: Path | None = None,
    seed: int = 0,
) -> list[tuple[str, NoiseSource]]:
    """Return a list of `(label, NoiseSource)` for a named preset.

    `walk_rate` is sourced from the active `RenderProfile.noise_walk_rate` so
    all the structured sources walk at the same rate as production.
    `image_ref` is required for the "full" preset; it is the reference image
    fed into `ImageDerivedNoise`.
    """
    structured: list[tuple[str, NoiseSource]] = [
        ("evolved_walk", EvolvedNoiseWalk(walk_rate=walk_rate)),
        ("perlin", PerlinNoise(feature_size=64.0, walk_rate=walk_rate, seed=seed)),
        ("worley", WorleyNoise(cell_density=300.0, walk_rate=walk_rate, seed=seed)),
        ("simplex", SimplexNoise(feature_size=64.0, walk_rate=walk_rate, seed=seed)),
        ("fbm", FBMNoise(feature_size=128.0, octaves=4, walk_rate=walk_rate, seed=seed)),
    ]
    if name == "structured":
        return structured
    if name == "full":
        extras: list[tuple[str, NoiseSource]] = []
        if image_ref is not None:
            extras.append(
                ("image_derived", ImageDerivedNoise(image_ref, use_vae=False))
            )
        extras.append(
            (
                "frequency_banded",
                FrequencyBandedNoise(
                    sources=[
                        WorleyNoise(cell_density=500.0, seed=seed),
                        PerlinNoise(feature_size=24.0, seed=seed),
                        FBMNoise(feature_size=64.0, octaves=3, seed=seed),
                    ],
                    band_sigmas=[0.0, 3.0, 9.0],
                    band_weights=[0.5, 1.0, 0.7],
                    walk_rate=walk_rate,
                ),
            )
        )
        return structured + extras
    raise ValueError(f"Unknown preset: {name!r} (choose from 'structured', 'full')")


# ---------------------------------------------------------------------------
# Per-source render
# ---------------------------------------------------------------------------


def _staging_dir(config: PipelineConfig, source_name: str) -> Path:
    return (
        config.output_dir
        / "staging"
        / f"{config.subject.name}_{source_name}"
        / "keyframes"
    )


def _per_source_config(config: PipelineConfig, source_name: str) -> PipelineConfig:
    """Return a config copy whose `output_name` is `<subject>_<source>`.

    This routes the per-source keyframes through `Pipeline.staging_dir` to
    `<output_dir>/staging/<subject>_<source>/keyframes/` and the per-source
    MP4 to `<output_dir>/<subject>_<source>.mp4`.
    """
    return dataclasses.replace(
        config, output_name=f"{config.subject.name}_{source_name}"
    )


def render_all_sources(
    config: PipelineConfig,
    sources: Sequence[tuple[str, NoiseSource]],
) -> list[tuple[str, Path]]:
    """Run Phase A (keyframes only) once per source, sharing the SDXL pipe.

    Returns a list of `(source_name, keyframes_dir)`. Phase A.5 smoothing and
    Phase C interpolation are skipped. Use `render_all_sources_full` to also
    smooth, interpolate, and encode an MP4 per source.
    """
    # Local imports so the harness can be imported in CPU-only environments
    # for dry-preview without pulling in torch / diffusers at module load.
    from ..keyframes import (
        generate_keyframes,
        load_sdxl_pipeline,
        unload_sdxl_pipeline,
    )

    per_source_dirs: list[tuple[str, Path]] = []
    pipe = load_sdxl_pipeline(config)
    try:
        for source_name, noise_source in sources:
            noise_source.reset()
            out_dir = _staging_dir(config, source_name)
            out_dir.mkdir(parents=True, exist_ok=True)
            print(f"[harness] rendering '{source_name}' -> {out_dir}")
            generate_keyframes(
                pipe,
                config,
                output_dir=out_dir,
                noise_walker=noise_source,
            )
            per_source_dirs.append((source_name, out_dir))
    finally:
        unload_sdxl_pipeline(pipe)
    return per_source_dirs


def render_all_sources_full(
    config: PipelineConfig,
    sources: Sequence[tuple[str, NoiseSource]],
) -> tuple[list[tuple[str, Path]], list[tuple[str, Path]]]:
    """Full pipeline render per source: Phase A + A.5 + C + D.

    SDXL is loaded once and used for every source's keyframes pass (the bulk
    of GPU time). Then SDXL is unloaded and each source is smoothed and
    RIFE-interpolated to its own MP4 at `outputs/<subject>_<source>.mp4`.

    Returns `(per_source_keyframe_dirs, per_source_mp4_paths)`. Either list
    may be partial if a later source fails (each source's MP4 is written
    independently).
    """
    from ..keyframes import (
        generate_keyframes,
        load_sdxl_pipeline,
        unload_sdxl_pipeline,
    )
    from ..pipeline import Pipeline

    # Phase A for every source (shared SDXL).
    per_source: list[tuple[str, Pipeline, Path]] = []
    pipe = load_sdxl_pipeline(config)
    try:
        for source_name, noise_source in sources:
            noise_source.reset()
            per_source_cfg = _per_source_config(config, source_name)
            pipeline = Pipeline(per_source_cfg)
            kf_dir = pipeline.keyframes_dir
            kf_dir.mkdir(parents=True, exist_ok=True)
            print(f"[harness] keyframes '{source_name}' -> {kf_dir}")
            generate_keyframes(
                pipe,
                per_source_cfg,
                output_dir=kf_dir,
                noise_walker=noise_source,
            )
            per_source.append((source_name, pipeline, kf_dir))
    finally:
        unload_sdxl_pipeline(pipe)

    # Phase A.5 + C + D, per source. SDXL is gone; RIFE loads inside each
    # interpolate_and_encode call via its context manager.
    per_source_dirs: list[tuple[str, Path]] = []
    mp4_paths: list[tuple[str, Path]] = []
    for source_name, pipeline, kf_dir in per_source:
        print(f"[harness] smoothing '{source_name}'")
        pipeline.smooth_keyframes()
        print(f"[harness] interpolate+encode '{source_name}' -> {pipeline.output_path}")
        mp4 = pipeline.interpolate_and_encode()
        per_source_dirs.append((source_name, kf_dir))
        mp4_paths.append((source_name, mp4))
        print(f"[harness] done '{source_name}': {mp4}")
    return per_source_dirs, mp4_paths


# ---------------------------------------------------------------------------
# Contact sheets
# ---------------------------------------------------------------------------


def _label_strip(images: Sequence[Image.Image], labels: Sequence[str]) -> Image.Image:
    """Compose images horizontally with text labels in a top gutter."""
    gutter = 28
    pad = 8
    total_w = sum(im.width for im in images) + pad * (len(images) - 1)
    total_h = max(im.height for im in images) + gutter
    sheet = Image.new("RGB", (total_w, total_h), (16, 16, 16))
    draw = ImageDraw.Draw(sheet)
    x = 0
    for img, lbl in zip(images, labels):
        sheet.paste(img, (x, gutter))
        draw.text((x + 4, 6), lbl, fill=(230, 230, 220))
        x += img.width + pad
    return sheet


def build_contact_sheet(
    per_source_dirs: Sequence[tuple[str, Path]],
    output_path: Path,
    frame_index: int = 0,
    max_height: int = 400,
) -> Path | None:
    """Compose a horizontal contact sheet from the Nth keyframe of each source."""
    images: list[Image.Image] = []
    labels: list[str] = []
    for source_name, kf_dir in per_source_dirs:
        frames = sorted(kf_dir.glob("*.png"))
        if not frames:
            print(f"[harness] no frames in {kf_dir}, skipping")
            continue
        idx = min(frame_index, len(frames) - 1)
        img = Image.open(frames[idx]).convert("RGB")
        if img.height > max_height:
            scale = max_height / img.height
            img = img.resize((int(img.width * scale), max_height), Image.LANCZOS)
        images.append(img)
        labels.append(source_name)

    if not images:
        return None
    sheet = _label_strip(images, labels)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)
    return output_path


def build_noise_preview(
    sources: Sequence[tuple[str, NoiseSource]],
    output_path: Path,
    width: int = 256,
    height: int = 256,
    n_steps: int = 20,
    blend_pct: float = 1.0,
) -> Path:
    """CPU-only preview: render each source's noise pattern in isolation.

    Steps each source `n_steps` times against a mid-gray canvas (to let the
    persistent tensor settle) then writes the final image. With `blend_pct=1.0`
    the resulting strip shows pure noise. Use this to sanity-check a new
    preset entry before paying for SDXL renders.
    """
    base = Image.new("RGB", (width, height), (128, 128, 128))
    images: list[Image.Image] = []
    labels: list[str] = []
    for source_name, src in sources:
        src.reset()
        img = base
        for _ in range(n_steps):
            img = src.blend(base, blend_pct=blend_pct)
        images.append(img)
        labels.append(source_name)
        src.reset()
    sheet = _label_strip(images, labels)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)
    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Render the same A/B/C subject across N noise sources "
        "and write a contact sheet for visual comparison."
    )
    parser.add_argument("config", type=Path, help="Pipeline YAML config.")
    parser.add_argument(
        "--noise-set",
        default="structured",
        choices=["structured", "full"],
        help="Preset of noise sources to compare.",
    )
    parser.add_argument(
        "--image-ref",
        type=Path,
        default=None,
        help="Reference image for ImageDerivedNoise (full preset only).",
    )
    parser.add_argument(
        "--contact-sheet",
        action="store_true",
        help="Build a contact sheet PNG after rendering.",
    )
    parser.add_argument(
        "--frame-index",
        type=int,
        default=0,
        help="Which keyframe to put in the contact sheet (default 0 = first A frame).",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Skip diffusion. Render only the raw noise patterns (CPU only).",
    )
    parser.add_argument(
        "--full-pipeline",
        action="store_true",
        help="After keyframes, also run Phase A.5 smoothing + Phase C RIFE "
        "interpolation + Phase D encoding, producing one MP4 per source at "
        "outputs/<subject>_<source>.mp4. Adds substantial GPU time.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Seed for stochastic noise generators (does not affect SDXL sampling).",
    )
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="Comma-separated list of source names to render (filters the preset). "
        "Useful for re-rendering one or two sources after a config change.",
    )
    parser.add_argument(
        "--structural-decay-radius",
        type=int,
        default=None,
        help="Override render.structural_decay_radius from the YAML. Set to 0 to "
        "disable the pre-frame Gaussian blur (the high-freq injection that "
        "white-noise sources rely on, which structured noise cannot provide).",
    )
    parser.add_argument(
        "--output-suffix",
        type=str,
        default=None,
        help="String appended to subject.name when computing output paths. "
        "Use to keep re-renders from overwriting earlier ones, e.g. "
        "--output-suffix no_decay produces 'tcole_valley_no_decay_perlin.mp4'.",
    )
    args = parser.parse_args(argv)

    config = load_pipeline_config(args.config)

    # CLI overrides on the loaded config (kept here so the YAML file is not
    # mutated as a side effect of a research-time flag).
    if args.structural_decay_radius is not None:
        config.render.structural_decay_radius = args.structural_decay_radius
        print(f"[harness] override structural_decay_radius -> {args.structural_decay_radius}")
    if args.output_suffix:
        config = dataclasses.replace(
            config,
            subject=dataclasses.replace(
                config.subject,
                name=f"{config.subject.name}_{args.output_suffix}",
            ),
        )
        print(f"[harness] output suffix -> subject.name='{config.subject.name}'")

    sources = build_preset(
        args.noise_set,
        walk_rate=config.render.noise_walk_rate,
        image_ref=args.image_ref,
        seed=args.seed,
    )

    if args.only:
        wanted = {n.strip() for n in args.only.split(",") if n.strip()}
        sources = [(n, s) for n, s in sources if n in wanted]
        if not sources:
            raise SystemExit(
                f"--only {args.only!r} filtered out all sources. "
                f"Available: {[n for n, _ in build_preset(args.noise_set, walk_rate=0.05, image_ref=args.image_ref)]}"
            )
        print(f"[harness] filtered to: {[n for n, _ in sources]}")

    staging_root = config.output_dir / "staging"
    staging_root.mkdir(parents=True, exist_ok=True)

    if args.preview:
        preview_path = staging_root / f"{config.subject.name}_noise_preview_{args.noise_set}.png"
        out = build_noise_preview(
            sources,
            preview_path,
            width=config.resolution.width // 4,
            height=config.resolution.height // 4,
        )
        print(f"[harness] noise preview: {out}")
        return

    if args.full_pipeline:
        per_source_dirs, mp4_paths = render_all_sources_full(config, sources)
        print("[harness] all MP4s written:")
        for source_name, mp4 in mp4_paths:
            print(f"  {source_name}: {mp4}")
    else:
        per_source_dirs = render_all_sources(config, sources)

    if args.contact_sheet:
        sheet_path = staging_root / f"{config.subject.name}_contact_sheet_{args.noise_set}.png"
        out = build_contact_sheet(
            per_source_dirs,
            sheet_path,
            frame_index=args.frame_index,
        )
        if out:
            print(f"[harness] contact sheet: {out}")


if __name__ == "__main__":
    main()
