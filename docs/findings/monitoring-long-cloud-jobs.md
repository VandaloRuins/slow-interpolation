# Monitoring long-running cloud jobs from an agent

> **This finding documents the Modal branch of the hardware-routing protocol at [`../manual/hardware-routing.md`](../manual/hardware-routing.md). Run the routing protocol first; this finding tells you HOW to operate Modal once you have decided to dispatch. Do not default to Modal blindly. The routing protocol's decision table is the source of truth for WHEN.**

Operational finding for any AI agent dispatching Modal renders, sweeps, or batches from inside an interactive coding session. The default temptation is to "sleep and check" or to repeatedly grep the log: both are wrong and burn tokens (and the prompt cache, see [Claude Code docs on background tasks]).

This doc is the playbook the slow-interpolation noise workstream settled on after two rounds of Modal dispatches, the second of which crashed first try due to a Windows-specific bug worth knowing about.

## The constraint

A typical Modal render: ~2 minutes (single tcole_valley config) to ~25 minutes (a 9-variant batch fanned out in parallel). A typical Modal sweep across LoRAs or parameter grids: longer. None of this fits inside a synchronous Bash call without timing out and none of it should be polled inside the agent turn.

## What works (three tools, used together)

### 1. Auto-notification via background execution

This is the primary mechanism. Dispatch with `run_in_background: true` on the Bash tool call. The agent moves on with other work. When the background job exits the runtime delivers a `<task-notification>` automatically. No polling required, no token cost during the wait.

```
# Pseudo-tool-call (Claude Code Bash tool):
{
  "command": "modal run -m cloud.batch --configs '<comma-separated-paths>'",
  "run_in_background": true,
  "description": "Modal batch dispatch (background)"
}
```

Agent receives a task-id like `bnx5m5p55`. The agent should:

- Acknowledge the dispatch to the user with the task-id and a rough ETA.
- Provide the user the dashboard URL (see #2) and the local log path (#3).
- **Stop.** Do not poll. Do not sleep. Continue with non-blocking work or wait.

When the auto-notification fires, the agent picks back up.

### 2. The Modal dashboard

Every `modal run` call prints its dashboard URL on the second line of stdout (after the `Initialized` heading). Pattern:

```
https://modal.com/apps/<workspace>/main/ap-<RUN-ID>
```

This URL is a live UI showing per-container status, per-container logs, queued / running / completed counts, total cost. The user can leave it open in a tab and refresh whenever they want a status check. **Always extract this URL from the dispatch log and surface it to the user.** It is the cheapest possible monitoring channel — zero tokens, real-time, the source of truth.

How to extract it: tail the first ~20 lines of the dispatch log after a few seconds. The URL is the first `https://modal.com/...` line.

### 3. Tailing the local log

For users who prefer terminal:

```powershell
# PowerShell:
Get-Content outputs\_harness_logs\<run-name>.log -Wait -Tail 30
```

```bash
# Bash / Git Bash:
tail -f outputs/_harness_logs/<run-name>.log
```

Always redirect the Modal command's stdout+stderr into a log file under `outputs/_harness_logs/` when dispatching in background. Without redirection, the user has no way to see live progress except via the dashboard.

## Anti-patterns the agent must avoid

- **Sleeping-and-checking inside the agent turn.** Each check is a tool call. The prompt cache TTL is 5 minutes; a 25-minute job sleep-checked every 30 seconds means ~50 unnecessary tool calls, dozens of cache misses, and a degraded interactive feel.
- **`tail -f` inside a foreground Bash call.** It blocks. The user types "status?" and Claude is stuck in a tail loop until something else happens.
- **Polling the Modal volume for output filenames.** Same problem as 1, plus every `modal volume ls` is a network call.
- **Re-running `modal run -m cloud.batch` to check status.** That's not how Modal works; it starts a new run.
- **Hard-coding short timeouts.** Modal batches that legitimately take 25 minutes do not deserve a 2-minute Bash timeout. Use `run_in_background: true`.

## The right agent workflow, end to end

1. **Pre-flight.** Run `modal run -m cloud.smoke` synchronously (it takes ~30 seconds, costs ~$0.015, and confirms the entire stack is healthy). If smoke fails, fix before dispatching anything bigger.
2. **Build the configs.** Generate YAMLs to a writable directory (`outputs/_harness_configs/<round-name>/` is the convention used in this repo). Verify at least one loads cleanly via `load_pipeline_config` and that `build_noise_source` returns the expected class.
3. **Build the configs argument carefully.** See the Windows gotcha below.
4. **Dispatch with `run_in_background: true`.** Redirect stdout to `outputs/_harness_logs/<run-name>.log`.
5. **Extract and surface the dashboard URL.** Quick `head -30` on the log a few seconds after dispatch is enough.
6. **Report to user.** Background ID, ETA, dashboard URL, log path. Then stop talking about it.
7. **Wait for the auto-notification.** Do not poll.
8. **On completion: download artifacts.** `modal volume get slow-interp-outputs <name>.mp4 ./outputs/...` and `modal volume get slow-interp-outputs <name>.manifest.json ./outputs/...`. Or pull the whole volume with the trailing `/`.
9. **Organize.** Move the MP4s into a dedicated subfolder. Keep `outputs/` root clean.

## Windows gotcha: comma-separated forward-slash paths

The first attempt at the Round 2 batch dispatch failed because the bash shell glob-expanded `outputs/_harness_configs/round-2-spatial-freq-cole/*.yaml` into 9 separate positional arguments, AND the resulting paths had Windows backslashes that confused `modal run`'s argument parser.

Symptom in the log:

```
Got unexpected extra arguments
(outputs/_harness_configs/round-2-spatial-freq-cole\r2_perlin_fs16.yaml
 outputs/_harness_configs/round-2-spatial-freq-cole\r2_perlin_fs24.yaml ...)
```

The fix: build the configs argument in Python with forward slashes and a comma separator, capture it into a shell variable, and pass it quoted:

```bash
CONFIGS=$(python -c 'import glob, os; \
  paths = sorted(glob.glob("outputs/_harness_configs/<round>/*.yaml")); \
  print(",".join(p.replace(os.sep, "/") for p in paths))')
modal run -m cloud.batch --configs "$CONFIGS"
```

`cloud/batch.py` accepts both globs and comma-separated lists by design. On Windows / Git Bash, **always prefer the comma-separated list** to avoid shell glob expansion and path-separator surprises.

## Gotcha: Modal mounts a fixed list of project folders

The Modal entrypoint only mounts these project folders into the render container:

```
vendor/   examples/   cloud/   src/
```

Anything else (`datasets/`, `outputs/`, `models/`, `docs/`, `tests/`, custom folders) is **not visible inside the container**, unless it lives on a Modal Volume (LoRAs go on `slow-interp-loras`, outputs go on `slow-interp-outputs`).

This is a quiet footgun for noise sources or any pipeline step that loads a file by relative path. The bite: round 3's `image_derived` variant referenced `datasets/renoir-flowers/raw/<name>.jpg` and crashed with `FileNotFoundError` on Modal even though the file existed locally. The cascade got worse: the failing variant tripped the app into `APP_STATE_STOPPED`, which aborted the still-running `banded_renoir_tuned` render alongside it. One missing file killed two valid renders.

**Rule for the agent: any file referenced by a YAML config must live under `vendor/`, `examples/`, `cloud/`, or `src/`.** If the resource is a reference image, a dataset sample, or anything else under a non-mounted path, copy or symlink it into `examples/references/<topic>/` (the convention this workstream used for Renoir references at `examples/references/renoir/`) and update the YAML to point at the mounted location. Local renders continue to work because local working directory exposes everything; only the Modal container needs the relocation.

**Verify before dispatch:** when adding a new noise source or pipeline element that reads from disk, do a single Modal smoke render of the affected config (cost ~$0.05) before fanning out to a multi-variant batch. The smoke catches missing-mount errors cheaply.

## Companion: UTF-8 environment variables

The Modal CLI prints Unicode glyphs (✓, 🔨, etc.) that crash on Windows's default cp1252 console:

```
'charmap' codec can't encode character '✓'
```

Fix per [docs/modal.md](../modal.md): set the environment for the dispatch shell:

```bash
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 modal run ...
```

Or once per PowerShell session:
```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
```

Belt-and-suspenders: also run `chcp 65001` to switch the codepage.

## TL;DR for the next agent

- Smoke test, then dispatch with `run_in_background: true`.
- Redirect stdout to `outputs/_harness_logs/<name>.log`.
- Surface the Modal dashboard URL and the log path to the user.
- Do not poll. Wait for the notification.
- On Windows, build the configs argument as a comma-separated forward-slash list in Python; set `PYTHONIOENCODING=utf-8 PYTHONUTF8=1`.
- Any file path inside a YAML must resolve under `vendor/` / `examples/` / `cloud/` / `src/` on Modal. Relocate reference images / datasets / non-mounted resources into `examples/references/<topic>/` before dispatch.
- One failing render in a batch can stop the whole app (`APP_STATE_STOPPED`) and abort siblings. Single-config smoke test any new file-path-touching variant before fanning out.

[Claude Code docs on background tasks]: https://docs.claude.com/en/docs/claude-code
