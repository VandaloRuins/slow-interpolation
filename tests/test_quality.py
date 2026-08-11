"""Guards on the measurement core and the artefact injector.

The failure these exist to prevent is not a crash, it is a detector that looks
authoritative and measures nothing. On 2026-08-11 eight were built that way. So
the tests here assert the two properties that make the bench trustworthy:

  1. an injection at zero amplitude changes NOTHING, so a control differs from a
     positive by the injection alone
  2. each shipped measure moves in the direction the bench says it does, on a
     synthetic fixture built in-process
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from slow_interpolation.quality import border_features, hf_ratio

ROOT = Path(__file__).resolve().parents[1]


def load_sim():
    spec = importlib.util.spec_from_file_location("asim", ROOT / "tools" / "artefact_sim.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def painterly(h=256, w=640, seed=0):
    """A frame with broad masses and fine detail, like the renders."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    base = 120 + 60 * np.sin(x / 90.0) + 40 * np.cos(y / 50.0)
    grain = rng.normal(0, 18, (h, w))
    return np.clip(base + grain, 0, 255).astype(np.uint8)


@pytest.mark.parametrize("name", ["canvas_edge", "morph", "blur", "flicker"])
def test_zero_amplitude_is_exactly_a_noop(name):
    sim = load_sim()
    f = np.stack([painterly()] * 3, axis=-1)
    ctx = sim.build_context(name, 10, f.shape[1], f.shape[0])
    ctx = sim.per_frame_context(name, ctx, 0, 10, 0.0)
    assert np.array_equal(sim.SPATIAL[name](f, 0.0, ctx), f)


def test_zero_amplitude_temporal_injections_are_identity_maps():
    sim = load_sim()
    assert sim.index_map("decimate", 1.0, 100, 10) == list(range(100))
    assert sim.index_map("lurch", 0, 100, 10) == list(range(100))
    # and that they actually do something when asked to
    assert len(sim.index_map("decimate", 1.5, 100, 10)) < 100
    assert len(sim.index_map("lurch", 4, 100, 10)) < 100


def test_hf_ratio_falls_when_an_image_is_blurred():
    import cv2
    f = painterly()
    assert hf_ratio(cv2.GaussianBlur(f, (9, 9), 3)) < hf_ratio(f)


def test_b_detail_falls_with_canvas_edge_band_width():
    """The one border feature that survived validation, and the direction it moves.

    Five other candidates reverse direction partway up the amplitude ladder;
    this one is monotonic on both synthetic bases. If this test ever fails, the
    detector wired into review_gate.py has stopped meaning what it claims.
    """
    sim = load_sim()
    f = np.stack([painterly(h=256, w=640)] * 3, axis=-1)
    ctx = sim.build_context("canvas_edge", 10, 640, 256)
    vals = []
    for amp in (0, 16, 32, 48):
        got = sim.inject_canvas_edge(f, amp, ctx)
        vals.append(border_features(got[..., 0].astype(np.uint8))["b_detail"])
    assert vals == sorted(vals, reverse=True), f"not monotonic: {vals}"
    assert vals[-1] < vals[0] * 0.85


def test_border_features_do_not_crash_on_a_narrow_frame():
    f = painterly(h=64, w=200)
    out = border_features(f)
    assert set(out) >= {"b_hf", "b_detail", "b_orient", "b_edgepeak"}
    assert all(np.isfinite(v) for v in out.values())
