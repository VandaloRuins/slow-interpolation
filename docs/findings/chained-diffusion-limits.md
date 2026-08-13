# What a chained img2img walk can and cannot hold

Date: 2026-08-08. Branch: main.
Source: ten Course of Empire renders (`outputs/empire/`), ~$6.10 of Modal, plus the
step-ladder and palette sweeps from the same day.

This is the distilled version. The per-experiment detail is in
[workstreams/quality-first/progress.md](../planning/workstreams/quality-first/progress.md)
and [denoise-step-budget.md](denoise-step-budget.md).

## The headline

**The pipeline is stable on content the LoRA was trained on and unstable on content
it was not.** Measured across ten renders: stages drawn from Cole's own repertoire
(storm, pasture, ruins) hold their sharpness and gain detail across the chain; a
modern city and a burning city lose it, every time, under every setting tried.

**Whether that is content complexity or the LoRA is UNTESTED as of 2026-08-09.**
The v10 experiment that was recorded here as decisive turned out to be a no-op:
`_pipe_call`'s ControlNet branch reassigned the kwargs dict and silently discarded
`cross_attention_kwargs`, which is the only path `lora_scale_per_segment` has to the
model, so every v10 frame ran at the base scale of 0.90 and nothing was ever halved.
Its "instability changed by 0% (1.234 to 1.235)" is the signature of a no-op, not
evidence about the LoRA. Fixed in `079598d`; the rerun against working code is queued
(quality-first L16 has the full account). Until it lands, treat the LoRA-vs-content
attribution as open.

What DID work was reducing the number of elements: v9 simplified the skyline from
twelve slender towers to five broad masses and scored `image 9/10`, the best of the
run. **Fewer things to keep consistent beats better weights to draw them with.**

## Coupled dials: change one, you must change another

Every regression this session came from moving one dial without its partner.

| If you raise | You must lower | Because |
|---|---|---|
| `num_inference_steps` | `steady_strengths` | More authority per frame becomes more drift |
| keyframe count | `steady_strengths` | Total drift is roughly K x per-frame change |
| keyframe count | `structural_decay_radius` | Decay fires once per keyframe and accumulates |
| `skip_boundary` | (accept velocity steps) | See the two-rhythms section |

**Watch the integer boundary.** Diffusers runs `int(num_inference_steps * strength)`
actual steps. At 12 steps, 0.44 gives 5 and 0.39 gives 4: a 20% loss of computation
from a rounding edge, invisible in the config. That single boundary caused v5's blur,
and crossing back over it was most of v6's fix.

## Two different rhythms, and they trade against each other

Blur in a chained render is not one thing.

**Sharpness pulse.** Sharpness peaks at every keyframe and troughs at RIFE's midpoint,
because an invented frame is a blend of two images that disagree. Measured swing:
29.8% (v2), 17.3% (v6), 7.5% (v7). Reads as the image breathing in and out of focus.

**Velocity rhythm.** Motion is slowest at each keyframe and fastest mid-pair. Measured
variation: 78.9% (v2), 57.6% (v6), **96.8% (v7)**. Reads as stepping rather than flow.

`skip_boundary` trades one for the other. Raising it discards the frames nearest each
keyframe, which are both the sharpest and the slowest, so the sharpness curve flattens
and the velocity curve gets worse. v7 had the flattest sharpness and the worst stepping
of any render. **`skip_boundary: 4` at `passes: 5` is the better balance**; 8 is only
right if breathing bothers you more than stepping.

Tools: [`pulse_plot.py`](../../tools/pulse_plot.py) draws both.

## Frame-average metrics lie, in three specific ways

This cost more time than any technical problem. A single sharpness number per clip hides:

1. **Temporal structure.** The pulse above averages away completely. A clip can average
   "sharp" while visibly breathing twice a second.
2. **Regional structure.** A dense city carries the frame average while sky and water
   stay soft. Band-wise measurement is needed.
3. **Per-stage structure.** A five-stage cycle that is sharp for 20 s and soft for 50 s
   reports as fine. **Always measure per stage.**

And **Laplacian variance is confounded by noise**: turning `structural_decay_radius` off
scored 3.5x on it while reading as a digital render. Cross-check with an FFT
high-frequency ratio, which is far less noise-biased. When the two disagree, believe the
FFT and believe the eye.

**Gemini's perceptual review contradicted the metrics repeatedly and was usually right
about whether something looked good.** Metrics find mechanism; they do not judge.

## What ControlNet fixed and what it did not

Structure is a conditioning problem, not a pixel problem.

- **Pixel-space re-assertion fails.** Blending each frame back toward an anchor sets up a
  tug of war with the diffusion and smears the surface. Tried at 0.08/0.15/0.25; all worse.
- **ControlNet works**, because it injects residuals at every denoising step instead of
  averaging the result. It is the only thing that ever put the intended landmark on screen.
- `guidance_end` matters more than `scale`. Around 0.6 the structure is set early and the
  model paints freely after; held to 0.8 it traces the map as flat slabs.
- **The map must not describe water.** Any grey value in a water region reads as ground:
  a steep ramp became a receding lawn, a flat mid value became a field. Leave water black.
- **Per-stage maps** (`control.images`) are required for a narrative cycle. One fixed map
  forces one geometry on every stage, which is how a wilderness stage got a city in it.

## Shipped this session

All backwards compatible, all default to previous behaviour.

| Feature | Field |
|---|---|
| Sampling dials reachable from YAML | `sampling.num_inference_steps`, `guidance_scale` |
| Skip the Lightning fuse | `models.lightning_lora: null` |
| Full VAE instead of TAESD | `models.vae_kind: full`, `vae_full` |
| Structural seed at warmup | `anchor_image`, `anchor_strength` |
| Per-frame anchor re-assertion (**failed, kept for the record**) | `render.anchor_reassert` |
| SDXL ControlNet | `control.{model,image,images,scale,guidance_start,guidance_end}` |
| Uneven stage pacing | `frames.steady_per_segment`, `transition_per_segment` |
| Per-stage LoRA strength | `style.lora_scale_per_segment` |
| Skip Phase A on Modal | `modal.skip_keyframes` |

## Dead ends, so nobody re-runs them

- **Externally staged keyframes at a fixed seed** (T1). Independently sampled frames
  morph rubberily: every small element is re-decided per frame. The chain works
  *because* each frame is a small edit of the previous image.
- **`frames.return_` raised to 4** at small K. Failed twice, in unrelated configs.
- **`structural_decay_radius: 0`.** Measures 3.5x sharper, looks digital.
- **Lowering `lora_scale` globally** to reach a modern subject. The style *prefix*
  carries the era; weakening weights while the prompt still says "Hudson River School"
  changes nothing.
- **AnimateDiff and StreamDiffusion.** See
  [workstreams/quality-first](../planning/workstreams/quality-first/progress.md) L10 and L15.

## Open, unresolved

**Stage III still blurs.** Ten renders in, the modern-city stage remains the weakest.
The untried routes are the rerun of the per-segment scale experiment (above), a LoRA
trained on modern architecture in a painterly register, or accepting a non-modern peak.

---
*Change note 2026-08-10: the v10 "decisive test" paragraph was rewritten after the
experiment was found to be a no-op (per-segment `lora_scale` never reached the model
under ControlNet; fixed in `079598d`). The trained-vs-untrained observation and the v9
fewer-larger-masses result are unaffected. See quality-first L16.*

---
*Counter-findings welcome. See [CONTRIBUTING.md](../../CONTRIBUTING.md) shape 4.*

> **Instrument note (2026-08-11):** `tools/pulse_plot.py` and `tools/motion_profile.py`, referenced in this finding, are deprecated in place, superseded by `tools/analyse_render.py`. The validated instrument set, with noise floors and sensitivities, is [render-quality-instruments.md](render-quality-instruments.md).