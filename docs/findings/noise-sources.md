# Noise sources as authoring surface

> **STATUS 2026-05-19: exploratory research, not a production recommendation.** The flagship + only validated noise source for slow-interpolation is `evolved` (the legacy walker). The six alternative sources documented below (Perlin, Worley, simplex, FBM, image-derived, frequency-banded) are experimental authoring tools that did not validate against `evolved` in production renders across any shipped LoRA family. They remain in the repo for researchers extending the technique; they are not peers of `evolved` in a production decision. The "spatial-frequency lever" framing below is the hypothesis we explored, not a confirmed tuning recommendation. For the operational protocol see [`../manual/noise.md`](../manual/noise.md), which leads with `evolved` as the default and reframes the alternatives as experimental.

# (Original research framing, retained for reference)

Findings doc for the Phase 3 noise-research workstream. The hypothesis is that
the small noise component blended into each img2img input (legacy: uniform
Gaussian, 8 percent steady, 15 percent transition) is doing more aesthetic work
than its size suggests. Substituting structured noise (Perlin, Worley, simplex,
FBM, image-derived, frequency-banded) for the production walker should produce
distinguishable micro-behaviors in the diffused output.

Status (2026-05-18, post Round 5): interface, all sources, harness, five render rounds, and the [comparison page](../../outputs/noise-tests/compare.html) Sections A through J all shipped. Two findings landed as load-bearing: the **spatial-frequency lever** (mass size drives motion softness, see [Authorial controls](#authorial-controls-the-spatial-frequency-lever)) and **fine-brushwork LoRAs need fine noise** (Cole, Casa del Suono, Renoir all share the high-frequency content register). Two open: **Round 5 motion-quality lever verdicts** (which value per lever becomes the new default) and **banded cell_density production lock** (cd=1000 vs cd=3000 visual equivalence test). Image_derived is paused (figure-bleed at sigma=32) but the technique is not deprecated. Active artifact under investigation: **interpolation jitteriness on off-distribution keyframes**, see the section by that name. Render-dispatch routing now follows [docs/manual/hardware-routing.md](../manual/hardware-routing.md); the in-text "next renders go on Modal" phrasings predate the routing protocol and read as historical narrative.

## Source catalogue

Quick reference. Each entry links to the file that implements it.

| Source | Recommended use | Default parameters | CPU cost (768x1344) | GPU | Notes |
|---|---|---|---|---|---|
| [EvolvedNoiseWalk](../../src/slow_interpolation/noise/evolved_walk.py) | Production baseline. Even, painterly, no spatial structure. | `walk_rate=0.05`, `blend_pct=0.08` | ~5 ms/frame | no | The legacy production setting. Reference for all comparisons. |
| [PerlinNoise](../../src/slow_interpolation/noise/sources/perlin.py) | Soft brushwork, broad colour patches. Floral candidates (petals, washes). | `feature_size=64`, `walk_rate=0.05` | ~25 ms/frame | no | Low spatial frequency. Try `feature_size` in {16, 32, 64, 128}. |
| [WorleyNoise](../../src/slow_interpolation/noise/sources/worley.py) | Petal cells, stamen clusters, anything with discrete repeating units. | `cell_density=300/Mpx`, `distance="euclidean"` | ~120 ms/frame | no | Dominant candidate for the Renoir florals. Try chebyshev for graphic geometry. |
| [SimplexNoise](../../src/slow_interpolation/noise/sources/simplex.py) | Similar to Perlin; potentially more flowing / less axis-aligned. | `feature_size=64`, `walk_rate=0.05` | ~40 ms/frame | no | If the diffusion model cannot distinguish Perlin from Simplex, drop Simplex. |
| [FBMNoise](../../src/slow_interpolation/noise/sources/fbm.py) | Atmospheric / cloud-like; landscape and broad-environment subjects. | `feature_size=128`, `octaves=4`, `persistence=0.5` | ~100 ms/frame | no | Multi-scale detail. The natural fit for After Cole horizontals. |
| [ImageDerivedNoise](../../src/slow_interpolation/noise/image_derived.py) | Bias the generation toward a reference texture without prompting it. | CPU mode, `high_pass_sigma=16` | one-time per shape | optional (TAESD) | Static per-shape texture. Combine with structured bands via `FrequencyBandedNoise` for temporal life. |
| [FrequencyBandedNoise](../../src/slow_interpolation/noise/frequency_banded.py) | Coarse motion + fine motion controlled independently. | N sub-sources, `band_sigmas`, `band_weights` | sum of sub-source costs | no | The composition layer. Sub-sources must be `WalkingNoiseSource` instances. |

Costs are rough CPU measurements with numpy on a single thread; the
implementations are vectorized but not threaded. For 768x1344 frames and a
26-frame After Cole render the noise stage adds at most ~3 seconds; for the
~60-frame portrait it adds ~7 seconds. Negligible next to the SDXL pass.

## Authorial controls: the spatial-frequency lever

Surfaced from direct video observation on 2026-05-17 (Luca's review of the seven tcole_valley renders). This is the most important authorial insight from the first render pass: the noise source's spatial frequency, not its identity, controls how the scene moves between frames.

### The observation

Watching the seven diffused MP4s side by side, two sources produce **soft, continuous scene drift** (evolved_walk, image_derived). The other five produce **coarser, jumpier regional shifts** (perlin, worley, simplex, fbm, frequency_banded). The visible noise pattern in each source's raw video correlates directly: the soft-motion sources have **small noise masses** (per-pixel sparkle or fine grain), the coarse-motion sources have **bigger noise masses** (blobs, cells, multi-scale clouds).

### Why this happens

The img2img blend is `input = previous_frame * (1 - blend_pct) + noise_tensor * blend_pct`. What the model encodes and denoises is the resulting input.

- **High-spatial-frequency noise** (white noise, fine grain): each pixel's perturbation is uncorrelated with its neighbours. Across any region, the per-pixel offsets average to approximately zero. The local mean of the image barely shifts. The model reads this as "uniform fine refinement" and produces continuous evolution.
- **Low-spatial-frequency noise** (Perlin blobs, Worley cells, FBM clouds): pixels within a single blob all push in the same direction. Whole regions of the image shift coherently. The model reads this as "this region has moved" and refines toward a new local solution. Different regions push on different frames, so successive keyframes carry visible regional jumps. RIFE then smooths between them, but the underlying motion is regional rather than uniform.

### The authorial dial

Spatial frequency is a continuous knob with a clean mapping to perceived motion character:

| You want... | Set the noise toward... | How |
|---|---|---|
| Maximum continuity, breath-like drift | High spatial frequency (small masses) | `evolved_walk`, or perlin / simplex / fbm with **small `feature_size`** (16 to 32), or worley with **high `cell_density`** (1000+/Mpx) |
| Bold compositional shifts between segments | Low spatial frequency (big masses) | Perlin / simplex / fbm with **large `feature_size`** (128+), worley with **low `cell_density`** (50 to 100/Mpx) |
| Consistent, photograph-like texture | Static high-frequency residual | `image_derived` with `high_pass_sigma=32-48` (32 or 48 to strip composition, keep grain) |

### Trade-off: motion softness vs texture life

These two qualities are partly in tension:

- High-frequency noise gives **soft motion** but also **constant fine-texture refresh** (texture "lives" frame to frame, no two frames look identical at the pixel level).
- Static high-frequency noise (image_derived) gives **soft motion AND stable texture** (composition drifts gently, fine detail stays consistent).
- Low-frequency noise gives **regional motion** but also **regional texture refresh** (texture changes by region rather than per-pixel, which can read as more "rendered" or more "painterly" depending on the LoRA).

### Independent axis: composition motion comes from elsewhere

Critically, **noise is not the primary driver of scene change**. The prompt SLERP transitions (A to B to C to A), the per-position cycling denoise strengths, and the recursive img2img chain all produce composition motion independently. The noise source modulates *how* that motion reads: gradual continuous evolution vs region-by-region jumps. To control composition motion itself, the levers are:

- Prompt semantic distance (how different A, B, C are from each other).
- Transition strength (`render.transition_strength`, defaults to 0.65).
- Transition frame count (`frames.transition`, defaults to 3 in horizontal).
- Steady frame count (`frames.steady`, defaults to 5 in horizontal): more steady frames mean the scene dwells longer before moving.

The noise source dial is orthogonal: pick the spatial-frequency register that suits the subject, then tune composition motion separately. This orthogonality is the most useful thing to know when authoring future subjects.

### Generalization: fine-brushwork LoRAs need fine noise

Stated 2026-05-17 after Round 2 review. The LoRAs in this project's stable each carry a fine-spatial-frequency content register: Thomas Cole (Hudson River School, dense atmospheric detail), Casa del Suono fresco (plaster grain and pigment stipple), and presumably Renoir (impressionist dabs). They share a property: **the LoRA's strokes are small and densely packed across the canvas**.

When a noise source's spatial register matches the LoRA's content register, they cooperate: the noise's high-frequency perturbations feed the LoRA's stroke-scale denoising decisions. When the noise register is much lower than the LoRA's (big Perlin blobs, big Worley cells on a fine-brush LoRA), the noise pushes whole compositional regions while the LoRA still tries to render fine strokes inside each region. The LoRA wins on visual quality (strokes are preserved) but the noise contributes nothing useful: it just adds compositional restlessness that fights the brushwork.

Practical consequence: **all three of our active LoRAs are fine-noise subjects.** The production palette for any of them should sit on the high-spatial-frequency end of the dial. The Round 2 sweep on the Cole LoRA validates this empirically and the same prediction should hold for Renoir (Round 3 will test it).

### Implications for the Renoir release

Renoir's brushwork is itself a high-spatial-frequency texture: short, dense strokes covering the whole canvas. The noise source should match:

- **First choice**: `image_derived` with a Renoir reference and `high_pass_sigma=32-48`. Stable Renoir grain every frame, soft composition motion.
- **Second choice**: `evolved_walk` (the production baseline). Soft motion, fine sparkle, but with white-noise texture refresh rather than Renoir-grained refresh.
- **Probably wrong for Renoir**: Perlin / Worley / FBM at default `feature_size`. The big-mass regional shifts will fight Renoir's even brushwork, producing motion that reads as "compositional jumps" rather than "petals trembling".
- **Worth testing**: a `frequency_banded` stack with **high-frequency Worley** at small cell scale (~2000/Mpx, producing small cell sizes that approximate Renoir petal grain), Perlin at medium frequency, FBM at low. This explicitly composes a Renoir-like texture grammar.

The parameter sweeps in the next Modal round should center on `feature_size` and `cell_density` rather than swapping sources, because the source family is now well-mapped: the question is *where on the spatial-frequency axis* each subject sits, not *which abstract pattern is best*.

## Interface

```python
class NoiseSource(ABC):
    def reset(self) -> None: ...
    def blend(self, img: PIL.Image.Image, blend_pct: float) -> PIL.Image.Image: ...
```

`reset()` drops persistent state. `blend()` returns the input image alpha-
blended with the source's noise tensor. The same interface fits the legacy
`EvolvedNoiseWalk` (which already satisfied this shape) and every new source.

Two layers of implementation help:

- `NoiseSource` is the bare interface. Used directly when the source's
  semantics are non-standard, like `ImageDerivedNoise` (static texture cached
  per shape, no temporal walk).
- `WalkingNoiseSource` is a concrete base that implements the production walk-
  and-renormalize pattern. Subclasses provide `_generate_fresh(shape)`
  returning a unit-variance ndarray. All four structured sources and
  `FrequencyBandedNoise` use this.

## How each source reads (a priori expectations, to be validated against GPU renders)

These are predictions to test, not findings. The harness will tell us whether
the diffusion model actually distinguishes them.

- **Evolved walk.** White-noise spectrum. The model gets dense per-pixel
  perturbations and tends to reinvent fine texture at every frame, restrained
  by the walk's temporal persistence. This is the baseline; everything else is
  judged relative to it.
- **Perlin.** Low-frequency blobs. Should push the model toward larger
  coherent colour regions, less fine texture chase. Hypothesis: reads as
  softer brushwork, more "wash" than "stippling". A natural test on Renoir
  bouquets (which is what Renoir's brushwork already does).
- **Worley.** Cell-bounded basins. Should produce textures organized around
  discrete units. Hypothesis: petals, anther clusters, scaled-leaf textures
  in Renoir; pebbled rock or canopy texture in landscape. Possibly the
  highest-value structured source for floral subjects.
- **Simplex.** Like Perlin but on a triangular lattice. The visual
  differences from Perlin are subtle; the diffusion model may or may not
  read them as different. If indistinguishable from Perlin in the contact
  sheet, drop simplex from the production palette.
- **FBM.** Self-similar across scales. Should give detail at multiple
  spatial frequencies simultaneously, the closest analogue to natural cloud
  / foliage / weathering texture. Hypothesis: best fit for After Cole
  landscapes and any Renoir subject that includes broader environmental
  drift.
- **Image-derived.** Bias the generation toward a specific reference's
  texture. Two intended uses: (a) carry a photograph's grain into a fresco-
  styled generation, (b) reuse one render's texture as the noise for the
  next. The reference image's content is *not* expected to bleed through;
  only its high-frequency statistics enter the denoising loop.
- **Frequency-banded.** Compose any of the above at different frequency
  registers. Coarse: large-scale motion direction. Mid: regional drift.
  Fine: per-petal / per-flake texture. Hypothesis: this is where the
  technique actually lives. The single-source choices above are calibration
  steps; the production palette will be banded mixes.

## Comparison harness

CLI:

```
python -m slow_interpolation.noise.harness <config.yaml> --noise-set structured
python -m slow_interpolation.noise.harness <config.yaml> --noise-set full \
    --image-ref path/to/reference.jpg --contact-sheet
python -m slow_interpolation.noise.harness <config.yaml> --preview
```

Modes:

- Default: render the keyframes for the config's subject once per source.
  Outputs land at `outputs/staging/<subject>_<source>/keyframes/`. SDXL is
  loaded once and reused across sources.
- `--contact-sheet`: after rendering, compose a horizontal contact sheet
  PNG of the Nth keyframe (default 0, the first A frame) across all sources.
- `--preview`: CPU-only. Render each source's raw noise pattern (no
  diffusion) and write a contact sheet of the noise itself. Use this when
  adding a new preset entry, before burning GPU time on full renders.

Presets:

- `structured`: `evolved_walk, perlin, worley, simplex, fbm`.
- `full`: `structured + image_derived + frequency_banded`. Requires
  `--image-ref` for the image-derived source.

The harness is not part of the production Pipeline. Treat it as a research
tool. Once a noise-source choice is locked for a release, re-render the
selected source through the production CLI (`python -m slow_interpolation.run
...`) for the full Phase A.5 + C + D path.

## First render pass: tcole_valley, full preset (2026-05-17)

Full pipeline rendered for all 7 sources against `examples/configs/tcole_valley.yaml` with image_derived referencing `outputs/staging/tcole_valley/keyframes/0010.png` (mid-sequence frame from the prior tcole_valley render; closed-loop probe). Total wall time ~3 hours. MP4s landed at `outputs/tcole_valley_<source>.mp4`.

### Quantitative signal: MP4 size as a temporal-variance proxy

At a fixed CRF (~23), per-frame variance translates almost linearly to encoded size. The seven outputs split cleanly:

| Source | MP4 size | Relative to baseline |
|---|---|---|
| evolved_walk (baseline) | 7.0 MB | 100% |
| image_derived | 5.5 MB | 79% |
| simplex | 4.8 MB | 69% |
| worley | 4.6 MB | 66% |
| perlin | 4.5 MB | 64% |
| fbm | 4.5 MB | 64% |
| frequency_banded | 4.5 MB | 64% |

The structured sources cluster ~30% smaller than the white-noise baseline. This is the temporal-coherence hypothesis confirmed quantitatively: spatial structure in the noise means the model reinvents less fine texture between frames. image_derived sits between because its static high-frequency residual still carries enough fine detail to push variance up.

### Spatial signature at frame 12 (preliminary, single-frame)

Contact sheet at [outputs/staging/tcole_valley_grid_frame12.png](../../outputs/staging/tcole_valley_grid_frame12.png). One-frame observations only; the temporal signature is the actual research question and lives in the MP4s.

- **evolved_walk.** Densest foreground foliage texture. Single dominant arch. The baseline.
- **perlin.** Multiple arches, dramatic dawn-pink sky, warmer palette overall. Hypothesis matches: coarse blobs push the model toward broader colour regions and more dramatic gradient skies.
- **worley.** Two stacked arches centered, lighter palette, lots of visible distance. Reads cleanly as a Cole composition.
- **simplex.** Subtle differences vs perlin in this single frame. Verdict on whether SDXL distinguishes Perlin from Simplex needs comparison of the videos and more renders.
- **fbm.** Multiple receding arches with rich mid-ground detail. Atmospheric depth.
- **image_derived.** Composition diverged most from the others: dense ruined structures, no dominant arch, more bridge-like ruins. The reference frame's foreground content bled through the high-pass at sigma=16; the high_pass_sigma is not aggressive enough for "texture only" biasing. Raise to 32 or 48 on the next pass for a cleaner separation.
- **frequency_banded.** Single very wide arch framing a panoramic vista. The cleanest "Cole canonical" composition of the seven.

### Notes on what the noise actually does

The expectation going in was "noise as texture overlay". The actual finding from frame 12 is that **noise is a composition seeder**, not just a texture modulator. Different noise sources push the model toward different scene structures from the very first VAE encoding. This is more powerful than expected and has two consequences:

1. **Source choice is a compositional decision**, not just a finish-pass decision. Locking a single source per Renoir subject is the right unit of authoring.
2. **Cross-source A/B comparisons need either a fixed first-frame seed or many-render averaging**, because each source produces a different scene realization from the same prompt. The frame-12 observations above are samples of N=1 per source.

### Verdicts pending

Watch the seven MP4s in `outputs/tcole_valley_<source>.mp4` and answer:
- Does the texture breathe coherently or flicker, per source?
- Which sources read most "Cole-canonical" in motion (not just at frame 12)?
- For Renoir, which spatial register most resembles Renoir's brushwork?

### Blur bug in five structured sources (2026-05-17)

Luca's review of the seven MP4s: evolved_walk and image_derived are crisp; perlin, worley, simplex, fbm, and frequency_banded are progressively blurry. Side-by-side video frames at [outputs/staging/video_frame700_crops.png](../../outputs/staging/video_frame700_crops.png) and [outputs/staging/perlin_early_vs_late.png](../../outputs/staging/perlin_early_vs_late.png) confirm:

- Per-source comparison at frame 700: evolved_walk holds brick texture, perlin / worley / fbm have soft mushy surfaces.
- Within-source comparison for perlin (frame 50 vs frame 1300): frame 50 is sharp, frame 1300 is severely smeared. **The blur accumulates across the chain.**

#### Root cause

The img2img loop in [keyframes.py](../../src/slow_interpolation/keyframes.py) runs:

```
input = structural_decay(previous_frame, radius=2)   # Gaussian blur, removes high freq
input = noise_walker.blend(input, blend_pct=0.08)    # add noise tensor
output = SDXL_img2img(input, strength)
```

The legacy white-noise walker injects per-pixel Gaussian content, which restores the high-frequency energy that `structural_decay` removed. The two operations balance and the chain stays crisp.

Structured noise (Perlin, Worley, Simplex, FBM) has its energy concentrated at low spatial frequencies. Replacing the white-noise injection with structured noise breaks the balance: `structural_decay` keeps removing high frequencies, nothing replaces them, the chain progressively low-passes itself. By frame 1300 the model is refining a Gaussian smear.

Image_derived is unaffected because its high-pass residual carries fine texture from the reference image, which serves the same injection role as white noise. Evolved_walk is unaffected because it IS the white-noise injection.

#### Fix options

| Option | What it does | Edit footprint | Re-render cost | Risk |
|---|---|---|---|---|
| **A. Disable `structural_decay`** for structured-noise renders. Override `render.structural_decay_radius: 0` in YAML or CLI. | Config-only. No code change. | One CLI flag on the harness (`--structural-decay-radius`) or one YAML override file. | ~30 min per source. | Loses the structural-decay safety net entirely. May allow fine-texture runaway in the white-noise component of compound sources (frequency_banded). |
| **B. White-noise floor** in `WalkingNoiseSource`. Mix Gaussian per-pixel noise into every fresh sample at e.g., 50% weight. Inject high-freq energy while preserving the low-freq signature. | One class edit ([base.py](../../src/slow_interpolation/noise/base.py)). Backward-compatible with `white_floor=0.0` default. | One parameter, ~10 lines. | ~3 hours for 5 affected sources. | Dilutes the structured signature. The "pure perlin" / "pure worley" aesthetic becomes "perlin + half white noise". May or may not be what we want artistically. |
| **C. A + B combined.** Disable structural_decay AND add a small white-noise floor. | Both. | Both. | Same as B. | Most robust but the variables are mixed. |
| **D. Accept and document.** Treat the progressive blur as a property of structured noise. Possibly artistically valid as "the world softens over time". | None. | None. | None. | Wastes the implementation work for the intended use case. Probably wrong call here. |

#### Decision (2026-05-17)

Proceeding with **Option A as a diagnostic**: re-render perlin (the cleanest single-source test) with `structural_decay_radius=0`, keep everything else equal. If the resulting video stays crisp from frame 50 through frame 1300, the fix is configuration-only and applies to all five affected sources via a single YAML override. If perlin still blurs, escalate to Option B (`white_floor` parameter in the base class).

#### Verdict on Option A (2026-05-17)

**Option A is sufficient. Option B not needed.**

Evidence at [outputs/staging/perlin_fix_comparison.png](../../outputs/staging/perlin_fix_comparison.png) and [outputs/staging/perlin_no_decay_early_vs_late.png](../../outputs/staging/perlin_no_decay_early_vs_late.png):

- Perlin with `structural_decay_radius=0` is sharp at frame 50 and equally sharp at frame 1300. The chain no longer accumulates blur. Brick texture, distant mountains and fine foliage all read cleanly.
- Side by side at frame 700: no_decay perlin is back to Cole-quality sharpness, comparable to the evolved_walk baseline. The composition still carries perlin's signature (broader colour regions, more atmospheric sky) but the resolution of detail is preserved.

MP4 sizes corroborate:

| Variant | MP4 size | Reading |
|---|---|---|
| evolved_walk (baseline) | 7.0 MB | reference |
| perlin (original, with structural_decay=2) | 4.5 MB | high freq lost, low temporal variance |
| **perlin (no_decay, structural_decay=0)** | **9.1 MB** | high freq fully preserved, slightly above baseline |

The +30% over the white-noise baseline indicates the no_decay path runs slightly hotter on fine detail than the legacy chain. Not a problem at this clip length (~60s). Worth watching for fine-texture runaway in longer subjects (3-minute portrait sessions). Mitigation if needed later: re-introduce a much smaller structural_decay (radius 1 instead of 2), or apply Option B (white_floor) at a low weight to add controlled high-freq injection without disabling the legacy mechanism entirely.

#### Re-rendering the other four affected sources

Worley, Simplex, FBM, and frequency_banded all share the same root cause and the same fix. Re-rendered with `structural_decay_radius=0` and `--output-suffix no_decay` so the originals stay around for the before/after record.

#### Full verdict across all 5 affected sources (2026-05-17)

Side-by-side at frame 700: [outputs/staging/before_after_no_decay_all5.png](../../outputs/staging/before_after_no_decay_all5.png). The fix holds uniformly. Every "no_decay" image reads visibly sharper than its blurry original.

| Source | Original size | No_decay size | Delta vs baseline (7.0 MB) |
|---|---|---|---|
| perlin | 4.5 MB | 9.1 MB | +30% |
| worley | 4.6 MB | 8.9 MB | +27% |
| simplex | 4.8 MB | 9.7 MB | +39% |
| fbm | 4.5 MB | 8.0 MB | +14% |
| frequency_banded | 4.5 MB | 9.3 MB | +33% |

All five sit ~14 to 39% above the evolved_walk baseline (7.0 MB), confirming the no_decay path runs slightly hotter on fine detail than the legacy chain. Fine at 60-second loop length. Worth monitoring for fine-texture runaway in 3-minute portrait subjects.

#### Per-source aesthetic reads from the fixed renders

Single-frame observation at frame 700 + video review across the full clip. Revised 2026-05-17 after the spatial-frequency-lever discovery (see [Authorial controls](#authorial-controls-the-spatial-frequency-lever) above).

- **Evolved_walk.** Per-pixel white noise. Small noise masses. **Soft, continuous scene motion.** The baseline, and confirmed in video review as one of the two softest-motion sources. Production default for good reason.
- **Image_derived.** Static high-frequency reference grain. **Soft scene motion + stable texture.** The other soft-motion source. Best when you want a real image's texture grammar carried through the chain with minimal flutter.
- **Perlin.** Broader colour regions, soft regional drift in stills, **but the regional drift reads as coarser motion in video** (whole regions push together each frame). Confirms the spatial-frequency hypothesis. To use with Renoir: drop `feature_size` from 64 to 16-24 so the masses shrink toward Renoir-petal scale.
- **Worley.** Drama. Single dominant arch, sharp clouds, atmospheric depth. **Coarse regional motion** in video (whole cell-regions evolve together). Cell-bounded mass character useful where the subject has discrete repeating units; the regional shift may or may not be desirable depending on subject.
- **Simplex.** Visually very close to Perlin in the diffused output AND in motion character. The triangular-lattice difference is below SDXL Lightning's perceptual threshold at this resolution and prompt. **Recommend deprecating Simplex from the production palette in favour of Perlin.**
- **FBM.** Richest multi-scale detail. **Coarsest regional motion** of the five (multi-scale low-frequency content -> biggest mass jumps frame to frame). Natural fit for landscape and atmospheric subjects where bold regional evolution is the intent, but the masses fight Renoir-style fine-texture subjects.
- **Frequency_banded.** Compound source (Worley + Perlin + FBM stacked). The motion character is dominated by whichever band carries the most weight. The current default stack favours mid frequencies, which produces medium-coarse motion. **A Renoir-tuned banded preset would emphasise the high-frequency band (Worley at high cell_density, low band_weight on FBM)** to land back in the soft-motion regime while keeping Renoir-petal grain.

#### Open recommendations carrying into the next round

1. **Default for structured-noise renders: set `structural_decay_radius=0` in the YAML.** The fix is configuration-only; no code change. Document this as part of the noise-source presets when we lock the production palette.
2. **Drop Simplex from the production palette.** Keep the implementation (Phase A interface compliance) but stop testing it as a distinct option. Saves a render slot in every sweep.
3. **Image_derived high_pass_sigma=16 is too low.** Reference content bled into the first render. Raise to 32 or 48 for the next test. (Already noted in earlier section; carrying forward.)
4. **Watch fine-texture runaway in longer subjects.** The no_decay path runs ~30% above legacy variance. At 60s clip length: invisible. At 3-min portrait: unknown. Mitigation if it appears: re-introduce a smaller structural_decay (radius 1 instead of 2) or apply Option B's white_floor at low weight (~0.2).
5. **Future render dispatch follows the hardware-routing protocol** at [docs/manual/hardware-routing.md](../manual/hardware-routing.md): local first, Modal `cloud/batch.py` when local is insufficient or the parallelism is worth the cost. Multi-variant noise sweeps are usually a Modal case (3 h sequential local vs 25 min parallel L40S), but the routing protocol is the gate. Reframed 2026-05-18; earlier text in this doc that says "next renders go on Modal" reflects the workstream's then-default and is historical narrative.
6. **Worley scales O(H × W × n_points) per kernel call. Budget accordingly.** Surfaced from Round 2 cost data: Worley at `cell_density=3000/Mpx` cost $1.41 per render and ran ~43 min wall (vs $0.04 / 80 s for any Perlin variant). The `dx[..., None] - px` broadcast in `worley_2d` allocates an `(H, W, n_points)` float32 tensor per channel per frame. At 1344x768 with 3000 points × 3 channels × 26 keyframes the arithmetic is dominated by this single operation. Mitigations for future sweeps: (a) test Worley at lower densities first, (b) use a kd-tree implementation if we sweep dense Worley regularly, (c) avoid stacking dense Worley inside a `FrequencyBandedNoise` (the banded preset using `cd=3000` cost $1.19, same root cause). Affects research budget planning, not authoring choices.
7. **Reframe the next sweep around spatial frequency, not source identity.** Per the authorial-controls section above, the meaningful dial is the noise mass size. The Modal Round 2 sweep should be: (a) Perlin at `feature_size` in `{16, 24, 32, 48, 64}`, (b) Worley at `cell_density` in `{100, 300, 1000, 3000}/Mpx`, (c) a Renoir-tuned `frequency_banded` preset with high-frequency dominance. Five to seven variants total. This grid will localise where on the spatial-frequency axis each Cole / Renoir subject lives.

## Round 2 render pass: spatial-frequency sweep on Modal (2026-05-17)

Nine variants dispatched in parallel against `examples/configs/tcole_valley.yaml`, all with `structural_decay_radius=0`, all on the Cole LoRA. Goal: operationalise the spatial-frequency-lever hypothesis from "Authorial controls" by sweeping the underlying parameter rather than the source kind. First Modal batch dispatch from this workstream.

Configs at `outputs/_harness_configs/round-2-spatial-freq-cole/`. Outputs at `outputs/noise-tests/round-2-spatial-freq-cole/`. Comparison page at `outputs/noise-tests/compare.html` Sections C and D.

### Sweep slate + cost

| Variant | Source | Spatial-freq parameter | Wall time | Cost (USD) |
|---|---|---|---|---|
| `r2_perlin_fs16` | Perlin | feature_size=16 (smallest masses) | 84 s | 0.05 |
| `r2_perlin_fs24` | Perlin | feature_size=24 | 82 s | 0.04 |
| `r2_perlin_fs32` | Perlin | feature_size=32 | 80 s | 0.04 |
| `r2_perlin_fs48` | Perlin | feature_size=48 | 89 s | 0.05 |
| `r2_perlin_fs64` | Perlin | feature_size=64 (default) | 86 s | 0.05 |
| `r2_worley_cd300` | Worley | cell_density=300 (default) | 306 s | 0.17 |
| `r2_worley_cd1000` | Worley | cell_density=1000 | 753 s | 0.41 |
| `r2_worley_cd3000` | Worley | cell_density=3000 (smallest cells) | 2605 s | 1.41 |
| `r2_banded_renoir_tuned` | Frequency-banded | Worley 3000 + Perlin 16 + low-weight FBM | 2204 s | 1.19 |
| | | **Batch wall (parallel)** | **2618 s (~43 min)** | |
| | | **Batch total** | | **3.40** |

Cost estimate was $0.63; actual was $3.40. Overshoot is entirely on Worley high-density variants and the banded variant (which uses Worley internally). See open-recommendation #6 above for the root cause.

### Verdicts pending

Watch the 9 MP4s in `outputs/noise-tests/round-2-spatial-freq-cole/` (Section C of [compare.html](../../outputs/noise-tests/compare.html)). Specifically: does the Perlin row show progressively softer motion as `feature_size` decreases? Does the Worley row show the same? Does the banded variant sit firmly in the soft-motion regime as designed? Verdicts get added below.

## Round 3 design: Renoir noise palette (queued 2026-05-17)

Triggered by the Renoir LoRA arrival at `models/loras/Renoir_Flowers_epoch_{1,5,10}.safetensors`. Luca's authorial decision after Round 2 review (2026-05-17): test only the **three soft-motion noise sources** against the Renoir LoRA, on the rationale that fine-brushwork LoRAs (Cole, fresco, Renoir) all need fine noise to read well (see "Generalization: fine-brushwork LoRAs need fine noise" above).

### Sweep slate (3 variants)

| Variant | Source | Rationale |
|---|---|---|
| `r3_renoir_evolved_walk` | EvolvedNoiseWalk | The production baseline. White noise sparkle, soft continuous motion. Anchors the comparison. |
| `r3_renoir_image_derived` | ImageDerivedNoise | A real Renoir painting fed in as the noise tensor. Carries the actual Renoir grain into the chain, biased toward the reference's brushwork statistics. Reference image: `datasets/renoir-flowers/raw/auguste-renoir-bouquet-de-narcisses-et-de-roses-ppp4825-mus-e-des-beaux-arts-de-la-ville-de-paris.jpg`. Use `high_pass_sigma=32` (raised from the default 16 per Round 1's reference-content-bleed observation). |
| `r3_renoir_banded_renoir_tuned` | FrequencyBandedNoise | The compound recipe designed for Renoir in the "Implications for the Renoir release" section: Worley cd=3000 (50%) + Perlin fs=16 (40%) + low-weight FBM (10%). Same recipe as Round 2's `r2_banded_renoir_tuned`; now tested against the LoRA it was designed for. |

### Subject and budget

- **Starting subject**: `roses_vase_60s.yaml` (the canonical Renoir test subject per the renoir-configs README).
- **Budget projected**: 3 × (evolved $0.05 + image_derived $0.05 + banded $1.19) ≈ $1.30 for one subject. Adding more subjects multiplies linearly; the banded variant is the dominant cost due to dense Worley.
- **Optional extensions** if Round 3 results are clear: re-run the same 3-noise palette against `peony_closeup_portrait_60s.yaml` (portrait orientation, fine close-up brushwork) and `anemones_60s.yaml` (multi-colour cluster, off-distribution).

### Round 3 actuals (completed 2026-05-18)

After a first-attempt failure caused by a path-mount issue (image_derived's reference image lived at `datasets/renoir-flowers/raw/...` which Modal does not mount; the cascade also stopped banded mid-run, see [monitoring playbook](monitoring-long-cloud-jobs.md)), the retry succeeded with the reference relocated to `examples/references/renoir/bouquet-narcisses-roses.jpg`.

| Variant | Wall time | Cost (USD) | Notes |
|---|---|---|---|
| `r3_evolved_walk` | ~80 s | 0.05 | succeeded on first attempt; not re-run on retry |
| `r3_image_derived` | 80 s | 0.04 | retry only; reference relocated |
| `r3_banded_renoir_tuned` | 2584 s | 1.40 | retry only; same dense-Worley cost as Round 2's banded variant |
| | **Round 3 total** | **~$1.49** | first attempt added ~$0.30 of wasted GPU on the stopped banded render |

Outputs at `outputs/noise-tests/round-3-renoir-palette/{evolved_walk,image_derived,banded_renoir_tuned}.mp4`. Integrated as Sections E and F of [compare.html](../../outputs/noise-tests/compare.html). Raw-noise companion videos at `outputs/noise-tests/round-3-renoir-palette/raw-noise/`.

### Verdicts (after Luca review)

Add per-variant observations here after the videos are watched. Three questions to answer:

1. **Soft-motion verdict.** Do evolved_walk, image_derived, and banded all sit in the soft-motion regime on Renoir as they did on Cole? If yes, the spatial-frequency-lever finding generalizes across LoRAs.
2. **Image-derived verdict.** Does the real-Renoir reference push the diffused output toward more authentic brushwork than evolved_walk, or does it bleed reference content (the failure mode flagged in Round 1)? `high_pass_sigma=32` was chosen to suppress structural bleed; the artistic test is whether it kept enough texture to be useful.
3. **Banded verdict.** Does the recipe designed for Renoir actually deliver the petal-grain reading we designed it for? Specifically: petal-bound texture units (from Worley high-freq), soft inter-petal wash (from Perlin small-feature-size), atmospheric base (from low-weight FBM). If yes, this is the production candidate for the objkt labs release.

### What this round tests

Two questions in one batch:

1. **Does the spatial-frequency-lever finding hold across LoRAs?** If the three soft-motion sources produce visibly soft scene motion on Renoir (same as they did on Cole), the finding generalizes and we have a defensible production palette.
2. **Does the Renoir-tuned banded recipe deliver the petal-grain reading we designed it for?** The recipe was constructed against Renoir's brushwork vocabulary but only tested on Cole. This is the artistic test.

Verdicts go in this section after the render lands.

## Round 4: Renoir outdoor field subjects (2026-05-18)

Dispatched after Round 3 confirmed the Renoir LoRA renders cleanly on still-life subjects. Round 4 tests **off-distribution behaviour**: outdoor fields and meadows, which the LoRA was not trained on. The objkt labs release content per Luca's project plan is grass and floral fields rather than potted plants, so this round is closer to the production target than Round 3 was.

### Slate (9 variants)

Three field subjects, each rendered with the same 3-source soft-motion palette from Round 3:

- `renoir_wildflower_meadow` (broad meadow of mixed wildflowers in tall grass)
- `renoir_poppy_field_path` (narrow grass path through poppies)
- `renoir_garden_corner` (corner of a flowering garden with a stone wall)

Configs at `outputs/_harness_configs/round-4-renoir-fields/`. Outputs at `outputs/noise-tests/round-4-renoir-fields/`. Integrated as Sections G + H of [compare.html](../../outputs/noise-tests/compare.html).

### Construction choices specific to Round 4

- **Anti-still-life negative prompt** appended (`vase, pot, container, table, indoor, still life`) so the LoRA's training bias does not paint bouquets into outdoor scenes.
- **`image_derived` reference replaced** with `examples/references/renoir/girls-picking-flowers-meadow.jpg` (Renoir's *Girls Picking Flowers in a Meadow*, c. 1890), an outdoor Renoir whose texture matches the target subjects. `high_pass_sigma=32` retained.
- **Same banded recipe** as Rounds 2 and 3: Worley cd=3000 (50%) + Perlin fs=16 (40%) + low-weight FBM. The recipe is now under cross-subject and cross-distribution test.
- `structural_decay_radius=0` everywhere.

### Round 4 actuals

| Variant | Wall (s) | Cost (USD) |
|---|---|---|
| meadow / evolved_walk | 77 | 0.04 |
| meadow / image_derived | 82 | 0.04 |
| meadow / banded | 1401 | 0.76 |
| poppyfield / evolved_walk | 70 | 0.04 |
| poppyfield / image_derived | 74 | 0.04 |
| poppyfield / banded | 1469 | 0.80 |
| garden / evolved_walk | 75 | 0.04 |
| garden / image_derived | 66 | 0.04 |
| garden / banded | 2183 | 1.18 |
| **Batch wall (parallel)** | **2189 (~36 min)** | |
| **Batch total** | | **$2.98** |

Two of the three banded variants were ~40% cheaper than Round 2/3's banded (~$0.80 vs ~$1.40). Likely cause: warmer Modal containers or less render-queue contention on this batch. Cost prediction was $4.50; actual was $2.98.

### Round 4 verdicts (preliminary, from Luca review 2026-05-18)

Three concrete observations from the first video review. Each carries forward into either a finding update or an open question.

1. **`image_derived` reference is bleeding figures through despite `high_pass_sigma=32`.** The Round 4 reference (Renoir's *Girls Picking Flowers in a Meadow*) contains two human figures. The Gaussian high-pass at sigma=32 was chosen to strip low-frequency structure, but the figures' silhouettes are coarse enough to survive that filter and emerge in the diffused output as ghost figures in the fields. This extends the Round 1 finding ("high_pass_sigma=16 bleeds content") into **Round 4 finding: high_pass_sigma=32 is also insufficient for figure-bearing references.** Mitigations to try, in order of effort: (a) raise `high_pass_sigma` to 48 or 64 and re-render one variant to test; (b) select a Renoir reference WITHOUT prominent figures (e.g. `bouquet-de-narcisses-et-de-roses` from Round 3, or a Renoir landscape without people); (c) accept the bleed as artistic and integrate the figures into the prompt. Luca's call.
2. **`banded_renoir_tuned` gave "interesting results"** on Renoir fields. Qualitative positive, not yet a binarized keep/drop. The recipe was designed against still-life brushwork but appears to translate. Production decision parked pending a closer side-by-side against `evolved_walk` and `image_derived` (once the figure-bleed issue is separated out so image_derived can be evaluated fairly).
3. **Jitteriness in interpolation: motion reads as chunks moving in step rather than as continuous painterly drift.** Observed across most Round 4 renders, less so on Round 3 still-lifes. This is a new finding documented in the [Interpolation jitteriness section below](#interpolation-jitteriness-on-off-distribution-or-loose-keyframes). It cuts across noise families, so it is not a noise-palette issue per se — likely a RIFE-meets-off-distribution-keyframes interaction.

### Image_derived paused (2026-05-18)

After Round 4 review, **`image_derived` is removed from the active sweep cycle**. The reference-content bleed at `high_pass_sigma=32` (figures from Renoir's *Girls Picking Flowers in a Meadow* surviving the high-pass and emerging in the diffused output) is not artistically usable as-is, and the cure (sigma 48 / 64 or a no-figure reference) is not the highest-value next experiment.

**The technique is not deprecated.** Parked use case worth preserving for future projects: a non-prompt mechanism for biasing generated assets toward a specific image composition or visual identity (artist's painting, photograph, anchor frame from a prior render). Useful when a project needs to inherit the texture grammar of a known reference without including the reference in the prompt path. Re-test when this need surfaces.

### Open recommendations from Round 4

- **Re-render image_derived only at `high_pass_sigma=48` or `64`** for one subject (probably meadow, fastest to render at ~80s, ~$0.05) as a quick figure-bleed diagnostic. If figures still survive at 64, the reference itself is the problem and we swap to a non-figure-bearing Renoir landscape painting.
- **Production decision on banded is still parked.** Hold until the jitteriness investigation lands; if jitteriness is dominant, the difference between noise sources on field subjects is secondary and the cheaper options win by default.
- **Anti-still-life negative prompt is a now-canonical authoring rule for outdoor Renoir.** Specifically: `vase, pot, container, table, indoor, still life` appended to the default Renoir negatives. Documented here, baked into the Round 4 YAMLs, should be the default for any future outdoor-subject Renoir config in this LoRA's lifetime.

## Interpolation jitteriness on off-distribution or loose keyframes

New finding from Round 4 video review (2026-05-18). Observation: outdoor Renoir field renders show **visibly chunkier motion** between consecutive frames than the in-distribution Round 3 still-life renders. The effect reads as "the paint is moving in regional chunks rather than as one continuous painterly drift". Present across all three noise sources tested (evolved_walk, image_derived, banded), so it is not a noise-palette property.

### Hypothesis

The pipeline produces 26 SDXL keyframes per loop, then RIFE generates 63 interpolated frames between each consecutive keyframe pair. RIFE's optical-flow model bridges the gap between keyframes by inferring smooth pixel motion. When consecutive keyframes are visually close (in-distribution prompt, low denoise strength, settled chain), RIFE has little to bridge and the interpolation reads as continuous breathing. When consecutive keyframes are visually farther apart (off-distribution prompt, higher per-keyframe variance, LoRA pulled toward base SDXL on out-of-training-set content), RIFE has to bridge larger displacements, and the resulting interpolation reads as **chunks of pixels moving in coherent groups separated by hard transitions**, i.e. the perceived jitter.

If true, the lever is **keyframe-to-keyframe similarity** rather than noise spatial frequency or noise temporal walk rate. The mechanism is RIFE-side, not Phase A-side.

### Cross-check against existing data

- Round 3 (still-life roses, in-distribution): visually smooth interpolation, jitteriness not reported.
- Round 4 (outdoor fields, off-distribution): jitteriness reported across all three noise sources.
- Round 2 (Cole landscapes, in-distribution for the Cole LoRA): jitteriness not reported in the soft-motion sources after the `structural_decay_radius=0` fix.

The pattern fits: jitter correlates with off-distribution LoRA use, not with noise source choice.

### Mitigations to test (none committed yet)

In order of effort vs. payoff:

1. **Lower denoise strength on the off-distribution subject.** Drop `render.steady_strengths` toward `[0.50, 0.50, 0.52, ...]` (the `calm` profile) for outdoor Renoir renders. Lower strength means less keyframe-to-keyframe variance, so RIFE has less to bridge. Trivial config change.
2. **Increase keyframe count** by raising `frames.steady` from 5 to 7 or 8. More keyframes per loop = shorter RIFE bridges. Adds GPU time linearly. Modest change.
3. **Tighter prompt structure across A/B/C.** Reduce the semantic distance between segment prompts so the model dwells longer in one composition before pivoting. Authoring change.
4. **Trained-distribution LoRA.** A Renoir LoRA fine-tuned on outdoor floral scenes would render closer to its training distribution on field subjects, producing closer keyframes naturally. Highest effort, requires a second training pass on a different dataset.

The cheapest diagnostic: re-render one meadow variant with `render: calm` profile and compare interpolation feel. ~$0.05 if just evolved_walk; ~$0.80 if including banded.

### Why this is a noise-research finding (and possible escalation)

This was surfaced from noise-research video review but the mechanism is RIFE / keyframe interaction, not noise. Filed here for now because the noise workstream produced the observation and has the evidence. Worth a parent-chat decision on whether to **promote this to its own finding** (e.g. `docs/findings/interpolation-jitter.md`) so other workstreams (compositing, future LoRA work, live work) can reference it without spelunking through noise-sources.md. Coordination request filed in workstream `progress.md`.

## Round 5 design: motion-quality levers sweep (dispatched 2026-05-18)

Triggered by Luca's reframe after Round 4 video review: **the dominant artifact may not be the noise, but the levers controlling interpolation feel.** Round 5 sweeps the four most-likely-relevant levers on a single subject + noise to isolate which one dominates the jitteriness identified as a Round 4 finding.

### Slate (9 variants)

Subject: `meadow` (established Round 4 baseline). Noise: `evolved_walk` for 8 of 9 (cleanest, cheapest, isolates lever effect from noise effect). One banded-recipe cost variant at the end.

| Variant | Lever | Value | Question it answers |
|---|---|---|---|
| `r5_denoise_calm` | denoise strength | `calm` profile (~12% lower) | Does lower per-frame variance reduce jitter? |
| `r5_denoise_aggressive` | denoise strength | +18% over standard | Confirms the lever direction: more variance → more jitter? |
| `r5_steady7` | `frames.steady` | 7 (default 5) | Does longer composition dwell change perceived speed? |
| `r5_steady9` | `frames.steady` | 9 | Same question, stronger dose |
| `r5_transition5` | `frames.transition` | 5 (default 3) | Does softer SLERP gradient reduce chunkiness? |
| `r5_transition7` | `frames.transition` | 7 | Same, stronger dose |
| `r5_rife_skip0` | `rife.skip_boundary` | 0 (default 4) | Do deceleration-zone frames near keyframe boundaries help or hurt? |
| `r5_rife_skip6` | `rife.skip_boundary` | 6 | Same, opposite direction |
| `r5_banded_cd1000` | banded `cell_density` | 1000 (default 3000) | Is dense-Worley overkill? Can we 3x cheaper without losing character? |

Baseline for comparison: `outputs/noise-tests/round-4-renoir-fields/renoir_meadow_r4_evolved_walk.mp4` (already rendered, no need to re-dispatch).

### Budget

- 8 evolved_walk variants × ~$0.05 each = ~$0.40
- 1 banded cd=1000 variant ≈ $0.27 (~3x cheaper than the cd=3000 banded at $0.76 in Round 4)
- **Total ~$0.67** on Modal L40S, ~80 s wall in parallel.

### What we are looking for

For each lever, after the renders land, watch the variant against the baseline and answer:

1. Does the variant **eliminate or reduce the jitter** Luca observed?
2. Does it change **perceived speed** (faster / slower drift)?
3. Does it visibly **degrade** anything else (sharpness, composition coherence, loop closure)?

The lever(s) that reduce jitter without obvious degradation become **new defaults for the production palette**. Levers that have no effect or only degrade get noted and dropped. After Round 5 locks the motion-quality config, the noise-palette comparison (banded vs evolved_walk) becomes meaningful again because the dominant artifact has been suppressed.

### Round 5 actuals (completed 2026-05-18)

9/9 succeeded on Modal L40S. Wall: 9 min (parallel). Total cost: $0.70 (predicted $0.67).

| Variant | Wall (s) | Cost (USD) |
|---|---|---|
| r5_denoise_calm | 83 | 0.045 |
| r5_denoise_aggressive | 85 | 0.046 |
| r5_steady7 | 93 | 0.051 |
| r5_steady9 | 114 | 0.062 |
| r5_transition5 | 96 | 0.052 |
| r5_transition7 | 104 | 0.056 |
| r5_rife_skip0 | 88 | 0.048 |
| r5_rife_skip6 | 85 | 0.046 |
| r5_banded_cd1000 | 536 | 0.290 |
| **Total** | wall 541 parallel | **$0.695** |

The `banded cd=1000` finished in **535 s vs 1401 to 2605 s for cd=3000**. ~3 to 5x faster, ~3 to 5x cheaper. Worley's broadcast cost scales linearly with `n_points` as predicted. Output at `outputs/noise-tests/round-5-motion-levers/`. Integrated as Section I (lever sweep) and Section J (raw companion for cd=1000) of [compare.html](../../outputs/noise-tests/compare.html).

### Verdicts pending

After video review, two decisions to lock:

1. **The motion-quality default.** For each of the four levers tested (denoise strength, steady frames, transition frames, RIFE skip_boundary), is the default value still the best, or does one of the swept values produce visibly better motion? The winners become new production defaults.
2. **Banded cell_density default.** Does `cd=1000` read visually indistinguishable from `cd=3000`? If yes, drop the production default to 1000 and save ~70% of the dense-Worley render cost across the release. If `cd=3000` is visibly superior, keep it and absorb the cost.

Verdicts get appended below after Luca's review.

### What's NOT in Round 5

- No `image_derived` variants (paused per Round 4 verdict above).
- No semantic-prompt-distance sweep (would require new A/B/C prompts; deferred until simpler levers are characterised).
- No subject variation (meadow only; cross-subject re-test happens after defaults lock).
- No `T3#9 anchor clamp A/B` (will run as a follow-up after Round 5 baseline, per the workstream-progress recommendation).

## Open questions (require GPU renders)

These need to be answered before the noise palette is locked for the Renoir
release.

- Does Simplex visibly differ from Perlin on SDXL Lightning output? If not,
  drop Simplex and keep one as the smooth-low-frequency option.
- Worley distance metric: euclidean reads most organic; do chebyshev and
  manhattan give us anything we want for graphic / geometric subjects, or
  are they just curiosities?
- For Renoir florals, which noise (or banded mix) maximizes the brushwork
  impression without losing the LoRA-driven floral content?
- Image-derived: does a Renoir reference fed in as image-derived noise push
  the generation toward more or less Renoir-like output, holding the LoRA
  constant? This is a knob for in-context steering.
- Frequency-banded with a Worley high-band and an FBM low-band: does this
  give the "petals on a softly drifting field" reading we expect?

## Next steps

1. GPU pass: run the `structured` preset against `tcole_valley.yaml` and a
   Renoir candidate config. Build the contact sheet. Annotate this doc with
   verdicts per source.
2. If Simplex is redundant with Perlin, deprecate it.
3. Sweep `feature_size` and `cell_density` over a coarse range to find the
   visual sweet spots for each source type, on the Renoir LoRA.
4. Design 3 to 5 banded presets for the Renoir release based on the sweep.
5. Coordinate with the parent chat to wire a `NoiseSource` selector into
   `config.py` / `keyframes.py` so the choice is configurable per-subject
   (request will be filed in [planning/workstreams/noise/progress.md](../planning/workstreams/noise/progress.md)).


---
*Did you reproduce this and observe something different? Counter-findings welcome. See [CONTRIBUTING.md](../../CONTRIBUTING.md) shape 4 and the [finding issue template](../../.github/ISSUE_TEMPLATE/finding.md).*
