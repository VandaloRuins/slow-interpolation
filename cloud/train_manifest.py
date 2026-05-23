"""Training-run manifest schema and helpers.

Mirrors cloud/manifest.py for the rendering app. Each Modal training
run emits a JSON manifest alongside the trained LoRA checkpoints
capturing what was trained, with what code, on what hardware, at
what cost.

Schema is flat and human-readable. Cost table imports from
cloud/manifest.py so rendering + training share one source of truth.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .manifest import GPU_HOURLY_USD


@dataclass
class RunArtifacts:
    # When and where
    started_at_utc: str
    ended_at_utc: str
    run_id: str
    git_commit: str
    git_dirty: bool

    # What was run
    trainer: str                       # "kohya" or "diffusers"
    trainer_version: str               # sd-scripts commit SHA (or diffusers version)
    base_model: str                    # HF id of base model
    config_yaml: str                   # resolved YAML verbatim
    dataset_zip: str                   # filename on slow-interp-datasets
    dataset_n_images: int              # post-unpack training image count
    trigger: str

    # On what hardware
    gpu_tier: str
    modal_app_name: str
    image_tag: str

    # Output paths on Modal volumes (relative to volume root)
    lora_checkpoints: list[str]
    training_log: str
    validation_contact_sheet: str | None

    # Cost + time
    total_seconds: float
    train_seconds: float
    validation_seconds: float
    gpu_hourly_usd: float
    estimated_cost_usd: float

    # Resolved hyperparameters (forensic re-train)
    network_rank: int
    network_alpha: int
    unet_lr: float
    text_encoder_lr: float
    optimizer: str
    batch_size: int
    gradient_accumulation: int
    repeats: int
    epochs: int
    mixed_precision: str
    min_snr_gamma: float
    resolution: int
    network_train_unet_only: bool

    # HF cache revisions (parity with rendering manifest)
    sdxl_base_revision: str = "unknown"

    # Free-form notes
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def write(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, sort_keys=False)
        return path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def estimate_cost_usd(gpu_tier: str, seconds: float) -> tuple[float, float]:
    """Return (gpu_hourly_usd, estimated_cost_usd). Falls back to 0
    for unknown tiers (recorded as such)."""
    hourly = GPU_HOURLY_USD.get(gpu_tier, 0.0)
    return hourly, hourly * (seconds / 3600.0)


def resolve_git_commit(repo_root: Path) -> tuple[str, bool]:
    """Return (commit_sha, dirty). ('unknown', False) on any failure."""
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        dirty_out = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=str(repo_root),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return sha, bool(dirty_out.strip())
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "unknown", False


def make_run_id(config_name: str, config_yaml_text: str) -> str:
    """Compose a run-id from config name + UTC time + content SHA.

    Format: <config-name>_<UTC-isoformat>_<short-sha>
    Collision-free across configs, time-orderable, reproducible
    (same YAML content gives the same SHA chunk).
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    sha = hashlib.sha256(config_yaml_text.encode("utf-8")).hexdigest()[:8]
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in config_name)
    return f"{safe_name}_{ts}_{sha}"


# Default training hyperparameters. Mirror lora-training.md §3 row-by-row.
# Any YAML field that is absent inherits from here.
_DEFAULT_TRAINING: dict[str, Any] = {
    "network_rank": 16,
    "network_alpha": 8,
    "unet_lr": 3e-5,
    "text_encoder_lr": 0,
    "optimizer": "adamw8bit",
    "lr_scheduler": "cosine_with_restarts",
    "lr_scheduler_num_cycles": 4,
    "batch_size": 2,
    "gradient_accumulation": 4,
    "repeats": 6,
    "epochs": 10,
    "save_every_n_epochs": 1,
    "mixed_precision": "bf16",
    "min_snr_gamma": 5.0,
    "gradient_checkpointing": True,
    "caption_shuffle": False,
    "caption_tag_dropout": 0,
    "resolution": 1024,
    "enable_bucket": True,
    "min_bucket_reso": 768,
    "max_bucket_reso": 1344,
    "bucket_no_upscale": True,
    "network_train_unet_only": True,
}


def merge_training_defaults(user_training: dict[str, Any]) -> dict[str, Any]:
    """Layer user-provided training fields on top of the defaults.
    Returns a new dict; never mutates inputs."""
    merged = dict(_DEFAULT_TRAINING)
    merged.update(user_training or {})
    return merged
