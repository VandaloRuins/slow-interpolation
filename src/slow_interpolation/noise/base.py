"""NoiseSource interface and a walk-and-blend helper base.

Every Phase A noise input is a function (image, blend_pct) -> image that returns
the input image alpha-blended with a noise tensor. The noise tensor is allowed
(in fact, required) to carry temporal state across frames so that fine detail in
the diffused output persists rather than being reinvented at every keyframe.
This is the same mechanism the production `EvolvedNoiseWalk` implements; the
abstraction exists so different *spatial* noise statistics (Perlin, Worley,
simplex, FBM, image-derived, frequency-banded) can be dropped into the same
call site in `keyframes.py`.

Two layers:

- `NoiseSource` is the abstract interface. `reset()` drops persistent state,
  `blend()` returns the blended image. `EvolvedNoiseWalk` is a direct
  implementation that keeps its own state shape.
- `WalkingNoiseSource` is a concrete helper base that implements the standard
  "evolve persistent tensor by `walk_rate`, renormalize, map to mid-gray
  pixels, alpha-blend" loop. Subclasses only need to implement
  `_generate_fresh(shape)` returning a unit-variance ndarray. All four
  structured sources in `sources/` use this.

Shape-keyed restart: if the input image size changes between calls, the
persistent tensor is dropped and reseeded from a fresh sample. This mirrors
`evolved_noise_blend`'s behavior and matters when the same source instance is
reused across orientations or test resolutions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
from PIL import Image


class NoiseSource(ABC):
    """Abstract per-frame noise input for the img2img chain.

    Implementations may keep temporal state across `blend` calls. Callers
    should invoke `reset()` between independent runs (typically at the start
    of each `Pipeline.generate_keyframes()` call).
    """

    @abstractmethod
    def reset(self) -> None:
        """Drop persistent state. The next `blend` call starts fresh."""

    @abstractmethod
    def blend(self, img: Image.Image, blend_pct: float) -> Image.Image:
        """Return `img` alpha-blended with this source's noise tensor.

        `blend_pct` is the noise weight in [0, 1]. The legacy production
        values are 0.08 steady and 0.15 transition (standard profile).
        """


class WalkingNoiseSource(NoiseSource):
    """Base class for noise sources that use the walk-and-renormalize pattern.

    Each frame, a fresh sample of the source's characteristic noise is drawn,
    blended into the persistent tensor at `walk_rate`, and the tensor is
    renormalized to unit variance. The tensor is mapped to pixels by
    `noise * pixel_spread + pixel_center` then alpha-blended into the input.

    Subclasses implement `_generate_fresh(shape)` to return a (H, W, C) float32
    array. The expected variance is ~1.0 but is not strictly enforced because
    renormalization handles drift.
    """

    def __init__(
        self,
        walk_rate: float = 0.05,
        pixel_spread: float = 40.0,
        pixel_center: float = 128.0,
    ) -> None:
        self.walk_rate = walk_rate
        self.pixel_spread = pixel_spread
        self.pixel_center = pixel_center
        self._noise: np.ndarray | None = None

    def reset(self) -> None:
        self._noise = None

    def blend(self, img: Image.Image, blend_pct: float = 0.08) -> Image.Image:
        arr = np.array(img).astype(np.float32)
        fresh = self._generate_fresh(arr.shape).astype(np.float32)

        if self._noise is None or self._noise.shape != arr.shape:
            self._noise = fresh.copy()
        else:
            self._noise = (1.0 - self.walk_rate) * self._noise + self.walk_rate * fresh
            std = self._noise.std()
            if std > 0:
                self._noise = self._noise / std

        noise_pixels = (self._noise * self.pixel_spread + self.pixel_center).clip(0, 255)
        blended = arr * (1.0 - blend_pct) + noise_pixels * blend_pct
        return Image.fromarray(blended.clip(0, 255).astype(np.uint8))

    @abstractmethod
    def _generate_fresh(self, shape: tuple[int, ...]) -> np.ndarray:
        """Return a fresh (H, W, C) float32 noise sample.

        Subclasses set the spatial statistics here. The result should be
        approximately zero-mean unit-variance; the parent class will renormalize
        across frames anyway, but a wildly mis-scaled sample changes the early
        frames before the walk has averaged in.
        """


__all__ = ["NoiseSource", "WalkingNoiseSource"]
