"""Structured noise sources for the slow-interpolation pipeline.

Each module here defines one `NoiseSource` implementation. They are intentionally
lightweight (pure numpy, no GPU) so the comparison harness can iterate quickly
on CPU. The image-derived and frequency-banded sources at the top-level of
`noise/` are heavier and may use the GPU.
"""

from .fbm import FBMNoise
from .perlin import PerlinNoise
from .simplex import SimplexNoise
from .worley import WorleyNoise

__all__ = ["FBMNoise", "PerlinNoise", "SimplexNoise", "WorleyNoise"]
