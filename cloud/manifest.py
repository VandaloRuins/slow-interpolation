"""Run-manifest schema and helpers.

Every Modal render emits a JSON manifest next to the MP4 capturing what
was rendered, with what code, on what hardware, at what cost. This is
what makes a Modal run reproducible after the fact.

Schema is intentionally flat and human-readable. No nesting beyond one
level. Times in seconds, cost in USD.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Modal published per-second prices (USD), approximate, source: Modal
# pricing page. Used for cost estimation only; the manifest also records
# the GPU tier and wall time so the user can recompute against current
# prices.
GPU_HOURLY_USD = {
    "T4": 0.59,
    "L4": 0.80,
    "A10G": 1.10,
    "L40S": 1.95,
    "A100-40GB": 2.78,
    "A100-80GB": 3.40,
    "H100": 4.56,
    "H200": 5.50,
}


@dataclass
class PhaseTime:
    phase: str  # "A", "A.5", "C+D"
    seconds: float


@dataclass
class RunManifest:
    # When and where
    started_at_utc: str
    ended_at_utc: str
    git_commit: str
    git_dirty: bool

    # What was run
    pipeline_entry: str
    config_loader: str
    config_yaml: str  # the resolved YAML text, verbatim
    output_name: str
    output_filename: str  # basename of the MP4

    # On what hardware
    gpu_tier: str
    modal_app_name: str
    image_tag: str  # e.g. python version + CUDA tag for the image

    # Resolved model identifiers (post-config defaults)
    sdxl_base: str
    lightning_lora: str
    lightning_weight_name: str
    vae: str
    style_lora_path: str
    style_lora_scale: float

    # Wall time per phase
    phase_times: list[PhaseTime]
    total_seconds: float

    # Cost
    gpu_hourly_usd: float
    estimated_cost_usd: float

    # Render parameters that matter for reproducibility
    resolution_width: int
    resolution_height: int
    rife_passes: int
    rife_skip_boundary: int
    rife_edge_crop: int
    encoding_fps: int
    encoding_quality: int

    # Free-form notes the entrypoint may add
    notes: list[str] = field(default_factory=list)

    # Resolved HF cache revision SHAs for forensic re-render. HuggingFace
    # silently pushes new revisions of base models; without capture, a
    # future re-render against the same model ID produces different
    # output. Captured at render time from the on-disk cache; fall back
    # to "unknown" if the model is not in cache (it should be, since
    # render() loaded it).
    sdxl_base_revision: str = "unknown"
    lightning_lora_revision: str = "unknown"
    vae_revision: str = "unknown"

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
    """Return (gpu_hourly_usd, estimated_cost_usd) for the given GPU tier
    and wall time. Falls back to 0 for unknown tiers (recorded as such)."""
    hourly = GPU_HOURLY_USD.get(gpu_tier, 0.0)
    return hourly, hourly * (seconds / 3600.0)


def resolve_hf_revisions(model_ids: list[str]) -> dict[str, str]:
    """Scan the local HuggingFace cache and return {model_id: revision_sha}
    for every model in `model_ids` that is present. Missing models
    resolve to "unknown".

    Called from inside the Modal container after the models have been
    loaded (and therefore cached), so every requested model should be
    present.
    """
    revisions: dict[str, str] = {mid: "unknown" for mid in model_ids}
    try:
        from huggingface_hub import scan_cache_dir
    except ImportError:
        return revisions

    try:
        cache_info = scan_cache_dir()
    except Exception:
        return revisions

    by_repo = {repo.repo_id: repo for repo in cache_info.repos}
    for mid in model_ids:
        repo = by_repo.get(mid)
        if repo is None or not repo.revisions:
            continue
        # In practice every render uses one revision per model, so the
        # common case is len(revisions) == 1. When multiple revisions
        # are cached, prefer the most recently modified; fall back to
        # any revision if attribute names differ across hf-hub versions.
        revs = list(repo.revisions)
        if len(revs) == 1:
            chosen = revs[0]
        else:
            try:
                chosen = max(revs, key=lambda r: getattr(r, "last_modified", 0))
            except (AttributeError, TypeError):
                chosen = revs[0]
        revisions[mid] = chosen.commit_hash
    return revisions


def resolve_git_commit(repo_root: Path) -> tuple[str, bool]:
    """Return (commit_sha, dirty). Falls back to ('unknown', False) if
    git is not available or the directory is not a repo."""
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
