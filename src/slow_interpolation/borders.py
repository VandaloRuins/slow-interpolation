"""Border-artifact suppression.

Two mechanisms applied together to stop SDXL (and the fresco LoRA in
particular) from painting a decorative arch around the frame:

1. `crops_coords_top_left` SDXL micro-conditioning, set on the call site
   inside `keyframes.py`. Tells the model the generation is a center-crop of
   a larger canvas, which correlates in training data with frameless interior
   content. Lives in the call, not here.

2. `edge_suppression_callback` (this module): a `callback_on_step_end` hook
   that, at every denoising step, blends the outer few latent pixels toward a
   mirror-padded interior, with a quadratic feather. Belt-and-suspenders.

Tested without LoRA and with LoRA at scale 0 to confirm both contribute
independently (legacy `legacy/choire-v2/research/video-generation-iterations.md`
Obstacle 5).
"""

from __future__ import annotations

import torch


def make_edge_suppression_callback(px: int = 3, strength: float = 0.3):
    """Build a `callback_on_step_end` that nudges latent edges toward mirror-
    padded interior at `strength` blend, with a quadratic feather over `px`
    latent pixels.
    """

    def callback(pipe, step, timestep, callback_kwargs):
        latents = callback_kwargs["latents"]
        _, _, H, W = latents.shape

        # Quadratic feather: 1.0 = keep original, 0.0 at extreme edge.
        mask = torch.ones(1, 1, H, W, device=latents.device, dtype=latents.dtype)
        for i in range(px):
            val = (i / max(1, px)) ** 2
            val_t = torch.tensor(val, device=latents.device, dtype=latents.dtype)
            mask[:, :, i, :] = torch.minimum(mask[:, :, i, :], val_t)
            mask[:, :, H - 1 - i, :] = torch.minimum(mask[:, :, H - 1 - i, :], val_t)
            mask[:, :, :, i] = torch.minimum(mask[:, :, :, i], val_t)
            mask[:, :, :, W - 1 - i] = torch.minimum(mask[:, :, :, W - 1 - i], val_t)

        blend_mask = (1.0 - mask) * strength

        # Mirror-pad from interior: reflect inner band outward so the model
        # sees consistent local texture, not a hard edge or a flat fill.
        interior = latents.clone()
        interior[:, :, :px, :] = torch.flip(latents[:, :, px : 2 * px, :], dims=[2])
        interior[:, :, -px:, :] = torch.flip(latents[:, :, -2 * px : -px, :], dims=[2])
        interior[:, :, :, :px] = torch.flip(latents[:, :, :, px : 2 * px], dims=[3])
        interior[:, :, :, -px:] = torch.flip(latents[:, :, :, -2 * px : -px], dims=[3])

        callback_kwargs["latents"] = latents * (1.0 - blend_mask) + interior * blend_mask
        return callback_kwargs

    return callback
