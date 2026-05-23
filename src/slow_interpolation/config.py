"""Pipeline configuration: dataclasses + YAML loader.

A single `PipelineConfig` bundles every dial the pipeline needs. YAML files
under `examples/configs/` populate one of these; programmatic users can also
construct them directly. No Pydantic dependency, validation is intentionally
minimal (trust internal code; boundaries are YAML files written by the user).

The `RenderProfile.standard()` and `RenderProfile.calm()` factories produce the
two profiles that match the legacy entry-point scripts (the latter is the
profile that produced the `*_calm.mp4` samples under `examples/outputs/`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Leaf configs
# ---------------------------------------------------------------------------


@dataclass
class ModelsConfig:
    """HuggingFace model identifiers. Resolved by diffusers via the HF cache."""

    sdxl_base: str = "stabilityai/stable-diffusion-xl-base-1.0"
    lightning_lora: str = "ByteDance/SDXL-Lightning"
    lightning_weight_name: str = "sdxl_lightning_4step_lora.safetensors"
    vae: str = "madebyollin/taesdxl"


@dataclass
class StyleConfig:
    """Domain LoRA + textual style scaffold.

    `lora_path` is either a local filesystem `Path` to a .safetensors file
    OR a `str` of the form `hf:<user>/<repo>` referencing a HuggingFace Hub
    LoRA. In the HF case, the pipeline auto-downloads to the HF cache on
    first use. `lora_filename` overrides the default filename convention
    (which is `<repo>.safetensors`) when the file inside the HF repo is
    named differently.
    """

    name: str
    lora_path: Path | str
    lora_scale: float
    prefix: str
    suffix: str = ""
    negative_prompt: str = ""
    lora_filename: str | None = None


@dataclass
class PromptConfig:
    """One segment prompt. The `denoising` field present in legacy SUBJECTS was
    never read by the generation loop and is intentionally absent.

    `negative_prompt` overrides `style.negative_prompt` for this segment only,
    enabling off-distribution endpoints (e.g. an A frame that needs strong
    anti-bloom CFG while B and C ride the default style negative).
    """

    label: str
    prompt: str
    negative_prompt: str | None = None


@dataclass
class SubjectConfig:
    """A/B/C/A-return prompts for one named subject."""

    name: str
    prompts: list[PromptConfig]


@dataclass
class ResolutionConfig:
    width: int = 1344
    height: int = 768


@dataclass
class FrameCounts:
    """Per-segment frame counts. Defaults match the horizontal entry-point
    variant (5/3/4/3) that produced every cloned sample MP4."""

    steady: int = 5
    transition: int = 3
    return_: int = 4
    warmup: int = 3


@dataclass
class NoiseConfig:
    """Which `NoiseSource` to use for the img2img walk + its parameters.

    `kind` names a source registered in `noise/__init__.py:build_noise_source`
    (currently `evolved` (default), `perlin`, `worley`, `simplex`, `fbm`,
    `image_derived`, `frequency_banded`). `params` is forwarded as kwargs to
    the source constructor. `walk_rate` is inherited from
    `RenderProfile.noise_walk_rate` if absent from `params`.
    """

    kind: str = "evolved"
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class RenderProfile:
    """The bag of "how aggressive is the drift" knobs: denoise schedule, noise
    walk, structural decay, temporal smoothing. Two presets (`standard`,
    `calm`) match the legacy entry-point variants."""

    # Steady-segment per-position denoise strengths (cycled with modulo).
    steady_strengths: list[float] = field(
        default_factory=lambda: [0.55, 0.55, 0.60, 0.55, 0.55, 0.65, 0.55, 0.60]
    )
    # Inter-segment transition strength (legacy entry points use a single value,
    # not the engine's 6-element ramp). Set <=0 to fall back to 0.65.
    transition_strength: float = 0.65

    # Return-segment scheme: strength ramps linearly across the return frames
    # while pixel-blend toward the anchor ramps quadratically up to a cap.
    return_strength_start: float = 0.50
    return_strength_end: float = 0.60
    return_pixel_blend_max: float = 0.20  # quadratic ease-in cap

    # Noise walk (see noise/evolved_walk.py).
    steady_noise_blend: float = 0.08
    transition_noise_blend: float = 0.15
    noise_walk_rate: float = 0.05

    # Pre-frame Gaussian blur radius applied to the prior frame before
    # re-encoding. Prevents fine-texture runaway. 0 disables (calm mode).
    structural_decay_radius: int = 2

    # Frequency-separated temporal smoother.
    smoothing_sigma: float = 1.5
    smoothing_window: int = 8
    smoothing_blur_radius: int = 16

    # Noise source selection. Defaults to the legacy EvolvedNoiseWalk.
    noise: NoiseConfig = field(default_factory=NoiseConfig)

    @classmethod
    def standard(cls) -> "RenderProfile":
        return cls()

    @classmethod
    def calm(cls) -> "RenderProfile":
        return cls(
            steady_strengths=[0.50, 0.50, 0.52, 0.50, 0.50, 0.54, 0.50, 0.52],
            transition_strength=0.52,
            return_strength_start=0.48,
            return_strength_end=0.55,
            return_pixel_blend_max=0.20,
            steady_noise_blend=0.04,
            transition_noise_blend=0.08,
            noise_walk_rate=0.02,
            structural_decay_radius=0,
            smoothing_sigma=1.8,
            smoothing_window=8,
            smoothing_blur_radius=16,
        )


@dataclass
class RIFEConfig:
    """Phase C interpolation.

    `edge_crop=0` is the default since the 2026-05-16 border-crop probe
    (`docs/findings/border-crop.md`) confirmed `crops_coords_top_left` plus the
    latent edge-suppression callback handle border artifacts in the SDXL 16:9
    training bucket; the historical 8 px post-RIFE crop is unnecessary. Re-set
    to 8 explicitly for legacy parity.
    """

    passes: int = 6  # 2^6 = 64x
    skip_boundary: int = 4
    edge_crop: int = 0
    sinusoidal: bool = False
    vendor_path: Path = field(default_factory=lambda: Path("vendor/rife_v425"))


@dataclass
class EncodingConfig:
    fps: int = 24
    quality: int = 5
    codec: str = "libx264"
    pixelformat: str = "yuv420p"


@dataclass
class BorderSuppressionConfig:
    """SDXL micro-conditioning + latent-edge callback parameters."""

    crops_coords_top_left: tuple[int, int] = (256, 256)
    original_size: tuple[int, int] = (1024, 1024)
    latent_edge_px: int = 3
    latent_edge_strength: float = 0.3


@dataclass
class PipelineConfig:
    """The full bundle. Composed from the leaf configs above."""

    style: StyleConfig
    subject: SubjectConfig
    render: RenderProfile = field(default_factory=RenderProfile.standard)
    frames: FrameCounts = field(default_factory=FrameCounts)
    resolution: ResolutionConfig = field(default_factory=ResolutionConfig)
    rife: RIFEConfig = field(default_factory=RIFEConfig)
    encoding: EncodingConfig = field(default_factory=EncodingConfig)
    borders: BorderSuppressionConfig = field(default_factory=BorderSuppressionConfig)
    models: ModelsConfig = field(default_factory=ModelsConfig)
    output_dir: Path = field(default_factory=lambda: Path("outputs"))
    output_name: str | None = None  # defaults to subject.name at render time


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------


def _coerce_paths(d: dict[str, Any], keys: list[str]) -> None:
    for k in keys:
        if k in d and d[k] is not None:
            d[k] = Path(d[k]).expanduser()


def _coerce_tuples(d: dict[str, Any], keys: list[str]) -> None:
    for k in keys:
        if k in d and d[k] is not None:
            d[k] = tuple(d[k])


def _build_style(d: dict[str, Any]) -> StyleConfig:
    # `lora_path` accepts either a local filesystem path or a
    # `hf:<user>/<repo>` HuggingFace Hub reference. HF strings stay as
    # strings; everything else coerces to a Path.
    raw = d.get("lora_path")
    if isinstance(raw, str) and raw.startswith("hf:"):
        d["lora_path"] = raw  # keep as str
    else:
        _coerce_paths(d, ["lora_path"])
    return StyleConfig(**d)


def _build_subject(d: dict[str, Any]) -> SubjectConfig:
    prompts = [PromptConfig(**p) for p in d["prompts"]]
    return SubjectConfig(name=d["name"], prompts=prompts)


def _build_render(d: dict[str, Any] | str | None) -> RenderProfile:
    if d is None:
        return RenderProfile.standard()
    if isinstance(d, str):
        return getattr(RenderProfile, d)()
    # Dict: support "profile: standard" / "calm" plus overrides.
    profile_name = d.pop("profile", "standard")
    base = getattr(RenderProfile, profile_name)()
    noise_raw = d.pop("noise", None)
    for k, v in d.items():
        setattr(base, k, v)
    if noise_raw is not None:
        base.noise = NoiseConfig(
            kind=noise_raw.get("kind", "evolved"),
            params=dict(noise_raw.get("params", {})),
        )
    return base


def _build_rife(d: dict[str, Any] | None) -> RIFEConfig:
    if d is None:
        return RIFEConfig()
    _coerce_paths(d, ["vendor_path"])
    return RIFEConfig(**d)


def _build_borders(d: dict[str, Any] | None) -> BorderSuppressionConfig:
    if d is None:
        return BorderSuppressionConfig()
    _coerce_tuples(d, ["crops_coords_top_left", "original_size"])
    return BorderSuppressionConfig(**d)


def load_pipeline_config(path: str | Path) -> PipelineConfig:
    """Parse a YAML file into a `PipelineConfig`."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    style = _build_style(raw["style"])
    subject = _build_subject(raw["subject"])
    render = _build_render(raw.get("render"))
    frames = FrameCounts(**raw["frames"]) if "frames" in raw else FrameCounts()
    resolution = (
        ResolutionConfig(**raw["resolution"]) if "resolution" in raw else ResolutionConfig()
    )
    rife = _build_rife(raw.get("rife"))
    encoding = EncodingConfig(**raw["encoding"]) if "encoding" in raw else EncodingConfig()
    borders = _build_borders(raw.get("borders"))
    models = ModelsConfig(**raw["models"]) if "models" in raw else ModelsConfig()

    output_dir = Path(raw.get("output_dir", "outputs")).expanduser()
    output_name = raw.get("output_name")

    return PipelineConfig(
        style=style,
        subject=subject,
        render=render,
        frames=frames,
        resolution=resolution,
        rife=rife,
        encoding=encoding,
        borders=borders,
        models=models,
        output_dir=output_dir,
        output_name=output_name,
    )
