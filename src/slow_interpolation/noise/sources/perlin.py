"""Perlin gradient noise as a NoiseSource.

Visual reading: smooth, organic, low spatial frequency, blob-like. On the
SDXL-Lightning img2img chain it reads (anecdotally, to be validated by the
harness) as soft brushwork: large coherent regions of noise push the model
toward broader colour patches rather than per-pixel jitter. Useful as a
candidate for impressionist / fresco subjects.

Parameters:

- `feature_size`: side of one grid cell in pixels. Default 64 means coarse
  structures (very smooth, blob-like). Smaller values increase spatial
  frequency. A reasonable range to sweep is 16 to 128.
- `walk_rate`: temporal blend rate, inherited from `WalkingNoiseSource`.

The three RGB channels are decorrelated by drawing independent gradient grids
per channel. This avoids the "coloured plate" look that would happen with a
single channel replicated.
"""

from __future__ import annotations

import numpy as np

from ..base import WalkingNoiseSource
from ._kernels import perlin_2d


class PerlinNoise(WalkingNoiseSource):
    """Perlin gradient noise. One octave; for multi-octave see `FBMNoise`."""

    def __init__(
        self,
        feature_size: float = 64.0,
        walk_rate: float = 0.05,
        pixel_spread: float = 40.0,
        pixel_center: float = 128.0,
        seed: int | None = None,
    ) -> None:
        super().__init__(
            walk_rate=walk_rate,
            pixel_spread=pixel_spread,
            pixel_center=pixel_center,
        )
        self.feature_size = float(feature_size)
        self._rng = np.random.default_rng(seed)

    def _generate_fresh(self, shape: tuple[int, ...]) -> np.ndarray:
        height, width = shape[0], shape[1]
        channels = shape[2] if len(shape) == 3 else 1
        planes = [
            perlin_2d(height, width, self.feature_size, self._rng)
            for _ in range(channels)
        ]
        return np.stack(planes, axis=-1) if channels > 1 else planes[0][..., None]
