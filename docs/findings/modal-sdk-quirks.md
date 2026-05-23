# Modal SDK quirks discovered while building cloud/

Date: 2026-05-18 (initial), updated 2026-05-19 (quirk #11 added).
Modal SDK version: **1.4.2** (`pip install modal>=0.66` resolves here as of
the build date).
Scope: load-bearing behaviours of the Modal Python SDK that took multiple
iteration cycles to discover during the build of [`cloud/`](../../cloud/)
(renderer) and the LoRA trainer. Capture so future agents do not
re-discover at cost.

Companion docs:
- [`../modal.md`](../modal.md): user-facing Modal renderer doc.
- [`../training.md`](../training.md): user-facing LoRA trainer doc.
- [`../planning/workstreams/modal/progress.md`](../planning/workstreams/modal/progress.md): renderer workstream log.
- The Modal-trainer workstream log (maintainer's private planning folder during v0.1; surfaces in v0.2).

## Quirks, with discovery cost

### 1. Module-mode invocation required when `cloud/` uses relative imports

**Symptom**: `modal run cloud/entrypoint.py` fails with
`InvalidError: The source file contains relative imports`.

**Cause**: Modal CLI's "script mode" (path to `.py`) refuses to load
files that use relative imports (`from .app import ...`). The
`cloud/` package uses them because its files share a manifest schema.

**Fix**: invoke in module mode with `-m` and a dotted path:

```bash
modal run -m cloud.entrypoint --config ...
modal run -m cloud.upload_weights --src ...
modal run -m cloud.smoke
modal run -m cloud.batch --configs ...
modal run -m cloud.preflight
modal run -m cloud.train_entrypoint --config ...
modal run -m cloud.upload_dataset --src ...
```

**Discovery cost**: 1 failed run. Error message is explicit but the
fix path (use `-m`) is non-obvious for users coming from CLI examples
in Modal docs that show script-mode.

**Captured in**: [`../modal.md`](../modal.md) "Why `modal run -m cloud.entrypoint`" section,
[`../training.md`](../training.md) preamble, all `cloud/*.py` module docstrings.

### 2. `add_local_*` must be the LAST step in an image chain

**Symptom**: `InvalidError: An image tried to run a build step after
using image.add_local_* to include local files.`

**Cause**: Modal optimises image rebuilds by treating `add_local_dir`
/ `add_local_file` as a runtime mount, not an image layer. Anything
after them in the chain would invalidate that optimisation.

**Fix**: order all `.env()`, `.workdir()`, `.run_commands()`, etc.
BEFORE the `add_local_*` calls. The pattern from [`cloud/app.py`](../../cloud/app.py)
and [`cloud/train_app.py`](../../cloud/train_app.py):

```python
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "ffmpeg")
    .pip_install("torch==2.5.1", ...)
    .env({"PYTHONPATH": "..."})           # before mounts
    .workdir("/root/slow-interpolation")  # before mounts
    .add_local_dir(...)                   # LAST
    .add_local_dir(...)
)
```

**Workaround if you must run a build step after a mount**: pass
`copy=True` to `add_local_*`, which materializes the files as an
image layer at build time (slower rebuilds; defeats the optimisation
purpose). Avoid.

**Discovery cost**: 1 failed run during renderer build. Error message
is helpful (names the rule explicitly), but the fix changed the
build's wall-time profile noticeably (faster iteration loop after).

### 3. `Function.with_options(gpu=...)` does NOT exist in Modal 1.4.x

**Symptom**: `AttributeError: 'Function' object has no attribute 'with_options'`.

**Cause**: Modal docs show `Function.with_options(...)` as the call-time
parameter-override mechanism, but that method was added after 1.4.2.
In 1.4.x, function attributes (GPU, timeout, keep_warm, etc.) are
locked at decoration time.

**Fix**: define one `@app.function`-decorated variant per GPU tier
you want to support, dispatch via a dict. Pattern from
[`cloud/app.py`](../../cloud/app.py) and [`cloud/train_app.py`](../../cloud/train_app.py):

```python
render = app.function(name="render", gpu="L40S", ...)(_render_impl)
render_a100_40 = app.function(name="render_a100_40", gpu="A100-40GB", ...)(_render_impl)
render_a100_80 = app.function(name="render_a100_80", gpu="A100-80GB", ...)(_render_impl)
render_h100 = app.function(name="render_h100", gpu="H100", ...)(_render_impl)

RENDER_BY_GPU = {"L40S": render, "A100-40GB": render_a100_40, ...}

def resolve_render_fn(gpu_tier):
    return RENDER_BY_GPU.get(gpu_tier, render)
```

Add new tiers by adding a new decorated function + a dispatch entry.

**Discovery cost**: 1 failed run during T3#11 probe + a refactor of
the renderer that propagated to `entrypoint.py`, `batch.py`,
`smoke.py`, `release_batch.py`. The trainer's `cloud/train_app.py`
was built with this pattern from the start.

**When to upgrade**: when Modal SDK ships a stable `Function.with_options`,
the dispatch tables collapse to one decorated function + per-call
overrides. Track Modal changelog.

### 4. Modal renamed `keep_warm` to `min_containers` and
`container_idle_timeout` to `scaledown_window` (2025-02-24)

**Symptom**:
`DeprecationError: Deprecated on 2025-02-24: The 'keep_warm' parameter has been renamed to 'min_containers'.`

**Cause**: legacy parameter names from the pre-1.0 Modal SDK were
removed in 1.x.

**Fix**: use the new names everywhere. The warm-pool variant in
[`cloud/app.py`](../../cloud/app.py):

```python
render_warm = app.function(
    name="render_warm",
    gpu="L40S",
    scaledown_window=1800,   # was: container_idle_timeout=1800
    min_containers=0,         # was: keep_warm=0
    ...
)(_render_impl)
```

**Discovery cost**: 1 failed import during T3#12 build.

### 5. `Volume.iterdir(recursive=True)` flag is silently ignored

**Symptom**: `Volume.iterdir(path, recursive=True)` returns only the
top-level entries, even though Modal docs document `recursive` as a
supported kwarg.

**Cause**: the `recursive` flag is accepted by the method signature
on 1.4.2 but does not actually recurse. Possible API drift between
versions.

**Fix**: walk manually. Pattern from [`cloud/preflight.py`](../../cloud/preflight.py)
and [`cloud/volume_admin.py`](../../cloud/volume_admin.py):

```python
def _walk(vol, root):
    total_bytes = 0
    n_files = 0
    for e in vol.iterdir(root):  # non-recursive
        t = str(getattr(e, "type", "")).upper()
        if "FILE" in t and "DIR" not in t:
            total_bytes += getattr(e, "size", 0) or 0
            n_files += 1
        elif "DIR" in t:
            sub_b, sub_n = _walk(vol, e.path)
            total_bytes += sub_b
            n_files += sub_n
    return total_bytes, n_files
```

**Discovery cost**: 1 misleading preflight run that reported 0-byte
volumes for non-empty volumes. Took a moment to spot because the
preflight didn't error; it just lied.

### 6. `huggingface_hub.CachedRevisionInfo` attribute names changed across versions

**Symptom**: `AttributeError: 'CachedRevisionInfo' object has no attribute 'last_accessed'`
(observed on hf-hub 1.15.x inside Modal images, which use newer hf-hub
than the local dev pin).

**Cause**: hf-hub renamed `last_accessed` to `last_modified` (or
dropped it; varies by version). Pre-1.0 hf-hub had `last_accessed`;
1.x has `last_modified`.

**Fix**: use `getattr` fallback + handle the common case of single
revision. Pattern from [`cloud/manifest.py`](../../cloud/manifest.py)
`resolve_hf_revisions`:

```python
revs = list(repo.revisions)
if len(revs) == 1:
    chosen = revs[0]
else:
    try:
        chosen = max(revs, key=lambda r: getattr(r, "last_modified", 0))
    except (AttributeError, TypeError):
        chosen = revs[0]
revisions[mid] = chosen.commit_hash
```

**Discovery cost**: 1 failed smoke run during T1#5 build. The smoke
loaded all models fine; the manifest-write step crashed.

### 7. Windows console codepage (cp1252) cannot encode Modal's Unicode output

**Symptom**: `'charmap' codec can't encode character '✓' in position 0`.
Modal CLI prints `✓` (U+2713) checkmarks during deploy / run; the
default Windows console codepage cannot encode it.

**Fix**: set UTF-8 mode once per shell. Either:

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
```

Or (codepage-level):

```powershell
chcp 65001
```

The env-var path is preferred (no console reset); the `chcp` path is
the belt-and-suspenders fallback for fresh shells where the env vars
don't take effect.

**Discovery cost**: 1 failed upload of LoRA weights. Workaround
becomes muscle memory.

**Captured in**: [`../modal.md`](../modal.md) Windows note section.

### 8. Modal's `Volume.batch_upload(force=True)` requires module-mode invocation context

Less of a quirk, more of an interaction. `Volume.batch_upload` works
fine from a local `@app.local_entrypoint()`, BUT only when the
entrypoint is launched via `modal run -m cloud.upload_X`. Script-mode
hits quirk #1 first.

### 9. Modal `Function.map()` shares ONE kwargs dict across all calls

**Cause**: `Function.map(iterable, kwargs=...)` and
`Function.starmap(...)` both accept a single shared `kwargs` dict
applied to every dispatched call. There is no per-call kwargs
parameter.

**Implication**: when a batch contains configs with different
per-call options (different GPU tier, different `pipeline_entry`,
different `preserve_staging`), you must GROUP configs by their
shared-kwargs tuple and dispatch one `.map()` per group.

**Pattern**: [`cloud/batch.py`](../../cloud/batch.py) groups by
`(gpu_tier, pipeline_entry, config_loader, preserve_staging)` and
calls `.map()` per group. Typical Renoir batches end up in one
group; the machinery scales when configs intentionally diverge.

**Discovery cost**: 1 design iteration during T1#1 build. Caught
during code-review pass, before any failing run.

### 10. Windows `pathlib.Path` stringifies with backslashes inside Modal `RUN` steps

**Symptom**: a Modal image build step like
`f"git clone {repo} {Path('/opt/sd-scripts')}"` runs on the remote
Linux container as `git clone <repo> \opt\sd-scripts`, which the
Linux shell parses as a single token `optsd-scripts`. The clone
silently lands in the wrong directory; later steps fail with
"No such file or directory: /opt/sd-scripts".

**Cause**: `Path("/opt/sd-scripts")` on a Windows host instantiates
as `WindowsPath`; `str()` yields `\opt\sd-scripts`. Modal serialises
the f-string verbatim and sends it to the Linux container, which has
no idea backslashes are path separators.

**Fix**: force POSIX form for any path that will be embedded in a
`RUN` step from a Windows host:

```python
SD_SCRIPTS_DIR = Path("/opt/sd-scripts")
image.run_commands(
    f"git clone {repo} {SD_SCRIPTS_DIR.as_posix()}",  # /opt/sd-scripts
)
```

Inside the container the same `Path` works fine (Linux runtime, no
backslash leak). The bug is purely at f-string-interpolation time on
the host.

**Discovery cost**: 1 failed image build during trainer G1. Build
output `Cloning into 'optsd-scripts'...` revealed the bug.

**Captured in**: the Modal-trainer workstream G1 entry (private during v0.1), and [`../../cloud/train_app.py`](../../cloud/train_app.py) image-build comment.

### 11. `modal.Secret.from_name(...)` validated at app-deploy time, not function-call time

**Symptom**: `modal run -m cloud.X` fails with
`NotFoundError: Secret 'huggingface' not found in environment 'main'`
even though the code path that needs the secret is not exercised on
this invocation, AND the `from_name(...)` call is wrapped in a
`try / except modal.exception.NotFoundError`.

**Cause**: Modal validates `Secret.from_name` references when the
client deploys the app definition to the Modal server, which happens
before any user code from the local entrypoint runs. The `try/except`
at module load time never fires because `from_name(...)` returns a
lazy reference object (no validation locally); the server-side
validation happens later, during deploy, and raises in a context
where the user-level handler cannot catch it. Attaching the
reference via `@app.function(secrets=[...])` is what triggers the
validation, so any function that lists the secret in its decorator
arguments will fail the whole app's deploy when the secret is absent.

**Symptom in practice**: in `cloud/validate_backbone.py`, attaching
`secrets=[modal.Secret.from_name("huggingface")]` to the function
intended to (sometimes) call FLUX gated models caused EVERY backbone
invocation (sdxl_lightning, sdxl_base) to fail at deploy with the
missing-secret error.

**Fix**: do not use `Modal.Secret` for "sometimes-needed" tokens.
Forward the token as a regular function kwarg from the local
entrypoint, and set the corresponding env vars inside the remote
function. Local entrypoint reads the token from env or
`~/.cache/huggingface/token` (the file `huggingface-cli login`
writes), passes it to `.remote(...)` only when the requested backbone
needs it. Remote function does `os.environ["HF_TOKEN"] = hf_token`
before importing `diffusers` / `huggingface_hub`.

```python
# DON'T (eager deploy-time validation, blocks unrelated calls):
@app.function(secrets=[modal.Secret.from_name("huggingface")])
def render(...): ...

# DO (token flows through function arg, no eager validation):
@app.function()  # no secrets=
def render(..., hf_token: str | None = None):
    if hf_token:
        os.environ["HF_TOKEN"] = hf_token
        os.environ["HUGGINGFACE_HUB_TOKEN"] = hf_token
    ...

@app.local_entrypoint()
def main(...):
    hf_token = _read_local_hf_token() if needs_gated_model else None
    render.remote(..., hf_token=hf_token)
```

Reference helper `_read_local_hf_token()` in
[`../../cloud/validate_backbone.py`](../../cloud/validate_backbone.py)
checks `HF_TOKEN`, `HUGGING_FACE_HUB_TOKEN`,
`HUGGINGFACE_HUB_TOKEN` env vars in order, then falls back to
reading `~/.cache/huggingface/token`.

**When the Modal Secret mechanism IS the right choice**: when EVERY
call to the function needs the secret. Then deploy-time validation is
a feature (it catches missing config early) instead of a bug.

**Discovery cost**: 2 failed runs during validate_backbone bring-up.
First run blamed Windows codepage (red herring, the codepage bug was
present too); second run revealed the deploy-time error message
clearly once UTF-8 was fixed.

**Captured in**: [`../../cloud/validate_backbone.py`](../../cloud/validate_backbone.py)
docstring + the helper function comments,
[`../planning/workstreams/modal/progress.md`](../planning/workstreams/modal/progress.md)
2026-05-19 log entry.

## General defensive patterns that emerged

- **`getattr` with default for any Modal / hf-hub attribute access** that
  could be renamed between SDK versions. Cheap defensive pattern.
- **Smoke test before any release session**. [`cloud/smoke.py`](../../cloud/smoke.py)
  is the canonical example. Costs ~$0.02 and catches regressions
  cheaply.
- **`scaledown_window=1800` as a hard-cap** for any function that
  could be left active by accident (warm pools, long-poll workers).
  Worst-case forgotten cost stays under $1.
- **Force UTF-8 on Windows** via env vars at session start; do not
  rely on the default codepage.
- **Pin SDK versions when they affect behaviour**: `modal>=0.66`
  resolves to 1.4.2 today; pin to `modal>=1.4.0,<2.0` if you want
  protection from breaking changes.

## What to re-validate when Modal SDK upgrades

When you bump the `modal` pin in [`../../pyproject.toml`](../../pyproject.toml)'s
`[cloud]` extra:

1. Re-run [`cloud/smoke.py`](../../cloud/smoke.py). Catches the cheap class.
2. Audit this doc against the new SDK version. Mark deprecations
   that flip to errors. Add new quirks discovered.
3. Specifically check whether `Function.with_options` is now
   available; if so, collapse the per-tier dispatch tables (quirk #3)
   to a cleaner shape.
4. Specifically check whether `Volume.iterdir(recursive=True)` works;
   if so, simplify `_walk` (quirk #5).

## What is NOT in this doc

- Modal pricing. Lives in [`cloud/manifest.py`](../../cloud/manifest.py)
  `GPU_HOURLY_USD`; update there.
- Modal feature wishlist. Lives in the workstream progress docs.
- General "how to use Modal" tutorial. Modal's own docs cover this
  better; this finding doc is failure-driven.

---
*Reproduced these or found new ones? Contribution welcome via the
[finding issue template](../../.github/ISSUE_TEMPLATE/finding.md).*
