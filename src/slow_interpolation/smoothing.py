"""Phase A.5: frequency-separated temporal smoothing.

Each keyframe is decomposed into a low-frequency component (Gaussian blur of
`blur_radius` pixels) and a high-frequency residual. Only the low-frequency
band is temporally smoothed across a window of +/- `window` frames with
Gaussian weights of `sigma`. The smoothed low-frequency is recombined with the
**center frame's own** high-frequency, so per-frame sharpness and brushwork are
preserved while inter-frame composition jitter is removed.

Earlier naive temporal averages produced ghosting; this two-band split is what
made the smoother safe to run on a keyframe sequence (see
`legacy/choire-v2/research/video-pipeline-best.md`).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


def temporal_smooth_keyframes(
    kf_dir: Path,
    sigma: float = 1.5,
    window: int = 8,
    blur_radius: int = 16,
) -> None:
    """Smooth every PNG in `kf_dir` in place using a frequency-separated blend
    across +/- `window` neighboring frames.
    """
    paths = sorted(kf_dir.glob("*.png"))
    if len(paths) < 3:
        return

    images = [np.array(Image.open(p)).astype(np.float32) for p in paths]

    lows = []
    highs = []
    for img_arr in images:
        pil_img = Image.fromarray(img_arr.astype(np.uint8))
        low = np.array(pil_img.filter(ImageFilter.GaussianBlur(radius=blur_radius))).astype(
            np.float32
        )
        high = img_arr - low
        lows.append(low)
        highs.append(high)

    smoothed: list[np.ndarray] = []
    for i in range(len(images)):
        lo_idx = max(0, i - window)
        hi_idx = min(len(images), i + window + 1)
        weights: list[float] = []
        frames: list[np.ndarray] = []
        for j in range(lo_idx, hi_idx):
            w = float(np.exp(-0.5 * ((j - i) / sigma) ** 2))
            weights.append(w)
            frames.append(lows[j])
        total_w = sum(weights)
        smoothed_low = sum((w / total_w) * f for w, f in zip(weights, frames))
        recombined = smoothed_low + highs[i]
        smoothed.append(recombined.clip(0, 255).astype(np.uint8))

    for path, arr in zip(paths, smoothed):
        Image.fromarray(arr).save(path)
