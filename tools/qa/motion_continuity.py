"""Motion-continuity check. QA tool 3 of the slow-interpolation toolkit.

Runs dense optical flow (Farneback) across a rendered MP4 and flags frames
where the flow magnitude or direction discontinuously breaks. The signal we
are watching for:

- **Discontinuity spikes**: frame-pair flow magnitude jumps by N-sigma over
  the rolling median. Indicates a SDXL keyframe insertion that did not
  interpolate smoothly, a RIFE collapse, or an encoder cut.
- **Direction reversals**: the dominant flow direction flips between
  adjacent pairs. Could indicate a tracking failure mid-loop.
- **Stall + jerk**: long runs of near-zero flow followed by a sudden burst.
  The deceleration-pause failure the legacy work spent months hunting.

These are diagnostic flags, not gradings. The artistic intent of
slow-interpolation IS very slow flow; the tool's job is to catch
discontinuities inside that slow drift, not to penalize slow drift itself.

Usage:
    python -m tools.qa.motion_continuity \\
        --video outputs/<piece>/<piece>.mp4 \\
        --output-json outputs/<piece>/qa/motion_continuity.json \\
        --output-plot outputs/<piece>/qa/motion_continuity_plot.png

The plot, if requested, shows per-frame flow magnitude over time with the
flagged frames marked.

OpenCV is required (`pip install opencv-python`). For a Modal-only future,
this same script can run inside the existing encoder image.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

TOOL_NAME = "motion_continuity"
TOOL_VERSION = "0.1.0"

DEFAULT_DOWNSCALE = 4
DEFAULT_SPIKE_SIGMA = 4.0
DEFAULT_STALL_FRACTION = 0.05


@dataclass
class FrameMetric:
    frame_idx: int
    flow_mag_mean: float
    flow_mag_p95: float
    dominant_angle_deg: float

    def to_dict(self) -> dict:
        return {
            "frame_idx": int(self.frame_idx),
            "flow_mag_mean": float(self.flow_mag_mean),
            "flow_mag_p95": float(self.flow_mag_p95),
            "dominant_angle_deg": float(self.dominant_angle_deg),
        }


def _read_frames_iter(path: Path, downscale: int):
    """Yield (frame_idx, grayscale ndarray) tuples downscaled by N."""
    import cv2

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video {path}")
    idx = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if downscale > 1:
                gray = cv2.resize(
                    gray,
                    (gray.shape[1] // downscale, gray.shape[0] // downscale),
                    interpolation=cv2.INTER_AREA,
                )
            yield idx, gray
            idx += 1
    finally:
        cap.release()


def _farneback_flow(prev_gray, curr_gray):
    import cv2

    return cv2.calcOpticalFlowFarneback(
        prev_gray,
        curr_gray,
        flow=None,
        pyr_scale=0.5,
        levels=3,
        winsize=15,
        iterations=3,
        poly_n=5,
        poly_sigma=1.2,
        flags=0,
    )


def _frame_metric(idx: int, flow: np.ndarray) -> FrameMetric:
    fx, fy = flow[..., 0], flow[..., 1]
    mag = np.sqrt(fx**2 + fy**2)
    angle = np.arctan2(fy, fx)
    flat_mag = mag.flatten()
    dominant_angle = float(np.angle(np.mean(np.exp(1j * angle))))
    return FrameMetric(
        frame_idx=idx,
        flow_mag_mean=float(flat_mag.mean()),
        flow_mag_p95=float(np.quantile(flat_mag, 0.95)),
        dominant_angle_deg=float(np.degrees(dominant_angle)),
    )


def _flag_spikes(metrics: list[FrameMetric], sigma: float) -> list[int]:
    """Find frames whose flow magnitude jumps N-sigma over rolling median."""
    if len(metrics) < 10:
        return []
    mags = np.array([m.flow_mag_mean for m in metrics])
    window = 11
    pad = window // 2
    padded = np.pad(mags, pad, mode="edge")
    rolling_med = np.array(
        [np.median(padded[i : i + window]) for i in range(len(mags))]
    )
    deltas = np.abs(mags - rolling_med)
    if deltas.std() < 1e-6:
        return []
    threshold = deltas.mean() + sigma * deltas.std()
    return [int(i) for i in np.where(deltas > threshold)[0]]


def _flag_stalls(metrics: list[FrameMetric], frac: float) -> list[int]:
    """Flag frames with flow magnitude in the bottom N%."""
    if len(metrics) < 10:
        return []
    mags = np.array([m.flow_mag_mean for m in metrics])
    threshold = np.quantile(mags, frac)
    return [int(i) for i in np.where(mags <= threshold)[0]]


def _flag_direction_reversals(metrics: list[FrameMetric]) -> list[int]:
    """Flag frame indices where dominant angle flips > 90 degrees."""
    if len(metrics) < 3:
        return []
    angles = np.array([m.dominant_angle_deg for m in metrics])
    flagged = []
    for i in range(1, len(angles)):
        delta = abs(angles[i] - angles[i - 1])
        delta = min(delta, 360 - delta)
        if delta > 90:
            flagged.append(i)
    return flagged


def _build_plot(metrics: list[FrameMetric], flags: dict, out_path: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return
    idx = [m.frame_idx for m in metrics]
    mag = [m.flow_mag_mean for m in metrics]
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(idx, mag, lw=0.8, color="#666666", label="flow mag mean")
    for label, indices, color in [
        ("spike", flags["spikes"], "#cc3333"),
        ("stall", flags["stalls"], "#3366cc"),
        ("reversal", flags["direction_reversals"], "#cc8833"),
    ]:
        if indices:
            ax.scatter(
                [idx[i] for i in indices],
                [mag[i] for i in indices],
                s=18,
                c=color,
                label=label,
                zorder=3,
            )
    ax.set_xlabel("frame index")
    ax.set_ylabel("optical flow magnitude (mean)")
    ax.set_title("Motion continuity")
    ax.legend(loc="upper right")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def analyze(video_path: Path, downscale: int, spike_sigma: float, stall_frac: float) -> dict:
    """Run flow analysis on the video. Returns the QA JSON dict."""
    metrics: list[FrameMetric] = []
    prev = None
    for idx, gray in _read_frames_iter(video_path, downscale):
        if prev is None:
            prev = gray
            continue
        flow = _farneback_flow(prev, gray)
        metrics.append(_frame_metric(idx, flow))
        prev = gray

    spikes = _flag_spikes(metrics, spike_sigma)
    stalls = _flag_stalls(metrics, stall_frac)
    reversals = _flag_direction_reversals(metrics)

    overall_mean = float(np.mean([m.flow_mag_mean for m in metrics])) if metrics else 0.0
    overall_p95 = float(np.mean([m.flow_mag_p95 for m in metrics])) if metrics else 0.0

    flags = []
    if len(spikes) > max(2, len(metrics) // 200):
        flags.append(
            f"many_spikes: {len(spikes)} frames flag as flow-magnitude spikes "
            f"(>{spike_sigma}-sigma). Possible keyframe insertion artifacts."
        )
    if len(reversals) > max(2, len(metrics) // 100):
        flags.append(
            f"frequent_direction_reversals: {len(reversals)} frames flip flow "
            f"direction by more than 90 degrees. Possible RIFE failure."
        )
    if overall_mean < 0.02:
        flags.append(
            "very_low_motion: average flow magnitude near zero. Either the "
            "render is genuinely stationary (which is allowed in this work) "
            "or the optical flow estimator failed."
        )

    return {
        "tool": TOOL_NAME,
        "version": TOOL_VERSION,
        "input": {"video": str(video_path)},
        "params": {
            "downscale": downscale,
            "spike_sigma": spike_sigma,
            "stall_frac": stall_frac,
        },
        "summary": {
            "n_frame_pairs": len(metrics),
            "flow_mag_mean_overall": overall_mean,
            "flow_mag_p95_overall": overall_p95,
            "n_spikes": len(spikes),
            "n_stalls": len(stalls),
            "n_direction_reversals": len(reversals),
        },
        "spike_frames": spikes,
        "stall_frames": stalls,
        "reversal_frames": reversals,
        "per_frame": [m.to_dict() for m in metrics],
        "flags": flags,
        "notes": (
            "Slow-interpolation is supposed to be slow; very-low-motion is "
            "expected and not a failure mode. Spike count is the most "
            "actionable signal."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-plot", type=Path, default=None)
    parser.add_argument("--downscale", type=int, default=DEFAULT_DOWNSCALE)
    parser.add_argument("--spike-sigma", type=float, default=DEFAULT_SPIKE_SIGMA)
    parser.add_argument("--stall-frac", type=float, default=DEFAULT_STALL_FRACTION)
    args = parser.parse_args()

    result = analyze(args.video, args.downscale, args.spike_sigma, args.stall_frac)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2))

    if args.output_plot is not None:
        flag_payload = {
            "spikes": result["spike_frames"],
            "stalls": result["stall_frames"],
            "direction_reversals": result["reversal_frames"],
        }
        # Rebuild a thin metrics list for the plot
        metrics = [
            FrameMetric(
                frame_idx=m["frame_idx"],
                flow_mag_mean=m["flow_mag_mean"],
                flow_mag_p95=m["flow_mag_p95"],
                dominant_angle_deg=m["dominant_angle_deg"],
            )
            for m in result["per_frame"]
        ]
        _build_plot(metrics, flag_payload, args.output_plot)

    s = result["summary"]
    print(
        f"frames={s['n_frame_pairs']} mean_flow={s['flow_mag_mean_overall']:.3f} "
        f"spikes={s['n_spikes']} stalls={s['n_stalls']} reversals={s['n_direction_reversals']}"
    )


if __name__ == "__main__":
    main()
