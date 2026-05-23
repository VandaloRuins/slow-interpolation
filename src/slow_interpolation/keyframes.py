"""Phase A: SDXL Lightning img2img keyframe generation.

Loads the SDXL base + Lightning 4-step LoRA + TAESD VAE + style LoRA stack,
then runs the img2img chain: warmup -> N forward segments (steady + SLERP
transition) -> return segment (gentle strength ramp + quadratic pixel blend
toward anchor) -> anchor frame appended for loop closure.

See `docs/pipeline.md` for the parameter rationale.
"""

from __future__ import annotations

import time
import traceback
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image, ImageFilter

from .borders import make_edge_suppression_callback
from .config import PipelineConfig
from .noise import EvolvedNoiseWalk, NoiseSource
from .prompts import encode_prompt, slerp_embeddings


# ---------------------------------------------------------------------------
# SDXL pipeline loader
# ---------------------------------------------------------------------------


def load_sdxl_pipeline(config: PipelineConfig) -> Any:
    """Load and configure the SDXL Lightning img2img pipeline + style LoRA."""
    from diffusers import (
        AutoencoderTiny,
        EulerDiscreteScheduler,
        StableDiffusionXLImg2ImgPipeline,
    )

    m = config.models

    pipe = StableDiffusionXLImg2ImgPipeline.from_pretrained(
        m.sdxl_base,
        torch_dtype=torch.float16,
        variant="fp16",
    ).to("cuda")

    # Lightning 4-step LoRA: fuse and unload. Scheduler must use trailing timesteps.
    pipe.load_lora_weights(m.lightning_lora, weight_name=m.lightning_weight_name)
    pipe.fuse_lora()
    pipe.unload_lora_weights()

    pipe.scheduler = EulerDiscreteScheduler.from_config(
        pipe.scheduler.config, timestep_spacing="trailing"
    )

    # TAESD VAE: fast, fp16-stable, ~1 GB saved vs full SDXL VAE.
    taesd = AutoencoderTiny.from_pretrained(m.vae, torch_dtype=torch.float16).to("cuda")
    pipe.vae = taesd
    pipe.safety_checker = None
    pipe.unet.to(memory_format=torch.channels_last)
    torch.cuda.empty_cache()

    # Style LoRA on top of fused Lightning. `style.lora_path` is either a
    # local filesystem path or a `hf:<user>/<repo>` HF Hub reference.
    style = config.style
    if style.lora_path:
        resolved = _resolve_lora_path(style.lora_path, style.lora_filename)
        if resolved is not None:
            _load_style_lora(pipe, resolved, style.lora_scale)
            torch.cuda.empty_cache()

    return pipe


def _resolve_lora_path(lora_path: Path | str, lora_filename: str | None) -> str | None:
    """Return a local filesystem path string for the style LoRA.

    Accepts either:
    - A `Path` pointing at a local .safetensors file (returns the str path if
      the file exists, else None).
    - A `str` of the form `hf:<user>/<repo>` that names a HuggingFace Hub LoRA
      repo. Downloads to the HF cache via `hf_hub_download` and returns the
      cached path. The filename inside the repo defaults to `<repo>.safetensors`
      unless `lora_filename` overrides it.
    """
    if isinstance(lora_path, str) and lora_path.startswith("hf:"):
        from huggingface_hub import hf_hub_download

        repo_id = lora_path[len("hf:"):]
        if "/" not in repo_id:
            raise ValueError(
                f"Invalid HF LoRA reference {lora_path!r}: expected 'hf:<user>/<repo>'."
            )
        filename = lora_filename or f"{repo_id.split('/', 1)[1]}.safetensors"
        return hf_hub_download(repo_id=repo_id, filename=filename)

    p = Path(lora_path)
    if p.exists():
        return str(p)
    return None


def _load_style_lora(pipe: Any, lora_path: str, lora_scale: float) -> None:
    """Load a style LoRA, with a UNet-only fallback for Kohya-format LoRAs.

    diffusers 0.31+ has a regression converting Kohya-format SDXL text-encoder
    LoRA keys: when the per-key rank dict ends up empty after the conversion,
    `get_peft_kwargs` crashes with `IndexError: list index out of range`. Style
    LoRAs trained with kohya_ss (the Thomas Cole and Casa del Suono checkpoints
    among them) trip this. The UNet portion is where ~95% of style adaptation
    lives, so dropping the text-encoder slice is style-equivalent.
    """
    try:
        pipe.load_lora_weights(lora_path)
    except IndexError:
        from safetensors.torch import load_file

        state_dict = load_file(lora_path)
        unet_only = {k: v for k, v in state_dict.items() if not k.startswith("lora_te")}
        pipe.load_lora_weights(unet_only)
    pipe.fuse_lora(lora_scale=lora_scale)
    pipe.unload_lora_weights()


def unload_sdxl_pipeline(pipe: Any) -> None:
    """Drop the pipeline and clear VRAM."""
    import gc

    del pipe
    gc.collect()
    torch.cuda.empty_cache()


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------


def _random_noise_image(width: int, height: int) -> Image.Image:
    arr = np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)
    return Image.fromarray(arr)


def _structural_decay(img: Image.Image, radius: int) -> Image.Image:
    if radius <= 0:
        return img
    return img.filter(ImageFilter.GaussianBlur(radius=radius))


def _pixel_blend_toward_anchor(
    current: Image.Image, anchor: Image.Image, alpha: float
) -> Image.Image:
    if alpha <= 0.0:
        return current
    cur_arr = np.array(current).astype(np.float32)
    anc_arr = np.array(anchor).astype(np.float32)
    blended = cur_arr * (1.0 - alpha) + anc_arr * alpha
    return Image.fromarray(blended.clip(0, 255).astype(np.uint8))


def _format_prompt(style_prefix: str, body: str, style_suffix: str) -> str:
    return f"{style_prefix}{body}{style_suffix}"


# ---------------------------------------------------------------------------
# Phase A: generate keyframes
# ---------------------------------------------------------------------------


def generate_keyframes(
    pipe: Any,
    config: PipelineConfig,
    output_dir: Path,
    noise_walker: NoiseSource | None = None,
    guidance_scale: float = 1.5,
    num_inference_steps: int = 4,
) -> int:
    """Run the Phase A img2img chain and write numbered PNGs into `output_dir`.

    Returns the number of keyframes written. Caller owns the SDXL pipe lifetime
    (use `load_sdxl_pipeline` + `unload_sdxl_pipeline`).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    style = config.style
    subject = config.subject
    render = config.render
    frames = config.frames
    res = config.resolution
    borders = config.borders

    if noise_walker is None:
        noise_walker = EvolvedNoiseWalk(walk_rate=render.noise_walk_rate)

    target_size = (res.width, res.height)
    callback = make_edge_suppression_callback(
        px=borders.latent_edge_px, strength=borders.latent_edge_strength
    )

    # Pre-encode every prompt (A, B, C, A-return). Each prompt may override the
    # style-level negative; falls back to style.negative_prompt when None.
    full_prompts = [_format_prompt(style.prefix, p.prompt, style.suffix) for p in subject.prompts]
    all_embeds = []
    for full, p_cfg in zip(full_prompts, subject.prompts):
        neg = p_cfg.negative_prompt if p_cfg.negative_prompt is not None else style.negative_prompt
        e, p, ne, np_ = encode_prompt(pipe, full, neg, guidance_scale)
        all_embeds.append((e, p, ne, np_))

    def _cfg_kwargs(seg_idx: int) -> dict[str, Any]:
        _, _, ne, np_ = all_embeds[seg_idx]
        if ne is None:
            return {}
        return {"negative_prompt_embeds": ne, "negative_pooled_prompt_embeds": np_}

    n_segments = len(subject.prompts) - 1
    current_img = _random_noise_image(res.width, res.height)
    frame_idx = 0

    def _pipe_call(
        image: Image.Image,
        embeds: torch.Tensor,
        pooled: torch.Tensor,
        cfg_kw: dict[str, Any],
        strength: float,
    ) -> Image.Image:
        result = pipe(
            prompt_embeds=embeds,
            pooled_prompt_embeds=pooled,
            **cfg_kw,
            image=image,
            strength=strength,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            crops_coords_top_left=borders.crops_coords_top_left,
            original_size=borders.original_size,
            target_size=target_size,
            callback_on_step_end=callback,
            callback_on_step_end_tensor_inputs=["latents"],
        ).images[0]
        return result

    # --- Warmup: establish from noise ---
    embeds_cur, pooled_cur, _, _ = all_embeds[0]
    cfg_kw = _cfg_kwargs(0)
    for wi in range(frames.warmup):
        strength = 0.85 if wi == 0 else 0.75
        input_img = noise_walker.blend(current_img, blend_pct=render.steady_noise_blend)
        current_img = _pipe_call(input_img, embeds_cur, pooled_cur, cfg_kw, strength)

    # Anchor = first coherent post-warmup frame. Used by the return segment
    # for pixel-space convergence and saved as the final keyframe for loop
    # closure (RIFE wrap-around in Phase C handles the rest).
    anchor_img = current_img.copy()

    # --- Forward segments + return ---
    for seg_idx in range(n_segments):
        embeds_cur, pooled_cur, _, _ = all_embeds[seg_idx]
        embeds_next, pooled_next, _, _ = all_embeds[seg_idx + 1]
        is_return = seg_idx == n_segments - 1
        cfg_kw = _cfg_kwargs(seg_idx)

        # Steady frames.
        for fi in range(frames.steady):
            strength = render.steady_strengths[fi % len(render.steady_strengths)]
            input_img = noise_walker.blend(
                _structural_decay(current_img, render.structural_decay_radius),
                blend_pct=render.steady_noise_blend,
            )
            current_img = _pipe_call(input_img, embeds_cur, pooled_cur, cfg_kw, strength)
            current_img.save(output_dir / f"{frame_idx:04d}.png")
            frame_idx += 1

        # Transition or return.
        actual_n = frames.return_ if is_return else frames.transition
        for ti in range(actual_n):
            t_linear = (ti + 1) / (actual_n + 1)
            t = 3 * t_linear**2 - 2 * t_linear**3  # smoothstep

            blended_embeds = slerp_embeddings(embeds_cur, embeds_next, t)
            blended_pooled = slerp_embeddings(pooled_cur, pooled_next, t)

            if is_return:
                progress = ti / max(1, actual_n - 1)
                strength = render.return_strength_start + progress * (
                    render.return_strength_end - render.return_strength_start
                )
                pixel_blend = (progress**2) * render.return_pixel_blend_max
                current_img = _pixel_blend_toward_anchor(current_img, anchor_img, pixel_blend)
            else:
                strength = render.transition_strength

            input_img = noise_walker.blend(
                _structural_decay(current_img, render.structural_decay_radius),
                blend_pct=render.transition_noise_blend,
            )
            current_img = _pipe_call(input_img, blended_embeds, blended_pooled, cfg_kw, strength)
            current_img.save(output_dir / f"{frame_idx:04d}.png")
            frame_idx += 1

    # Append anchor as final keyframe for clean loop closure.
    anchor_img.save(output_dir / f"{frame_idx:04d}.png")
    frame_idx += 1

    return frame_idx


def expected_keyframe_count(config: PipelineConfig) -> int:
    """Compute how many PNGs `generate_keyframes` will produce for this config.

    Warmup frames are not saved. n_segments = len(prompts) - 1. Each segment
    writes `steady` + `transition` frames (last segment uses `return_` instead
    of `transition`), then one anchor is appended.
    """
    f = config.frames
    n_segments = len(config.subject.prompts) - 1
    return n_segments * f.steady + (n_segments - 1) * f.transition + f.return_ + 1
