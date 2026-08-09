# Workstream: quality-first

**Opened** 2026-08-07. **Status: open, pre-prioritisation.**

## Why this workstream exists

Luca's call on 2026-08-07: *"I am not satisfied with current slow interpolation outputs and
want better outputs, so this research phase leading to a better-tested direction is a
priority."*

That inverts the NYC billboard framing. The billboard's three delivery files are banked and
spec-verified in `outputs/nyc-billboard/delivery/`, so nothing ships on a deadline from here.
This workstream is about the technique's output quality, and the billboard is downstream of
it, not the other way round.

**Read this file before doing any work on the render stack.** It holds every learning from
the 2026-08-07 session, every open direction, and the task board. It is deliberately one file
so the prioritisation conversation has one surface.

---

## Learnings

Numbered so the task board and the conversation can reference them. "Promotion" is where a
learning should end up per [docs-strategy.md](../../docs-strategy.md); most are not there yet.

### L1. Every keyframe ever rendered got 2 denoising steps

`num_inference_steps` was hardcoded at 4 and unreachable from YAML; diffusers img2img runs
`int(num_inference_steps * strength)`, and steady strength is 0.55. `int(4 * 0.55) = 2`.

Confirmed in code and in a live Modal container log (`2/2` on every keyframe progress bar).
Applies to all three banked billboard deliverables and every render before them.

**Promotion: DONE.** [findings/denoise-step-budget.md](../../../findings/denoise-step-budget.md).

### L2. `strength` and `num_inference_steps` are separable, and only one is a drift control

`strength` sets the re-entry point in the noise schedule, which is the amount of change.
`num_inference_steps` sets how finely that distance is traversed, which is quality. Raising
steps at fixed strength buys model authority at identical drift rate.

**Promotion: DONE**, same finding.

### L3. TAESD does seven lossy round trips per render

`load_sdxl_pipeline` swaps in `madebyollin/taesdxl`. The chain decodes and re-encodes once per
keyframe, so a 7-keyframe render is seven round trips in series. TAESD is benchmarked
near-lossless for one. Hypothesis, probe specified (rung d), not run.

**Promotion: DONE as a hypothesis**, same finding.

### L4. LoRA checkpoint facts, read off the safetensors headers

Nowhere in the docs. Refutes the assumption that Cole is a "floral preset" LoRA.

| LoRA | rank / alpha | LR | text encoder | modules | size |
|---|---|---|---|---|---|
| Thomas Cole ep10 | 32 / 32 | 5e-4 | **trained**, 792 keys | 986 | 218 MB |
| Soutine ep10 | 32 / 32 | 5e-4 | none | 722 | 163 MB |
| Renoir ep10 | 16 / 8 | 3e-5 | none | 722 | 81 MB |
| Casa del Suono ep4 | (unread) | | | | 218 MB |

Consequences: Cole and Soutine have identical `alpha/rank`, so **Soutine at a given
`lora_scale` is not "hotter" than Cole at the same scale**. Cole was trained with what
[expressionist-style-preset.md](../../../findings/expressionist-style-preset.md) calls the
expressionist preset, not the floral one. And Cole is the only checkpoint with a text-encoder
arm, which [`_load_style_lora`](../../../../src/slow_interpolation/keyframes.py) probably
discards: it catches a diffusers `IndexError` on Kohya text-encoder keys and reloads UNet-only,
and names Cole as a checkpoint that trips it. Unverified at runtime; log it on the next load.

**Promotion: pending.** Task T7.

### L5. Cole's `lora_scale` has never been swept and has no decisions-log entry

`0.75` is inherited unchanged from the legacy After Cole pipeline through
`examples/configs/tcole_valley.yaml` into every Cole config in the repo. It is a legacy
default, not an empirical call. The only two scale datapoints in the repo are Renoir, and
both point the same way: dropping scale killed the style.

**Promotion: pending.** Task T8.

### L6. `rife.sinusoidal` is a per-pair pulse, not clip-level easing

`linear_interp` eases between *each keyframe pair*, so 7 keyframes gives 7 ease cycles per
loop, roughly a 0.7 Hz throb. That contradicts the technique's "glacial motion that never
pauses" thesis. It may still be wanted, but judge it as breathing mode, not as pacing.

True clip-level easing (slow start and end across the whole clip) is **not available from any
current knob**; it would be a `setpts` curve inside `conform.py`.

### L7. `skip_boundary` cuts by frame index, not by timestep, and sinusoidal breaks it

`skip_boundary` exists to drop RIFE's decelerating boundary zones. Under sinusoidal the
timesteps cluster toward `t=0` and `t=1`, so `skip_boundary: 4` trims 1.5% of the interval
instead of linear's 7.8%, a 5.2x shortfall, while simultaneously *deepening* the zone it was
meant to remove.

Correct equivalent is `skip_boundary: 24` at `passes: 7`. Frame arithmetic:

```
total = K * (2^passes - 1 - 2 * skip_boundary) - 1
```

`conform.py` refuses below 300 frames, which makes sinusoidal at the correct boundary
**incompatible with 7 keyframes at `passes: 6`**. You cannot flip the flag alone.

### L8. `frames.return_: 1` makes the return mechanism completely inert

Both billboard configs set it. At `n=1`, `progress` is 0, so `pixel_blend` is 0 and
`return_strength_end` is never reached. Zero anchor pull. The loops close only because the A
and A-return prompt strings are byte-identical and the RIFE wrap pass bridges the gap.
`return_: 2` is *worse* than 1 (the blend snaps to max in one step); 4 is the minimum for a
real ramp.

This is fine while the drift stays light-only and K stays 7. Any increase in K raises the
last-return-to-anchor gap and forces `return_` back to at least 4.

### L9. A content arc cannot read as slow drift in 10 seconds

[narrative-arc-drift.md](../../../findings/narrative-arc-drift.md) Finding 2's `return_: 10`
was authored at K=39 on a 60 s piece. Preserving the quantity that actually matters, the final
pixel-blend step, gives `return_: 6` with `return_pixel_blend_max: 0.35` at small K. But a
real content arc also needs `return_/K` under about a third, forcing K to 16 or 17, which is
2.3x the current drift rate inside a fixed 10 s. That reads as time-lapse.

**So "the subject changes" and "10 seconds of slow drift" are close to mutually exclusive.**
Put the meaning in the subject, not in the arc.

### L10. StreamDiffusion transfer verdict

- **Stream Batch does not transfer.** Proven from the code: the shift register holds
  partially denoised states of the previous N-1 *external* frames, a frame fed at call n exits
  at call n+N-1, and every consumer feeds an external source. Our chain is a feedback loop.
  The one `feedback_safe` flag is TouchDesigner latency compensation, not feedback.
- **RCFG cannot be lifted piecemeal.** `stock_noise` is written at three sites across two
  methods and only converges under stream continuity. Taking it means taking the batch layout
  and the fixed-noise policy, which collides with our noise-walk module.
- **The canonical package has zero SDXL support.** No `text_encoder_2`, no
  `added_cond_kwargs`, no pooled embeds. SDXL support exists only in the vendored
  `StreamDiffusionTD/` TouchDesigner fork in the same checkout, which *is* a usable reference
  implementation if the live path is ever built.
- **The one thing worth stealing is `t_index_list`**: denoise as an explicit list of
  scheduler timesteps to visit rather than a strength scalar. About 30 lines. The LCM boundary
  machinery around it can be dropped (`c_skip` is ~7e-6 across the whole usable range, i.e.
  numerically the identity).

**Promotion: pending.** Task T9.

### L11. Modal is installed, authenticated and working

The billboard handover's "modal is not installed" was true only of the repo's active Python
3.10. It is installed under 3.11 with the CLI on PATH, profile `vandaloruins`, and
`modal run -m cloud.X` works today with zero setup.

- Spend: **$0.00 this month**, $21.00 in May across 70 invocations. Measured medians: render
  $0.050, validation grid $0.020, training $0.112 (max observed $1.61).
- Fitted cost model: **36 s fixed + 2.3 s per keyframe at 1344x768 on L40S.**
- All weights already on volumes, **including FLUX.1-dev and FLUX.1-schnell**. Nothing to
  upload for any probe below.
- Smoke re-verified 2026-08-07: `SMOKE PASS`, 33.8 s, $0.0183, no image rebuild needed.
- L40S is the right tier. A10G fits but runs ~2x the wall, losing on both axes.

### L12. Three tooling gaps

- **`docs/manual/modal-operations.md` lines 135 and 163 tell agents to run `modal token
  current`, which does not exist in modal 1.4.2.** An agent following that branch reads a
  healthy account as unauthenticated and pushes the user into a pointless signup flow. This
  very likely produced the billboard handover's false claim. Working command is
  `modal profile current`.
- **`tools/gallery.py` globs `*.mp4` only**, so it cannot display a stills contact sheet, and
  it surfaces only `rife.passes` from a config, so movement variants render as identical
  cards. The existing PNG-grid pattern is `outputs/validation/comparison.html`.
- **`cloud/app.py` mounts all of `examples/` (109 MB) on every dispatch**, of which
  `examples/outputs/` is 101 MB of MP4s the container never reads. Costs 5 to 15 s of local
  latency per dispatch, no dollars.

### L14. The Lightning-versus-base question was already answered at keyframe level, and the test has been waiting three months

Found 2026-08-07 while rebuilding the gallery, in
[workstreams/modal/progress.md](../modal/progress.md) 2026-05-19. Not lost, just never picked
up.

- `cloud/validate_backbone.py` was extended to load a domain LoRA per backbone, and the probe
  ran: `examples/configs/validation/renoir_lora_lightning_vs_base.yaml`, Renoir epoch 10 at
  0.85, five painterly prompts, both backbones. Outputs and a contact sheet are on disk at
  `outputs/validation/renoir-lora-lightning-vs-base/`.
- **Luca's verdict, 2026-05-19: "sdxl base reads more the painting brush".** So the Renoir
  LoRA does *not* compensate for Lightning's 4-step smoothing. The keyframe-level result
  survives with the LoRA applied.
- That entry also states plainly that **SDXL base has never been run through the video
  pipeline**, and specifies the plumbing needed: `lightning_lora` made optional,
  `guidance_scale` and `num_inference_steps` threaded out of function defaults, "~30 lines".
  That is exactly what shipped today, arrived at independently.
- It recommends one minimum-scope SDXL-base clip with a halved denoise schedule, ~$0.10 to
  $0.25, and closes with **"NOT executed in this session, awaiting Luca's go."**

**Consequences.** T1 is not a new idea, it is the execution of a test that has been queued
since 2026-05-19, now broader (5 rungs instead of 1) and with the plumbing actually built. And
the workstream's schedule-calibration warning adds a rung: run base with strengths held *and*
halved, or a bad result is unattributable. See
[denoise-step-budget.md](../../../findings/denoise-step-budget.md) Finding 2.

**Process note worth keeping.** Two sessions independently derived the same ~30 lines three
months apart because the first one's conclusion lived in a workstream log nobody read on
resume. The billboard session then rebuilt on Lightning defaults without knowing base had
already won a visual call.

### L15. AnimateDiff cannot paint our in-betweens, and the reason is architectural

Anatomy pass 2026-08-07 against the locally installed diffusers 0.38.0, with the load-order
claims executed on CPU rather than reasoned about.

**Everything that would make keyframe-anchored inbetweening work is SD1.5 only.**

| Capability | SD1.5 | SDXL |
|---|---|---|
| SparseCtrl (conditions on scattered frames, incl. `[0, N-1]`, the exact primitive) | yes | **none** |
| FreeNoise (the only way past the 32-frame cap) | yes | **none** |
| AnimateDiff-Lightning (distilled, 1/2/4/8 step) | yes | **none** |
| MotionLoRA (zoom, pan, tilt, roll) | yes | **none** |
| video2video, ControlNet | yes | **none** |
| Motion adapter | v2/v3, 453 M params, 4 blocks + mid block | **beta only, 237 M, 3 blocks, no mid block** |

The single SDXL adapter is labelled beta, was never followed by a v2, and has roughly half the
temporal capacity. `AnimateDiffSDXLPipeline.__call__` has **no `image` and no `strength`
parameter**; it is text-to-video only. Handing it an SD1.5 adapter fails cleanly and early on a
block-count guard, so at least you cannot do the wrong thing silently.

**Two mechanical facts worth keeping even if we never use AnimateDiff:**

- The motion module is **two stacked temporal self-attentions with
  `cross_attention_dim=None`**, and the call site passes no `encoder_hidden_states`. It never
  sees the prompt. It reshapes to `(B*H*W, F, C)`, so there is zero spatial mixing: pixel
  `(3,7)` at frame 5 only ever sees pixel `(3,7)` at other frames. *The motion module does not
  know what it is animating.*
- A motion adapter **does** compose with our fused style LoRAs (disjoint parameter sets), but
  `fuse_lora()` alone is not enough. PEFT leaves the wrapper in the tree, so the graft's strict
  `load_state_dict` raises. You must `unload_lora()` first. Verified by running all four
  orderings, not inferred.

**The architectural objection that matters more than any of the above.** Our design is 26 to 60
keyframes, so painting the in-betweens means 25 to 59 *independent* diffusion samples. The
endpoints match by construction because they are clamped, but the interior trajectories are
independently sampled, so segment k and segment k+1 take different micro-paths through the same
endpoint. That produces a velocity and texture discontinuity **at every keyframe**, which is
exactly the artefact class `skip_keyframes` and `skip_boundary: 4` were introduced to kill. RIFE
has no such problem: it is deterministic and C0-continuous through every endpoint. Loop closure
gets worse still, since the wrap segment becomes one more independent sample and the seam we
care about most becomes the most visible one.

Cost seals it: roughly **50x to 100x** wall clock (a 60 s clip goes from ~2 min and $0.07 to
~1.6 to 2 h and $3 to $4), because no SDXL Lightning-equivalent motion adapter exists so we
cannot get to 4 steps. And AnimateDiff cannot stream: temporal attention needs all F frames
resident, whereas Phase C currently streams to the encoder at constant ~50 MB, which was itself
a deliberate fix for a 37 GB OOM.

**What survives.** Two things.

1. **`callback_on_step_end` can return replacement latents** (`latents = callback_outputs.pop("latents", latents)`).
   So endpoint-anchored inbetweening is testable in 40 to 60 lines without forking the library,
   by overwriting `latents[:, :, 0]` and `latents[:, :, -1]` with re-noised keyframes each step.
   Unsupported but using a real public API as intended. It is the cheapest possible test of the
   whole thesis, and the risk is quality, not plumbing.
2. **A denser keyframe walk with fewer RIFE passes**, which is a config change and needs no new
   model at all. See T14.

**Environment footnote:** the legacy pipeline runs on diffusers 0.31.0 in `.venv-sd`; the main
env has 0.38.0. Any AnimateDiff work happens in 0.38.0. Do **not** upgrade `.venv-sd`, the LoRA
fuse path changed a lot across those releases and production renders depend on it.

#### Checkpoint-level corroboration (second pass, from the HF API and the papers)

Confirms the above from the published configs rather than from the installed code, and adds
four facts worth not re-deriving.

- **The architecture gap is in the config, not in the training budget.** SDXL beta:
  `block_out_channels [320, 640, 1280]`, `use_motion_mid_block: false`, 950 MB. SD1.5 v1-5-2:
  `[320, 640, 1280, 1280]`, `use_motion_mid_block: true`, 1.82 GB. One fewer resolution level
  and no motion mid-block at all. You cannot tune around that.
- **It is abandoned, not merely beta.** Released 2023-11-10 with a README promising "more
  checkpoints with better-quality would be available soon". Three years on, the `guoyww`
  namespace has 18 repos and none of them is an SDXL follow-up. Three GitHub issues asking for
  one are open and unanswered.
- **Hotshot-XL is the other SDXL option, and it does not help us.** `hotshotco/Hotshot-XL`,
  a genuine SDXL temporal model. But **8 frames at 8 fps**, i.e. one second, recommended
  against an SDXL base fine-tuned at 512x512, last touched 2023-10-11, and `HotshotXLPipeline`
  lives in its own repo rather than diffusers core. Not usable for painting in-betweens between
  1344x768 keyframes. Recorded so nobody rediscovers it hopefully. Notably, the circulating
  community pairing for few-step SDXL video is **SDXL-Lightning + Hotshot-XL**, and there is no
  documented case of anyone running SDXL-Lightning against the AnimateDiff SDXL beta.
- **AnimateDiff-Lightning on SDXL is impossible, on the record.** diffusers issue #9115, a
  maintainer reply: "AnimateDiff Lightning is compatible only with SD1.5 based models and can't
  really work with SDXL due to differing model architectures." The failure is the same
  block-count guard.

Two terminology traps that would waste a search:

- In the SparseCtrl paper, start-plus-end conditioning is called **"Transition"**.
  **"Interpolation"** means something else there (uniform keyframe upsampling). Searching the
  paper for "interpolation" misses the result we care about. Also useful: `{first, last}` is
  genuinely **in-distribution**, because training draws `Nc` condition indices uniformly without
  replacement, so it is an ordinary training sample rather than an exploit.
- **`guoyww/animatediff-motion-lora-v1-5-3` is NOT a camera-motion LoRA** despite a README that
  opens with copy-pasted camera-motion boilerplate. It is the v3 domain adapter.

Two additions from a third pass, both concrete:

- **There is an open, unresolved scheduler bug that may itself explain the quality complaints.**
  [AnimateDiff issue #376](https://github.com/guoyww/AnimateDiff/issues/376): AnimateDiff's SDXL
  noise scheduler uses `beta_end` 0.020 against Stability's original SDXL value of 0.012. Open
  since 2024-08-17, no maintainer reply. So "the SDXL adapter looks bad" is partly confounded
  with "the SDXL adapter ships a wrong beta schedule". Worth knowing before concluding anything
  from T16, and worth overriding if T16 runs.
- **The maintainer of the main WebUI frontend advises against it outright.** continue-revolution,
  `sd-webui-animatediff` docs: *"I strongly discourage anyone from applying SDXL for video
  generation. You will be VERY disappointed if you do that."* Kosinkadink's ComfyUI extension
  README says the SDXL support is "still in beta after several months". The `sdxl` branch's last
  commit is 2023-11-13 and the repo has **zero GitHub releases**.

One correction to carry: "trained at 1024x1024, 16 frames" is widely repeated but is **not a
published training spec**. The README states an output capability, and the "trained upon larger
resolution and batch size" line that gets quoted for SDXL is actually about SD1.5 v2. The frame
count of 16 is well supported; the resolution is an inference from the inference defaults.

One operational note that would apply to T15 if we ever get there: the SparseCtrl README warns
that for interpolation-style use, **both endpoint images must come from the same base model plus
LoRA**, or the transition drifts in style. In our case they would, since both are our own
keyframes. And `controlnet_frame_indices` is not validated in `check_inputs`, so an out-of-range
index wraps silently or throws a raw indexing error. Clamp it yourself.

### L13. CLIP token budget rule

77 total minus BOS and EOS leaves 75 usable; target 62 for BPE slack. Trigger prefix <= 6,
drift driver 8 to 12 **and first in the string**, subject and composition 25 to 32, style
suffix <= 14 and sacrificial. Check **both** SDXL tokenizers and take the max. The billboard
configs already overran once at 80 tokens, silently truncating the drift term.

**Promotion: pending.** Task T7.

---

## Open directions

Each is a fork, not a task. The task board below serves them.

### D1. Subject grammar

- **(a) Aperture.** Something you look through. The aqueduct satisfies this by accident, which
  is why it works better than a rushed choice should. Keeps the "same motif at two scales"
  property that solves the 1:3 / 16:5 / 1:1 geometry.
- **(b) Field.** No object at all, just weather and light. The vertical and horizontal stop
  being two compositions and become two crops of one atmosphere, so the geometry problem
  vanishes by construction. Only viable if the style carries everything.
- **(c) Mass.** Soutine. Vertical is a body, horizontal is a hillside. Two different things
  held together by surface rather than structure.

Unsettled. Agent recommendation on record: (b), on the argument that a Times Square LED at
22:30 rewards being the dark slow thing rather than competing on brightness.

### D2. Style, and whether to train

**Downstream of D1.** If (a), Cole is already correct and a new LoRA is a luxury. If (b), Cole
is wrong (landscape-with-objects, and a field has no objects) and the LoRA becomes the
load-bearing decision.

Candidates ranked for the field case: **Turner late** (subject of the paintings is light
destroying form, huge PD corpus, style and drift are the same gesture), **Aivazovsky** (more
literal luminous aperture, ~6000 works, weak vertical), **Friedrich** (best geometry fit
anywhere, but 60 to 80 paintings is at or under the style-LoRA floor and his signature move
involves a figure, which drifts badly in a chain). **Piranesi** raised and argued against:
pure high-frequency line, and the pipeline has three separate mechanisms that destroy
high-frequency content.

Modal cost of training is negligible ($0.30 to $1.61). The cost is `dataset-mosaic` curation
hours.

### D3. Quality backbone

The ladder in L1's finding. Also open: FLUX with a LoRA. Note FLUX **base** was already tested
and rejected on exactly the painterly-surface axis (2026-05-18, Luca's verdict: SDXL base gave
the most interesting brush strokes, the others essentially none), so re-running base
reproduces a known result. A meaningful FLUX test needs a LoRA on it; the cheap version pulls a
third-party painterly FLUX LoRA off HuggingFace rather than committing to a ~1 week retrain.

### D4. Phase C: keep RIFE, or generative in-between

RIFE warps pixels along an optical flow field with no knowledge of the prompt or the LoRA. It
is the documented source of high-frequency loss
([narrative-arc-drift.md](../../../findings/narrative-arc-drift.md) Finding 3) and of
rubber-sheet morphing when one flow field fills 1.4 s. A keyframe-conditioned generative
in-between (SparseCtrl is the obvious candidate) would *paint* the in-betweens instead.

Preserves the A/B/C/A authoring, the LoRA, the loop closure and the drift. Changes only the
layer that is currently a dumb warp. Bounded, because Phase C is already a clean seam.

**Largely closed by L15, 2026-08-07.** AnimateDiff cannot deliver it on SDXL: every mechanism
that would (SparseCtrl, FreeNoise, MotionLoRA, Lightning distillation) is SD1.5 only, and the
models that *can* paint anchored in-betweens (Wan FLF2V, LTX2) cannot carry an SDXL LoRA, so
they would render in their own aesthetic rather than ours. The requirement has two halves,
*knows the prompt and the LoRA* and *paints coherent in-betweens*, which are individually
available and jointly unavailable today.

Independently of the library, the per-keyframe discontinuity argument in L15 says a
sample-per-gap interpolator would reintroduce artefacts this pipeline already solved.

**What is left of D4**, in priority order:

1. **T14, denser keyframes with fewer RIFE passes.** No new model, config only. The right first
   move and it is not really about AnimateDiff at all.
2. **T15, the `callback_on_step_end` anchored-latent spike.** 40 to 60 lines, tests the thesis
   cheaply, quality is the risk rather than plumbing.
3. Wan FLF2V and LTX2 stay on the shelf as *aesthetic* options, not as ways to interpolate our
   own work.

### D5. Movement authoring

Three kinds of motion; only the first is in use, and only at its default.

- **What changes** (diffusion side). `steady_strengths` is already a per-frame list and has
  only ever been used as texture jitter. Written as a ramp it becomes an acceleration curve.
  Needs a check on how it is indexed before promising a curve shape.
- **When it changes** (timing side). Clip-level easing via `setpts` in `conform.py`. Also:
  segment frame counts are uniform, so the piece cannot linger anywhere.
- **Where the camera looks** (frame side). The pipeline has no camera. Options are a slow
  crop-window drift in `conform.py` (free, smooth, arguably a Ken Burns gesture beneath the
  technique) or AnimateDiff MotionLoRA (latent-space camera motion, needs D4's stack).

### D6. Live path

StreamDiffusion, `next-exploration-steps.md` sections 2 to 4. Parked. L10 says the
`StreamDiffusionTD` fork is the reference if it is ever unparked.

### D7. Billboard delivery

Ship the banked files, or re-render off whatever this workstream concludes. Landlord approval
is due 2026-08-28; One Love's own Drive cutoff was 2026-08-08. **No outbound send without
Luca's explicit per-message clearance.** Campaign name is still a placeholder
("COURSE OF EMPIRE").

---

## Task board

Cost is Modal dollars unless marked. "Unblocks" names what the result decides.

### Ready to run now

| # | Task | Cost | Unblocks |
|---|---|---|---|
| **T1** | **Step ladder, 6 rungs** (L1 Finding 2, plus rung c2 per L14). Blocked only on choosing the subject to run it on. | ~$0.43, ~4 min | D3, and the quality question generally |
| ~~T2~~ | ~~Fix the `modal token current` doc bug~~ | **DONE 2026-08-07.** Three occurrences fixed in `modal-operations.md` plus quirk #12 in `modal-sdk-quirks.md` | |
| ~~T3~~ | ~~Extend `tools/gallery.py`~~ | **DONE 2026-08-07.** Indexes PNG directories as one strip card each (48 found), resolves identity through `keyframes/` to the parent, reads PNG dimensions from the IHDR with no new dependency, and `variant_rows()` now surfaces sampling budget, backbone, VAE kind, RIFE scheme and segment frame counts | |
| ~~T4~~ | ~~Point `cloud/app.py` at `examples/configs`~~ | **DONE 2026-08-07.** The comment already said "examples/configs is small"; the code mounted all 109 MB of `examples/` | |

### Needs a decision first

| # | Task | Blocked on | Cost |
|---|---|---|---|
| T5 | FLUX + third-party painterly LoRA probe | Confirming it is worth it given the base rejection | ~$0.20 |
| T6 | Subject and style sweep as a stills contact sheet (the original Strip A/B) | D1, and arguably should wait for T1 | ~$0.03 + T3 |
| T10 | Train a new style LoRA | D1 then D2 | $0.30 to $1.61 + curation hours |
| T11 | Movement strip, 5 video variants | D5, and should inherit T1's winner | ~$0.25 |
| ~~T12~~ | ~~Scope D4~~ | **DONE 2026-08-07**, see L15. D4 is largely closed | |
| **T14** | **Denser keyframe walk, fewer RIFE passes.** More painted content per second of output while keeping the deterministic interpolator. Config only, no new model. A prior "2x density + 8x RIFE" test was rejected. Read the actual verdict before assuming it settles this: [pipeline.md:299](../../../pipeline.md) records it as "Video too fast, same flashing", i.e. it was judged on **pacing** and on **failing to fix a rhythmic-pulse bug**, never on texture. That whole rejected-approaches table also predates Phase A.5, the frequency-separated smoother that actually fixed the pulse. So the texture question is genuinely open, and pacing decouples via fps and steady-frame counts. Belongs in the same batch as T1 | Nothing | ~$0.10 |
| T15 | `callback_on_step_end` anchored-latent spike: overwrite `latents[:, :, 0]` and `[:, :, -1]` with re-noised keyframes each step, on the SDXL beta motion adapter. Do T16 first | T16 | ~$0.20 |
| T16 | Half-day spike: does the SDXL beta motion adapter survive a rank-32 style LoRA at all? 16 frames, text2video, ~30 lines. If it flattens the fresco or Renoir texture, T15 and everything downstream is moot | Nothing | ~$0.10 |

### Documentation debt

| # | Task | Source |
|---|---|---|
| T7 | `docs/manual/render-tuning.md`, the umbrella page `lever`'s own agent definition says does not exist. Absorbs L4, L5, L13, plus the "compare keyframe 0000 against 0006" diagnostic | lever, twice |
| T8 | Decisions-log entries for Cole `lora_scale` and for the Soutine epoch verdict, neither of which was ever recorded | L4, L5 |
| T9 | `docs/findings/borrowing-from-streamdiffusion.md` from L10 | anatomy pass |
| T13 | Fold L6 to L9 into `render-tuning.md` or into `narrative-arc-drift.md` as a small-K companion | lever |

---

## Shipped this session

- `SamplingConfig` (`num_inference_steps`, `guidance_scale`) threaded from YAML to
  `generate_keyframes`. `ModelsConfig.lightning_lora: null` to skip the Lightning fuse and the
  trailing-timestep scheduler swap together. `ModelsConfig.vae_kind` plus a separate
  `vae_full` field. Backwards compatible, 60 tests pass.
- [findings/denoise-step-budget.md](../../../findings/denoise-step-budget.md).
- Modal smoke re-verified after a three-month gap.

## PARKED: directional motion, attempt 1 failed. Read this before retrying.

Shipped `motion.py` + `MotionConfig` (commit `0264d3118`). The mechanism is wired and
the mask is exact, but **the first waterfall test is a regression and must not be built
on as-is.**

### What was measured, not guessed

Cross-correlating the water column between consecutive frames:

| render | frame-to-frame shift | frames still |
|---|---|---|
| `led4_a_fall` (dy=154) | **+0.09 px** mean, median 0.00 | **92%** |
| `led4_a_fall_static` (dy=0) | 0.00 px | 100% |

Intended speed was 5.0 px/frame. **The water never translated.** An earlier claim that
motion was working came from a pixel-delta ratio (water changed 1.65x the rock against
1.09x static); that measured CHURN and was the wrong instrument. Cross-correlate before
claiming translation.

### Why it failed, and it is a design error rather than a tuning one

**The region was translated, not the texture.** The mask covers the whole channel
including the top of the fall, so displacing it downward carries the fall's own top edge
down and the waterfall SHORTENS FROM ABOVE instead of water descending through it. Luca
identified this from the render before the measurement did. The vacated strip is then
edge-filled and repainted, which is where the artefacts come from. Both reported
symptoms follow from the one mistake.

### The retry design

1. **Frequency-separate the moving region.** Advect ONLY the high-frequency band. The
   silhouette is low-frequency, so pinning it makes the fall's height structurally
   incapable of changing. Phase A.5 is already a frequency-separated smoother and
   `noise/frequency_banded.py` exists; this is existing practice, not a new idea.
2. **Make the advection cyclic within the mask**, so texture leaving the bottom re-enters
   at the top. Physically right for a steady fall, removes the vacated strip and its
   artefacts entirely, and closes the loop by construction, which was the open risk.
3. **Then sweep strength.** 92% of frames unchanged says the repaint erases what it is
   given. Motion wants LOW strength (preserve a displaced input, ~0.15 to 0.25), which is
   the opposite of every tuning decision made so far, because all of those were asking
   the model to BUILD an image rather than preserve one.
4. Consider displacing the noise walk's persistent tensor with the texture, or disabling
   the walk inside the mask. It re-imposes a static spatial pattern every frame and is a
   second anchoring mechanism working against the motion.

### Worth keeping regardless of how this resolves

- **`skip_boundary` must be 0 for translation work.** It drops the invented frames
  nearest each keyframe, which is correct for content drift but inserts a positional jump
  of about `2*skip/2^passes` of the step into a rigid translation. Motion and light-drift
  configs therefore cannot share a preset.
- **Static regions cost nothing.** Flow is zero over them, so RIFE copies them: no
  mid-pair sharpness pulse on the rock. Softness lands only on the moving region, which
  is the one place it is correct.
- The gorge depth map and the 1:3 framing both read well. Only the motion is unresolved.

## Session 2026-08-09: delivery-aspect authoring, and two code faults it exposed

Paused mid-session at Luca's request. **Read L16 before trusting L-anything about
v10, and read L17 before authoring any anchored render.**

### L16. v10 was a no-op, so the headline of `chained-diffusion-limits.md` is unsupported

`_pipe_call` in [keyframes.py](../../../../src/slow_interpolation/keyframes.py) built
`ctrl_kw`, put `cross_attention_kwargs` in it to carry `lora_scale_per_segment`, then the
ControlNet branch **reassigned** the dict instead of updating it. That is the only path
carrying per-segment scale to the model: the `keep_live` route calls `set_adapters` once
with a single scale for the whole render.

`empire_v10_dualsource.yaml` sets `lora_scale_per_segment: [0.90, 0.90, 0.40, 0.45, 0.85]`
**and** `control.images`, with base `lora_scale: 0.90`. Every frame ran at 0.90. Nothing
was halved.

So "halving `lora_scale` on the city stages changed instability by 0% (1.234 to 1.235),
therefore the constraint is content complexity and not the LoRA" is not evidence about the
LoRA. A 0% change is the signature of a no-op. That experiment is the **sole** support for
the headline of [findings/chained-diffusion-limits.md](../../../findings/chained-diffusion-limits.md),
which currently reads as settled.

**Status is untested, not refuted.** The v9 result (fewer, larger, hazier masses scored
best) is independent of this and still stands. Fixed in `079598d4c`; the experiment needs
re-running before the finding can be relied on. Nobody has edited the finding doc: rewriting
a shipped conclusion is Luca's call.

### L17. `warmup` > 1 largely defeats `anchor_image`

The warmup loop runs pass 0 at `anchor_strength` and **every later pass at a hardcoded
0.75**, which repaints the composition the anchor existed to preserve. With an anchor,
`warmup: 1`. Not a bug exactly, but it is undocumented and silently wastes the mechanism.

### L18. There was no seed anywhere, so no render before today is reproducible

The warmup canvas came from an unseeded `np.random.randint` and no `generator` reached the
pipeline. Re-running a config gave a different picture, and a composition worth keeping
could only be recovered by feeding a frame of its own render back in as `anchor_image`.
`PipelineConfig.seed` now exists, defaults to `None` (old behaviour byte-for-byte), and
threads both the canvas and a `torch.Generator`. 60 tests pass.

This is why the v1 billboard compositions had to be anchored rather than re-rolled.

### L19. A depth map that is mostly black is not a constraint

The 1:3 and 16:5 maps authored this session were ~75% black, on an over-application of the
v4 water rule (which was "no depth ramp in the water", not "black out most of the frame").
At `scale: 0.65` ControlNet never set the horizon and did not hold the crag on the side the
map specified; those compositions were prompt-driven. The empire maps worked because they
blacked out only sky and bay and carried a bright near shore across the lower third.

Corollary: an inert map is survivable, but a map that **disagrees** with an `anchor_image`
is worse than none. Both were dropped from the second pass.

### L20. Delivery-aspect geometry, measured

With `edge_crop: 8`, verified end to end through `conform.py`:

| Screen | Render | Crop | Delivered region of the render | Upscale |
|---|---|---|---|---|
| A 912x2736 | 896x1536 | 506x1520 at x=187 | central 506 px column, full height | 1.802x |
| B/C 1728x540 | 1536x896 | 1520x474 | a 474 px band, 53% of the frame | 1.137x |

**The handover's `--crop-y 0` is wrong for a bay subject.** It was written for the arcade,
whose crowns sat at the top. A storm seascape puts its horizon low, so the band that works
is the BOTTOM one, `--crop-y 406`. Pick the offset from a still every time; this is the
second time that advice has paid.

### L21. Two prompts 10 s apart is a transformation, not a drift

v1 gave each prompt 4 steady frames and a semantically wider gap than it looked
("pale silver moonlight" reads as daylight, not as a moonlit variant). Frames 0 and 299
matched, so loop closure was excellent, but frame 150 was a different scene: C lost the
moon and warmed to daylight, B lost its waterline and grew trees.

The fix has three parts, none sufficient alone: the subject clause byte-identical between
prompts so only the light adjective moves, `steady 5 / transition 1` so the chain settles
into a prompt instead of being permanently in transit, and the drift budget down from
15 x 0.36 = 5.4 to 15 x 0.30 = 4.5 (banked files are 7 x 0.55 = 3.85).

### State at pause

- **v1 batch:** 3/3, $0.16, all spec-verified. Conformed at the corrected crops into
  `outputs/nyc-billboard/led/candidate/`. B and C are good images, A is flat and
  off-concept. Drift is wrong on all three, per L21.
- **v2 batch:** landed, 3/3, $0.1404. `led_a_storm`, `led_b_savage_v2`,
  `led_c_desolation_v2` on the outputs volume. A drops the Consummation framing for
  weather; B and C keep their v1 compositions via `anchor_image` at `warmup: 1`.
  **NOT synced, NOT conformed, NOT looked at.** Nobody has seen these three yet.
- **Open and unverified: did the seed actually take?** The `[keyframes] seeded, seed=1087`
  line does not appear in the batch log. That is NOT evidence of failure: `[keyframes]`
  lines do not appear in the v1 log either, including ones that certainly ran, so
  `cloud/batch.py` is not forwarding container stdout for them. Inconclusive either way.
  Cheapest check is to re-run one config unchanged and diff frame 0 against this run's.
- **The three banked delivery files are untouched.** Nothing sent. No deadline risk.
- Campaign name still the holding "SLOW INTERPOLATION". Landlord approval due 2026-08-28.

### Next, in order

1. `python tools/sync_outputs.py`, then conform and judge the v2 batch: does the drift now
   read as light-only over 10 s. B and C at `--screen bc --crop-y 406`; A's crop has to be
   picked by eye from a still, since it has no anchor and no map.
2. Confirm the seed took, per the open item above. Everything downstream assumes it.
3. Re-run the v10 experiment against the fixed code, then decide what
   `chained-diffusion-limits.md` should say.

## Session 2026-08-08: the Course of Empire arc, v1 to v10

Ten renders, ~$6.10. Distilled into
[findings/chained-diffusion-limits.md](../../../findings/chained-diffusion-limits.md);
this is the scoreboard and the state at handoff.

| Render | subject | loop | motion | image | total | what it changed |
|---|---|---|---|---|---|---|
| harbor_75s | 4 | 3 | 4 | 8 | 19 | first 5-stage arc, 75 s |
| **harbor_v2** | 1 | 10 | 7 | **9** | **29** | transition 3->6, control 0.70 |
| v3a_dense | - | - | - | - | 28 | passes 6->5, 23 frames/pair |
| v3b_nodecay | - | - | - | - | 16 | decay off: measured sharp, looked digital |
| v4_breathing | 2 | 7 | 6 | 7 | 22 | per-segment pacing + per-stage maps |
| v5_armature | 3 | 9 | 4 | 7 | 23 | fixed land-strip armature |
| v6_sharp | 5 | 9 | 6 | 6 | 26 | decay 2->1, strengths back over the int boundary |
| v7_flat | 6 | 10 | 7 | 6 | 29 | skip_boundary 8: flattest pulse, worst stepping |
| **v8_steps** | **8** | 10 | 6 | 6 | **30** | steps 12->20. Best SUBJECT score |
| **v9_haze** | 4 | 10 | 6 | **9** | 29 | simplified city. Best IMAGE score |
| v10_dualsource | 6 | 3 | 5 | 5 | 19 | per-stage lora_scale. **Decisive negative** |

**Current best depends on the axis.** `v8_steps` for subject legibility,
`v9_haze` for painterly quality. Nothing has beaten both at once.

**v10 is the most valuable render of the ten** despite scoring lowest: halving the
LoRA on the city stages changed instability by 0%, which rules the LoRA out and
points at content complexity. It also broke the loop, because the anchor frame is
made during warmup at the base scale while the return segment ran at 0.85. Per-stage
scaling needs the return pinned to the anchor's scale; not yet fixed.

**Still unresolved:** stage III blurs in every version. See the findings doc.

## Open questions for Luca

1. **Which subject does the step ladder (T1) run on?** Aqueduct gives comparability to the
   banked files. Anything else costs nothing extra but is not a control.
2. **D1**, which decides D2, which decides whether T10 happens at all.
3. **T2**, the doc fix. Trivial, twice deferred.
