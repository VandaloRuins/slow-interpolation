# Dev setup

Bootstrap notes for running the pipeline on a fresh machine.

## Target environment

- Windows 11 with Git Bash (or WSL), or Linux.
- NVIDIA GPU, >=8 GB VRAM. RTX 4060 Laptop class confirmed working.
- Python 3.10 or 3.11.
- CUDA 12.1 driver (the precompiled torch wheels target cu121).

## Initial bootstrap

**Important: install torch + torchvision from PyTorch's CUDA wheel index BEFORE `pip install -e .`**. PyPI's default torchvision wheel pulls in a CPU-only torch as a transitive dependency and silently downgrades any existing CUDA build. The CUDA wheels live on a separate index.

```powershell
cd c:\Users\lucaa\OneDrive\Desktop\slow-interpolation
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip

# 1) CUDA torch + matching torchvision FIRST, from the PyTorch cu121 index.
pip install --index-url https://download.pytorch.org/whl/cu121 torch==2.5.1 torchvision==0.20.1

# 2) The rest of the package deps (will not re-touch torch / torchvision).
pip install -e .[dev]
```

Bash equivalent:

```bash
python -m venv .venv && source .venv/Scripts/activate
pip install --upgrade pip
pip install --index-url https://download.pytorch.org/whl/cu121 torch==2.5.1 torchvision==0.20.1
pip install -e .[dev]
```

Verify CUDA after install:

```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
# expected: 2.5.1+cu121 True
```

If `cuda.is_available()` is `False`, something downgraded torch to a CPU build. Reinstall step 1 with `--force-reinstall`.

## Extras

- `pip install -e .[train]` (Phase 3): adds `datasets` + `bitsandbytes` for LoRA training. Not needed for rendering.
- `pip install -e .[live]` (Phase 4+): adds `mediapipe` + `opencv-python` for live webcam-driven work.

## External assets

- **LoRA checkpoints** for rendering go under [../models/loras/](../models/loras/) (gitignored). See [../models/README.md](../models/README.md). The included example config [../examples/configs/tcole_valley.yaml](../examples/configs/tcole_valley.yaml) expects `models/loras/Thomas_Cole_epoch_10.safetensors`.
- **RIFE v4.25 inference weights** are re-vendored under [../vendor/rife_v425/](../vendor/rife_v425/). See [../vendor/rife_v425/README.md](../vendor/rife_v425/README.md). No external download needed.
- **SDXL base, Lightning LoRA, TAESD** are pulled from HuggingFace on first use into `~/.cache/huggingface/`. ~6 GB initial download.

## Running the acceptance command

See [phase-2-acceptance.md](phase-2-acceptance.md) for the per-milestone GPU acceptance procedures (2A foundation, 2B keyframes, 2C full render).

## Outputs

`outputs/` is gitignored. Long renders should write progress checkpoints into `outputs/staging/<subject>/` so a session can be resumed. The current implementation does this via the per-PNG keyframe writes in Phase A.
