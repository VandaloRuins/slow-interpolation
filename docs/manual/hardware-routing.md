# Picking a render target (for agents)

You are an AI agent picking where to run a slow-interpolation render on behalf of a user. The user has cloned this repo and asked you to render something. Before you dispatch, you decide: local GPU, Modal cloud, or hybrid. The user does not know their own hardware capabilities versus this codebase's demands; bridging that gap is the load-bearing reason this page exists.

## The default

**Local first.** Run on the user's machine if their hardware is sufficient and free. Route to Modal only when local is insufficient, when parallelism is worth the cost, or when the local GPU is occupied. Modal credit is a finite resource (free tier ~$30/month, paid tier billed per second); reserve it for work that genuinely needs cloud GPUs.

This default supersedes the noise workstream's earlier 2026-05-17 "Modal default for multi-variant tests" decision. That decision was set when Luca's local GPU was busy with other work; it was correct then, but it is not the universal default. The universal default is the protocol below.

## Pre-flight: detect hardware

Run the four checks below in order. On agent runtimes with shell access (Claude Code, Cursor, Antigravity, Codex CLI, Aider), execute them and read the output. On chat-only agents (web-based Claude, ChatGPT in browser, Copilot Chat), paste the commands and ask the user to paste back the output; route based on what they show.

If `outputs/_hardware.json` exists and is fewer than 30 days old, you can skip the detection and trust the cache. The user can force re-detection by saying "re-check hardware" or "re-detect"; otherwise the cache is the answer.

### Check 1: NVIDIA driver

```bash
nvidia-smi --query-gpu=name,memory.total,memory.free,utilization.gpu --format=csv,noheader,nounits
```

Expected: one CSV line per GPU. Example: `NVIDIA GeForce RTX 4060 Laptop GPU, 8188, 7521, 3`. Fields: name, total MB, free MB, utilisation percent.

If the command is not found:
- On macOS: expected (no NVIDIA support since 2018). Route Modal.
- On Linux or Windows: NVIDIA driver missing. Route Modal AND surface to the user: "no NVIDIA driver detected; install drivers if you want local rendering, otherwise routing through Modal."

### Check 2: CUDA reachable through torch

Skip this check on a fresh clone (torch not yet installed). After bootstrap:

```bash
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)"
```

Expected: `True NVIDIA GeForce RTX 4060 Laptop GPU`.

If `False`: torch is the CPU-only PyPI build. The install order in [getting-started.md](getting-started.md) was wrong; fix before proceeding.

If `ImportError`: torch not yet installed. Continue using only check 1's result until the user has bootstrapped.

### Check 3: HF cache disk free

The HuggingFace cache lands at `~/.cache/huggingface/` (Linux/macOS) or `%USERPROFILE%/.cache/huggingface/` (Windows). First run needs ~7 GB downloaded plus working room; budget 20 GB free on the drive holding it.

```bash
# Linux / macOS
df -h ~/.cache/huggingface/ 2>/dev/null || df -h ~

# Windows PowerShell
Get-PSDrive -PSProvider FileSystem | Where-Object Used -gt 0 | Select-Object Name,Used,Free
```

If less than 20 GB free: route Modal, AND surface to the user: "disk free on the HF cache drive is X GB; first local render needs ~7 GB downloaded plus working room. Free space or route through Modal."

### Check 4: GPU currently busy

```bash
nvidia-smi --query-compute-apps=pid,name,used_memory --format=csv,noheader
```

Expected: empty line if the GPU is idle.

If populated (other processes are using VRAM): surface the process list to the user. Default lean: route Modal so you do not collide with their work. Confirm with the user before deciding.

### Cache the result

After running the checks, write `outputs/_hardware.json` (gitignored under the existing `outputs/` rule):

```json
{
  "detected_at": "2026-05-18T14:30:00Z",
  "platform": "Windows 11",
  "gpu_present": true,
  "gpu_name": "NVIDIA GeForce RTX 4060 Laptop GPU",
  "vram_total_mb": 8188,
  "vram_free_mb": 7521,
  "cuda_torch_available": true,
  "hf_cache_free_gb": 312.4,
  "gpu_busy": false,
  "busy_processes": []
}
```

Subsequent sessions on this machine skip detection and read from the cache unless it is older than 30 days or the user says "re-check hardware".

## Decision table

Match the user's render request to a row. Cells specify route + rationale.

| Render type | Local sufficient? | Local free? | Route | Why |
|---|---|---|---|---|
| Single render, 1344x768, ~80 s | yes (>= 8 GB VRAM) | yes | local | free, sub-2-minute, no Modal cost |
| Single render, 1344x768, ~80 s | yes | no (GPU occupied) | Modal L40S | ~$0.07; do not collide with the user's other work |
| Single render | VRAM < 8 GB OR no GPU | n/a | Modal L40S | hardware-gated |
| Multi-variant batch (5+ variants, parallel-able) | yes (sequential) | yes | Modal L40S parallel | 3 h local sequential collapses to ~25 min parallel on Modal |
| Multi-variant batch | yes (sequential) | no | Modal L40S parallel | both reasons stack |
| Release-grade 1536x896 or higher | possibly (12+ GB VRAM) | n/a | Modal A100-80GB | tier-gated; SCI_ART, large compositing renders |
| CPU-bound noise prep (Worley high `cell_density`, image-derived first-pass) | n/a | n/a | local CPU | Worley at `cell_density >= 1000/Mpx` is O(H * W * n_points); local fast CPU beats Modal L40S for this stage |
| Iteration loop (3+ renders in quick succession, tuning params) | yes | yes | local for the loop, Modal once locked | iteration is single-stream; do not pay Modal per iteration |
| First-render bootstrap (fresh clone, never run before) | yes | yes | local | so the user learns their setup works; download the HF models once; from there iterate locally |
| First-render bootstrap | no | n/a | Modal | the user gets to a result without local bootstrap pain; flag they will not have local capability for follow-ups |

If the request does not match a row, default to local. Surface your routing decision to the user in one sentence before dispatching.

## Trade-offs (named)

- **Local**: free per render, fits an iteration loop well, no per-second metering. Single-stream: one render at a time. Collides with other GPU work (editor, browser, other ML jobs). Bound by the user's hardware; cannot escape an 8 GB VRAM ceiling for SDXL Lightning at 1344x768.
- **Modal**: paid (~$0.07 to $0.30 per 60s loop on L40S; A100 tiers higher). Parallel: dispatches all variants of a batch simultaneously. Dedicated: no contention with the user's other work. Bound by the $30/month free credit if applicable; reserve for work that needs the cloud's properties.
- **The user does not know their own hardware specs versus this code's demands.** This is the actual reason the pre-flight exists. The agent runs the four checks, decides correctly, and the user does not have to learn the VRAM-bucket-to-SDXL-resolution math.
- **Hybrid pattern**: iterate locally to lock the config and the prompts, then dispatch the final batch to Modal for parallel renders. Best of both for release work. The local-iteration / Modal-release pattern is the recommended default for any multi-render project.

## Concrete commands

After routing, you dispatch:

### Local

```bash
python -m slow_interpolation.run examples/configs/<your-config>.yaml
```

Output lands at `outputs/<output_name>.mp4`. Phase A keyframes take ~20 minutes on an RTX 4060 Laptop class card; Phase C + D takes ~5 minutes; total ~25 minutes per render.

### Modal single

```bash
modal run -m cloud.entrypoint --config examples/configs/<your-config>.yaml
```

Output lands on the `slow-interp-outputs` Modal volume; download with `modal volume get`. Total wall time ~2 minutes on L40S, ~$0.07 per 60s loop.

### Modal batch (multi-variant parallel)

```bash
# Build the configs list as a comma-separated string with forward slashes
# (Windows shells and bash globs disagree; explicit is safer).
CONFIGS=$(ls examples/configs/<round>/*.yaml | tr '\n' ',' | sed 's/,$//')

modal run -m cloud.batch --configs "$CONFIGS"
```

Use `run_in_background: true` on the Bash dispatch and follow [findings/monitoring-long-cloud-jobs.md](../findings/monitoring-long-cloud-jobs.md) for the monitoring playbook.

## When to ask the user before dispatching

- Modal cost estimate exceeds $1 for the planned work. Cost estimator: `python cloud/cost_estimate.py --configs <list>`.
- Local GPU is occupied by a known process and the user has not signalled willingness to pause it.
- The render is for release (final cut), not iteration. Confirm GPU tier (L40S vs A100-80GB).
- The hardware cache is older than 30 days and you would otherwise rely on it. Ask if the user wants a re-check or to trust the cache.

Otherwise, route per the decision table, surface your choice in one sentence, and proceed.

## When something looks wrong

| Symptom | Action |
|---|---|
| `nvidia-smi` works but `torch.cuda.is_available()` is False | torch install order; reinstall CUDA torch FIRST per [getting-started.md](getting-started.md) install protocol |
| Modal credit near $0 | switch to local OR ask user to top up; do not dispatch silently |
| Local render OOM mid-Phase-A | reduce `resolution` to a smaller SDXL bucket (832x1216, 1024x1024) OR re-route to Modal L40S; document a config-side fix if the issue recurs |
| Modal queue contention slows a dispatched job | accept and wait; do not reroute mid-job. A Modal A-tier wait is usually faster than restarting local from scratch |
| `nvidia-smi` segfaults or hangs | NVIDIA driver bug; ask the user to reboot or update drivers, route Modal in the meantime |
| Free disk drops below 5 GB during local render | abort the render, surface to user, suggest moving the HF cache off the OS drive OR routing to Modal |

If the symptom is not on this list, do not improvise routing. Surface the symptom + your two candidate routes (local with a workaround, Modal) to the user and let them decide.

## Once you have chosen Modal

Follow [findings/monitoring-long-cloud-jobs.md](../findings/monitoring-long-cloud-jobs.md) for the dispatch playbook: `run_in_background: true`, log to `outputs/_harness_logs/`, surface the dashboard URL, do not poll. The hardware-routing protocol on this page tells you WHEN to use Modal; the monitoring finding tells you HOW to operate it after the decision.

## Surface to the user

After picking, tell the user in one line what you chose and why:

> "Detected RTX 4060 Laptop, 7.3 GB free, GPU idle. Routing local. Estimated ~25 min for `roses_vase_60s.yaml`."

Or:

> "GPU is occupied by `comfyui.exe` (3.2 GB VRAM in use). Routing Modal L40S to avoid collision. Estimated ~2 min, ~$0.07. Override if you'd rather pause the local process."

That's the prompt-library framing in practice: you named the default, named the rationale, left the door open for the user to redirect.
