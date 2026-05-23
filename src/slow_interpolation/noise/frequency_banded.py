"""Frequency-banded noise as a NoiseSource.

Stacks N sub-sources at different spatial-frequency targets. Each sub-source
draws a fresh sample per frame; the sample is Gaussian-blurred at the band's
sigma (higher sigma = lower frequency) and weighted into the final tensor. The
sum is then put through the standard walk-and-renormalize loop, so the band
stack itself evolves temporally with `walk_rate`.

The point: control coarse motion and fine motion independently. Typical
artistic use:

- Worley (sigma=0)  at the high-frequency band: cell texture / petal grain.
- Perlin (sigma=4)  at the mid band: soft regional drift.
- FBM    (sigma=16) at the low band: atmospheric, large-scale modulation.

By varying `band_weights` the operator can dial up or down each register
without retraining intuition for any single source.

Construction:

    FrequencyBandedNoise(
        sources=[WorleyNoise(...), PerlinNoise(...), FBMNoise(...)],
        band_sigmas=[0.0, 4.0, 16.0],
        band_weights=[0.5, 1.0, 0.7],
    )

Constraints. Sub-sources must be `WalkingNoiseSource` instances (the band stack
accesses their `_generate_fresh` to bypass the per-source walk and pixel
mapping). Their own `walk_rate` is irrelevant; the outer stack owns the walk.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from ._filters import gaussian_blur_2d
from .base import WalkingNoiseSource


class FrequencyBandedNoise(WalkingNoiseSource):
    """N walking noise sources stacked at distinct frequency bands."""

    def __init__(
        self,
        sources: Sequence[WalkingNoiseSource],
        band_sigmas: Sequence[float],
        band_weights: Sequence[float] | None = None,
        walk_rate: float = 0.05,
        pixel_spread: float = 40.0,
        pixel_center: float = 128.0,
    ) -> None:
        super().__init__(
            walk_rate=walk_rate,
            pixel_spread=pixel_spread,
            pixel_center=pixel_center,
        )
        sources = list(sources)
        band_sigmas = list(band_sigmas)
        if not all(isinstance(s, WalkingNoiseSource) for s in sources):
            raise TypeError(
                "FrequencyBandedNoise sub-sources must be WalkingNoiseSource "
                "instances (Perlin/Worley/Simplex/FBM/EvolvedNoiseWalk)."
            )
        if len(sources) != len(band_sigmas):
            raise ValueError(
                f"sources ({len(sources)}) and band_sigmas ({len(band_sigmas)}) "
                "must have the same length."
            )
        if band_weights is None:
            band_weights = [1.0] * len(sources)
        elif len(band_weights) != len(sources):
            raise ValueError(
                f"band_weights ({len(band_weights)}) must match sources length."
            )

        self.sources = sources
        self.band_sigmas = [float(s) for s in band_sigmas]
        self.band_weights = [float(w) for w in band_weights]

    def reset(self) -> None:
        super().reset()
        for s in self.sources:
            s.reset()

    def _generate_fresh(self, shape: tuple[int, ...]) -> np.ndarray:
        out = np.zeros(shape, dtype=np.float32)
        for src, sigma, weight in zip(
            self.sources, self.band_sigmas, self.band_weights
        ):
            band = src._generate_fresh(shape).astype(np.float32)
            if sigma > 0:
                band = gaussian_blur_2d(band, sigma)
            out += weight * band
        std = out.std()
        if std > 0:
            out = out / std
        return out
