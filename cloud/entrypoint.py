"""CLI entrypoint for `modal run -m cloud.entrypoint`.

Reads a local YAML config, splits off the optional `modal:` top-level
section, calls the remote `render` function with the raw YAML text plus
the modal-specific settings.

Usage (module mode required because cloud/ uses relative imports):

    modal run -m cloud.entrypoint --config examples/configs/tcole_valley.yaml

Override the entry point or config loader without editing this file:

    modal run -m cloud.entrypoint --config my.yaml \\
        --pipeline-entry mypkg.pipeline:CompositingPipeline

Or set the same overrides in the YAML:

    modal:
      gpu: A100-40GB
      pipeline_entry: mypkg.pipeline:CompositingPipeline
      config_loader: mypkg.config:load_my_config

The CLI flags override the YAML values when both are present.

See `docs/modal.md` for the full schema and the variant-shipping recipe.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import modal
import yaml

from .app import (
    DEFAULT_CONFIG_LOADER,
    DEFAULT_GPU,
    DEFAULT_PIPELINE_ENTRY,
    OUTPUTS_VOLUME_NAME,
    app,
    resolve_render_fn,
)
from .manifest import resolve_git_commit


# Known Modal-specific keys. Anything else under `modal:` is preserved
# and forwarded as notes; this keeps the schema forgiving for future
# fields without needing to bump validation here.
KNOWN_MODAL_KEYS = {"gpu", "pipeline_entry", "config_loader", "notes"}


@app.local_entrypoint()
def main(
    config: str,
    gpu: str | None = None,
    pipeline_entry: str | None = None,
    config_loader: str | None = None,
) -> None:
    """Render a slow-interpolation config on Modal.

    Args:
        config: path to a YAML pipeline config.
        gpu: GPU tier override (e.g. L40S, A100-40GB, H100). Overrides
            the YAML `modal.gpu` field if both are present.
        pipeline_entry: dotted-path override for the Pipeline class
            (e.g. `mypkg.pipeline:CompositingPipeline`).
        config_loader: dotted-path override for the config loader
            function (e.g. `mypkg.config:load_my_config`).
    """
    cfg_path = Path(config).resolve()
    if not cfg_path.exists():
        raise SystemExit(f"Config file not found: {cfg_path}")

    yaml_text = cfg_path.read_text(encoding="utf-8")
    raw = yaml.safe_load(yaml_text)
    modal_section: dict[str, Any] = dict(raw.get("modal") or {})

    # Resolve precedence: CLI > YAML > built-in default.
    resolved_gpu = gpu or modal_section.get("gpu") or DEFAULT_GPU
    resolved_entry = (
        pipeline_entry or modal_section.get("pipeline_entry") or DEFAULT_PIPELINE_ENTRY
    )
    resolved_loader = (
        config_loader or modal_section.get("config_loader") or DEFAULT_CONFIG_LOADER
    )

    preserve_staging = bool(modal_section.get("preserve_staging", False))
    skip_keyframes = bool(modal_section.get("skip_keyframes", False))

    # Forward any non-standard `modal:` fields as manifest notes.
    extra_notes: list[str] = []
    for k, v in modal_section.items():
        if k not in KNOWN_MODAL_KEYS:
            extra_notes.append(f"modal.{k}={v!r} (forwarded from YAML)")
    extra_notes.extend(modal_section.get("notes") or [])

    # Capture local git state so the manifest is honest about what
    # source the deploy was built from.
    repo_root = Path(__file__).resolve().parent.parent
    git_commit, git_dirty = resolve_git_commit(repo_root)

    print(f"[modal] config:         {cfg_path}")
    print(f"[modal] gpu:            {resolved_gpu}")
    print(f"[modal] pipeline_entry: {resolved_entry}")
    print(f"[modal] config_loader:  {resolved_loader}")
    print(f"[modal] git commit:     {git_commit}{' (dirty)' if git_dirty else ''}")

    # Dispatch to the function bound to this GPU tier. Modal 1.4.x
    # requires per-tier static binding; see cloud/app.py.
    fn = resolve_render_fn(resolved_gpu)

    result = fn.remote(
        yaml_text,
        gpu_tier=resolved_gpu,
        pipeline_entry=resolved_entry,
        config_loader=resolved_loader,
        git_commit=git_commit,
        git_dirty=git_dirty,
        notes=extra_notes,
        preserve_staging=preserve_staging,
        skip_keyframes=skip_keyframes,
    )

    print()
    print("[modal] render complete.")
    print(f"[modal] total wall time:    {result['total_seconds']:.1f}s")
    print(f"[modal] estimated cost:     {result['estimated_cost_usd']:.2f} USD")
    print(f"[modal] output (in volume): {result['output_path']}")
    print(f"[modal] manifest:           {result['manifest_path']}")
    for note in result.get("notes") or []:
        print(f"[modal] note: {note}")
    print()
    print("[modal] download with:")
    print(
        f"        modal volume get {OUTPUTS_VOLUME_NAME} "
        f"{result['output_path']} ./outputs/"
    )
    print(
        f"        modal volume get {OUTPUTS_VOLUME_NAME} "
        f"{result['manifest_path']} ./outputs/"
    )
