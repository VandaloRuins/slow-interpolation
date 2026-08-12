"""Family-agnostic LoRA validation: render a configured prompt set on
any LoRA family's epoch checkpoints, save PNGs + manifest to the
outputs volume.

Sibling of `cloud/app.py` (uses the same image + volumes). Replaces
the Renoir-hardcoded `cloud/validation_renoir.py`; that module is now
a thin shim that calls into this one with the Renoir config.

Driven by a per-family YAML config under
`examples/configs/validation/<family>.yaml`. Schema:

    family: renoir-flowers
    lora_filename_template: "Renoir_Flowers_epoch_{epoch}.safetensors"
    default_epochs: [1, 5, 10]
    render:
      width: 1216
      height: 832
      seed: 42
      lora_scale: 0.85
      guidance_scale: 1.5
      num_inference_steps: 4
      base_model: stabilityai/stable-diffusion-xl-base-1.0
      lightning_lora: ByteDance/SDXL-Lightning
      lightning_weight: sdxl_lightning_4step_lora.safetensors
      taesd_vae: madebyollin/taesdxl
    negative_prompt: "photograph, 3D render, anime, cartoon, ..."
    tracks:
      - name: field
        label: "Track 1, off-distribution probe"
        prompts:
          - slug: F1-wildflower-meadow
            text: "rfl, a wildflower meadow ..."
          - ...
      - name: vase
        label: "Track 2, in-distribution hold-outs"
        prompts:
          - ...

Run once per epoch (the renderer + manifest emit per-epoch outputs):

    modal run -m cloud.validate_lora --config examples/configs/validation/renoir.yaml --epoch 10
    modal run -m cloud.validate_lora --config examples/configs/validation/soutine.yaml --epoch 10

Outputs land at
`/root/slow-interpolation/outputs/validation/<family>/epoch-<N>/` on
the `slow-interp-outputs` volume. Download:

    modal volume get slow-interp-outputs validation/<family>/epoch-10 outputs/validation/

The CivitAI-comparison HTML at
`outputs/validation/comparison.html` is the canonical viewer; mirror
its structure for new families if you want a head-to-head view.
"""

from __future__ import annotations

import time
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


VOLUMES = {
    "/root/slow-interpolation/models/loras": loras_volume,
    "/root/slow-interpolation/outputs": outputs_volume,
    str(HF_CACHE_PATH): hf_cache_volume,
}


app = modal.App("slow-interpolation-validate-lora", image=image)


# ---------------------------------------------------------------------------
# Render function. Loaded with all config baked into the YAML text passed in.
# ---------------------------------------------------------------------------


def _render_impl(
    config_yaml_text: str,
    *,
    epoch: int,
) -> dict[str, Any]:
    """Render one epoch's validation grid for the LoRA family in the
    config. Returns a manifest dict; PNGs + manifest persisted to the
    outputs volume."""
    import json

    import torch
    import yaml
    from PIL import Image
    from diffusers import (
        AutoencoderTiny,
        DiffusionPipeline,
        EulerDiscreteScheduler,
    )

    cfg = yaml.safe_load(config_yaml_text)
    if not isinstance(cfg, dict):
        raise ValueError("Invalid validation YAML (empty or not a mapping)")

    family = cfg["family"]
    template = cfg["lora_filename_template"]
    negative = cfg.get("negative_prompt") or ""
    render = cfg["render"]
    tracks = cfg.get("tracks") or []

    width = int(render["width"])
    height = int(render["height"])
    seed = int(render["seed"])
    lora_scale = float(render["lora_scale"])
    guidance_scale = float(render["guidance_scale"])
    num_inference_steps = int(render["num_inference_steps"])
    base_model = render["base_model"]
    lightning_lora = render["lightning_lora"]
    lightning_weight = render["lightning_weight"]
    taesd_vae = render["taesd_vae"]

    t0 = time.perf_counter()
    print(f"[validate-lora] family={family} epoch={epoch} scale={lora_scale}")

    out_dir = CONTAINER_REPO_ROOT / "outputs" / "validation" / family / f"epoch-{epoch}"
    out_dir.mkdir(parents=True, exist_ok=True)

    lora_filename = template.format(epoch=epoch)
    lora_path = CONTAINER_REPO_ROOT / "models" / "loras" / lora_filename
    if not lora_path.exists():
        raise FileNotFoundError(
            f"LoRA not on volume: {lora_path}. "
            f"Train it first (see docs/manual/train-lora-on-modal.md) "
            f"or upload via cloud/upload_weights.py."
        )

    # Build the SDXL pipeline. Lightning fuse is CONDITIONAL: set
    # `lightning_lora: null` in the validation YAML to validate on pure base,
    # which matters because epoch choice must be made on the deployment
    # backbone (Lightning and base behave oppositely through the chain, see
    # quality-first L27/L31; the vhm family deploys on base at guidance 6).
    tA = time.perf_counter()
    pipe = DiffusionPipeline.from_pretrained(
        base_model, torch_dtype=torch.float16, variant="fp16"
    ).to("cuda")
    if lightning_lora:
        pipe.load_lora_weights(lightning_lora, weight_name=lightning_weight)
        pipe.fuse_lora()
        pipe.unload_lora_weights()
        pipe.scheduler = EulerDiscreteScheduler.from_config(
            pipe.scheduler.config, timestep_spacing="trailing"
        )
    pipe.vae = AutoencoderTiny.from_pretrained(
        taesd_vae, torch_dtype=torch.float16
    ).to("cuda")
    pipe.safety_checker = None
    pipe.unet.to(memory_format=torch.channels_last)
    torch.cuda.empty_cache()
    print(f"[validate-lora] base + Lightning loaded in {time.perf_counter() - tA:.1f}s")

    # Load the family LoRA. UNet-only fallback for kohya text-encoder
    # key mismatches (same logic as validation_renoir.py).
    tB = time.perf_counter()
    try:
        pipe.load_lora_weights(str(lora_path))
    except IndexError:
        from safetensors.torch import load_file

        sd = load_file(str(lora_path))
        unet_only = {k: v for k, v in sd.items() if not k.startswith("lora_te")}
        pipe.load_lora_weights(unet_only)
    pipe.fuse_lora(lora_scale=lora_scale)
    pipe.unload_lora_weights()
    torch.cuda.empty_cache()
    print(f"[validate-lora] {family} LoRA fused at {lora_scale} in {time.perf_counter() - tB:.1f}s")

    # Render every track's prompts. Flatten to a single list with track tags.
    all_prompts: list[dict[str, str]] = []
    for track in tracks:
        track_name = track["name"]
        for p in track.get("prompts") or []:
            all_prompts.append({
                "slug": p["slug"],
                "text": p["text"],
                "track": track_name,
            })
    if not all_prompts:
        raise RuntimeError("Config has no prompts under tracks[].prompts")

    timings: list[dict[str, Any]] = []
    for p in all_prompts:
        tP = time.perf_counter()
        generator = torch.Generator(device="cuda").manual_seed(seed)
        result = pipe(
            prompt=p["text"],
            negative_prompt=negative,
            width=width,
            height=height,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            generator=generator,
        )
        img: Image.Image = result.images[0]
        png_path = out_dir / f"{p['slug']}.png"
        img.save(png_path, "PNG")
        elapsed = time.perf_counter() - tP
        timings.append({
            "slug": p["slug"],
            "track": p["track"],
            "seconds": round(elapsed, 2),
        })
        print(f"[validate-lora] {p['slug']} ({p['track']}): {elapsed:.1f}s")

    outputs_volume.commit()

    total = time.perf_counter() - t0
    manifest = {
        "family": family,
        "epoch": epoch,
        "lora_filename": lora_filename,
        "lora_scale": lora_scale,
        "seed": seed,
        "resolution": [width, height],
        "num_prompts": len(all_prompts),
        "total_seconds": round(total, 2),
        "per_prompt": timings,
        "output_dir_on_volume": str(out_dir.relative_to(CONTAINER_REPO_ROOT / "outputs")),
        "base_model": base_model,
        "lightning_lora": lightning_lora,
        "negative_prompt": negative,
    }
    (out_dir / "_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    outputs_volume.commit()
    print(f"[validate-lora] done in {total:.1f}s")
    return manifest


render_validation = app.function(
    name="render_validation",
    image=image,
    volumes=VOLUMES,
    gpu="L40S",
    timeout=60 * 30,
)(_render_impl)


@app.local_entrypoint()
def main(config: str, epoch: int) -> None:
    """Render one epoch's validation grid for a LoRA family.

    Args:
        config: path to YAML at examples/configs/validation/<family>.yaml.
        epoch: epoch number; the LoRA must already exist on the loras
            volume as `<lora_filename_template>` substituted with this
            epoch (see the config).
    """
    cfg_path = Path(config).resolve()
    if not cfg_path.exists():
        raise SystemExit(f"Validation config not found: {cfg_path}")

    yaml_text = cfg_path.read_text(encoding="utf-8")

    manifest = render_validation.remote(yaml_text, epoch=epoch)
    print()
    print(f"Validation {manifest['family']} epoch {epoch} complete:")
    print(f"  prompts:        {manifest['num_prompts']}")
    print(f"  wall time:      {manifest['total_seconds']:.1f}s")
    print(f"  outputs on volume: {OUTPUTS_VOLUME_NAME}:/{manifest['output_dir_on_volume']}")
    print()
    print("Download with:")
    print(
        f"  modal volume get {OUTPUTS_VOLUME_NAME} "
        f"{manifest['output_dir_on_volume']} outputs/"
    )
