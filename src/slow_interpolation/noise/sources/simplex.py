"""Simplex noise as a NoiseSource.

Visual reading: similar to Perlin (smooth, blob-like) but on a triangular
lattice. Subjectively, less axis-aligned than Perlin and slightly more
"flowing". The harness will tell us whether the diffusion model actually
distinguishes them; if it doesn't, Perlin is the cheaper default.

Parameters mirror `PerlinNoise`:

- `feature_size`: side of one lattice cell in pixels. Default 64.
- `walk_rate`: temporal blend rate.
"""

from __future__ import annotations

import numpy as np

from ..base import WalkingNoiseSource
from ._kernels import simplex_2d


class SimplexNoise(WalkingNoiseSource):
    """2D simplex noise."""

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
            simplex_2d(height, width, self.feature_size, self._rng)
            for _ in range(channels)
        ]
        return np.stack(planes, axis=-1) if channels > 1 else planes[0][..., None]
