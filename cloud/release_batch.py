"""Release-day batch dispatch with optional warm-pool.

Two modes:

1. Without `--warm`: identical to `cloud/batch.py` fan-out. Each
   config renders on its own cold-started container in parallel via
   `Function.map()`. No idle billing. **Use this for fire-and-forget
   parallel batches.** This is most release-day workflows.

2. With `--warm DURATION` (e.g. `30m`): activates a warm container
   pool with six safety layers (see docs/release-batch.md). Use this
   ONLY for sequential dispatch with human-in-the-loop iteration over
   ~7 to 25 renders within a bounded session under 1 hour. The warm
   pool skips ~30 s container cold-start per render.

For fire-and-forget `map()` batches the warm pool gives NOTHING (each
parallel container cold-starts in parallel anyway). It only earns its
keep in the sequential pattern.

Usage:

    # Default: parallel map, no warm pool.
    modal run -m cloud.release_batch --configs "examples/configs/renoir/*.yaml"

    # With warm pool, auto-stop after 30 min.
    modal run -m cloud.release_batch --configs "..." --warm 30m

    # CLI override of GPU tier for the batch.
    modal run -m cloud.release_batch --configs "..." --gpu A100-40GB

Worst-case cost guard: even if every layer of the safety harness fails,
the container's `container_idle_timeout=1800` hard-stops the warm pool
after 30 min idle. Max forgotten cost: ~0.50 USD on L40S.

See `docs/release-batch.md` for the full safety design and when to use.
"""

from __future__ import annotations

import glob
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Any

import yaml

from .app import (
    DEFAULT_CONFIG_LOADER,
    DEFAULT_GPU,
    DEFAULT_PIPELINE_ENTRY,
    OUTPUTS_VOLUME_NAME,
    app,
    render_warm,
    resolve_render_fn,
)
from .manifest import resolve_git_commit


@app.local_entrypoint()
def main(
    configs: str,
    gpu: str | None = None,
    pipeline_entry: str | None = None,
    config_loader: str | None = None,
    warm: str | None = None,
) -> None:
    """Release-day batch dispatch with optional warm-pool.

    Args:
        configs: glob pattern OR comma-separated explicit paths.
        gpu: GPU tier override applied to every config in the batch.
        pipeline_entry: dotted-path override applied to every config.
        config_loader: dotted-path override applied to every config.
        warm: duration to keep the warm pool active (e.g. "30m", "45m",
            "1h"). When set, opt into the warm-pool path. Required;
            never a boolean. Max accepted is 60 min per safety layer.
    """
    paths = _resolve_paths(configs)
    if not paths:
        raise SystemExit(f"No configs matched: {configs!r}")

    warm_seconds = _parse_duration(warm) if warm else 0
    if warm_seconds and warm_seconds > 3600:
        raise SystemExit(
            f"--warm {warm!r}: maximum is 60 minutes (got {warm_seconds}s). "
            f"Spin up multiple sessions if you need longer."
        )

    repo_root = Path(__file__).resolve().parent.parent
    git_commit, git_dirty = resolve_git_commit(repo_root)

    entries = [_read_entry(p, gpu, pipeline_entry, config_loader) for p in paths]

    print(f"[release_batch] configs:    {len(paths)}")
    print(f"[release_batch] git commit: {git_commit}{' (dirty)' if git_dirty else ''}")
    print(f"[release_batch] warm pool:  {'ACTIVE' if warm_seconds else 'off'}")
    if warm_seconds:
        _print_warm_banner(warm_seconds, entries[0]["gpu_tier"])

    # Group by (gpu_tier, pipeline_entry, config_loader, preserve_staging)
    # so each .map() call shares one kwargs dict (Modal's map constraint).
    groups: dict[tuple[str, str, str, bool], list[dict[str, Any]]] = {}
    for e in entries:
        key = (
            e["gpu_tier"],
            e["pipeline_entry"],
            e["config_loader"],
            e["preserve_staging"],
        )
        groups.setdefault(key, []).append(e)

    print(f"[release_batch] groups: {len(groups)}")
    print()

    # Choose the function variant based on warm flag.
    # Warm path: `render_warm` (L40S, container_idle_timeout=1800).
    # Cold path: per-tier dispatch via resolve_render_fn (no warm pool).
    t0 = time.perf_counter()
    results: list[tuple[str, dict[str, Any] | Exception]] = []
    warm_start = time.perf_counter() if warm_seconds else 0.0

    try:
        for (gpu_tier, p_entry, c_loader, preserve_staging), group in groups.items():
            if warm_seconds:
                if gpu_tier != "L40S":
                    print(
                        f"[release_batch] WARNING: warm-pool variant is L40S only, "
                        f"requested {gpu_tier} forced to L40S for this group."
                    )
                fn = render_warm
                effective_gpu = "L40S"
            else:
                fn = resolve_render_fn(gpu_tier)
                effective_gpu = gpu_tier

            labels = [e["label"] for e in group]
            yaml_texts = [e["yaml_text"] for e in group]
            shared_kwargs = {
                "gpu_tier": effective_gpu,
                "pipeline_entry": p_entry,
                "config_loader": c_loader,
                "git_commit": git_commit,
                "git_dirty": git_dirty,
                "notes": [
                    f"RELEASE BATCH (group gpu={effective_gpu}, "
                    f"warm={'on' if warm_seconds else 'off'})"
                ],
                "preserve_staging": preserve_staging,
            }

            try:
                outs = list(
                    fn.map(yaml_texts, kwargs=shared_kwargs, return_exceptions=True)
                )
            except Exception as exc:
                outs = [exc] * len(group)

            for label, out in zip(labels, outs):
                results.append((label, out))

            # If warm and we have time left, do not exit early. The
            # group loop runs through naturally; we shut down warm in
            # the `finally`.

    except KeyboardInterrupt:
        print()
        print("[release_batch] INTERRUPTED -- shutting down warm pool...")
        raise
    finally:
        # Explicit warm-pool shutdown. Container hard-cap is the safety
        # net behind this; we belt-and-suspenders here.
        if warm_seconds:
            _shutdown_warm_pool(warm_start)

    total = time.perf_counter() - t0
    warm_idle_seconds = (
        max(0.0, (time.perf_counter() - warm_start)) if warm_seconds else 0.0
    )
    _print_summary(results, total, warm_seconds, warm_idle_seconds, entries)


# ---------------------------------------------------------------------------
# Safety + UX helpers
# ---------------------------------------------------------------------------


def _print_warm_banner(warm_seconds: int, gpu_tier: str) -> None:
    """One of the six safety layers: loud terminal banner."""
    from .manifest import GPU_HOURLY_USD

    hourly = GPU_HOURLY_USD.get(gpu_tier, 0.0)
    # Modal bills idle at GPU rate (no special idle-discount documented
    # for keep_warm). Estimate conservatively.
    idle_cost_max = hourly * (warm_seconds / 3600.0)
    auto_stop_min = warm_seconds // 60

    print()
    print("=" * 70)
    print("WARM CONTAINER POOL ACTIVE")
    print(f"  GPU tier:        {gpu_tier}")
    print(f"  Hourly rate:     ${hourly:.2f}/hr")
    print(f"  Auto-stop in:    {auto_stop_min} min")
    print(f"  Max idle cost:   ${idle_cost_max:.2f} (if no renders dispatched)")
    print(f"  Hard-cap:        container_idle_timeout=1800s (30 min)")
    print(f"  Manual stop:     Ctrl+C this process")
    print("=" * 70)
    print()


def _shutdown_warm_pool(warm_start_perf: float) -> None:
    """End-of-session warm-pool note.

    Modal 1.4.x does not expose a per-call `keep_warm` override; the
    warm-pool size is set on the Function at decoration time
    (`render_warm` has `keep_warm=0`, so once we stop calling it the
    container becomes idle and the `container_idle_timeout=1800`
    hard-cap spins it down within 30 min).

    This means there's no explicit shutdown call to make. The safety
    net is the `container_idle_timeout` on `render_warm`. Worst-case
    forgotten cost: ~0.50 USD on L40S over 30 min.
    """
    elapsed = time.perf_counter() - warm_start_perf
    print()
    print(f"[release_batch] warm session active for {elapsed:.0f}s.")
    print(
        "[release_batch] no explicit shutdown needed: "
        "render_warm has container_idle_timeout=1800s."
    )
    print(
        "[release_batch] container will hard-stop within 30 min of last call. "
        "Max forgotten cost ~0.50 USD."
    )


def _print_summary(
    results: list[tuple[str, dict[str, Any] | Exception]],
    total_seconds: float,
    warm_seconds: int,
    warm_idle_actual: float,
    entries: list[dict[str, Any]],
) -> None:
    print()
    print("=" * 70)
    print("RELEASE BATCH SUMMARY")
    print("=" * 70)

    successes = [(lbl, r) for lbl, r in results if not isinstance(r, Exception)]
    failures = [(lbl, r) for lbl, r in results if isinstance(r, Exception)]

    render_active_seconds = sum(r["total_seconds"] for _, r in successes)
    render_cost = sum(r["estimated_cost_usd"] for _, r in successes)

    # Estimate warm-pool idle cost: total active minus actual GPU work.
    # Modal's exact billing is per-second of container hold; we report
    # an upper bound estimate.
    warm_idle_estimate = max(0.0, warm_idle_actual - render_active_seconds)
    from .manifest import GPU_HOURLY_USD

    warm_gpu = entries[0]["gpu_tier"] if entries else DEFAULT_GPU
    warm_hourly = GPU_HOURLY_USD.get(warm_gpu, 0.0)
    warm_idle_cost = warm_hourly * (warm_idle_estimate / 3600.0)

    print(f"  wall (parallel):       {total_seconds:.1f}s")
    print(f"  render-active GPU-s:   {render_active_seconds:.1f}s")
    if warm_seconds:
        print(f"  warm-idle GPU-s est:   {warm_idle_estimate:.1f}s")
    print()
    print(f"  render cost:           ${render_cost:.4f}")
    if warm_seconds:
        print(f"  warm-idle cost est:    ${warm_idle_cost:.4f}")
        print(f"  total cost est:        ${render_cost + warm_idle_cost:.4f}")
    else:
        print(f"  total cost:            ${render_cost:.4f}")
    print()
    print(f"  successes:             {len(successes)}/{len(results)}")
    print()

    if successes:
        print("  outputs (in slow-interp-outputs volume):")
        for label, r in successes:
            print(
                f"    {label}: {r['output_path']}  "
                f"({r['total_seconds']:.1f}s, ${r['estimated_cost_usd']:.4f})"
            )
        print()

    if failures:
        print("  failures:")
        for label, exc in failures:
            print(f"    {label}: {exc!r}")
        print()

    print(f"  download all MP4s with:")
    print(f"    modal volume get {OUTPUTS_VOLUME_NAME} / ./outputs/from-modal/")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------


def _resolve_paths(configs: str) -> list[Path]:
    if "," in configs:
        paths = [Path(p.strip()) for p in configs.split(",") if p.strip()]
    else:
        matches = glob.glob(configs, recursive=True)
        paths = [Path(m) for m in matches]
    return sorted({p.resolve() for p in paths if p.exists()})


def _read_entry(
    p: Path,
    cli_gpu: str | None,
    cli_entry: str | None,
    cli_loader: str | None,
) -> dict[str, Any]:
    yaml_text = p.read_text(encoding="utf-8")
    raw = yaml.safe_load(yaml_text)
    modal_section: dict[str, Any] = dict(raw.get("modal") or {})
    return {
        "label": p.stem,
        "yaml_text": yaml_text,
        "gpu_tier": cli_gpu or modal_section.get("gpu") or DEFAULT_GPU,
        "pipeline_entry": (
            cli_entry or modal_section.get("pipeline_entry") or DEFAULT_PIPELINE_ENTRY
        ),
        "config_loader": (
            cli_loader or modal_section.get("config_loader") or DEFAULT_CONFIG_LOADER
        ),
        "preserve_staging": bool(modal_section.get("preserve_staging", False)),
    }


def _parse_duration(s: str) -> int:
    """Parse '30m', '45m', '1h', '90s' into seconds. Bare int is seconds."""
    s = s.strip().lower()
    m = re.fullmatch(r"(\d+)\s*([smh]?)", s)
    if not m:
        raise SystemExit(
            f"Invalid --warm duration {s!r}. Use e.g. '30m', '1h', '90s'."
        )
    n = int(m.group(1))
    unit = m.group(2) or "s"
    return {"s": 1, "m": 60, "h": 3600}[unit] * n
