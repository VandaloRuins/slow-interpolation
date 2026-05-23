"""Vectorized 2D noise kernels shared across structured sources.

Pure numpy. No GPU. Each kernel returns a float32 array of the requested shape
with approximately zero mean and unit variance; the parent `WalkingNoiseSource`
will renormalize anyway, but staying close to unit variance avoids large early-
frame swings before the walk has averaged in.

The implementations here trade theoretical purity for speed and clarity. Perlin
uses gradient noise on a coarse grid with smoothstep interpolation. Simplex is
implemented with the standard 2D skew/unskew construction (one channel; per-RGB
decorrelation is achieved by per-channel grid permutations). Worley scatters
feature points and returns distance-to-nearest.
"""

from __future__ import annotations

import numpy as np


def _smoothstep(t: np.ndarray) -> np.ndarray:
    return t * t * (3.0 - 2.0 * t)


def perlin_2d(
    height: int,
    width: int,
    feature_size: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Single-octave 2D Perlin gradient noise. Returns (H, W) float32.

    `feature_size` is the side of one grid cell in pixels. Smaller = higher
    spatial frequency. Output is normalized to ~unit variance.
    """
    if feature_size < 1.0:
        feature_size = 1.0

    gh = int(np.ceil(height / feature_size)) + 2
    gw = int(np.ceil(width / feature_size)) + 2

    # Random unit-vector gradients at each grid corner.
    angles = rng.uniform(0.0, 2.0 * np.pi, size=(gh, gw)).astype(np.float32)
    gx = np.cos(angles)
    gy = np.sin(angles)

    # Per-pixel grid coordinates.
    xs = np.arange(width, dtype=np.float32) / feature_size
    ys = np.arange(height, dtype=np.float32) / feature_size
    yy, xx = np.meshgrid(ys, xs, indexing="ij")

    x0 = np.floor(xx).astype(np.int32)
    y0 = np.floor(yy).astype(np.int32)
    x1 = x0 + 1
    y1 = y0 + 1

    # Local offsets to each of the four cell corners.
    dx0 = xx - x0
    dy0 = yy - y0
    dx1 = dx0 - 1.0
    dy1 = dy0 - 1.0

    # Dot products with corner gradients.
    n00 = gx[y0, x0] * dx0 + gy[y0, x0] * dy0
    n10 = gx[y0, x1] * dx1 + gy[y0, x1] * dy0
    n01 = gx[y1, x0] * dx0 + gy[y1, x0] * dy1
    n11 = gx[y1, x1] * dx1 + gy[y1, x1] * dy1

    sx = _smoothstep(dx0)
    sy = _smoothstep(dy0)

    nx0 = n00 * (1.0 - sx) + n10 * sx
    nx1 = n01 * (1.0 - sx) + n11 * sx
    out = nx0 * (1.0 - sy) + nx1 * sy

    # Perlin's natural range is roughly [-sqrt(2)/2, sqrt(2)/2]. Normalize.
    std = out.std()
    if std > 0:
        out = out / std
    return out.astype(np.float32)


def fbm_2d(
    height: int,
    width: int,
    feature_size: float,
    octaves: int,
    persistence: float,
    lacunarity: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Multi-octave fractional Brownian motion over Perlin noise.

    `persistence` controls amplitude falloff per octave (0.5 = each octave half
    as loud as the prior). `lacunarity` controls frequency growth per octave
    (2.0 = each octave twice the frequency).
    """
    out = np.zeros((height, width), dtype=np.float32)
    amplitude = 1.0
    size = feature_size
    for _ in range(octaves):
        out += amplitude * perlin_2d(height, width, size, rng)
        amplitude *= persistence
        size = max(1.0, size / lacunarity)
    std = out.std()
    if std > 0:
        out = out / std
    return out


def worley_2d(
    height: int,
    width: int,
    n_points: int,
    distance: str,
    rng: np.random.Generator,
) -> np.ndarray:
    """Worley / cellular noise. Returns distance-to-nearest-feature-point.

    `distance` is one of "euclidean", "manhattan", "chebyshev". Output is
    centered to zero mean and normalized to unit variance.
    """
    # Scatter feature points in pixel coordinates.
    px = rng.uniform(0.0, width, size=n_points).astype(np.float32)
    py = rng.uniform(0.0, height, size=n_points).astype(np.float32)

    # Per-pixel grid.
    xs = np.arange(width, dtype=np.float32)
    ys = np.arange(height, dtype=np.float32)
    yy, xx = np.meshgrid(ys, xs, indexing="ij")

    # Tile feature points to broadcast against (H, W). For 100-200 points this
    # is fine memory-wise; for huge densities we'd need a kd-tree.
    dx = xx[..., None] - px  # (H, W, n_points)
    dy = yy[..., None] - py

    if distance == "manhattan":
        d = np.abs(dx) + np.abs(dy)
    elif distance == "chebyshev":
        d = np.maximum(np.abs(dx), np.abs(dy))
    else:  # euclidean
        d = np.sqrt(dx * dx + dy * dy)

    nearest = d.min(axis=-1)
    nearest = nearest - nearest.mean()
    std = nearest.std()
    if std > 0:
        nearest = nearest / std
    return nearest.astype(np.float32)


# -- Simplex noise (standard 2D construction) -------------------------------
# Reference: Stefan Gustavson, "Simplex noise demystified" (2005). The skew
# and unskew constants below are exact for 2D.

_F2 = (np.sqrt(3.0) - 1.0) / 2.0
_G2 = (3.0 - np.sqrt(3.0)) / 6.0


def simplex_2d(
    height: int,
    width: int,
    feature_size: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """2D simplex noise. Returns (H, W) float32, normalized to ~unit variance.

    Like Perlin but on a triangular lattice. Cheaper per pixel asymptotically
    and visually less axis-aligned. We carry a random gradient table per call
    so successive frames decorrelate (the persistence comes from the parent
    walk-and-blend loop).
    """
    if feature_size < 1.0:
        feature_size = 1.0

    # Build a permutation-indexed gradient table of unit vectors.
    n_grad = 256
    angles = rng.uniform(0.0, 2.0 * np.pi, size=n_grad).astype(np.float32)
    grads = np.stack([np.cos(angles), np.sin(angles)], axis=-1)  # (256, 2)
    perm = rng.permutation(n_grad).astype(np.int32)
    perm2 = np.concatenate([perm, perm])  # length 512, for index wrap

    xs = np.arange(width, dtype=np.float32) / feature_size
    ys = np.arange(height, dtype=np.float32) / feature_size
    yy, xx = np.meshgrid(ys, xs, indexing="ij")

    s = (xx + yy) * _F2
    i = np.floor(xx + s).astype(np.int32)
    j = np.floor(yy + s).astype(np.int32)

    t = (i + j) * _G2
    X0 = i - t
    Y0 = j - t
    x0 = xx - X0
    y0 = yy - Y0

    # Determine which simplex (triangle) we are in.
    i1 = (x0 > y0).astype(np.int32)
    j1 = 1 - i1  # complement

    x1 = x0 - i1 + _G2
    y1 = y0 - j1 + _G2
    x2 = x0 - 1.0 + 2.0 * _G2
    y2 = y0 - 1.0 + 2.0 * _G2

    ii = i & 255
    jj = j & 255

    g0 = grads[perm2[ii + perm2[jj]] & (n_grad - 1)]
    g1 = grads[perm2[ii + i1 + perm2[jj + j1]] & (n_grad - 1)]
    g2 = grads[perm2[ii + 1 + perm2[jj + 1]] & (n_grad - 1)]

    def _contrib(x: np.ndarray, y: np.ndarray, g: np.ndarray) -> np.ndarray:
        t_ = 0.5 - x * x - y * y
        t_ = np.maximum(t_, 0.0)
        t4 = t_ * t_ * t_ * t_
        return t4 * (g[..., 0] * x + g[..., 1] * y)

    n0 = _contrib(x0, y0, g0)
    n1 = _contrib(x1, y1, g1)
    n2 = _contrib(x2, y2, g2)

    out = 70.0 * (n0 + n1 + n2)  # Gustavson's empirical scaling
    std = out.std()
    if std > 0:
        out = out / std
    return out.astype(np.float32)
