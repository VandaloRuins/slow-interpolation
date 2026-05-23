# Getting started (for agents)

You are an AI agent setting up `slow-interpolation` on behalf of a user. The user has cloned the repo and asked you to take them from "fresh clone" to "first rendered MP4". You run this protocol; the user observes, confirms when prompted, and watches the final video. Expect the bootstrap to take 25 to 40 minutes wall time on first run (most of that is HuggingFace model downloads, ~7 GB).

## Decision tree before you begin

Run these checks in order. Stop at the first failure and resolve with the user before proceeding.

1. **GPU present and CUDA visible.** Run `nvidia-smi`. Expect at least 8 GB VRAM (RTX 4060 Laptop class confirmed working). If the command is missing or shows no NVIDIA GPU, switch to the [Modal cloud path](#fallback-modal-cloud-gpu); brief the user that local rendering is not available and confirm they want to proceed via cloud GPU at ~0.07 to 0.30 USD per render.
2. **Python 3.10 or 3.11 available.** `python --version`. 3.12 is untested; if 3.10 / 3.11 are unavailable, ask the user to install one before continuing; do not improvise.
3. **Disk space.** 15 GB free on the drive holding the HF cache (`~/.cache/huggingface/`). The first run downloads ~7 GB models plus the user's output renders. If short, ask the user to free space.
4. **Platform.** Windows 11 with PowerShell, Linux, or WSL. macOS / Apple Silicon (MPS) is untested with the diffusers + SDXL Lightning stack pinned here; if the user is on macOS, surface this caveat and offer the Modal cloud path instead.

## Install protocol

Order matters. CUDA torch MUST be installed before `pip install -e .`. The PyPI torchvision wheel pulls in a CPU-only torch as a transitive dependency, which silently downgrades any CUDA build that came before it.

```bash
python -m venv .venv

# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Bash / WSL / Linux:
source .venv/bin/activate

pip install --upgrade pip

# Step 1, CUDA torch from the PyTorch index.
pip install --index-url https://download.pytorch.org/whl/cu121 torch==2.5.1 torchvision==0.20.1

# Step 2, the package itself.
pip install -e .

# Verify CUDA is alive.
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
# Expected: 2.5.1+cu121 True
```

If the verify line prints `False`, the install order got cross-wired. Re-run step 1 with `--force-reinstall` and re-verify before continuing. Do not proceed to Step 2 with a broken CUDA setup; the failure will surface 20 minutes into the first render instead of now.

For development work (you will be modifying `src/`), substitute `pip install -e .[dev]` for `pip install -e .` to pull `pytest` and helpers.

## Get a LoRA before the first render

The pipeline ships without LoRA weights. The reference config `examples/configs/tcole_valley.yaml` expects a Thomas Cole SDXL LoRA at `models/loras/Thomas_Cole_epoch_10.safetensors`. `models/loras/` is gitignored; weights are not committed.

Three paths. Pick one with the user before downloading anything.

| Path | When to use | Action |
|---|---|---|
| Test without a LoRA | First-render smoke test only | Set `style.lora_path` to a non-existent path. The pipeline silently skips LoRA loading. Renders generic SDXL Lightning output. Useful to prove the install works; not useful as a final render. |
| Download a published checkpoint | The user wants a quick first render with a real style | Ask the user for the CivitAI URL or HuggingFace ID. Any 1024-trained Kohya-format SDXL LoRA is compatible (the loader has a UNet-only fallback for the diffusers 0.31+ Kohya text-encoder regression). Save to `models/loras/`, update the config's `style.lora_path` and `style.prefix` to match. |
| Train one | The user has a domain in mind and wants to ship a release piece | Walk them through [dataset-curation.md](dataset-curation.md). Plan for 1 to 2 days wall time including dataset curation. |

Do not commit a `.safetensors` file by accident. The gitignore covers `models/loras/`; verify with `git status` after dropping the weight in.

## Run the first render

```bash
python -m slow_interpolation.run examples/configs/tcole_valley.yaml
```

Expected timeline on an RTX 4060 Laptop class card:

| Phase | First run | Subsequent runs | Output |
|---|---|---|---|
| HF cache download | 5 to 15 min | 0 (cached) | `~/.cache/huggingface/` populated |
| Phase A (keyframes) | 20 to 25 min | 20 to 25 min | `outputs/staging/tcole_valley/keyframes/*.png` (26 PNGs at 1344x768) |
| Phase A.5 (smoothing) | ~30 s | ~30 s | Same PNGs, smoothed in place |
| Phase C + D (RIFE + H.264) | 4 to 7 min | 4 to 7 min | `outputs/tcole_valley.mp4` |

Total: 30 to 50 minutes first time, 25 to 35 minutes after. Brief the user with the estimate when you start; they will check back rather than watch.

Expected output: `outputs/tcole_valley.mp4`. 1328 x 752 pixels (1344 x 768 minus an EDGE_CROP that is 0 by default since the 2026-05-16 border-crop probe; the 16-pixel total reduction comes from the SDXL crop micro-conditioning + the latent edge-suppression callback, not from a post-RIFE crop), 24 fps, ~60 seconds, ~7 MB H.264 yuv420p. Pastoral valley with Roman aqueduct ruins drifting between three light conditions (afternoon amber, golden hour, misty morning), looping seamlessly.

## When something fails

Decision table. Match the symptom, run the suggested action, surface the result to the user only if it does not resolve.

| Symptom | Diagnosis | Action |
|---|---|---|
| `torch.cuda.is_available()` is False post-install | torchvision install pulled CPU-only torch | Re-run install Step 1 with `--force-reinstall`. Re-verify before continuing. |
| First Phase A call hangs for >30 s with no log output | HF cache download in progress | Check `~/.cache/huggingface/` is growing. Wait. ~7 GB to fetch. Update the user every 5 minutes if they are watching. |
| `IndexError: list index out of range` during LoRA load | diffusers 0.31+ Kohya text-encoder regression | The pipeline's `_load_style_lora` catches this and retries with UNet-only LoRA. If the retry also fails, the LoRA file is malformed; verify the path and the file size with the user. See [docs/findings/lora-training.md](../findings/lora-training.md) section on the regression for details. |
| Out of memory during Phase A | VRAM pressure | Reduce `resolution` in the config to a smaller SDXL training-bucket size. Options: 832 x 1216, 1024 x 1024, 768 x 1024. See [../pipeline.md](../pipeline.md) for the SDXL bucket constraint. Re-run. |
| Render output looks "stuck" between keyframes | Not a failure; the technique is intentionally slow | The 64x RIFE interpolation produces 24 fps motion from sparse keyframes. Confirm with the user that the slow drift is the desired aesthetic before chasing this. |
| Border artifacts on output (decorative frames, geometric edges) | LoRA-specific failure mode | Add `rife.edge_crop: 8` to the config and re-render. See [docs/findings/border-crop.md](../findings/border-crop.md) for the probe that decided the default is 0. |
| `Connection refused` or HF rate limit during download | Network or HF infrastructure issue | Wait 5 minutes and retry. If persistent, ask the user if they need to be on a different network or have a HF token to set. |

If the symptom is not on this list, do not improvise a fix. Surface the error to the user with the exact stack trace and check [docs/findings/](../findings/) for prior art before proceeding.

## Routing: local vs Modal

**Do not route by reading this page; route by reading [hardware-routing.md](hardware-routing.md).** That page is the canonical pre-flight + decision table. The four pre-flight checks (nvidia-smi, torch CUDA, HF cache disk free, GPU busy) decide local vs Modal vs hybrid; the decision table maps render-type + local-capability to a route; the trade-offs (free-but-single-stream vs paid-but-parallel) are named explicitly.

This page is the local-bootstrap protocol. If `hardware-routing.md` decides Modal, jump to [../modal.md](../modal.md) for the command surface; the bootstrap above is skippable in that branch (Modal handles its own environment).

## After the first render lands

Surface the success to the user. Then surface the natural next moves:

- "Want to try a different LoRA?" If yes, walk them through swapping `style.lora_path` and `style.prefix` in the config.
- "Want to try a different noise source?" If yes, add a `render.noise.kind: perlin` block to a config; see [../findings/noise-sources.md](../findings/noise-sources.md) for the catalog.
- "Want to train a domain LoRA?" If yes, switch to [dataset-curation.md](dataset-curation.md).
- "Want to see what else is worth exploring?" If yes, point at [docs/next-exploration-steps.md](../next-exploration-steps.md). The repo's contribution funnel rewards PRs back; see [../../CONTRIBUTING.md](../../CONTRIBUTING.md) shape 1 for new-LoRA-domain findings.

Do not push these all at once. Wait for the user's next ask.
