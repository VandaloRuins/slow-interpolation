"""Author keyframes OUTSIDE the img2img chain, for `skip_keyframes` runs.

The production pipeline builds keyframes by chaining: each frame is a small
img2img step from the previous one, which is what produces the drift quality but
also means the composition comes from the LoRA's prior rather than from you.

This renders each keyframe INDEPENDENTLY at a fixed seed, varying only the part
of the prompt you want to drift. Same seed plus same subject text keeps the
composition close; only the named term moves. The result is a staged keyframe
set you can hand to the pipeline with `skip_keyframes: true`.

    python tools/stage_keyframes.py --config examples/configs/course-of-empire/desolation.yaml \\
        --name t1_staged --count 7 --seed 42

Writes to `<output_dir>/staging/<name>/keyframes/0000.png ...`.

The drift ramp is built from the config's own prompts: prompt[0] is the A state,
prompt[1] the B state. Keyframes ramp A -> B -> A across `count` frames by
SLERPing the text embeddings, exactly as the chain does, but with no image
feedback between frames.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch

# Run from anywhere: tools/ is not a package and src/ is not installed.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.slow_interpolation.config import load_pipeline_config
from src.slow_interpolation.keyframes import (
    _format_prompt,
    _random_noise_image,
    load_sdxl_pipeline,
    unload_sdxl_pipeline,
)
from src.slow_interpolation.prompts import encode_prompt, slerp_embeddings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--name", required=True, help="staging name, becomes output_name")
    ap.add_argument("--count", type=int, default=7)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    cfg = load_pipeline_config(args.config)
    out = cfg.output_dir / "staging" / args.name / "keyframes"
    out.mkdir(parents=True, exist_ok=True)

    pipe = load_sdxl_pipeline(cfg)
    style, res, borders = cfg.style, cfg.resolution, cfg.borders

    # Encode the A and B states once; keyframes are SLERPs between them.
    encoded = []
    for p in cfg.subject.prompts[:2]:
        full = _format_prompt(style.prefix, " ".join(p.prompt.split()), style.suffix)
        neg = p.negative_prompt if p.negative_prompt is not None else style.negative_prompt
        encoded.append(encode_prompt(pipe, full, neg, cfg.sampling.guidance_scale))
    (eA, pA, nA, npA), (eB, pB, nB, npB) = encoded

    canvas = _random_noise_image(res.width, res.height)
    print(f"staging {args.count} independent keyframes at seed {args.seed} -> {out}")
    for i in range(args.count):
        # Triangular ramp A -> B -> A so the set closes on itself.
        half = (args.count - 1) / 2
        t = (i / half) if i <= half else (2 - i / half)
        e = slerp_embeddings(eA, eB, t)
        pooled = slerp_embeddings(pA, pB, t)

        # Fixed seed on EVERY frame: same noise, so composition stays put and
        # only the conditioning moves. This is what makes independently
        # rendered keyframes coherent enough to interpolate.
        # `load_sdxl_pipeline` returns an Img2Img pipeline, which has no
        # width/height and requires an image. strength=1.0 fully replaces the
        # input with noise, so this IS text2img; the input only sets the size.
        gen = torch.Generator(device="cuda").manual_seed(args.seed)
        img = pipe(
            image=canvas,
            strength=1.0,
            prompt_embeds=e,
            pooled_prompt_embeds=pooled,
            negative_prompt_embeds=nA,
            negative_pooled_prompt_embeds=npA,
            num_inference_steps=cfg.sampling.num_inference_steps,
            guidance_scale=cfg.sampling.guidance_scale,
            generator=gen,
            crops_coords_top_left=borders.crops_coords_top_left,
            original_size=borders.original_size,
        ).images[0]
        img.save(out / f"{i:04d}.png")
        print(f"  {i:04d}.png  t={t:.2f}")

    unload_sdxl_pipeline(pipe)
    print(f"\nupload with:\n  modal volume put slow-interp-outputs "
          f"{out.as_posix()} staging/{args.name}/keyframes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
