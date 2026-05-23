"""DEPRECATED shim. Use `cloud/validate_lora.py` with
`examples/configs/validation/renoir.yaml` instead.

Kept as a shim so historical commands like

    modal run -m cloud.validation_renoir --epoch 10

still work. New families should NOT add Family-named modules; they
add a YAML config under `examples/configs/validation/<family>.yaml`
and dispatch via:

    modal run -m cloud.validate_lora --config examples/configs/validation/<family>.yaml --epoch 10

See [docs/manual/train-lora-on-modal.md](../docs/manual/train-lora-on-modal.md)
Step 5c for the canonical protocol.

This shim was introduced 2026-05-18 alongside the Renoir cold-run
validation (run-id `renoir_flowers_20260518T082516Z_45374f1b`) when
the Soutine LoRA was queued as the second worked example.
"""

from __future__ import annotations

from pathlib import Path

import modal

from .validate_lora import (
    OUTPUTS_VOLUME_NAME,
    app,
    render_validation,
)


_RENOIR_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent
    / "examples" / "configs" / "validation" / "renoir.yaml"
)


@app.local_entrypoint()
def main(epoch: int) -> None:
    """Render the Renoir LoRA's validation grid at the given epoch.

    Args:
        epoch: 1, 5, or 10 (the conventional Renoir keepers).
    """
    if epoch not in (1, 5, 10):
        raise SystemExit(f"epoch must be 1, 5, or 10 (got {epoch})")
    if not _RENOIR_CONFIG_PATH.exists():
        raise SystemExit(
            f"Renoir validation config not found at {_RENOIR_CONFIG_PATH}. "
            "Dispatch via the generalized CLI instead: "
            "modal run -m cloud.validate_lora --config "
            "examples/configs/validation/renoir.yaml --epoch <N>"
        )
    yaml_text = _RENOIR_CONFIG_PATH.read_text(encoding="utf-8")
    print(
        "[shim] cloud.validation_renoir is deprecated; "
        "use cloud.validate_lora --config examples/configs/validation/renoir.yaml"
    )
    manifest = render_validation.remote(yaml_text, epoch=epoch)
    print()
    print(f"Renoir validation epoch {epoch} complete:")
    print(f"  total: {manifest['total_seconds']:.1f}s")
    print(f"  outputs on volume: {OUTPUTS_VOLUME_NAME}:/{manifest['output_dir_on_volume']}")
