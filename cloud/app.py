"""Modal app definition and the remote render function.

This module is the cloud sibling of `src/slow_interpolation/run.py`. It
loads a `PipelineConfig` from YAML, resolves the configured Pipeline
class via `importlib`, runs `.render()`, and emits a run manifest.

Two override knobs make the app variant-friendly:

- `pipeline_entry` (string, default `slow_interpolation.pipeline:Pipeline`):
  the class to instantiate. Any class with the contract
  `__init__(config: PipelineConfig)` and `.render() -> Path` works.
- `config_loader` (string, default `slow_interpolation.config:load_pipeline_config`):
  the function that turns a YAML path into a config object. Override
  this if you ship a fork with an extended config schema.

Both are set in the optional `modal:` top-level section of the YAML.

Storage layout on the container:

    /root/slow-interpolation/         <- source tree, mounted from local repo
        src/slow_interpolation/
        vendor/rife_v425/
        cloud/
        examples/configs/
        models/loras/   <- Modal Volume (uploaded via upload_weights.py)
        outputs/        <- Modal Volume (downloaded via `modal volume get`)
    /root/.cache/huggingface/   <- Modal Volume (persisted across runs)

GPU tier defaults to L40S (sufficient for 1344x768 SDXL Lightning,
~2 USD/hr). Override via the `modal:` YAML section for heavier work.
"""

from __future__ import annotations

import importlib
import os
import sys
import time
from pathlib import Path
from typing import Any

import modal

from .manifest import (
    PhaseTime,
    RunManifest,
    estimate_cost_usd,
    resolve_git_commit,
    resolve_hf_revisions,
    utc_now_iso,
)


APP_NAME = "slow-interpolation"
CONTAINER_REPO_ROOT = Path("/root/slow-interpolation")
HF_CACHE_PATH = Path("/root/.cache/huggingface")

LORAS_VOLUME_NAME = "slow-interp-loras"
OUTPUTS_VOLUME_NAME = "slow-interp-outputs"
HF_CACHE_VOLUME_NAME = "slow-interp-hf-cache"

DEFAULT_GPU = "L40S"
DEFAULT_TIMEOUT_SEC = 60 * 60  # 1 hour. A 60s loop is ~25 min at L40S.

DEFAULT_PIPELINE_ENTRY = "slow_interpolation.pipeline:Pipeline"
DEFAULT_CONFIG_LOADER = "slow_interpolation.config:load_pipeline_config"


# ---------------------------------------------------------------------------
# Image: CUDA + Python + the package + system ffmpeg.
# ---------------------------------------------------------------------------

# Pin CUDA 12.4 base. diffusers + torch wheels resolve to a cu124 build.
# Python 3.11 is the default on Modal's debian_slim and matches the local
# venv on Luca's machine.
IMAGE_TAG = "py3.11-cu124"

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Modal requires all `add_local_*` calls to come LAST in the image chain
# (otherwise local file changes invalidate downstream build layers). Set
# the env vars and workdir first; mount the source tree last.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "ffmpeg")
    .pip_install(
        "torch==2.5.1",
        "torchvision==0.20.1",
        # PyTorch CUDA 12.4 wheels live on the pytorch index:
        extra_index_url="https://download.pytorch.org/whl/cu124",
    )
    .pip_install(
        "diffusers>=0.30,<0.40",
        "transformers",
        "accelerate",
        "peft",
        "numpy",
        "pillow",
        "imageio",
        "imageio-ffmpeg",
        "pyyaml",
    )
    .env({"PYTHONPATH": "/root/slow-interpolation/src:/root/slow-interpolation"})
    .workdir("/root/slow-interpolation")
    # Mount the local repo source tree at /root/slow-interpolation/.
    # add_local_dir runs at container startup (no image rebuild on
    # source changes); editing src/ and re-running `modal run` ships
    # the new code.
    .add_local_dir(
        local_path=str(_REPO_ROOT / "src"),
        remote_path="/root/slow-interpolation/src",
    )
    .add_local_dir(
        local_path=str(_REPO_ROOT / "vendor"),
        remote_path="/root/slow-interpolation/vendor",
    )
    .add_local_dir(
        local_path=str(_REPO_ROOT / "cloud"),
        remote_path="/root/slow-interpolation/cloud",
    )
    # examples/configs is small (~170 KB) and useful to have on the container
    # for sanity-check renders. Mount ONLY it: `examples/` as a whole is 109 MB,
    # of which `examples/outputs/` is 101 MB of sample MP4s the container never
    # reads, and the client hash-walks the whole tree on every dispatch.
    .add_local_dir(
        local_path=str(_REPO_ROOT / "examples" / "configs"),
        remote_path="/root/slow-interpolation/examples/configs",
    )
)


# ---------------------------------------------------------------------------
# Volumes.
# ---------------------------------------------------------------------------

loras_volume = modal.Volume.from_name(LORAS_VOLUME_NAME, create_if_missing=True)
outputs_volume = modal.Volume.from_name(OUTPUTS_VOLUME_NAME, create_if_missing=True)
hf_cache_volume = modal.Volume.from_name(HF_CACHE_VOLUME_NAME, create_if_missing=True)


app = modal.App(APP_NAME, image=image)


# ---------------------------------------------------------------------------
# The remote render function, defined ONCE as a plain implementation and
# decorated MULTIPLE times below (one per supported GPU tier).
#
# Modal 1.4.x does not support `Function.with_options(gpu=...)` at call
# time, so we statically bind each tier. Callers select a tier via
# `RENDER_BY_GPU[gpu_tier]` (see entrypoint.py / batch.py / smoke.py).
# ---------------------------------------------------------------------------


VOLUMES = {
    "/root/slow-interpolation/models/loras": loras_volume,
    "/root/slow-interpolation/outputs": outputs_volume,
    str(HF_CACHE_PATH): hf_cache_volume,
}


def _render_impl(
    config_yaml_text: str,
    *,
    gpu_tier: str = DEFAULT_GPU,
    pipeline_entry: str = DEFAULT_PIPELINE_ENTRY,
    config_loader: str = DEFAULT_CONFIG_LOADER,
    git_commit: str = "unknown",
    git_dirty: bool = False,
    notes: list[str] | None = None,
    preserve_staging: bool = False,
    skip_keyframes: bool = False,
) -> dict[str, Any]:
    """Render one config end-to-end on a Modal GPU.

    Returns a dict with the output MP4 path on the outputs volume, the
    manifest path, total wall time, and estimated cost. Caller logs and
    downloads via `modal volume get slow-interp-outputs <path>`.
    """
    started = utc_now_iso()
    t0 = time.perf_counter()
    notes = list(notes or [])

    # Resolve pipeline_entry and config_loader.
    pipeline_cls = _resolve_dotted(pipeline_entry)
    load_cfg = _resolve_dotted(config_loader)

    # Write the YAML to a temp path on the container, then load it. We
    # pass YAML text (not path) over the wire so the entrypoint does not
    # need to mount the config file separately.
    cfg_path = CONTAINER_REPO_ROOT / "outputs" / "_inflight" / "config.yaml"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(config_yaml_text, encoding="utf-8")

    config = load_cfg(cfg_path)

    # Force outputs into the mounted volume regardless of what the YAML
    # said. (The local default is "outputs"; on the container we want
    # that to resolve to the volume mount.)
    config.output_dir = CONTAINER_REPO_ROOT / "outputs"

    pipeline = pipeline_cls(config)

    # Run phases with per-phase timing.
    phase_times: list[PhaseTime] = []

    # Phase A is skippable so keyframes can be authored OUTSIDE this pipeline
    # (a stronger model, a real photograph, a hand edit) and this run does only
    # smoothing plus interpolation. Mirrors `run.py --skip-keyframes`. The
    # keyframes must already be on the outputs volume at
    # `staging/<output_name>/keyframes/` before dispatch.
    tA = time.perf_counter()
    if skip_keyframes:
        kf_dir = pipeline.keyframes_dir
        existing = sorted(kf_dir.glob("*.png")) if kf_dir.exists() else []
        if len(existing) < 2:
            raise FileNotFoundError(
                f"skip_keyframes was requested but {kf_dir} holds "
                f"{len(existing)} PNG(s). Upload keyframes to the outputs "
                f"volume at staging/{pipeline.output_name}/keyframes/ first."
            )
        notes.append(f"phase A skipped, reused {len(existing)} staged keyframes")
    else:
        pipeline.generate_keyframes()
    phase_times.append(PhaseTime("A", time.perf_counter() - tA))

    tS = time.perf_counter()
    pipeline.smooth_keyframes()
    phase_times.append(PhaseTime("A.5", time.perf_counter() - tS))

    tC = time.perf_counter()
    output_path = pipeline.interpolate_and_encode()
    phase_times.append(PhaseTime("C+D", time.perf_counter() - tC))

    total = time.perf_counter() - t0
    ended = utc_now_iso()
    hourly, cost = estimate_cost_usd(gpu_tier, total)

    # Capture resolved HF cache revisions for forensic re-render. Models
    # are guaranteed cached by this point (Phase A loaded them).
    hf_revs = resolve_hf_revisions(
        [config.models.sdxl_base, config.models.lightning_lora, config.models.vae]
    )

    if cost > 5.0:
        notes.append(
            f"COST CEILING EXCEEDED: estimated {cost:.2f} USD > 5.00 USD target."
        )

    manifest = RunManifest(
        started_at_utc=started,
        ended_at_utc=ended,
        git_commit=git_commit,
        git_dirty=git_dirty,
        pipeline_entry=pipeline_entry,
        config_loader=config_loader,
        config_yaml=config_yaml_text,
        output_name=pipeline.output_name,
        output_filename=output_path.name,
        gpu_tier=gpu_tier,
        modal_app_name=APP_NAME,
        image_tag=IMAGE_TAG,
        sdxl_base=config.models.sdxl_base,
        lightning_lora=config.models.lightning_lora,
        lightning_weight_name=config.models.lightning_weight_name,
        vae=config.models.vae,
        style_lora_path=str(config.style.lora_path),
        style_lora_scale=config.style.lora_scale,
        sdxl_base_revision=hf_revs.get(config.models.sdxl_base, "unknown"),
        lightning_lora_revision=hf_revs.get(config.models.lightning_lora, "unknown"),
        vae_revision=hf_revs.get(config.models.vae, "unknown"),
        phase_times=phase_times,
        total_seconds=total,
        gpu_hourly_usd=hourly,
        estimated_cost_usd=cost,
        resolution_width=config.resolution.width,
        resolution_height=config.resolution.height,
        rife_passes=config.rife.passes,
        rife_skip_boundary=config.rife.skip_boundary,
        rife_edge_crop=config.rife.edge_crop,
        encoding_fps=config.encoding.fps,
        encoding_quality=config.encoding.quality,
        notes=notes,
    )

    manifest_path = output_path.with_suffix(".manifest.json")
    manifest.write(manifest_path)

    # Staging cleanup. Default ON to keep the outputs volume tidy
    # (each render produces ~150 MB of intermediate PNGs under
    # outputs/staging/<name>/). Opt OUT via `modal.preserve_staging:
    # true` in the YAML when you actively want to inspect Phase A
    # output or download the staged keyframes for offline reuse.
    if not preserve_staging:
        import shutil
        staging_dir = pipeline.staging_dir
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
            notes.append(f"staging cleaned: {staging_dir.name}")
    else:
        notes.append("staging preserved (modal.preserve_staging=true)")

    # Commit the outputs volume so the host can `modal volume get` them.
    outputs_volume.commit()
    hf_cache_volume.commit()

    return {
        "output_volume": OUTPUTS_VOLUME_NAME,
        "output_path": str(output_path.relative_to(CONTAINER_REPO_ROOT / "outputs")),
        "manifest_path": str(manifest_path.relative_to(CONTAINER_REPO_ROOT / "outputs")),
        "total_seconds": total,
        "estimated_cost_usd": cost,
        "gpu_tier": gpu_tier,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Per-tier function bindings.
#
# Each tier becomes its own Modal Function. RENDER_BY_GPU dispatches at
# call time. Add a new tier here when needed (e.g. H200, L4); it ships
# with the next `modal deploy`.
#
# `render_warm` is a sibling of `render` (L40S) with keep_warm=1 and
# container_idle_timeout=1800 (30 min idle hard-cap). Used by
# cloud/release_batch.py for sequential-dispatch sessions; the
# container_idle_timeout is the safety net guaranteeing worst-case
# forgotten cost stays under ~0.50 USD.
# ---------------------------------------------------------------------------


render = app.function(
    name="render",
    gpu="L40S",
    timeout=DEFAULT_TIMEOUT_SEC,
    volumes=VOLUMES,
)(_render_impl)

render_a100_40 = app.function(
    name="render_a100_40",
    gpu="A100-40GB",
    timeout=DEFAULT_TIMEOUT_SEC,
    volumes=VOLUMES,
)(_render_impl)

render_a100_80 = app.function(
    name="render_a100_80",
    gpu="A100-80GB",
    timeout=DEFAULT_TIMEOUT_SEC,
    volumes=VOLUMES,
)(_render_impl)

render_h100 = app.function(
    name="render_h100",
    gpu="H100",
    timeout=DEFAULT_TIMEOUT_SEC,
    volumes=VOLUMES,
)(_render_impl)

render_a10g = app.function(
    name="render_a10g",
    gpu="A10G",
    timeout=DEFAULT_TIMEOUT_SEC,
    volumes=VOLUMES,
)(_render_impl)


RENDER_BY_GPU: dict[str, Any] = {
    "L40S": render,
    "A100-40GB": render_a100_40,
    "A100-80GB": render_a100_80,
    "H100": render_h100,
    "A10G": render_a10g,
}


# Warm-pool variant: L40S only initially. Add more tiers if release
# sessions ever need a different GPU; see cloud/release_batch.py docs
# for when warm-pool earns its keep.
#
# Modal 1.4.x renamed legacy parameters:
#   keep_warm                → min_containers
#   container_idle_timeout   → scaledown_window
# min_containers=0 means no warm pool by default; caller induces warmth
# by dispatching repeated calls within scaledown_window (30 min).
render_warm = app.function(
    name="render_warm",
    gpu="L40S",
    timeout=DEFAULT_TIMEOUT_SEC,
    volumes=VOLUMES,
    scaledown_window=1800,  # 30 min idle hard-cap safety net
    min_containers=0,  # caller holds the warm container via repeated calls
)(_render_impl)


def resolve_render_fn(gpu_tier: str, *, warm: bool = False) -> Any:
    """Return the Modal Function bound to a given GPU tier.

    Args:
        gpu_tier: e.g. "L40S", "A100-40GB", "A100-80GB", "H100", "A10G".
        warm: if True, return the warm-pool variant (L40S only).

    Falls back to the default (L40S, non-warm) for unknown tiers so
    the caller's render at least dispatches; the manifest still
    records the requested gpu_tier for forensic clarity.
    """
    if warm:
        return render_warm
    return RENDER_BY_GPU.get(gpu_tier, render)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_dotted(spec: str) -> Any:
    """Resolve a "module.path:attribute" string to the attribute object.

    Used for `pipeline_entry` and `config_loader`. This is the single
    hook that decouples this app from any specific Pipeline / config
    schema implementation.
    """
    if ":" not in spec:
        raise ValueError(
            f"Invalid dotted spec {spec!r}. "
            f"Expected 'module.path:attribute' (e.g. "
            f"'slow_interpolation.pipeline:Pipeline')."
        )
    module_path, attr = spec.split(":", 1)
    module = importlib.import_module(module_path)
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise AttributeError(
            f"Module {module_path!r} has no attribute {attr!r} "
            f"(resolved from dotted spec {spec!r})."
        ) from exc
