# Kickoff prompt: replace nano banana with an open-weight editor, 100% on Modal

> **DONE, 2026-08-14. Do not re-run this brief.** All three candidates were tested on
> Modal and all three failed. klein and Mage-Flow died on the Q1 painterly gate at the
> first edit; FireRed passed Q1 marginally, then disintegrated over a nine-edit chain
> (surface energy x11 against frame 0, wrap SSIM 0.15) and composited rather than
> interpolated on Q4. **We stay on `gemini-3.1-flash-image`.** Verdicts, evidence and
> three corrections to the research are in
> [image-edit-model-alternatives.md section 10](../findings/image-edit-model-alternatives.md#10-bake-off-results-2026-08-14).
> The implementation is kept and works: [`cloud/edit.py`](../../cloud/edit.py) hosts all
> three candidates and [`tools/edit_keyframes.py`](../../tools/edit_keyframes.py) is a
> validated drop-in for `banana_keyframes.py`, so re-probing a NEW candidate is now a
> one-class change rather than a fresh build.
>
> **Read section 10.6 before designing any successor experiment.** The project's own
> health metric, consecutive SSIM, rose as the failing chain died and scored FireRed
> *above* nano banana. Measure drift against frame 0, not against the neighbour.

**Original brief follows, preserved for posterity.**

**MUST DO. Blocked production once already** (Gemini credits depleted mid-session,
2026-08-13, stopping both keyframe generation and the review gate).

Paste everything between the rulers into a fresh chat in this repo. It is written to be
self-contained: it assumes no memory of the session that produced the research.

---

You are picking up a migration task for the `slow-interpolation` project. Read
`CLAUDE.md` first, then `docs/findings/image-edit-model-alternatives.md`, which is the
research behind this task. Do not redo that research; it cost four agent passes.

## The task

Our keyframe editor is Google's `gemini-3.1-flash-image` ("nano banana"), called from
`tools/banana_keyframes.py`. It is metered, it depleted mid-production once, and it costs
$0.67 per 10-keyframe chain. Run a **three-way bake-off of open-weight replacements
entirely on Modal**, decide whether any of them can carry the series, and if one can,
implement it as a Modal app alongside the existing ones in `cloud/`.

**Everything runs on Modal. Do not set up a local ComfyUI or download model weights to
this machine.** The reason is in the finding, section 8: all three candidates fit L40S
48 GB at full precision, which removes the entire quantisation-degradation risk class. A
local test on the 8 GB laptop would force Q2/Q3 for the 20B model and we would end up
blaming the model for the quantisation.

## The three candidates, in test order

| order | model | HF id | why it is here | size |
|---|---|---|---|---|
| 1 | **FireRed-Image-Edit 1.1** | `FireRedTeam/FireRed-Image-Edit-1.1` | highest background-preservation score of any model measured, above both Nano Banana tiers; multi-image 1-3 native; Apache 2.0; uses `QwenImageEditPlusPipeline` | 20B, ~30 GB |
| 2 | **Mage-Flow-Edit** | `Comfy-Org/Mage-Flow` (Microsoft original is gated) | MIT; **true native resolution at any aspect ratio**, the only candidate that cannot silently resize us; 4-step Turbo variant | 4B, ~18-20 GB |
| 3 | **FLUX.2 [klein] 4B** | `black-forest-labs/FLUX.2-klein-4B` | Apache 2.0; best Visual Consistency among commercially clean models; multi-image to 10 refs; explicit `height`/`width` | 4B, ~13 GB |

**Licence rule, non-negotiable:** only these three. Do NOT substitute FLUX klein 9B,
FLUX.2 [dev] or FLUX.1 Kontext [dev]: they are non-commercial and the series ships as a
paid objkt labs edition from a public repo. Do not use Fibo-Edit (CC BY-NC). Z-Image-Edit
does not exist regardless of what any blog says.

## The four questions the bake-off must answer, in this order

Stop early if a candidate fails an earlier question; do not spend on later ones.

**Q1. Does it hold the painterly register?** THE HARD GATE. Our subject matter is soft
tonal oil painting, sfumato, muted palette, no visible brushstrokes. Luca explicitly
rejected the material/impasto register. The documented risk is that open editors drift
toward photorealism or add a yellow cast. Take an existing keyframe 0 (e.g.
`outputs/arendt/grow_well2/keyframes/0000.png` at 1408x768, or
`outputs/arendt/labor_embers/keyframes/0000.png`), apply ONE small edit, and **judge by
eye at native resolution, never on a montage**. Looking for: visible brushstrokes
appearing, edge crispening, warm cast, loss of blending. If it fails here it is out, no
matter what it scores.

**Q2. Does output resolution equal input resolution, exactly?** Assume silent resizing
until disproved: no candidate documents otherwise, and several editors in the field snap
to aspect buckets or a 1 MP ceiling. Test both 1408x768 and 1024x1280. A model that
returns anything else breaks the chain and is out unless `height`/`width` genuinely
override.

**Q3. Does preservation hold across a 9-edit chain?** Run a full sequential chain (each
edit receives the previous output) and measure consecutive SSIM. Healthy is **0.80-0.98**;
below ~0.75 the pair needs bridging. Watch turns 6-9 specifically: FreqEdit measured open
models degrading severely after ~5 sequential edits, and our chains are 8-9, so this is
where a candidate is most likely to die. Compare against a nano banana chain from
`outputs/arendt/*/keyframes/` as the reference.

**Q4. Can it do the two-endpoint call?** This is load-bearing and the likeliest failure.
Hand it the previous keyframe AND keyframe 0 in one call and ask for "the moment two
thirds of the way from the first to the second". All three accept multiple images, but all
were trained for *compositing*, not temporal interpolation. If zero-shot fails, work the
fallback ladder in the finding's section 6 (explicit reference numbering, then latent
SLERP plus a cleanup pass, then RIFE the midpoint and promote it to an authored keyframe)
before concluding the capability is unavailable.

## Prompt-format warning

Do NOT paste our Gemini preamble verbatim. `tools/banana_keyframes.py` uses:

> "Edit this image. Keep ABSOLUTELY EVERYTHING identical: the setting, the lighting, the
> palette, the brushwork, the camera. Change ONLY this: {change}. The result must look
> like the SAME painting a moment later."

That works because Gemini reasons over the instruction. These models are conditioned
samplers: Qwen-family guidance is explicitly that **short specific prompts beat long
detailed ones**, and klein's card warns prompt-following is phrasing-sensitive. Test both
forms (full preamble vs bare imperative such as "the ivy reaches the seat") on the same
seed and report which preserves better. Preservation should come from the architecture,
not from asking nicely.

## Implementation pattern

Follow the existing Modal apps in `cloud/` (see `cloud/app.py` for the volume + entrypoint
shape). Two deviations that matter:

- Use `@app.cls` with `@modal.enter()` so the model loads once and stays resident across
  all 10 edits of a chain. With `@app.function` you pay the load per edit and the cost
  model collapses.
- Cache weights on a `modal.Volume` (reuse `slow-interp-hf-cache`). First run downloads
  ~17-40 GB depending on model; that is a one-time cost.

Starting sketch (klein; for FireRed swap in `QwenImageEditPlusPipeline` and the model id,
the call shape is the same):

```python
"""cloud/edit.py -- instruction-edit keyframes on Modal."""
from __future__ import annotations
import io
import modal

MODEL_ID = "black-forest-labs/FLUX.2-klein-4B"
HF_CACHE = "/root/.cache/huggingface"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch==2.7.0", "accelerate", "safetensors", "pillow",
        "transformers>=4.57", "hf_transfer",
        "git+https://github.com/huggingface/diffusers.git",
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

app = modal.App("slow-interp-edit", image=image)
hf_cache = modal.Volume.from_name("slow-interp-hf-cache", create_if_missing=True)


@app.cls(gpu="L40S", volumes={HF_CACHE: hf_cache}, timeout=1800, scaledown_window=300)
class Editor:
    @modal.enter()
    def load(self):
        import torch
        from diffusers import Flux2KleinPipeline
        self.pipe = Flux2KleinPipeline.from_pretrained(
            MODEL_ID, torch_dtype=torch.bfloat16, cache_dir=HF_CACHE
        ).to("cuda")

    @modal.method()
    def edit(self, images: list[bytes], prompt: str,
             width: int = 1408, height: int = 768,
             steps: int = 4, seed: int = 0) -> bytes:
        import torch
        from PIL import Image
        refs = [Image.open(io.BytesIO(b)).convert("RGB") for b in images]
        out = self.pipe(
            image=refs if len(refs) > 1 else refs[0],   # list == multi-reference
            prompt=prompt,
            width=width, height=height,                 # exact %64, no silent resize
            num_inference_steps=steps,
            guidance_scale=1.0,
            generator=torch.Generator("cuda").manual_seed(seed),
        ).images[0]
        buf = io.BytesIO()
        out.save(buf, format="PNG")
        return buf.getvalue()
```

## Repo conventions you must follow

- **Every Modal command needs the env prefix**: `env PYTHONIOENCODING=utf-8 PYTHONUTF8=1 modal run ...`.
  Without it a Windows codepage crash creates a zombie ephemeral app that renders nothing,
  spends nothing, and can still exit 0 through a pipe.
- **`modal volume get` on a DIRECTORY silently writes nothing.** Fetch files singly.
- New maps/anchors/inputs need `modal volume put` before dispatch or the render dies on a
  bare `FileNotFoundError` after the container has spun up.
- Seed is **1087** across this project.
- Budget: Modal credit is $30/month with roughly $19.60 left as of 2026-08-13. The whole
  bake-off should cost $1-2. **Confirm with the user before any dispatch above ~$0.50.**

## Deliverables

1. A verdict per candidate against Q1-Q4, with the evidence (frames opened, SSIM ladders,
   measured output dimensions), written into
   `docs/findings/image-edit-model-alternatives.md` under a new "Bake-off results" section.
2. If one passes: `cloud/edit.py` working end to end, plus a `tools/` entrypoint that is a
   drop-in for `tools/banana_keyframes.py` (same CLI shape: `--base`, `--edit` repeatable,
   `--out`), so the edit-model loop can switch editors by changing one command.
3. If none passes: say so plainly and record why, with the frames that show it. A negative
   result here is a first-class outcome and saves the next attempt.
4. Update `.claude/skills/edit-model-loop/SKILL.md` only if the editor actually changes.

## What good looks like

A candidate that holds the sfumato, returns exactly 1408x768, keeps consecutive SSIM in
0.80-0.98 through nine sequential edits without the turn-6 cliff, and does something
usable on the two-endpoint call. That model replaces nano banana and cuts cost per chain
by roughly 10x. Anything less is a fallback, not a replacement, and should be reported as
such.
