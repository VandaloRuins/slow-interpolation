"""Edge-band sampler. QA tool 1 of the slow-interpolation compositing toolkit.

For a rendered frame and its corresponding figure alpha matte, quantifies whether
the figure-ground boundary reads as edge-wrap (the painter's hand traveled across
the silhouette, brushstrokes cross the boundary) or edge-slap (the figure feels
pasted on top of the background).

See docs/compositing-design.md "Edge-wrap specification" for the artistic
target this tool measures against.

Usage:
    python -m tools.qa.edge_band_sampler \\
        --frame outputs/<piece>/keyframes/0042.png \\
        --alpha outputs/<piece>/alpha/0042.png \\
        --output-json outputs/<piece>/qa/edge_band_0042.json \\
        --output-overlay outputs/<piece>/qa/edge_band_0042_overlay.png

Outputs:
    JSON with metrics (edge_step, stroke_crossing_score, wrap_score) and flags.
    Optional overlay PNG: alpha contour drawn over the frame with the feather
    band tinted to show where measurements were taken.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image


TOOL_NAME = "edge_band_sampler"
TOOL_VERSION = "0.1.0"

FEATHER_LOW = 0.05
FEATHER_HIGH = 0.95


@dataclass
class RegionStats:
    n_pixels: int
    mean_rgb: tuple[float, float, float]
    std_rgb: tuple[float, float, float]

    def to_dict(self) -> dict:
        return {
            "n_pixels": int(self.n_pixels),
            "mean_rgb": [float(c) for c in self.mean_rgb],
            "std_rgb": [float(c) for c in self.std_rgb],
        }


def _region_stats(frame: np.ndarray, mask: np.ndarray) -> RegionStats:
    """Mean and std of frame RGB across the masked pixels."""
    pixels = frame[mask]
    if pixels.size == 0:
        return RegionStats(0, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    return RegionStats(
        n_pixels=pixels.shape[0],
        mean_rgb=tuple(pixels.mean(axis=0)),
        std_rgb=tuple(pixels.std(axis=0)),
    )


def _edge_step_score(
    inside: RegionStats, outside: RegionStats, feather: RegionStats
) -> float:
    """How smoothly the feather band bridges inside to outside.

    Score in [0, 1]. 1.0 means the feather mean lies exactly halfway between
    inside_core and outside_core means. 0.0 means the feather mean equals one
    of the core regions (a hard step at the contour).

    A perfect wrap would score ~1.0 IF the brushwork on both sides happens to
    differ smoothly in mean color. A deliberately contrasting Soutine inside +
    Renoir outside may score lower than 1.0 even when the wrap is artistically
    healthy, because the means are far apart by design. The companion metric
    `stroke_crossing_score` is what catches the wrap aesthetic for the
    contrasting case.
    """
    if inside.n_pixels == 0 or outside.n_pixels == 0 or feather.n_pixels == 0:
        return 0.0
    inside_arr = np.array(inside.mean_rgb)
    outside_arr = np.array(outside.mean_rgb)
    feather_arr = np.array(feather.mean_rgb)
    midpoint = 0.5 * (inside_arr + outside_arr)
    span = np.linalg.norm(inside_arr - outside_arr) + 1e-6
    distance_to_midpoint = np.linalg.norm(feather_arr - midpoint)
    return float(max(0.0, 1.0 - distance_to_midpoint / (0.5 * span + 1e-6)))


def _stroke_crossing_score(frame: np.ndarray, alpha: np.ndarray) -> float:
    """Estimate brushstroke continuity across the alpha contour.

    Computes the spatial gradient magnitude of the frame and the gradient
    magnitude of the alpha. A "good wrap" has frame gradient that does NOT
    align tightly with the alpha gradient: brushstrokes go their own direction
    across the silhouette. A "slap" has frame gradient that follows the alpha
    contour closely (the visible edge is exactly the silhouette edge).

    Score in [0, 1]: 1.0 = perpendicular gradients (independent), 0.0 =
    parallel gradients (frame edges align with alpha contour).
    """
    gray = frame.mean(axis=2)
    fy, fx = np.gradient(gray)
    ay, ax = np.gradient(alpha)
    frame_mag = np.sqrt(fx**2 + fy**2)
    alpha_mag = np.sqrt(ax**2 + ay**2)

    feather_mask = (alpha > FEATHER_LOW) & (alpha < FEATHER_HIGH)
    if feather_mask.sum() == 0:
        return 0.0

    fm = frame_mag[feather_mask]
    am = alpha_mag[feather_mask]
    if fm.std() < 1e-6 or am.std() < 1e-6:
        return 0.0

    correlation = float(np.corrcoef(fm, am)[0, 1])
    correlation = max(-1.0, min(1.0, correlation))
    return float(1.0 - 0.5 * (correlation + 1.0))


def _wrap_score(edge_step: float, stroke_crossing: float) -> float:
    """Combined wrap-quality metric.

    The contrasting-LoRA case wants stroke crossing high (independent brushwork
    across the boundary) and edge_step moderate (some color discontinuity is
    OK and expected). Weight stroke crossing twice.
    """
    return float((2.0 * stroke_crossing + edge_step) / 3.0)


def _build_overlay(frame: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Render an overlay PNG showing where measurements were taken.

    - Inside core (alpha > 0.95): unchanged.
    - Outside core (alpha < 0.05): unchanged.
    - Feather band: tinted yellow at 30% opacity.
    - Alpha = 0.5 contour: drawn in red, 1px.
    """
    overlay = frame.astype(np.float32).copy()
    feather_mask = (alpha > FEATHER_LOW) & (alpha < FEATHER_HIGH)
    tint = np.array([255.0, 230.0, 0.0])
    overlay[feather_mask] = 0.7 * overlay[feather_mask] + 0.3 * tint

    # Approximate contour: pixels where alpha crosses 0.5.
    ay, ax = np.gradient(alpha)
    grad_mag = np.sqrt(ax**2 + ay**2)
    contour_mask = (np.abs(alpha - 0.5) < 0.05) & (grad_mag > 0.01)
    overlay[contour_mask] = np.array([255.0, 30.0, 30.0])

    return overlay.clip(0, 255).astype(np.uint8)


def _flags(metrics: dict) -> list[str]:
    """Heuristic concerns to surface. Thresholds are uncalibrated v0 guesses."""
    out = []
    if metrics["stroke_crossing_score"] < 0.35:
        out.append(
            "stroke_crossing_low: frame edges align with the alpha contour; "
            "possible edge-slap (figure feels pasted on)"
        )
    if metrics["inside_core"]["n_pixels"] < 5000:
        out.append("inside_core_small: figure region tiny in this frame")
    if metrics["outside_core"]["n_pixels"] < 5000:
        out.append("outside_core_small: background region tiny in this frame")
    if metrics["feather_band"]["n_pixels"] < 200:
        out.append(
            "feather_band_narrow: alpha matte is nearly binary; feather radius "
            "may be too small for wrap aesthetic"
        )
    return out


def analyze(frame_path: Path, alpha_path: Path) -> dict:
    """Run the analysis. Returns a dict matching the tools/qa JSON schema."""
    frame_img = Image.open(frame_path).convert("RGB")
    alpha_img = Image.open(alpha_path).convert("L")
    if frame_img.size != alpha_img.size:
        alpha_img = alpha_img.resize(frame_img.size, Image.BILINEAR)

    frame = np.array(frame_img).astype(np.float32)
    alpha = np.array(alpha_img).astype(np.float32) / 255.0

    inside_mask = alpha >= FEATHER_HIGH
    outside_mask = alpha <= FEATHER_LOW
    feather_mask = (alpha > FEATHER_LOW) & (alpha < FEATHER_HIGH)

    inside = _region_stats(frame, inside_mask)
    outside = _region_stats(frame, outside_mask)
    feather = _region_stats(frame, feather_mask)

    edge_step = _edge_step_score(inside, outside, feather)
    stroke_crossing = _stroke_crossing_score(frame, alpha)
    wrap = _wrap_score(edge_step, stroke_crossing)

    metrics = {
        "edge_step_score": edge_step,
        "stroke_crossing_score": stroke_crossing,
        "wrap_score": wrap,
        "inside_core": inside.to_dict(),
        "outside_core": outside.to_dict(),
        "feather_band": feather.to_dict(),
    }

    return {
        "tool": TOOL_NAME,
        "version": TOOL_VERSION,
        "input": {
            "frame": str(frame_path),
            "alpha": str(alpha_path),
        },
        "metrics": metrics,
        "flags": _flags(metrics),
        "notes": (
            "v0 thresholds are uncalibrated. Run a batch across known-good and "
            "known-bad renders, then tune in tools/qa/calibration/edge_band_sampler/."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame", required=True, type=Path)
    parser.add_argument("--alpha", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-overlay", type=Path, default=None)
    args = parser.parse_args()

    result = analyze(args.frame, args.alpha)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2))

    if args.output_overlay is not None:
        frame = np.array(Image.open(args.frame).convert("RGB")).astype(np.float32)
        alpha_img = Image.open(args.alpha).convert("L")
        if alpha_img.size != (frame.shape[1], frame.shape[0]):
            alpha_img = alpha_img.resize((frame.shape[1], frame.shape[0]), Image.BILINEAR)
        alpha = np.array(alpha_img).astype(np.float32) / 255.0
        overlay = _build_overlay(frame, alpha)
        args.output_overlay.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(overlay).save(args.output_overlay)

    print(
        f"wrap_score={result['metrics']['wrap_score']:.3f} "
        f"edge_step={result['metrics']['edge_step_score']:.3f} "
        f"stroke_crossing={result['metrics']['stroke_crossing_score']:.3f}"
    )


if __name__ == "__main__":
    main()
