# External dependencies

Everything the legacy scripts touch outside this repo, where it actually lives on disk, and what the port should do about it.

Verified against the local file system on 2026-05-14. Paths are absolute Windows paths under the developer's Desktop root. For brevity below, **`$DESK`** abbreviates that root.

## Policy

**Target state: zero references to `Choire/`, `Choire-v2/`, `After Cole/`, or any other sibling project directory from anywhere in this repo's runtime code.** Every external asset is either re-vendored into the repo (small, license-permissive code) or resolved from a config-defined absolute path that the user provides (large per-release assets). The port is self-contained.

## Quick map

| What | Where it lives now | Used by | Resolution for the port |
|---|---|---|---|
| **Choire v1 `visuals/`** | `$DESK/Choire/visuals/` | All legacy scripts via `V1_VISUALS = BASE_DIR.parent / "Choire" / "visuals"` | Resolve from config, do not assume sibling-directory layout |
| **Casa del Suono fresco LoRA** | `$DESK/Choire/visuals/lora_weights/SDXL CASA DEL SUONO_epoch_{3,4}.safetensors` (218 MB each) | `generate_videos.py` `LORA_CANDIDATES` | Config-resolved path. **Not re-vendored** (project asset, lives with Choire). |
| **RIFE v4.25 checkpoint + repo** | `$DESK/Choire/visuals/rife_v425/` (and the doubly-nested `train_log/train_log/`) | `generate_videos.py` `load_rife()` | **Re-vendor** the train_log under `assets/` or `models/` in the port. Repo code path goes into `vendor/rife/`. |
| **Real-ESRGAN + basicsr packages** | `$DESK/Choire/visuals/.venv-sd/Lib/site-packages/{realesrgan,basicsr}` | `generate_videos.py` `load_esrgan()` (cross-venv import) | Either install cleanly in the main venv as optional dependencies, **or** drop ESRGAN entirely until Renoir testing decides. |
| **Thomas Cole SDXL LoRA** | `$DESK/After Cole/lora-dataset/checkpoints/Thomas_Cole_epoch_{1,10}.safetensors` (218 MB each) | `generate_horizontal_tcole.py` `TCOLE_LORA_DIR` | Config-resolved path. **Not re-vendored** (large, lives with After Cole). |
| **Earlier `thomas_cole.safetensors` (prototype)** | Not on disk anywhere | `generate_thomas_cole_video.py` (the pre-pipeline prototype) | Ignore. Script is archaeological. |
| **`prompt_engine.py`** | `$DESK/Choire-v2/prompt_engine.py` (NOT in `legacy/`) | `generate_videos.py` (only when invoked directly with `--all` / `--section`) | Drop. 54-excerpt scheduling is Choire-specific and irrelevant to slow-interpolation. |
| **`generate_crown_video.py`** | `$DESK/Choire-v2/generate_crown_video.py` (NOT in `legacy/`) | All three entry-point scripts; supplies `evolved_noise_blend` + re-exports `TRANSITION_STRENGTHS` + `TRANSITION_NOISE_RAMP` from `generate_videos.py` | **RESOLVED.** Function body captured verbatim in [pipeline.md appendix](pipeline.md#appendix-evolved_noise_blend-the-production-noise-path). Port absorbs it as-is; the ramp re-exports collapse with the rest of the engine constants. |
| **`text/curated_excerpts.json`** | `$DESK/Choire-v2/text/curated_excerpts.json` | `generate_videos.py` (engine only) | Drop. |
| **SDXL base + Lightning LoRA + TAESD** | HuggingFace cache (`~/.cache/huggingface/`) | All scripts that load SDXL | Resolved by `diffusers` automatically; pin model IDs in config. |

## Detailed entries

### 1. The Choire v1 `visuals/` root

All paths in `generate_videos.py` hang off:

```python
V1_VISUALS = BASE_DIR.parent / "Choire" / "visuals"
```

`BASE_DIR` is `Path(__file__).parent`. For the cloned scripts under `legacy/choire-v2/scripts/`, this resolves to `legacy/choire-v2/Choire/visuals/`, which **does not exist**. Inside the original Choire v2 repo, the same relative path resolved to `$DESK/Choire/visuals/`, which is the actual Choire v1 installation. The legacy scripts therefore cannot run from `legacy/` as-cloned without either:

- Moving them back into a Choire-v2-style sibling-of-Choire layout, or
- Symlinking `legacy/choire-v2/Choire -> $DESK/Choire`, or
- Editing `V1_VISUALS` (which we cannot, the legacy tree is read-only).

This is one of the strongest arguments for the port. The port reads a `config.yaml` for `assets_root`, `rife_repo`, `lora_paths`, etc., and resolves nothing by relative-path archaeology.

What lives under `$DESK/Choire/visuals/`:

```
Choire/visuals/
  lora_weights/                  fresco LoRA checkpoints (see entry 2)
  rife_v425/                     RIFE v4.25 repo + checkpoint (see entry 3)
  .venv-sd/Lib/site-packages/    cross-venv source for realesrgan + basicsr (see entry 4)
  lora-datasets/                 LoRA training datasets (Choire-side, not used by slow-interpolation)
  benchmark_output/              old SDXL benchmark scratch
  out/                           old preview output
  generate_thomas_cole_video.py  (a copy of the same prototype that is in legacy/after-cole/)
  ... (many other unrelated Choire scripts)
```

The Choire visuals/ tree is also where Luca's Choire v1 lived: it's full of unrelated scripts (`live_visual_server*.py`, `generate_fresco_batch*.py`, etc.). The port only cares about three subdirectories, which are listed individually below.

### 2. Casa del Suono fresco LoRA

```
$DESK/Choire/visuals/lora_weights/
  SDXL CASA DEL SUONO_epoch_3.safetensors   218 MB
  SDXL CASA DEL SUONO_epoch_4.safetensors   218 MB
```

The two epoch checkpoints are the SDXL fresco LoRA trained on the Casa del Suono visuals. `generate_videos.py` `LORA_CANDIDATES` lists epoch 4 first, epoch 3 as fallback. Used at `LORA_SCALE=0.35`.

These are project assets that belong with Choire, not slow-interpolation. The port should:

- Resolve the path from `config.lora.path` (absolute or `~`-relative), not hard-code.
- Skip the LoRA gracefully when the path doesn't exist (already the case via `if lora_path: ...`).
- Allow a list of fallback paths (the candidates pattern is fine; generalize to N).

Do not check these into this repo (218 MB each, plus they belong to Choire's archive).

### 3. RIFE v4.25 repo and checkpoint

The legacy `load_rife()` is one of the more delicate cross-repo dependencies in the codebase.

```
$DESK/Choire/visuals/rife_v425/                 the Practical-RIFE v4.25 repo
  inference_video.py
  model/
  requirements.txt
  train_log/                                    "outer" train_log dir
    __MACOSX/                                   macOS zip artifact, harmless
    train_log/                                  "inner" train_log dir (the actual one!)
      IFNet_HDv3.py
      RIFE_HDv3.py                              the Model class
      flownet.pkl                               24 MB, the actual weights
      refine.py
```

The doubly-nested `train_log/train_log/` is a real quirk of how the v4.25 zip was extracted. `load_rife()` handles it by adding three different paths to `sys.path`:

```python
rife_repo   = str(RIFE_DIR.parent)    # rife_v425/
rife_str    = str(RIFE_DIR)           # rife_v425/train_log/
rife_tl_str = str(RIFE_TRAIN_LOG)     # rife_v425/train_log/train_log/
```

Plus a monkey-patch for old-torchvision compatibility:

```python
import torchvision.transforms.functional as _F
sys.modules['torchvision.transforms.functional_tensor'] = _F
```

Then:

```python
from train_log.RIFE_HDv3 import Model
model = Model()
model.load_model(str(RIFE_TRAIN_LOG), -1)
```

Port resolution: **re-vendor the RIFE train_log inside this repo**, since it is only 24 MB plus the small Python files, MIT-licensed (Practical-RIFE), and the alternative is to keep dragging the Choire visuals tree along forever. Suggested layout:

```
slow-interpolation/
  vendor/
    rife_v425/                  copied from Choire/visuals/rife_v425/, train_log flattened to one level
      model/
      train_log/
        RIFE_HDv3.py
        IFNet_HDv3.py
        flownet.pkl
        refine.py
        LICENSE
  src/slow_interpolation/interpolation/rife.py    wraps the import + monkey-patch
```

Pin v4.25 explicitly (v4.26 has divisibility-by-64 requirements and slightly worse non-video flicker per `frame-interpolation.md` G3). Keep the torchvision monkey-patch behind a try/except so the dependency on the old API can be removed cleanly when torchvision drops `functional_tensor` entirely.

### 4. Real-ESRGAN and basicsr (cross-venv)

`generate_videos.py` `load_esrgan()` does the most fragile import in the legacy codebase. The packages live in **a different virtualenv** than the one running the script:

```
$DESK/Choire/visuals/.venv-sd/Lib/site-packages/
  realesrgan/                   realesrgan 0.3.0
  basicsr/                      basicsr 1.4.2
```

The legacy load sequence:

1. Pre-import `torchvision` in the host venv (otherwise the next step will pull in `.venv-sd`'s incompatible torchvision and break torch op registration).
2. Monkey-patch `sys.modules['torchvision.transforms.functional_tensor']` to the modern `functional` module (basicsr expects the old name).
3. Try to `import realesrgan, basicsr`; on `ImportError`, prepend `$DESK/Choire/visuals/.venv-sd/Lib/site-packages/` to `sys.path` and try again.
4. Build `RRDBNet` + `RealESRGANer` with a HuggingFace-style URL pointing at `RealESRGAN_x2plus.pth`.

This works but only because nothing else in the host venv conflicts with the cross-venv site-packages. It is also tied to **Windows venv layout** (`Lib/site-packages`, not `lib/python3.x/site-packages`).

Phase B is disabled in production. So the port's options are:

- **Recommended: drop ESRGAN until Renoir testing demands it.** No code, no dependency. If Renoir testing later proves x2 upscale helps, install `realesrgan` and `basicsr` cleanly in the main venv as optional `[upscale]` extras.
- Alternative: vendor a small wrapper around `realesrgan` that does the torchvision monkey-patch automatically. Keep `.venv-sd` out of it.
- Worst option: preserve the cross-venv import as-is. Do not.

The `RealESRGAN_x2plus.pth` model file itself is downloaded on first use from GitHub releases; no on-disk dependency required.

### 5. Thomas Cole SDXL LoRA

The After Cole script points at:

```python
TCOLE_LORA_DIR = BASE_DIR / "visuals" / "lora-datasets" / "thomas-cole" / "checkpoints"
```

With `BASE_DIR = Path(__file__).parent`, the expected path is `<after-cole>/visuals/lora-datasets/thomas-cole/checkpoints/`. **This path does not exist** in either the cloned `legacy/after-cole/` or the source After Cole working directory. The checkpoints actually live at:

```
$DESK/After Cole/lora-dataset/checkpoints/
  Thomas_Cole_epoch_1.safetensors    218 MB (light style)
  Thomas_Cole_epoch_10.safetensors   218 MB (strong, default)
```

Note the differences from what the script expects:

- Singular `lora-dataset/`, not `lora-datasets/`.
- No `visuals/` parent directory.
- No `thomas-cole/` intermediate.

The After Cole working tree was reorganized at some point between when `generate_horizontal_tcole.py` was last run and when the clone happened. The script as-checked-in will not find the LoRA without editing. This is a pure path drift, not a missing asset.

Port resolution: same as fresco LoRA. Config-resolved absolute path, fallback list, graceful skip. Pin `lora_scale=0.75` for epoch 10 (default) and ~0.50 for epoch 1 (light).

### 6. The earlier `thomas_cole.safetensors` prototype LoRA

`generate_thomas_cole_video.py` references:

```python
LORA_WEIGHTS_PATH = visuals_dir / "lora_weights" / "thomas_cole.safetensors"
```

Searching `$DESK` shows this file no longer exists anywhere on disk. It was the prototype LoRA from before the After Cole `Thomas_Cole_epoch_{1,10}` tree existed. Since the prototype script is archaeological (SDXL Turbo CFG=0, RIFE HDv3 8x recursive, no SLERP, no anchor return, no smoothing), this missing dependency does not need to be resolved. The script will not run; that is acceptable.

### 7. `prompt_engine.py` (Choire-v2)

Imported by `generate_videos.py` for:

- `prompt_engine.get_metadata()` -> `negative_prompt` string.
- `prompt_engine.get_loop_prompts(excerpt_id)` -> the A/B/C/A prompts for a given Choire excerpt.
- `prompt_engine.get_section_for_passage(passage_index)` -> Italian I/II/.../VII section labels for `--section` filtering.

Lives at `$DESK/Choire-v2/prompt_engine.py`. **Not cloned into `legacy/`**. The three entry-point scripts (`generate_horizontal*.py`, `generate_subject_test.py`) do **not** import it (they define their own `SUBJECTS` dict and `NEG_PROMPT` constant). Only the engine entry point needs it.

Port resolution: **drop**. The 54-excerpt-per-Calvino-section scheduling is a Choire installation concern, not a slow-interpolation one. The port's equivalent is a `Subjects` config object holding A/B/C/A prompts per named subject, plus a per-style `negative_prompt`. No external module needed.

### 8. `generate_crown_video.py` (Choire-v2), RESOLVED

Lived at `$DESK/Choire-v2/generate_crown_video.py`, not cloned into `legacy/`. Imported by all three entry-point scripts. The function the port actually needs (`evolved_noise_blend`) has been captured **verbatim** in [pipeline.md, appendix](pipeline.md#appendix-evolved_noise_blend-the-production-noise-path). The other two imports (`TRANSITION_STRENGTHS`, `TRANSITION_NOISE_RAMP`) are re-exports from `generate_videos.py`, not original definitions, and the horizontal entry points import-but-don't-use them.

Confirmed properties of the captured `evolved_noise_blend`:

- Pixel-space (RGB uint8 -> float32 -> uint8), not latent-space.
- Gaussian noise (`np.random.randn`).
- Persistent state in a module-global `_persistent_noise` tensor, reset when input shape changes.
- Defaults `blend_pct=0.08, walk_rate=0.05` (standard mode); calm passes 0.04 / 0.02.

The port reimplements this as a small class with per-instance state (no module global), drops the `generate_crown_video` import, and removes the indirection to the engine's transition ramps (since the horizontal scripts ignore them anyway).

### 9. `text/curated_excerpts.json` (Choire-v2)

Lives at `$DESK/Choire-v2/text/curated_excerpts.json`. Loaded by `generate_videos.py` to populate the `--all` / `--section` / `--excerpt` selection. Not needed by the entry-point scripts.

Port resolution: drop, alongside `prompt_engine`. The slow-interpolation CLI uses `--subject <key>` against a `Subjects` config, no separate excerpt registry.

### 10. HuggingFace-resolved models

These are downloaded automatically by `diffusers` on first use into `~/.cache/huggingface/`. No on-disk asset dependency from this repo.

| Model | Loader call |
|---|---|
| `stabilityai/stable-diffusion-xl-base-1.0` (fp16 variant) | `StableDiffusionXLImg2ImgPipeline.from_pretrained(...)` |
| `ByteDance/SDXL-Lightning` -> `sdxl_lightning_4step_lora.safetensors` | `pipe.load_lora_weights(...)` |
| `madebyollin/taesdxl` | `AutoencoderTiny.from_pretrained(...)` |
| `RealESRGAN_x2plus.pth` | URL passed to `RealESRGANer(...)`, downloaded by it from GitHub releases |

Port resolution: pin model IDs in `config.models` so they are not scattered across the codebase. Test that everything still resolves on a fresh HuggingFace cache.

## Python packages used by the legacy scripts

Imported across the four `generate_*.py` files:

- `torch`, `torchvision`
- `diffusers` (`StableDiffusionXLImg2ImgPipeline`, `AutoencoderTiny`, `EulerDiscreteScheduler`, `AutoPipelineForImage2Image` in the prototype)
- `numpy`
- `PIL` (`Image`, `ImageFilter`)
- `imageio` (`get_writer` + the `libx264` plugin via PyAV in the prototype's fallback)
- `opensimplex` (only by `coherent_noise_image`, dead code)
- Standard library: `argparse`, `gc`, `json`, `math`, `time`, `traceback`, `pathlib`, `os`, `sys`

ESRGAN (Phase B, currently disabled): `realesrgan`, `basicsr`.

RIFE (Phase C): no extra pip install; the v4.25 train_log uses only `torch` + `numpy`.

`pyproject.toml` should split these across extras:

- `[default]`: torch, diffusers, numpy, PIL (Pillow), imageio + imageio-ffmpeg.
- `[upscale]` (optional): realesrgan, basicsr.
- `[train]` (Phase 2 of roadmap): whatever LoRA-training stack the Renoir LoRA needs.
- `[live]` (Phase 4+): mediapipe, opencv, etc.

Drop `opensimplex` unless the coherent noise path is intentionally revived.

## Summary action plan (target: no sibling-folder dependencies)

Three buckets:

1. **Re-vendor into the repo.**
   - RIFE v4.25 train_log (24 MB, MIT). Copy `Choire/visuals/rife_v425/train_log/train_log/{RIFE_HDv3.py, IFNet_HDv3.py, flownet.pkl, refine.py}` plus `model/` and `LICENSE` into `vendor/rife_v425/` flat-layout (no doubly-nested `train_log/train_log/`). The Python wrapper in `src/slow_interpolation/interpolation/rife.py` handles the import + torchvision compat shim.
   - `evolved_noise_blend`: captured verbatim in [pipeline.md appendix](pipeline.md#appendix-evolved_noise_blend-the-production-noise-path). Port will paste it into `src/slow_interpolation/noise/evolved_walk.py` and refactor the module-global to per-instance state.

2. **Config-resolved, owned by the user, no default in sibling project.**
   - LoRA checkpoints (218 MB each). User provides absolute paths in `config.yaml`. No fallback to `Choire/visuals/lora_weights/` or `After Cole/lora-dataset/`. A recommended layout would be `<this-repo>/models/loras/` (gitignored), but anything accessible to the user is fine.
   - HuggingFace-resolved models (SDXL base, Lightning LoRA, TAESD): model IDs pinned in `config.yaml`, downloaded into the user's HF cache by `diffusers`. No on-disk dependency from this repo.

3. **Drop entirely.**
   - `prompt_engine.py` and `text/curated_excerpts.json` (Choire-specific scheduling).
   - The cross-venv ESRGAN import path. Phase B is disabled; if Renoir testing later asks for ESRGAN, install cleanly in the main venv as a `[upscale]` extra.
   - The dead `thomas_cole.safetensors` reference in the prototype script.
   - The `V1_VISUALS` relative-path arithmetic; replaced by explicit config keys.

After this, `grep -rE "Choire|After Cole" src/ vendor/` returns nothing. That is the acceptance test for the policy.
