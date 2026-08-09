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
    """HuggingFace model identifiers. Resolved by diffusers via the HF cache.

    Set `lightning_lora` to `null` in YAML to skip the Lightning fuse entirely
    and run the undistilled base model. The trailing-timestep scheduler swap is
    a Lightning requirement and is skipped with it.

    `vae_kind` selects the autoencoder: `tiny` loads `vae` as an
    `AutoencoderTiny` (TAESD, fast, ~1 GB saved, lossy) and `full` loads
    `vae_full` as an `AutoencoderKL`. The chain decodes and re-encodes once per
    keyframe, so TAESD's loss compounds across the render; `full` is the control
    for that. The two are separate fields on purpose: the latent scaling factors
    differ (TAESD 1.0, SDXL KL 0.13025) and each repo carries its own, so
    pointing one class at the other's repo produces silent colour garbage rather
    than an error.
    """

    sdxl_base: str = "stabilityai/stable-diffusion-xl-base-1.0"
    lightning_lora: str | None = "ByteDance/SDXL-Lightning"
    lightning_weight_name: str = "sdxl_lightning_4step_lora.safetensors"
    vae: str = "madebyollin/taesdxl"
    vae_full: str = "madebyollin/sdxl-vae-fp16-fix"
    vae_kind: str = "tiny"


@dataclass
class SamplingConfig:
    """Diffusion sampling dials.

    Previously hardcoded as `generate_keyframes` defaults and unreachable from
    YAML, which is why neither was ever swept. Note that diffusers img2img runs
    `int(num_inference_steps * strength)` actual denoising steps, so the two
    interact: `strength` sets how far back in the schedule each frame re-enters
    (the amount of change) while `num_inference_steps` sets how finely that same
    distance is traversed (the quality). At the shipped defaults of 4 steps and
    a steady strength of 0.55, every keyframe gets 2 denoising steps.
    """

    guidance_scale: float = 1.5
    num_inference_steps: int = 4


@dataclass
class ControlConfig:
    """SDXL ControlNet structural conditioning.

    The anchor at warmup seeds composition once and its influence decays; a
    pixel-space blend back toward it fights the model and smears the surface
    (both measured, 2026-08-08). ControlNet instead injects residuals into the
    UNet at EVERY denoising step of EVERY frame, so structure is part of what
    the model paints rather than something applied to the result.

    `image` is a fixed control map used on every frame, which pins composition
    for the whole clip while light and surface keep drifting. That is the
    palette-drift-on-stable-composition case the denoise schedule was tuned for.

    `guidance_end` is the important dial, not `scale`: at ~0.5 the structure is
    applied over the first half of each frame's denoising and the model is then
    free to paint, which is the mitigation for the traced-geometry look that
    high anchor strengths produced.

    Depth rather than canny on purpose: canny prints hard edges that read as
    line art under paint.
    """

    model: str = "diffusers/controlnet-depth-sdxl-1.0"
    image: Path | None = None
    # One map per PROMPT, cross-faded on the same t as the embedding SLERP. A
    # single fixed map forces one geometry on every stage, which is why a
    # wilderness stage came back with a city in it. With a list, stage 1 can be
    # empty shoreline and stage 3 a dense modern skyline, while shared elements
    # (the crag, Liberty's island) stay at identical coordinates in every map
    # and therefore persist across the whole cycle.
    images: list[Path] | None = None
    scale: float = 0.55
    guidance_start: float = 0.0
    guidance_end: float = 0.5


@dataclass
class MotionConfig:
    """Masked directional motion: one region physically moves, the rest does not.

    A second axis of change, independent of the light drift. See `motion.py` for
    why RIFE renders this correctly rather than blurring it: flow is non-zero
    over the displaced region and exactly zero over the static one, so water
    moves and rock stays sharp without either being asked to.

    `dy` is pixels PER KEYFRAME, positive downward, applied cumulatively as the
    chain walks. Keep it inside what optical flow can track across one pair:
    `dy` spread over `frames_per_pair` invented frames is the per-frame speed,
    and a few pixels per frame is comfortable. Large steps reintroduce exactly
    the blur `passes` was lowered to fix.

    The mask comes from the control map's dark region by default, which is where
    water already lives by convention, so no new asset is needed.
    """

    dx: int = 0
    dy: int = 0
    mask_threshold: int = 60
    mask_feather: int = 24
    mask_invert: bool = False
    # Advect only the high-frequency band above this blur sigma. 0 translates
    # the whole region, which moves the SUBJECT rather than the texture through
    # it and made attempt 1 a regression: the waterfall shortened from the top.
    hp_sigma: float = 6.0
    # Wrap the moving band rather than edge-filling it. Texture leaving the
    # bottom re-enters at the top, which is right for a steady fall, removes the
    # vacated strip and its artefacts, and closes the loop by construction.
    cyclic: bool = True
    # Coarse edge of the moving band. With this set, the advected band is
    # blur(hp_sigma) minus blur(band_hi) rather than everything finer than
    # hp_sigma. Measured on consecutive keyframes: finer than ~8 px does not
    # survive img2img (r = 0.05 to 0.31) and cannot carry motion at all, while
    # ~80 px and coarser is the silhouette and must stay put. So the usable
    # band is roughly 10 to 80.
    band_hi: float = 0.0


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

    # Per-segment LoRA strength, one entry per segment. When set, the style LoRA
    # is kept as a LIVE adapter instead of being fused, and the scale is passed
    # per call, so it can vary through the chain.
    #
    # Why: the LoRA is an asset on content it was trained on and a liability on
    # content it has never seen. Measured on v8, stages III (modern city) and IV
    # (burning city) have the softest keyframes and the highest per-frame change
    # of the five, because with no learned representation the model reconsiders
    # every frame rather than refining. SDXL base, meanwhile, knows a modern
    # skyline perfectly well. So drop the LoRA only where it hurts and let the
    # base model draw, with painterliness coming from the prompt instead.
    #
    # This works because the city is DISTANT and HAZY. Prompt-level painterliness
    # is generic close up but adequate for a mass at the horizon, while the
    # foreground crag, shore and sky keep the LoRA at full strength.
    lora_scale_per_segment: list[float] | None = None

    def scale_at(self, seg: int) -> float:
        if self.lora_scale_per_segment and seg < len(self.lora_scale_per_segment):
            return self.lora_scale_per_segment[seg]
        return self.lora_scale


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

    # Per-segment overrides, one entry per segment (len(prompts) - 1). A single
    # global `steady` means every stage gets equal screen time, so a narrative
    # cycle cannot linger on its climax. These let it: e.g. [10, 12, 26, 14, 10]
    # spends more than twice as long on segment 2 as on segment 0. None = uniform.
    steady_per_segment: list[int] | None = None
    transition_per_segment: list[int] | None = None

    def steady_at(self, seg: int) -> int:
        if self.steady_per_segment and seg < len(self.steady_per_segment):
            return self.steady_per_segment[seg]
        return self.steady

    def transition_at(self, seg: int) -> int:
        if self.transition_per_segment and seg < len(self.transition_per_segment):
            return self.transition_per_segment[seg]
        return self.transition


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

    # Per-frame pixel blend back toward the post-warmup anchor, applied to EVERY
    # steady and transition frame rather than only the return segment.
    #
    # `anchor_image` seeds composition once, at the warmup, and its influence
    # then decays as the walk proceeds: the landmark appears in the first second
    # and morphs away (measured, 2026-08-08). This holds it. The target is the
    # post-warmup frame, not the raw source image, because that frame is the
    # structure already rendered in the LoRA's hand; blending toward the flat
    # source sketch would inject grey geometry instead.
    #
    # Small values only. This competes directly with the drift, so 0.25+ starts
    # freezing the piece into a still. 0 keeps the old behaviour exactly.
    anchor_reassert: float = 0.0

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
    sampling: SamplingConfig = field(default_factory=SamplingConfig)
    control: ControlConfig | None = None
    motion: MotionConfig | None = None
    rife: RIFEConfig = field(default_factory=RIFEConfig)
    encoding: EncodingConfig = field(default_factory=EncodingConfig)
    borders: BorderSuppressionConfig = field(default_factory=BorderSuppressionConfig)
    models: ModelsConfig = field(default_factory=ModelsConfig)
    output_dir: Path = field(default_factory=lambda: Path("outputs"))
    output_name: str | None = None  # defaults to subject.name at render time

    # Structural seed. The warmup normally starts from pure random pixels at
    # strength 0.85, which is text2img in disguise: the model composes from the
    # prompt alone, so composition always comes from the LoRA's prior. Point
    # `anchor_image` at a real photograph or a massing sketch and the whole
    # chain inherits that geometry instead, while the LoRA supplies the surface.
    # `anchor_strength` is the FIRST warmup pass only; lower keeps more of the
    # source structure. 0.85 (the noise default) keeps almost none.
    anchor_image: Path | None = None
    anchor_strength: float = 0.65

    # Reproducibility. Left at None the warmup canvas comes from an unseeded
    # `np.random.randint` and no generator reaches the pipeline, so a render is
    # a one-off: re-running the same config gives a different picture and a
    # composition you liked cannot be recovered except by pointing
    # `anchor_image` at a frame of the render that produced it. Set an int and
    # both the canvas and the sampler become deterministic, which is what makes
    # a delivery iterable (change one dial, keep the picture).
    #
    # Determinism is per (seed, config, hardware): the same seed on a different
    # GPU or a different diffusers build will not match frame for frame.
    seed: int | None = None


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
    sampling = SamplingConfig(**raw["sampling"]) if "sampling" in raw else SamplingConfig()
    control = None
    if raw.get("control"):
        cd = dict(raw["control"])
        _coerce_paths(cd, ["image"])
        if cd.get("images"):
            cd["images"] = [Path(p).expanduser() for p in cd["images"]]
        control = ControlConfig(**cd)
    motion = MotionConfig(**raw["motion"]) if raw.get("motion") else None
    rife = _build_rife(raw.get("rife"))
    encoding = EncodingConfig(**raw["encoding"]) if "encoding" in raw else EncodingConfig()
    borders = _build_borders(raw.get("borders"))
    models = ModelsConfig(**raw["models"]) if "models" in raw else ModelsConfig()

    output_dir = Path(raw.get("output_dir", "outputs")).expanduser()
    output_name = raw.get("output_name")
    anchor_raw = raw.get("anchor_image")
    anchor_image = Path(anchor_raw).expanduser() if anchor_raw else None
    anchor_strength = float(raw.get("anchor_strength", 0.65))
    seed_raw = raw.get("seed")
    seed = int(seed_raw) if seed_raw is not None else None

    return PipelineConfig(
        style=style,
        subject=subject,
        render=render,
        frames=frames,
        resolution=resolution,
        sampling=sampling,
        control=control,
        motion=motion,
        rife=rife,
        encoding=encoding,
        borders=borders,
        models=models,
        output_dir=output_dir,
        output_name=output_name,
        anchor_image=anchor_image,
        anchor_strength=anchor_strength,
        seed=seed,
    )
