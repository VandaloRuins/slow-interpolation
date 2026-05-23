# Noise research progress

Pre-curation flush completed 2026-05-18, mode B.

Status log for the Phase 3 noise-research workstream. The master log lives
at [../../progress.md](../../progress.md); this doc is the integration
surface for this workstream.

> ## PARENT-CHAT NOTICE: hardware-routing protocol shipped, Modal-default reframe required (2026-05-18)
>
> Luca flagged that "Modal is default for multi-variant tests" (your decision-log line dated 2026-05-17) was correct in its context (Luca's local GPU was busy with other work then) but is not the universal default. The new canonical protocol is at [`../../../manual/hardware-routing.md`](../../../manual/hardware-routing.md): **local first; Modal when local is insufficient or parallelism is worth the cost.** Modal credit is finite (~$30/month free); reserve for work that genuinely needs cloud.
>
> Action on your next session:
>
> 1. Read [`../../../manual/hardware-routing.md`](../../../manual/hardware-routing.md) start to finish. The pre-flight (nvidia-smi + torch + disk + GPU-busy), decision table, trade-offs, and cache file are all there.
> 2. Reframe the "Modal cloud-render is the default for multi-variant tests" decision-log entry in this `progress.md` (line ~223 today). New shape: **"Modal is the default WHEN local hardware is insufficient OR the parallelism is worth the cost."** Keep the workstream-local rationale (parallel L40S collapses 3 h sequential to 25 min); just soften the unconditional default. Add a cross-link to the routing protocol.
> 3. Update the workstream-local auto-memory entry `feedback_slow_interp_modal_preference` to match: "Modal is the default WHEN local hardware is insufficient OR the parallelism is worth the cost." (Per Luca's note in the original request.)
> 4. Skim [`../../../findings/noise-sources.md`](../../../findings/noise-sources.md) for the few "next renders go on Modal" phrasings (~line 325) and either soften or leave as historical-narrative depending on context. Not blocking; cosmetic.
>
> Nothing in your scientific findings changes. The spatial-frequency lever, the source verdicts, the multi-round results are all sound. The change is purely about where future renders dispatch: local-first by default, Modal when local is insufficient or parallelism is worth the cost. Your work was the test case that proved the value of Modal for parallel sweeps; that lesson stands. The new protocol just makes the routing decision explicit rather than implicit.

See [docs/findings/noise-sources.md](../../../findings/noise-sources.md) for
the research findings doc itself.

Last updated: 2026-05-18.

## Resume here (post-compact pointer)

State at the chat compact on 2026-05-18, late afternoon:

- **Five render rounds shipped, all integrated as Sections A through J of [outputs/noise-tests/compare.html](../../../../outputs/noise-tests/compare.html).** Page is now collapsible (`<details>` per section + Expand-all / Collapse-all buttons + click-to-collapse arrows).
- **Round 5 (the most recent) just landed**: 9 meadow variants, $0.695, 9 min wall. Sweeps four motion-quality levers on evolved_walk, plus a banded cd=1000 cost variant against the Round 4 cd=3000 baseline. **Verdicts pending Luca review.** Two decisions to lock from Round 5: (a) which lever value becomes the new motion-quality default for each of the four levers tested, (b) whether banded cd=1000 reads visually equivalent to cd=3000 (a "yes" cuts ~70% of dense-Worley spend on the release).
- **Known artifact under investigation**: chunky interpolation jitter, observed across all Round 4 outdoor-field renders. Likely RIFE-meets-off-distribution-keyframes, not noise-side. Round 5 was designed to localise which lever dominates the jitter. Full writeup in [findings doc, "Interpolation jitteriness" section](../../../findings/noise-sources.md#interpolation-jitteriness-on-off-distribution-or-loose-keyframes).
- **Image_derived paused** (not deprecated). Reference-content bleed at `high_pass_sigma=32` is not artistically usable as-is; technique parked for future texture-biasing use cases.
- **Modal credit budget**: ~$18 to $20 remaining of the $30 monthly free tier (after 5 rounds + smoke tests + Round 3 retry).
- **Next moves once verdicts arrive**: lock motion-quality defaults; lock banded cd=1000 vs cd=3000; potentially re-render Round 4's three field subjects with the new defaults to confirm jitter is suppressed; only THEN return to the noise-palette comparison for the release decision.
- **Cross-workstream**: T3#9 anchor clamp A/B (approved + assigned, see CROSS-WORKSTREAM VISIBILITY note below) is the recommended next batch after Round 5 verdicts land. Independent of noise palette; A/B's pixel-blend-toward-anchor at 0% / 20% / 40%.

## Log

- 2026-05-18 (Round 5 complete): 9/9 succeeded. Wall 541 s parallel (~9 min), total cost $0.695. Banded cd=1000 ran in 535 s ($0.29) vs Round 4 cd=3000's 1401-2605 s ($0.76-$1.18). Worley broadcast cost scaled linearly with n_points as predicted. Outputs at `outputs/noise-tests/round-5-motion-levers/`. Integrated as Sections I + J of compare.html (compare.html sections are now collapsible via native `<details>` + Expand-all/Collapse-all controls). Verdicts pending: which lever values become new motion-quality defaults + whether cd=1000 reads as well as cd=3000 (production-cost lock-in).
- 2026-05-18 (Round 5 dispatched): nine-variant motion-quality lever sweep on Modal. Subject = meadow, noise = evolved_walk for 8 variants, plus 1 `banded` at `cell_density=1000` (3x cost reduction test). Sweeps denoise strength (calm + aggressive), `frames.steady` (7, 9), `frames.transition` (5, 7), `rife.skip_boundary` (0, 6). Reframe of Round 4 noise-vs-noise comparison: dominant artifact is likely lever-side not noise-side. Budget ~$0.67, wall ~80 s parallel. Full design in [findings doc Round 5 section](../../../findings/noise-sources.md#round-5-design-motion-quality-levers-sweep-dispatched-2026-05-18).
- 2026-05-18 (image_derived paused): removed from the active sweep cycle pending a return-to-need signal. Reference-content bleed at `high_pass_sigma=32` is not artistically usable as-is. Technique itself is not deprecated; documented as a parked future use (texture biasing via reference image) in findings doc.
- 2026-05-18 (Round 4 verdicts, preliminary): `image_derived` with the `girls-picking-flowers-in-a-meadow` reference still bleeds the two figures into the diffused output despite `high_pass_sigma=32`. Either raise sigma to 48 or 64 on a one-variant re-render, or swap to a non-figure-bearing Renoir landscape reference. Documented in findings doc Round 4 verdicts section.
- 2026-05-18: `banded_renoir_tuned` produces "interesting results" on Renoir field subjects per Luca; production keep/drop decision is parked behind the jitteriness investigation (a noise-vs-noise comparison is only meaningful once the dominant artifact is understood).
- 2026-05-18 (new finding): interpolation jitteriness observed across all Round 4 renders, less so on in-distribution Round 3 still-lifes. Cuts across noise families, so noise-palette-independent. Likely RIFE-meets-off-distribution-keyframes mechanism. Cheapest diagnostic: re-render one meadow variant with `render: calm` profile (~$0.05) to test the lower-denoise-strength hypothesis. Full writeup in findings doc, [Interpolation jitteriness section](../../../findings/noise-sources.md#interpolation-jitteriness-on-off-distribution-or-loose-keyframes).
- 2026-05-17: Migrated from `docs/noise-research-progress.md` to `docs/planning/workstreams/noise/progress.md` per the D2 protocol in [../../docs-strategy.md](../../docs-strategy.md). Relative links updated.

> ## CROSS-WORKSTREAM VISIBILITY (from Modal chat, 2026-05-18)
>
> The Modal workstream shipped its Tier 1 + Tier 2 followup plan on 2026-05-18 and approved two items assigned to this noise workstream for integration. Modal provides infra (`cloud/batch.py`, render functions per GPU tier, `render_warm` for sequential dispatch); this chat owns the noise-design + harness side.
>
> 1. **T3#8 Renoir noise sweep.** Approved and assigned for integration. Run the full noise palette against a `examples/configs/renoir/*.yaml` once the Renoir LoRA lands at `models/loras/Renoir_Flowers_epoch_10.safetensors`. **CRITICAL: use the new schema.** Parent chat wired `render.noise.kind` + `render.noise.params` into PipelineConfig on 2026-05-17. The sweep iterates across `noise.kind` values (`evolved`, `perlin`, `worley`, `simplex`, `fbm`, `image_derived`, `frequency_banded`), not just the legacy `noise_walk_rate` knob. The harness already exists at `src/slow_interpolation/noise/harness.py`; verify it consumes the new schema before running the full sweep.
> 2. **T3#9 anchor clamp A/B.** Approved and assigned for integration. Modal provides the batch infra; this chat designs the A/B configs and interprets the results.
>
> Modal-side prerequisites for both: `cloud/batch.py` shipped, `render` + `render_warm` available across L40S / A100-40GB / A100-80GB tiers, `cost_estimate.py` (T1#3) operational.
>
> Gated on Renoir LoRA arrival (same gate as Modal T1#2). No action required from this workstream until the LoRA lands; at that point, T3#8 + T3#9 are ready to run.

## At a glance

| Phase | Scope | Status |
|---|---|---|
| A | NoiseSource ABC + structured sources (Perlin, Worley, Simplex, FBM) | **Done** |
| A tests | `tests/test_noise_sources.py` smoke coverage | **Done** (49 tests, all green) |
| B | Image-derived + frequency-banded sources | **Done** (CPU; VAE path opt-in) |
| C | Comparison harness CLI + contact sheet + `--full-pipeline` | **Done** |
| C-render | First full-pipeline pass: all 7 sources against tcole_valley | **Done** (2026-05-17, ~3h wall time, 7 MP4s + grid PNG) |
| Findings | First-pass `docs/findings/noise-sources.md` | **Updated** with frame-12 observations + compression-size signal; verdicts pending video viewing |
| Bug-A | Diagnose progressive blur in 5 structured-noise videos | **Done** (2026-05-17). Root cause: `structural_decay` removes high freq, structured noise cannot inject it back, blur compounds. See findings doc. |
| Bug-A-fix-test | Re-render perlin with `structural_decay_radius=0` (Option A) | **Done** (2026-05-17). Fix confirmed; Option B (white_floor) not needed. |
| Bug-A-fix-rollout | Re-render worley, simplex, fbm, frequency_banded with no_decay | **Done** (2026-05-17). All 5 sources sharp; before/after sheet at [`../outputs/staging/before_after_no_decay_all5.png`](../../../../outputs/staging/before_after_no_decay_all5.png). |
| Findings-v2 | Per-source aesthetic verdicts + open recommendations | **Done** (2026-05-17). Simplex flagged for deprecation (visually indistinguishable from Perlin); frequency_banded flagged as highest-value landscape source. |
| Workflow | Modal preference saved for future tests | **Done** (2026-05-17). Future GPU-heavy batches dispatch through `cloud/batch.py`. Local harness reserved for CPU preview + one-off iteration. |
| Ops-doc | Long-cloud-job monitoring playbook for agents | **Done** (2026-05-17). Captured at [`docs/findings/monitoring-long-cloud-jobs.md`](../../../findings/monitoring-long-cloud-jobs.md). Background dispatch + auto-notification + dashboard URL + log tail; no polling. Includes the Windows glob-expansion + cp1252 gotchas the Round 2 dispatch hit. |
| Findings-v3 | **Authorial discovery: spatial-frequency lever** | **Done** (2026-05-17). Surfaced by Luca from direct video review: small noise masses produce soft scene motion (evolved_walk, image_derived); big noise masses produce coarse regional motion (Perlin/Worley/FBM/banded). The dial is `feature_size` for Perlin/Simplex/FBM and `cell_density` for Worley. Reframes Modal Round 2 sweep around spatial frequency instead of source identity. See [findings doc](../../../findings/noise-sources.md#authorial-controls-the-spatial-frequency-lever). |
| Round-2-render | **9-variant spatial-frequency sweep on Modal (Cole LoRA)** | **Done** (2026-05-17). Wall 43 min parallel, total cost $3.40. All 9 succeeded. Outputs at `outputs/noise-tests/round-2-spatial-freq-cole/`, integrated as Sections C and D of `outputs/noise-tests/compare.html`. Cost overshoot due to Worley high cell_density being O(H × W × n_points); see [findings doc](../../../findings/noise-sources.md#round-2-render-pass-spatial-frequency-sweep-on-modal-2026-05-17). Verdicts pending video review. |
| Findings-v4 | **Fine-brushwork LoRAs need fine noise (generalization)** | **Done** (2026-05-17). All three active LoRAs (Cole, fresco, Renoir) carry a high-spatial-frequency content register. The Round 1 + Round 2 spatial-frequency lever should generalize to all of them. See [findings doc](../../../findings/noise-sources.md#generalization-fine-brushwork-loras-need-fine-noise). |
| Round-3-plan | **Renoir noise palette test (3-source soft-motion subset)** | **Designed** (2026-05-17). Triggered by Renoir LoRA arrival. Test only `evolved_walk`, `image_derived` (with Renoir reference + `high_pass_sigma=32`), and `banded_renoir_tuned` against `roses_vase_60s.yaml`. Budget ~$1.30 for one subject. Awaiting Luca go-ahead before Modal dispatch. See [findings doc](../../../findings/noise-sources.md#round-3-design-renoir-noise-palette-queued-2026-05-17). |
| Round-3-render | **3-variant Renoir palette on Modal** | **Done** (2026-05-18). First attempt failed due to Modal mount paths gotcha (image_derived's reference image lived under `datasets/` which is not mounted); cascade also stopped banded mid-run. Retry succeeded after relocating reference to `examples/references/renoir/`. All 3 outputs at `outputs/noise-tests/round-3-renoir-palette/` and integrated as Sections E + F of `compare.html`. Total cost ~$1.49. Verdicts pending Luca video review. The mount-paths lesson is now codified in the [monitoring playbook](../../../findings/monitoring-long-cloud-jobs.md). |
| Round-4-render | **9-variant Renoir outdoor-fields sweep on Modal** | **Done** (2026-05-18). Three field subjects (`wildflower_meadow`, `poppy_field_path`, `garden_corner`) × the same 3-source soft-motion palette. Off-distribution test. 9/9 succeeded; $2.98 total. Outputs at `outputs/noise-tests/round-4-renoir-fields/`. Integrated as Sections G + H of `compare.html`. Three preliminary verdicts from Luca: (1) `image_derived` figures bleed through at `high_pass_sigma=32`; (2) `banded` produces "interesting results" but production decision parked; (3) interpolation jitteriness observed across all 9 renders (new finding, likely RIFE-side). See [findings doc Round 4 section](../../../findings/noise-sources.md#round-4-renoir-outdoor-field-subjects-2026-05-18). |

## What landed

### Phase A (done)

Files added:

- [src/slow_interpolation/noise/base.py](../../../../src/slow_interpolation/noise/base.py) — `NoiseSource` ABC + `WalkingNoiseSource` helper base.
- [src/slow_interpolation/noise/sources/_kernels.py](../../../../src/slow_interpolation/noise/sources/_kernels.py) — vectorized numpy kernels: `perlin_2d`, `fbm_2d`, `worley_2d`, `simplex_2d`.
- [src/slow_interpolation/noise/sources/perlin.py](../../../../src/slow_interpolation/noise/sources/perlin.py) — `PerlinNoise`.
- [src/slow_interpolation/noise/sources/worley.py](../../../../src/slow_interpolation/noise/sources/worley.py) — `WorleyNoise`.
- [src/slow_interpolation/noise/sources/simplex.py](../../../../src/slow_interpolation/noise/sources/simplex.py) — `SimplexNoise`.
- [src/slow_interpolation/noise/sources/fbm.py](../../../../src/slow_interpolation/noise/sources/fbm.py) — `FBMNoise`.
- [src/slow_interpolation/noise/sources/__init__.py](../../../../src/slow_interpolation/noise/sources/__init__.py).

File modified (only by adding):

- [src/slow_interpolation/noise/evolved_walk.py](../../../../src/slow_interpolation/noise/evolved_walk.py): `EvolvedNoiseWalk` now inherits from `NoiseSource`. No behavior change.
- [src/slow_interpolation/noise/__init__.py](../../../../src/slow_interpolation/noise/__init__.py): re-exports the new symbols.

### Phase B (done)

Files added:

- [src/slow_interpolation/noise/_filters.py](../../../../src/slow_interpolation/noise/_filters.py) — dependency-free separable Gaussian blur.
- [src/slow_interpolation/noise/image_derived.py](../../../../src/slow_interpolation/noise/image_derived.py) — `ImageDerivedNoise`. Defaults to a CPU path (resize + high-pass). Opt-in `use_vae=True` does a TAESD roundtrip on CUDA; silently falls back to CPU if torch/diffusers/CUDA are unavailable.
- [src/slow_interpolation/noise/frequency_banded.py](../../../../src/slow_interpolation/noise/frequency_banded.py) — `FrequencyBandedNoise`. Stacks N `WalkingNoiseSource` sub-sources at distinct frequency targets via per-band Gaussian sigmas and weights. The band stack itself owns the temporal walk.

### Phase C (done, GPU pass pending)

Files added:

- [src/slow_interpolation/noise/harness.py](../../../../src/slow_interpolation/noise/harness.py) — CLI harness. `--noise-set {structured, full}`, `--contact-sheet`, `--preview` (CPU only), `--image-ref`, `--frame-index`, `--seed`.

The CPU `--preview` mode is verified end-to-end on both presets (7 sources rendered to a contact-sheet PNG). The GPU rendering pass is pending and requires a config + LoRA in `models/loras/`.

### Tests

- [tests/test_noise_sources.py](../../../../tests/test_noise_sources.py): 49 tests covering interface compliance, drift behavior, shape-keyed restart, reset, blend_pct=0 identity, per-instance independence, and source-specific edge cases (Worley distance validation, FBM octaves validation, FrequencyBandedNoise type / length validation, ImageDerivedNoise static-texture invariant).
- All 49 pass on CPU. Combined with `test_evolved_walk.py` (6 tests, also green) the noise module is at 55 passing tests.

## Coordination

Per the file ownership matrix in [../../progress.md](../../progress.md):

- This workstream writes freely under `src/slow_interpolation/noise/sources/`, `src/slow_interpolation/noise/base.py`, `src/slow_interpolation/noise/_filters.py`, `src/slow_interpolation/noise/image_derived.py`, `src/slow_interpolation/noise/frequency_banded.py`, `src/slow_interpolation/noise/harness.py`, `docs/findings/noise-sources.md`, `tests/test_noise_sources.py`, and this doc.
- Modified only by adding (no behavior change): `src/slow_interpolation/noise/__init__.py`, `src/slow_interpolation/noise/evolved_walk.py`.

## Pending coordination requests

### 2. Promote interpolation-jitter finding to standalone doc? (FILED 2026-05-18)

Round 4 video review surfaced a **pipeline-wide artifact**: interpolation reads as chunks of pixels moving in coherent groups rather than as continuous painterly drift. The artifact correlates with off-distribution LoRA use (Renoir-on-fields, less so Renoir-on-still-lifes) and cuts across noise families. Hypothesis is RIFE-meets-loose-keyframes, not a noise property. Full writeup in [findings doc, "Interpolation jitteriness" section](../../../findings/noise-sources.md#interpolation-jitteriness-on-off-distribution-or-loose-keyframes).

The finding currently lives under the noise-sources findings doc because the noise workstream produced the observation. But the **mechanism is RIFE / Phase C / keyframe-similarity**, not noise. Other workstreams (compositing, future LoRA work, anchored live prompting) will run into the same artifact and would benefit from a direct reference.

**Request**: parent chat decides whether to extract this section into a standalone `docs/findings/interpolation-jitter.md` (or similar name). Either is fine from this workstream's perspective; the writeup is already canonical-form in noise-sources.md. If extracted, replace the section in noise-sources.md with a short pointer.

No urgency. Default lean: leave it in noise-sources.md until a second workstream needs to cite it; promote then.

### 1. ~~Wire a NoiseSource selector into the rendering loop~~ (CLOSED 2026-05-17)

**Parent chat closed this on 2026-05-17.** Schema landed as proposed:
`render.noise.kind` + `render.noise.params`, `walk_rate` inherited from
`RenderProfile.noise_walk_rate`. Factory `build_noise_source(config)` lives in
[src/slow_interpolation/noise/__init__.py](../../../../src/slow_interpolation/noise/__init__.py)
and supports the seven kinds (`evolved`, `perlin`, `worley`, `simplex`, `fbm`,
`image_derived`, `frequency_banded`). `Pipeline.generate_keyframes()` calls
the factory. The `frequency_banded` kind supports recursive sub-source specs
via `params.sources = [{kind, params}, ...]`. The harness can now point at a
YAML and run the production path end-to-end.

Original request, preserved for posterity:

The harness currently bypasses `Pipeline` and calls `keyframes.generate_keyframes`
directly with a `NoiseSource` instance (the call site already duck-types
`noise_walker.blend(img, blend_pct=...)`, so it works without changes). For
production renders to be able to pick a noise source per subject, we need:

- A `noise` field on `PipelineConfig` (or on `RenderProfile`) that names a
  source type and its parameters. Suggested shape:

  ```yaml
  render:
    profile: standard
    noise:
      kind: perlin
      params:
        feature_size: 64.0
      # walk_rate already lives on RenderProfile; reuse it for sources that
      # honour it (the WalkingNoiseSource family).
  ```

- A `build_noise_source(config)` factory (could live in
  `src/slow_interpolation/noise/__init__.py` so the workstream can write it)
  that returns a `NoiseSource` from the config.

- A change in `Pipeline.generate_keyframes()` (currently constructs
  `EvolvedNoiseWalk` directly) to call the factory instead.

The first two are inside this workstream's write set (I can add
`build_noise_source` here on request). The third is parent-chat territory.

**Status:** waiting on parent chat. I have not added the YAML field or the
factory yet because the schema is a coordination call; if the parent chat
prefers a different shape (e.g., noise as a sibling of `render` rather than a
child) I would rather know first. Default lean: child of `render`, kind +
params, with `walk_rate` inherited from the parent `RenderProfile`.

## Outstanding work in this workstream

1. ~~**GPU contact-sheet renders.**~~ **Done 2026-05-17.** Tcole_valley pass completed for all 7 sources, blur regression caught and fixed via `structural_decay_radius=0`, verdicts in findings doc.
2. **Spatial-frequency sweep, Modal Round 2.** Per the authorial-controls discovery, the meaningful next axis is noise mass size, not source identity. Concrete sweep slate:
   - `perlin` at `feature_size` in `{16, 24, 32, 48, 64}` (small to medium masses).
   - `worley` at `cell_density` in `{100, 300, 1000, 3000}/Mpx` (large to small cells).
   - One Renoir-tuned `frequency_banded` preset with high-frequency dominance (Worley at 3000/Mpx + Perlin at feature_size=16 + low-weight FBM).
   - All variants run against the same tcole_valley config first (sanity), then again against the first Renoir config when the LoRA lands.
   - Drop Simplex (deprecated).
3. **Banded presets, biased toward high-frequency Renoir grain.** Design 3 to 5 ready-to-use `FrequencyBandedNoise` stacks. **Default emphasis on the high-frequency band** (Worley high cell_density at 70-80% of weight) so they sit in the soft-motion regime; reserve a "landscape" preset that emphasises mid/low for explicitly bold-motion subjects. Add as named factories in the harness or as canned YAML in `outputs/_harness_configs/`.
4. ~~**Optional `--full-pipeline` flag for the harness.**~~ **Done 2026-05-17** (local only). Modal supersedes it for batches.
5. **YAML generator for Modal batch dispatch.** Small helper in this workstream's write set that turns a base config + a list of `(name, noise_kind, params)` into per-variant YAML files under `outputs/_harness_configs/<round>/`. Then `modal run -m cloud.batch --configs "<glob>"`. Pre-req for the parameter sweeps.
6. **Image_derived high_pass_sigma re-test.** Original at 16 bled reference content. Test 32 and 48 in the next round.
7. **Renoir LoRA renders.** Gated on the Renoir LoRA dataset workstream landing a usable LoRA checkpoint.

## Decisions log (workstream-local)

- **`WalkingNoiseSource` chosen as the shared base** (2026-05-16). The
  walk-and-renormalize pattern is the production semantics already used by
  `EvolvedNoiseWalk`; pulling it into a base class avoids re-implementing it
  in every structured source. `ImageDerivedNoise` is intentionally not a
  `WalkingNoiseSource` because its semantics are static-per-shape; it
  subclasses `NoiseSource` directly.
- **`FrequencyBandedNoise` requires `WalkingNoiseSource` sub-sources**
  (2026-05-16). The band stack accesses `_generate_fresh` on its sub-sources
  to bypass their per-source walk and pixel mapping. This is cleaner than
  trying to reconstruct band samples from per-source `blend` outputs.
  Documented in the class docstring.
- **No scipy dependency** (2026-05-16). The Gaussian blur for band
  decomposition is implemented in pure numpy (separable convolution) to
  avoid pulling scipy into the project. Roughly 30 lines, no measurable
  slowdown at the canvas sizes we use.
- **TAESD path in `ImageDerivedNoise` is opt-in** (2026-05-16). Default is
  pure-CPU resize plus optional high-pass residual. The VAE path is silently
  skipped if torch / diffusers / CUDA are unavailable, so the source remains
  test-friendly.
- **Seeded fresh sampling** (2026-05-16). Each structured source carries its
  own `np.random.default_rng` so `seed=` reproducibly fixes the noise
  pattern. The walk-and-renormalize loop is independent of the seed: setting
  seeds only fixes the per-frame fresh sample, not the diffusion process.
- **`structural_decay_radius=0` is the default for structured-noise renders**
  (2026-05-17). Structured noise cannot inject the high-frequency content
  that white noise inherently provides; `structural_decay` at radius 2
  therefore compounds blur across the chain. Setting it to 0 restores
  sharpness uniformly across all 5 affected sources (perlin, worley,
  simplex, fbm, frequency_banded). MP4 size jumps ~+30% vs the white-noise
  baseline; acceptable at 60s clip length. Reason: simpler fix than
  introducing a white_floor mix in the base class and easier to undo on a
  per-subject basis. Re-evaluate if 3-minute portrait runs show fine-texture
  runaway. See [`docs/findings/noise-sources.md`](../../../findings/noise-sources.md).
- **Simplex deprecated from production palette** (2026-05-17). SDXL Lightning
  output is visually indistinguishable from Perlin at the resolutions tested.
  Implementation stays in the codebase for interface completeness but is
  dropped from sweep slates. Reason: every Simplex render slot is better
  spent on a Perlin parameter variant or a banded preset.
- **Spatial frequency is the authorial dial, not source identity** (2026-05-17). Direct video review surfaced that the noise mass size controls perceived motion character: small masses (white noise, fine grain) give soft continuous evolution; big masses (Perlin blobs, Worley cells, FBM clouds) give coarse regional jumps. Mechanism: low-frequency noise pushes whole regions coherently each frame; high-frequency noise averages to zero across any region and only perturbs fine detail. **Practical consequence**: parameter sweeps should sweep `feature_size` (Perlin/Simplex/FBM) and `cell_density` (Worley) across an order of magnitude, not just compare different source kinds at default settings. Composition motion comes from prompt SLERP + img2img chain and is orthogonal to noise; noise picks the *texture register* of the motion. Documented in [`findings/noise-sources.md`](../../../findings/noise-sources.md) under "Authorial controls".
- **Long-running cloud jobs are dispatched in the background and monitored via auto-notification, never polled** (2026-05-17). The agent operating this workstream MUST follow [`docs/findings/monitoring-long-cloud-jobs.md`](../../../findings/monitoring-long-cloud-jobs.md) when dispatching Modal runs. Concrete rules: `run_in_background: true` on the Bash call; redirect stdout to `outputs/_harness_logs/<run>.log`; surface the Modal dashboard URL and log path to the user; stop polling. The first Round 2 dispatch failed because the bash glob expanded with Windows backslashes; the canonical fix (Python-built comma-separated forward-slash configs list, plus `PYTHONIOENCODING=utf-8 PYTHONUTF8=1`) is documented there.
- **Outdoor Renoir configs must append the anti-still-life negative prompt** (2026-05-18). Specifically: `vase, pot, container, table, indoor, still life` appended to the default Renoir negative `frame, vignette, panel, ornament, photograph, modern, sharp, photoreal`. The Renoir LoRA was trained on indoor bouquets and without this suppression it paints vase ghosts and tabletops into outdoor meadows. Verified across all 9 Round 4 variants; no still-life artifacts surfaced. **Canonical authoring rule for any non-bouquet Renoir subject.** Should be baked into a future `examples/configs/renoir/outdoor/` template directory when the parent chat is ready to expand the Renoir config family (coordination request to file when needed; not yet urgent).
- **Modal is the default WHEN local hardware is insufficient OR the parallelism is worth the cost** (2026-05-17, reframed 2026-05-18). The canonical routing protocol lives at [`../../../manual/hardware-routing.md`](../../../manual/hardware-routing.md): **local first**, Modal when the user's GPU is missing / underpowered / occupied, when a multi-variant batch is worth parallelism, or when reproducibility manifests are needed. The earlier "Modal cloud-render is the default for multi-variant tests" wording was correct in its 2026-05-17 context (Luca's local GPU was busy with other work) but is not universal. The workstream-local rationale still holds: parallel L40S fan-out collapses ~3 h sequential into ~25 min wall at ~$0.07 per render, and that economics is the right reason to choose Modal **once you have determined local is unsuitable or the batch is worth it**. The local harness is the right choice for CPU preview (`--preview`), one-off iteration loops where YAML round-trip cost dominates GPU time, and any render the local hardware can handle in acceptable time. Hardware-routing protocol decides; this finding tells you how to operate Modal once the protocol has routed you there.
