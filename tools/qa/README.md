# tools/qa/ — quality assessment toolkit

Per-render quality assessment tools for the slow-interpolation pipeline. Designed and built incrementally by the Compositing workstream (see [docs/compositing-design.md](../../docs/compositing-design.md) "Quality assessment tooling" section) but useful across the whole repo.

Subjective grading by Luca is the lock; these tools surface candidates and flag regressions so Luca's review time concentrates on the pieces that need it.

## Tools (in build order)

| # | Tool | Status | Purpose |
|---|---|---|---|
| 1 | `edge_band_sampler.py` | **v0** | For a (frame, alpha) pair, quantifies whether the figure-ground boundary reads as edge-wrap (good) or edge-slap (bad). |
| 2 | `palette_histogram.py` | not started | Per-region color-distribution check against reference Renoir / Soutine palettes. |
| 3 | `motion_continuity.py` | not started | Optical flow on final RIFE-interpolated video; flags discontinuities. |
| 4 | `gemini_judge.py` | not started | Gemini-as-rubric-judge for painterly read, palette friction, seam visibility. |
| 5 | `series_similarity.py` | not started | CLIP / DINOv2 cross-piece similarity matrix; coherence check across the release. |

Each tool reads inputs from a render output directory, writes structured JSON next to the output, and (where useful) emits a heat-map overlay PNG. A future `report.py` aggregates per-piece scores into a single review surface.

## Conventions

- Each tool is a standalone Python script with a `main()` entry point and a CLI parsable by `python -m tools.qa.<tool> --help`.
- Inputs are file paths, not Python objects. Tools do not import from `src/slow_interpolation/`.
- JSON output schema: top-level keys `tool`, `version`, `input` (paths), `metrics` (numeric), `flags` (string list of concerns), `notes` (free-form). Stable across versions; new metrics get added, never renamed.
- Heat-map overlays are PNGs at the same resolution as the input frame.

## Calibration

These tools start uncalibrated. The long-term loop:

1. Run them across a batch of renders.
2. Luca grades the same renders subjectively.
3. Compute correlation between tool scores and subjective grade.
4. Tune thresholds / reweight metrics until correlation is acceptable.
5. Use the calibrated tools to triage future batches before Luca looks.

Calibration data lives at `tools/qa/calibration/<tool>/<date>.json`.
