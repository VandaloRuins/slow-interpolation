"""Evolved Gaussian noise walk.

A persistent noise tensor is held across frames and slowly evolved by blending in
a small fraction of fresh Gaussian noise each call, then renormalized to unit
variance. The evolved tensor is mapped to mid-gray-centered pixels and alpha-
blended into the input image.

Fine detail in the diffused output depends on the noise pattern. Reusing a
slowly-evolving tensor instead of fresh per-frame randomness means those details
persist rather than being reinvented every keyframe (the documented root cause
of the 1.3 s rhythmic detail pulse in earlier iterations of the pipeline).

Source: captured verbatim from the legacy production codebase (the
`generate_crown_video.py` script of an earlier project); see
`docs/pipeline.md` appendix for the line-by-line provenance. Refactored from
module-global state to a class so multiple Pipeline instances can coexist
without sharing noise state.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from .base import NoiseSource


class EvolvedNoiseWalk(NoiseSource):
    """Slowly-evolving Gaussian noise blended into img2img inputs."""

    def __init__(self, walk_rate: float = 0.05) -> None:
        self.walk_rate = walk_rate
        self._noise: np.ndarray | None = None

    def reset(self) -> None:
        """Drop the persistent tensor. Next blend call starts fresh."""
        self._noise = None

    def blend(self, img: Image.Image, blend_pct: float = 0.08) -> Image.Image:
        """Return `img` blended with the current (evolved) noise tensor."""
        arr = np.array(img).astype(np.float32)
        fresh = np.random.randn(*arr.shape).astype(np.float32)

        if self._noise is None or self._noise.shape != arr.shape:
            self._noise = fresh.copy()
        else:
            self._noise = (1.0 - self.walk_rate) * self._noise + self.walk_rate * fresh
            std = self._noise.std()
            if std > 0:
                self._noise = self._noise / std

        noise_pixels = (self._noise * 40 + 128).clip(0, 255)
        blended = arr * (1 - blend_pct) + noise_pixels * blend_pct
        return Image.fromarray(blended.clip(0, 255).astype(np.uint8))
