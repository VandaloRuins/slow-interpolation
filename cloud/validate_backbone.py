"""Backbone capability probe: render a prompt set across several
diffusion backbones (SDXL Lightning, SDXL base, FLUX schnell, FLUX dev),
no LoRA on any backbone, to compare painterly surface and prompt
adherence at the base-model level.

Built 2026-05-18 to answer "should we retrain the Renoir + Soutine
LoRAs on FLUX?" before sinking the retraining cost. See
[`../docs/planning/workstreams/alt-techniques/brainstorm.md`](../docs/planning/workstreams/alt-techniques/brainstorm.md)
section 1 (FLUX backbone) for the framing.

Sibling of `cloud/validate_lora.py`. Shares the `slow-interp-outputs`
and `slow-interp-hf-cache` volumes but defines its own image and app
because FLUX needs additional Python dependencies (sentencepiece,
protobuf) for the T5 text encoder, and a larger diffusers floor.

Driven by a per-probe YAML config under
`examples/configs/validation/<name>.yaml`. The runner dispatches one
backbone per invocation; comparison is post-hoc by browsing the
output volume side by side.

Usage:

    modal run -m cloud.validate_backbone --config examples/configs/validation/painterly_backbone.yaml --backbone sdxl_lightning
    modal run -m cloud.validate_backbone --config examples/configs/validation/painterly_backbone.yaml --backbone sdxl_base
    modal run -m cloud.validate_backbone --config examples/configs/validation/painterly_backbone.yaml --backbone flux_schnell
    modal run -m cloud.validate_backbone --config examples/configs/validation/painterly_backbone.yaml --backbone flux_dev

Outputs land at
`/root/slow-interpolation/outputs/validation/<family>/<backbone>/` on
the `slow-interp-outputs` volume. Download:

    modal volume get slow-interp-outputs validation/<family> outputs/validation/

HuggingFace gating note: `flux_dev` requires accepting the FLUX.1-dev
license at https://huggingface.co/black-forest-labs/FLUX.1-dev. Then
create a Modal secret named `huggingface` containing `HF_TOKEN`:

    modal secret create huggingface HF_TOKEN=<your-token>

The render function attaches that secret when it exists; absent the
secret, flux_schnell and the SDXL backbones still work.
"""

from __future__ import annotations

import os
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
    hf_cache_volume,
    loras_volume,
    outputs_volume,
)


# ---------------------------------------------------------------------------
# Image: extends the validate_lora image with FLUX-required deps.
#
# Defined as its own image (not a chain off cloud.app.image) so that
# any future dependency drift on the FLUX side does not affect the
# renderer image used by the production pipeline.
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .pip_install(
        "torch==2.5.1",
        "torchvision==0.20.1",
        extra_index_url="https://download.pytorch.org/whl/cu124",
    )
    .pip_install(
        # FLUX support landed in diffusers 0.30. Pin >=0.31 to be safe
        # on FluxPipeline API stability; the existing renderer image
        # caps at <0.40 for the same reason.
        "diffusers>=0.31,<0.40",
        "transformers>=4.43",
        "accelerate",
        "peft",
        "numpy",
        "pillow",
        "pyyaml",
        # FLUX uses T5-XXL as the secondary text encoder; T5 tokenization
        # needs sentencepiece + protobuf at import time.
        "sentencepiece",
        "protobuf",
    )
    .env({"PYTHONPATH": "/root/slow-interpolation"})
    .workdir("/root/slow-interpolation")
    .add_local_dir(
        local_path=str(_REPO_ROOT / "cloud"),
        remote_path="/root/slow-interpolation/cloud",
    )
    .add_local_dir(
        local_path=str(_REPO_ROOT / "examples"),
        remote_path="/root/slow-interpolation/examples",
    )
)


VOLUMES = {
    "/root/slow-interpolation/outputs": outputs_volume,
    "/root/slow-interpolation/models/loras": loras_volume,
    str(HF_CACHE_PATH): hf_cache_volume,
}


_LORAS_PATH = Path("/root/slow-interpolation/models/loras")


def _fuse_optional_lora(pipe, bcfg: dict[str, Any]) -> dict[str, Any] | None:
    """If `bcfg.lora` is set, load + fuse + unload a domain LoRA on top
    of the current pipeline. Returns the lora info dict (filename,
    scale, fallback_used) for the manifest, or None if no LoRA was
    requested.

    Path resolution: `bcfg.lora.filename` is interpreted relative to
    `/root/slow-interpolation/models/loras` (the mounted loras volume).
    Falls back to UNet-only loading on IndexError (kohya text-encoder
    key mismatch), matching the pattern in validate_lora.py.
    """
    lora_spec = bcfg.get("lora")
    if not lora_spec:
        return None
    filename = lora_spec["filename"]
    scale = float(lora_spec.get("scale", 0.85))
    lora_path = _LORAS_PATH / filename
    if not lora_path.exists():
        raise FileNotFoundError(
            f"Domain LoRA not on volume: {lora_path}. "
            f"Upload via cloud/upload_weights.py first."
        )
    fallback_used = False
    try:
        pipe.load_lora_weights(str(lora_path))
    except IndexError:
        from safetensors.torch import load_file

        sd = load_file(str(lora_path))
        unet_only = {k: v for k, v in sd.items() if not k.startswith("lora_te")}
        pipe.load_lora_weights(unet_only)
        fallback_used = True
    pipe.fuse_lora(lora_scale=scale)
    pipe.unload_lora_weights()
    import torch  # local import to avoid module-level dep on torch
    torch.cuda.empty_cache()
    print(
        f"[validate-backbone] domain LoRA {filename} fused at scale {scale}"
        + (" (UNet-only fallback)" if fallback_used else "")
    )
    return {
        "filename": filename,
        "scale": scale,
        "fallback_used": fallback_used,
    }


app = modal.App("slow-interpolation-validate-backbone", image=image)


# ---------------------------------------------------------------------------
# Per-backbone render dispatch.
# ---------------------------------------------------------------------------


def _render_sdxl_lightning(
    *,
    bcfg: dict[str, Any],
    prompts: list[dict[str, str]],
    negative: str,
    width: int,
    height: int,
    seed: int,
    out_dir: Path,
    lora_info: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    import torch
    from PIL import Image
    from diffusers import AutoencoderTiny, DiffusionPipeline, EulerDiscreteScheduler

    dtype = torch.float16 if bcfg.get("dtype", "float16") == "float16" else torch.bfloat16
    pipe = DiffusionPipeline.from_pretrained(
        bcfg["model_id"], torch_dtype=dtype, variant="fp16"
    ).to("cuda")
    pipe.load_lora_weights(
        bcfg["lightning_lora"], weight_name=bcfg["lightning_weight"]
    )
    pipe.fuse_lora()
    pipe.unload_lora_weights()
    pipe.scheduler = EulerDiscreteScheduler.from_config(
        pipe.scheduler.config, timestep_spacing="trailing"
    )
    if bcfg.get("taesd_vae"):
        pipe.vae = AutoencoderTiny.from_pretrained(
            bcfg["taesd_vae"], torch_dtype=dtype
        ).to("cuda")
    pipe.safety_checker = None
    pipe.unet.to(memory_format=torch.channels_last)
    torch.cuda.empty_cache()

    info = _fuse_optional_lora(pipe, bcfg)
    if info is not None:
        lora_info.append(info)

    return _run_prompts(
        pipe=pipe,
        prompts=prompts,
        negative=negative,
        width=width,
        height=height,
        seed=seed,
        out_dir=out_dir,
        num_inference_steps=int(bcfg["num_inference_steps"]),
        guidance_scale=float(bcfg["guidance_scale"]),
        max_sequence_length=None,
    )


def _render_sdxl_base(
    *,
    bcfg: dict[str, Any],
    prompts: list[dict[str, str]],
    negative: str,
    width: int,
    height: int,
    seed: int,
    out_dir: Path,
    lora_info: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    import torch
    from diffusers import DiffusionPipeline

    dtype = torch.float16 if bcfg.get("dtype", "float16") == "float16" else torch.bfloat16
    pipe = DiffusionPipeline.from_pretrained(
        bcfg["model_id"], torch_dtype=dtype, variant="fp16"
    ).to("cuda")
    pipe.safety_checker = None
    pipe.unet.to(memory_format=torch.channels_last)
    torch.cuda.empty_cache()

    info = _fuse_optional_lora(pipe, bcfg)
    if info is not None:
        lora_info.append(info)

    return _run_prompts(
        pipe=pipe,
        prompts=prompts,
        negative=negative,
        width=width,
        height=height,
        seed=seed,
        out_dir=out_dir,
        num_inference_steps=int(bcfg["num_inference_steps"]),
        guidance_scale=float(bcfg["guidance_scale"]),
        max_sequence_length=None,
    )


def _render_flux(
    *,
    bcfg: dict[str, Any],
    prompts: list[dict[str, str]],
    width: int,
    height: int,
    seed: int,
    out_dir: Path,
) -> list[dict[str, Any]]:
    """Render across FLUX.1 [schnell] or FLUX.1 [dev]. FLUX ignores
    negative prompts (no CFG branch in its rectified-flow sampling at
    schnell's guidance=0; dev runs with cfg but the diffusers
    FluxPipeline does not accept negative_prompt on the standard path).
    """
    import torch
    from diffusers import FluxPipeline

    dtype = torch.bfloat16 if bcfg.get("dtype", "bfloat16") == "bfloat16" else torch.float16
    pipe = FluxPipeline.from_pretrained(
        bcfg["model_id"], torch_dtype=dtype
    ).to("cuda")
    # CPU offload would let smaller GPUs fit; on L40S (48GB) the full
    # pipeline fits in VRAM with headroom. Leaving offload off for speed.
    torch.cuda.empty_cache()

    return _run_prompts(
        pipe=pipe,
        prompts=prompts,
        negative=None,
        width=width,
        height=height,
        seed=seed,
        out_dir=out_dir,
        num_inference_steps=int(bcfg["num_inference_steps"]),
        guidance_scale=float(bcfg["guidance_scale"]),
        max_sequence_length=int(bcfg.get("max_sequence_length", 512)),
    )


def _run_prompts(
    *,
    pipe,
    prompts: list[dict[str, str]],
    negative: str | None,
    width: int,
    height: int,
    seed: int,
    out_dir: Path,
    num_inference_steps: int,
    guidance_scale: float,
    max_sequence_length: int | None,
) -> list[dict[str, Any]]:
    import torch
    from PIL import Image  # noqa: F401  (Pillow is needed by diffusers result.images[0].save)

    timings: list[dict[str, Any]] = []
    for p in prompts:
        tP = time.perf_counter()
        generator = torch.Generator(device="cuda").manual_seed(seed)
        call_kwargs: dict[str, Any] = dict(
            prompt=p["text"],
            width=width,
            height=height,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            generator=generator,
        )
        if negative is not None:
            call_kwargs["negative_prompt"] = negative
        if max_sequence_length is not None:
            call_kwargs["max_sequence_length"] = max_sequence_length

        result = pipe(**call_kwargs)
        img = result.images[0]
        png_path = out_dir / f"{p['slug']}.png"
        img.save(png_path, "PNG")
        elapsed = time.perf_counter() - tP
        timings.append({"slug": p["slug"], "seconds": round(elapsed, 2)})
        print(f"[validate-backbone] {p['slug']}: {elapsed:.1f}s")
    return timings


BACKBONE_DISPATCH = {
    "sdxl_lightning": "sdxl_lightning",
    "sdxl_base": "sdxl_base",
    "flux_schnell": "flux",
    "flux_dev": "flux",
}


# ---------------------------------------------------------------------------
# The Modal function. Single GPU tier (L40S) is enough for all four
# backbones at 1024x1024; FLUX.1 [dev] bf16 peaks around 32GB.
# ---------------------------------------------------------------------------


def _render_impl(
    config_yaml_text: str,
    *,
    backbone: str,
    hf_token: str | None = None,
) -> dict[str, Any]:
    import json

    import yaml

    if backbone not in BACKBONE_DISPATCH:
        raise SystemExit(
            f"Unknown backbone {backbone!r}. "
            f"Choices: {sorted(BACKBONE_DISPATCH)}"
        )

    if hf_token:
        os.environ["HF_TOKEN"] = hf_token
        os.environ["HUGGING_FACE_HUB_TOKEN"] = hf_token
        os.environ["HUGGINGFACE_HUB_TOKEN"] = hf_token

    cfg = yaml.safe_load(config_yaml_text)
    if not isinstance(cfg, dict):
        raise ValueError("Invalid backbone-probe YAML (empty or not a mapping)")

    family = cfg["family"]
    render = cfg["render"]
    width = int(render["width"])
    height = int(render["height"])
    seed = int(render["seed"])
    backbones_cfg = cfg.get("backbones") or {}
    if backbone not in backbones_cfg:
        raise SystemExit(
            f"YAML has no `backbones.{backbone}` section. "
            f"Available: {sorted(backbones_cfg)}"
        )
    bcfg = backbones_cfg[backbone]
    negative = (cfg.get("negative_prompt") or "").strip()
    prompts = cfg.get("prompts") or []
    if not prompts:
        raise RuntimeError("Config has no `prompts:` list")

    out_dir = (
        CONTAINER_REPO_ROOT / "outputs" / "validation" / family / backbone
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    print(
        f"[validate-backbone] family={family} backbone={backbone} "
        f"prompts={len(prompts)} seed={seed} res={width}x{height}"
    )

    dispatch_kind = BACKBONE_DISPATCH[backbone]
    lora_info: list[dict[str, Any]] = []
    if dispatch_kind == "sdxl_lightning":
        timings = _render_sdxl_lightning(
            bcfg=bcfg,
            prompts=prompts,
            negative=negative,
            width=width,
            height=height,
            seed=seed,
            out_dir=out_dir,
            lora_info=lora_info,
        )
    elif dispatch_kind == "sdxl_base":
        timings = _render_sdxl_base(
            bcfg=bcfg,
            prompts=prompts,
            negative=negative,
            width=width,
            height=height,
            seed=seed,
            out_dir=out_dir,
            lora_info=lora_info,
        )
    elif dispatch_kind == "flux":
        timings = _render_flux(
            bcfg=bcfg,
            prompts=prompts,
            width=width,
            height=height,
            seed=seed,
            out_dir=out_dir,
        )
    else:
        raise RuntimeError(f"Unhandled dispatch kind {dispatch_kind!r}")

    total = time.perf_counter() - t0

    manifest = {
        "family": family,
        "backbone": backbone,
        "backbone_config": bcfg,
        "domain_loras": lora_info,
        "seed": seed,
        "resolution": [width, height],
        "num_prompts": len(prompts),
        "negative_prompt_applied": negative if dispatch_kind != "flux" else "",
        "total_seconds": round(total, 2),
        "per_prompt": timings,
        "output_dir_on_volume": str(
            out_dir.relative_to(CONTAINER_REPO_ROOT / "outputs")
        ),
    }
    (out_dir / "_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    outputs_volume.commit()
    hf_cache_volume.commit()

    print(f"[validate-backbone] done in {total:.1f}s")
    return manifest


# HuggingFace token (required for flux_dev only) is passed as a
# function arg rather than via a Modal Secret. Modal validates secret
# references at app-deploy time, so attaching a missing `huggingface`
# secret would block sdxl_lightning, sdxl_base, and flux_schnell too.
# Token flow: local entrypoint reads it from env or the standard HF
# cache file, forwards it as a `hf_token` kwarg; the remote function
# sets HF_TOKEN + HUGGINGFACE_HUB_TOKEN env vars in-process.


render_backbone = app.function(
    name="render_backbone",
    image=image,
    volumes=VOLUMES,
    gpu="L40S",
    timeout=60 * 30,
)(_render_impl)


def _read_local_hf_token() -> str | None:
    """Look up a HuggingFace token from env vars or the HF cache file.

    Returns the first token found or None. Used only for flux_dev (the
    gated FLUX.1-dev model). The other backbones do not need a token.
    """
    for var in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_HUB_TOKEN"):
        v = os.environ.get(var)
        if v:
            return v.strip()
    token_path = Path.home() / ".cache" / "huggingface" / "token"
    if token_path.exists():
        return token_path.read_text(encoding="utf-8").strip() or None
    return None


@app.local_entrypoint()
def main(config: str, backbone: str) -> None:
    """Render the configured prompt set on one backbone.

    Args:
        config: path to YAML at examples/configs/validation/<name>.yaml.
        backbone: one of sdxl_lightning, sdxl_base, flux_schnell, flux_dev.
    """
    cfg_path = Path(config).resolve()
    if not cfg_path.exists():
        raise SystemExit(f"Backbone-probe config not found: {cfg_path}")

    yaml_text = cfg_path.read_text(encoding="utf-8")

    hf_token: str | None = None
    if backbone in ("flux_dev", "flux_schnell"):
        # Both FLUX repos require HuggingFace auth as of 2026-05; schnell
        # has been reclassified gated since the initial 2024 Apache-2.0
        # release. dev has always been gated.
        hf_token = _read_local_hf_token()
        if not hf_token:
            raise SystemExit(
                f"{backbone} requires a HuggingFace token "
                "(both FLUX.1-schnell and FLUX.1-dev are gated on the Hub). "
                "Either set HF_TOKEN in your environment, or run "
                "`huggingface-cli login` so a token lands at "
                "~/.cache/huggingface/token, then retry."
            )

    manifest = render_backbone.remote(yaml_text, backbone=backbone, hf_token=hf_token)
    print()
    print(
        f"Backbone probe {manifest['family']} / {manifest['backbone']} complete:"
    )
    print(f"  prompts:        {manifest['num_prompts']}")
    print(f"  wall time:      {manifest['total_seconds']:.1f}s")
    print(
        f"  outputs on volume: {OUTPUTS_VOLUME_NAME}:/{manifest['output_dir_on_volume']}"
    )
    print()
    print("Download with:")
    print(
        f"  modal volume get {OUTPUTS_VOLUME_NAME} "
        f"{manifest['output_dir_on_volume']} outputs/"
    )
