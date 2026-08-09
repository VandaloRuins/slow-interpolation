"""Masked directional motion inside the img2img feedback loop.

The pipeline makes still pictures whose LIGHT drifts. This module adds a second,
independent axis: a region of the frame that physically MOVES while the rest
stays put. Falling water against still rock is the motivating case.

## Why this works, and why RIFE is the asset rather than the obstacle

RIFE estimates per-pixel optical flow between consecutive keyframes and warps
along it. If the water is displaced between two keyframes and the rock is not,
the flow field is non-zero over the water and *exactly zero* over the rock. So
the interpolator advances the water smoothly and leaves the rock untouched and
sharp. The contrast is not something we have to engineer; it is what a per-pixel
flow interpolator does for free.

This inverts the usual reading of RIFE in this repo. It has been treated as a
source of blur, and it is, but only when consecutive keyframes disagree in ways
flow cannot explain (a reinvented skyline, a wandering waterline). A clean
translation is the one kind of disagreement optical flow handles perfectly.

## Where it plugs in

`keyframes.py` already routes every frame through `noise_walker.blend(img, pct)`
before img2img. That is an image-to-image hook on the feedback loop, so a
displacement belongs at exactly the same seam and nothing architectural changes.
Order matters: displace FIRST, then blend noise, then diffuse. Displacing after
the noise blend would drag the noise field around with the water and defeat the
temporal-persistence the walk exists to provide.

## The mask is free

The depth map already separates the two regions, because we deliberately leave
water black (far, unconstrained) and draw rock bright (near). So the moving
region is just the dark part of the control map we are already passing. No new
asset, no hand-painted mask.

The mask is feathered, because a hard boundary between displaced and static
pixels leaves a visible seam that img2img then paints INTO the picture as a
crack rather than smoothing away.

## What this does not do

It translates a region. It does not deform one. A real wave crest changes shape
as it advances, and a rigid translation of it will read as a sliding sheet. The
img2img repaint at moderate strength reshapes it somewhat, which may be enough;
if it is not, the fix is a non-uniform displacement field rather than a scalar,
which this signature deliberately leaves room for.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter


def build_motion_mask(
    control: Image.Image,
    size: tuple[int, int],
    threshold: int = 60,
    feather: int = 24,
    invert: bool = False,
) -> np.ndarray:
    """Float mask in [0, 1], 1 where pixels should move.

    Reads the DARK region of a depth map as the moving region, since that is
    where the map already says "far, unconstrained" and where water lives by
    the convention this project settled on after v4.

    `feather` is in pixels and is applied as a blur on the binary mask, so the
    displacement fades in across the boundary instead of stepping.
    """
    g = control.convert("L").resize(size, Image.LANCZOS)
    a = np.asarray(g, dtype=np.float32)
    m = (a >= threshold) if invert else (a < threshold)
    mask = Image.fromarray((m.astype(np.uint8) * 255))
    if feather > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(feather))
    return np.asarray(mask, dtype=np.float32) / 255.0


def displace(img: Image.Image, mask: np.ndarray, dx: int, dy: int) -> Image.Image:
    """Shift the masked region by (dx, dy) pixels; leave the rest alone.

    Vacated rows and columns are filled by edge replication rather than by
    wrapping. Wrapping would carry the plunge pool up to the lip of a fall,
    which is worse than a smear the model is about to repaint anyway: the
    vacated strip is exactly where new water should be arriving, and img2img
    invents it from the prompt.

    Positive `dy` moves DOWN, matching image coordinates.
    """
    if dx == 0 and dy == 0:
        return img
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    shifted = a
    if dy:
        shifted = np.roll(shifted, dy, axis=0)
        if dy > 0:
            shifted[:dy] = shifted[dy:dy + 1]
        else:
            shifted[dy:] = shifted[dy - 1:dy]
    if dx:
        shifted = np.roll(shifted, dx, axis=1)
        if dx > 0:
            shifted[:, :dx] = shifted[:, dx:dx + 1]
        else:
            shifted[:, dx:] = shifted[:, dx - 1:dx]
    m = mask[:, :, None]
    out = shifted * m + a * (1.0 - m)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
