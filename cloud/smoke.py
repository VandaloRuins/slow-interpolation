"""Smoke test for the Modal cloud-render path.

Renders the smallest possible config (`examples/configs/smoke.yaml`,
~10 s wall, ~0.005 USD on L40S) and asserts the output MP4 exists with
non-zero duration. Use this as a pre-flight check before:

- The first run after pulling a branch.
- A batch dispatch.
- Release-day session start.

Run:

    modal run -m cloud.smoke

Exit code 0 on green, non-zero on red. Failure output points at the
likely cause (image build, LoRA path, volume mount, RIFE checkpoint).
"""

from __future__ import annotations

import sys
from pathlib import Path

import modal

from .app import (
    DEFAULT_CONFIG_LOADER,
    DEFAULT_GPU,
    DEFAULT_PIPELINE_ENTRY,
    OUTPUTS_VOLUME_NAME,
    app,
    outputs_volume,
    render,  # smoke always uses the default L40S binding
)


SMOKE_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "examples" / "configs" / "smoke.yaml"
)


@app.local_entrypoint()
def main() -> None:
    """Run the smoke render. Print PASS/FAIL with a one-line reason."""
    if not SMOKE_CONFIG_PATH.exists():
        _fail(f"Smoke config not found: {SMOKE_CONFIG_PATH}")
        return

    yaml_text = SMOKE_CONFIG_PATH.read_text(encoding="utf-8")

    print(f"[smoke] config:   {SMOKE_CONFIG_PATH}")
    print(f"[smoke] gpu:      {DEFAULT_GPU}")
    print(f"[smoke] entry:    {DEFAULT_PIPELINE_ENTRY}")
    print()

    try:
        result = render.remote(
            yaml_text,
            gpu_tier=DEFAULT_GPU,
            pipeline_entry=DEFAULT_PIPELINE_ENTRY,
            config_loader=DEFAULT_CONFIG_LOADER,
            git_commit="smoke",
            git_dirty=False,
            notes=["SMOKE TEST RENDER"],
        )
    except Exception as exc:
        _fail(f"render.remote() raised: {exc!r}")
        return

    # Verify the MP4 made it into the outputs volume with non-zero size.
    output_path_rel = result.get("output_path")
    if not output_path_rel:
        _fail("render() returned no output_path")
        return

    try:
        size_bytes = _volume_file_size("smoke.mp4")
    except Exception as exc:
        _fail(f"could not stat smoke.mp4 in outputs volume: {exc!r}")
        return

    if size_bytes is None or size_bytes <= 0:
        _fail(f"smoke.mp4 missing or empty (size={size_bytes})")
        return

    print()
    print("=" * 50)
    print(f"SMOKE PASS")
    print(f"  wall:     {result['total_seconds']:.1f}s")
    print(f"  cost:     {result['estimated_cost_usd']:.4f} USD")
    print(f"  output:   {output_path_rel}  ({size_bytes / 1024:.1f} KB)")
    print(f"  manifest: {result['manifest_path']}")
    print("=" * 50)


def _volume_file_size(remote_path: str) -> int | None:
    """Return byte size of a file on the outputs volume, or None if absent."""
    for entry in outputs_volume.iterdir("/"):
        if entry.path.lstrip("/") == remote_path:
            return entry.size
    return None


def _fail(reason: str) -> None:
    print()
    print("=" * 50)
    print(f"SMOKE FAIL")
    print(f"  reason: {reason}")
    print()
    print("Common causes:")
    print(
        f"  - LoRA missing on volume {OUTPUTS_VOLUME_NAME}'s sibling "
        f"slow-interp-loras. Re-run:"
    )
    print(f"      modal run -m cloud.upload_weights --src models/loras")
    print(f"  - Image build broken. Try a fresh deploy:")
    print(f"      modal deploy cloud/app.py")
    print(f"  - HF cache volume corrupted. Inspect:")
    print(f"      modal volume ls slow-interp-hf-cache")
    print("=" * 50)
    sys.exit(1)
