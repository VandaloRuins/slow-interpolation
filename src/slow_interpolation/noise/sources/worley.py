"""Worley (cellular) noise as a NoiseSource.

Visual reading: cell-like. Distance-to-nearest-feature-point produces dark
basins around each point and bright ridges along Voronoi boundaries. Strong
candidate for floral subjects (petal cells, stamen clusters) and for textures
with discrete repeating units.

Parameters:

- `cell_density`: feature points per million pixels. Default 300 puts ~310
  points on a 768x1344 frame. Higher = smaller cells. A reasonable sweep is
  100 to 1500.
- `distance`: "euclidean" (round basins), "manhattan" (diamond basins),
  "chebyshev" (square basins). Euclidean is the default and the most organic
  reading; manhattan and chebyshev produce more graphic, geometric textures.
- `walk_rate`: temporal blend rate.

Per-RGB-channel independence: each channel scatters its own point set so the
three colour planes do not align onto identical cells (which would read as a
monochrome cellular texture).
"""

from __future__ import annotations

import numpy as np

from ..base import WalkingNoiseSource
from ._kernels import worley_2d


class WorleyNoise(WalkingNoiseSource):
    """Cellular / Worley noise. Distance-to-nearest-feature-point."""

    def __init__(
        self,
        cell_density: float = 300.0,
        distance: str = "euclidean",
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
        if distance not in ("euclidean", "manhattan", "chebyshev"):
            raise ValueError(f"Unknown distance metric: {distance!r}")
        self.cell_density = float(cell_density)
        self.distance = distance
        self._rng = np.random.default_rng(seed)

    def _n_points(self, height: int, width: int) -> int:
        n = int(round(self.cell_density * height * width / 1_000_000.0))
        return max(4, n)

    def _generate_fresh(self, shape: tuple[int, ...]) -> np.ndarray:
        height, width = shape[0], shape[1]
        channels = shape[2] if len(shape) == 3 else 1
        n_points = self._n_points(height, width)
        planes = [
            worley_2d(height, width, n_points, self.distance, self._rng)
            for _ in range(channels)
        ]
        return np.stack(planes, axis=-1) if channels > 1 else planes[0][..., None]
