# Inpainting feature: implementation plan (v2)

Plan for adding brush-mask inpainting to the dataset-curation gallery. **Priority use case (2026-05-17 update): erase signature artefacts from training images before retraining.** Original use cases (subject highlighting, watermark removal) ride on the same infrastructure.

> v1 of this plan focused on fal.ai-only and on the "highlight a non-flower subject" use case. After the first Renoir LoRA training round (CivitAI AI Toolkit, 2026-05-17) the validation renders showed signatures baked into every epoch-10 corner — a direct consequence of the 48 Sotheby's + Christie's auction-catalogue scans in the dataset, which all show Renoir's signature. The root-cause fix is dataset-side: erase signatures, retrain. This v2 expands the backend menu and rebases Phase 1 around the signature-erasure flow. v1 details preserved in git history.

Background research lives at [docs/findings/inpainting-options.md](../../../findings/inpainting-options.md).

## Scope

A "paint mask + run inpaint" workflow inside the existing gallery cropper modal. The user paints a brush mask over:

- **Signatures / monograms** (lower-right corner of auction-catalogue scans) — the prompted Phase-1 use case.
- **Auction-house watermarks / lot numbers / "Sotheby's" stamps** — same flow as signatures.
- **Non-target subjects in scenes-with-flowers** (a cat, a partial figure, a fruit bowl) — same UI, different inpaint backend.
- **Frame remnants the cropper left in** — edge cases the auto-crop missed.

The masked region is filled with style-matching content that respects the surrounding pixels. Out of scope: outpainting, multi-region simultaneous edits, video, text overlay.

## Backend research, 2026-05-17

Five candidate backends, ranked by fit for the signature-erase use case (default) and the style-fill use case (secondary).

### 1. Stability AI Erase API — recommended default for signature removal

Endpoint: `https://api.stability.ai/v2beta/stable-image/edit/erase`. Purpose-built for object removal: takes an image + mask PNG, returns the image with the masked region filled by surrounding texture. **No prompt required.**

Pros:
- Purpose-built. No prompt engineering. No style drift. The model's entire job is "continue the surrounding texture".
- Cheap: ~3 credits per call ≈ $0.03. 48 Renoir signatures → ~$1.50 total.
- Mask-precise (true PNG mask, not semantic).
- Mature API, low failure rate.
- Style-agnostic by design, which is what we want when the goal is "make this pixel region match the surrounding pixels".

Cons:
- Cannot inject Renoir style. If the surrounding pixels are bad, the fill will be bad.
- Not useful for the style-fill secondary use case (where we WANT to add Renoir style to a highlighted region).

Verdict: **Phase 1 default**. Set up first.

### 2. fal.ai FLUX [pro] Fill — recommended for style-aware fills

Endpoint: `fal-ai/flux-pro/v1/fill`. Mask + image + prompt. FLUX Fill is a dedicated inpainting model trained on masked-region completion; prompt steers the fill.

Pros:
- Higher fidelity than Stability Erase for non-trivial fills (texture continuation across complex edges, partial-subject removal).
- Prompt can request "continue the impressionist brushwork", "warm afternoon light", etc.
- Single-call API on fal.ai.

Cons:
- $0.05/MP (about 2x Stability Erase). 48 Renoir signatures → ~$2-3 total.
- Prompt sensitivity adds tuning surface.

Verdict: **Phase 2**. Fall-back when Stability Erase produces visible seams or when the masked region requires style continuity (subject removal, large mask).

### 3. fal.ai FLUX [dev] LoRA Inpainting + Renoir LoRA — recommended for style-conditioned fills

Endpoint: `fal-ai/flux-lora/inpainting`. Same as #2 but accepts a LoRA URL parameter, applied during inpainting.

Pros:
- Style-perfect for the style-fill use case: the Renoir LoRA we just trained guarantees the fill matches Renoir's brushwork.
- ~$0.035/MP (cheaper than FLUX [pro] Fill).

Cons:
- Requires publishing the Renoir LoRA to a public URL (CivitAI page once we publish it, or HuggingFace). Until then this backend is gated.
- Overkill for the signature-erase use case (background fill doesn't need style injection — the LoRA may actually try to add petals where we want plain canvas).

Verdict: **Phase 2 alternate**. Wired but used only for the "highlight a non-flower subject and replace with Renoir-style fill" use case. Not the signature-erase default.

### 4. Modal-hosted SDXL Inpaint + Renoir LoRA — recommended for "students with no API key"

Build a new `cloud/inpaint_app.py` that runs SDXL Inpainting (via `diffusers.AutoPipelineForInpainting`) on Modal L40S with the Renoir LoRA fused on top. Same pattern as `cloud/app.py` and the new `cloud/validation_renoir.py`.

Pros:
- Free per call (only Modal GPU cost, ~$0.005 per inpaint at ~3 s on L40S).
- No third-party API key needed. Students using the dataset-curation protocol on their own LoRA workstream can run this with their own Modal account.
- Same Renoir LoRA we already uploaded to `slow-interp-loras` volume.
- Style-perfect by construction.

Cons:
- More plumbing: new Modal function, new HTTP endpoint in the gallery server, new image cache invalidation.
- SDXL Inpaint at 4-step Lightning is fast but lower quality than FLUX Fill at 30 steps for hard cases.
- Mask must be aligned to SDXL bucket dimensions (1024-divisible by 8); requires server-side resize.

Verdict: **Phase 3**. The canonical workshop-student path. Ships after Phase 1 and 2 are proven on the UX side.

### 5. Gemini Nano Banana (Nano Banana 2 / Gemini 3.1 Flash Image) — NOT fit for signature erase

Per Google's docs: **the Nano Banana API does NOT support pixel masks**. Editing is entirely natural-language-driven ("change the watermark in the bottom-right corner to plain canvas, leave the rest unchanged"). The model does semantic masking internally.

Pros:
- The user already has `GOOGLE_API_KEY` set up.
- Excellent at semantic edits when the target is clearly describable.

Cons:
- No pixel-mask precision. For a 5% bottom-right corner signature, the model may interpret the natural-language localisation ambiguously and edit a larger region.
- Higher cost per edit (~$0.04 to $0.06 depending on resolution).
- We have no way to constrain the model to "ONLY touch these exact pixels".

Verdict: **Skip for the signature-erase use case.** Strong alternative for a future "stylise this highlighted subject" workflow where natural-language localisation is acceptable, but not for tight pixel-precise corner edits.

Sources: [Nano Banana image generation docs](https://ai.google.dev/gemini-api/docs/image-generation), [Google Cloud Nano Banana guide](https://cloud.google.com/blog/products/ai-machine-learning/ultimate-prompting-guide-for-nano-banana).

### Honourable mention: OpenAI gpt-image-1 edit endpoint

Mask + image input, mature reliable API, ~$0.04/image. Less style-aware than FLUX for "match surrounding painterly texture". Not differentiated enough vs Stability Erase or FLUX Fill to add as a primary backend. Document as a fallback only.

## Recommended phasing (v2)

| Phase | When | Backend | Default for | Cost per call |
|---|---|---|---|---|
| **1** | This week | **Stability AI Erase** | Signature, watermark, lot-number removal on training data | ~$0.03 |
| **2** | This week | fal.ai FLUX [pro] Fill | Non-target subject removal, large mask, hard-to-erase cases | ~$0.05 |
| **3** | After Modal-trainer cold-run validation | Modal SDXL Inpaint + Renoir LoRA | Workshop-student default; style-conditioned fills | ~$0.005 |
| **4** | After Renoir LoRA published publicly | fal.ai FLUX [dev] LoRA Inpainting | Style-fill use case with public LoRA URL | ~$0.035 |

The UI is one brush-mask tool that exposes a backend dropdown. Default backend selectable in `gallery-state.json`.

## Backend abstraction (new)

```
datasets/<name>/inpaint_backend.py
  class InpaintBackend(Protocol):
      def erase(image: PIL.Image, mask: PIL.Image, prompt: str = "") -> PIL.Image: ...

  class StabilityEraseBackend:    # Phase 1
      def __init__(api_key): ...
      def erase(image, mask, prompt=""): ...

  class FalFluxFillBackend:        # Phase 2
      def __init__(api_key, prompt_default): ...

  class ModalSDXLInpaintBackend:   # Phase 3
      def __init__(modal_function): ...

  class FalFluxLoraInpaintBackend: # Phase 4
      def __init__(api_key, lora_url, lora_scale): ...

  BACKENDS = {"stability": ..., "fal_flux_fill": ..., "modal_sdxl": ..., "fal_flux_lora": ...}
```

The gallery server has ONE `/api/inpaint` endpoint that takes a `backend` parameter, looks it up in `BACKENDS`, and dispatches.

## Architecture (updated)

```
Browser (gallery.html)                Local Python service (serve.py + inpaint_backend.py)
=====================                 ==================================================
[cropper modal, mask tool]                POST /api/inpaint
  🖌 Paint mask                              ├─ validate filename + mask
  Backend: [stability ▾]                    ├─ build PIL image + mask
  ⊕ Run inpaint ───────►                    ├─ call backend.erase(img, mask)
                                              ├─ back up raw_orig/<filename> if first time
                                              ├─ overwrite raw/<filename>
                                              └─ append inpaint_audit.jsonl
  card re-render ◄──────────────────  { status, url_with_cache_buster, backend, ms }
```

The local-service rationale carries over from v1: API keys cannot live in the browser, the output JPEG must overwrite a local file, and we already need the local HTTP server.

## Phase 1 implementation steps (Stability Erase first)

### Step 1. Add Stability AI Erase backend

`datasets/<name>/inpaint_backend.py`:

```python
import os, io, requests
from pathlib import Path
from PIL import Image
from dotenv import load_dotenv

load_dotenv(Path("C:/Users/lucaa/OneDrive/Desktop/Choire-v2/.env"))

class StabilityEraseBackend:
    URL = "https://api.stability.ai/v2beta/stable-image/edit/erase"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ["STABILITY_API_KEY"]

    def erase(self, image: Image.Image, mask: Image.Image, prompt: str = "") -> Image.Image:
        # prompt is ignored: Stability Erase has no prompt input
        img_buf = io.BytesIO()
        image.save(img_buf, format="PNG")
        img_buf.seek(0)
        mask_buf = io.BytesIO()
        mask.save(mask_buf, format="PNG")
        mask_buf.seek(0)
        r = requests.post(
            self.URL,
            headers={"Authorization": f"Bearer {self.api_key}", "Accept": "image/*"},
            files={"image": img_buf, "mask": mask_buf},
            data={"output_format": "png"},
            timeout=120,
        )
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGB")
```

### Step 2. Wire the gallery server's `/api/inpaint` endpoint

Extend `datasets/<name>/serve.py` (currently `ThreadingHTTPServer + SimpleHTTPRequestHandler`) with a new POST route. Keep the existing routes (`/api/state`, `/api/remove`, `/api/restore`) untouched. The handler:

1. Validates `filename` is in `raw/`.
2. Reads image bytes from multipart, opens as PIL.
3. Reads mask bytes, opens as PIL (mode `L`, threshold at 128 → binary mask).
4. Calls `BACKENDS[backend].erase(image, mask)`.
5. Backs up original to `raw_orig/<filename>` if not already.
6. Writes result to `raw/<filename>` as JPEG q=95.
7. Appends to `inpaint_audit.jsonl`: timestamp, filename, backend, mask_sha1, elapsed_ms, cost_estimate.
8. Returns `{status: "ok", url: "/raw/<filename>?v=<ts>", backend, ms}`.

Approximate code size: ~80 lines added to `serve.py`.

### Step 3. Frontend: brush-mask tool in the cropper modal

The existing cropper modal has a crop-rect canvas overlay. Add a tool toggle in the top bar:

```
[ ✂ Crop | 🖌 Mask ]   ← radio toggle
```

When `Mask` is active:
- Show brush controls: size slider (5 to 200 px on the displayed image), opacity slider, erase toggle, clear-mask button.
- Hide crop rectangle handles.
- Show a `Backend: [stability ▾]` dropdown.
- Show `⊕ Run inpaint` button (disabled until mask has > 100 non-zero pixels).

Pointerdown/move/up on the image area paint white into an overlay canvas (`<canvas id="mask-canvas">`). The canvas is positioned absolutely over the displayed image at the same fitted dimensions. `globalCompositeOperation = "destination-out"` when erasing.

A "Auto signature mask" preset button auto-paints the bottom-right 18% × 12% of the image as a quick start for signature removal (most Renoir auction signatures fall in this region). User can adjust with brush after.

### Step 4. Mask resampling

The displayed canvas is fit-to-viewport (e.g. 1100 × 750 for a 4400 × 3000 source). The mask must be sent at native image resolution.

```js
function getNaturalSizeMaskBlob() {
  const display = document.getElementById("mask-canvas");
  const target = document.createElement("canvas");
  target.width = cropState.imgW;
  target.height = cropState.imgH;
  const ctx = target.getContext("2d");
  // Pre-fill black, then draw the white painted region over it.
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, target.width, target.height);
  ctx.drawImage(display, 0, 0, target.width, target.height);
  return new Promise(r => target.toBlob(r, "image/png"));
}
```

The mask convention all backends expect: **white = inpaint region, black = preserve**. Server-side feather the mask before sending (`ImageFilter.GaussianBlur(radius=2)`) to smooth the transition.

### Step 5. Revert button + audit

Add a "↺ Revert original" button on cards that have a corresponding `raw_orig/<filename>` backup. Clicking reverts the file and clears the relevant `inpaint_audit.jsonl` rows for that filename. Same UI affordance as the existing × Remove button, different action.

`inpaint_audit.jsonl` format (one JSON object per line):

```json
{"ts": 1731831234.5, "filename": "renoir-roses-1898.jpg", "backend": "stability",
 "mask_sha1": "abc...", "elapsed_ms": 2840, "cost_usd_estimate": 0.03,
 "preset": "signature_corner", "user_brush_seconds": 4.2}
```

Cost-tracking: a small status pill in the gallery toolbar shows running session spend ("$0.21 inpaint today, 7 calls"). Hard cap at $5/day; soft cap warning at $2/day.

### Step 6. Batch signature-removal workflow

For the Renoir dataset specifically, add a one-time helper script `datasets/renoir-flowers/batch_erase_signatures.py`:

1. Iterate over `metadata.csv` rows where `collection` contains "Sotheby" or "Christie" or filename matches auction patterns.
2. For each, programmatically generate a default signature mask (bottom-right 18% × 12%).
3. Send to Stability Erase backend in parallel (5 concurrent).
4. Save results, write audit rows.
5. Print summary: N processed, N succeeded, total cost.

This skips the gallery UI for the bulk pass; the gallery is for the long-tail per-image fixes that need a custom mask.

Estimated: 48 auction-scan signatures × $0.03 = ~$1.50 + 5 min wall time.

## Phase 2 implementation (fal.ai FLUX [pro] Fill)

Add `FalFluxFillBackend` to `inpaint_backend.py`. Same endpoint pattern as v1 of this doc. Backend dropdown in the UI now shows both options. No other UI changes.

## Phase 3 implementation (Modal SDXL Inpaint + Renoir LoRA)

Build `cloud/inpaint_app.py` mirroring `cloud/validation_renoir.py`:

1. Modal function `inpaint(image_bytes, mask_bytes, lora_path, lora_scale, prompt) -> bytes`.
2. Uses `diffusers.AutoPipelineForInpainting.from_pretrained("stabilityai/stable-diffusion-xl-base-1.0", ...)` with the SDXL Lightning 4-step LoRA + Renoir LoRA fused.
3. Volume mounts identical to `cloud/app.py`.
4. Local-side `ModalSDXLInpaintBackend` in `inpaint_backend.py` calls the Modal function via `modal.Function.lookup("slow-interpolation-inpaint", "inpaint").remote(...)`.

The gallery server doesn't need to change beyond adding the new backend entry. Students with their own LoRA + Modal account can run inpaint against THEIR LoRA by setting `modal_function_name` in `gallery-state.json`.

## Phase 4 implementation (fal.ai FLUX LoRA Inpainting)

Same as v1 plan: once the Renoir LoRA has a public URL (published model page on CivitAI or HuggingFace), add `FalFluxLoraInpaintBackend` and wire it into the dropdown.

## Open questions before implementation

1. **`STABILITY_API_KEY` provisioning.** Stability AI offers a free tier (~25 free credits at signup, then $10 minimum top-up for 1000 credits). For 48 Renoir signatures at 3 credits each = 144 credits. Free tier covers it. Document the signup flow.
2. **Per-student API key model.** Workshop students need their own keys. The gallery's `gallery-state.json` already persists a backend choice; extend it to hold per-backend API keys (encrypted at rest? or assume the student's filesystem is private?). Phase 1 ships with env-var-only; Phase 2 may add a settings panel.
3. **Mask feather radius.** Server-side `ImageFilter.GaussianBlur(radius=2)` for Phase 1. Tune empirically; signatures benefit from harder edges, broader subject removal from softer.
4. **Resolution constraints.** Stability Erase accepts up to ~10 MP. SDXL Inpaint on Modal needs 1024-divisible by 8 dimensions. Server-side resize-then-restore where needed.
5. **What about the auction signatures the LoRA already memorised?** Phase 1 fixes the training set. Retraining is the cleanup. The currently-trained Renoir LoRA stays usable in the meantime via the inference-time mitigations in the validation grid (negative prompt, post-render crop).

## Estimated effort

| Phase | Backend code | Gallery UI | Server | Test pass | Total |
|---|---|---|---|---|---|
| 1 (Stability Erase) | 1.5 h | 4 h | 2 h | 1 h | **8.5 h** |
| 2 (fal.ai FLUX [pro]) | 1 h | 0.5 h (dropdown) | 0.5 h | 0.5 h | **2.5 h** |
| 3 (Modal SDXL) | 4 h Modal app | 0.5 h | 1 h | 1.5 h | **7 h** |
| 4 (fal.ai LoRA) | 0.5 h | 0 h | 0 h | 0.5 h | **1 h** |

Phase 1 alone: ~1 day focused work. Add Phase 2 the same week (low marginal cost). Phase 3 and 4 are independent additions, schedule against the Modal-trainer workstream's cold-run.

## Acceptance criteria (Phase 1)

- Paint a mask in the cropper, click `⊕ Run inpaint`, see the inpainted result replace the gallery card image within 10 seconds.
- "Auto signature mask" preset paints a usable default mask in one click for a typical Sotheby's / Christie's scan.
- Stability Erase removes Renoir signatures cleanly on at least 8 of 10 test images (subjective grade) without visible seams.
- `raw_orig/<filename>` backup exists for every inpainted file.
- `inpaint_audit.jsonl` row written with mask sha1, backend, elapsed ms, cost estimate.
- "Revert original" button restores the file and clears audit rows.
- No API key leaks to the browser (verifiable in dev tools).
- Running cost pill in toolbar tracks session spend.
- Daily soft cap at $2 surfaces a warning; hard cap at $5 disables the button.

## Acceptance criteria (post-Phase-1 retraining)

- Run `batch_erase_signatures.py` over the 48 auction-scan subset of `datasets/renoir-flowers/raw/`.
- Re-run the dataset-curation gallery walk to verify the erasures look clean.
- Rebuild the CivitAI ZIP (`package_for_civitai.py`).
- Re-train the LoRA on civitai.red (~500 yellow Buzz, ~20 min).
- Re-run `modal run -m cloud.validation_renoir --epoch 10` against the new checkpoint.
- New validation grid shows zero baked-in signatures on the 11 prompts.
- Update [validation-grid.md](validation-grid.md) with the v2 grid.

## Risk register

| Risk | Mitigation |
|---|---|
| Stability Erase leaves a visible seam at the mask boundary | Server-side feather radius (default 2 px); fall back to FLUX [pro] Fill for hard cases. |
| Auction signatures are too large/varied for an 18%×12% default mask | "Auto signature mask" is the starting point; user adjusts with brush. |
| The retrained LoRA still has signature artefacts (model memorised the pattern from positive contexts) | Add "no signature, no text, no initials" to the negative prompt at training time too. CivitAI's training UI exposes a negative-sample slot. |
| Per-student API keys are a UX wall | Phase 1 ships with env-var-only. Settings panel deferred to Phase 2 if students complain. |
| Modal SDXL Inpaint cold-start is too slow for interactive use | Phase 3 only. Use Modal's `keep_warm=1` to keep one container hot during gallery sessions, or accept ~30s cold-start latency on first call. |
| The brush-paint UX is slow on mobile / touch devices | Stretch goal; ship desktop-first. Touch events already supported by the existing cropper. |
| Cost run-aways from a stuck loop | Hard cap at $5/day per dataset; manual override via env var. |

## Filing

This is `docs/planning/workstreams/renoir-dataset/inpaint-plan.md`. Status entries land in `docs/planning/workstreams/renoir-dataset/progress.md` per the workstream convention. When Phase 1 ships, post a one-line entry: "Phase 1 inpaint shipped, Stability Erase as default, signature batch run, retrained on civitai.red, validation grid v2 at validation-grid.md".

If the inpainting infrastructure proves useful beyond the Renoir workstream (Cézanne, Vermeer, future LoRA datasets), promote `inpaint_backend.py` to a generic library at `tools/inpaint/` and reference it from `docs/manual/gallery.md` under a new "Inpainting" section.

## Recommendation

Ship **Phase 1 (Stability Erase) + Phase 2 (FLUX [pro] Fill)** this week. Both use the same UI, same server endpoint, same backend abstraction. Total effort ~11 hours focused dev. Stability Erase handles the signature batch (the immediate pain); FLUX [pro] Fill is the fallback for hard cases. Phase 3 (Modal SDXL Inpaint) follows the Modal-trainer cold-run; Phase 4 (FLUX LoRA Inpainting) follows the Renoir LoRA's public publication.

**Skip Gemini Nano Banana for this use case.** It is a strong tool for other workflows (semantic stylisation, full-image edits described in natural language), but the lack of pixel-mask precision makes it unfit for tight corner signature removal.
