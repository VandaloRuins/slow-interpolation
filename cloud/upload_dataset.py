"""One-time dataset uploader for the slow-interp-datasets volume.

Run after `pip install -e .[cloud]` and `modal token new`:

    modal run -m cloud.upload_dataset --src datasets/renoir-flowers/renoir-flowers-civitai.zip

Idempotent. Uploads the ZIP to the volume keyed by filename; re-runs
overwrite with the latest local copy. Sibling of cloud/upload_weights.py.

The training YAML's `dataset.zip` field references the uploaded ZIP by
basename:

    dataset:
      zip: renoir-flowers-civitai.zip

so once the ZIP is on the volume the trainer finds it.

Module-mode (`-m`) invocation is required because `cloud/` uses
relative imports.
"""

from __future__ import annotations

from pathlib import Path

import modal

from .train_app import DATASETS_VOLUME_NAME


app = modal.App("slow-interpolation-upload-dataset")
volume = modal.Volume.from_name(DATASETS_VOLUME_NAME, create_if_missing=True)


@app.local_entrypoint()
def main(src: str) -> None:
    """Upload one dataset ZIP to the slow-interp-datasets volume.

    Args:
        src: path to a local .zip file (the CivitAI-shape ZIP produced
            by `datasets/<name>/package_for_civitai.py`).
    """
    src_path = Path(src).resolve()
    if not src_path.exists():
        raise SystemExit(f"Source ZIP not found: {src_path}")
    if src_path.suffix.lower() != ".zip":
        raise SystemExit(f"Expected a .zip file; got: {src_path.name}")

    size_mb = src_path.stat().st_size / (1024 * 1024)
    print(f"[upload] source:  {src_path}")
    print(f"[upload] size:    {size_mb:.1f} MB")
    print(f"[upload] volume:  {DATASETS_VOLUME_NAME}")
    print(f"[upload] remote:  /{src_path.name}")
    print()

    with volume.batch_upload(force=True) as batch:
        batch.put_file(src_path, src_path.name)

    print(f"[upload] done. Reference in training YAML as:")
    print(f"           dataset:")
    print(f"             zip: {src_path.name}")
