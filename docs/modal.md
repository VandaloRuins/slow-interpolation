# Modal cloud-render path (optional)

`slow-interpolation` can render in the cloud on [Modal.com](https://modal.com).
This is the parallel path to the local CLI
(`python -m slow_interpolation.run`). Use it when you want a bigger GPU
than your local box, or you want to batch many configs in parallel, or
you want reproducible artifacts that survive your local machine.

The local path is the documented default and always works without
installing the Modal SDK. **This page is for the day you want the cloud
path too.**

> **Verified 2026-05-17**: cold-run against
> [`examples/configs/tcole_valley.yaml`](../examples/configs/tcole_valley.yaml)
> on Modal L40S completed in **121.4 s** at **0.07 USD**, output
> envelope (1328x752, 24 fps, 59.54 s, 6.8 MB) matches the local Phase
> 2C reference exactly, visual inspection passed (no border / pulse /
> loop-closure regressions). See
> [`docs/planning/workstreams/modal/progress.md`](planning/workstreams/modal/progress.md) for the full bring-up
> log.

Contents:

- [When to use it](#when-to-use-it)
- [One-time setup](#one-time-setup)
- [Render a config](#render-a-config)
- [What you get back](#what-you-get-back)
- [The YAML `modal:` section](#the-yaml-modal-section)
- [Shipping a variant](#shipping-a-variant) -- three worked examples
- [Cost expectations per GPU tier](#cost-expectations-per-gpu-tier)
- [Troubleshooting](#troubleshooting)

## When to use it

| Scenario | Use Modal? |
|---|---|
| You have an RTX 3090 / 4090 locally and one config to render | No, run locally |
| You want to render 5 Renoir subjects in parallel | Yes |
| You want to render at A100 80GB or H100 | Yes |
| You want artifacts a collaborator can pull without your machine being up | Yes |
| You want a permanent reproducibility manifest stapled to every render | Yes (the local CLI does not emit one) |
| You are iterating on the pipeline itself | No, run locally; iteration round-trips are faster |

## One-time setup

```bash
# 1. Install the cloud extra.
pip install -e .[cloud]

# 2. Authenticate. Opens a browser; you log in with email or GitHub.
modal token new

# 3. Upload LoRA checkpoints to the slow-interp-loras Volume.
#    Re-run anytime to add or update weights. Files in models/loras/ are
#    gitignored locally; this step pushes them to Modal storage.
modal run -m cloud.upload_weights --src models/loras
```

### Windows note

The Modal CLI prints Unicode checkmarks that Windows' default cp1252
console can't encode. If you see `'charmap' codec can't encode character`,
set UTF-8 once per shell:

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
```

Or bash:

```bash
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1
```

Alternative for fresh PowerShell sessions where the env vars don't
take effect (e.g. some shell-launch ordering edge cases): switch the
console codepage to UTF-8 directly.

```powershell
chcp 65001
```

Apply once per shell. Belt-and-suspenders with the env vars above.

### Batch rendering

Dispatch N configs in parallel via `cloud/batch.py`. Per-container GPU
billing means cost is identical to serial, but wall time collapses
from sum(individual) to ~max(individual).

```bash
# Render every YAML matching a glob.
modal run -m cloud.batch --configs "examples/configs/renoir/*.yaml"

# Explicit list.
modal run -m cloud.batch --configs "a.yaml,b.yaml,c.yaml"

# Override GPU for the whole batch.
modal run -m cloud.batch --configs "..." --gpu A100-40GB
```

At end of batch you get a summary table with wall time, GPU-seconds
sum, parallel speedup, per-config output paths, total cost. For
sequential dispatch with human-in-the-loop iteration (rather than
fire-and-forget parallel `map()`), see `cloud/release_batch.py` plus
[`docs/planning/workstreams/modal/release-batch.md`](planning/workstreams/modal/release-batch.md), adds an opt-in warm
pool with six safety layers; max forgotten cost capped at ~0.50 USD
by `scaledown_window=1800` on the function. Use `release_batch` only
when your batch is **sequential with human-in-the-loop**, otherwise
`batch.py` parallel fan-out gives identical cost and faster wall.

### Volume housekeeping

`cloud/volume_admin.py` is a project-specific wrapper over Modal's
volume operations. Knows the three volume names, adds capabilities
Modal's CLI lacks (recursive `size`, pattern-based delete, single-
render `inspect`).

```bash
# Quick overview.
python -m cloud.volume_admin list

# Total size per volume + cost/month estimate.
python -m cloud.volume_admin size

# Inspect one render's artifacts on the outputs volume.
python -m cloud.volume_admin inspect outputs tcole_valley

# Pattern-based delete (dry-run first).
python -m cloud.volume_admin rm outputs "*.png" --dry-run
python -m cloud.volume_admin rm outputs "*.png"

# One-time cleanup of staging backlog (complement to per-render cleanup).
python -m cloud.volume_admin gc-staging

# Bulk download by pattern.
python -m cloud.volume_admin download outputs "*.mp4" ./outputs/from-modal/
```

Run with `python -m`, not `modal run` (volume operations are network
calls; no container needed).

### Pre-flight check

`cloud/preflight.py` prints workspace identity + volume sizes + total
disk before you commit to a render or batch. Read-only, ~5 s, free.

```bash
modal run -m cloud.preflight
```

Run before a release-day batch, after a long gap, or any time you want
to know what's already in your volumes.

### Smoke test before any batch

`cloud/smoke.py` runs the smallest possible config end-to-end (~30 s,
~0.02 USD on L40S) and asserts the output MP4 lands on the volume.
Use as a pre-flight check before release sessions, batches, or after
any branch pull:

```bash
modal run -m cloud.smoke
```

Exits PASS with wall time + cost, or FAIL with a one-line cause and a
list of common fixes (LoRA missing on volume, image build broken, HF
cache corrupted). The cost is so low that it can be a no-think
pre-flight every time you sit down with Modal after a gap.

### Why `modal run -m cloud.entrypoint` and not `modal run cloud/entrypoint.py`

`cloud/` is a Python package (it has `__init__.py`), and its files use
relative imports (`from .app import ...`). Modal's "script mode"
(`modal run path/to/file.py`) refuses to load files with relative
imports; you must invoke in "module mode" with the `-m` flag and a
dotted path. The error message Modal gives you is explicit about this.

That is the entire setup. The first render auto-creates the
`slow-interp-outputs` and `slow-interp-hf-cache` Volumes and downloads
the SDXL base + Lightning LoRA + TAESD models into the HF cache volume
(adds ~5 min to the first render only; subsequent renders reuse the
cache).

## Render a config

```bash
modal run -m cloud.entrypoint --config examples/configs/tcole_valley.yaml
```

Output:

```
[modal] config:         /.../examples/configs/tcole_valley.yaml
[modal] gpu:            L40S
[modal] pipeline_entry: slow_interpolation.pipeline:Pipeline
[modal] config_loader:  slow_interpolation.config:load_pipeline_config
[modal] git commit:     1a2b3c4 (dirty)
...
[modal] render complete.
[modal] total wall time:    1462.3s
[modal] estimated cost:     0.79 USD
[modal] output (in volume): tcole_valley.mp4
[modal] manifest:           tcole_valley.manifest.json
[modal] download with:
        modal volume get slow-interp-outputs tcole_valley.mp4 ./outputs/
        modal volume get slow-interp-outputs tcole_valley.manifest.json ./outputs/
```

CLI overrides for one-off use:

```bash
# Override the GPU tier without editing YAML.
modal run -m cloud.entrypoint --config my.yaml --gpu A100-40GB

# Override the entry point (see "Shipping a variant" below).
modal run -m cloud.entrypoint --config my.yaml \
    --pipeline-entry mypkg.pipeline:CompositingPipeline
```

## What you get back

Two files per render, both in the `slow-interp-outputs` Volume:

- `<output_name>.mp4` -- the final video. Same envelope as the local
  Phase 2C reference (`outputs/tcole_valley.mp4`): H.264 yuv420p, 24 fps,
  composition family / palette / surface visually equivalent to the
  legacy samples.
- `<output_name>.manifest.json` -- a run manifest with the resolved
  config YAML (verbatim), git commit and dirty flag, `pipeline_entry`
  and `config_loader` strings used, resolved model identifiers, GPU
  tier, per-phase wall time (A, A.5, C+D), total wall time, hourly USD
  rate at render time, and estimated cost in USD.

Download both:

```bash
modal volume get slow-interp-outputs tcole_valley.mp4         ./outputs/
modal volume get slow-interp-outputs tcole_valley.manifest.json ./outputs/
```

Or pull the whole volume:

```bash
modal volume get slow-interp-outputs / ./outputs-from-modal/
```

The cost ceiling target is **< 5 USD per 60s loop**. Renders that exceed
the ceiling are logged conspicuously in both the CLI output and the
manifest's `notes` field. They are not failed; the manifest is the
audit trail.

## The YAML `modal:` section

The local CLI (`python -m slow_interpolation.run`) only consumes the
standard top-level YAML keys (`style`, `subject`, `render`, `frames`,
`resolution`, `rife`, `encoding`, `borders`, `models`, `output_dir`,
`output_name`). Anything else, including a `modal:` section, is
silently ignored. That means the same YAML file is valid for both
paths.

The Modal entrypoint parses `modal:` if present:

```yaml
# At the bottom of any pipeline YAML config.
modal:
  gpu: L40S                                                 # default
  pipeline_entry: slow_interpolation.pipeline:Pipeline      # default
  config_loader: slow_interpolation.config:load_pipeline_config  # default
  notes:
    - "Optional free-form strings copied verbatim into the manifest."
  preserve_staging: false                                   # default
```

All five fields are optional. Defaults match the values above. CLI
flags (`--gpu`, `--pipeline-entry`, `--config-loader`) take precedence
over the YAML values.

`preserve_staging` controls whether the per-render `staging/<name>/`
directory of intermediate PNG keyframes is kept on the outputs volume.
**Default false** (cleanup) to keep the outputs volume tidy: each
render leaves only the MP4 + manifest. Set `true` when you want to
inspect Phase A intermediates or download the staged keyframes for
offline reuse. `cloud/volume_admin.py gc-staging` clears pre-fix
backlog or recovers from accidental sessions where it was `true`.

Supported GPU tiers (Modal pricing in `cloud/manifest.py`):

```
T4    L4    A10G    L40S    A100-40GB    A100-80GB    H100    H200
```

The default `L40S` (1.95 USD/hr) is enough for 1344x768 SDXL Lightning.
The 1344x768 workload fits comfortably in 24 GB VRAM; the larger tiers
are reserved for higher-resolution work or batch parallelism.

## Shipping a variant

The Modal app is decoupled from any one specific Pipeline class. Three
variant shapes are supported without touching `cloud/`:

### (i) Same Pipeline, different LoRA + subjects

This is the Renoir release shape, and any future domain LoRA.

```yaml
# examples/configs/renoir_vase.yaml
style:
  name: renoir_strong
  lora_path: models/loras/Renoir_flowers_epoch_8.safetensors
  lora_scale: 0.75
  prefix: "rfl, impressionist oil painting, "

subject:
  name: renoir_vase
  prompts:
    - { label: "A: morning vase", prompt: "..." }
    - { label: "B: noon vase",    prompt: "..." }
    - { label: "C: dusk vase",    prompt: "..." }
    - { label: "A (return)",      prompt: "..." }

# Same Pipeline class, same config schema. No code changes.
```

Upload the new LoRA once:

```bash
modal run -m cloud.upload_weights --src models/loras
```

Render:

```bash
modal run -m cloud.entrypoint --config examples/configs/renoir_vase.yaml
```

### (ii) Override `pipeline_entry` to a fork's Pipeline class

**Step 0**: add your fork's dotted path to `KNOWN_PIPELINE_ENTRIES` in
`tests/test_modal_contract.py` and run:

```bash
pytest tests/test_modal_contract.py -v
```

This catches contract regressions (missing `render`, wrong `__init__`
signature, etc.) locally in <1 s, no GPU required. **Run before
spending Modal credits to discover the same regression.**


When you have a different Pipeline class entirely (post-Phase-3 dual
prompt compositing is the planned example, see
[`docs/next-exploration-steps.md`](next-exploration-steps.md) section
4.3). Any class with the contract:

```python
class CompositingPipeline:
    def __init__(self, config: PipelineConfig) -> None: ...
    def render(self) -> Path: ...
```

is a valid `pipeline_entry`.

```yaml
# examples/configs/renoir_composite.yaml
style:    { ... }
subject:  { ... }

modal:
  pipeline_entry: slow_interpolation.compositing:CompositingPipeline
```

Or pass on the CLI:

```bash
modal run -m cloud.entrypoint --config my.yaml \
    --pipeline-entry slow_interpolation.compositing:CompositingPipeline
```

The dotted-path string is resolved on the container via `importlib`. If
the new class needs config fields that the standard `PipelineConfig`
does not have, you also need (iii) below: an extended `config_loader`.

### (iii) Deploy a branch with structural source changes

When a fork restructures the pipeline or extends the config schema:

```bash
# 1. Edit src/ on a branch.
git checkout -b experimental-noise-warping
# ... edit src/slow_interpolation/pipeline.py, add a new noise source ...

# 2. Deploy the new image. add_local_dir picks up your local source
#    tree at deploy time, so the new container has the new code.
modal deploy cloud/app.py

# 3. Render against the new image, optionally with an extended
#    config loader if you added new YAML keys.
modal run -m cloud.entrypoint --config my.yaml \
    --pipeline-entry slow_interpolation.pipeline:Pipeline \
    --config-loader slow_interpolation.config:load_pipeline_config_v2
```

The git commit recorded in the manifest reflects the local checkout at
the time of the run, so the cloud render is bound to your local
branch's exact source state.

To run two branches side-by-side without confusion, change the Modal
app name in `cloud/app.py` (`APP_NAME = "slow-interpolation-noise-warp"`)
before deploying the branch. Different app name, different deployed
image, the two coexist on Modal.

## Cost expectations per GPU tier

For a 60-second loop (26 keyframes at 1344x768, RIFE 64x). L40S is the
measured baseline; the other tiers are scaled estimates from published
throughput ratios and should be confirmed empirically before counting on
them. The manifest records actual wall time and cost per run.

| GPU | USD/hr | Wall time | Cost per 60s loop | Notes |
|---|---|---|---|---|
| L4 | 0.80 | ~6 min (est.) | ~0.08 USD | Cheapest viable tier. |
| A10G | 1.10 | ~3 min (est.) | ~0.06 USD | Good price/perf. |
| **L40S** | **1.95** | **121 s (measured)** | **0.07 USD** | **Default.** Best balance for 1344x768 SDXL Lightning. |
| A100-40GB | 2.78 | ~90 s (est.) | ~0.07 USD | Slight speedup, similar cost. Worth it for batches. |
| A100-80GB | 3.40 | ~85 s (est.) | ~0.08 USD | Reserved for >24 GB workloads (larger res, multi-LoRA). |
| H100 | 4.56 | ~60 s (est.) | ~0.08 USD | Fastest. Cost-competitive for short jobs. |

Cost target: **< 5 USD per 60s loop**. The measured L40S baseline of
**0.07 USD** has 70x headroom under the ceiling. The ceiling exists for
the day someone runs a much larger config (longer loop, higher res,
heavier LoRA stack); for the current pipeline it is essentially
unreachable.

## Modal SDK gotchas

[`findings/modal-sdk-quirks.md`](findings/modal-sdk-quirks.md) is the
failure-driven compendium of Modal SDK 1.4.x behaviours that informed
the design of `cloud/`. Read before upgrading the `modal` pin or
adding a new function with non-trivial Modal API surface.

## Troubleshooting

### "No weight files found" when uploading LoRAs

`upload_weights.py` looks for `.safetensors / .bin / .ckpt / .pt` under
`--src` (default `models/loras`). Confirm:

```bash
ls models/loras/*.safetensors
```

If empty, copy your style LoRA checkpoints into the directory. The repo
gitignores them.

### "ImportError: cannot import name 'load_pipeline_config'"

The Modal app imports your `config_loader` via `importlib`. The dotted
spec must be `module.path:attribute`, not `module.path.attribute`. If
you forgot the colon you get an `ImportError` on the container.

### Renders are slower than the wall-time estimates above

The first render against a new HF cache volume downloads ~7 GB of model
weights (SDXL base + Lightning LoRA + TAESD). Subsequent renders reuse
the cache and run at the estimated speed. Watch for "downloading
sdxl_lightning..." in the Modal log to confirm.

### Local CLI fails with "ModuleNotFoundError: No module named 'modal'"

You ran the local CLI without the cloud extra, but somehow imported
something from `cloud/`. The local CLI must NOT depend on `cloud/`.
Confirm:

```bash
grep -r "import cloud" src/
grep -r "from cloud" src/
```

Both should return nothing. If they do, that is a bug to fix; the
opt-in design is broken if local code imports cloud code.

### "modal volume get" downloads zero bytes

The volume was committed in `render()` (`outputs_volume.commit()`) but
the host-side cache may be stale. Force-refresh:

```bash
modal volume ls slow-interp-outputs
```

If your file is listed, retry the `get`. If it is not listed, the render
did not write it (check the Modal logs for the run).

### My image build is slow / I hit Modal's image-build cache miss

`add_local_dir` invalidates the layer when any file under the dir
changes. Editing `src/slow_interpolation/` triggers a rebuild of that
layer (fast: just file copy). Editing `pyproject.toml` does NOT trigger
an `Image.pip_install` rebuild because the pinned pip versions are
encoded in `cloud/app.py`'s `image` definition, not read from pyproject.
If you change a pip pin, update `cloud/app.py` to match and the rebuild
runs cleanly.

### I want to keep the local YAML clean of `modal:` sections

Use CLI flags only. `modal run -m cloud.entrypoint --config my.yaml
--gpu A100-40GB --pipeline-entry ...` overrides everything. The YAML
stays a pure pipeline config.

### How do I know which Modal app a render belongs to?

The manifest records `modal_app_name` (defaults to
`slow-interpolation`). On the Modal dashboard, all renders under that
app name share a function and log stream.
