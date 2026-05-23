"""Compositing sketch entrypoint: Soutine figure inside Renoir background.

Two-pass with SEQUENTIAL LoRA swap (deliberately, not dual-LoRA
simultaneous load). Pass 1: txt2img background under Renoir LoRA.
Pass 2: SDXL inpaint figure under Soutine LoRA, masked by the
user-supplied alpha. The unmasked Renoir surround is preserved
natively by the inpaint pipeline; the two painters only meet at the
mask feather band.

Honours the 2026-05-18 compositing constraint: Renoir reads as Renoir,
Soutine reads as Soutine. Dual-LoRA + regional cross-attention
(Attention Couple) is the promotion path (Compositing REQUEST 0),
not in scope here.

Closest sibling: cloud/validate_lora.py (LoRA loading + Lightning +
TAESD scaffolding). cloud/app.py for the shared image + volumes.

Run:

    modal run -m cloud.compositing_sketch \\
      --background-prompt "..." \\
      --figure-prompt "..." \\
      --mask-path-on-volume inputs/masks/sketch01.png \\
      --output-dir outputs/compositing-sketch/sketch01_<id>/

Outputs land at `<output_dir>` on the slow-interp-outputs volume:
  background.png         pass-1 result (Renoir register)
  composite.png          pass-2 result (Renoir surround + Soutine masked region)
  sketch_triptych.png    side-by-side: bg | mask overlay | composite
  manifest.json          provenance + per-pass timings + scales + seeds

Volumes:
  slow-interp-loras      LoRA weights at `models/loras/<filename>`
  slow-interp-datasets   mask PNGs at `inputs/masks/<name>.png` (uploaded by user)
  slow-interp-outputs    artifacts at `outputs/compositing-sketch/<run_id>/`
  slow-interp-hf-cache   SDXL base, Lightning LoRA, TAESD VAE

Promotion path (NOT in this file):
- BiRefNet-segmented alphas → Compositing REQUEST 1.
- Dual-LoRA + Attention Couple regional cross-attention → Compositing REQUEST 0.
This sketch entrypoint stays as the baseline reference.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import modal

from .app import (
    CONTAINER_REPO_ROOT,
    HF_CACHE_PATH,
    HF_CACHE_VOLUME_NAME,
    LORAS_VOLUME_NAME,
    OUTPUTS_VOLUME_NAME,
    image,
    loras_volume,
    outputs_volume,
    hf_cache_volume,
)


DATASETS_VOLUME_NAME = "slow-interp-datasets"
datasets_volume = modal.Volume.from_name(DATASETS_VOLUME_NAME, create_if_missing=True)


VOLUMES = {
    "/root/slow-interpolation/models/loras": loras_volume,
    "/root/slow-interpolation/datasets": datasets_volume,
    "/root/slow-interpolation/outputs": outputs_volume,
    str(HF_CACHE_PATH): hf_cache_volume,
}


APP_NAME = "slow-interpolation-compositing-sketch"
app = modal.App(APP_NAME, image=image)


# ---------------------------------------------------------------------------
# Render constants (mirror cloud/validate_lora.py for parity with the
# slow-interpolation rendering pipeline). Caller can override most via
# function args.
# ---------------------------------------------------------------------------

SDXL_BASE = "stabilityai/stable-diffusion-xl-base-1.0"
LIGHTNING_LORA = "ByteDance/SDXL-Lightning"
LIGHTNING_WEIGHT_NAME = "sdxl_lightning_4step_lora.safetensors"
TAESD_VAE = "madebyollin/taesdxl"


# ---------------------------------------------------------------------------
# Function: two-pass compositing sketch.
# ---------------------------------------------------------------------------


@app.function(
    name="compositing_sketch",
    image=image,
    gpu="L40S",
    volumes=VOLUMES,
    timeout=60 * 10,
)
def compositing_sketch(
    background_prompt: str,
    figure_prompt: str,
    mask_path_on_volume: str,
    output_dir: str,
    background_negative_prompt: str = "",
    figure_negative_prompt: str = "",
    renoir_lora_filename: str = "Renoir_Flowers_epoch_1.safetensors",
    renoir_lora_scale: float = 0.85,
    soutine_lora_filename: str = "Soutine_Figures_epoch_10.safetensors",
    soutine_lora_scale: float = 0.85,
    width: int = 832,
    height: int = 1216,
    seed: int = 42,
    inpaint_strength: float = 0.85,
    guidance_scale: float = 1.5,
    num_inference_steps: int = 4,
) -> dict[str, Any]:
    """End-to-end two-pass compositing test.

    Args:
        background_prompt: pass-1 prompt; must lead with the Renoir trigger (`rfl`).
        figure_prompt: pass-2 prompt; must lead with the Soutine trigger (`stn`).
        mask_path_on_volume: path inside slow-interp-datasets volume (e.g.
            `inputs/masks/sketch01.png`). White = paint with Soutine, black =
            preserve Renoir background. Mask must match `width x height`.
        output_dir: path inside slow-interp-outputs volume (e.g.
            `outputs/compositing-sketch/sketch01_<run_id>/`).
        background_negative_prompt: SDXL negative for pass 1 (suppress Soutine
            register, photoreal, ornament, frame).
        figure_negative_prompt: SDXL negative for pass 2 (suppress Renoir floral
            decorative register inside the mask).
        renoir_lora_filename: file under `models/loras/` on slow-interp-loras.
        renoir_lora_scale: fuse scale for pass 1.
        soutine_lora_filename: file under `models/loras/` on slow-interp-loras.
        soutine_lora_scale: fuse scale for pass 2.
        width, height: render resolution (must match mask dimensions).
        seed: torch CUDA generator seed (shared between passes).
        inpaint_strength: SDXL inpaint `strength` (0.85 = strong repaint inside
            mask, mild preservation of underlying background structure).
        guidance_scale: SDXL CFG for both passes (Lightning prefers ~1.5).
        num_inference_steps: 4 for SDXL Lightning 4-step LoRA.

    Returns:
        Manifest dict with run_id, paths to all artifacts on the outputs
        volume, per-pass wall times, all input args resolved.
    """
    import torch
    from PIL import Image, ImageDraw
    from diffusers import (
        AutoencoderTiny,
        DiffusionPipeline,
        EulerDiscreteScheduler,
        StableDiffusionXLInpaintPipeline,
    )

    started = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()

    run_id = _make_run_id(background_prompt, figure_prompt, seed)
    print(f"[sketch] run_id: {run_id}")

    # Resolve volume paths.
    mask_path = CONTAINER_REPO_ROOT / "datasets" / mask_path_on_volume
    if not mask_path.exists():
        raise FileNotFoundError(
            f"Mask not on slow-interp-datasets volume: {mask_path}. "
            "Upload with: modal volume put slow-interp-datasets <local> "
            f"{mask_path_on_volume}"
        )

    renoir_lora_path = CONTAINER_REPO_ROOT / "models" / "loras" / renoir_lora_filename
    if not renoir_lora_path.exists():
        raise FileNotFoundError(f"Renoir LoRA not on volume: {renoir_lora_path}")

    soutine_lora_path = CONTAINER_REPO_ROOT / "models" / "loras" / soutine_lora_filename
    if not soutine_lora_path.exists():
        raise FileNotFoundError(f"Soutine LoRA not on volume: {soutine_lora_path}")

    # Resolve output dir under outputs volume (output_dir is repo-root-relative
    # per the request convention: starts with `outputs/...`).
    out_dir = CONTAINER_REPO_ROOT / output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[sketch] output dir: {out_dir}")

    # Load mask early to fail fast on shape mismatch.
    mask_image = Image.open(mask_path).convert("L")
    if mask_image.size != (width, height):
        raise ValueError(
            f"Mask size {mask_image.size} does not match render size "
            f"{(width, height)}. Re-generate mask or pass --width / --height."
        )

    # --------------------------------------------------
    # Build SDXL Lightning pipeline (same recipe as validate_lora.py).
    # --------------------------------------------------
    tA = time.perf_counter()
    pipe = DiffusionPipeline.from_pretrained(
        SDXL_BASE, torch_dtype=torch.float16, variant="fp16"
    ).to("cuda")
    pipe.load_lora_weights(LIGHTNING_LORA, weight_name=LIGHTNING_WEIGHT_NAME)
    pipe.fuse_lora()
    pipe.unload_lora_weights()
    pipe.scheduler = EulerDiscreteScheduler.from_config(
        pipe.scheduler.config, timestep_spacing="trailing"
    )
    # Register VAE via register_modules so it lands in pipe.components +
    # pipe.config. Direct attribute assignment (`pipe.vae = ...`, the
    # validate_lora.py pattern) leaves the new VAE out of pipe.components,
    # which makes StableDiffusionXLInpaintPipeline.from_pipe(pipe) raise
    # `ValueError: ... expected [..., 'vae'], but only {...no vae...} were passed`.
    pipe.register_modules(
        vae=AutoencoderTiny.from_pretrained(
            TAESD_VAE, torch_dtype=torch.float16
        ).to("cuda")
    )
    pipe.safety_checker = None
    pipe.unet.to(memory_format=torch.channels_last)
    torch.cuda.empty_cache()
    print(f"[sketch] base + Lightning loaded in {time.perf_counter() - tA:.1f}s")

    # --------------------------------------------------
    # PASS 1: Renoir background (txt2img).
    # --------------------------------------------------
    tBg = time.perf_counter()
    _load_lora_with_fallback(pipe, renoir_lora_path)
    pipe.fuse_lora(lora_scale=renoir_lora_scale)
    print(f"[sketch] Renoir LoRA fused at {renoir_lora_scale}")

    generator = torch.Generator(device="cuda").manual_seed(seed)
    bg_result = pipe(
        prompt=background_prompt,
        negative_prompt=background_negative_prompt,
        width=width,
        height=height,
        num_inference_steps=num_inference_steps,
        guidance_scale=guidance_scale,
        generator=generator,
    )
    background_image: Image.Image = bg_result.images[0]
    background_path = out_dir / "background.png"
    background_image.save(background_path, "PNG")
    bg_seconds = time.perf_counter() - tBg
    print(f"[sketch] PASS 1 (Renoir background): {bg_seconds:.1f}s -> {background_path.name}")

    # Unfuse + unload Renoir BEFORE loading Soutine. Without this, the
    # Soutine fusion would stack on a Renoir-fused UNet and the two
    # painters would entangle in the masked region.
    pipe.unfuse_lora()
    pipe.unload_lora_weights()
    torch.cuda.empty_cache()

    # --------------------------------------------------
    # PASS 2: Soutine inpaint inside the mask.
    # --------------------------------------------------
    tInp = time.perf_counter()
    _load_lora_with_fallback(pipe, soutine_lora_path)
    pipe.fuse_lora(lora_scale=soutine_lora_scale)
    print(f"[sketch] Soutine LoRA fused at {soutine_lora_scale}")

    # Share the Soutine-fused UNet + VAE + text encoders with the inpaint
    # pipeline via from_pipe. The inpaint pipeline operates only inside
    # the mask; the unmasked Renoir surround passes through untouched.
    #
    # Pass vae=pipe.vae explicitly: in diffusers 0.38, even after
    # `register_modules(vae=...)` and direct attr assignment, the TAESD
    # VAE does not show up in `pipe.components` when from_pipe walks them.
    # Empirically tested both register_modules and bare attr assignment;
    # neither makes the inpaint pipeline see the VAE. Passing it as a
    # kwarg to from_pipe is the only path that works in this version.
    inpaint_pipe = StableDiffusionXLInpaintPipeline.from_pipe(pipe, vae=pipe.vae)
    inpaint_pipe.safety_checker = None

    # Re-seed the generator so seed-controlled noise is identical to the
    # background pass (inpaint reuses noise inside the mask).
    generator = torch.Generator(device="cuda").manual_seed(seed)
    inp_result = inpaint_pipe(
        prompt=figure_prompt,
        negative_prompt=figure_negative_prompt,
        image=background_image,
        mask_image=mask_image,
        width=width,
        height=height,
        num_inference_steps=num_inference_steps,
        guidance_scale=guidance_scale,
        strength=inpaint_strength,
        generator=generator,
    )
    composite_image: Image.Image = inp_result.images[0]
    composite_path = out_dir / "composite.png"
    composite_image.save(composite_path, "PNG")
    inpaint_seconds = time.perf_counter() - tInp
    print(f"[sketch] PASS 2 (Soutine inpaint): {inpaint_seconds:.1f}s -> {composite_path.name}")

    # --------------------------------------------------
    # Triptych for one-glance visual review.
    # --------------------------------------------------
    triptych_path = out_dir / "sketch_triptych.png"
    _make_triptych(background_image, mask_image, composite_image, triptych_path)
    print(f"[sketch] triptych -> {triptych_path.name}")

    # Persist + commit.
    outputs_volume.commit()

    ended = datetime.now(timezone.utc).isoformat()
    total = time.perf_counter() - t0

    manifest = {
        "run_id": run_id,
        "started_at_utc": started,
        "ended_at_utc": ended,
        "total_seconds": round(total, 2),
        "background_seconds": round(bg_seconds, 2),
        "inpaint_seconds": round(inpaint_seconds, 2),
        "modal_app_name": APP_NAME,
        "gpu_tier": "L40S",
        "base_model": SDXL_BASE,
        "lightning_lora": LIGHTNING_LORA,
        "loras": {
            "renoir": {
                "filename": renoir_lora_filename,
                "scale": renoir_lora_scale,
            },
            "soutine": {
                "filename": soutine_lora_filename,
                "scale": soutine_lora_scale,
            },
        },
        "prompts": {
            "background": background_prompt,
            "background_negative": background_negative_prompt,
            "figure": figure_prompt,
            "figure_negative": figure_negative_prompt,
        },
        "render": {
            "width": width,
            "height": height,
            "seed": seed,
            "inpaint_strength": inpaint_strength,
            "guidance_scale": guidance_scale,
            "num_inference_steps": num_inference_steps,
        },
        "mask_path_on_volume": mask_path_on_volume,
        "output_dir": output_dir,
        "artifacts": {
            "background": str(background_path.relative_to(CONTAINER_REPO_ROOT)),
            "composite": str(composite_path.relative_to(CONTAINER_REPO_ROOT)),
            "triptych": str(triptych_path.relative_to(CONTAINER_REPO_ROOT)),
            "manifest": str((out_dir / "manifest.json").relative_to(CONTAINER_REPO_ROOT)),
        },
    }

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    outputs_volume.commit()
    print(f"[sketch] done in {total:.1f}s")
    return manifest


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


def _load_lora_with_fallback(pipe: Any, lora_path: Path) -> None:
    """Load LoRA weights with the UNet-only fallback for any kohya text-
    encoder key mismatches (same logic as validate_lora.py)."""
    try:
        pipe.load_lora_weights(str(lora_path))
    except IndexError:
        from safetensors.torch import load_file

        sd = load_file(str(lora_path))
        unet_only = {k: v for k, v in sd.items() if not k.startswith("lora_te")}
        pipe.load_lora_weights(unet_only)


def _make_triptych(
    background: Any,
    mask: Any,
    composite: Any,
    out_path: Path,
) -> None:
    """Compose a 3-panel side-by-side: background | mask-overlay | composite.

    Mask overlay: background with the mask region tinted semi-transparent
    rose so the figure area is visually clear. All three panels at native
    resolution.
    """
    from PIL import Image

    w, h = background.size
    gutter = 8
    sheet = Image.new("RGB", (w * 3 + gutter * 2, h), (20, 20, 20))

    # Panel 1: background.
    sheet.paste(background, (0, 0))

    # Panel 2: background with semi-transparent rose mask overlay.
    overlay_bg = background.copy().convert("RGBA")
    mask_rgba = Image.new("RGBA", (w, h), (180, 90, 90, 0))
    # Use mask brightness as the alpha channel of the rose tint.
    mask_rgba.putalpha(mask.point(lambda p: int(p * 0.5)))  # 50% max tint
    overlay_bg = Image.alpha_composite(overlay_bg, mask_rgba).convert("RGB")
    sheet.paste(overlay_bg, (w + gutter, 0))

    # Panel 3: composite.
    sheet.paste(composite, (w * 2 + gutter * 2, 0))

    sheet.save(out_path, "PNG")


def _make_run_id(background_prompt: str, figure_prompt: str, seed: int) -> str:
    """Compose a timestamp-based run-id with a content SHA tail for
    collision-free reproducibility across re-runs."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    content = f"{background_prompt}|{figure_prompt}|{seed}".encode("utf-8")
    sha = hashlib.sha256(content).hexdigest()[:8]
    return f"sketch_{ts}_{sha}"


# ---------------------------------------------------------------------------
# CLI entrypoint.
# ---------------------------------------------------------------------------


@app.local_entrypoint()
def main(
    background_prompt: str,
    figure_prompt: str,
    mask_path_on_volume: str,
    output_dir: str,
    background_negative_prompt: str = "",
    figure_negative_prompt: str = "",
    renoir_lora_filename: str = "Renoir_Flowers_epoch_1.safetensors",
    renoir_lora_scale: float = 0.85,
    soutine_lora_filename: str = "Soutine_Figures_epoch_10.safetensors",
    soutine_lora_scale: float = 0.85,
    width: int = 832,
    height: int = 1216,
    seed: int = 42,
    inpaint_strength: float = 0.85,
    guidance_scale: float = 1.5,
    num_inference_steps: int = 4,
) -> None:
    """CLI wrapper. See `compositing_sketch` docstring for arg meanings."""
    print(f"[sketch] dispatching to {APP_NAME} on L40S")
    print(f"[sketch] mask:        {mask_path_on_volume}")
    print(f"[sketch] out_dir:     {output_dir}")
    print(f"[sketch] Renoir LoRA: {renoir_lora_filename} @ {renoir_lora_scale}")
    print(f"[sketch] Soutine LoRA:{soutine_lora_filename} @ {soutine_lora_scale}")
    print(f"[sketch] resolution:  {width}x{height} seed={seed}")
    print()

    manifest = compositing_sketch.remote(
        background_prompt=background_prompt,
        figure_prompt=figure_prompt,
        mask_path_on_volume=mask_path_on_volume,
        output_dir=output_dir,
        background_negative_prompt=background_negative_prompt,
        figure_negative_prompt=figure_negative_prompt,
        renoir_lora_filename=renoir_lora_filename,
        renoir_lora_scale=renoir_lora_scale,
        soutine_lora_filename=soutine_lora_filename,
        soutine_lora_scale=soutine_lora_scale,
        width=width,
        height=height,
        seed=seed,
        inpaint_strength=inpaint_strength,
        guidance_scale=guidance_scale,
        num_inference_steps=num_inference_steps,
    )

    print()
    print(f"[sketch] run_id:       {manifest['run_id']}")
    print(f"[sketch] total:        {manifest['total_seconds']:.1f}s "
          f"(bg {manifest['background_seconds']:.1f}s, "
          f"inpaint {manifest['inpaint_seconds']:.1f}s)")
    print(f"[sketch] artifacts on volume {OUTPUTS_VOLUME_NAME}:")
    for k, v in manifest["artifacts"].items():
        print(f"  {k:12s} {v}")
    print()
    print("Download with:")
    print(
        f"  modal volume get {OUTPUTS_VOLUME_NAME} "
        f"{manifest['output_dir']} ./outputs/"
    )
