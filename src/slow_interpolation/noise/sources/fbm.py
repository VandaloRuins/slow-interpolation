"""Fractional Brownian Motion (multi-octave Perlin) as a NoiseSource.

Visual reading: cloud-like. Stacks several octaves of Perlin noise with
geometrically decreasing amplitude and increasing frequency, producing a
self-similar texture with detail at multiple scales. Strong candidate for
atmospheric / landscape subjects where the existing noise feels too flat or
too crisp.

Parameters:

- `feature_size`: side of the base (lowest-frequency) cell in pixels. Default
  128.
- `octaves`: number of octaves to sum. Default 4. More octaves = more fine
  detail and more compute. Diminishing returns after ~6.
- `persistence`: amplitude falloff per octave. 0.5 = each octave half as loud
  as the prior. Higher = more high-frequency energy.
- `lacunarity`: frequency growth per octave. 2.0 = each octave twice the
  frequency of the prior.
- `walk_rate`: temporal blend rate.
"""

from __future__ import annotations

import numpy as np

from ..base import WalkingNoiseSource
from ._kernels import fbm_2d


class FBMNoise(WalkingNoiseSource):
    """Fractional Brownian Motion over Perlin gradient noise."""

    def __init__(
        self,
        feature_size: float = 128.0,
        octaves: int = 4,
        persistence: float = 0.5,
        lacunarity: float = 2.0,
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
        if octaves < 1:
            raise ValueError("octaves must be >= 1")
        self.feature_size = float(feature_size)
        self.octaves = int(octaves)
        self.persistence = float(persistence)
        self.lacunarity = float(lacunarity)
        self._rng = np.random.default_rng(seed)

    def _generate_fresh(self, shape: tuple[int, ...]) -> np.ndarray:
        height, width = shape[0], shape[1]
        channels = shape[2] if len(shape) == 3 else 1
        planes = [
            fbm_2d(
                height,
                width,
                self.feature_size,
                self.octaves,
                self.persistence,
                self.lacunarity,
                self._rng,
            )
            for _ in range(channels)
        ]
        return np.stack(planes, axis=-1) if channels > 1 else planes[0][..., None]
