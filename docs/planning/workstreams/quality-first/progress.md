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

### Attempts 2 and 3 also failed, and together they identify the real obstacle

**Attempt 2** (`led5_a_fall`, `led5_a_fall_soft`): advect only the high-frequency band,
cyclically. The envelope fix WORKS and is verified on a synthetic fall: ten keyframes of
advection moved the top edge from y=153 to y=1431 under attempt 1 and from y=153 to
y=151 under attempt 2. But nothing moved: 99% of frames identical. A strength sweep down
to 0.26 (5 real steps) made it *more* static, not less.

**Why**: measured band survival between consecutive KEYFRAMES.

| band | r between keyframes |
|---|---|
| finer than ~4 px | **0.05** |
| finer than ~8 px | **0.15** |
| ~8 to 24 px | 0.82 |
| ~24 to 80 px | 0.99 |
| ~80 to 240 px | 0.99 |

**Everything finer than ~8 px is re-invented at every keyframe.** `hp_sigma: 6` advected
exactly that band, i.e. the only part of the image the chain discards.

**Attempt 3** (`led6_a_fall`): band-pass 10 to 80 px, chosen from the table above so the
moving band both survives the round trip and excludes the silhouette. Keyframe-to-keyframe
shift of the advected band: **+1 px against an intended +154**.

### The obstacle, stated properly

The model does not CARRY texture it is handed; it RE-DERIVES it. The low band (coarser
than 80 px) is held static by design, and the mid band is largely a deterministic function
of that low band plus the prompt plus the fixed control map, so the model reconstructs
streaks in the place the underlying structure implies rather than where the displaced
input put them. Lower strength does not help because the issue is not how much it
repaints, it is that what it repaints is determined by something we are deliberately
holding still.

That is a real obstacle rather than a dial, and it should be treated as such before a
fourth attempt. Untested routes, in the order they look most promising:

1. **Animate the control map instead of the pixels.** Give the water region a moving
   structure in the depth map itself, per keyframe, so the thing that DETERMINES the
   texture moves rather than the texture. Needs per-keyframe maps, since `control.images`
   currently cross-fades one map per PROMPT and a cross-fade is a dissolve, not a
   translation.
2. **Drop ControlNet inside the mask only**, so the water has nothing asserting where it
   should be, while the rock stays pinned.
3. **Advect the low band too, with the envelope enforced by the control map** rather than
   by frequency. Attempt 1 failed at this because it edge-filled; cyclic wrap plus a lip
   asserted in the map is a different experiment.
4. Very low strength, 0.10 to 0.15, so the chain barely repaints at all. Cheap to try and
   worth one run, but expect soft output.

Spend on this thread so far: about $0.22 across five renders.

### Attempts 4 and 5: animate the conditioning. Also failed, completing the picture

Per-keyframe control maps now exist (`control.keyframe_images`, cycled by keyframe
index; `images` cross-fades per prompt, and a cross-fade is a dissolve, not a
translation). Streak texture authored at phase i/K descends through the maps and wraps,
so the loop closes in the conditioning by construction.

- **Attempt 4** (led7): streaks at value 34 to 54. Invisible to ControlNet: 3/10
  keyframes best-matched their own phase map, r ~ 0.1, chance level.
- **Attempt 5** (led8): streaks at 108 to 148, K=20 so RIFE tracks a ~77 px step,
  pixel advection removed entirely. Phase-following 2/20, own-phase r = +0.05.

**Conclusion across all five mechanisms**: the img2img feedback loop inherits its own
previous texture more strongly than any external signal injectable at settings
compatible with this aesthetic. Displaced pixels are discarded (attempts 1 to 3), and
conditioning phase is out-shouted by the input image (4 and 5). Directional in-frame
water motion is beyond this pipeline's current mechanism set.

**The one untried route is fundamentally different**: composite the falling-water layer
OUTSIDE diffusion. Paint the gorge with the pipeline (it is now very good at that), then
render the fall as a procedural cyclic layer blended in at the channel, Phase B style.
Guaranteed motion, guaranteed loop, and the open question moves to whether a composited
layer can read as paint. `cloud/compositing_sketch.py` exists as a starting point.

### The corner smear: root-caused through four map versions, and it does not ship

The band is **in the raw keyframes**, Phase A, not RIFE. It appears wherever the map
asks the border to be something featureless or semantically false, and it survived four
border treatments: smooth ramps (v1), a flat grey ring (v2), a black ring cutting
through rock (v3, nonsense geometry paints as mud), and shaped rock columns to the edge
(v4, a tall UNIFORM column paints as repetitive fill that collapses into smear).
Comparison across portrait renders shows the variable is edge CONTENT: led3's sky and
shore edges are clean, terrace's varied rock is mildly affected, the fall's uniform
1500 px columns are heavily affected.

**Practically: screen A's conform crop keeps only the central 506 px, and the smear
lives in the outer ~80. The delivered file's corners are clean**, verified on
`candidate4/`. The raw renders in the gallery DO show it, so judge A candidates from
the conformed file, not the raw card. For B/C the full width ships, but their maps put
sky and shore at the edges, which is the clean case.

### led9 is the best waterfall composition of the run

Stepped-ledge cliffs paint as real Cole rock, multi-tier fall, foliage, basin.
Conformed and spec-verified at `candidate4/VANDALO RUINS_SLOW INTERPOLATION_
NY1087A_090226.mp4`. The water churns painterly rather than descending; whether that
is acceptable for the billboard, or the compositing route gets built, is Luca's call.

### Worth keeping regardless of how this resolves

- **`skip_boundary` must be 0 for translation work.** It drops the invented frames
  nearest each keyframe, which is correct for content drift but inserts a positional jump
  of about `2*skip/2^passes` of the step into a rigid translation. Motion and light-drift
  configs therefore cannot share a preset.
- **Static regions cost nothing.** Flow is zero over them, so RIFE copies them: no
  mid-pair sharpness pulse on the rock. Softness lands only on the moving region, which
  is the one place it is correct.
- The gorge depth map and the 1:3 framing both read well. Only the motion is unresolved.

## Session 2026-08-10: the light arc measured, and the seed question closed

Screens B and C. All figures below are taken on the **delivered crop**
(rows 288 to 762 of the 880-row render), never the full frame, because the sky
above row 288 never reaches the wall.

### L22. Light CAN be the subject, and the cost is now a number rather than an argument

led12 = led3 with `steady` 1 to 2, strengths 0.44/0.46 to 0.58/0.60, transition
0.45 to 0.62, return given the forward path's authority, `return_pixel_blend_max`
0.35 to 0.45. Map, prompts, negative, seed and RIFE scheme byte-identical, so the
result attributes to the schedule.

| | B storm to sun | C night to moon |
|---|---|---|
| luminance swing, led3 to led12 | 5.72 to **8.77** | 7.39 to **10.09** |
| contrast ratio | 1.08x to **1.14x** | 1.15x to **1.25x** |
| structural r, trough to peak | 0.965 to **0.911** | 0.894 to **0.672** |
| loop delta | 0.12 to 0.72 | 0.10 to 0.54 |

**led3's arc was spatially FLAT** (per-band swings 6.7 / 5.2 / 5.4 on B), which is
an exposure change, not a light event. led12's is 12.1 / 6.8 / 7.7: the break in
the cloud now brightens more than the water beneath it. That qualitative shift is
invisible in the global number.

**Both poles darkened.** B's min fell 70.6 to 63.1 and its **max also fell**, 76.3
to 71.9. A prediction that the growth would be upward was refuted. More authority
per keyframe let the model finally assert "black storm light"; the sun pole still
does not arrive.

**The diagnostic that names the cheap fix: the peak lands at 62% of the loop,
which is the first RETURN keyframe.** The light is still climbing when the chain
is told to turn around, so the arc is step-limited at the B pole, not
strength-limited. Strength is the expensive lever and is what bought the
stability loss.

**led13, dispatched:** four renders isolating the two dials. `steady_per_segment
[1, 3]` reallocates the budget to the B pole at identical K=8, identical 439 raw
frames and identical 0.8 Hz throb, crossed with strengths held (0.58/0.60) versus
lowered (0.52/0.54). led12 moved keyframe count and strength together, which the
coupled-dial rule forbids; this separates them. C's pair also adds `people,
figures, a standing figure` to the negative, constant across both so the strength
comparison is unaffected.

**Defect found in led12_c:** an unprompted standing figure on the foreground ledge
at the peak. C's negative banned warm light and foliage but never people. Same
defect class as the objects in screen A's pool.

### L23. The seed took, but renders are NOT bit-reproducible, so a hash is the wrong instrument

L21's open question is answered. led12's warmup anchor against led3's, same
warmup, same map, same seed 1087:

| | B | C |
|---|---|---|
| pearson r | **0.979** | **0.948** |
| mean abs diff | 5.58 / 255 | 5.95 / 255 |
| pixels byte-identical | 0.2% | 0.2% |

r ~0.98 rules out an unseeded canvas, which would give a different painting. But
0.2% identical rules out determinism. Consistent with GPU kernel
nondeterminism amplified through the ~47 sequential denoising steps of warmup.
The L16 `cross_attention_kwargs` fix is inert for these configs, since
`lora_scale` stays `None` unless `lora_scale_per_segment` is set, so it is not the
cause.

**Consequence:** verify reproducibility by correlation, never by checksum. The
definitive run-to-run check (re-run one config unchanged, ~$0.04) is still not run.

### L24. How to measure a light arc

- For a light-drift clip the **global luminance IS the subject**, so a frame
  average is the right instrument here. This is the exception to
  `chained-diffusion-limits.md`'s "frame-average metrics lie", which is about
  sharpness.
- Measure it on the **delivered crop**, per band. "Gold on the water" is a claim
  about a region, and a general lift versus a directional light read identically
  in the global number.
- Structural stability is best read as pearson r on a low-passed (sigma 12) frame
  pair, trough against peak: it reports composition rather than texture.
- Script currently in the session scratchpad. Promote to `tools/` if a third
  session needs it; two uses is not yet a tool.

### L25. There is NO prompt-side suppression lever at `guidance_scale: 1.5`

led12_c painted an unprompted standing figure. led13_c added `people, figures, a standing
figure` to the negative and the figure SURVIVED, merely changing posture. So led14 ran a
discriminating pair, because two different causes predict the same surviving figure.

| render | change from `led13_c_realloc_soft` | figure | mean L | HF energy |
|---|---|---|---|---|
| control | -- | present | 53.9 | 100% |
| `led14_c_cfg3` | `guidance_scale` 1.5 to 3.0 | **GONE** | 42.8 | **155%** |
| `led14_c_pospeople` | `no people` in the POSITIVE prompt | present | 53.7 | 103% |

**Negatives are weight-starved, not ignored.** Give the negative branch weight and it bites
immediately, with nothing else changed. But you cannot do it selectively: raising guidance
activates the WHOLE negative list at once, and C's bans golden hour, warm light, daylight
and fire, which is where the 25% darkening comes from. It also came out **harder and
crisper, not flatter** (155% of control's contrast-normalised FFT high-frequency energy),
which is the documented trap where a sharpness gain reads worse.

**The positive route is a null result and it refutes a standing precedent.** `led11_a_fall`
puts "no people" in the POSITIVE prompt and that has never been verified. Here it did
nothing measurable: identical to control on every axis, and the figure got more prominent.

So at 1.5 there is no prompt-side lever in either direction, and the repo's elaborate
negatives (picture frame, watermark, sepia, brown monochrome) are largely decoration. The
remaining lever is structural: a control map that gives the element no room. That is
priorities row PL12 and it is the next render.

### PENDING DECISION for Luca, one word, nothing is blocked on it

**`docs/tutorial-first-runs.md` teaches negatives as an active control, at exactly the
guidance where L25 measured them inert.** Its own config sets `guidance_scale: 1.5` (line
84, also the code default), line 91 hands the student a 16-term negative including
`angel, wings, halo, saint, religious, crucifix, biblical, cherub`, and line 215 tells them
to TUNE it per-LoRA ("drop the religious-bias suppressions, keep the generic anti-noise
terms"), which implies a granularity that does not exist at 1.5.

The harm is a false cause: a student credits their negative for the absence of angels, when
the work is being done by the style prefix, the LoRA and the subject clause. Later, when
something unwanted does appear, they add negative terms, nothing happens, and they have no
model of why.

`/kb-sync` FLAGGED this on 2026-08-10 and deliberately wrote nothing, because rewriting
teaching material on one render pair would overstate the evidence. **Approved text, to
APPEND (not to replace their guidance), on Luca's yes:**

> **Measured caution, 2026-08-10.** At `guidance_scale: 1.5` (the value above, and the code
> default) classifier-free guidance gives the negative branch almost no weight, and a
> negative term measured close to inert: a figure that a `people, figures, a standing figure`
> ban failed to remove vanished immediately at guidance 3.0 with nothing else changed, and
> putting the suppression in the positive prompt did nothing either. Treat this negative as
> inherited convention, not an active control. What keeps unwanted content out here is the
> style prefix, the LoRA and the subject clause. Evidence is one render pair on the Cole
> LED-wall configs (`led14_c_cfg3` against `led14_c_pospeople`, L25 above), so read it as
> "measured here, expect it to hold" rather than proven across every subject.

Do NOT tell the student to delete the negative: that has not been measured.
Same open question applies to `docs/manual/train-lora-on-modal.md:114` ("aggressive negatives
fight stylistic LoRAs"), which may be unaffected if validation runs at a different guidance.
Check the guidance there before touching it.

### L25. PL12 answered: the map was the CAUSE of the figure, not a bystander

`led15_c_broken`, $0.042, every dial held at `led13_c_realloc_soft` except
`control.image`.

The diagnosis is the result. `led2-c-desolation.png`'s near shore is a
**perfectly level plane**: its crest sits within 13 rows across 1248 columns,
and at row 760 every single column is exactly 219. In depth terms that is a
lit, empty stage, and Cole painted staffage on foreground ledges all his life.
The map was not permitting the figure, it was inviting it.

`tools/make_massing.py --break-ledge` rewrites only that shelf: about six broad
wedges instead of one plane, three notches cut to black with one centred on
x=487 where the figure actually stood, and a lateral tilt so a horizontal cut
crosses several depths. Rows 0 to 639 are byte-identical, so the crag, the far
shore and the ruined columns are untouched and the result attributes to the
ledge alone.

| | control | led15_c_broken |
|---|---|---|
| standing figure | present at the peak | **gone, at every frame checked** |
| mean luminance, delivered crop | 50.26 | **52.23** (+3.9%) |
| arc swing | 9.93 | **10.29** |
| HF energy | 100% | 97% |
| loop delta | 0.97 | 1.24 |

**Compare the cost of the only other lever that works.** Guidance 3.0 removed
the same figure for 25% of the luminance and 155% of control's HF energy.
Geometry removed it while getting slightly BRIGHTER and slightly wider in the
arc. The palette was the thing this screen is for, so this is the route.

**Judge the composition, not just the defect.** The wedges read as broken
columnar blocks, so the "ruined columns" the prompt puts *far across the water*
now also stand in the foreground. On-concept for Desolation, arguably, but it
is a real compositional change and it is Luca's call, not a metric's.

**First bisect if it is wanted:** teeth, notches and tilt shipped together as
one intervention. Teeth alone measure near mass-neutral (map mean 61.4 against
the original 62.8), so notches-only is the cheap next probe.

**Two mechanics worth not rediscovering.** `outputs/_anchors/` is NOT in any
Modal mount; the maps live on the `slow-interp-outputs` volume. A new map needs
`modal volume put` first or the render dies on a bare `FileNotFoundError`
*after* the container has spun up. And `output_name` overrides the render
filename while feeding nothing else (`pipeline.py:47`), which is what makes a
byte-identical rerun possible.

### L26. PL9 answered in full, and it hands the workstream a NOISE FLOOR

`led15_c_repro` is `led13_c_realloc_soft` with one line added, `output_name`.
Same seed, same map, same schedule, same tier.

| frame | % of loop | raw r | composition r (sigma 12) |
|---|---|---|---|
| 0 | 0% | 0.927 | **0.980** |
| 120 | 40% | 0.847 | 0.928 |
| 150 | 50% | 0.852 | **0.922** |
| 186 | 62% | 0.846 | 0.930 |
| 260 | 87% | 0.921 | 0.980 |
| 299 | 100% | 0.932 | 0.982 |

**The seed takes and determinism does not**, confirming L23 on the finished
render rather than on the warmup anchor. But the new fact is the SHAPE:
divergence is smallest at the loop ends, where warmup and the return pin the
image, and largest at the midpoint, which is furthest from both. Kernel
nondeterminism accumulating with chain depth, then pulled back by loop closure.

**The consequence is a measurement rule the whole board needs.** Re-running the
SAME config gives composition r ~0.92 at mid-loop. So a frame-matched
composition r of 0.92 or better between two DIFFERENT configs is inside the
noise floor and attributes to nothing. Any A/B claim on this pipeline has to
clear that bar first.

**Arc metrics are far safer than frame-matched ones**, which is why the light
work stands: control against its own rerun differs by 0.15 on swing (9.93 vs
10.08) and 0.3 on min. The arc results in L22 are 3 to 4 units, i.e. an order
of magnitude above the floor.

**The 62% peak survived a third lever.** Control 62.6%, rerun 62.6%, broken map
63.6%. Neither frame allocation nor the control map moves it. It is the first
return keyframe, and it is structural.

## Session 2026-08-11: seamlessness is arithmetic, and the objective changed

Luca's steer, mid-session: **drop the Course of Empire / NYC skyline framing and work
only on subjects the LoRAs were trained for. The objective is soft and seamless
interpolation with sharp focus across the whole 10 seconds, at wall geometry.** That
is a quality target, not a narrative one, and it decomposes into measurable axes.

### L27. Two of the three faults were arithmetic, not aesthetic, and nobody chose them

Measured on the raw 439-frame `led13_c_realloc_soft`, not on the conformed file.

**Fault 1, the keyframe lurch.** Velocity spikes at raw frames 54, 109, 164, 219, 274,
329, 384 and nowhere else. Those are exactly the keyframe boundaries; within a pair the
velocity is flat. The cause is in [`linear_interp`](../../../../src/slow_interpolation/interpolation/rife.py):
it visits `t = i/64` for i in 1..63 then drops the first and last `skip_boundary`. So a
normal step is 1/64 of a pair and the step ACROSS a keyframe is `(2*skip + 1)/64`. At
`skip_boundary: 4` that is **9x a normal frame, eight times per loop, at 0.8 Hz.**

This corrects the model in [chained-diffusion-limits.md](../../../findings/chained-diffusion-limits.md),
which says motion is "slowest at each keyframe and fastest mid-pair". On these configs
the opposite is true: the keyframe crossing is the FASTEST event in the clip.

**Fault 2, the retime shimmer, and it is created after the render is finished.**
`conform.py` retimes 439 to 300 with `setpts` + `fps`, i.e. nearest-neighbour
decimation, dropping 139 frames so roughly every third output frame is a double step.
Raw velocity runs 0.616, 0.837, 0.806, 0.597, 0.577, 0.486. The same content conformed
runs 1.532, 0.917, 0.939, 0.555, 1.015, 0.55. The alternation does not exist upstream.

**Fault 3, the sharpness pulse.** HF folded over one pair swings 44.7%, sharp at the
keyframe and soft at the midpoint, and it is visible by eye at native resolution.

### L28. The fix is config-only, and the pair `led17_*_dense` beats the previous best on every axis

`skip_boundary: 0` kills fault 1. **K=10 at `passes: 5` kills fault 2 by arithmetic**:
`10 * 31 - 1 = 309` raw frames, so conform drops 9 instead of 139. Strengths came down
0.52/0.54 to 0.46/0.48 for the coupled dial, landing on 9 real steps at 20, clear of the
integer boundaries at 0.45 and 0.50.

Delivered files, screen C, against `led13_c_realloc_soft`. Run-to-run floors from the
`led15_c_repro` pair are in brackets.

| | control | `led17_c_dense` | floor |
|---|---|---|---|
| lurch (keyframe step / median step) | 2.31 | **0.99** | +-2% |
| jitter (frame-to-frame roughness) | 0.55 | **0.18** | +-2% |
| loop step | 4.65 | **3.43** | +-8% |
| **light arc swing** | 10.00 | **18.56** | +-0.1% |
| HF trough, the softest moment (raw) | 0.0192 | **0.0205** | +-1.6% |

Screen B moves the same way: lurch 1.63 to 0.44, jitter 0.57 to 0.15, arc 9.50 to 16.71.

**Read the pulse number correctly, it is a trap.** The folded swing gets WORSE, 44.7% to
54.1%, and that is not a regression: the trough ROSE 6.8% while the peak rose 21%. No
moment in the clip is softer than before. A normalised swing hides whether the floor
moved, which is the same failure class as "frame-average metrics lie" in ratio form.
**Always report the trough next to the swing.**

**The arc result extends L22 and is the biggest number here.** Lowering strength made the
arc nearly double (+86% on C, +76% on B), and it did it at the BRIGHT end: C's max went
56.39 to 64.38 while its min held at 45.82. L22 recorded that the sun pole "still does
not arrive". At K=10 with strength down, it arrives.

**Noise floors for the seamlessness instruments**, derived free from `led15_c_repro`:
lurch +-2%, pair pulse +-0.8%, HF mean +-1.3% raw, loop step +-8%, arc swing +-0.1%.
Arc and lurch are sharp instruments; velocity variation as `(max-min)/mean` is NOT, it
carries a +-20% floor and is not comparable between clips of different frame counts.

### Open from this session

- **`conform.py` should not decimate.** A motion-compensated retime on the same source
  measured velocity variation 529% to 431% at zero sharpness cost, but the better fix is
  the one used here: choose K and passes so the raw count lands near 300. Worth a
  standing note in the tool, and `TARGET_FRAMES` arithmetic belongs in the config
  comments of every new render. NOT yet edited.
- **`linear_interp` could take an explicit frames-per-pair.** It already calls
  `model.inference(img0, img1, timestep=t)` at arbitrary t, so `2**passes` only decides
  HOW MANY t values. An explicit count would let a render hit exactly 300 raw frames and
  remove the retime entirely. Small, additive, backwards compatible. Proposal only.
- The standing figure is absent from `led17_c_dense`, but as a side effect of a different
  trajectory, not controlled suppression. It is NOT evidence for PL12.

### L29. The publish gate, and what building it revealed about the instruments

Standing rule from Luca, 2026-08-11: every output is analysed with the Gemini
multimodal video tool AND with frame analysis at the frames Gemini flags, and a clip
with blur, non-smooth interpolation or border artefacts does NOT reach the gallery.
Implemented as [`tools/review_gate.py`](../../../../tools/review_gate.py).

Three things had to be learned the hard way while building it, all worth keeping.

**1. Gemini is noisy and a single sample cannot be gated on.** Same clip, same
prompt, three runs: loop 7/9/7, motion 6/7/6, flag count 8/3/6. An earlier verdict
of 9/9/8/9 was a lucky draw that did not reproduce. The gate now takes the MEDIAN of
three runs and keeps a flag only if a MAJORITY of runs report that kind within 1.5 s.
On one clip that dropped 15 of 15 flags as unsupported. Treat any single Gemini score
as +-2 on loop and +-1 elsewhere.

**2. The canvas edge is invisible to BOTH instruments, and stayed invisible.** Gemini
raised no border flag on renders that carry an obvious 55px smear band, because it
watches a downscaled clip and the band is 3% of the width. Four band statistics were
then tried against a hand-verified set of four dirty and four clean clips, and all
four overlapped:

| discriminator | dirty | clean |
|---|---|---|
| HF energy, band vs interior | 1.17 to 3.06 | 1.01 to 1.44 |
| streak direction, bin-count corrected | 0.07 to 0.23 | 0.11 to 1.57 |
| strongest vertical edge near the border | 1.45 to 2.53 | 1.27 to 2.49 |
| local tile detail, band vs interior | 0.68 to 1.05 | 0.69 to 1.35 |

One of those failed for an instructive reason: a 64px band has 33 x-frequency bins
and a 1344px interior has 673, so any SUM over a frequency bucket measures the crop
width rather than the content. Using the mean per bin fixes that particular bug but
still does not separate. **So the gate writes native-resolution edge strips and they
get LOOKED AT.** Do not replace that with a threshold without re-validating.

**3. Rubbery morphing is the dominant defect and no metric here can see it.** It is
local warping at constant global velocity, so every frame-step measure is blind. It
is found only by the judge, which is why the gate also fails on Gemini's scores.

### L30. Everything currently fails the gate, and the pattern names the cause

Ten renders across led18 and led19, $0.35. Median-of-three Gemini scores.

| render | subject | loop | motion | image | verdict |
|---|---|---|---|---|---|
| `led18_cole_woods` | 9 | 10 | **6** | 9 | 8 confirmed motion/blur flags |
| `led19_cole_soft` | 9 | 9 | **6** | 9 | morphing of branches and roots |
| `led19_renoir_base` | 8 | **3** | 7 | **9** | loop broken, image the best of any run |
| `led19_renoir_crop` | 9 | 8 | **3** | 6 | dissolves mid-loop, REJECT |
| `led19_renoir_soft` | 8 | 9 | 7 | 7 | blur CONFIRMED 0.62x, morph 4.46x |

**Motion 6 recurs on every Lightning render regardless of subject.** That is the
systemic blocker, and it is Luca's own diagnosis: RIFE's flow field reconciling two
keyframes whose composition and detail differ.

**Two attempted fixes both backfired, and the direction is the lesson.**
`crops_coords_top_left` 256 to 512 was meant to kill the canvas edge and instead
destabilised the chain into a mid-loop dissolve (motion 3, image 6). Lowering
`steady_strengths` to 0.40/0.42 was meant to reduce inter-keyframe difference and
instead made it BLURRIER (confirmed 0.62x): repainting less means the model stops
restoring detail, so RIFE's soft in-betweens are never refreshed. **Less repaint buys
stability and costs sharpness**, which is the opposite trade from the light arc.

### L31. SDXL base answers a question queued since 2026-05-19, and the answer is yes

`led19_renoir_base` is the FIRST time pure SDXL base has run through the video
pipeline: `lightning_lora: null`, 24 steps, `guidance_scale: 6.0`. Every render before
it fused the 4-step Lightning distillation and then asked it for 20 steps, which is
off-distribution.

- **image 9, the best of any render this session**, and no blur or morphing flag
  survived voting. Luca's 2026-05-19 keyframe-level verdict, "sdxl base reads more the
  painting brush", now holds at video level.
- **The canvas edge is gone.** At guidance 6.0 the negative branch finally carries
  weight, so the `canvas edge, picture frame` ban that L25 measured inert at 1.5
  actually bites. The edge fix and the backbone change are the same change.
- **Loop 3, and that is the one thing to fix.** Score spread across runs was 7, so it
  is a low-confidence number, but every run named the wrap. `return_: 2` and
  `return_pixel_blend_max: 0.45` were tuned for Lightning and have never been tuned
  for base.

**Next: base plus loop closure.** That is the open thread, not another subject.

### L32. The output analyser: what was built, and the three detectors that do NOT exist

Luca 2026-08-11: build an analyser that reads speed, smoothness, focus and artefacts,
so renders can be produced, benchmarked, improved and iterated into a set worth
curating. Shipped as [`tools/analyse_render.py`](../../../../tools/analyse_render.py)
alongside [`tools/review_gate.py`](../../../../tools/review_gate.py).

**What works, with floors.** speed (optical-flow magnitude, which unlike frame
differencing does not confuse a light change with a move), lurch, jitter, loop,
flicker, focus mean AND trough, and `rigid%`, the share of flow energy explained by a
global affine fit. Floors from the repro pair: lurch +-2%, focus +-1.3%, trough
+-1.6%, loop +-8%, arc +-0.1%, Gemini +-2 on loop and +-1 elsewhere.

**Three detectors were attempted and do not exist. Recording them so nobody spends
another day on them without new evidence.**

1. **Border / painted canvas edge.** FIVE statistics tried against a hand-labelled
   set of four dirty and four clean clips; all five overlap. HF energy in the band,
   streak direction, bin-count-corrected streak direction, strongest vertical edge
   near the border, local tile detail, per-pixel temporal variance. The artefact is
   repainted every keyframe, so it drifts with the picture and is neither spatially
   nor temporally anomalous. **Gemini never flagged it either**, because it watches a
   downscaled clip and the band is 3% of the width. Only opening a native-resolution
   edge strip found it. The gate writes those strips; they get looked at.
2. **Rubbery morphing.** Three flow measures tried, none matched the judgement:
   residual-px tracks speed almost exactly (so it measures speed, not rubberiness),
   spatial roughness spans 0.148 to 0.239 with no ordering, and temporal coherence
   puts `led19_renoir_base` LOWEST at 0.492 despite it being the one clip with no
   morph flag.
3. **A single-number quality score.** Not attempted on purpose, see below.

**The reason the last two failed is methodological and it matters more than the
metrics.** Each was being fitted to ONE Gemini label per clip, at +-1 noise, across
clips that differ in backbone, subject, palette and schedule simultaneously. That is
not a validation set. Any threshold fitted that way is fitted to noise.

**So the proposal is to build the labelled set from the curation loop that already
exists.** Luca already removes cards he does not like, and that removal list is a
labelled rejection set sitting unused in `outputs/_glance-inbox/`. Pair each removal
with the analyser's row for that clip and the thresholds can be FITTED to his taste
instead of guessed. Until roughly 20 to 30 labelled clips exist, the analyser should
report numbers and refuse to render a verdict, which is what it currently does.

### L33. SDXL base is better paint on a less stable chain, and the fix is calibration

`led19_renoir_base` against `led18_renoir_field`, identical prompt and subject, only
the backbone differing:

| | Lightning | base |
|---|---|---|
| Gemini image | 8 | **9** |
| morph / blur flags surviving a majority vote | several | **none** |
| canvas edge | present | **gone** |
| lurch | 0.01 | **2.09** |
| flicker events | 2 | **24** |
| jitter | 0.13 | **0.31** |

**Diagnosis: base was run at Lightning's strength.** At 24 steps, `strength 0.46` is
11 real steps of a NON-distilled model, which is a far heavier repaint than 9 steps of
Lightning. Heavier repaint means keyframes that differ more, which is exactly the
instability the numbers show. Base needs its own denoise calibration, roughly 0.30 to
0.35, and that is the next render rather than another subject.

One caution on the focus column: `renoir_base` reads 0.0561 against `renoir_field`'s
0.0091, a 6x gain. **Do not quote that as a sharpness win.** The measure is a ratio
against total spectral energy, and base's pastel low-contrast surface inflates it. The
metric's own docstring says it is not comparable between compositions, and two renders
of the same subject at very different contrast are two different compositions.

## Session 2026-08-12: the gate recalibrated to Luca's taste, and four clips published

### L34. The absolute gate bar sat ABOVE the taste it served, and the keepers proved it

After 22 renders in two days had ALL failed the publish gate, the calibration check
that should have come first was finally run: gate the two clips Luca chose to KEEP.

| clip | subject | loop | motion | image | confirmed flags |
|---|---|---|---|---|---|
| `led13_c_realloc_soft` (keeper) | 7 | 10 | **5** | 9 | **5** |
| `led12_c_desolation` (keeper) | 8 | 9 | **5** | 8 | **10** |

Both fail "every axis >= 7 and no confirmed flags". So that bar, invented with the
gate, was stricter than the exhibition's own standard, and a day of renders was
judged against it. **The bar is now the keeper floor: subject >= 7, loop >= 9,
motion >= 5, image >= 8, and confirmed flags are reported, never fatal.**

Scores are necessary, not sufficient: Luca REMOVED `led18_cole_woods` at 9/10/6/9,
which outscores both keepers. The gate filters artefact regressions; he curates
taste on top. That is ST3's division of labour, now with numbers.

**Published under the calibrated bar** (never removed by Luca, floor met):
`led20_base_s35` 8/9/7/9, `led20_base_s40` 9/9/7/9, `led22_cole_anchor` 9/10/6/8,
`led22_casa_anchor` 8/9/7/9. All four beat both keepers on motion, which was the
axis the whole seamlessness effort targeted.

### L35. The anchored base chain: Lightning seeds, base sustains

`led22_*_anchor` runs the base backbone from a sharp Lightning keyframe
(`anchor_image` at `anchor_strength: 0.45`, `warmup: 1` per L17). Results:

- **The warm-up ramp collapses where the anchor is clean**: Cole 4.16x to 1.66x,
  Casa to 1.69x. Keyframe agreement doubles or better (Cole 0.849 vs Lightning's
  0.332).
- **An anchor carries its defects into the chain.** `led22_renoir_anchor` was
  seeded from a keyframe with the canvas edge, and the edge came back. Anchor
  hygiene: only seed from a frame that passed inspection.
- **The wrap pair (kf8 to kf9) sits near ssim 0.5 in every anchored chain**: it
  compares the drifted chain end against the saved anchor itself, i.e. it measures
  accumulated loop drift, and `return_` reallocation does not move it (led23:
  0.51 to 0.50). Weakening `return_pixel_blend_max` 0.45 to 0.35 BROKE closure
  (Gemini loop 10 to 4). Leave the blend at 0.45 on anchored chains.
- Removing the water subject did not clear the morph complaint (led24: trees morph
  too), so morphing pressure is in the chain, not the subject.

### Curation loop hardening, after a real failure

Luca curated at 16:53 on 08-11; the list sat unapplied for six hours because the
exclusion union was hand-built. `tools/curation_sync.py` now owns it: `--check`
exits 1 naming unapplied keys, `--apply` archives and rebuilds. Runs before every
export. His removals are permanent and are never re-added by the agent, including
clips that outscore the keeper floor.

### L36. Two published clips failed by eye, and the gate now withholds PASS until the eye step is recorded

Luca, 2026-08-12: the Renoir clips carry "line artefacts on the left and right side"
and the Cole "has a loss of detail and looks underdeveloped". Both confirmed at
native resolution and both pulled (plus `led20_base_s40`, same edge). Only
`led22_casa_anchor` survived inspection and stays.

**Neither was an instrument gap. Both were the agent skipping its own documented
steps.** The gate had already written the edge strips and labelled them INSPECT BY
EYE; they sat unopened while the clips published on scores. And the Cole haze was
observed by the agent at first look ("Cole is very soft"), then overridden by
Gemini's image 8. Two rules follow:

1. **A score never overrides your own eye.** Gemini's image axis is +-1 and it
   watches a downscaled clip; the native-res frame is the evidence.
2. **The strip inspection is now enforced, not requested.** `review_gate.py` can no
   longer emit PASS from scores: it emits PENDING-EYE, and `--signoff <clip>
   --edges-clean --detail-ok` flips it only after both claims are made about files
   actually opened, timestamped into `review-gate.json`. Signoff evaluates stored
   scores against the current keeper floor and cannot override a floor failure.

**On the Cole underdevelopment, the diagnosis is L30's trade seen from the other
side.** kf_ssim was optimised to 0.849 at strength 0.35, and that agreement was
bought by under-painting: a chain that barely repaints barely develops. The anchored
chain fixed the ramp but capped detail at 8 real steps per keyframe. Development
needs steps, agreement needs small strength; the two are the same dial only at fixed
step count, so the next lever is `num_inference_steps` up at strength held low,
which raises steps-per-keyframe without raising drift. Untested.

### L37. led25: the development dial works on Renoir, the edge is strength-bound, and the trim ships

Four renders at `num_inference_steps: 40`, strength held 0.35 (14 real steps against 8).
Eye inspection ran FIRST this time, before any Gemini spend.

- **Development recovered on Renoir**: `led25_renoir_peony`'s opening frames show formed
  petal structure inside what used to be the warm-up haze. The 14-step recipe fixes the
  underdevelopment Luca called out, on this LoRA.
- **It did NOT recover Cole** (`led25_cole_steps` still washed out). The anchored-base
  recipe is refuted on Cole at any tested steps; Cole currently has no working base
  recipe. Chrys and wisteria stayed milky: subjects whose detail is fine-grained
  (small blooms, clusters) need more than 14 steps or more strength; the close-up
  peony resolved because its forms are large.
- **The canvas edge is STRENGTH-bound, not steps-bound.** led19 at 0.46/11 real steps:
  clean. led25 at 0.35/14 real steps: edge present. So it is repaint fraction that
  overwrites the band each keyframe, not denoise depth, and low-strength Renoir will
  always paint it.
- **The shipping fix is mechanical: trim the band before conform.** Crop 56 px per side
  off the raw render, conform upscales 1.227x instead of 1.137x. Edge verified gone by
  eye in the delivered file. Cost: zero renders. Caveat: the trimmed intermediate loses
  manifest provenance; acceptable for candidates, fix conform.py provenance pass-through
  if a trim ever ships as a delivery file.

**Published after signoff**: `led25_renoir_peony_trim`, gate 9/9/6/9, edges and opening
and worst-flagged moment all opened and judged. The t=2-4s softness is the drift itself,
wet paint moving, same flag class the keepers carry.

## Session 2026-08-12 (later): the Arendt pivot, and the first loop that beats every chained render

### L38. New direction: the Vita Activa series

Luca's call: drop the long-aspect single pieces as primary format. The work becomes a
SERIES of 10 s loops on Hannah Arendt's vita activa triad (labor / work / action, The
Human Condition 1958; his descriptions verified against sources, terminology corrected:
"work as repetition" is Arendt's LABOR), later EDITED side by side into the long
billboard file. For both the NYC billboard and the objkt labs release. Show-side record:
`Ruins-agent/knowledge/research/arendt-vita-activa-series.md`. Styles: Cole and Soutine
LoRAs, plus NO-LORA prompt-styled experiments.

### L39. Edit-model keyframes: only the acting element moves, and it beats the chain

The capability Luca specified: keyframes authored with an image-EDIT model (Gemini
image editing, `gemini-3.1-flash-image`) that holds everything constant except the
acting element, so interpolation animates just that element.

**Validated end to end, first try.** `tools/banana_keyframes.py` + local RIFE Phase C
(`vendor/rife_v425`, no Modal, w and h must be % 64):

- Five keyframes: hands washing in a sink from above, prompt-styled oil paint, no LoRA.
  Background SSIM 0.83 to 0.94 between consecutive keyframes with the hands masked.
- `outputs/arendt/labor_hands.mp4`, 1408x768, 300 frames, 10.000 s.
- **Gate: subject 10, loop 9, motion 9, image 9. Highest scores of the project.** Every
  chained render scored motion 5 to 7; this scores 9 because the morphing complaint is
  absent BY CONSTRUCTION: keyframes disagree only where they are supposed to.

**Why this matters beyond one clip.** The diffusion chain re-derives the whole image
every keyframe, so everything morphs a little; two days of tuning fought that. The
edit-model path inverts the architecture: consistency is the default and change is
authored. Phase A becomes optional per piece. Open questions: whether the aesthetic
holds without the chain's drift texture (Luca judges), per-keyframe control maps for
ControlNet passes over these keyframes, and the wrap pair (author the last edit to land
near the base state, or the wrap carries the biggest step).

### L40. The first Arendt triptych: two of three land, and the third names a law

Built banana-first in the soft register (sfumato brief, impasto banned), ~10 to 14
keyframes each at SMALL deltas (consecutive SSIM 0.82 to 0.98 against the probe's
0.64 to 0.73), local RIFE, 300 frames at 10.000 s. Keyframes eyed and measured
BEFORE interpolation, per Luca's instruction.

| piece | cluster | gate | seam treatment |
|---|---|---|---|
| `labor_knead` | Labor | 9/9/5/8 PASS | bridge keyframe authored from BOTH endpoints (multi-image edit) to shrink the wrap |
| `action_window` | Action | **9/10/9/8 PASS** | ten-frame held dark beat before the wrap, the doctrine's in-breath, and the gate scored the loop 10 |
| `work_chair` | Work | FAIL loop 4, twice | see below |

**What the chair taught, in two layers.** First attempt: the hand materialised in one
keyframe step; pixel SSIM (0.94) cannot see semantic velocity, so keyframe critique
must check WHAT changed, not how many pixels. Second attempt spread entry and exit
over three keyframes each and still failed on speed, which exposes the real law:
**a 10-second loop cannot contain a plot.** Decay + entry + work + exit is four acts;
every act above one is paid for in speed. The redesign drops the decay act: the
hand's single slow pass IS the loop, care as perpetual. More Arendtian anyway.

**Mechanics worth keeping:** nano banana accepts MULTI-IMAGE input, so a wrap can be
closed by handing it both endpoint keyframes and asking for the in-between (labor's
bridge). The tone drift across a chain (table warming) caps endpoint SSIM but RIFE
cross-fades it invisibly; do not chase it. 448 raw frames to 300 is the documented
judder ratio, so long chains retime with minterpolate mci, not frame drops. And
Gemini flagged the kneading table's own plank grain as a border artefact: eye
overrides recorded as false positive.

### L41. Hammershøi dataset: sourcing and audit under way

Luca picked Hammershøi over Morandi from side-by-side mosaics (Morandi reviewed and
deleted; in copyright, never to be trained without an explicit decision). Sources:

- **SMK API**: 64 works with images, all flagged public_domain. Audited: **zero
  perceptual duplicates** (dhash, after fixing a hash bug that made every image
  identical); 15 border suspects are charcoal-on-paper margins and portrait mounts,
  nearly all outside the register anyway.
- **Wikimedia Commons**: category tree walked recursively (58 categories, including
  a pre-sorted `Paintings of interiors by Vilhelm Hammershøi`), **260 unique files
  listed**. Download was 429-throttled after burst fetching; restarted at 6 s pace
  honouring Retry-After. Lesson recorded: Wikimedia throttles the IP, not the
  request, so a burst poisons the whole session.

Next: dedupe the wave against SMK (Commons carries multiple scans of one painting,
keep highest resolution), register filter (interiors, windows, still, pale
landscape; drop portraits and nudes per the Cole figure-drift experience), review
mosaic to Luca, then caption and train (~$0.30-1.60 on Modal).

### L42. The vhm LoRA: Luca's curation processed, training dispatched

The dataset-mosaic protocol ran end to end for Hammershøi in one day. Luca walked the
gallery (`datasets/hammershoi/serve.py`, the renoir-flowers tooling reused): **115
keeps, 18 rejects, 3 manual crops**. He overruled 13 of the agent's proposed drops,
keeping Hammershøi's figures (Ida with the teacup, the models seen from behind) in
the register: the curator's call, now captioned in a figure register.

Packaging: captions aligned 115/115 (5 slug-collision duplicates deduped), crops
applied at percent coordinates so they survive resolution changes, staged as
image+txt pairs, 118 MB ZIP, uploaded. Training dispatched:
`examples/configs/training/hammershoi_interiors.yaml`, trigger `vhm`, floral preset
(rank 16/8, lr 3e-5, repeats 6), publishing `Hammershoi_Interiors_epoch_{epoch}`.

Sourcing lessons for the next dataset, all paid for in wall-clock:
- **Wikimedia throttles the IP, not the request.** One burst poisoned every later
  fetch; Retry-After compliance is mandatory from the first request.
- **The thumb server 400s when asked to upscale**: request 1600px only for files
  whose original exceeds it, else fetch the original.
- **Slug collisions silently overwrite**: two scans of one painting can share a
  slug; keep the caption list deduped by filename and let the perceptual hash own
  duplicate detection (32 dupes caught across SMK+Commons).
- Mixed 1600/900px training input accepted deliberately: SDXL bucketing handles it
  and the Renoir set trained the same way. Do not chase pixels past the bucket size.

### L43. vhm epoch choice by instrument, and the first two chain lessons of a fresh LoRA

**Epoch selection ran as a real instrument sweep**, not an eyeball: `validate_lora`
extended to run on the deployment backbone (`lightning_lora: null` now supported,
because epoch choice must be made on the backbone that ships, L27/L31), 11 prompts
across epochs 1/5/8/10 on pure base at guidance 6. Epoch 10 won every axis
simultaneously: detail (HF 1.66 vs 1.43), tonal compression (value range 107 vs 136,
Hammershøi's own signature), grey chroma (8.3), cross-prompt coherence (0.39). A
monotonic sweep with no trade-off = no overfit signature. **Epoch 10 at 0.80 is the
family default.**

**Chain lesson 1: a caption prior is a composition force.** The vhm corpus is
saturated with "bare walls / plain plaster wall", and the first Space-of-Appearance
chain (`arendt_action_vhm`) collapsed to exactly that: blank wall mid-frame, windows
squeezed to the edges. An anchor image alone cannot hold composition against a LoRA
prior; naming the prior in the prompt ("plaster walls") summons it. Same mechanism
as Cole's staffage, opposite sign.

**Chain lesson 2: the map pins what the prior erases, but the map's margins paint as
smear.** v2 added a depth map derived from the lit banana keyframe (windows as
recesses): the grid SURVIVED the whole chain, proving the pin, but the map's grey
margin band rendered as a smeared ring, and the lit-window warmth barely penetrates
the LoRA's grey. v3 spec: full-bleed map (build from a frame cropped to the facade),
window recesses enlarged, "glowing warm amber windows" promoted to the head of the
light phrase, and lora_scale dropped a step (0.80 to 0.70) to loosen the grey grip
at the peak. Not yet run.

### Cross-workstream, for `/ingest` to route (NOT this workstream's zone)

- **`tools/glance_curate.js`**: the tier-0 curate face lost every mark on exit,
  because the viewer's `exitSelectMode()` runs `selection.clear()`, and `done` was
  the only button that looked like a commit. Relabelled, marks now persist to
  `localStorage` and restore via `selectShas()`, export states plainly that the
  tiles remain until the rebuild. Verified in Playwright against a local build of
  the assembled site. Landed `a26fbd705`. **The production redeploy is still
  pending** and the removal round trip was proven end to end (107 to 104 assets,
  exactly the exported keys). No row exists in the workstream registry for
  `tools/glance_*`, so this defaults to the parent tracker.
- **`modal-sdk-quirks.md` quirk 7b**: the Windows codepage crash on `modal run`
  creates a zombie ephemeral app with 0 tasks, renders nothing, spends nothing,
  and can exit 0 through a pipe. Fix is a per-command `env PYTHONIOENCODING=utf-8`
  prefix, because Bash-tool shell state does not persist.

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
