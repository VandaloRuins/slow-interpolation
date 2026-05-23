"""CLI entrypoint for `modal run -m cloud.train_entrypoint`.

Reads a local training YAML config, dispatches to the right
GPU-tier-bound function via `resolve_train_fn(gpu_tier)`, prints a
cost summary at end. Sibling of cloud/entrypoint.py.

Usage:

    modal run -m cloud.train_entrypoint --config examples/configs/training/renoir_flowers.yaml

Override the GPU tier from the CLI:

    modal run -m cloud.train_entrypoint --config X.yaml --gpu A100-80GB

CLI flags override the YAML `modal:` block when both are present.

See docs/training.md for the full schema + cold-run protocol.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .train_app import (
    APP_NAME,
    ARTIFACTS_VOLUME_NAME,
    DEFAULT_GPU,
    LORAS_VOLUME_NAME,
    app,
    resolve_train_fn,
)
from .train_manifest import resolve_git_commit


@app.local_entrypoint()
def main(
    config: str,
    gpu: str | None = None,
) -> None:
    """Train one LoRA on Modal from a YAML config.

    Args:
        config: path to a YAML training config under
            `examples/configs/training/`.
        gpu: GPU tier override (L40S, A100-40GB, A100-80GB, H100).
            Overrides YAML `modal.gpu` if both are present.
    """
    cfg_path = Path(config).resolve()
    if not cfg_path.exists():
        raise SystemExit(f"Training config not found: {cfg_path}")

    yaml_text = cfg_path.read_text(encoding="utf-8")
    raw = yaml.safe_load(yaml_text)
    modal_section: dict[str, Any] = dict((raw or {}).get("modal") or {})

    resolved_gpu = gpu or modal_section.get("gpu") or DEFAULT_GPU

    repo_root = Path(__file__).resolve().parent.parent
    git_commit, git_dirty = resolve_git_commit(repo_root)

    print(f"[train] config:    {cfg_path}")
    print(f"[train] gpu:       {resolved_gpu}")
    print(f"[train] git:       {git_commit}{' (dirty)' if git_dirty else ''}")
    print(f"[train] app:       {APP_NAME}")
    print()

    fn = resolve_train_fn(resolved_gpu)
    result = fn.remote(
        yaml_text,
        gpu_tier=resolved_gpu,
        config_name=cfg_path.stem,
        git_commit=git_commit,
        git_dirty=git_dirty,
        notes=[f"launched via cloud/train_entrypoint from {cfg_path.name}"],
    )

    print()
    print("[train] training complete.")
    print(f"[train] run_id:         {result['run_id']}")
    print(f"[train] wall time:      {result['total_seconds']:.1f}s "
          f"(train {result['train_seconds']:.1f}s)")
    print(f"[train] estimated cost: ${result['estimated_cost_usd']:.4f}")
    print(f"[train] checkpoints:    {len(result['lora_checkpoints'])}")
    for c in result["lora_checkpoints"]:
        print(f"  - {c}")
    if result.get("validation_contact_sheet"):
        print(f"[train] validation:     {result['validation_contact_sheet']}")
    print(f"[train] manifest:       {result['manifest_path']}")
    for note in result.get("notes") or []:
        print(f"[train] note: {note}")
    print()
    print("[train] download with:")
    print(f"  modal volume get {LORAS_VOLUME_NAME} runs/{result['run_id']} ./models/loras/runs/")
    print(f"  modal volume get {ARTIFACTS_VOLUME_NAME} runs/{result['run_id']} ./train-artifacts/runs/")
