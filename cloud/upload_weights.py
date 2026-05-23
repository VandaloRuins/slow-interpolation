"""One-time uploader for the LoRA weights Modal Volume.

Run after `pip install -e .[cloud]` and `modal token new`:

    modal run -m cloud.upload_weights --src models/loras

Module mode (`-m`) is required because cloud/ uses relative imports.

Mirrors every `.safetensors` (and `.bin`, `.ckpt`, `.pt`, for future
checkpoint formats) under the source directory into the
`slow-interp-loras` Modal Volume, preserving filenames. Subdirectories
are preserved.

The YAML configs reference LoRAs by repo-relative path
(`models/loras/Thomas_Cole_epoch_10.safetensors`) and the Modal app
mounts the volume at exactly that path on the container, so once a
checkpoint is uploaded the existing YAML configs work without edits.

Re-run anytime to refresh / add weights. Existing files in the volume
are overwritten by name. The uploader does NOT delete files that no
longer exist locally; clear the volume manually with
`modal volume rm slow-interp-loras <path>` if you need to.
"""

from __future__ import annotations

from pathlib import Path

import modal

from .app import LORAS_VOLUME_NAME


WEIGHT_SUFFIXES = {".safetensors", ".bin", ".ckpt", ".pt"}


app = modal.App("slow-interpolation-upload-weights")
volume = modal.Volume.from_name(LORAS_VOLUME_NAME, create_if_missing=True)


@app.local_entrypoint()
def main(src: str = "models/loras") -> None:
    """Upload every LoRA checkpoint under `src/` to the loras volume.

    Args:
        src: local directory containing the .safetensors files.
            Defaults to `models/loras` (the repo's gitignored LoRA dir).
    """
    src_dir = Path(src).resolve()
    if not src_dir.is_dir():
        raise SystemExit(f"Source directory not found: {src_dir}")

    files: list[Path] = sorted(
        p for p in src_dir.rglob("*") if p.is_file() and p.suffix.lower() in WEIGHT_SUFFIXES
    )
    if not files:
        raise SystemExit(
            f"No weight files found under {src_dir} "
            f"(looked for {sorted(WEIGHT_SUFFIXES)})."
        )

    print(f"[upload] source:  {src_dir}")
    print(f"[upload] volume:  {LORAS_VOLUME_NAME}")
    print(f"[upload] files:   {len(files)}")
    for f in files:
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"  - {f.relative_to(src_dir)}  ({size_mb:.1f} MB)")

    with volume.batch_upload(force=True) as batch:
        for local in files:
            remote = local.relative_to(src_dir).as_posix()
            batch.put_file(local, remote)

    print()
    print(f"[upload] done. Files are now available at:")
    print(f"         /root/slow-interpolation/models/loras/<filename>")
    print(f"         on every render container.")
