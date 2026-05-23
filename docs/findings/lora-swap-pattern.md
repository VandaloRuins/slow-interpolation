# Two-pass LoRA swap pattern for sequential style composition

Date: 2026-05-18.
Scope: when a single render pipeline must apply TWO different LoRAs to TWO different spatial regions of one image without entanglement. Validated in [`../../cloud/compositing_sketch.py`](../../cloud/compositing_sketch.py) for the Renoir-background + Soutine-figure compositing use case.

Companion docs:
- The compositing workstream's design carries the artistic motivation (two painters meeting only at a mask feather band) and the promotion path (simultaneous dual-LoRA + Attention Couple regional cross-attention) that supersedes this pattern when ready. Workstream log lives in the maintainer's private planning folder during v0.1; surfaces publicly in v0.2 as `docs/manual/compositing.md`.
- [`expressionist-style-preset.md`](expressionist-style-preset.md): the trainer preset that produced the Soutine LoRA the swap uses.

## The pattern

Sequential LoRA swap inside a single Modal GPU session:

1. Build SDXL Lightning pipeline once.
2. Load LoRA A, fuse at scale, run pass 1 (e.g. txt2img background).
3. **`unfuse_lora()` then `unload_lora_weights()`** before loading LoRA B.
4. Load LoRA B, fuse at scale, run pass 2 (e.g. SDXL inpaint figure).
5. Optionally share UNet across pipelines via `StableDiffusionXLInpaintPipeline.from_pipe(txt2img_pipe)`.

## Why `unfuse_lora()` is mandatory between swaps

`fuse_lora()` MERGES the LoRA's delta-W into the base UNet weights. After fusing, `unload_lora_weights()` frees the LoRA adapter state-dict but the base UNet remains modified.

If you skip the unfuse and just unload + load + fuse the next LoRA, the second fusion stacks on top of an already-modified UNet. The result is a non-zero blend of both LoRAs in the second pass, defeating any spatial region separation.

The correct order is:
```python
pipe.load_lora_weights(LORA_A)
pipe.fuse_lora(lora_scale=scale_A)
# pass 1 renders here

pipe.unfuse_lora()           # restore base UNet weights
pipe.unload_lora_weights()   # free state-dict

pipe.load_lora_weights(LORA_B)
pipe.fuse_lora(lora_scale=scale_B)
# pass 2 renders here, cleanly LoRA-B-only
```

`unfuse_lora` requires the LoRA weights to still be loaded (so it has the delta-W reference to subtract). Don't unload before unfusing.

**SDXL Lightning is a special case**: it lives in the UNet permanently across the whole session. Load Lightning → fuse → unload state-dict, never unfuse. The base UNet for the rest of the session is "base + Lightning"; subsequent LoRA fuse + unfuse cycles operate cleanly on top of that constant.

## Pipeline sharing via `from_pipe`

When the two passes need DIFFERENT pipeline classes (here: txt2img → inpaint), use diffusers' `from_pipe`:

```python
inpaint_pipe = StableDiffusionXLInpaintPipeline.from_pipe(txt2img_pipe, vae=txt2img_pipe.vae)
```

`from_pipe` shares all components by reference: UNet, VAE, text encoders, tokenizers. The LoRA fusion on `txt2img_pipe.unet` propagates to `inpaint_pipe` because they hold the same UNet object.

This avoids reloading SDXL base (~5s) and re-applying Lightning (~2s) for the second pass. Cost: zero, since references not copies.

### Always pass non-standard VAEs explicitly as a kwarg

`from_pipe` walks `pipe.components` to assemble the new pipeline's required components. In diffusers 0.38, a TAESD `AutoencoderTiny` attached to the source pipe via either `pipe.vae = AutoencoderTiny.from_pretrained(...)` (direct attr) OR `pipe.register_modules(vae=AutoencoderTiny.from_pretrained(...))` does NOT appear in the walked `components` dict. `from_pipe` then raises:

```
ValueError: Pipeline <...InpaintPipeline> expected
[..., 'vae'], but only {..., no vae ...} were passed
```

The two patterns that should-but-don't work: `__setattr__` skips the `_modules` bookkeeping diffusers uses, and `register_modules` apparently skips a TAESD-specific code path (the class is not the canonical `AutoencoderKL`). Empirically tested both during the `compositing_sketch.py` cold-run verification on 2026-05-18.

The fix that works: pass the VAE explicitly as a kwarg to `from_pipe`. The kwarg-pass bypasses the component-walk entirely:

```python
inpaint_pipe = StableDiffusionXLInpaintPipeline.from_pipe(
    txt2img_pipe,
    vae=txt2img_pipe.vae,  # explicit, required for non-standard VAEs
)
```

Apply this pattern whenever you swap an SDXL pipeline's standard `AutoencoderKL` for `AutoencoderTiny` (or any other VAE class), then call `from_pipe`. Default `AutoencoderKL` works without the kwarg because diffusers' component-walk recognises it as canonical.

**Discovery cost**: 1 failed Modal cold-run (~$0.005). Catalogued so the next agent does not re-derive.

**Captured in**: [`../../cloud/compositing_sketch.py`](../../cloud/compositing_sketch.py) inline comment at the `from_pipe` call site.

## Generator re-seeding for deterministic inpaint

The SDXL inpaint pipeline uses the generator to sample noise INSIDE the mask. To get reproducible composites across re-runs with the same seed:

```python
generator = torch.Generator(device="cuda").manual_seed(seed)
# ... pass 1 consumes generator state ...
generator = torch.Generator(device="cuda").manual_seed(seed)  # re-instantiate
# ... pass 2 starts with fresh generator at same seed ...
```

If you reuse the same generator object across passes without re-instantiating, the pass-2 noise depends on pass-1's generator consumption pattern. Re-seeding makes pass-2 noise independent of pass-1 implementation details.

## Mask convention

SDXL inpaint pipeline expects an L-mode (grayscale) PIL Image where:
- White (255) = paint here with the LoRA-B prompt
- Black (0) = preserve the underlying pass-1 background pixel
- Greyscale values in between = soft blend, weighted by `strength` parameter

The compositing-sketch entrypoint enforces the mask size equals render size; any mismatch is a fail-fast error before GPU work begins.

## `inpaint_strength` (the `strength` parameter)

SDXL inpaint's `strength` controls how aggressively the masked region is repainted:
- `1.0`: full repaint inside the mask, ignoring the underlying pass-1 content entirely
- `0.85` (compositing-sketch default): strong repaint with mild preservation of underlying structure (figure inherits pose suggestions from any structure already in the background, but the painter style overrides)
- `0.5`: half-blend; the masked region looks like a 50/50 mix of pass-1 background and pass-2 prompt
- `0.0`: no change inside the mask

For two-painter composition where painter A's style must NOT leak into painter B's region, default to 0.85 or higher. Lower strength leaks the underlying register through.

## Performance envelope on Modal L40S

Measured in `compositing_sketch.py`:

| Step | Cold | Warm |
|---|---|---|
| Container start + image pull | ~25-30s | ~3-5s (snapshot warm) |
| SDXL base + Lightning load | ~5-8s | ~5s |
| LoRA A load + fuse | ~1-2s | ~1s |
| Pass 1 (4-step Lightning txt2img at 832x1216) | ~3-4s | ~3s |
| Unfuse + unload + LoRA B load + fuse | ~2-3s | ~2s |
| Pass 2 (4-step Lightning inpaint) | ~3-4s | ~3s |
| Triptych compose + write | ~0.5s | ~0.5s |
| Volume commit | ~1-2s | ~1s |
| **Total (cold)** | ~45-55s | ~17-22s |

Cost on L40S at $1.95/hr: ~$0.025 cold, ~$0.012 warm per sketch.

## When NOT to use this pattern

- **Same LoRA, two passes (e.g. img2img refinement)**: just keep the LoRA fused; no swap needed.
- **Two LoRAs but full-frame blend (not regional)**: fuse both with summed scales OR use diffusers' multi-adapter API at call-time. No need for the unfuse dance.
- **Production multi-region rendering at scale**: this pattern is O(N) in pipeline build cost per render. For >100 sketches in a batch, promote to dual-LoRA + Attention Couple (regional cross-attention) per the compositing workstream's promotion path (lands publicly in v0.2). The sketch entrypoint is a baseline reference, not a production renderer.
- **Realtime / interactive**: the swap costs ~2-3s per cycle. Unacceptable for interactive UIs; OK for offline batch.

## What this finding does NOT claim

- Sequential swap is artistically equivalent to dual-LoRA regional attention. It is NOT; the swap can only enforce hard mask boundaries, while dual-LoRA can blend continuously. Use this pattern when hard boundaries are desired (the Renoir / Soutine artistic constraint) or when the dual-LoRA infrastructure is not yet built.
- The pattern generalizes to >2 LoRAs. With 3+ LoRAs you'd need >2 swap cycles per render, multiplying overhead. Probably promote to multi-adapter or regional attention.
- LoRA fusion mathematics are exactly invertible across `unfuse_lora`. Floating-point precision means a fuse-unfuse-refuse cycle may not be bit-exact with a single fuse. Empirically the drift is negligible for one cycle; >5 cycles per session has not been tested.

## Reproducing the pattern

Minimal example (5 LoC after pipeline build):

```python
pipe.load_lora_weights("path/to/lora_a.safetensors")
pipe.fuse_lora(lora_scale=0.85)
out_a = pipe(prompt=prompt_a, ...).images[0]

pipe.unfuse_lora()
pipe.unload_lora_weights()

pipe.load_lora_weights("path/to/lora_b.safetensors")
pipe.fuse_lora(lora_scale=0.85)
out_b = pipe(prompt=prompt_b, ...).images[0]
```

Full implementation including SDXL inpaint pipeline sharing: [`../../cloud/compositing_sketch.py`](../../cloud/compositing_sketch.py).
