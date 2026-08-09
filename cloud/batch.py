"""Batch render fan-out via Modal's `Function.map()`.

Dispatches N configs in parallel on N containers. Per-container GPU
billing is the same as serial dispatch, so cost is identical but wall
time collapses from sum(individual) to ~max(individual).

Best for fire-and-forget batches (release-day "render all 7 Renoir
subjects"). For sequential dispatch with human-in-the-loop iteration,
see `cloud/release_batch.py` (T3#12) which adds an opt-in warm-pool.

Usage:

    # Render every YAML matching a glob.
    modal run -m cloud.batch --configs "examples/configs/renoir/*.yaml"

    # Render an explicit comma-separated list.
    modal run -m cloud.batch --configs "a.yaml,b.yaml,c.yaml"

    # Override GPU for the whole batch.
    modal run -m cloud.batch --configs "..." --gpu A100-40GB

Note: Modal's `Function.map()` accepts a single shared `kwargs` dict,
not per-call kwargs. So configs that share (gpu_tier, pipeline_entry,
config_loader) batch into one `.map()` call; configs with different
overrides are grouped and dispatched per-group. Typical batches use
one group.
"""

from __future__ import annotations

import glob
import time
from pathlib import Path
from typing import Any

import yaml

from .app import (
    DEFAULT_CONFIG_LOADER,
    DEFAULT_GPU,
    DEFAULT_PIPELINE_ENTRY,
    OUTPUTS_VOLUME_NAME,
    app,
    resolve_render_fn,
)
from .manifest import resolve_git_commit


KNOWN_MODAL_KEYS = {"gpu", "pipeline_entry", "config_loader", "notes",
                    "preserve_staging", "skip_keyframes"}


@app.local_entrypoint()
def main(
    configs: str,
    gpu: str | None = None,
    pipeline_entry: str | None = None,
    config_loader: str | None = None,
) -> None:
    """Fan out a batch of configs across N parallel containers.

    Args:
        configs: glob pattern (e.g. "examples/configs/renoir/*.yaml") OR
            comma-separated explicit paths.
        gpu: GPU tier override applied to every config in the batch.
            Overrides per-config `modal.gpu` if both present.
        pipeline_entry: dotted-path override applied to every config.
        config_loader: dotted-path override applied to every config.
    """
    paths = _resolve_paths(configs)
    if not paths:
        raise SystemExit(f"No configs matched: {configs!r}")

    repo_root = Path(__file__).resolve().parent.parent
    git_commit, git_dirty = resolve_git_commit(repo_root)

    # Read each config and resolve its (gpu_tier, pipeline_entry,
    # config_loader) triple. CLI flags override YAML modal section;
    # YAML modal section overrides defaults.
    entries: list[dict[str, Any]] = []
    for p in paths:
        yaml_text = p.read_text(encoding="utf-8")
        raw = yaml.safe_load(yaml_text)
        modal_section: dict[str, Any] = dict(raw.get("modal") or {})

        entries.append(
            {
                "label": p.stem,
                "yaml_text": yaml_text,
                "gpu_tier": gpu or modal_section.get("gpu") or DEFAULT_GPU,
                "pipeline_entry": (
                    pipeline_entry
                    or modal_section.get("pipeline_entry")
                    or DEFAULT_PIPELINE_ENTRY
                ),
                "config_loader": (
                    config_loader
                    or modal_section.get("config_loader")
                    or DEFAULT_CONFIG_LOADER
                ),
                "preserve_staging": bool(modal_section.get("preserve_staging", False)),
                "skip_keyframes": bool(modal_section.get("skip_keyframes", False)),
            }
        )

    print(f"[batch] configs:        {len(paths)}")
    print(f"[batch] git commit:     {git_commit}{' (dirty)' if git_dirty else ''}")
    for e in entries:
        print(f"  - {e['label']}  gpu={e['gpu_tier']}  entry={e['pipeline_entry']}")

    # Group by (gpu_tier, pipeline_entry, config_loader, preserve_staging,
    # skip_keyframes). Every one of these lands in the shared kwargs dict
    # that Function.map broadcasts, so any of them differing must split
    # the batch into separate .map() calls (SDK quirk #9).
    # Each group becomes one .map() call (Modal's map can only share one
    # kwargs dict across the batch).
    groups: dict[tuple[str, str, str, bool], list[dict[str, Any]]] = {}
    for e in entries:
        key = (
            e["gpu_tier"],
            e["pipeline_entry"],
            e["config_loader"],
            e["preserve_staging"],
            e["skip_keyframes"],
        )
        groups.setdefault(key, []).append(e)

    print()
    print(f"[batch] groups: {len(groups)} (one .map() per group)")
    print("[batch] dispatching...")
    print()

    t0 = time.perf_counter()
    results: list[tuple[str, dict[str, Any] | Exception]] = []

    for (gpu_tier, p_entry, c_loader, preserve_staging, skip_keyframes), group in groups.items():
        fn = resolve_render_fn(gpu_tier)
        labels = [e["label"] for e in group]
        yaml_texts = [e["yaml_text"] for e in group]

        # All members of the group share these kwargs.
        shared_kwargs = {
            "gpu_tier": gpu_tier,
            "pipeline_entry": p_entry,
            "config_loader": c_loader,
            "git_commit": git_commit,
            "git_dirty": git_dirty,
            "notes": [f"BATCH RUN (group gpu={gpu_tier})"],
            "preserve_staging": preserve_staging,
            "skip_keyframes": skip_keyframes,
        }

        try:
            outs = list(
                fn.map(
                    yaml_texts,
                    kwargs=shared_kwargs,
                    return_exceptions=True,
                )
            )
        except Exception as exc:
            # Whole-group infra error.
            outs = [exc] * len(group)

        for label, out in zip(labels, outs):
            results.append((label, out))

    total = time.perf_counter() - t0
    _print_summary(results, total)


def _resolve_paths(configs: str) -> list[Path]:
    """Resolve a glob OR a comma-separated list into a list of Paths."""
    if "," in configs:
        paths = [Path(p.strip()) for p in configs.split(",") if p.strip()]
    else:
        matches = glob.glob(configs, recursive=True)
        paths = [Path(m) for m in matches]
    return sorted({p.resolve() for p in paths if p.exists()})


def _print_summary(
    results: list[tuple[str, dict[str, Any] | Exception]],
    total_seconds: float,
) -> None:
    print()
    print("=" * 70)
    print("BATCH SUMMARY")
    print("=" * 70)

    successes = [(lbl, r) for lbl, r in results if not isinstance(r, Exception)]
    failures = [(lbl, r) for lbl, r in results if isinstance(r, Exception)]

    total_cost = sum(r["estimated_cost_usd"] for _, r in successes)
    total_render_seconds = sum(r["total_seconds"] for _, r in successes)

    print(f"  wall (parallel):   {total_seconds:.1f}s")
    print(f"  GPU-seconds sum:   {total_render_seconds:.1f}s")
    if total_render_seconds > 0:
        print(f"  parallel speedup:  {total_render_seconds / total_seconds:.1f}x")
    print(f"  total cost:        {total_cost:.4f} USD")
    print(f"  successes:         {len(successes)}/{len(results)}")
    print()

    if successes:
        print("  outputs (in slow-interp-outputs volume):")
        for label, r in successes:
            print(
                f"    {label}: {r['output_path']}  "
                f"({r['total_seconds']:.1f}s, {r['estimated_cost_usd']:.4f} USD)"
            )
        print()

    if failures:
        print("  failures:")
        for label, exc in failures:
            print(f"    {label}: {exc!r}")
        print()

    print("  download all MP4s with:")
    print(f"    modal volume get {OUTPUTS_VOLUME_NAME} / ./outputs/from-modal/")
    print("=" * 70)
