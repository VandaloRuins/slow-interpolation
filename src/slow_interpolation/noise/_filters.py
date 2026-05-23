"""Shared filter utilities for the noise sources.

Pure numpy, dependency-free. The point is to avoid pulling scipy into the
project dependencies for one Gaussian blur.
"""

from __future__ import annotations

import numpy as np


def gaussian_blur_2d(arr: np.ndarray, sigma: float) -> np.ndarray:
    """Separable Gaussian blur on a 2D or (H, W, C) float array.

    Reflect-padded; channel-last layout for 3D input. Returns a new array of
    the same shape and dtype as the input.
    """
    if sigma <= 0:
        return arr.copy()
    radius = max(1, int(np.ceil(3.0 * sigma)))
    xs = np.arange(-radius, radius + 1, dtype=np.float32)
    kernel = np.exp(-(xs * xs) / (2.0 * sigma * sigma))
    kernel /= kernel.sum()

    # Horizontal pass.
    h_pad = ((0, 0), (radius, radius)) + ((0, 0),) * (arr.ndim - 2)
    padded = np.pad(arr, h_pad, mode="reflect")
    out = np.zeros_like(arr, dtype=np.float32)
    for i, k in enumerate(kernel):
        out += k * padded[:, i : i + arr.shape[1]]

    # Vertical pass.
    v_pad = ((radius, radius),) + ((0, 0),) * (arr.ndim - 1)
    padded2 = np.pad(out, v_pad, mode="reflect")
    out2 = np.zeros_like(arr, dtype=np.float32)
    for i, k in enumerate(kernel):
        out2 += k * padded2[i : i + arr.shape[0]]

    return out2.astype(arr.dtype, copy=False)
