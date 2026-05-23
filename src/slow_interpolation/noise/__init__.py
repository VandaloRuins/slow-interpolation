"""Noise sources for the Phase A img2img walk.

`build_noise_source(config)` is the factory used by `Pipeline.generate_keyframes`
to materialise a `NoiseSource` from `config.render.noise` (a `NoiseConfig` with
`kind` + `params`). `walk_rate` is inherited from `RenderProfile.noise_walk_rate`
when not explicitly set in `params`.

Known kinds (extend `_KIND_BUILDERS` to register more):

- `evolved` (default) -> `EvolvedNoiseWalk`
- `perlin` -> `PerlinNoise`
- `worley` -> `WorleyNoise`
- `simplex` -> `SimplexNoise`
- `fbm` -> `FBMNoise`
- `image_derived` -> `ImageDerivedNoise` (no walk_rate)
- `frequency_banded` -> `FrequencyBandedNoise` (recursive sub-sources via
  `params.sources = [{kind, params}, ...]`)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import NoiseSource, WalkingNoiseSource
from .evolved_walk import EvolvedNoiseWalk
from .frequency_banded import FrequencyBandedNoise
from .image_derived import ImageDerivedNoise
from .sources import FBMNoise, PerlinNoise, SimplexNoise, WorleyNoise

if TYPE_CHECKING:
    from ..config import PipelineConfig


def build_noise_source(config: "PipelineConfig") -> NoiseSource:
    """Construct the `NoiseSource` named by `config.render.noise`.

    `walk_rate` falls back to `config.render.noise_walk_rate` for the source
    families that honour it (everything except `image_derived`).
    """
    noise_cfg = config.render.noise
    default_walk_rate = config.render.noise_walk_rate
    return _build_from_spec(noise_cfg.kind, noise_cfg.params, default_walk_rate)


def _build_from_spec(
    kind: str, params: dict[str, Any] | None, default_walk_rate: float
) -> NoiseSource:
    params = dict(params or {})

    if kind in ("evolved", "evolved_walk"):
        params.setdefault("walk_rate", default_walk_rate)
        return EvolvedNoiseWalk(**params)

    if kind == "perlin":
        params.setdefault("walk_rate", default_walk_rate)
        return PerlinNoise(**params)

    if kind == "worley":
        params.setdefault("walk_rate", default_walk_rate)
        return WorleyNoise(**params)

    if kind == "simplex":
        params.setdefault("walk_rate", default_walk_rate)
        return SimplexNoise(**params)

    if kind == "fbm":
        params.setdefault("walk_rate", default_walk_rate)
        return FBMNoise(**params)

    if kind == "image_derived":
        # No walk_rate; static-per-shape texture.
        return ImageDerivedNoise(**params)

    if kind in ("banded", "frequency_banded"):
        sources_spec = params.pop("sources", [])
        sub_sources = [
            _build_from_spec(s["kind"], s.get("params", {}), default_walk_rate)
            for s in sources_spec
        ]
        params["sources"] = sub_sources
        params.setdefault("walk_rate", default_walk_rate)
        return FrequencyBandedNoise(**params)

    raise ValueError(f"Unknown noise kind: {kind!r}")


__all__ = [
    "EvolvedNoiseWalk",
    "FBMNoise",
    "FrequencyBandedNoise",
    "ImageDerivedNoise",
    "NoiseSource",
    "PerlinNoise",
    "SimplexNoise",
    "WalkingNoiseSource",
    "WorleyNoise",
    "build_noise_source",
]
