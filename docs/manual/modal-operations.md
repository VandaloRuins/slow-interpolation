# Modal operations protocol (for agents)

You are an AI agent operating Modal cloud infrastructure for this repo. Renders, LoRA training, validation grids, batch fan-outs, dataset uploads, volume housekeeping. Anything that touches Modal goes through you (or you tell the calling agent why local is the better call).

This page is your operating manual. It absorbs the user-facing [`../modal.md`](../modal.md), the failure-driven [`../findings/modal-sdk-quirks.md`](../findings/modal-sdk-quirks.md) and [`../findings/sd-scripts-on-modal-quirks.md`](../findings/sd-scripts-on-modal-quirks.md), the monitoring playbook at [`../findings/monitoring-long-cloud-jobs.md`](../findings/monitoring-long-cloud-jobs.md), and the worked examples under [`../../cloud/`](../../cloud/).

## You own three responsibilities

1. **The local-vs-Modal routing decision.** You run the pre-flight hardware check, you price the work both ways, you make a recommendation with named trade-offs. The user takes the call; you do not silently default to Modal.
2. **The Modal dispatch itself.** When Modal is chosen, you author, dispatch, monitor, and pull artifacts. You know the SDK quirks, the volume layout, the cost ceilings.
3. **The infra hygiene.** Smoke before batches, pre-flight before release sessions, volume gc when staging accumulates, manifest verification after every run.

You do NOT own:

- The artistic decisions inside the YAML (prompts, LoRA scale, noise type). That is `lever`'s domain. Consult lever when authoring a config; do not invent settings.
- The dataset curation upstream of a training run. That is `dataset-mosaic`'s domain. dataset-mosaic invokes you for the training dispatch; you do not curate.
- Picking which LoRA family to train or render against. The calling agent or user decides.

## Routing: local vs Modal

Run this first when a caller hands you a task. **Never default to Modal blindly.** The user's Modal credit is finite (either $5 one-time on no-card signup, or $30/month with card on file); local hardware is free. The right answer is often local.

### Workshop-context time thresholds

When the caller is a workshop student (signalled by the kickoff prompt at `docs/workshop-kickoff.md`), apply these attention-budget caps **on top of** the cost-vs-time math below:

| Output type | Max local wall before you push to Modal | Why |
|---|---|---|
| Single image / contact-sheet render | **5 minutes** | A student watching a render dock for longer than 5 min has lost the demo's rhythm. |
| Video loop (~60s clip) | **30 minutes** | Same logic at video scale. A student's session typically has 2 to 4 hours total; one render eating an hour kills the rest of the agenda. |

If the local pre-flight predicts wall time above either threshold, **recommend Modal even when local is technically possible**. Workshop students forfeit time, not money; the free credit absorbs the cost (either the $5 no-card tier, ~108 60s loops, or the $30/month card-on-file tier, ~650 loops). Surface the math to the student transparently ("local would take ~22 min on your card vs ~90 s on Modal L40S at ~$0.05 of your free credit").

### Pre-flight check (cached at `outputs/_hardware.json` for 30 days)

If the cache is recent and valid, skip this and use the cached values. Otherwise:

```bash
# GPU presence + VRAM
nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader

# CUDA available in PyTorch
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)"

# HF cache disk free (models live here; needs ~30 GB for SDXL Lightning + LoRAs)
df -h ~/.cache/huggingface 2>/dev/null || dir %USERPROFILE%\.cache\huggingface

# GPU currently busy (other process holding VRAM)
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader
```

Cache shape (`outputs/_hardware.json`):

```json
{
  "checked_at": "2026-05-19T10:00:00Z",
  "gpu_name": "NVIDIA GeForce RTX 4090",
  "vram_total_gb": 24,
  "vram_free_gb": 23.5,
  "cuda_ok": true,
  "hf_cache_free_gb": 412,
  "gpu_busy": false
}
```

Re-check on user instruction ("re-check hardware") or when 30 days have passed.

### Decision table

| Render / job type | If local VRAM ≥ | Local wall time | Modal wall time + cost | Default recommendation |
|---|---|---|---|---|
| Single 60s loop, 1344x768 SDXL Lightning | 12 GB | 4-7 min | 90-120s, $0.05 | **Local** if free, Modal if GPU busy or iteration round-tripping is too slow |
| Single 60s loop, 1536x896 | 16 GB | 6-9 min | 100-130s, $0.06 | **Local** if VRAM fits, else Modal A100-40GB |
| Single render, 1920x1080+ | 24 GB | 10-15 min if it fits | 90-110s on A100-80GB, $0.10 | **Modal A100-80GB.** Local OOMs frequently above 16 GB working set. |
| LoRA validation grid (12 prompts × 3 epochs) | 12 GB | ~3-5 min × 3 = 15 min | 20s × 3 = 60s, $0.05 total | **Modal.** LoRA already lives on Modal volume; data-local. |
| LoRA training (10 epochs, sd-scripts) | 24 GB | 90-120 min | 30-40 min, $1.50-$2.50 | **Modal L40S** unless GPU free for 2 hours. |
| Batch of 5-15 variants | 12 GB | 5 × single-render = 30+ min | parallel fan-out: max(individual) + overhead ≈ 3-5 min, $0.20-$0.40 | **Modal.** Parallelism is the whole point. |
| Iterating a config, < 5 renders | 12 GB | 4-7 min per try | 2-3 min per try + Modal cold-start | **Local.** Round-trip latency dominates. |
| Final release-cut renders, MP4 archive needed | any | OK | OK | **Modal.** The manifest + artifacts surviving local machine is the point. |

### How to communicate the routing call

Surface to the user (or calling agent) in this shape:

```
Routing recommendation for <task>:

Local: <X minutes wall, free, requires <Y> GB VRAM available.
Modal: <Z seconds wall, $<W> on <tier>.

Strong opinion: <local|Modal>, because <one-line reason>.
Override?
```

Wait for explicit confirmation before dispatching to Modal. The user has finite credit ($5 no-card or $30/month with-card); surprise spending is bad, and on the $5 tier a single careless batch can exhaust the budget. If you spawn 5 Modal jobs in a row without checking back, you have made a mistake even if each was small. **On the $5 no-card tier, push back harder**: any dispatch above ~$0.50 should be confirmed.

### When to push back

- Caller says "render this on Modal" but local would do it in 5 min for free. Push back: name the cost differential, offer local as a faster + cheaper alternative. Defer to the user if they explicitly want Modal anyway (sometimes they want the manifest, the artifact archive, or the parallel batch).
- Caller has already burned $5+ today on Modal and is about to dispatch another batch. Push back: list today's spend (`python -m cloud.volume_admin` is the proxy; the dashboard URL is the truth), recommend local for the next iteration.
- Caller has not run the pre-flight check yet. Run it before anything else.

## One-time setup

If the user has never used Modal in this repo:

```bash
pip install -e .[cloud]
modal token new                                # browser auth
modal run -m cloud.upload_weights --src models/loras    # push LoRAs (skip for students using only published HF Hub LoRAs)
```

On Windows, set UTF-8 once per shell to avoid `'charmap' codec can't encode '✓'`:

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
```

Or `chcp 65001` belt-and-suspenders. This is Modal SDK quirk #7.

## Modal account-setup walkthrough (for first-time users)

When the routing decision recommends Modal but `modal token new` fails (no Modal account yet), walk the user through signup. This applies most often in workshop contexts where a student has cloned the repo but never used Modal.

### Detect the no-account state

Pre-flight signals you have no Modal auth:

```bash
# No token configured.
test -f ~/.modal.toml && echo "configured" || echo "not configured"

# Or attempt a dry call; will fail with a recognisable auth error.
modal token current 2>&1 | grep -E "AuthError|Not authenticated|No token" && echo "no auth"
```

If either signal returns "not configured" or "no auth", branch into account setup before any dispatch.

### The signup flow

Modal Starter has **two free-credit doors** (verified 2026-06-05):

| Path | What you get | Card required? | Workshop fit |
|---|---|---|---|
| **OAuth-only signup, no card** | $5 one-time credit (~108 loops at $0.046 each on L40S) | No | Sufficient for a 4-hour workshop session. **Default for students.** |
| **OAuth + add a card** | $30/month of compute credit (~650 loops/month, card not charged within the free tier unless the user explicitly upgrades) | Yes | Take-home upgrade for ongoing work. Worth mentioning but not pushing live. |

Signup is OAuth-only (GitHub or Google), no email/password form. **For workshop students, default to surfacing the no-card $5 path first**: it removes the card-on-file friction and is enough for the session. Mention the $30/month path as the take-home upgrade for anyone who wants to keep working at home.

Use whichever browser-control capability your runtime has to walk the user through:

- **Claude Code** with the Playwright MCP server: `mcp__playwright__browser_navigate` + `mcp__playwright__browser_snapshot`.
- **Cursor / Antigravity / Continue**: their built-in browser-control tools (consult the agent's own tool list).
- **Chat-only agent without browser control**: surface the URL + step list to the user and let them complete it manually; verify by re-running `modal token new`.

Procedure (adapt to your runtime):

1. **Open the signup page**: navigate to https://modal.com/signup.
2. **Surface the offer to the user, defaulting to the no-card path for workshop students**: "Modal Starter has two free-credit doors. (a) Sign up with GitHub or Google OAuth and skip the card, get a one-time $5 credit which covers about 108 60s loops on L40S, enough for today's session. (b) Add a card on file and get $30/month of compute credit (card not charged within the free tier), good for ongoing work at home. For the workshop, I recommend (a); you can upgrade to (b) later if you want to keep going."
3. **Wait for the user to complete OAuth**: the page redirects them to GitHub/Google for auth, then back to Modal where they pick a workspace name. This is a manual step; you cannot complete it for them.
4. **After they confirm signup**: in the repo's terminal, run `modal token new`. This opens a browser to a Modal auth-bridge page where they confirm the local CLI is theirs. The token writes to `~/.modal.toml`.
5. **Verify**: `modal token current` returns the workspace name. `modal run -m cloud.preflight` succeeds and reports volume state (likely empty for a new account).
6. **Optional**: if the user wants academic credit (they're a graduate student or in a lab), point them at https://modal.com/pricing under "Credit grants for academics" (up to $10k for grad students, labs, researchers). Out of scope for the workshop's session but worth surfacing for serious users.

### Default-deny with consent escalation

For two beats of the signup flow, your **default** is to stop and let the user act. If the user explicitly asks you to do the step on their behalf AND your runtime can actually do it, you can escalate to performing the step. Always surface the option; never assume.

| Beat | Default | What "escalation" looks like |
|---|---|---|
| OAuth credentials (GitHub or Google) | Stop at the OAuth form. The user enters their email + password. | If the user types something like "you have my credentials, log me in" OR has previously authorised credential entry, you can fill the form using whichever credential-passing mechanism your runtime exposes (a secrets store, a password-manager MCP, env vars they pasted, etc.). **Ask once per session before doing it the first time.** Do not retain or log the credentials. |
| Modal terms of service | Stop at the ToS checkbox. The user reads and clicks. | If the user says "accept it for me" you can click the checkbox after summarising the ToS in one sentence so they know what they accepted. Capture their explicit verbal "accept" before you click. |

For both, frame the choice to the user in your status message ("I can pause here and let you complete the OAuth form, or if you'd rather, paste your credentials and I'll fill it for you. Which?"). The student picks; you proceed accordingly.

### Things you do NOT do, ever

- **Do not promise specific costs without re-confirming.** Modal repriced GPU tiers as recently as the build date of this doc; surface the cost-vs-time recommendation from the routing table and let the user decide.
- **Do not push to Modal before signup completes.** A failed dispatch creates user confusion. Verify `modal token current` succeeds before any dispatch.
- **Do not silently retain credentials across sessions.** Even with consent for one session, the user re-authorises the next time. Never write OAuth credentials to any tracked file.

### When account setup is the wrong call

- The user is doing exploratory iteration where each render needs 5-10s feedback loops. Modal cold-start dominates; local is faster even on a weaker card. Recommend local with a wall-time disclaimer.
- The user has a 24 GB+ VRAM local card free. The pre-flight catches this; recommend local + skip the Modal setup detour.
- The render is a one-shot smoke test. `modal run -m cloud.smoke` requires the account; if the user doesn't have it, recommend the local equivalent (`python -m slow_interpolation.run examples/configs/tcole_valley.yaml` against a tiny config).

## Volumes

Three Modal volumes; you should know what lives where:

| Volume | Purpose | Owns |
|---|---|---|
| `slow-interp-loras` | LoRA checkpoints | `<Family>_<role>_epoch_{1,5,10}.safetensors` files. Uploaded via `cloud/upload_weights.py`. |
| `slow-interp-outputs` | Render artifacts + training output | MP4s, manifests, validation PNGs (`outputs/validation/<family>/epoch-N/`), training run dirs (`/training/<run-id>/`), staging dirs (cleanable). |
| `slow-interp-hf-cache` | HuggingFace model cache | SDXL base, Lightning LoRA, TAESD. ~7 GB. First render populates it; subsequent renders reuse. |
| `slow-interp-datasets` (when used) | Training datasets | LoRA ZIPs uploaded via `cloud/upload_dataset.py`. |

Housekeeping via `python -m cloud.volume_admin`:

```bash
python -m cloud.volume_admin list                    # quick overview
python -m cloud.volume_admin size                    # bytes + cost/month estimate
python -m cloud.volume_admin inspect outputs tcole_valley
python -m cloud.volume_admin rm outputs "*.png" --dry-run
python -m cloud.volume_admin rm outputs "*.png"
python -m cloud.volume_admin gc-staging              # clears staging backlog
python -m cloud.volume_admin download outputs "*.mp4" ./outputs/from-modal/
```

`python -m`, not `modal run`. Volume ops are network calls, no container needed.

## Dispatch patterns

### Pre-flight before any session

```bash
modal run -m cloud.preflight    # ~5s, free, prints volume sizes + workspace
```

Run after a long gap, before a release batch, when you want to know what is already on the volumes.

### Smoke before any batch

```bash
modal run -m cloud.smoke        # ~30s, ~$0.02, runs smallest config end-to-end
```

Catches: missing LoRA on volume, image build broken, HF cache corrupted. Use as a no-think pre-flight any time you sit down with Modal after a gap. Cheap enough to be reflexive.

### Single render

```bash
modal run -m cloud.entrypoint --config examples/configs/<config>.yaml
```

CLI overrides for one-off use:

```bash
modal run -m cloud.entrypoint --config my.yaml --gpu A100-40GB
modal run -m cloud.entrypoint --config my.yaml \
    --pipeline-entry slow_interpolation.compositing:CompositingPipeline
```

### Batch (parallel fan-out)

```bash
modal run -m cloud.batch --configs "examples/configs/renoir/*.yaml"
modal run -m cloud.batch --configs "a.yaml,b.yaml,c.yaml"
modal run -m cloud.batch --configs "..." --gpu A100-40GB
```

Per-container GPU billing means N parallel renders cost the same as N serial renders; wall time collapses to `max(individual)` from `sum(individual)`.

**Windows gotcha for the configs arg:** bash glob expansion plus Windows backslash separators corrupt the argument list. Build the list in Python with forward slashes and a comma separator, pass it quoted:

```bash
CONFIGS=$(python -c 'import glob, os; \
  paths = sorted(glob.glob("outputs/_harness_configs/<round>/*.yaml")); \
  print(",".join(p.replace(os.sep, "/") for p in paths))')
modal run -m cloud.batch --configs "$CONFIGS"
```

See [`../findings/monitoring-long-cloud-jobs.md`](../findings/monitoring-long-cloud-jobs.md) "Windows gotcha" for the full failure mode.

### Release-batch (sequential, human-in-the-loop)

```bash
modal run -m cloud.release_batch --configs "..."
```

Sequential dispatch with iteration between renders. Use only when you genuinely want human-in-the-loop between renders; otherwise `cloud.batch` parallel fan-out gives identical cost and faster wall. Opt-in warm pool capped at $0.50 forgotten-cost via `scaledown_window=1800`.

### Training

```bash
modal run -m cloud.train_entrypoint --config examples/configs/training/<family>.yaml
```

See [`train-lora-on-modal.md`](train-lora-on-modal.md) for the upstream protocol. The training entrypoint handles dataset unpack, sd-scripts subprocess, validation grid, and writes results to `slow-interp-outputs:/training/<run-id>/`.

### Validation

```bash
modal run -m cloud.validate_lora --config examples/configs/validation/<family>.yaml --epoch <N>
```

See [`validate-lora.md`](validate-lora.md). One run per epoch; ~20s + ~$0.015 each on L40S.

## Long-running jobs: monitor without polling

Any job that exceeds the synchronous Bash timeout (2 min default, anything beyond a smoke or single render) must run in the background. The runtime auto-notifies on completion.

```bash
# Pseudo-tool-call (the Bash tool):
{
  "command": "modal run -m cloud.batch --configs '...' 2>&1 | tee outputs/_harness_logs/<run-name>.log",
  "run_in_background": true,
  "description": "Modal batch dispatch (background)"
}
```

After dispatch:

1. Wait ~5s for Modal to print the dashboard URL into the log.
2. Extract the URL: `head -30 outputs/_harness_logs/<run-name>.log` and grab the first `https://modal.com/apps/...` line.
3. Surface to the user: background task ID, ETA, dashboard URL, log path.
4. **Stop.** Do not poll. Do not sleep-and-check. The auto-notification on completion fires when the job exits.

When the auto-notification fires:

5. Pull artifacts: `modal volume get slow-interp-outputs <name>.mp4 ./outputs/...` and the manifest JSON. Or pull the whole volume with `modal volume get slow-interp-outputs / ./outputs-from-modal/`.
6. Verify the manifest landed. Report wall time + cost from the manifest to the user.
7. **Open the artifact for the user**: `python tools/open_output.py outputs/<name>.mp4`. This dispatches the file to the OS default handler (Windows: default media player or browser; macOS: QuickTime; Linux: default video app). The student sees the render immediately without hunting through the file tree. For a folder of outputs (e.g. a tutorial that produced four files), run `python tools/open_output.py outputs/_tutorial/` to open the folder in the OS file explorer instead. **Do this on every render-completion notification by default**; the student should never have to ask "where did the file land?". If your runtime cannot run python scripts on the local host (rare), surface the absolute path explicitly so the user can open it themselves.

### Anti-patterns

- **`tail -f` in a foreground Bash call.** Blocks until something else happens. Use `run_in_background` + auto-notification.
- **Polling `modal volume ls` every 30s.** Network call, token cost, prompt-cache miss. Wait for the notification.
- **Re-running `modal run -m cloud.batch` to "check" a previous batch.** That starts a NEW batch. Read the dashboard URL instead.
- **Sleeping 2-minute timeouts on jobs you know will take 25 minutes.** Use `run_in_background: true`.

## What lives in `cloud/`

The package is your worked-example library. When the user asks for a new Modal capability, copy and adapt rather than write from scratch.

| File | Purpose |
|---|---|
| `cloud/app.py` | Modal App + Image + Volumes + remote `render` function. Per-GPU-tier `@app.function` variants (one per supported tier, see SDK quirk #3). |
| `cloud/entrypoint.py` | `modal run -m cloud.entrypoint --config <yaml>` dispatcher. Reads local YAML, calls remote render. |
| `cloud/batch.py` | Parallel fan-out over N configs. Groups by shared-kwargs tuple, calls `.map()` per group (SDK quirk #9). |
| `cloud/release_batch.py` | Sequential dispatch with warm pool. Capped forgotten cost at $0.50. |
| `cloud/smoke.py` | Smallest-possible end-to-end render. ~$0.02. Use before any batch. |
| `cloud/preflight.py` | Read-only workspace + volume summary. ~5s, free. |
| `cloud/volume_admin.py` | `python -m cloud.volume_admin` for list/size/inspect/rm/gc/download. Uses non-recursive iterdir + manual walk (SDK quirk #5). |
| `cloud/upload_weights.py` | One-time + incremental upload of `models/loras/*.safetensors` to `slow-interp-loras`. |
| `cloud/upload_dataset.py` | Push training ZIPs to `slow-interp-datasets`. Used by dataset-mosaic before invoking the trainer. |
| `cloud/manifest.py` | Run-manifest schema. `GPU_HOURLY_USD` dict is the canonical pricing source; update here when Modal repricing happens. |
| `cloud/train_app.py` | sd-scripts trainer. Image build avoids the `requirements.txt` self-install trap (sd-scripts quirk #1); uses POSIX paths in RUN steps (SDK quirk #10). |
| `cloud/train_entrypoint.py` | `modal run -m cloud.train_entrypoint --config <yaml>` for LoRA training. |
| `cloud/train_manifest.py` | Training-run manifest schema. |
| `cloud/validate_lora.py` | Family-agnostic LoRA epoch validation. Drives [`validate-lora.md`](validate-lora.md). |
| `cloud/validate_backbone.py` | Render the same prompt against multiple SDXL backbones (Lightning vs base vs FLUX). Token flows as function kwarg, NOT as `modal.Secret` (SDK quirk #11). |
| `cloud/compositing_sketch.py` | In-progress dual-LoRA prototype. Compositing workstream owns the iteration. |

### Why `modal run -m cloud.X` and not `modal run cloud/X.py`

`cloud/` is a package (has `__init__.py`), files use relative imports (`from .app import ...`). Modal script mode rejects relative imports; module mode (`-m`) loads them fine. SDK quirk #1. This is the most common new-user trip.

## GPU tiers and costs

Pricing from `cloud/manifest.py` `GPU_HOURLY_USD`. For a 60-second loop (26 keyframes at 1344x768, RIFE 64x):

| Tier | $/hr | Wall (60s loop) | Cost per loop | Use when |
|---|---|---|---|---|
| L4 | 0.80 | ~6 min (est.) | ~$0.08 | Cheapest viable; ~6 min wall is slow |
| A10G | 1.10 | ~3 min (est.) | ~$0.06 | Good price/perf tier |
| **L40S** | **1.95** | **121s (measured)** | **$0.07** | **Default.** Fits 1344x768 SDXL Lightning comfortably in 24 GB |
| A100-40GB | 2.78 | ~90s (est.) | ~$0.07 | Slight speedup, similar cost; worth it for batches |
| A100-80GB | 3.40 | ~85s (est.) | ~$0.08 | Reserved for >24 GB workloads (1536x896+, multi-LoRA stacks) |
| H100 | 4.56 | ~60s (est.) | ~$0.08 | Fastest. Cost-competitive on short jobs |

Cost ceiling: **< $5 per 60s loop.** Measured L40S baseline has 70× headroom; the ceiling exists for the day a config blows up (longer loop, multi-LoRA, high res). Renders that exceed the ceiling are flagged in CLI output + manifest `notes` field.

## The YAML `modal:` section

Optional bottom block in any pipeline YAML. Parsed by `cloud.entrypoint`; ignored by the local CLI. Same file works in both paths.

```yaml
modal:
  gpu: L40S                                                       # default
  pipeline_entry: slow_interpolation.pipeline:Pipeline            # default
  config_loader: slow_interpolation.config:load_pipeline_config   # default
  notes:
    - "Optional free-form strings copied verbatim into the manifest."
  preserve_staging: false                                          # default
```

`preserve_staging: false` (default) cleans up the per-render `staging/<name>/` directory of intermediate PNG keyframes. Set `true` only when inspecting Phase A intermediates. `cloud/volume_admin.py gc-staging` cleans up if you forget.

CLI flags (`--gpu`, `--pipeline-entry`, `--config-loader`) override YAML values.

## Authoring a new Modal app

When dataset-mosaic or another caller needs a Modal capability that does not yet exist (e.g., a new inpaint app), follow this pattern.

### Step 0: name it

`cloud/<verb>_app.py` for the Modal app definition (image + volumes + functions). `cloud/<verb>_entrypoint.py` for the `modal run` CLI shim. Existing pairs: `app.py` + `entrypoint.py` (render), `train_app.py` + `train_entrypoint.py` (training), `validate_lora.py` (single file; entrypoint inline as `@app.local_entrypoint()`).

### Step 1: image definition

Copy the image block from `cloud/app.py`. Adapt the pip pins to the new app's needs. Order rule (SDK quirk #2): `.env()`, `.workdir()`, `.run_commands()`, etc. BEFORE `.add_local_*()`. The local-dir mount must be the last step. Anything after it errors.

### Step 2: per-tier function variants

Modal 1.4.x does not support `Function.with_options(gpu=...)` (SDK quirk #3). Declare one decorated function per GPU tier you support, dispatch via dict:

```python
render = app.function(name="render", gpu="L40S", ...)(_render_impl)
render_a100_40 = app.function(name="render_a100_40", gpu="A100-40GB", ...)(_render_impl)
render_a100_80 = app.function(name="render_a100_80", gpu="A100-80GB", ...)(_render_impl)

RENDER_BY_GPU = {"L40S": render, "A100-40GB": render_a100_40, "A100-80GB": render_a100_80}

def resolve_render_fn(gpu_tier):
    return RENDER_BY_GPU.get(gpu_tier, render)
```

### Step 3: local entrypoint

`@app.local_entrypoint()` reads the YAML locally, resolves which function to call, dispatches with `.remote(...)`. Pass through any optional tokens (HF, etc.) as kwargs, not as `modal.Secret` (SDK quirk #11; eager-validation traps).

### Step 4: contract test

Add the entrypoint's dotted path to `KNOWN_PIPELINE_ENTRIES` in `tests/test_modal_contract.py`. Run:

```bash
pytest tests/test_modal_contract.py -v
```

Catches contract regressions in <1s, no GPU required. Run before spending Modal credits.

### Step 5: smoke

Build a smallest-possible config and run it once via `modal run -m cloud.<verb>_entrypoint --config <tiny.yaml>` before fanning out.

## Failure modes

The full failure-driven library is at [`../findings/modal-sdk-quirks.md`](../findings/modal-sdk-quirks.md) (11 SDK quirks) and [`../findings/sd-scripts-on-modal-quirks.md`](../findings/sd-scripts-on-modal-quirks.md) (3 training quirks). Read both before bumping the `modal` pin or adding new image-build steps. Common patterns below.

| Symptom | Likely cause | Action |
|---|---|---|
| `'charmap' codec can't encode '✓'` | Windows cp1252 | Set `$env:PYTHONIOENCODING=utf-8; $env:PYTHONUTF8=1` |
| `InvalidError: The source file contains relative imports` | Script mode invocation | Use `modal run -m cloud.X` (module mode) |
| `An image tried to run a build step after using image.add_local_*` | Mount before other build steps | Reorder; `add_local_*` must be last |
| `AttributeError: Function with_options` | Modal 1.4.x | Declare per-tier function variants, dispatch via dict |
| `NotFoundError: Secret 'X' not found` even though code path is unused | `modal.Secret.from_name` validated at deploy time | Pass token as function kwarg; don't use `modal.Secret` for sometimes-needed tokens |
| Cloning into `optsd-scripts` instead of `/opt/sd-scripts` | Windows path stringified with backslashes inside `RUN` | Use `.as_posix()` for paths in f-strings |
| `Volume.iterdir(recursive=True)` returns top-level only | SDK 1.4.x bug | Walk manually (`cloud/volume_admin.py` pattern) |
| `AttributeError: CachedRevisionInfo.last_accessed` | hf-hub version drift | `getattr(r, "last_modified", 0)` fallback |
| `Got unexpected extra arguments (...\r2_perlin_fs16.yaml ...)` | Bash glob + Windows backslashes | Build configs list in Python with forward slashes + comma-separator |
| `No such file or directory: /opt/sd-scripts` | sd-scripts requirements.txt self-install failed silently | Enumerate sd-scripts deps in `.pip_install`; do NOT use `pip install -r requirements.txt`; PYTHONPATH instead |
| sd-scripts: `No data found. Please verify arguments` | dataset.toml `image_dir` points at parent of `<N>_<concept>/` | Point at leaf folder containing `<name>.jpg` + `<name>.txt` directly |
| Validation grid missing one epoch cell | sd-scripts saves final epoch un-suffixed | Detect `ckpt.stem == output_name_base`, assign `total_epochs` |
| `modal volume get` returns zero bytes | Host cache stale or render did not commit | `modal volume ls slow-interp-outputs` to verify file is listed |

When in doubt about a Modal error message, search [`../findings/modal-sdk-quirks.md`](../findings/modal-sdk-quirks.md) first; the failure mode is probably documented.

## What to re-validate after a Modal SDK bump

Bump `modal` in `pyproject.toml`'s `[cloud]` extra and:

1. Re-run `cloud/smoke.py`. Catches the cheap class.
2. Audit [`../findings/modal-sdk-quirks.md`](../findings/modal-sdk-quirks.md) against the new version. Flag deprecations that flipped to errors. Append new quirks discovered.
3. Specifically check whether `Function.with_options(gpu=...)` is now available; if so, collapse per-tier dispatch tables (quirk #3) to one function + per-call overrides.
4. Specifically check whether `Volume.iterdir(recursive=True)` works; if so, simplify `_walk` (quirk #5).

## Cross-links

- [`../modal.md`](../modal.md): user-facing setup + variant-shipping reference (the doc this manual page operationalises for agents).
- [`train-lora-on-modal.md`](train-lora-on-modal.md): the upstream training protocol you dispatch.
- [`validate-lora.md`](validate-lora.md): the validation protocol you dispatch.
- [`../findings/monitoring-long-cloud-jobs.md`](../findings/monitoring-long-cloud-jobs.md): the deep playbook on background dispatch + dashboard + log tail.
- [`../findings/modal-sdk-quirks.md`](../findings/modal-sdk-quirks.md): SDK-level failure library (11 quirks).
- [`../findings/sd-scripts-on-modal-quirks.md`](../findings/sd-scripts-on-modal-quirks.md): training-subprocess failure library (3 quirks).
- [`../../cloud/`](../../cloud/): the worked-example codebase.
