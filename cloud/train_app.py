"""Modal app for SDXL LoRA training. Sibling of cloud/app.py (renderer).

Wraps `kohya-ss/sd-scripts` `sdxl_train_network.py` as a subprocess
inside a Modal container. Reads a YAML config, generates the
sd-scripts toml, runs training, optionally validates each saved
checkpoint by rendering hold-out prompts on it, emits a RunArtifacts
manifest, writes outputs to the slow-interp-loras volume.

Storage layout on the container:

    /root/slow-interpolation/         <- source tree, mounted from local repo
        src/slow_interpolation/
        cloud/
        examples/configs/
        models/loras/                 <- Modal Volume (output target)
        datasets/                     <- Modal Volume (input ZIPs)
        train-artifacts/              <- Modal Volume (manifests + contact sheets)
    /opt/sd-scripts/                  <- kohya-ss/sd-scripts at pinned commit
    /root/.cache/huggingface/         <- Modal Volume (SDXL base, shared with renderer)

Multi-tier GPU dispatch mirrors cloud/app.py: define one
`@app.function` per GPU tier, dispatch via `TRAIN_BY_GPU[tier]`.
Modal 1.4.x does not support `Function.with_options(gpu=...)` at
call time.

See docs/planning/workstreams/modal-trainer/design.md for the full
design rationale.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Any

import modal

from .manifest import resolve_hf_revisions
from .train_manifest import (
    RunArtifacts,
    estimate_cost_usd,
    make_run_id,
    merge_training_defaults,
    utc_now_iso,
)


APP_NAME = "slow-interpolation-trainer"
CONTAINER_REPO_ROOT = Path("/root/slow-interpolation")
HF_CACHE_PATH = Path("/root/.cache/huggingface")
SD_SCRIPTS_DIR = Path("/opt/sd-scripts")

# Shared with rendering app. Trained LoRAs land here under runs/<run-id>/
# so the renderer picks them up immediately.
LORAS_VOLUME_NAME = "slow-interp-loras"

# New volumes specific to the trainer.
DATASETS_VOLUME_NAME = "slow-interp-datasets"
ARTIFACTS_VOLUME_NAME = "slow-interp-train-artifacts"

# Shared with rendering app.
HF_CACHE_VOLUME_NAME = "slow-interp-hf-cache"

DEFAULT_GPU = "L40S"
DEFAULT_TIMEOUT_SEC = 4 * 60 * 60  # 4 h ceiling. Renoir-shape runs land ~35 min.

# Pinned sd-scripts commit. Resolved 2026-05-18 during the G3 cold-run
# (Renoir training, app ap-EpvH1RuwPGX7IkKRx6NjG0, manifest
# trainer_version="502cc3fab2aa"). Captured into the image at build
# time. Bump deliberately; track in design doc.
SD_SCRIPTS_REPO = "https://github.com/kohya-ss/sd-scripts.git"
SD_SCRIPTS_COMMIT = "502cc3fab2aa"

IMAGE_TAG = "py3.11-cu124-sd-scripts"

_REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Image: CUDA + Python + sd-scripts + supporting libs.
# Add_local_dir calls last (Modal API rule, confirmed by rendering app build).
# ---------------------------------------------------------------------------

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .pip_install(
        "torch==2.5.1",
        "torchvision==0.20.1",
        extra_index_url="https://download.pytorch.org/whl/cu124",
    )
    .pip_install(
        "xformers==0.0.28.post3",
        "diffusers>=0.30,<0.40",
        "transformers",
        "accelerate",
        "peft",
        "bitsandbytes",
        "safetensors",
        "pillow",
        "pyyaml",
        "numpy",
        "huggingface-hub",
        # sd-scripts' own deps (would come from its requirements.txt, but
        # that file ends with a `.` self-install line that breaks `pip
        # install -r` and there is no clean way to strip it from a Modal
        # RUN step. Install the deps explicitly; they all sit on top of
        # our cu124 torch.). Includes opencv-python-headless (cv2 import
        # at sd-scripts startup), albumentations (augmentations),
        # voluptuous (config validation), omegaconf, imagesize,
        # pytorch-lightning, tensorboard, schedulefree, plus the
        # optimisers + multimodal libs already useful for validation:
        "einops",
        "open-clip-torch",
        "lion-pytorch",
        "prodigyopt",
        "toml",
        "opencv-python-headless",
        "albumentations",
        "voluptuous",
        "omegaconf",
        "imagesize",
        "pytorch-lightning",
        "tensorboard",
        "schedulefree",
    )
    .run_commands(
        # Force posix paths: on Windows hosts, str(Path("/opt/sd-scripts"))
        # returns "\opt\sd-scripts" which the Linux remote shell parses
        # as a single token "optsd-scripts". `.as_posix()` keeps slashes.
        f"git clone {SD_SCRIPTS_REPO} {SD_SCRIPTS_DIR.as_posix()}",
        f"cd {SD_SCRIPTS_DIR.as_posix()} && git checkout {SD_SCRIPTS_COMMIT}",
    )
    .env(
        {
            "PYTHONPATH": (
                "/root/slow-interpolation/src"
                ":/root/slow-interpolation"
                ":/opt/sd-scripts"
            ),
            "HF_HOME": "/root/.cache/huggingface",
            "TOKENIZERS_PARALLELISM": "false",
        }
    )
    .workdir("/root/slow-interpolation")
    .add_local_dir(
        local_path=str(_REPO_ROOT / "src"),
        remote_path="/root/slow-interpolation/src",
    )
    .add_local_dir(
        local_path=str(_REPO_ROOT / "cloud"),
        remote_path="/root/slow-interpolation/cloud",
    )
    .add_local_dir(
        local_path=str(_REPO_ROOT / "examples"),
        remote_path="/root/slow-interpolation/examples",
    )
)


# ---------------------------------------------------------------------------
# Volumes.
# ---------------------------------------------------------------------------

loras_volume = modal.Volume.from_name(LORAS_VOLUME_NAME, create_if_missing=True)
datasets_volume = modal.Volume.from_name(DATASETS_VOLUME_NAME, create_if_missing=True)
artifacts_volume = modal.Volume.from_name(ARTIFACTS_VOLUME_NAME, create_if_missing=True)
hf_cache_volume = modal.Volume.from_name(HF_CACHE_VOLUME_NAME, create_if_missing=True)

VOLUMES = {
    "/root/slow-interpolation/models/loras": loras_volume,
    "/root/slow-interpolation/datasets": datasets_volume,
    "/root/slow-interpolation/train-artifacts": artifacts_volume,
    str(HF_CACHE_PATH): hf_cache_volume,
}


app = modal.App(APP_NAME, image=image)


# ---------------------------------------------------------------------------
# Training function body. Decorated once per GPU tier (see below).
# ---------------------------------------------------------------------------


def _train_impl(
    config_yaml_text: str,
    *,
    gpu_tier: str = DEFAULT_GPU,
    config_name: str = "training",
    git_commit: str = "unknown",
    git_dirty: bool = False,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    """Run one SDXL LoRA training end-to-end on the container.

    Returns a dict with paths on the volumes + cost + timing. Caller
    downloads via `modal volume get`.
    """
    import yaml

    started = utc_now_iso()
    t0 = time.perf_counter()
    notes = list(notes or [])

    cfg = yaml.safe_load(config_yaml_text)
    if cfg is None or not isinstance(cfg, dict):
        raise ValueError("Empty or invalid training YAML")

    trainer = cfg.get("trainer", "kohya")
    if trainer == "diffusers":
        raise NotImplementedError(
            "diffusers fallback trainer not implemented in v1; switch is a "
            "documented contingency. Pin trainer: kohya for now."
        )
    if trainer != "kohya":
        raise ValueError(f"Unknown trainer: {trainer!r}. Expected 'kohya' or 'diffusers'.")

    base_model = cfg.get("base_model", "stabilityai/stable-diffusion-xl-base-1.0")
    dataset_cfg = cfg.get("dataset") or {}
    dataset_zip_name = dataset_cfg.get("zip")
    if not dataset_zip_name:
        raise ValueError("dataset.zip is required (filename inside slow-interp-datasets volume)")
    trigger = dataset_cfg.get("trigger")
    if not trigger:
        raise ValueError("dataset.trigger is required")
    caption_ext = dataset_cfg.get("caption_extension", ".txt")

    training = merge_training_defaults(cfg.get("training") or {})

    if cfg.get("per_image_repeats"):
        raise NotImplementedError(
            "per_image_repeats is a v2 feature. See "
            "docs/planning/workstreams/modal-trainer/design.md "
            "'Future work' for the implementation sketch. v1 uses uniform repeats."
        )

    validation = cfg.get("validation") or {}

    run_id = make_run_id(config_name, config_yaml_text)
    print(f"[train] run_id: {run_id}")

    # --- prepare dataset on container ---
    zip_path = CONTAINER_REPO_ROOT / "datasets" / dataset_zip_name
    if not zip_path.exists():
        raise FileNotFoundError(
            f"Dataset ZIP not found on slow-interp-datasets volume: {dataset_zip_name}. "
            "Upload via: modal run -m cloud.upload_dataset --src <local-zip>"
        )

    work_root = Path("/tmp") / "train" / run_id
    dataset_dir = work_root / "dataset"
    output_dir = work_root / "output"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    # sd-scripts expects: <dataset_dir>/<repeats>_<concept>/{image.jpg, image.txt}
    # Use a single subset folder named "<repeats>_<trigger>".
    subset_dir = dataset_dir / f"{int(training['repeats'])}_{trigger}"
    subset_dir.mkdir(parents=True, exist_ok=True)
    n_images = _unpack_zip_to_subset(zip_path, subset_dir, caption_ext, trigger)
    notes.append(f"unpacked {n_images} image/caption pairs to {subset_dir.name}")

    # --- generate sd-scripts toml configs ---
    training_toml = work_root / "training.toml"
    dataset_toml = work_root / "dataset.toml"
    log_path = output_dir / "training.log"

    _write_dataset_toml(dataset_toml, subset_dir, training)
    _write_training_toml(
        training_toml,
        base_model=base_model,
        dataset_config=dataset_toml,
        output_dir=output_dir,
        output_name=run_id,
        training=training,
    )

    # --- run training via accelerate launch ---
    train_t0 = time.perf_counter()
    try:
        _run_sd_scripts_training(
            training_toml,
            log_path=log_path,
            mixed_precision=str(training["mixed_precision"]),
        )
    except subprocess.CalledProcessError as exc:
        notes.append(f"TRAINING FAILED (exit {exc.returncode}); log preserved at {log_path}")
        raise
    train_seconds = time.perf_counter() - train_t0

    # --- collect saved checkpoints ---
    checkpoints = sorted(output_dir.glob("*.safetensors"))
    if not checkpoints:
        raise RuntimeError(
            f"sd-scripts ran but produced no .safetensors in {output_dir}. "
            f"Check {log_path}."
        )
    notes.append(f"saved {len(checkpoints)} checkpoint(s)")

    # --- copy checkpoints to slow-interp-loras volume under runs/<run-id>/ ---
    loras_runs_dir = CONTAINER_REPO_ROOT / "models" / "loras" / "runs" / run_id
    loras_runs_dir.mkdir(parents=True, exist_ok=True)
    persisted_checkpoints: list[str] = []
    for ckpt in checkpoints:
        dest = loras_runs_dir / ckpt.name
        shutil.copy2(ckpt, dest)
        persisted_checkpoints.append(
            str(dest.relative_to(CONTAINER_REPO_ROOT / "models" / "loras"))
        )

    # --- optionally publish checkpoints to the top of the loras volume
    # under a stable filename so existing renderers (e.g.
    # cloud/validation_renoir.py) can load them by convention.
    publish_cfg = cfg.get("publish") or {}
    published: list[str] = []
    template = publish_cfg.get("checkpoint_template")
    if template:
        loras_root = CONTAINER_REPO_ROOT / "models" / "loras"
        for ckpt in checkpoints:
            if ckpt.stem == run_id:
                epoch = int(training["epochs"])
            else:
                parsed = _parse_checkpoint_epoch(ckpt.stem)
                if parsed is None:
                    continue
                epoch = parsed
            published_name = template.format(epoch=epoch)
            published_path = loras_root / published_name
            shutil.copy2(ckpt, published_path)
            published.append(published_name)
        notes.append(f"published {len(published)} checkpoint(s) via template {template!r}")

    # --- copy training log to artifacts volume ---
    artifacts_run_dir = CONTAINER_REPO_ROOT / "train-artifacts" / "runs" / run_id
    artifacts_run_dir.mkdir(parents=True, exist_ok=True)
    persisted_log = artifacts_run_dir / "training.log"
    if log_path.exists():
        shutil.copy2(log_path, persisted_log)

    # --- validation pass (optional) ---
    val_t0 = time.perf_counter()
    validation_contact_sheet: str | None = None
    if validation and validation.get("prompts"):
        try:
            contact_sheet_path = _run_validation(
                checkpoints=checkpoints,
                output_name_base=run_id,
                base_model=base_model,
                validation=validation,
                artifacts_dir=artifacts_run_dir,
                total_epochs=int(training["epochs"]),
            )
            validation_contact_sheet = str(
                contact_sheet_path.relative_to(CONTAINER_REPO_ROOT / "train-artifacts")
            )
            notes.append(f"validation contact sheet: {validation_contact_sheet}")
        except Exception as exc:
            notes.append(f"VALIDATION FAILED: {exc!r}; training checkpoints still saved")
    validation_seconds = time.perf_counter() - val_t0

    total = time.perf_counter() - t0
    ended = utc_now_iso()
    hourly, cost = estimate_cost_usd(gpu_tier, total)
    if cost > 4.0:
        notes.append(
            f"COST CEILING EXCEEDED: estimated {cost:.2f} USD > 4.00 USD cold-run target."
        )

    hf_revs = resolve_hf_revisions([base_model])

    manifest = RunArtifacts(
        started_at_utc=started,
        ended_at_utc=ended,
        run_id=run_id,
        git_commit=git_commit,
        git_dirty=git_dirty,
        trainer=trainer,
        trainer_version=_resolve_sd_scripts_commit(),
        base_model=base_model,
        config_yaml=config_yaml_text,
        dataset_zip=dataset_zip_name,
        dataset_n_images=n_images,
        trigger=trigger,
        gpu_tier=gpu_tier,
        modal_app_name=APP_NAME,
        image_tag=IMAGE_TAG,
        lora_checkpoints=persisted_checkpoints,
        training_log=str(persisted_log.relative_to(CONTAINER_REPO_ROOT / "train-artifacts")),
        validation_contact_sheet=validation_contact_sheet,
        total_seconds=total,
        train_seconds=train_seconds,
        validation_seconds=validation_seconds,
        gpu_hourly_usd=hourly,
        estimated_cost_usd=cost,
        network_rank=int(training["network_rank"]),
        network_alpha=int(training["network_alpha"]),
        unet_lr=float(training["unet_lr"]),
        text_encoder_lr=float(training["text_encoder_lr"]),
        optimizer=str(training["optimizer"]),
        batch_size=int(training["batch_size"]),
        gradient_accumulation=int(training["gradient_accumulation"]),
        repeats=int(training["repeats"]),
        epochs=int(training["epochs"]),
        mixed_precision=str(training["mixed_precision"]),
        min_snr_gamma=float(training["min_snr_gamma"]),
        resolution=int(training["resolution"]),
        network_train_unet_only=bool(training["network_train_unet_only"]),
        sdxl_base_revision=hf_revs.get(base_model, "unknown"),
        notes=notes,
    )

    manifest_path = artifacts_run_dir / "manifest.json"
    manifest.write(manifest_path)

    # Commit volumes so the host can `modal volume get`.
    loras_volume.commit()
    artifacts_volume.commit()
    hf_cache_volume.commit()

    return {
        "run_id": run_id,
        "loras_volume": LORAS_VOLUME_NAME,
        "artifacts_volume": ARTIFACTS_VOLUME_NAME,
        "lora_checkpoints": persisted_checkpoints,
        "manifest_path": str(manifest_path.relative_to(CONTAINER_REPO_ROOT / "train-artifacts")),
        "validation_contact_sheet": validation_contact_sheet,
        "total_seconds": total,
        "train_seconds": train_seconds,
        "estimated_cost_usd": cost,
        "gpu_tier": gpu_tier,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Per-tier function bindings. Modal 1.4.x lacks `Function.with_options(gpu=)`.
# ---------------------------------------------------------------------------


train_lora = app.function(
    name="train_lora",
    gpu="L40S",
    timeout=DEFAULT_TIMEOUT_SEC,
    volumes=VOLUMES,
)(_train_impl)

train_lora_a100_40 = app.function(
    name="train_lora_a100_40",
    gpu="A100-40GB",
    timeout=DEFAULT_TIMEOUT_SEC,
    volumes=VOLUMES,
)(_train_impl)

train_lora_a100_80 = app.function(
    name="train_lora_a100_80",
    gpu="A100-80GB",
    timeout=DEFAULT_TIMEOUT_SEC,
    volumes=VOLUMES,
)(_train_impl)

train_lora_h100 = app.function(
    name="train_lora_h100",
    gpu="H100",
    timeout=DEFAULT_TIMEOUT_SEC,
    volumes=VOLUMES,
)(_train_impl)


TRAIN_BY_GPU: dict[str, Any] = {
    "L40S": train_lora,
    "A100-40GB": train_lora_a100_40,
    "A100-80GB": train_lora_a100_80,
    "H100": train_lora_h100,
}


def resolve_train_fn(gpu_tier: str) -> Any:
    """Return the Modal Function bound to a given GPU tier. Falls back
    to L40S default for unknown tiers; the manifest still records the
    requested tier for forensic clarity."""
    return TRAIN_BY_GPU.get(gpu_tier, train_lora)


# ---------------------------------------------------------------------------
# Dataset unpack
# ---------------------------------------------------------------------------


def _unpack_zip_to_subset(
    zip_path: Path,
    subset_dir: Path,
    caption_ext: str,
    trigger: str,
) -> int:
    """Extract a CivitAI-shape ZIP (<name>.jpg + <name>.txt pairs) into
    `subset_dir`. Validates that every caption starts with `<trigger>,`.
    Returns the count of image/caption pairs.
    """
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(subset_dir)

    images = sorted(p for p in subset_dir.glob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})
    if not images:
        raise RuntimeError(f"No images found inside {zip_path.name} after unpack")

    n_with_caption = 0
    missing_trigger: list[str] = []
    for img in images:
        cap_path = img.with_suffix(caption_ext)
        if not cap_path.exists():
            continue
        n_with_caption += 1
        cap_text = cap_path.read_text(encoding="utf-8").strip()
        first_token = cap_text.split(",", 1)[0].strip().lower()
        if first_token != trigger.lower():
            missing_trigger.append(img.name)

    if n_with_caption == 0:
        raise RuntimeError(
            f"Found {len(images)} images but zero captions in {zip_path.name}. "
            f"Expected <name>{caption_ext} sidecars."
        )
    if missing_trigger:
        sample = ", ".join(missing_trigger[:5])
        more = f" (+{len(missing_trigger) - 5} more)" if len(missing_trigger) > 5 else ""
        raise RuntimeError(
            f"{len(missing_trigger)} captions do not lead with trigger {trigger!r}: "
            f"{sample}{more}. Fix the ZIP and re-upload."
        )
    return n_with_caption


# ---------------------------------------------------------------------------
# sd-scripts toml generation
# ---------------------------------------------------------------------------


def _write_dataset_toml(
    toml_path: Path,
    subset_image_dir: Path,
    training: dict[str, Any],
) -> None:
    """sd-scripts dataset config.

    `subset_image_dir` is the folder that contains the loose image +
    caption pairs (not its parent). When using the TOML subsets API,
    sd-scripts does NOT walk into <N>_<concept> subfolders looking for
    images; `image_dir` must be the leaf folder."""
    import toml

    payload = {
        "general": {
            "enable_bucket": bool(training["enable_bucket"]),
            "min_bucket_reso": int(training["min_bucket_reso"]),
            "max_bucket_reso": int(training["max_bucket_reso"]),
            "bucket_no_upscale": bool(training["bucket_no_upscale"]),
            "shuffle_caption": bool(training["caption_shuffle"]),
            "caption_tag_dropout_rate": float(training["caption_tag_dropout"]),
            "caption_extension": ".txt",
            "keep_tokens": 1,  # the trigger token stays at position 0
            "color_aug": False,
            "flip_aug": False,
            "random_crop": False,
        },
        "datasets": [
            {
                "resolution": int(training["resolution"]),
                "batch_size": int(training["batch_size"]),
                "subsets": [
                    {
                        "image_dir": str(subset_image_dir),
                        "num_repeats": int(training["repeats"]),
                    }
                ],
            }
        ],
    }
    toml_path.write_text(toml.dumps(payload), encoding="utf-8")


def _write_training_toml(
    toml_path: Path,
    *,
    base_model: str,
    dataset_config: Path,
    output_dir: Path,
    output_name: str,
    training: dict[str, Any],
) -> None:
    """sd-scripts training config for sdxl_train_network.py.

    Field names match sd-scripts' CLI / toml conventions. We pass the
    config file via `--config_file` so the CLI line stays short.
    """
    import toml

    payload = {
        "pretrained_model_name_or_path": base_model,
        "dataset_config": str(dataset_config),
        "output_dir": str(output_dir),
        "output_name": output_name,
        "save_model_as": "safetensors",
        "save_every_n_epochs": int(training["save_every_n_epochs"]),
        "max_train_epochs": int(training["epochs"]),
        "mixed_precision": str(training["mixed_precision"]),
        "save_precision": str(training["mixed_precision"]),
        "gradient_checkpointing": bool(training["gradient_checkpointing"]),
        "gradient_accumulation_steps": int(training["gradient_accumulation"]),
        "min_snr_gamma": float(training["min_snr_gamma"]),
        "network_module": "networks.lora",
        "network_dim": int(training["network_rank"]),
        "network_alpha": float(training["network_alpha"]),
        "network_train_unet_only": bool(training["network_train_unet_only"]),
        "unet_lr": float(training["unet_lr"]),
        "text_encoder_lr": float(training["text_encoder_lr"]),
        "optimizer_type": _kohya_optimizer_name(str(training["optimizer"])),
        "lr_scheduler": str(training["lr_scheduler"]),
        "lr_scheduler_num_cycles": int(training["lr_scheduler_num_cycles"]),
        "xformers": True,
        "cache_latents": True,
        "cache_text_encoder_outputs": True,
        "no_half_vae": True,
        "max_data_loader_n_workers": 0,
        "persistent_data_loader_workers": False,
        "seed": 42,
    }
    toml_path.write_text(toml.dumps(payload), encoding="utf-8")


def _kohya_optimizer_name(name: str) -> str:
    """Map our YAML's optimizer aliases to sd-scripts' expected strings."""
    mapping = {
        "adamw": "AdamW",
        "adamw8bit": "AdamW8bit",
        "prodigy": "Prodigy",
        "adafactor": "Adafactor",
        "lion": "Lion",
    }
    return mapping.get(name.lower(), name)


def _run_sd_scripts_training(
    training_toml: Path,
    *,
    log_path: Path,
    mixed_precision: str,
) -> None:
    """Subprocess-launch sd-scripts sdxl_train_network.py via accelerate.

    Tees output to both the log file (for the artifacts volume) and the
    container stdout (so Modal's run page shows the live progress and
    any failure surfaces in the CLI on raise).
    """
    script = SD_SCRIPTS_DIR / "sdxl_train_network.py"
    cmd = [
        "accelerate", "launch",
        "--num_cpu_threads_per_process", "1",
        "--mixed_precision", mixed_precision,
        str(script),
        "--config_file", str(training_toml),
    ]
    print(f"[train] launching: {' '.join(cmd)}", flush=True)
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(SD_SCRIPTS_DIR),
        bufsize=1,
        text=True,
    )
    with log_path.open("w", encoding="utf-8") as log_f:
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            log_f.write(line)
    process.wait()
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, cmd)


def _resolve_sd_scripts_commit() -> str:
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(SD_SCRIPTS_DIR),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return sha[:12]
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Validation: render hold-out prompts on each saved checkpoint, contact-sheet.
# ---------------------------------------------------------------------------


def _run_validation(
    *,
    checkpoints: list[Path],
    output_name_base: str,
    base_model: str,
    validation: dict[str, Any],
    artifacts_dir: Path,
    total_epochs: int,
) -> Path:
    """For each saved checkpoint matching validation.render_at_epochs,
    render every prompt at validation.lora_scale + validation.seed,
    compose a contact sheet PNG.

    Returns the path of the saved contact sheet.
    """
    import torch
    from diffusers import StableDiffusionXLPipeline
    from PIL import Image

    prompts: list[str] = list(validation.get("prompts") or [])
    if not prompts:
        raise RuntimeError("validation.prompts is empty")

    render_epochs: set[int] = set(validation.get("render_at_epochs") or [])
    scale: float = float(validation.get("lora_scale", 0.8))
    seed: int = int(validation.get("seed", 0))

    # Match checkpoints to epoch numbers. sd-scripts saves intermediate
    # epochs as `<base>-NNNNNN.safetensors` and the FINAL epoch
    # un-suffixed as `<base>.safetensors`. Assign the un-suffixed one
    # to `total_epochs`.
    chosen: list[tuple[int, Path]] = []
    for ckpt in checkpoints:
        if ckpt.stem == output_name_base:
            epoch = total_epochs
        else:
            epoch = _parse_checkpoint_epoch(ckpt.stem)
        if epoch is None:
            continue
        if not render_epochs or epoch in render_epochs:
            chosen.append((epoch, ckpt))

    if not chosen:
        raise RuntimeError(
            f"No saved checkpoints matched validation.render_at_epochs={sorted(render_epochs)}"
        )

    # Render each (epoch, prompt) cell.
    rows: list[list[Image.Image]] = []
    for epoch, ckpt in sorted(chosen):
        print(f"[validation] epoch {epoch}: loading {ckpt.name}")
        pipe = StableDiffusionXLPipeline.from_pretrained(
            base_model, torch_dtype=torch.float16, variant="fp16"
        ).to("cuda")
        pipe.safety_checker = None
        pipe.load_lora_weights(str(ckpt))
        pipe.fuse_lora(lora_scale=scale)

        row: list[Image.Image] = []
        for i, prompt in enumerate(prompts):
            gen = torch.Generator(device="cuda").manual_seed(seed + i)
            print(f"[validation]   prompt {i+1}/{len(prompts)}: {prompt[:60]}...")
            img = pipe(
                prompt,
                num_inference_steps=30,
                guidance_scale=7.5,
                generator=gen,
                height=1024,
                width=1024,
            ).images[0]
            row.append(img)

        pipe.unload_lora_weights()
        del pipe
        torch.cuda.empty_cache()
        rows.append(row)

    contact_sheet = _compose_contact_sheet(rows, cell_size=512)
    out_path = artifacts_dir / "validation.png"
    contact_sheet.save(out_path)
    return out_path


def _parse_checkpoint_epoch(stem: str) -> int | None:
    """sd-scripts saves checkpoints as `<output_name>-<epoch>.safetensors`
    or `<output_name>-step<N>.safetensors`. We want the epoch flavour."""
    # Try `<base>-<N>` form (the most common save_every_n_epochs output)
    if "-" not in stem:
        return None
    tail = stem.rsplit("-", 1)[-1]
    if tail.startswith("step"):
        return None
    try:
        return int(tail)
    except ValueError:
        return None


def _compose_contact_sheet(rows: list[list], *, cell_size: int = 512):
    from PIL import Image

    n_rows = len(rows)
    n_cols = max(len(r) for r in rows)
    sheet = Image.new("RGB", (n_cols * cell_size, n_rows * cell_size), (0, 0, 0))
    for r, row in enumerate(rows):
        for c, img in enumerate(row):
            cell = img.resize((cell_size, cell_size), Image.LANCZOS)
            sheet.paste(cell, (c * cell_size, r * cell_size))
    return sheet
