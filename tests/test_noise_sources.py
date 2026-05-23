"""Smoke tests for the NoiseSource interface and the structured sources.

No GPU, no diffusers. Each implementation is exercised through the standard
interface (init, blend, persistent-state drift, shape-keyed restart, reset).
Sizes are kept small (64 to 96 px) so the suite stays under a second on CPU.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from slow_interpolation.noise import (
    EvolvedNoiseWalk,
    FBMNoise,
    FrequencyBandedNoise,
    ImageDerivedNoise,
    NoiseSource,
    PerlinNoise,
    SimplexNoise,
    WalkingNoiseSource,
    WorleyNoise,
)


def _solid(w: int = 64, h: int = 64, value: int = 128) -> Image.Image:
    return Image.new("RGB", (w, h), (value, value, value))


def _all_sources() -> list[NoiseSource]:
    """One instance of each structured source plus the legacy walker."""
    return [
        EvolvedNoiseWalk(walk_rate=0.05),
        PerlinNoise(feature_size=16.0, walk_rate=0.05, seed=0),
        WorleyNoise(cell_density=500.0, walk_rate=0.05, seed=0),
        SimplexNoise(feature_size=16.0, walk_rate=0.05, seed=0),
        FBMNoise(feature_size=32.0, octaves=3, walk_rate=0.05, seed=0),
    ]


@pytest.mark.parametrize("src", _all_sources(), ids=lambda s: type(s).__name__)
def test_satisfies_noise_source_interface(src: NoiseSource) -> None:
    assert isinstance(src, NoiseSource)
    assert callable(src.reset)
    assert callable(src.blend)


@pytest.mark.parametrize("src", _all_sources(), ids=lambda s: type(s).__name__)
def test_first_call_initializes_state_and_returns_image(src: NoiseSource) -> None:
    assert src._noise is None
    out = src.blend(_solid(), blend_pct=0.08)
    assert isinstance(out, Image.Image)
    assert out.size == (64, 64)
    assert src._noise is not None
    assert src._noise.shape == (64, 64, 3)


@pytest.mark.parametrize("src", _all_sources(), ids=lambda s: type(s).__name__)
def test_persistent_state_drifts_slowly(src: NoiseSource) -> None:
    src.blend(_solid(), blend_pct=0.08)
    snapshot = src._noise.copy()
    src.blend(_solid(), blend_pct=0.08)
    diff_norm = np.linalg.norm(src._noise - snapshot) / max(
        1e-9, np.linalg.norm(snapshot)
    )
    # walk_rate=0.05 -> ~5% replacement per step. Allow a loose envelope to
    # accommodate structured sources whose fresh sample has different per-pixel
    # variance even after kernel-level renormalization.
    assert 0.005 < diff_norm < 0.8


@pytest.mark.parametrize("src", _all_sources(), ids=lambda s: type(s).__name__)
def test_shape_change_resets_state(src: NoiseSource) -> None:
    src.blend(_solid(64, 64), blend_pct=0.08)
    assert src._noise.shape == (64, 64, 3)
    src.blend(_solid(96, 64), blend_pct=0.08)
    assert src._noise.shape == (64, 96, 3)


@pytest.mark.parametrize("src", _all_sources(), ids=lambda s: type(s).__name__)
def test_reset_drops_state(src: NoiseSource) -> None:
    src.blend(_solid(), blend_pct=0.08)
    src.reset()
    assert src._noise is None


@pytest.mark.parametrize("src", _all_sources(), ids=lambda s: type(s).__name__)
def test_blend_pct_zero_leaves_image_unchanged(src: NoiseSource) -> None:
    img = _solid(value=200)
    out = src.blend(img, blend_pct=0.0)
    assert np.array_equal(np.array(out), np.array(img))


@pytest.mark.parametrize("src", _all_sources(), ids=lambda s: type(s).__name__)
def test_per_instance_state_is_independent(src: NoiseSource) -> None:
    other = type(src)() if not isinstance(src, (PerlinNoise, SimplexNoise, FBMNoise, WorleyNoise)) else type(src)(seed=1)
    src.blend(_solid(), blend_pct=0.08)
    assert other._noise is None


def test_worley_rejects_unknown_distance() -> None:
    with pytest.raises(ValueError):
        WorleyNoise(distance="taxicab")


def test_fbm_rejects_zero_octaves() -> None:
    with pytest.raises(ValueError):
        FBMNoise(octaves=0)


def _ref_image_path(tmp_path) -> "Path":  # noqa: F821
    from pathlib import Path

    # Build a synthetic reference (some recognizable pattern) and save it.
    arr = np.zeros((48, 48, 3), dtype=np.uint8)
    arr[..., 0] = np.tile(np.arange(48, dtype=np.uint8), (48, 1))  # red ramp
    arr[..., 1] = np.tile(np.arange(48, dtype=np.uint8)[:, None], (1, 48))  # green ramp
    arr[..., 2] = 128
    p = Path(tmp_path) / "ref.png"
    Image.fromarray(arr).save(p)
    return p


def test_image_derived_satisfies_interface(tmp_path) -> None:
    src = ImageDerivedNoise(_ref_image_path(tmp_path), use_vae=False)
    assert isinstance(src, NoiseSource)
    out = src.blend(_solid(), blend_pct=0.08)
    assert isinstance(out, Image.Image)
    assert src._noise is not None
    assert src._noise.shape == (64, 64, 3)


def test_image_derived_texture_is_static(tmp_path) -> None:
    """Two consecutive blends should produce identical cached textures (the
    source is intentionally static)."""
    src = ImageDerivedNoise(_ref_image_path(tmp_path), use_vae=False)
    src.blend(_solid(), blend_pct=0.08)
    first = src._noise.copy()
    src.blend(_solid(), blend_pct=0.08)
    assert np.array_equal(src._noise, first)


def test_image_derived_shape_change_recomputes(tmp_path) -> None:
    src = ImageDerivedNoise(_ref_image_path(tmp_path), use_vae=False)
    src.blend(_solid(64, 64), blend_pct=0.08)
    assert src._noise.shape == (64, 64, 3)
    src.blend(_solid(96, 64), blend_pct=0.08)
    assert src._noise.shape == (64, 96, 3)


def test_image_derived_reset_drops_state(tmp_path) -> None:
    src = ImageDerivedNoise(_ref_image_path(tmp_path), use_vae=False)
    src.blend(_solid(), blend_pct=0.08)
    src.reset()
    assert src._noise is None


def test_image_derived_blend_pct_zero_is_identity(tmp_path) -> None:
    src = ImageDerivedNoise(_ref_image_path(tmp_path), use_vae=False)
    img = _solid(value=200)
    out = src.blend(img, blend_pct=0.0)
    assert np.array_equal(np.array(out), np.array(img))


# ---------- FrequencyBandedNoise --------------------------------------------


def _three_band_stack() -> FrequencyBandedNoise:
    return FrequencyBandedNoise(
        sources=[
            WorleyNoise(cell_density=500.0, seed=0),
            PerlinNoise(feature_size=24.0, seed=0),
            FBMNoise(feature_size=48.0, octaves=3, seed=0),
        ],
        band_sigmas=[0.0, 3.0, 9.0],
        band_weights=[0.5, 1.0, 0.7],
        walk_rate=0.05,
    )


def test_frequency_banded_satisfies_interface() -> None:
    src = _three_band_stack()
    assert isinstance(src, NoiseSource)
    assert isinstance(src, WalkingNoiseSource)
    out = src.blend(_solid(), blend_pct=0.08)
    assert isinstance(out, Image.Image)
    assert src._noise.shape == (64, 64, 3)


def test_frequency_banded_drifts_slowly() -> None:
    src = _three_band_stack()
    src.blend(_solid(), blend_pct=0.08)
    snap = src._noise.copy()
    src.blend(_solid(), blend_pct=0.08)
    diff_norm = np.linalg.norm(src._noise - snap) / max(1e-9, np.linalg.norm(snap))
    assert 0.005 < diff_norm < 0.8


def test_frequency_banded_shape_change_resets() -> None:
    src = _three_band_stack()
    src.blend(_solid(64, 64), blend_pct=0.08)
    assert src._noise.shape == (64, 64, 3)
    src.blend(_solid(96, 64), blend_pct=0.08)
    assert src._noise.shape == (64, 96, 3)


def test_frequency_banded_reset_cascades_to_subsources() -> None:
    """The band stack owns the walk and bypasses sub-sources' `blend`, so they
    do not accumulate `_noise` state on their own. Still, if a sub-source was
    used independently elsewhere, the outer reset should propagate."""
    src = _three_band_stack()
    src.blend(_solid(), blend_pct=0.08)
    assert src._noise is not None
    # Simulate sub-source state set by an external caller.
    for sub in src.sources:
        sub.blend(_solid(), blend_pct=0.08)
        assert sub._noise is not None
    src.reset()
    assert src._noise is None
    for sub in src.sources:
        assert sub._noise is None


def test_frequency_banded_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError):
        FrequencyBandedNoise(
            sources=[PerlinNoise()],
            band_sigmas=[0.0, 4.0],
        )


def test_frequency_banded_rejects_non_walking_source() -> None:
    class _Dummy(NoiseSource):
        def reset(self): pass
        def blend(self, img, blend_pct):
            return img
    with pytest.raises(TypeError):
        FrequencyBandedNoise(sources=[_Dummy()], band_sigmas=[0.0])


def test_structured_sources_produce_non_uniform_output() -> None:
    """Sanity: a structured source should produce per-pixel variation in the
    blended output even when the input is a solid colour. (The legacy
    EvolvedNoiseWalk would also pass this; the parametric check above already
    covers it for all sources, but this is a focused sanity check that catches
    a degenerate `_generate_fresh` returning zeros.)"""
    for src in (
        PerlinNoise(feature_size=16.0, seed=0),
        WorleyNoise(cell_density=500.0, seed=0),
        SimplexNoise(feature_size=16.0, seed=0),
        FBMNoise(feature_size=32.0, octaves=3, seed=0),
    ):
        out = np.array(src.blend(_solid(value=128), blend_pct=0.5))
        assert out.std() > 1.0, f"{type(src).__name__} produced near-uniform output"
