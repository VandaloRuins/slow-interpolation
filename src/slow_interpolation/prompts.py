"""SDXL prompt-embedding helpers.

`slerp_embeddings` interpolates between two prompt embeddings along the great
circle of their normalized vectors (spherical linear interpolation), with a
linear fallback when the two embeddings are nearly parallel. Used during inter-
segment transitions to make the visual content shift smoothly rather than swap.

`encode_prompt` wraps the SDXL pipeline's `encode_prompt` and returns the
prompt embeds plus the negative embeds when CFG is in use.
"""

from __future__ import annotations

import torch


def slerp_embeddings(
    embed_a: torch.Tensor,
    embed_b: torch.Tensor,
    t: float,
    dot_threshold: float = 0.9995,
) -> torch.Tensor:
    """Spherical linear interpolation between two prompt embeddings."""
    a_flat = embed_a.reshape(-1).float()
    b_flat = embed_b.reshape(-1).float()
    dot = torch.dot(a_flat, b_flat) / (torch.norm(a_flat) * torch.norm(b_flat))
    if abs(dot.item()) > dot_threshold:
        result = (1 - t) * embed_a + t * embed_b
    else:
        theta_0 = torch.acos(dot.clamp(-1, 1))
        sin_theta_0 = torch.sin(theta_0)
        theta_t = theta_0 * t
        s0 = torch.sin(theta_0 - theta_t) / sin_theta_0
        s1 = torch.sin(theta_t) / sin_theta_0
        result = s0 * embed_a + s1 * embed_b
    return result.to(embed_a.dtype)


def encode_prompt(
    pipe,
    prompt_text: str,
    neg_text: str = "",
    guidance_scale: float = 1.5,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor | None, torch.Tensor | None]:
    """Encode a prompt + optional negative through an SDXL Img2Img pipeline.

    Returns `(prompt_embeds, pooled, neg_embeds, neg_pooled)`. The neg pair is
    None when CFG is disabled (`guidance_scale <= 1.0`).
    """
    use_cfg = guidance_scale > 1.0
    prompt_embeds, neg_embeds, pooled, neg_pooled = pipe.encode_prompt(
        prompt=prompt_text,
        prompt_2=prompt_text,
        device=pipe.device,
        num_images_per_prompt=1,
        do_classifier_free_guidance=use_cfg,
        negative_prompt=neg_text if neg_text else None,
    )
    if use_cfg:
        return prompt_embeds, pooled, neg_embeds, neg_pooled
    return prompt_embeds, pooled, None, None
