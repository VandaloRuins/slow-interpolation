# Phase 2 acceptance commands

Commands to run on the studio GPU machine to validate each milestone of the port. Each milestone produces a runnable artifact that can be visually checked against the legacy sample MP4s under [../examples/outputs/](../examples/outputs/).

## 2A (foundation, no GPU)

Already passing on dev machines without a GPU.

```bash
python -m pytest tests/
python -c "from slow_interpolation import load_pipeline_config, Pipeline; \
    cfg = load_pipeline_config('examples/configs/tcole_valley.yaml'); \
    p = Pipeline(cfg); \
    print(f'expected keyframes: {p.expected_keyframe_count()}')"
# expected output: expected keyframes: 26
```

## 2B (Phase A keyframe generation, GPU required)

This is the first GPU-bound milestone. Targets an NVIDIA card with >=8 GB VRAM (RTX 4060 Laptop class or better). First run downloads SDXL base (~7 GB) plus the Lightning LoRA and TAESD VAE into `~/.cache/huggingface/`.

```bash
# One-time install. CUDA torch MUST be installed before the package itself,
# otherwise PyPI's CPU-only torchvision wheel will downgrade torch silently.
# See docs/dev-setup.md for the full bootstrap.
python -m pip install --index-url https://download.pytorch.org/whl/cu121 torch==2.5.1 torchvision==0.20.1
python -m pip install -e .

# Generate the 26-keyframe sequence into outputs/staging/tcole_valley/keyframes/
python -c "from slow_interpolation import load_pipeline_config, Pipeline; \
    cfg = load_pipeline_config('examples/configs/tcole_valley.yaml'); \
    p = Pipeline(cfg); \
    p.generate_keyframes(); \
    p.smooth_keyframes()"
```

### Expected outcome

- A directory `outputs/staging/tcole_valley/keyframes/` containing exactly 26 PNGs named `0000.png` through `0025.png`.
- Each PNG is **1344 x 768** RGB (resolution before RIFE edge crop; cropping happens in Phase C).
- No frame/arch border artifacts at the image edges (latent-edge callback + `crops_coords_top_left` working).
- Frames `0000.png` through `0004.png` show the **A** prompt (panoramic green valley, amber light, distant aqueduct).
- Frames `0005.png` through `0007.png` are the **A -> B** SLERP transition.
- Frames `0008.png` through `0012.png` show the **B** prompt (golden hour valley).
- Frames `0013.png` through `0015.png` are the **B -> C** SLERP transition.
- Frames `0016.png` through `0020.png` show the **C** prompt (misty morning, luminism).
- Frames `0021.png` through `0024.png` are the **C -> A return** segment (strength ramps 0.50 -> 0.60, pixel-blend toward anchor quadratically up to 20%).
- Frame `0025.png` is the **anchor** frame (a copy of the first coherent post-warmup frame, used for Phase C wrap-around loop closure).

### Acceptance check

Visual: open the 26 PNGs side-by-side in an image viewer. Composition should hold across all forward segments (the aqueduct should be present at appropriate scale, not zooming in/out, not being replaced by other subjects), and the return segment should land back at the A composition.

Quantitative: shape and count check.

```bash
python -c "
from pathlib import Path
from PIL import Image
files = sorted(Path('outputs/staging/tcole_valley/keyframes').glob('*.png'))
print(f'count: {len(files)}')
assert len(files) == 26, f'expected 26 keyframes, got {len(files)}'
img = Image.open(files[0])
print(f'size: {img.size}')
assert img.size == (1344, 768), f'expected (1344, 768), got {img.size}'
print('OK')
"
```

### Troubleshooting

- **CUDA OOM during `load_sdxl_pipeline`**: drop the style LoRA (delete the `style.lora_path` line in the YAML or set it to a path that does not exist; the loader skips silently when the file is missing). Then add it back once SDXL base is fitting comfortably.
- **`from train_log.RIFE_HDv3 import Model` errors**: not in scope yet, that's 2C.
- **LoRA path resolves but Diffusers raises `KeyError`**: the LoRA was trained for SD1.5, not SDXL. Check `LORA-USAGE.md` under [../legacy/after-cole/](../legacy/after-cole/).

### Known cosmetic differences from the legacy `tcole_valley_horizontal_v2.mp4`

- The legacy script ran `np.random.randn` without seed control; this re-run will produce different specific frames (different cloud shapes, different aqueduct brick patterns), but the same composition family and palette. See [roadmap.md](roadmap.md) Phase 2 exit criteria.
- This milestone produces PNGs only, not an MP4. The MP4 lands in 2C after RIFE interpolation + H.264 encoding.

## 2C (full render pipeline, planned)

Adds RIFE interpolation, H.264 encoding, the CLI entry point. The acceptance command will be a single `python -m slow_interpolation.run examples/configs/tcole_valley.yaml` that produces `outputs/tcole_valley.mp4` visually equivalent to `legacy/after-cole/`'s `tcole_valley_horizontal.mp4`.
