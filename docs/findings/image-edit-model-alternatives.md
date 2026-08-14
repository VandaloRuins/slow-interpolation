# Replacing nano banana: open-weight instruction image editors

**Status: researched 2026-08-13, NOT yet tested. Four independent research passes.**
**Next action: the Modal bake-off in [kickoff-editor-migration.md](../planning/kickoff-editor-migration.md).**

You are an agent picking up the question "what replaces `gemini-3.1-flash-image`
(nano banana) as the keyframe editor". This page is the evidence. It does not tell you
which model to use, because **no benchmark measures the thing that decides it for this
project**, and nobody has run the test yet.

---

## 1. Why this question exists

Nano banana authors every keyframe in the edit-model loop
([edit-model-loop skill](../../.claude/skills/edit-model-loop/SKILL.md)). On 2026-08-13
the Gemini prepayment credits were **depleted mid-production** (429 RESOURCE_EXHAUSTED),
which stopped both new keyframes and `tools/review_gate.py` (scoring runs on Gemini too).

Cost context: nano banana is **$0.067/image = $0.67 per 10-keyframe chain**. A day of
series production is roughly 30 chains, so ~$20. That is where the credit went.

Self-hosting is therefore both a resilience and a cost question, and secondarily a
sovereignty one: this repo is public and workshop-facing, and a self-hosted open-weight
editor is the more defensible story than a dependency on a preview endpoint whose
behaviour and price can change underneath us.

---

## 2. The hard requirements (these eliminate most of the field)

1. **Preservation above all.** Every call says "keep ABSOLUTELY EVERYTHING identical,
   change ONLY this". Consecutive keyframes must disagree only where intended; the health
   metric is SSIM 0.80-0.98 between neighbours. A model that is brilliant at instruction
   following but repaints the frame is useless here.
2. **Multi-image input, load-bearing.** The dual-endpoint call (previous keyframe AND
   keyframe 0, "paint the moment two thirds of the way between") is what closes our loops.
   It took `action_chairs` from 0.758 to 0.953 and saved four chains in one day. A
   single-image editor cannot do it.
3. **Exact non-square dimensions**: 1408x768 and 1024x1280, both %64. Several editors
   silently snap to aspect buckets or a 1 MP ceiling, which breaks a keyframe chain.
4. **Painterly register.** Soft tonal oil, sfumato, muted palette, no visible brushstrokes.
   Luca explicitly rejected the material/impasto register. A model that drifts toward
   photorealism is disqualified regardless of scores.
5. **Commercial licence, public repo.** Output goes into a paid objkt labs edition.

---

## 3. Results

### 3.1 The four passes disagreed, and why

| pass | winner | decided on | blind spot |
|---|---|---|---|
| A | FireRed-Image-Edit 1.1 | ImgEdit/GEdit + instruction compliance | did not consider klein |
| B | FLUX.2 [klein] 4B | GEditBench v2 **Visual Consistency** (preservation) | — |
| C | FireRed 1.1, second seat Mage-Flow-Edit | preservation sub-scores + resolution handling | brief excluded klein and Qwen |
| D | Mage-Flow-Edit-Turbo (local), FireRed to Modal | 8 GB feasibility, measured timings | local-focused |

Not chaos: **A and C converged on FireRed independently**, and C could not pick klein
because its brief excluded it. The genuine split is preservation-metric (B) versus
overall-benchmark (A, C).

**The finding all four share: no benchmark measures "leaves the rest of a painted fresco
untouched across a 300-frame chain".** Only our own probe answers it.

### 3.2 The shortlist that survives our constraints

| model | licence | multi-image | size | preservation evidence |
|---|---|---|---|---|
| **FireRed-Image-Edit 1.1** (Xiaohongshu, Mar 2026) | Apache 2.0 | **yes, 1-3 native** | 20B, ~30 GB | ImgEdit **background 4.45**, highest of any model measured, above Nano Banana Pro (4.40) and Nano Banana (4.32). ImgEdit overall 4.56, GEdit EN 7.943, both open-source firsts. v1.1 was specifically a consistency release. Rides `QwenImageEditPlusPipeline`. |
| **Mage-Flow-Edit** (Microsoft, Jul 2026) | MIT (HF repo gated) | yes | 4B, 18-20 GB bf16 | GEdit-EN 8.271 / CN 8.264. **True native resolution 512-2048 at any aspect ratio, no bucket snapping**, which no other candidate offers. Turbo runs 4 steps, 1.02 s/edit on A100. |
| **FLUX.2 [klein] 4B** (BFL, Jan 2026) | Apache 2.0 | **yes, to 10 refs** | 4B, 13 GB bf16 | GEditBench v2 Visual Consistency **1,070**, 2nd among open models and 1st among commercially clean ones. Explicit `height`/`width`. |

### 3.3 Eliminated, with reasons (do not re-walk these)

| model | why not |
|---|---|
| GLM-Image | **80 GB VRAM floor** does not fit L40S 48 GB. Also contested: one pass cites the best Visual Consistency of any model (1,109); another notes it is tagged text-to-image, publishes zero editing benchmarks, and is absent from every editing leaderboard at 9.6k downloads/month. |
| LongCat-Image-Edit | **Hard 1 MP output ceiling with no height/width override** (cannot make 1024x1280 = 1.31 MP), and **single-image only** so no wrap bridge. |
| Step1X-Edit v1.2 | Single-image; ImgEdit 3.95, weakest of the cohort; successor went closed-source. Legacy. |
| Qwen-Image-Edit-2511 | Preservation is its documented weakness (VC 972, below all three shortlisted). Named unfixed defect: **pixel drift**, output shifts/zooms a few pixels per edit, a direct attack on our SSIM instrument. Keep in reserve only because it is the one model we could realistically fine-tune. |
| FLUX klein 9B / FLUX.2 dev / FLUX.1 Kontext dev | **Non-commercial licence.** See §4. Kontext additionally has the worst Visual Consistency of any open model (840). |
| Fibo-Edit | CC BY-NC. Commercially disqualified. |
| Z-Image-Edit | **Does not exist.** Still "to be released" nine months after announcement; the org has published nothing since Jan 2026. Multiple blogs claim otherwise and are wrong. |
| Boogu-Image-0.1-Edit | Single reference image only, and its own model card admits instability in "strict preservation of subject identity, layout, or fine details". |
| Bernini (ByteDance) | A **video** model with an image side-door: 848px default, zero image-editing benchmarks. |
| step-image-edit-2, "GLM-Image Edit" | API-only, no weights. Another hosted dependency is the thing we are escaping. |

---

## 4. The FLUX licence trap

klein 9B, FLUX.2 [dev] and FLUX.1 Kontext [dev] carry the FLUX **Non-Commercial** licence.
It says outputs may be used commercially, but the grant covers the model "solely for your
Non-Commercial Purposes", excluding revenue-generating activity. **Running the model to
produce keyframes for a paid edition falls outside the grant**, even though the outputs
would be ours. In a public repo that documents the workflow, that is discoverable, not
theoretical.

**FLUX.2 [klein] 4B is Apache 2.0 and unaffected**, and happens to be the FLUX model with
the best Visual Consistency.

---

## 5. Chain drift: quantified, and it explains what we already measured

**FreqEdit** (arXiv 2512.01755) is the only rigorous study of our exact problem. Measured
on Kontext at 28 steps:

| turn | 1 | 4 | 7 | 10 |
|---|---|---|---|---|
| LPIPS (lower better) | 0.222 | 0.365 | 0.468 | **0.542** |
| CLIP-I (higher better) | 0.966 | 0.927 | 0.889 | **0.854** |

Open base models hold **~5 sequential edits**, then degrade severely; 10+ is
"catastrophic". **Our chains are 8-9 edits, so we sit past the documented cliff.**

Its three failure modes map onto observations this project recorded independently:

| FreqEdit failure mode | our recorded observation |
|---|---|
| subject deformation | "chairs never reset, textures accumulate as swirl" |
| **edge over-sharpening** | "smooth hands turn veined over 8+ edits and never return" |
| texture collapse | the aging drift that never returns |

**The cause is NOT VAE re-encode loss** (they tested that by manipulating high-frequency
content directly). It is accumulated error in high-frequency features, so fixes aimed at
the VAE will not work. FreqEdit itself is training-free and claims stability past 10 turns;
verify its code actually landed before depending on it.

**Free mitigation, model-agnostic, applies even if we stay on nano banana:** both Qwen and
Kontext show a per-edit **yellow cast** on artistic material, compounding across 9 edits.
A deterministic per-keyframe colour normalisation against keyframe 0, applied to the
**low-frequency band only** so the edit itself is untouched, removes an entire drift axis.
The frequency-separation machinery already exists in Phase A.5.

---

## 6. The multi-image question, and the honest risk

| model | 2+ images per call |
|---|---|
| FLUX.2 klein 4B | yes, to 10 refs; KV-cache pipeline caches reference attention |
| FireRed 1.1 | yes, 1-3 native; an Agent module crops/stitches beyond 3 |
| Mage-Flow-Edit | yes, max unstated ("blend the object from image 2 into image 1") |

**The caveat that applies to all of them:** multi-image was trained for *compositing*
(person + product, person + scene), not for "two moments of the same scene, paint the
moment between". Nano banana follows that instruction because it reasons over images;
open editors are conditioned samplers. **Expect the zero-shot in-between call to be the
hardest part of the migration, and probe it specifically.**

**Precedent that it is reachable:** Edit2Interp (arXiv 2603.15003) adapts
Qwen-Image-Edit-2509 to frame interpolation by framing it as constrained multimodal
editing, using a **LoRA trained on 64-256 triplets** (best: 256 samples, rank 128).
Caveats: t=0.5 only, no code or weights released. But we can generate those triplets
automatically from existing RIFE renders.

**Fallback ladder if the zero-shot call fails, cheapest first:**
1. Explicit reference numbering in the prompt ("image 1 is the later moment...").
2. SLERP the two endpoints in latent space, then one low-strength edit pass to clean the
   ghosting. Phase A already owns SLERP.
3. RIFE the wrap pair at high pass count and promote the midpoint to an authored keyframe.
4. Train the Edit2Interp-style LoRA. The Modal training rig and dataset-mosaic protocol
   already exist.

---

## 7. What we would lose, stated plainly

1. **The blended register, which is exactly our aesthetic.** In head-to-head testing on
   oil-painting material, nano banana produced an "air-brushed, well-blended look closest
   to the original" while Qwen and Kontext produced "a painterly, unblended look" with a
   yellow tint. The reviewer's summary: **no model tested preserved an existing artistic
   style well.** This is the biggest risk and the reason the painterly probe is a hard gate.
2. **Long prohibitive prompts.** Our `EDIT_PREAMBLE` works because Gemini reasons over
   "keep ABSOLUTELY EVERYTHING identical". Qwen's guidance is that short beats long; klein
   warns on phrasing sensitivity. Every prompt gets rewritten, and preservation has to come
   from architecture rather than from asking nicely.
3. **The temporal in-between call.** No guaranteed replacement; may need a LoRA.
4. **Chain-length headroom.** ~5 documented turns against our 8-9.

**What we gain:** exact output dimensions (nano banana emits 1376x768 and forces the
resize we absorb today), a fixable seed and therefore reproducible keyframes, roughly 10x
lower cost per chain, the ability to fine-tune on our own corpus, and independence from a
metered preview endpoint.

---

## 8. Why Modal-only is the right first test

Running the bake-off entirely on Modal **removes the whole quantisation-risk class** that
dominates any 8 GB local analysis. All three shortlisted models fit L40S 48 GB at full
precision: klein 4B ~13 GB, Mage-Flow ~18-20 GB, FireRed ~30 GB. On the laptop we would be
forced into Q2/Q3 for the 20B model, which is exactly the tier where documented ghosting
and colour-shift failures live, so a local test would risk blaming the model for the
quantisation.

Cost is not a constraint at this scale: a 10-edit chain on L40S is roughly **$0.06 to
$0.35** depending on model size, against nano banana's $0.67, so the whole three-way
bake-off is $1-2 of the remaining credit.

**Local remains viable later** for the 4B models (Mage-Flow-Edit-Turbo int8 is 3.87 GiB,
klein Q8_0 is 4.01 GiB, both fit 8 GB and neither needs a torch upgrade). Recorded in the
scratch research for whoever wants a free iteration loop; not the path for the decision.

---

## 9. Sources

GEditBench v2 leaderboard and paper (arXiv 2603.28547) · FreqEdit (arXiv 2512.01755) ·
Edit2Interp (arXiv 2603.15003) · FireRed-Image-Edit (arXiv 2602.13344, github.com/FireRedTeam/FireRed-Image-Edit) ·
Mage-Flow (arXiv 2607.19064, Comfy-Org/Mage-Flow) · FLUX.2 klein (bfl.ai, black-forest-labs/FLUX.2-klein-4B) ·
Qwen-Image issue #243 (square-resolution degradation) · QuantStack GGUF discussion #6 (quantisation ghosting) ·
Tongyi-MAI/Z-Image (Z-Image-Edit unreleased)
