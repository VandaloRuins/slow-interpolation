# Replacing nano banana: open-weight instruction image editors

**Status: researched 2026-08-13, bake-off run on Modal 2026-08-14. CLOSED.**
**Result: all three candidates failed. Stay on nano banana. Jump to
[section 10](#10-bake-off-results-2026-08-14) for the verdicts and, more usefully, for
the instrument lesson in 10.6. Sections 1-9 are the research that set the test up and
are unchanged except where 10.4 corrects them.**

You are an agent picking up the question "what replaces `gemini-3.1-flash-image`
(nano banana) as the keyframe editor". Sections 1-9 are the evidence that framed the
question; section 10 is what happened when the three candidates were actually run.
**No benchmark measures the thing that decides it for this project**, which is why the
probe exists.

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
| B | FLUX.2 [klein] 4B | GEditBench v2 **Visual Consistency** (preservation) | none identified |
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

---

## 10. Bake-off results (2026-08-14)

**Answer: none of the three can replace nano banana. Stay on `gemini-3.1-flash-image`.**

This is a clean negative and it closes the question properly. Two candidates died on the
painterly gate, the third held the register well enough to be worth chasing and then
disintegrated over a nine-edit chain. Read 10.6 before ever running this experiment
again, because the project's own health metric said the failing chain was the *healthier*
of the two.

Run on Modal from [`cloud/edit.py`](../../cloud/edit.py), one resident container per
candidate, seed 1087 throughout, total spend about 1.53 USD. Source frames are current
Arendt-series work, not the Thomas Cole material: `labor_embers/keyframes/0000.png`
(1408x768, gated 10/10/9/9), `ledA_window/accum/0000.png` (592x1792),
`ledB_snow/accum/0000.png` (1856x576).

### 10.1 Verdict table

| candidate | Q1 painterly | Q2 exact dims | Q3 nine-edit chain | Q4 dual-endpoint | status |
|---|---|---|---|---|---|
| FLUX.2 [klein] 4B | **FAIL** | pass (needs `height`/`width`) | not run | not run | **out on Q1** |
| Mage-Flow-Edit-Turbo 4B | **FAIL** | **pass natively** | not run | not run | **out on Q1** |
| FireRed-Image-Edit 1.1 | marginal pass | pass (needs `height`/`width`) | **FAIL, catastrophic** | **FAIL** | **out on Q3** |

Q1 is a stop gate, so nothing was spent on Q3 or Q4 for the two that failed it.

### 10.2 Q1, the painterly gate: how it was measured

Judging the whole frame is useless here, because most of it changes for legitimate
reasons. The instrument that separates the candidates is a **704x384 1:1 crop of a region
the edit did not name** (the stone pile and hearth at the bottom left of `labor_embers`,
box `100,384` to `804,768`). Everything that moves in that crop is collateral damage.

One edit, from the identical base, against the nano banana chain's own first edit on the
same base:

| candidate + prompt form | SSIM (untouched region) | lapvar ratio | warmth (dR-dB) |
|---|---|---|---|
| **nano banana (the reference)** | **0.870** | **1.21** | **+7.4** |
| firered, bare imperative | 0.703 | 1.38 | +6.4 |
| firered, full preamble | 0.674 | 1.28 | +3.9 |
| mageflow, full preamble | 0.631 | 2.88 | +11.3 |
| mageflow, bare imperative | 0.578 | 2.64 | +15.5 |
| klein, full preamble | 0.487 | 2.15 | +28.3 |
| klein, bare imperative | 0.467 | 1.50 | +38.3 |

`lapvar ratio` is Laplacian variance after divided by before. It is the edge-crispening
axis: 1.0 means the surface is as soft as it started, 2.0 means the model doubled the
high-frequency energy of a region it was not asked to touch. `warmth` is mean red minus
mean blue delta, the yellow-cast axis section 5 predicted.

**What the numbers say, confirmed by eye at native resolution in every case:**

- **klein repaints the frame and pours warm light over it.** The single instruction "the
  embers brighten a little" produced open flames, a global amber wash roughly six times
  nano banana's colour shift, and hard-edged chiselled stone where the original had soft
  tonal masses. The preamble version additionally redrew the pot, the stove interior and
  the door panel. Both documented failure modes, photorealism drift and yellow cast, fire
  on edit one.
- **Mage-Flow goes photographic, and it is the worst offender on surface.** lapvar 2.6 to
  2.9 in an untouched region: hearth ash becomes granular photographic grit, charcoal
  gains specular highlights, stone edges harden. On the 592x1792 ledwall frame it also put
  **visible directional brushstrokes in the sky** and outlined every stone and ivy leaf.
  Precisely the "painterly, unblended look" section 7 warned about, which Luca has
  explicitly rejected.
- **FireRed holds the palette.** Its warm shift is +6.4 against nano banana's +7.4, so the
  yellow-cast problem does not appear at all. Crispening is mild (1.38 against 1.21). What
  it does worse is preservation: 0.703 against 0.870, below the 0.80 floor on turn one,
  visible as hearth debris turning from soft smudges into hard-edged chips.

**Prompt-format answer, which the brief asked for explicitly:** the long "keep ABSOLUTELY
EVERYTHING identical" preamble is **not** what buys preservation on these models.

| candidate | better form | why |
|---|---|---|
| firered | **bare imperative** | higher SSIM (0.703 vs 0.674); costs a little colour neutrality |
| mageflow | **full preamble** | bare doubled the warm shift (+15.5 vs +11.3) |
| klein | neither | the forms differ by 0.02 SSIM; both fail |

Do not port the Gemini preamble verbatim to any open editor.

### 10.3 Q2, exact dimensions: all three pass, but only with an override

Assume silent resizing until disproved was the right posture. It is real, and it is
overridable in every candidate.

| candidate | no `height`/`width` passed | explicit `height`/`width` |
|---|---|---|
| klein | 1376x752 | exact 1408x768, 592x1792, 1856x576 |
| firered | 1376x768 | exact 1408x768, 592x1792, 1856x576 |
| mageflow | **1408x768, the native source size** | exact 1408x768, 592x1792, 1856x576 |

Two things worth carrying forward whatever we end up using:

1. **Always pass `height`/`width`.** Left to itself each diffusers-family candidate snaps
   to a ~1 MP bucket. klein lands on 1376x752 and FireRed on 1376x768, and FireRed's
   default is *exactly the size nano banana emits*, which confirms everyone is quantising
   to the same 1 MP budget.
2. **The output canvas is exact; the conditioning path is not.** Both diffusers pipelines
   downsample the reference internally regardless of what you ask for:
   `QwenImageEditPlusPipeline` resizes the VAE conditioning to
   `calculate_dimensions(1024*1024, ratio)` and the semantic conditioning to a 384x384
   *area*; `Flux2KleinPipeline` calls `_resize_to_target_area(img, 1024*1024)` on any
   reference above 1 MP then crops to a multiple of 16. Our frames are 1.06 to 1.08 MP, so
   each takes a downsample-then-upsample round trip **per edit**, which is one of the
   mechanisms behind the Q3 collapse. Mage-Flow is the only candidate that avoids this
   (`vl_cond_long_edge` caps only the reference fed to the text encoder), which is what its
   native-resolution claim actually means.

### 10.4 Corrections to sections 1-9, all measured

Three claims in the research above are wrong and would mislead the next attempt.

| claim in the research | what is actually true |
|---|---|
| FireRed is "20B, ~30 GB" and "all three fit L40S 48 GB at full precision" (section 8) | **57.7 GB of weights** (transformer 40.86 + text encoder 16.58), measured at **58.4 GB resident on an A100-80GB**. It does **not** fit L40S. The 30 GB on the model card is the quantised acceleration suite. Section 8's premise, that Modal removes the quantisation-risk class for all three, holds only if FireRed is given an 80 GB card, which also triples its hourly rate. |
| Mage-Flow ships via `Comfy-Org/Mage-Flow` because "the Microsoft original is gated" | `microsoft/Mage-Flow*` returns **404 even with a valid token**, and `Comfy-Org/Mage-Flow` is ComfyUI single-file format with no `model_index.json`, so diffusers cannot load it at all. Working route: the `mage_flow` package from **github.com/microsoft/Mage** (MIT, subdirectory `mage_flow`) plus a diffusers-layout community mirror such as `mage-flow-community/Mage-Flow-Edit-Turbo`. Provenance is a re-upload, not first-party; treat the MIT claim as inherited rather than verified. |
| The kickoff sketch pins `transformers>=4.57` | Unresolvable. diffusers from git requires `huggingface-hub>=1.23`; every transformers 4.57.x caps `huggingface-hub<1.0`. Use `transformers>=5.5,<5.6`. |

Two build traps, both of which cost a container start:

- **Mage-Flow needs flash-attn switched off in two independent places.**
  `set_attn_backend("sdpa")` covers the DiT only, and it must be called **after**
  `from_pretrained`, because `MageFlowModel.__init__` calls
  `set_attn_backend(config.attn_type)` itself and the repo config says `flash2`. The
  Qwen3-VL text encoder is separate and is constructed with
  `attn_implementation="flash_attention_2"` hard-coded; the env var
  **`VF_HF_ATTN_IMPL=sdpa`** is the first-party override for it. With both set the 4B model
  loads in 28.6 s with no CUDA compile. Without them you face a 30 to 60 minute flash-attn
  source build inside an image layer.
- **Weights live on a dedicated `slow-interp-edit-cache` volume**, not the shared
  `slow-interp-hf-cache`, so the bake-off scratch can be dropped in one command without
  touching the render path's SDXL and RIFE cache. See 10.8.

### 10.5 Q3, the nine-edit chain: FireRed disintegrates

Base `ledB_snow/keyframes/0000.png` (1856x576), reusing **that chain's own documented edit
list** for turns 1 to 5 so they compare like for like against the nano banana frames on
disk, plus four authored continuation edits for turns 6 to 9. FireRed at 24 steps,
true_cfg 4.0, seed 1087.

| turn | nano SSIM | FireRed SSIM | FireRed lapvar vs frame 0 |
|---|---|---|---|
| 1 | 0.9605 | 0.8061 | 0.64 |
| 2 | 0.9485 | 0.8392 | 1.83 |
| 3 | 0.7557 | 0.6871 | **7.55** |
| 4 | 0.6640 | 0.8224 | **10.39** |
| 5 | 0.8197 | 0.8978 | **11.11** |
| 6 | - | 0.9552 | **11.19** |
| 7 | - | 0.9629 | 10.73 |
| 8 | - | 0.9696 | 10.58 |
| 9 | - | 0.9748 | 10.12 |
| **mean** | **0.8297** | **0.8795** | |
| **wrap to frame 0** | **0.6510** | **0.1508** | |

**What actually happened, by eye:** turns 1 and 2 are clean and genuinely good, the
footprints appear as asked in a muted winter palette. At **turn 3 the chroma channels
detonate**: violent magenta and green noise erupts across the snow and sky with hard
outlining. From there it compounds monotonically, and by turn 6 the muted square is a
saturated neon riot with nothing of the original register left. Turns 7 to 9 stay neon.

### 10.6 The methodological finding, which matters more than the verdict

**Consecutive SSIM went UP as the chain died, and FireRed beat nano banana on the
project's own health metric while producing garbage.**

FireRed's mean consecutive SSIM is 0.8795 against nano banana's 0.8297, and its four
highest-scoring turns are 6 to 9, exactly the window the brief told us to watch. Read
naively, the ladder says the chain settled down. It did not settle: it **converged to a
fixed point that is not the painting.** Once the frame is saturated noise, consecutive
frames agree closely because the noise is the attractor.

If you take one thing from this bake-off, take this:

| instrument | what it saw | verdict |
|---|---|---|
| consecutive SSIM (neighbour to neighbour) | 0.88 mean, rising to 0.97 | **blind, and actively misleading** |
| **lapvar ratio against FRAME 0** | 0.64 to 7.55 between turns 2 and 3 | caught it at turn 3 |
| **SSIM of the last frame to FRAME 0 (the wrap)** | 0.1508 against nano's 0.6510 | caught it decisively |
| the eye, at native resolution | neon | caught it |

**Measure drift against frame 0, not against the neighbour.** Consecutive SSIM measures
step size; it cannot see a monotonic walk away from the original, because every individual
step is small. This extends the repo's standing "verify the way the user will experience
it" rule into the metric layer: a chain metric that only ever compares adjacent items
cannot detect divergence of the chain as a whole.

The single-edit Q1 crop test already forecast this. FireRed measured lapvar x1.38 on one
edit in a region it was not asked to touch; compounded over six edits that is x1.38^6, or
about 5.5, and we measured x11.19. nano banana measured x1.21 on one edit and yet its
chain ends at **x0.88**, because it re-blends rather than accumulating. **The per-edit
crispening ratio in an untouched region is the cheap predictor of chain survival, and it
costs one call.**

**No 40-step re-probe was run, deliberately.** The failure is not narrow and is not a
sampler artefact. Per-edit outputs at turns 1 and 2 are clean, so individual sampling
quality is not the problem; the defect is a positive feedback loop in a system that eats
its own output, and more steps change the per-step magnitude, not the sign. Turn 1
actually *softened* the image (lapvar 0.64) before the runaway, which is not the signature
of under-stepping.

### 10.7 Q4, the dual-endpoint bridge: it composites, exactly as predicted

Handed `ledB_snow` keyframes 0005 and 0000 with a request for the moment two thirds of the
way from the first to the second. A true in-between should be closer to each endpoint than
the endpoints are to each other.

| bridge | SSIM to 0005 | SSIM to 0000 | verdict |
|---|---|---|---|
| endpoints to each other | - | 0.6510 | the bar |
| naive pixel lerp at t=2/3 | 0.8149 | 0.9263 | ghosts, but is genuinely between |
| **nano banana `bridge_0003_0004`** | **0.7406** | **0.7167** | above its own endpoint bar (0.6640) |
| FireRed, plain prompt | 0.5812 | 0.5977 | **below the bar on both sides** |
| FireRed, explicit reference numbering | 0.5421 | 0.6319 | **worse**; fallback rung 1 does not help |

FireRed's bridge is a competent, plausible painting of a partly-trampled snowy square in
the right palette, with healthy surface (lapvar 262 against endpoints at 221 and 252). It
is simply **not this painting**: the buildings are rearranged and the composition is
re-derived. It made a third picture rather than a point on the path, which is section 6's
prediction almost verbatim, that multi-image conditioning was trained for compositing and
not for temporal interpolation.

Two forward notes for whoever picks this up:

- **Fallback rung 1 (explicit reference numbering) is dead.** It measured worse than the
  plain prompt. Do not spend on it again.
- **Rung 2 (latent SLERP plus a low-strength cleanup pass) is the live option**, and the
  numbers support it: a trivial pixel lerp already scores 0.81 and 0.93 against the
  endpoints. The problem with a crossfade is ghosting, not position, so a cleanup pass has
  something real to work with. Phase A already owns SLERP.

### 10.8 Measured economics, and the housekeeping

| candidate | GPU | load | per edit | 10-keyframe chain |
|---|---|---|---|---|
| klein 4B | L40S | 78 s | 2.7 s | ~0.06 USD |
| mageflow 4B | L40S | 29 s | 3.2 s | ~0.06 USD |
| firered 20B | A100-80GB | 132 s | 47 s (24 steps, true_cfg 4.0) | ~0.60 USD |
| nano banana | n/a | n/a | metered | 0.67 USD |

**State this plainly to Luca: FireRed was never a cost saving.** At roughly 0.60 USD per
chain against nano banana's 0.67, the migration case rested entirely on sovereignty,
reproducible seeds and exact dimensions, not on price. The 10x saving the brief hoped for
existed only in the two 4B models, and both failed the painterly gate on their first edit.
So even in the world where FireRed had passed Q3, the honest recommendation would have
been "equal cost, better reproducibility, worse preservation".

**Volume housekeeping.** `slow-interp-edit-cache` holds **73.7 GB measured** (FireRed
57.72, klein 15.98) plus Mage-Flow's ~17.5 GB, whose xet-backed blobs report zero size to
the volume API, so call it **~91 GB**. It is pure bake-off scratch; nothing in the render
path reads it. Luca decides whether it goes:

```
modal volume delete slow-interp-edit-cache
```

Keep it if a re-probe is likely within the month (it saves a 91 GB re-download); delete it
otherwise. `cloud/edit.py` recreates it on demand via `create_if_missing=True`.

### 10.9 What would change the answer

Nothing in the current open-weight field, on this evidence. The three things that would:

1. **A LoRA trained on our own corpus**, which the finding's section 6 already proposed for
   the interpolation problem and which applies equally to the register problem. FireRed
   ships full LoRA training code and is Apache 2.0, and it is the candidate worth training
   because it is the only one whose colour behaviour was already correct.
2. **A per-edit colour and frequency normalisation against keyframe 0**, applied to the
   low-frequency band only, using the Phase A.5 machinery. Section 5 proposed this as a
   free mitigation. Q3 shows it would have to fight an x11 surface explosion, so it is not
   sufficient alone, but a frame-0 anchored renormalisation is the obvious first thing to
   try on any future candidate.
3. **A model that does not eat its own output.** Every failure here is a feedback-loop
   failure. Authoring each keyframe from keyframe 0 plus a cumulative instruction, rather
   than from its predecessor, would break the loop at the cost of the accumulated history
   that makes our chains read as one continuous act. Worth a probe before the next
   three-way bake-off.

### 10.10 Reference ladders, computed free from frames already on disk

Consecutive SSIM over the nano banana chains, for anyone calibrating a future candidate:

| chain | frames | mean | min | wrap | note |
|---|---|---|---|---|---|
| `labor_embers` 1408x768 | 8 | **0.903** | 0.844 | 0.917 | the gated 10/10/9/9 piece; this is what healthy looks like |
| `ledB_snow` 1856x576 | 6 | 0.830 | 0.664 | 0.651 | two mid-chain pairs already below the bridging threshold |
| `ledA_window` 592x1792 | 6 | 0.429 | 0.401 | 0.258 | dusk-to-night; global SSIM is luminance-dominated here and is **not** a usable instrument |

Note the wrap column, not the mean. `labor_embers` closes at 0.917, near its own
consecutive average, which is what a loop that actually closes looks like. Do not use a
chain like `ledA_window` to judge preservation: when every keyframe changes the global
light level, SSIM measures the lighting change rather than the drift.
