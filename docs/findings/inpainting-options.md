# Style-aware inpainting solutions, ranked

For the dataset workflow: paint a mask over a signature, a watermark, a non-floral subject (a cat in the corner of a still life, a partial figure in a garden scene), or an auction-house lot number; have an AI fill the masked region so it matches the surrounding painting's style and texture seamlessly.

Use case constraints that drive the ranking:
- **Style fidelity to the surrounding pixels** is paramount. We are removing artefacts from impressionist oil paintings; the fill must look like the artist's own surrounding brushwork, not generic AI smoothing.
- **Brush mask input** required. We hand-paint the mask in the browser.
- **Custom LoRA support** is the killer feature once the Renoir LoRA exists: inpaint with `rfl` style intrinsic.
- **API-first**. We want to wire this into the gallery's manual cropper modal, not depend on a desktop GUI.
- **Reasonable price per image** so a 50-image cleanup pass is not a budget conversation.

## Tier 1 — recommended for this project

### 1. fal.ai · FLUX.1 [dev] Inpainting with LoRAs

Endpoint: [`fal-ai/flux-lora/inpainting`](https://fal.ai/models/fal-ai/flux-lora/inpainting).

**Pros**
- Native LoRA loading at inference. Pass the trained Renoir LoRA URL (CivitAI hosts safetensors directly) and a `rfl, ...` prompt; the fill carries Renoir's style intrinsically. This is the single biggest leverage point for our project.
- Mask + image + prompt API, exactly what we need. JPEG / PNG / WebP all accepted.
- Pricing $0.035 per megapixel. A 1344x768 inpaint is $0.036; a 2000x2000 is $0.14.
- FLUX edge-blending is the current SOTA. Independent benchmarks score Flux Fill ahead of Ideogram 2.0 and SDXL Inpainting in "respect for the surrounding scene during masking and replacement".
- Multiple LoRAs can be stacked per request (Renoir + a "remove signature" LoRA, for instance).
- HTTP REST endpoint, easy to call from a Node/Python script behind the gallery cropper.

**Cons**
- Requires the Renoir LoRA to exist first. Without it, falls back to FLUX's default impressionist understanding, which is decent but not Renoir-specific.
- FLUX [dev] license restricts certain commercial uses; check the licence for objkt labs release context. The [pro] variant has clearer commercial terms but costs more.
- LoRA loading adds 3 to 5 seconds of cold-start latency per first call after idle.

**Best for:** post-Renoir-LoRA, all in-dataset cleanup (signatures, lot numbers, cat in the corner of `fleurs-et-chats`, the maillol-statuette study in some Renoir prints). Default tier-1 choice.

### 2. fal.ai · FLUX.1 [pro] Fill

Endpoint: [`fal-ai/flux-pro/v1/fill`](https://fal.ai/models/fal-ai/flux-pro/v1/fill).

**Pros**
- Same FLUX-grade edge blending as the [dev] LoRA variant, slightly stronger base model.
- Clearer commercial-use licensing.
- $0.05 per megapixel.
- No LoRA management overhead. Useful before the Renoir LoRA is trained.

**Cons**
- No LoRA support. You drive style via prompt only ("oil painting, impressionist, broken colour, soft scumbled background"); fidelity to Renoir specifically is "good" but not "Renoir's own hand".
- Slightly more expensive per megapixel than the [dev] LoRA variant.

**Best for:** the pre-Renoir-LoRA cleanup window. Use this right now (May 2026) for any urgent dataset polish. Migrate to tier 1.1 once `Renoir_Flowers_epoch_10.safetensors` exists.

### 3. fal.ai · FLUX.1 Krea [dev] Inpainting with LoRAs

Endpoint: [`fal-ai/flux-krea-lora/inpainting`](https://fal.ai/models/fal-ai/flux-krea-lora/inpainting).

**Pros**
- Krea variant is fine-tuned for "more painterly, less photographic" output. Closer aesthetic to oil painting out of the box.
- Same LoRA support and pricing as tier 1.

**Cons**
- Narrower base distribution than vanilla FLUX [dev]; for some non-painterly subjects (a clean transparent vase, a porcelain glaze) it under-renders detail.

**Best for:** if you want the model to lean impressionist by default even before any LoRA loads. Worth A/B-testing against tier 1 on the first 5 images.

## Tier 2 — viable, lower priority

### 4. Replicate · `batouresearch/sdxl-controlnet-lora-inpaint`

**Pros**
- SDXL with ControlNet + LoRA support, the same architecture our Renoir LoRA is trained against. **Native compatibility**: no architecture mismatch between training data and inference.
- ControlNet branch lets us pass Canny / depth / segmentation to keep the inpaint geometrically locked to the surrounding composition. Particularly useful for the cat-in-corner removal case where there are real edges that should not bleed into the fill.
- Replicate hosts your LoRA from a public URL, same as fal.ai.

**Cons**
- SDXL inpainting is one generation behind FLUX on edge blending. You can see the seam slightly more often than with FLUX Fill.
- Pricing is per-second of compute; a typical SDXL inpaint runs $0.01 to $0.03 per call but cold starts cost extra.
- Replicate's API surface is more verbose than fal.ai's.

**Best for:** if your Renoir LoRA produces FLUX-incompatible outputs (unlikely but possible) or if you specifically need ControlNet guidance to lock geometry.

### 5. fal.ai · `rundiffusion-fal/juggernaut-flux-lora/inpainting`

**Pros**
- Juggernaut-tuned FLUX, "richer colours and enhanced realism" per the model card. The richer-colour bias is a plus for Renoir's saturated palette.
- Drop-in replacement for FLUX [dev] inpainting with the same LoRA API.

**Cons**
- Juggernaut leans photographic. Risk of pushing inpainted regions toward photoreal versus oil-painting surface.
- Same FLUX [dev] licence considerations.

**Best for:** A/B test against tier 1. Pick whichever gives cleaner brushwork on the validation hold-out.

## Tier 3 — viable but not the right fit here

### 6. OpenAI gpt-image-1 (DALL·E inpainting)

**Pros**
- Best-in-class for prompt fidelity overall. Reliable, robust API.
- Strong at "complete the scene plausibly". Good when surrounding context is information-rich.

**Cons**
- **No custom LoRA / style loading.** Cannot inject the Renoir LoRA. You can prompt-engineer "Renoir-style oil painting" but the base distribution is photoreal-leaning; you get a tasteful approximation, not Renoir's hand.
- Pricing: ~$0.04 to $0.17 per call depending on quality tier.
- Output is post-processed for "safety / plausibility" which can flatten brushwork detail.

**Best for:** generic image touch-ups outside this dataset pipeline. Not for Renoir-specific work.

### 7. Stability AI · Stable Diffusion 3.5 Large Inpainting

**Pros**
- Direct API from Stability. Predictable pricing and rate limits.
- SD3.5 base supports custom LoRA via their `style transfer` add-on, though the LoRA architecture differs from SDXL.

**Cons**
- LoRA support is partial — the Renoir LoRA trained for SDXL is not directly compatible with SD3.5; you would need a separate Renoir LoRA training run.
- Edge blending in our hands is noticeably weaker than FLUX Fill.

**Best for:** if your project standardises on SD3.5. We do not.

### 8. Ideogram 3 · Magic Fill

**Pros**
- Strong text-rendering accuracy (95 % per public benchmarks). Useful if the masked region needs to contain text (e.g. you want to preserve a Renoir-style signature instead of removing it).
- Pleasant UX in their own web tool.

**Cons**
- No LoRA support. Cannot match Renoir specifically.
- API surface is younger than fal.ai's; less ergonomic for batch dataset work.
- Optimised for photographic / illustrative content; oil-painting brushwork is not a strong suit.

**Best for:** non-painting projects where text legibility matters. Not for this dataset.

### 9. Adobe Firefly Fill

**Pros**
- Enterprise-friendly licensing. Outputs cleared for commercial use with indemnification.
- Tight integration with Photoshop if Luca wants a manual workflow on a few images.

**Cons**
- API access is gated and pricing is enterprise-tier; over-engineered for a 50-image cleanup pass.
- No custom LoRA support.
- Aesthetic bias toward "polished commercial illustration", further from Renoir than FLUX.

**Best for:** if you ever ship for an enterprise client that requires content-provenance certification.

## Tier 4 — local / self-hosted

### 10. ComfyUI · BrushNet (SDXL) + Renoir LoRA + IP-Adapter

**Pros**
- Runs on your own GPU, no per-call cost after the model is downloaded.
- Maximum control. You can stack: Renoir LoRA for style, IP-Adapter for "match the rest of this exact painting", ControlNet for geometric lock, BrushNet's dual-branch model for the actual inpainting.
- Reproducible: same seed + same workflow = byte-identical output. Important for the kind of slow-iteration practice this project values.
- No data leaves the machine. Relevant for any in-progress works that should not be uploaded.

**Cons**
- Setup is heavy: ComfyUI install + node packs + 30 to 50 GB of weights. Worth doing once, painful the first time.
- 8 GB VRAM is tight for SDXL inpainting + LoRA + ControlNet stacked; 12 GB is comfortable, 16 GB is fine. Luca's GPU machine for visuals (per `project_visual_gpu.md`) should handle it.
- No HTTP API by default. You can expose ComfyUI's REST endpoint and call it from the gallery cropper, but it is one more service to babysit.

**Best for:** the second-pass workflow after FLUX cleans the bulk. For the 3 to 5 most-important paintings of the release, where Luca wants reproducible byte-identical fills he can iterate on.

### 11. ComfyUI · FLUX Fill + ControlNet + LoRA (local)

**Pros**
- Same architecture as tier 1 but local. No per-call cost.
- FLUX Fill weights are available; the LoRA loader pattern is identical to fal.ai's.

**Cons**
- FLUX is bigger than SDXL. 24 GB VRAM is comfortable; 16 GB is tight; 12 GB will OOM.
- Same setup heaviness as tier 10.

**Best for:** if Luca's GPU machine has 24 GB and he wants tier 1's quality without the per-call cost.

## Comparison table

| Tool | LoRA | Brush mask | Style fit (Renoir) | Edge blend | Local | $ per typical call | API ergonomics |
|---|---|---|---|---|---|---|---|
| 1. fal · FLUX [dev] LoRA Inpaint | YES | yes | best (with LoRA) | best | no | $0.03 to $0.14 | excellent |
| 2. fal · FLUX [pro] Fill | no | yes | good (prompt only) | best | no | $0.05 to $0.20 | excellent |
| 3. fal · FLUX Krea LoRA Inpaint | YES | yes | very good | best | no | $0.03 to $0.14 | excellent |
| 4. Replicate · SDXL ControlNet LoRA | YES | yes | very good | good | no | $0.01 to $0.03 | ok |
| 5. fal · Juggernaut FLUX LoRA | YES | yes | very good | best | no | $0.03 to $0.14 | excellent |
| 6. OpenAI gpt-image-1 | no | yes | fair | very good | no | $0.04 to $0.17 | excellent |
| 7. Stability SD3.5 Inpaint | partial | yes | fair (different arch) | good | no | $0.02 to $0.08 | good |
| 8. Ideogram 3 Magic Fill | no | yes | fair | good | no | $0.02 to $0.05 | ok |
| 9. Adobe Firefly | no | yes | low | very good | no | enterprise | enterprise |
| 10. ComfyUI BrushNet + LoRA | YES | yes | very good | very good | YES | free after setup | self-hosted |
| 11. ComfyUI FLUX Fill local | YES | yes | best (with LoRA) | best | YES | free after setup | self-hosted |

## Recommended path for this project

**Phase 1 (now, pre-Renoir-LoRA):** start with tier 2 (fal.ai FLUX [pro] Fill). No LoRA management. Wire it into the gallery's cropper modal as a "fill masked region" button that POSTs `{image, mask, prompt}` to the fal endpoint and writes the result back over the file. Use a generic Renoir-leaning prompt: `"oil painting, impressionist, soft scumbled background, broken colour, no text, no signature"`.

**Phase 2 (post-Renoir-LoRA):** swap the endpoint to tier 1 (fal.ai FLUX [dev] Inpainting with LoRAs). Pass the CivitAI URL of `Renoir_Flowers_epoch_10.safetensors`, prompt prefixed with `rfl, ...`. Same gallery hook, different endpoint URL. This is where the style matching becomes near-indistinguishable from the artist's own hand.

**Phase 3 (release polish):** for the 3 to 5 most-important paintings of the objkt labs release, drop into tier 11 (local ComfyUI + FLUX Fill + Renoir LoRA + IP-Adapter referencing the rest of the painting). Iterate at zero marginal cost; pick the best seed; lock the result. The slow-interpolation project's aesthetic of "the image is allowed to take its time" applies to the cleanup pass too — sometimes the right inpaint takes 20 seeds, and that is fine when each seed costs nothing.

## Gallery integration sketch

This is the proposed extension to the gallery cropper modal. Implement when needed; not part of this task.

```
[cropper modal: existing crop rect + rotate buttons]
  +----------------------------------------------+
  | ✎ Paint mask        ⊕ Run inpaint            |
  +----------------------------------------------+
```

- `✎ Paint mask` toggles the modal into mask-paint mode: a canvas overlay where the user paints with the mouse / stylus. Brush size + opacity + eraser. Output: a 1-channel PNG, white = mask, black = keep, same dimensions as the visible image.
- `⊕ Run inpaint` POSTs the current cropped + rotated image and the mask to the configured endpoint (fal.ai by default), receives the filled image, writes it back over `raw/<filename>.jpg`. Cache buster so the gallery card re-renders.
- A small prompt input lives next to the button. Default: `"rfl, oil painting, impressionist, soft scumbled background, broken colour, continue the surrounding texture"`. Override per image when needed.
- Audit: save `{filename, mask_sha1, prompt, seed, endpoint, timestamp}` next to the file. Same audit pattern as `processed.json`.

Build this when the Renoir LoRA exists. Until then, the cropper alone covers the artefact-removal cases that are amenable to cropping (frames, white borders, watermarks at edges). Inpainting becomes essential when the artefact is INSIDE the painting (a cat we want gone, an auction lot stamp in the middle, a partial figure to remove from a garden scene).

Sources:
- [FLUX.1 [dev] Inpainting with LoRAs · fal.ai](https://fal.ai/models/fal-ai/flux-lora/inpainting)
- [FLUX.1 [pro] Fill · fal.ai](https://fal.ai/models/fal-ai/flux-pro/v1/fill/api)
- [FLUX.1 Krea [dev] Inpainting with LoRAs · fal.ai](https://fal.ai/models/fal-ai/flux-krea-lora/inpainting)
- [Juggernaut Flux LoRA Inpainting · fal.ai](https://fal.ai/models/rundiffusion-fal/juggernaut-flux-lora/inpainting/api)
- [sdxl-controlnet-lora-inpaint · Replicate](https://www.aimodels.fyi/models/replicate/sdxl-controlnet-lora-inpaint-batouresearch)
- [BrushNet for ComfyUI · RunComfy](https://www.runcomfy.com/comfyui-nodes/ComfyUI-BrushNet)
- [Inpainting Quality benchmarks 2026 · MyAIForce](https://myaiforce.com/flux-tools-workflow/)
- [AI Image Editing Quality Shootout · skywork.ai](https://skywork.ai/blog/photoshop-vs-midjourney-vs-dalle-vs-ideogram-vs-sdxl-comparison/)


---
*Did you reproduce this and observe something different? Counter-findings welcome. See [CONTRIBUTING.md](../../CONTRIBUTING.md) shape 4 and the [finding issue template](../../.github/ISSUE_TEMPLATE/finding.md).*
