"""Smoke tests for EvolvedNoiseWalk. No GPU, no diffusers."""

import numpy as np
from PIL import Image

from slow_interpolation.noise import EvolvedNoiseWalk


def _solid(w: int = 64, h: int = 64, value: int = 128) -> Image.Image:
    return Image.new("RGB", (w, h), (value, value, value))


def test_first_call_initializes_state():
    walk = EvolvedNoiseWalk(walk_rate=0.05)
    assert walk._noise is None
    out = walk.blend(_solid(), blend_pct=0.08)
    assert walk._noise is not None
    assert walk._noise.shape == (64, 64, 3)
    assert out.size == (64, 64)


def test_persistent_state_drifts_slowly():
    walk = EvolvedNoiseWalk(walk_rate=0.05)
    walk.blend(_solid(), blend_pct=0.08)
    snapshot = walk._noise.copy()
    walk.blend(_solid(), blend_pct=0.08)
    diff_norm = np.linalg.norm(walk._noise - snapshot) / np.linalg.norm(snapshot)
    # walk_rate=0.05 means each step replaces ~5% of state. Drift should be
    # measurable but small. Bounds chosen loosely to avoid flakiness.
    assert 0.01 < diff_norm < 0.5


def test_shape_change_resets_state():
    walk = EvolvedNoiseWalk()
    walk.blend(_solid(64, 64), blend_pct=0.08)
    assert walk._noise.shape == (64, 64, 3)
    walk.blend(_solid(128, 64), blend_pct=0.08)
    assert walk._noise.shape == (64, 128, 3)


def test_reset_drops_state():
    walk = EvolvedNoiseWalk()
    walk.blend(_solid(), blend_pct=0.08)
    walk.reset()
    assert walk._noise is None


def test_blend_pct_zero_leaves_image_unchanged():
    walk = EvolvedNoiseWalk()
    src = _solid(value=200)
    out = walk.blend(src, blend_pct=0.0)
    assert np.array_equal(np.array(out), np.array(src))


def test_per_instance_state_is_independent():
    a = EvolvedNoiseWalk()
    b = EvolvedNoiseWalk()
    a.blend(_solid(), blend_pct=0.08)
    assert b._noise is None
