# cloud/

Optional [Modal.com](https://modal.com) deployment of the
slow-interpolation pipeline. The local CLI
(`python -m slow_interpolation.run`) is the primary entry point; this
subpackage is a parallel cloud path for when you want a bigger GPU or
batch parallelism.

**Status: verified 2026-05-17.** Cold-run against `tcole_valley.yaml`
on L40S completed in 121 s at 0.07 USD; output envelope and visual
inspection both match the local Phase 2C reference. See
[`../docs/planning/workstreams/modal/progress.md`](../docs/planning/workstreams/modal/progress.md).

## Quickstart

```bash
pip install -e .[cloud]
modal token new

# One-time: upload LoRA checkpoints to the Modal volume.
modal run -m cloud.upload_weights --src models/loras

# Render.
modal run -m cloud.entrypoint --config examples/configs/tcole_valley.yaml

# Download the rendered MP4 + manifest.
modal volume get slow-interp-outputs tcole_valley.mp4 ./outputs/
modal volume get slow-interp-outputs tcole_valley.manifest.json ./outputs/
```

## Full docs

See [`../docs/modal.md`](../docs/modal.md) for setup, the `modal:` YAML
schema, the `pipeline_entry` / `config_loader` override pattern, cost
expectations per GPU tier, troubleshooting, and the variant-shipping
recipe.

## Layout

- `app.py` -- Modal App + Image + Volumes + the remote `render` function.
- `entrypoint.py` -- `modal run` entrypoint. Reads a local YAML, calls
  the remote function.
- `upload_weights.py` -- one-time uploader for the LoRA volume.
- `manifest.py` -- run-manifest schema (JSON written next to every MP4).

## Why `cloud/` and not `modal/`

A local `modal/__init__.py` would shadow the `modal` Python SDK on
sys.path. The cloud framing also matches the opt-in design: this is the
cloud path, vs. the local path under `src/`.
