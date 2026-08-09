# The denoise step budget: every keyframe ever rendered got 2 steps

Date: 2026-08-07.
Branch: main.
Status: Finding 1 confirmed in code and in a live container log. Findings 2 and 3 are
hypotheses with probes specified but not yet run.

## Question

The NYC billboard exploration opened with "the outputs are not good enough". The obvious
suspects were the LoRA, the prompt and the subject. None of them turned out to be the first
thing to check.

This finding documents what the pipeline was actually spending on each keyframe, why it was
invisible, and the config schema change that makes it adjustable.

## Finding 1: `num_inference_steps` was hardcoded, and interacts multiplicatively with `strength`

[`keyframes.generate_keyframes`](../../src/slow_interpolation/keyframes.py) declares:

```python
guidance_scale: float = 1.5,
num_inference_steps: int = 4,
```

and [`pipeline.py`](../../src/slow_interpolation/pipeline.py) called it without passing
either. So both sat at the function default and **neither was reachable from YAML**. That is
the whole reason nobody had ever swept them: they did not look like dials, they looked like
constants.

The multiplicative part is the trap. Diffusers img2img does not run `num_inference_steps`
steps. It runs:

```python
int(num_inference_steps * strength)
```

`RenderProfile.standard` sets steady strengths around 0.55. So:

```
int(4 * 0.55) = 2
```

**Two denoising steps per keyframe.** Transition frames at 0.65 also get 2. Only the first
warmup frame at 0.85 gets 3. That is the entire computation budget behind every frame of
every render this project has shipped, including the three banked billboard deliverables.

### How to verify it yourself

Two ways, both free:

```python
from slow_interpolation.config import SamplingConfig
d = SamplingConfig()
print(int(d.num_inference_steps * 0.55))   # 2
```

Or read any Modal container log. The per-keyframe diffusers progress bars read `2/2`.
`modal run -m cloud.smoke` prints them and costs $0.018.

### Why this matters more than it looks

Two steps is not "a bit fast". It is at the floor of what SDXL Lightning can do, and the
chain compounds the shortfall: each keyframe is the next keyframe's input, so a surface that
is slightly under-resolved at keyframe 0 is the starting point for keyframe 1.

It also reframes an existing open question. The 2026-05-18 backbone probe
([alt-techniques brainstorm](../planning/private/alt-techniques/brainstorm.md), FLUX verdict)
found SDXL base at 30 steps carried painterly brushwork that SDXL Lightning smoothed out, and
filed "is Lightning bottlenecking our LoRAs' brushwork" as a follow-up. That probe rendered
Lightning at its full 4 steps at strength 1.0. **The production chain runs at half that**, so
the pipeline sits below the worst case that probe measured.

### The two dials are separable, and only one of them is a drift control

This is the part to internalise, because it is what makes the fix cheap:

- **`strength`** sets how far back in the noise schedule each frame re-enters. That is the
  *amount of change*, and it is the drift control. Raising it makes the piece move faster.
- **`num_inference_steps`** sets how finely that same distance is traversed. That is the
  *quality*, and it is not a drift control at all.

So raising steps at fixed strength buys strictly more model authority per keyframe at
identical drift rate. It is close to a free quality dial, bounded only by GPU time and by
whether the distilled Lightning weights tolerate finer steps than they were distilled for.

## Schema change shipped 2026-08-07

New [`SamplingConfig`](../../src/slow_interpolation/config.py), threaded through
[`pipeline.py`](../../src/slow_interpolation/pipeline.py) into `generate_keyframes`:

```yaml
sampling:
  num_inference_steps: 12    # was hardcoded 4
  guidance_scale: 1.5
```

Two companion changes on `ModelsConfig`, both needed to run the ladder in Finding 2:

```yaml
models:
  lightning_lora: null       # skips the Lightning fuse AND the trailing-timestep
                             # scheduler swap, which is a Lightning requirement
  vae_kind: full             # AutoencoderKL from `vae_full` instead of TAESD from `vae`
```

Backwards compatible. Every existing config loads with identical defaults (verified against
`billboard_a_arch.yaml`, `tcole_valley.yaml`, `smoke.yaml`, `roses_bloom_cycle_60s_v5.yaml`);
60 tests pass.

Note `vae` and `vae_full` are deliberately separate fields. The latent scaling factors differ
(TAESD 1.0, SDXL KL 0.13025) and each repo carries its own, so pointing one class at the
other's repo produces silent colour garbage rather than an error.

## Finding 2 (hypothesis): the step ladder

Five rungs, one chain of 7 keyframes each, same prompts, same strengths, same seed. Compare
keyframe `0000` against `0006` on each rung, so one run reads both surface quality and chain
survival.

| Rung | Change | Real steps/frame | Isolates |
|---|---|---|---|
| 0 | as shipped | 2 | control |
| a | `num_inference_steps: 12` | 6 | step count, same backbone |
| b | 8-step Lightning weight, 16 steps | 8 | more steps, in family |
| c | `lightning_lora: null`, 30 steps, guidance 7.0 | 16 | undistilled base |
| d | `vae_kind: full` | 2 | VAE round trip only |

Rung a is off-distribution on purpose. The 4-step Lightning LoRA is distilled to take large
steps and may degrade rather than improve when run finely. Worth knowing, free to find out.

Rung c is **not** a clean single-variable test and should not be read as one. At guidance 1.5
the classifier-free term is small and negatives have weak authority; at 7.0 they bite hard,
which is the mechanism [`narrative-arc-drift.md`](narrative-arc-drift.md) Finding 1 depends
on. Rung c changes the sampling regime, not just the step count.

**Rung c also needs a schedule-calibration twin.** The
[modal workstream log](../planning/workstreams/modal/progress.md) 2026-05-19 entry predicted
that `steady_strengths` tuned for Lightning's 4-step regime will over-cook under base, and
proposed halving them (0.30 steady, 0.40 transition) as a starting guess. Its stated mechanism
("effective denoise = steps x strength") is loose: `strength` picks the entry sigma, so the
starting noise level is identical at 4 and 30 steps and only the refinement density changes.
The concern is still real, just for a different reason. More refinement from the same entry
point gives the model more opportunity to impose its prior, so content departs further from
the input frame. Whether that reads as over-cooked is empirical, so run both:

| Rung | Change |
|---|---|
| c | base, 30 steps, guidance 7.0, **strengths held** (clean isolation) |
| c2 | base, 30 steps, guidance 7.0, **strengths halved** to 0.30 / 0.40 (the workstream's guess) |

Without c2 a bad result from c is unattributable: it could mean base is wrong for this
pipeline, or only that base at an uncalibrated schedule is. One extra render, about $0.12.

Cost, against the measured L40S model (36 s fixed + 2.3 s per keyframe at 1344x768): about
**$0.31 for the whole ladder**, roughly 4 minutes wall as a batch fan-out.

## Finding 2 RESULT (2026-08-07): the VAE won, the step count did not, and base failed

Eight rungs, 63 s wall, **$0.1888**. Measured across all 384 frames of each clip with
[`tools/analyse_ladder.py`](../../tools/analyse_ladder.py), not from poster frames.

| Rung | detail | hf_ratio | drift | loop | decay |
|---|---|---|---|---|---|
| r0 control | 119.2 | 0.410 | 4.81 | 0.32 | 3.20 |
| ra steps12 | 73.9 | 0.395 | 7.34 | 0.20 | 3.83 |
| rb lightning8 | 72.8 | 0.391 | 6.79 | 0.21 | 5.33 |
| rc base held | 67.0 | 0.429 | 3.48 | 0.23 | 2.55 |
| rc2 base halved | 105.5 | 0.409 | 2.79 | 0.16 | 2.16 |
| **rd vae full** | 75.6 | 0.391 | 4.41 | 0.23 | 2.58 |
| rw0 soutine | 57.2 | 0.230 | 6.88 | 0.24 | 10.12 |
| rwa soutine | 64.4 | 0.246 | 13.01 | 0.18 | 11.07 |

**Winner: `vae_kind: full`.** Same 2 steps as the control, one line changed, no extra compute.
It recovers the atmospheric depth TAESD was crushing: real haze on the distance, a clean value
ladder from dark mass to luminous opening, stable composition across the full duration. Finding
3 below is therefore CONFIRMED, and the culprit was the VAE rather than the step budget.

**SDXL base fails at video scale, both schedule variants.** `rc` is a murky brown-green wash
with the luminous opening gone; `rc2` is worse, soft as well as dark. This answers the question
the [modal workstream](../planning/workstreams/modal/progress.md) queued on 2026-05-19 and never
ran: the keyframe-level win Luca called that day does **not** survive a chained img2img walk.
**The pipeline stays on Lightning.**

**Step count trades atmosphere for texture on Cole, so it is not a free win.** `ra` and `rb`
both gain brushwork and lose luminosity. `rb` needs a different Lightning weight and 4x the
control's compute to deliver what `ra` already does, so the in-family test came back neutral.

### Three things worth more than the verdict

**1. The chain ACCUMULATES detail. It does not wash out.** `decay` is above 1.0 on every rung,
from 2.16 to 11.07: keyframe 6 carries 2 to 11 times keyframe 0's Laplacian variance. Both this
repo's docs and the working assumption behind this whole probe had it backwards. That makes
`structural_decay_radius` more load-bearing than it has been treated, not less, and it is now
the obvious next dial.

**2. Read `detail` and `hf_ratio` together or you will draw the wrong conclusion.** `rc` scored
the LOWEST Laplacian variance and the HIGHEST high-frequency share of the Cole rungs. That
combination means abundant fine grain with no strong edges, i.e. noise, not brushwork. Either
metric alone would have called `rc` a winner. Laplacian variance also rewards the control's hard
clean CG-brick edges, which is why r0 tops the table while looking the least like paint.

**3. Loop closure is a non-issue at K=7.** Every rung wraps at 0.16 to 0.32 of a typical
inter-frame step, so the seam is *smoother* than an ordinary transition. This is consistent
with [narrative-arc-drift.md](narrative-arc-drift.md) Finding 2 for the palette-drift case, and
it holds even with `frames.return_: 1` making the return mechanism inert.

### Soutine: a dataset problem, not a tuning problem

Both Soutine rungs carry a persistent fake **signature artifact** in every frame, which is
auction-catalogue training data leaking through. At 2 steps the output is flat and naive; at 6
steps real paint handling appears but on the wrong painter, reading as Utrillo rather than
Soutine. `hf_ratio` sits at 0.23 to 0.25 against Cole's 0.39 to 0.43. Step count does not fix
either problem. Route to `dataset-mosaic` before any further Soutine render.

## Finding 3 (hypothesis): TAESD's loss compounds across the chain

[`load_sdxl_pipeline`](../../src/slow_interpolation/keyframes.py) replaces the SDXL VAE with
`madebyollin/taesdxl`, a distilled tiny autoencoder. It is fast, fp16-stable and saves about
1 GB, which is why it is there.

But the chain decodes to pixels and re-encodes to latents **once per keyframe**. On a
7-keyframe render that is seven lossy round trips in series. TAESD is benchmarked as
near-lossless for *one* round trip. Nobody designed or measured it for seven in a chain.

Rung d isolates this: one line changed, same backbone, same steps, same seed. It is the
cheapest rung and the cleanest single-variable test in the set.

Stated as a hypothesis rather than a finding because it has not been run. If accumulated
softness is the complaint, a compounding lossy autoencoder is a better suspect than most.

## What would change the verdict

- **Rung a degrades.** Then the distilled Lightning weights genuinely do not tolerate fine
  steps, and the quality path runs through rung b or c rather than through step count alone.
- **Rung d is indistinguishable.** Then TAESD is not the problem and Finding 3 gets a
  "tested, rejected" footer. Do not delete it; the next agent needs to see it was checked.
- **Rungs a to d are all indistinguishable from the control.** Then the step budget was never
  the bottleneck, this finding downgrades to a documentation note, and the search moves back
  to LoRA, prompt and subject.

## Related

- Denoise-as-entry-timestep. StreamDiffusion has no `strength` parameter at all; it expresses
  denoise as an explicit list of scheduler timesteps to visit, which decouples entry point
  from step count *and* allows non-uniform spacing. Full anatomy at
  [workstreams/quality-first/progress.md](../planning/workstreams/quality-first/progress.md)
  learning L10, pending promotion to its own finding. Worth building only after the ladder
  says whether step count matters.
- [`upscale-source-resolution.md`](upscale-source-resolution.md) for the resolution buckets
  these probes should run in.

## Source artefacts

- [src/slow_interpolation/config.py](../../src/slow_interpolation/config.py) `SamplingConfig`, `ModelsConfig.vae_kind`, `ModelsConfig.lightning_lora`
- [src/slow_interpolation/keyframes.py](../../src/slow_interpolation/keyframes.py) `load_sdxl_pipeline` VAE and Lightning branches
- [src/slow_interpolation/pipeline.py](../../src/slow_interpolation/pipeline.py) sampling pass-through

---
*Did you reproduce this and observe something different? Counter-findings welcome. See [CONTRIBUTING.md](../../CONTRIBUTING.md) shape 4 and the [finding issue template](../../.github/ISSUE_TEMPLATE/finding.md).*
