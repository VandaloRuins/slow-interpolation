# sd-scripts on Modal, integration quirks

Date: 2026-05-18.
sd-scripts version: pinned commit `502cc3fab2aa` (the resolved-from-`main` SHA at the Renoir G3 cold-run).
Modal SDK version: 1.4.2.
Scope: gotchas discovered while wrapping `kohya-ss/sd-scripts` as a Modal subprocess inside [`cloud/train_app.py`](../../cloud/train_app.py). Captured separately from [`modal-sdk-quirks.md`](modal-sdk-quirks.md) because these are sd-scripts behaviours, not Modal SDK behaviours; the failure mode is sd-scripts errors / silent misbehaviour, not Modal errors.

Companion docs:
- [`modal-sdk-quirks.md`](modal-sdk-quirks.md): general Modal SDK quirks, including #10 Windows pathlib backslash leak (which is Modal-host, not sd-scripts).
- [`../manual/train-lora-on-modal.md`](../manual/train-lora-on-modal.md): the operational protocol that uses these fixes.
- The Modal-trainer workstream produced this doc; its log lives in the maintainer's private planning folder during v0.1 and surfaces in v0.2.

## Quirks

### 1. `requirements.txt` ends with `.` (self-install), `pip install -r` errors out

**Symptom**: `pip install -r /opt/sd-scripts/requirements.txt` fails with:

```
Obtaining file:/// (from -r /opt/sd-scripts/requirements.txt (line 49))
ERROR: file:/// (from -r /opt/sd-scripts/requirements.txt (line 49)) does not appear to be a Python project: neither 'setup.py' nor 'pyproject.toml' found.
```

**Cause**: line 49 of `sd-scripts/requirements.txt` is a bare `.` (intended as editable self-install). sd-scripts itself ships no `setup.py` / `pyproject.toml`, so pip cannot install it that way. The trailing `.` only works if the consumer first `pip install -e .` from the sd-scripts repo root (which has the project metadata), not the file-list install path.

**Failure mode if masked**: appending `|| true` to swallow the error leaves cv2, voluptuous, omegaconf, albumentations, imagesize, schedulefree, pytorch-lightning, tensorboard, opencv-python-headless uninstalled. sd-scripts then crashes at import with `ModuleNotFoundError: No module named 'cv2'`.

**Stripping the line via grep does not reliably work** either: line endings (CRLF vs LF) and trailing whitespace defeated pattern matches like `grep -v '^\.$'` during the G1 cold-run. Process substitution `<(...)` is not available in Modal's image build (uses `sh`, not `bash`).

**Fix**: do not install sd-scripts requirements.txt. Enumerate the sd-scripts runtime deps in the `.pip_install(...)` call. sd-scripts itself loads via `PYTHONPATH` (added to the `.env` block), no editable install needed. Concretely:

```python
image = (
    modal.Image.debian_slim(...)
    .pip_install(
        # ... base deps ...
        "opencv-python-headless",   # cv2 import at sd-scripts startup
        "albumentations",
        "voluptuous",
        "omegaconf",
        "imagesize",
        "pytorch-lightning",
        "tensorboard",
        "schedulefree",
        # ...
    )
    .run_commands(
        f"git clone {SD_SCRIPTS_REPO} {SD_SCRIPTS_DIR.as_posix()}",
        f"cd {SD_SCRIPTS_DIR.as_posix()} && git checkout {SD_SCRIPTS_COMMIT}",
        # no `pip install -r requirements.txt`
    )
    .env({"PYTHONPATH": "...:/opt/sd-scripts"})
)
```

**Discovery cost**: 2 image-build iterations on G1 before the fix landed.

**Captured in**: [`../../cloud/train_app.py`](../../cloud/train_app.py) image-build block + inline comment.

### 2. dataset.toml `subsets[].image_dir` must be the LEAF folder, not the `<N>_<concept>` parent

**Symptom**: sd-scripts logs

```
WARNING  ignore subset with image_dir='/tmp/train/<run-id>/dataset':
         no images found / 画像が見つからないため...
ERROR    No data found. Please verify arguments (train_data_dir must
         be the parent of folders with images)
```

**Cause**: sd-scripts has TWO config surfaces:
- CLI flag `--train_data_dir` (positional, parent of `<N>_<concept>/` folders, walks subfolders).
- TOML subsets API: `[[datasets.subsets]]` with `image_dir = "<path>"` (direct path to a folder of loose `<name>.jpg` + `<name>.txt` pairs, does NOT walk subfolders).

The wording "train_data_dir must be the parent" in the error message refers to the CLI flag. When using the TOML subsets API, `image_dir` must point at the leaf folder containing the images directly.

**Failure mode if confused**: dataset unpacks to `/tmp/.../dataset/6_rfl/*.jpg`, TOML points `image_dir` at `/tmp/.../dataset/`, sd-scripts sees zero images and aborts before training starts.

**Fix**: pass the subset directory (the `<repeats>_<trigger>/` folder) to `_write_dataset_toml`, not its parent.

```python
subset_dir = dataset_dir / f"{repeats}_{trigger}"
# unpack ZIP into subset_dir directly (not into dataset_dir then organise)
_unpack_zip_to_subset(zip_path, subset_dir, caption_ext, trigger)
_write_dataset_toml(dataset_toml, subset_dir, training)
# inside _write_dataset_toml:
#   subsets: [{ "image_dir": str(subset_dir), "num_repeats": repeats }]
```

**Discovery cost**: 1 failed run on G1 (free, error message was specific enough to fix in one iteration).

**Captured in**: [`../../cloud/train_app.py`](../../cloud/train_app.py) `_train_impl` + `_write_dataset_toml` signature.

### 3. Final-epoch checkpoint saved un-suffixed; epoch parser must handle it

**Symptom**: validation hook saw only N-1 of N saved checkpoints. With `epochs=2, save_every_n_epochs=1`, the trainer logged "saved 2 checkpoint(s)" but the validation contact sheet only rendered epoch 1.

**Cause**: sd-scripts saves intermediate epochs as `<output_name>-NNNNNN.safetensors` (6-digit zero-padded epoch suffix). The FINAL epoch is saved un-suffixed as `<output_name>.safetensors`. With `output_name = run_id` (e.g. `_smoke_20260518T081833Z_ea078655`) and run_ids containing only underscores, the un-suffixed final has no `-N` in its stem; the epoch parser returned `None` and the validator skipped it.

**Failure mode if confused**: validation contact sheet is missing the most important cell (epoch 10 in the Renoir cold-run). The checkpoints themselves are saved correctly; only the validation indexing breaks.

**Fix**: in the validation routine, detect `ckpt.stem == output_name_base` and assign it `total_epochs` (passed in from the training config).

```python
for ckpt in checkpoints:
    if ckpt.stem == output_name_base:
        epoch = total_epochs
    else:
        epoch = _parse_checkpoint_epoch(ckpt.stem)
    ...
```

**Discovery cost**: 1 failed validation pass on G2 (the run still succeeded; the missing cell was the tell). Tiny cost.

**Captured in**: [`../../cloud/train_app.py`](../../cloud/train_app.py) `_run_validation` + `_train_impl` call site.

## What is NOT in this doc

- General Modal SDK quirks (Windows path leak, `add_local_*` ordering, `Function.with_options` absence, `keep_warm` renames, `Volume.iterdir(recursive=)` ignored, hf-hub `CachedRevisionInfo` rename, cp1252, `batch_upload` mode, `.map()` kwargs). Those live in [`modal-sdk-quirks.md`](modal-sdk-quirks.md).
- Hyperparameter rationale or LoRA training theory. Those live in [`lora-training.md`](lora-training.md) and [`lora-training-deep-dive.md`](lora-training-deep-dive.md).
- The operational protocol for training a new LoRA. That lives in [`../manual/train-lora-on-modal.md`](../manual/train-lora-on-modal.md).
