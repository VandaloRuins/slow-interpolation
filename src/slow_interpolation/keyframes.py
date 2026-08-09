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
from .motion import build_motion_mask, displace
from .noise import EvolvedNoiseWalk, NoiseSource
from .prompts import encode_prompt, slerp_embeddings


# ---------------------------------------------------------------------------
# SDXL pipeline loader
# ---------------------------------------------------------------------------


def load_sdxl_pipeline(config: PipelineConfig) -> Any:
    """Load and configure the SDXL Lightning img2img pipeline + style LoRA."""
    from diffusers import (
        AutoencoderKL,
        AutoencoderTiny,
        ControlNetModel,
        EulerDiscreteScheduler,
        StableDiffusionXLControlNetImg2ImgPipeline,
        StableDiffusionXLImg2ImgPipeline,
    )

    m = config.models
    ctrl = config.control

    if ctrl is not None:
        # Same img2img chain, plus a fixed control map injected at every
        # denoising step. The Lightning and style LoRAs still fuse into the
        # UNet below; ControlNet is a separate network on the residuals, so
        # they compose rather than conflict.
        controlnet = ControlNetModel.from_pretrained(
            ctrl.model, torch_dtype=torch.float16, variant="fp16"
        )
        pipe = StableDiffusionXLControlNetImg2ImgPipeline.from_pretrained(
            m.sdxl_base,
            controlnet=controlnet,
            torch_dtype=torch.float16,
            variant="fp16",
        ).to("cuda")
        print(f"[keyframes] ControlNet {ctrl.model} scale={ctrl.scale} "
              f"guidance {ctrl.guidance_start}-{ctrl.guidance_end}")
    else:
        pipe = StableDiffusionXLImg2ImgPipeline.from_pretrained(
            m.sdxl_base,
            torch_dtype=torch.float16,
            variant="fp16",
        ).to("cuda")

    # Lightning LoRA: fuse and unload. Scheduler must use trailing timesteps.
    # `lightning_lora: null` skips both, running the undistilled base model,
    # which wants many more steps at a normal guidance scale.
    if m.lightning_lora:
        pipe.load_lora_weights(m.lightning_lora, weight_name=m.lightning_weight_name)
        pipe.fuse_lora()
        pipe.unload_lora_weights()

        pipe.scheduler = EulerDiscreteScheduler.from_config(
            pipe.scheduler.config, timestep_spacing="trailing"
        )

    # TAESD VAE: fast, fp16-stable, ~1 GB saved vs full SDXL VAE, at the cost of
    # a lossy encode/decode round trip once per keyframe. `vae_kind: full`
    # swaps in AutoencoderKL to measure what that costs across a chain.
    if m.vae_kind == "full":
        pipe.vae = AutoencoderKL.from_pretrained(m.vae_full, torch_dtype=torch.float16).to("cuda")
    else:
        pipe.vae = AutoencoderTiny.from_pretrained(m.vae, torch_dtype=torch.float16).to("cuda")
    pipe.safety_checker = None
    pipe.unet.to(memory_format=torch.channels_last)
    torch.cuda.empty_cache()

    # Style LoRA on top of fused Lightning. `style.lora_path` is either a
    # local filesystem path or a `hf:<user>/<repo>` HF Hub reference.
    style = config.style
    if style.lora_path:
        resolved = _resolve_lora_path(style.lora_path, style.lora_filename)
        if resolved is not None:
            live = style.lora_scale_per_segment is not None
            _load_style_lora(pipe, resolved, style.lora_scale, keep_live=live)
            if live:
                print(f"[keyframes] style LoRA kept LIVE, per-segment scales "
                      f"{style.lora_scale_per_segment}")
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


def _load_style_lora(pipe: Any, lora_path: str, lora_scale: float,
                     keep_live: bool = False) -> None:
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
    if keep_live:
        # Do NOT fuse: fusing bakes one scale into the weights for the whole
        # render. Left live, the scale can be passed per call via
        # cross_attention_kwargs and therefore vary per stage.
        pipe.set_adapters(pipe.get_active_adapters() or ["default_0"], [lora_scale])
        return
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


def _random_noise_image(width: int, height: int, seed: int | None = None) -> Image.Image:
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, (height, width, 3), dtype=np.uint8)
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

    kf_counter = [0]   # running index of the NEXT keyframe to be generated
    current_img = _random_noise_image(res.width, res.height, config.seed)
    # One generator threaded through every call, so the SEQUENCE of samples is
    # what is reproducible, not each call in isolation. Left None the sampler
    # falls back to global torch RNG and the render is a one-off.
    generator = (
        torch.Generator(device=pipe.device).manual_seed(config.seed)
        if config.seed is not None else None
    )
    if config.seed is not None:
        print(f"[keyframes] seeded, seed={config.seed}")
    frame_idx = 0

    # Control map loaded once; it is FIXED across every frame, which is what
    # pins the composition for the whole clip.
    ctrl = config.control
    ctrl_maps: list[Image.Image] = []
    if ctrl is not None:
        srcs = list(ctrl.images) if ctrl.images else ([ctrl.image] if ctrl.image else [])
        ctrl_maps = [
            Image.open(s).convert("RGB").resize((res.width, res.height), Image.LANCZOS)
            for s in srcs
        ]
        if ctrl_maps:
            print(f"[keyframes] {len(ctrl_maps)} control map(s), "
                  f"{'cross-faded per stage' if len(ctrl_maps) > 1 else 'fixed'}")

    # Per-KEYFRAME control maps: the channel through which structure MOVES.
    # `images` cross-fades per prompt, which is a dissolve; a dissolve cannot
    # translate anything. These are indexed by the running keyframe counter
    # instead, so a texture authored at phase i/K in map i genuinely descends
    # from one keyframe to the next, and the repaint follows it because the
    # conditioning is what the model re-derives texture FROM (attempts 1 to 3).
    kf_ctrl_maps: list[Image.Image] = []
    if ctrl is not None and ctrl.keyframe_images:
        kf_ctrl_maps = [
            Image.open(s).convert("RGB").resize((res.width, res.height), Image.LANCZOS)
            for s in ctrl.keyframe_images
        ]
        print(f"[keyframes] {len(kf_ctrl_maps)} PER-KEYFRAME control maps, cycled")
        if not ctrl_maps:
            ctrl_maps = [kf_ctrl_maps[0]]   # motion mask + warmup use phase 0

    # Masked directional motion. Built once: the mask is derived from the first
    # control map's dark region, which is where water already lives by the
    # convention settled after v4. Displacement is applied to the PREVIOUS frame
    # before the noise blend, so the noise walk's temporal persistence is not
    # dragged around with the water. See motion.py.
    motion_cfg = getattr(config, "motion", None)
    motion_mask = None
    if motion_cfg is not None and (motion_cfg.dx or motion_cfg.dy):
        if not ctrl_maps:
            raise ValueError(
                "motion needs a control map to derive its mask from; set control.image"
            )
        motion_mask = build_motion_mask(
            ctrl_maps[0], (res.width, res.height),
            threshold=motion_cfg.mask_threshold,
            feather=motion_cfg.mask_feather,
            invert=motion_cfg.mask_invert,
        )
        print(f"[keyframes] motion dx={motion_cfg.dx} dy={motion_cfg.dy} per keyframe, "
              f"hp_sigma={motion_cfg.hp_sigma} cyclic={motion_cfg.cyclic}, "
              f"mask covers {100 * float(motion_mask.mean()):.1f}% of the frame")

    def _move(img: Image.Image) -> Image.Image:
        if motion_mask is None:
            return img
        return displace(img, motion_mask, motion_cfg.dx, motion_cfg.dy,
                        hp_sigma=motion_cfg.hp_sigma, cyclic=motion_cfg.cyclic,
                        band_hi=motion_cfg.band_hi)

    def _ctrl_at(seg: int, t: float) -> Image.Image | None:
        """Control map for a frame at SLERP position `t` within segment `seg`.

        With one map, always that map. With a list, cross-fade between map[seg]
        and map[seg+1] on the same `t` the prompt embeddings use, so structure
        and text change together instead of fighting. Per-keyframe maps trump
        both and cycle on the keyframe counter.
        """
        if kf_ctrl_maps:
            return kf_ctrl_maps[kf_counter[0] % len(kf_ctrl_maps)]
        if not ctrl_maps:
            return None
        if len(ctrl_maps) == 1:
            return ctrl_maps[0]
        a = ctrl_maps[min(seg, len(ctrl_maps) - 1)]
        b = ctrl_maps[min(seg + 1, len(ctrl_maps) - 1)]
        if t <= 0.0:
            return a
        if t >= 1.0:
            return b
        return Image.blend(a, b, t)

    def _pipe_call(
        image: Image.Image,
        embeds: torch.Tensor,
        pooled: torch.Tensor,
        cfg_kw: dict[str, Any],
        strength: float,
        ctrl_img: Image.Image | None = None,
        lora_scale: float | None = None,
    ) -> Image.Image:
        ctrl_kw: dict[str, Any] = {}
        if lora_scale is not None:
            ctrl_kw["cross_attention_kwargs"] = {"scale": lora_scale}
        if ctrl is not None and ctrl_img is not None:
            # `update`, NOT reassignment. This branch used to replace the dict
            # wholesale, which silently dropped `cross_attention_kwargs`
            # whenever a control map was present. Since that is the only
            # mechanism carrying `lora_scale_per_segment` to the model (the
            # keep_live path sets one scale via `set_adapters` for the whole
            # render), any config combining per-segment scales with ControlNet
            # ran entirely at the base `lora_scale`. empire_v10_dualsource is
            # exactly that combination; see the note in its own comment header.
            ctrl_kw.update({
                "control_image": ctrl_img,
                "controlnet_conditioning_scale": ctrl.scale,
                "control_guidance_start": ctrl.guidance_start,
                "control_guidance_end": ctrl.guidance_end,
            })
        result = pipe(
            **ctrl_kw,
            prompt_embeds=embeds,
            pooled_prompt_embeds=pooled,
            **cfg_kw,
            image=image,
            strength=strength,
            generator=generator,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            crops_coords_top_left=borders.crops_coords_top_left,
            original_size=borders.original_size,
            target_size=target_size,
            callback_on_step_end=callback,
            callback_on_step_end_tensor_inputs=["latents"],
        ).images[0]
        return result

    # --- Warmup: establish from noise, or from a structural anchor ---
    embeds_cur, pooled_cur, _, _ = all_embeds[0]
    cfg_kw = _cfg_kwargs(0)
    anchor_src = getattr(config, "anchor_image", None)
    if anchor_src is not None:
        # Seeded: the first pass runs at anchor_strength (default 0.65) so the
        # source geometry survives instead of being replaced by noise.
        current_img = Image.open(anchor_src).convert("RGB").resize(
            (res.width, res.height), Image.LANCZOS
        )
        first_strength = config.anchor_strength
        print(f"[keyframes] seeded from {anchor_src} at strength {first_strength}")
    else:
        # `current_img` is already the random-noise canvas from above; leave it.
        first_strength = 0.85
    for wi in range(frames.warmup):
        strength = first_strength if wi == 0 else 0.75
        input_img = noise_walker.blend(current_img, blend_pct=render.steady_noise_blend)
        current_img = _pipe_call(input_img, embeds_cur, pooled_cur, cfg_kw, strength,
                                 _ctrl_at(0, 0.0),
                                 style.scale_at(0) if style.lora_scale_per_segment else None)

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
        for fi in range(frames.steady_at(seg_idx)):
            strength = render.steady_strengths[fi % len(render.steady_strengths)]
            base = _pixel_blend_toward_anchor(
                current_img, anchor_img, render.anchor_reassert
            )
            input_img = noise_walker.blend(
                _move(_structural_decay(base, render.structural_decay_radius)),
                blend_pct=render.steady_noise_blend,
            )
            current_img = _pipe_call(input_img, embeds_cur, pooled_cur, cfg_kw, strength,
                                     _ctrl_at(seg_idx, 0.0),
                                     style.scale_at(seg_idx) if style.lora_scale_per_segment else None)
            current_img.save(output_dir / f"{frame_idx:04d}.png")
            frame_idx += 1
            kf_counter[0] += 1

        # Transition or return.
        actual_n = frames.return_ if is_return else frames.transition_at(seg_idx)
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

            # The return segment already blends toward the anchor on its own
            # ramp; do not double-apply there.
            base = current_img if is_return else _pixel_blend_toward_anchor(
                current_img, anchor_img, render.anchor_reassert
            )
            input_img = noise_walker.blend(
                _move(_structural_decay(base, render.structural_decay_radius)),
                blend_pct=render.transition_noise_blend,
            )
            current_img = _pipe_call(input_img, blended_embeds, blended_pooled, cfg_kw,
                                     strength, _ctrl_at(seg_idx, t),
                                     style.scale_at(seg_idx) if style.lora_scale_per_segment else None)
            current_img.save(output_dir / f"{frame_idx:04d}.png")
            frame_idx += 1
            kf_counter[0] += 1

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
    # Per-segment aware: a cycle that lingers on one stage must still report the
    # right count, because this feeds conform.py's frame-floor check.
    total = 0
    for seg in range(n_segments):
        total += f.steady_at(seg)
        total += f.return_ if seg == n_segments - 1 else f.transition_at(seg)
    return total + 1
