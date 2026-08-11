# Measuring a render: what each instrument sees, and what none of them see

Date: 2026-08-11. Branch: main.
Source: `tools/artefact_sim.py`, `tools/detector_bench.py`, `src/slow_interpolation/quality.py`,
a 72-clip synthetic corpus, and a hand-labelled set of real renders.

You are an agent judging whether a render is good enough to publish. Read this before
inventing a metric. Eight were invented and withdrawn in a single day because they were
never tested against anything with a known answer.

## The method, which matters more than any individual number

**Do not fit a detector to a judgement.** On 2026-08-11 five statistics for the painted
canvas edge and three for rubbery morphing were each invented, eyeballed against a handful
of clips, and believed. All eight failed. The reason was not the maths. Each was fitted to
ONE Gemini label per clip, at +-1 noise, across clips that differed in backbone, subject,
palette and schedule simultaneously.

**Manufacture ground truth instead.** [`artefact_sim.py`](../../tools/artefact_sim.py)
injects a defect into a clean render at a stated amplitude, so you know exactly what is in
the result and how much. [`detector_bench.py`](../../tools/detector_bench.py) then asks
three questions no eyeball can answer: is the score monotonic in amplitude, what is the
smallest amplitude it can see, and does it stay quiet on other defects.

Two rules make the output usable as evidence:

- **amp=0 is an exact no-op**, asserted in `tests/test_quality.py`. A control differs from
  a positive by the injection and nothing else.
- **Compare against the amp=0 RE-ENCODE, never the original file.** Re-encoding is lossy,
  so the original carries different codec noise from everything the simulator writes.

## Sensitivity: the smallest defect each instrument can see

Validated against known amplitudes on two different base clips. "min" is the smallest
injected amplitude whose score moves further than the 8% run-to-run floor.

| instrument | detects | rho | min detectable |
|---|---|---|---|
| `focus_mean` / `focus_trough` / `focus_p05` | blur | -0.94 | sigma **1.0** |
| `speed` | deformation | +1.00 | **0.5 px** |
| `rigid` | deformation | -0.94 | **1.0 px** |
| `warp_resid`, `coherence` | deformation | +1.00, +0.97 | **2.0 px** |
| `jitter` | decimation | +0.89 | ratio **1.10** |
| `jitter` | flicker | +0.91 | **1%** gain |
| `flicker` count | dropped frames | +1.00 | **1** per boundary |
| `b_detail` | canvas edge | -1.00 | **16 px** band, WITHIN SUBJECT |

**Report the trough, never the swing alone.** A normalised swing hides whether the floor
moved: one config read as a 21% regression on `focus_swing` while its softest moment was
6.8% *sharper*. `focus_swing` is also the weakest blur detector in the table (rho +0.54).

**Flow settings were chosen by measurement, not argument.** 864x270 at step 3. The
intuition that a 0.13 px/frame drift needs a longer baseline is wrong: at step 10 coherence
collapses to rho +0.09, because the flow field decorrelates faster than motion accumulates.

## The rule that decides how to read any of this

**`b_detail` and every `focus` column are WITHIN-SUBJECT measures.**

On the real corpus `focus_mean` appears to separate four defective clips from four clean
ones by a factor of four. It is measuring nothing of the sort. The defective four are
Renoir and Soutine and the clean four are Cole and Casa, so any feature that varies by LoRA
family "separates" them. Seven features passed that test and six of them are confounds.

The check that survives is **within subject**. `led18_renoir_field` (canvas edge, verified
by eye) against `led19_renoir_base` (edge gone, verified by eye), same prompt and seed:

| feature | edge present | edge gone | synthetic ladder |
|---|---|---|---|
| **`b_detail`** | 0.674 | 0.950 | **-31%, and monotonic on both bases** |
| `b_streak_mean` | 0.399 | 0.732 | reverses direction above 48 px |
| `b_hf` | 1.263 | 0.719 | reverses direction above 48 px |
| `b_edgepeak` | 1.424 | 1.467 | no movement on the real pair |
| `b_orient` | 0.057 | 0.061 | no movement on the real pair |

One of six candidates survives. Use `analyse_render.py --against <same-subject clip>`.
Without a baseline there is no absolute border threshold and there cannot be one.

## The cause, not the symptom

The most useful measurement here is not of the video at all. It is of the **keyframes RIFE
was handed**, kept on the `slow-interp-outputs` volume under `staging/<name>/keyframes/`
whenever `modal.preserve_staging: true`.

Luca, 2026-08-11: *"the interpolation smoothness is also given by the detail and
composition differences between the interpolated frames."* That is measurable as
`kf_ssim`, the agreement between consecutive keyframes. Low agreement means the
interpolator has more to invent, and inventing is what reads as rubbery morphing.

Measured at half scale (see the memory note below).

| render | strength | `kf_ssim` | travel | perceptual verdict |
|---|---|---|---|---|
| `led20_base_s30` | 0.30 | **0.887** | 0.27 px | |
| `led20_base_s35` | 0.35 | 0.882 | 0.31 px | loop 9, image 9 |
| `led20_base_s40` | 0.40 | 0.873 | 0.32 px | |
| `led19_renoir_base` | 0.46 | 0.854 | 0.59 px | the only earlier clip with **no morph flag** |
| `led18_renoir_field` | Lightning | **0.357** | 1.33 px | motion 7 |
| `led18_cole_woods` | Lightning | 0.332 | 1.70 px | morphing named |

Two things fall out, both within subject on an identical prompt.

**SDXL base more than doubles keyframe agreement** against its Lightning twin, 0.854
against 0.357. That is the mechanism behind its clean motion score.

**Keyframe agreement is monotonic in `steady_strengths`**: 0.30 gives 0.887 and 0.46 gives
0.854, with travel halving from 0.59 px to 0.27 px. So this IS the dial, and it trades
against the light arc, because keyframes that agree completely are keyframes that never
evolve. Look for the knee, not the maximum.

## One confound that was tested and cleared

**The blur detector is not just reading the light arc**, which was the obvious way for it
to be wrong in a pipeline whose subject IS a light change. On `led20_base_s35`, luminance
and focus correlate at **r = -0.658**, the wrong sign for that failure mode, and at both
frames Gemini flagged as soft the luminance sits at the median (1.01x and 1.00x) while
focus is 0.64x and 0.76x. The softness is real and independent of the light. Re-run this
check on any subject whose arc is much larger.

## The warm-up ramp: intrinsic to the base chain, three fixes tried and refuted

Found by measuring the KEYFRAMES rather than the video, on `led20_base_s35`. The first
three keyframes score 3.2 / 3.4 / 10.6 against 34.1 at keyframe 7, a **4.16x ramp**, and
both blur flags Gemini confirmed sit inside it. The folded mid-pair pulse is only 16%, so
the interpolator is innocent, and the light arc is ruled out separately (r = -0.658).

**Lightning and base run opposite trajectories through the chain.** Lightning starts sharp
and decays (2.60 to 0.41 by keyframe 6); base starts soft and builds. This is a
base-specific fault.

| attempt | ramp | kf_ssim | what actually happened |
|---|---|---|---|
| `led20_base_s35` control | 4.16x | 0.882 | keyframe 7 peaks at 34.1 |
| `steady_noise_blend` 0.08 to 0.03 | 3.34x | 0.868 | **10x SOFTER mid-chain** (kf5 18.6 to 1.7) |
| front-loaded strengths | 3.32x | 0.872 | held sharpness, **broke the loop**, Gemini 9 to 6 |
| `warmup` 3 to 8 | **2.02x** | **0.893** | flattest ramp, but the CEILING collapsed 34.1 to 10.5 |

**Every one of the three flattened the ratio by lowering the whole curve.** None raised the
opening. Read the absolute keyframe values, never the ramp ratio alone: two of these three
would look like wins on the ratio and both are regressions.

**Mechanism, and it is the useful part.** In the base chain, detail is ACCUMULATED by the
img2img walk itself, and **the noise walk supplies the raw material it accumulates from**.
That is why cutting `steady_noise_blend` made things worse rather than cleaner: the noise
is not a contaminant the model has to clean, it is the high-frequency stock the model
organises into brushwork. And it is why warmup cannot pre-bake the detail: eight strong
passes converge the canvas to something smooth that the chain then has less to build from.

**The consequence for the loop.** The clip runs soft to sharp and then wraps, joining the
sharpest keyframe to the softest, which is a sharpness step at the wrap. The untried route
is not another dial: render extra lead-in keyframes and DISCARD them, so only the resolved
part of the chain ships.

## What no instrument here can see

Record these rather than re-deriving them.

1. **Rubbery morphing has no direct detector.** Three flow measures were tried against the
   perceptual verdict: `residual_px` tracks speed almost exactly, spatial roughness spans
   0.148 to 0.239 with no ordering, and temporal coherence ranks the one clip with *no*
   morph flag LOWEST at 0.492. They do respond to *injected* deformation, so they measure
   deformation; they do not reproduce the judgement. Use `kf_ssim` for the cause and Gemini
   for the verdict.
2. **The canvas edge is invisible to Gemini.** It never raised a border flag on renders
   carrying an obvious 55px band, because it watches a downscaled clip and the band is 3%
   of the width. `review_gate.py` writes native edge strips for this reason.
3. **The `lurch` ratio does not detect *injected* lurch** (rho +0.09), because dropping
   frames shifts the boundary indices the metric is looking at. It does detect the real
   artefact, which changes interpolation spacing rather than dropping frames: 2.31 on
   `led13_c_realloc_soft` against 0.99 on `led17_c_dense`, far outside the +-2% floor.
   Injected lurch shows up on `flicker` (rho +1.00) instead. The simulation is an imperfect
   model of the real mechanism; the real mechanism is covered.

## Two environment traps that cost an hour

**Never import the package to use these tools.** `from slow_interpolation.quality import
...` runs `slow_interpolation/__init__.py`, which imports `Pipeline`, which imports
`torch`, which maps roughly 2 GB of CUDA DLLs that no measurement here uses. On a loaded
machine that turns into `OSError [WinError 1455] The paging file is too small`. All three
tools load `quality.py` directly by path instead.

**`modal volume get` on a DIRECTORY silently writes nothing on Windows**, prints "Finished
downloading files to local", exits 0, and leaves a FILE where the directory should be, so
every later `mkdir -p` fails with "Not a directory". Single-file gets work. Enumerate with
`modal volume ls` and pull one file at a time.

## Noise floors

From re-running one config unchanged (`led15_c_repro`). A difference smaller than its floor
is not a result.

| quantity | floor |
|---|---|
| arc swing | +-0.1% |
| `lurch` | +-2% |
| `focus_mean` | +-1.3% |
| `focus_trough` | +-1.6% |
| `loop` | +-8% |
| Gemini `loop` | **+-2 points** |
| Gemini `motion` / `image` / `subject` | **+-1 point** |

Gemini's spread is why `review_gate.py` takes the median of three runs and keeps a flag
only when a majority back it. On one clip that dropped 15 of 15 flags as unsupported, and
an earlier single-sample verdict of 9/9/8/9 did not reproduce.

## Superseded

`tools/pulse_plot.py` scaled to 448x256 before measuring sharpness, destroying the
frequencies it reported, using Laplacian variance that
[chained-diffusion-limits.md](chained-diffusion-limits.md) already records as
noise-confounded. `tools/motion_profile.py` used a per-frame delta, which cannot separate a
light change from a movement in a pipeline whose subject IS a light change. Both are
deprecated in place and still run; build on `analyse_render.py`.

---
*Counter-findings welcome. See [CONTRIBUTING.md](../../CONTRIBUTING.md) shape 4.*
