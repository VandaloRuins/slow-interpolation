# The pipeline (technical reference)

Mechanical specification of the existing slow-interpolation pipeline. Derived from a line-by-line read of [../legacy/choire-v2/scripts/](../legacy/choire-v2/scripts/) and [../legacy/after-cole/](../legacy/after-cole/), cross-checked against the three Choire v2 research docs at [../legacy/choire-v2/research/](../legacy/choire-v2/research/).

The single most important fact about this pipeline: **there are two variants**, an "engine" variant in `generate_videos.py` and an "entry-point" variant in the three scripts that import from it (`generate_subject_test.py`, `generate_horizontal.py`, `generate_horizontal_calm.py`). They share the same architecture but differ on frame counts, return scheme, transition handling, noise path, and RIFE configuration. Every sample MP4 under [../examples/outputs/](../examples/outputs/) was rendered by the entry-point variant. The After Cole release (Hudson River School horizontals) is the entry-point variant with the fresco LoRA + style monkey-patched out for the Thomas Cole LoRA + style.

When this doc gives a single value, it is the **entry-point variant value** (the one that produced the sample outputs). Engine-only values are flagged explicitly.

## Four phases

Sequential, no VRAM contention. Models are loaded, used, unloaded.

```
A.   Keyframes      SDXL Lightning 4-step img2img chain   ->  PNG sequence
A.5  Smoothing      Frequency-separated temporal smoother  ->  PNG sequence
B.   Upscale        Real-ESRGAN x2  (DISABLED in production) -> PNG sequence
C.   Interpolation  RIFE v4.25 64x at linear timestep      ->  PNG / direct-to-encoder
D.   Encoding       H.264 yuv420p, 24 fps                  ->  MP4
```

## Phase A: keyframes (SDXL Lightning img2img)

### Model stack

- Base: `stabilityai/stable-diffusion-xl-base-1.0`, fp16.
- Speed: `ByteDance/SDXL-Lightning` 4-step LoRA. Loaded then `fuse_lora()` at scale 1.0, then `unload_lora_weights()`. Lightning replaces an earlier SDXL Turbo stack which was rejected because CFG=0 could not render figured subjects (documented in `video-pipeline-best.md`, the "subject collapse" finding).
- Style: a domain LoRA fused on top at scale 0.35 (fresco) or 0.75 (Thomas Cole). The scale gap is real: the Casa del Suono fresco LoRA was trained on top of a domain-tuned base and works at 0.35; the Thomas Cole LoRA was trained from scratch on SDXL base and needs 0.7 to 0.9 to read.
- VAE: `madebyollin/taesdxl` (TAESD), fp16. Full SDXL VAE was rejected on 8 GB (fp16 produced NaN, fp32 OOM'd at portrait, bf16 was visibly soft).
- `pipe.unet.to(memory_format=torch.channels_last)`. `pipe.safety_checker = None`.

### Scheduler / sampler

- `EulerDiscreteScheduler.from_config(pipe.scheduler.config, timestep_spacing="trailing")`. Trailing timesteps are required by Lightning.
- `num_inference_steps=4`.
- `guidance_scale=1.5`. Non-zero CFG is what fixed "subject collapse" when migrating from Turbo. CFG=1.5 is low enough that Lightning's 4-step distillation still applies cleanly.

### Resolution

| Orientation | Script | Generated size | Notes |
|---|---|---|---|
| Portrait | `generate_videos.py`, `generate_subject_test.py` | 768 x 1344 | Official SDXL training bucket (4:7). Off-grid sizes (576x1024, 512x896) were tried and rejected for amplifying border artifacts. |
| Horizontal | `generate_horizontal.py`, `generate_horizontal_calm.py`, `generate_horizontal_tcole.py` | 1344 x 768 | Same bucket, transposed. All cloned sample outputs are horizontal. |

### Border suppression

Two mechanisms applied together (belt and suspenders, both kept after testing):

- `crops_coords_top_left=(256, 256)` plus `original_size=(1024, 1024)` plus `target_size=(W, H)` micro-conditioning. Tells SDXL the generation is a center-crop of a larger canvas. Correlated in training data with frameless interior content.
- Latent-edge masking callback (`edge_suppression_callback`) at every denoising step: builds a quadratic-feather mask 3 latent pixels deep at each edge, blends the outer band toward a mirror-padded interior at 30% strength. Targets the model's tendency to paint a decorative arch around the frame, especially with the fresco LoRA. `EDGE_SUPPRESS_PX=3`, `EDGE_SUPPRESS_STRENGTH=0.3` in [../legacy/choire-v2/scripts/generate_videos.py](../legacy/choire-v2/scripts/generate_videos.py).

Edge-weighted noise (heavier noise at borders) was tried and rejected as itself a source of border artifacts. The current entry-point noise is uniform.

### Segment structure

A clip is a sequence of segments. Each segment is one prompt. Default layout is three forward segments plus a return:

```
[A steady] [A->B transition] [B steady] [B->C transition] [C steady] [C->A return]
```

Then an extra anchor frame is appended at the end for clean loop closure. Anchor = the first coherent frame after warmup.

### Frame counts

The engine constants in `generate_videos.py` are not what produced the sample outputs. The entry-point scripts override them.

| Setting | Engine | Subject test (portrait, `--full`) | Subject test (portrait, test) | Horizontal |
|---|---|---|---|---|
| `STEADY_FRAMES` | 54 | 17 | 12 | 5 |
| `TRANSITION_FRAMES` | 6 | 6 | 3 | 3 |
| `RETURN_FRAMES` | 16 | 16 | 6 | 4 |
| `WARMUP_FRAMES` | 3 | 3 | 3 | 3 |
| Total keyframes (3 fwd segs + return + anchor) | 191 | 60 | 51 | 26 |
| Output duration at RIFE 64x / 24 fps / `skip_boundary=4` | ~7 min (engine, no skip-boundary) | ~3 min | ~1.5 min | ~60 s |

Warmup frames are generated but **kept**, not discarded. The first frame is run at strength 0.85, frames 2 and 3 at 0.75. The last warmup frame becomes the anchor for return-segment convergence. Pipeline.md previously said warmup frames are discarded; that was wrong.

### Denoise schedule

**Steady frames.** Per-position strength cycled through `STEADY_STRENGTHS`:

- Standard: `[0.55, 0.55, 0.60, 0.55, 0.55, 0.65, 0.55, 0.60]`. The variation introduces micro-fluctuation without losing composition. Earlier attempts to lock strength flat (e.g., 0.50) lost visual interest.
- Calm: `[0.50, 0.50, 0.52, 0.50, 0.50, 0.54, 0.50, 0.52]`. ~12% lower average. Used to produce the `_calm` sample outputs.

Important caveat from the research log: SDXL Lightning's progressive adversarial distillation has trained anchors at strengths 0.25 / 0.50 / 0.75 (for the 4-step model). The cycling values above are slightly off-anchor. The community recommendation (B4 in `frame-interpolation.md`) is to clamp to 0.50 or 0.75. The legacy scripts do not do this. This is a candidate experiment for the port.

**Transitions.** The engine defines a ramp `TRANSITION_STRENGTHS = [0.65, 0.72, 0.80, 0.80, 0.72, 0.65]` (peak 0.80 mid-transition to let the image actually travel). **The entry-point scripts do not use it.** They use a single constant transition strength:

- Standard: 0.65 (or `--transition-strength` override).
- Calm: 0.52.

The engine's ramp is documented in the research as the "winning configuration" but the cloned scripts that produced the sample outputs flattened it. Likely an oversight during the horizontal port. Worth restoring as an option in the port.

**Return segment.** Pixel-space convergence toward the anchor. Three different schemes exist in the legacy code, representing the historical evolution (engine -> horizontal -> calm):

| Variant | Strength | Pixel blend toward anchor |
|---|---|---|
| Engine (`generate_videos.py`) | 3-phase: 0.50 to 0.58 (frames 0-5), 0.60 to 0.75 (6-11), 0.75 to 0.80 (12+) | 0% (0-5), 0% to 40% linear (6-11), 40% to 85% linear (12+) |
| Horizontal | 0.50 to 0.60 linear | 0% to 20% quadratic ease-in |
| Calm | 0.48 to 0.55 linear | 0% to 20% quadratic ease-in |

The 85% engine variant produces a "snap" at loop closure (research obstacle 17). The 40% second-pass softened it. The 20% quadratic third-pass plus RIFE wrap-around (see Phase C) is the production setting and what produced every cloned sample. The `ANCHOR_RETURN_STRENGTH = 0.75` constant in the engine is **dead code**.

### Noise blend

A small noise component is mixed into each img2img input image to keep texture alive and break frame-to-frame identicality. The engine and entry-point scripts use different noise functions:

- **Engine** (`generate_videos.py`): `edge_weighted_noise_blend` over uint8 random noise. With `NOISE_BLEND_CENTER=0.08` and `NOISE_BLEND_EDGE=0.08`, the result is uniform per-frame independent random-pixel noise at 8%. `coherent_noise_image` and `temporal_noise_blend` are defined but never called.
- **Entry points** (`generate_horizontal*.py`, `generate_subject_test.py`): `evolved_noise_blend(img, blend_pct, walk_rate)` from the non-cloned module `generate_crown_video.py`. The function signature and the `walk_rate` parameter (0.05 standard, 0.02 calm) match the "noise walk" technique documented as recipe B1 in `frame-interpolation.md`: persist a latent-shape noise tensor across frames and evolve it slowly by blending in `walk_rate` fresh noise per frame, then renormalize to unit variance. The point is temporal noise consistency, so fine detail does not get reinvented at every step (this was the documented root cause of the "1.3 s rhythmic pulse" before the Lightning + RIFE v4.25 fixes).

Until the `generate_crown_video.py` source is recovered or reimplemented, the exact `evolved_noise_blend` behavior on RGB pixel input (vs. on a latent tensor as recipe B1 describes) is inferred but not directly verified. The recovered behavior is recipe B1 applied in pixel space rather than latent space. This is one of the things the port needs to nail down.

Per-frame and per-transition noise levels:

| Setting | Steady noise | Transition noise | Pre-frame blur (`STRUCTURAL_DECAY_RADIUS`) | `walk_rate` |
|---|---|---|---|---|
| Engine | 0.08 uniform | `[0.15, 0.25, 0.35, 0.35, 0.25, 0.15]` ramp | 2 | n/a |
| Horizontal | 0.08 | 0.15 constant (engine ramp unused) | 2 | 0.05 |
| Calm | 0.04 | 0.08 constant | 0 (disabled, prevents focus loss) | 0.02 |

The pre-frame structural-decay blur (Gaussian blur of the previous frame before re-encoding) prevents fine-texture runaway. Disabling it in calm mode is the single biggest reason calm frames feel sharper despite the gentler denoise.

### Prompt conditioning during transitions

Between two prompts A and B, transition frames use SLERP (spherical linear interpolation) of the prompt embeddings, not text concatenation. The slerp is parameterized by a `smoothstep` of the linear frame index: `t = 3*tl**2 - 2*tl**3` where `tl = (i+1)/(actual_trans_n+1)`. This produces a slow-fast-slow easing of conditioning between prompts. The pooled embeddings are SLERP'd alongside.

Negative prompts (CFG branch) hold the source-segment's negative embeds across the entire transition (do not slerp negatives). A module-level `NEG_PROMPT` in `generate_horizontal*.py` blocks religious / angelic / nude imagery that the Casa del Suono fresco LoRA otherwise pulls toward.

### Output of phase A

Numbered PNGs at `videos/staging/<name>/keyframes/0000.png`, `0001.png`, ... including the appended anchor as the last frame.

## Phase A.5: temporal smoothing

Frequency-separated smoother applied to the keyframe sequence in place. Decomposes each frame into a low-frequency component (Gaussian blur, radius 16) and a high-frequency residual; temporally blends only the low-frequency component across +/- `window` frames with Gaussian weights of `sigma`; recombines with the **center frame's** high-frequency. This kills the ghosting that a naive temporal average would produce while keeping per-frame sharpness.

Function default in `generate_videos.py`: `sigma=1.0, window=5, blur_radius=16`. The engine calls it without arguments.

CLI defaults in the entry-point scripts:

- Horizontal: `--smooth-sigma 1.5 --smooth-window 8`.
- Calm: `--smooth-sigma 1.8 --smooth-window 8`.

Higher sigma was tried (2.0) and rejected as too aggressive (lost texture breathing, made subjects abstract). Smaller window (5) was the earlier engine setting and was bumped to 8 for horizontal. Calm uses 1.8 to compensate for its lower noise levels.

## Phase B: upscale (disabled)

`generate_videos.py` wires up Real-ESRGAN x2 (`RealESRGAN_x2plus`) with `tile=384`, `tile_pad=10`, half precision, GPU 0. Output would be 1536 x 2688 (or 2688 x 1536 horizontal).

It is **disabled by default** in production. Both ESRGAN x2 and an SDXL img2img upscale at low strength were tested and rejected on 2026-03-31: they destroyed the fresco aesthetic (over-sharpening, geometric artifacts, "cubist look", Gemini-rated 3/10 fresco authenticity). 768 x 1344 native is the production output for Choire v2 and 1344 x 768 native for After Cole.

For Renoir, this decision is open. Floral subjects may survive ESRGAN better than frescoes did. Test on a short clip before committing.

The ESRGAN load path uses a cross-venv import trick: `realesrgan` and `basicsr` live in Choire v1's `visuals/.venv-sd/Lib/site-packages/`, not in the main venv. `load_esrgan()` pre-imports torchvision in the host venv (to prevent the cross-venv `.venv-sd` from clobbering it with an incompatible version), then prepends `.venv-sd`'s site-packages to `sys.path`. The port should re-vendor ESRGAN cleanly, not inherit this trick.

## Phase C: RIFE interpolation

### Model

RIFE v4.25 from `hzwer/Practical-RIFE`. Upgraded from RIFE HDv3 to fix the "1.3 s rhythmic sharpness flash" caused by HDv3's recursive binary midpoint behavior (the t=0.5 frame was systematically sharper than t=0.25/0.75 due to the training distribution peak; recursing on midpoints exposed this every 1.3 s at 12 fps). The class `train_log.RIFE_HDv3.Model` is preserved as the v4.25 loader keeps the legacy module name.

v4.25 is preferred over v4.26 per the SmoothVideo project community: v4.26 requires resolution divisible by 64 (v4.25 only needs 32) and shows marginally worse flicker on non-video content. The legacy scripts run on v4.25 with the default `ensemble=True` and do not enable `TTA` (TTA introduces brightness inconsistencies between frames). These are inherited from Practical-RIFE defaults and should be preserved in the port.

### Configuration (entry-point variant, production)

- `RIFE_PASSES = 6` -> 63 intermediate frames per keyframe pair. Originally referred to as "RIFE 64x" but only the 63 intermediates are written; see "skip keyframes" below.
- **Linear timestep**, not recursive binary. `linear_interp(model, img0, img1, n_passes, skip_boundary, sinusoidal)` calls `model.inference(img0, img1, timestep=t)` for `t = i / (n_frames + 1)`. Eliminates the binary-midpoint sharpness flash. Sinusoidal spacing (`--sinusoidal`) was tested and rejected as having a similar pause artifact.
- **Skip keyframes.** The entry-point Phase C loop writes only the RIFE-interpolated frames to the MP4 writer. Source keyframes are not appended. This eliminates "snap-to-clarity" micro-stalls that would otherwise occur every keyframe (SDXL keyframes are sharper than RIFE interpolants).
- **Skip boundary 4.** `linear_interp` drops the four frames closest to `t=0` and the four closest to `t=1` of each pair. These are the deceleration zones where RIFE flow energy is near zero. Skipping them removes the "soft pause" that would otherwise read at each keyframe boundary. `skip_boundary=6` was tested and made it worse.
- **Edge crop 8 px.** After RIFE, 8 pixels are trimmed from each side of every frame before writing. Removes residual arch/border content that survived the latent-edge callback.

### Engine variant departures

`generate_videos.py`'s `phase_c_interpolate` differs from the entry points:

- **Keyframes are written** to the MP4 alongside interpolants. No skip-keyframes.
- `linear_interp` is called **without** `skip_boundary`, defaulting to 0.

The engine variant therefore does **not** have the deceleration-pause removal that the production samples have. It is the older, pre-Lightning configuration.

### Loop closure (both variants)

After the keyframe sequence is interpolated, a final wrap-around set is generated: `linear_interp(model, last_keyframe, first_keyframe, RIFE_PASSES, skip_boundary)` produces 63 frames between the last keyframe and the first; all except the final one (which equals the first frame) are appended to the writer. The MP4 thus closes into the next loop iteration with a continuous interpolated trajectory, not a cut. Combined with the gentle pixel-blend toward anchor in the return segment, this is what makes the loops seamless.

This wrap-around is critical to the work's aesthetic and should be a first-class step in the port, not buried in Phase C.

### Output frame rate

24 fps. 12 fps was the early setting (paired with 16x RIFE for ~3 s gaps); 30 fps was tested and rejected. 24 fps + 64x RIFE is the current setting.

## Phase D: encoding

`imageio.get_writer(path, fps=24, codec='libx264', quality=Q, pixelformat='yuv420p')`. The two-codepath split:

- `phase_c_interpolate` streams frames directly to the writer as RIFE produces them (constant ~50 MB RAM regardless of total frames). This was a deliberate fix for a 37 GB OOM that occurred when the full RIFE output was held in memory at 1536 x 2688.
- `phase_d_encode_only` (for `--no-rife`) reads the keyframe PNGs and encodes them straight, no interpolation.

Quality slider:

- Choire v2 portrait sessions: `--quality 5` default (CRF ~23). File sizes 26 to 93 MB per 3-min clip.
- After Cole / horizontal: the same quality slider applies; the horizontal scripts hard-code `quality=5` (no `--quality` flag at this level).

Existing output files are not overwritten. `archive_if_exists(path)` moves an existing `<name>.mp4` to `videos/archive/<name>_<timestamp>.mp4` before writing.

A `videos/manifest.json` records per-clip metadata (frames, duration, size, resolution, pipeline tag, generation time).

## How a new style is plugged in (the After Cole pattern)

`generate_horizontal_tcole.py` is the reference example. Three things change:

1. The fresco LoRA candidate list is replaced (`gv.LORA_CANDIDATES = [thomas_cole_path]`).
2. `gv.LORA_SCALE` is raised (0.35 -> 0.75 default; CLI `--lora-scale`).
3. `gv.STYLE_PREFIX` is replaced (fresco prefix -> `"tcole, romantic landscape oil painting, Hudson River School style, "`). The trigger word `tcole` activates the LoRA.

The subjects dict is then `dict.update`'d with Cole subjects (`tcole_ruins`, `tcole_valley`, `tcole_cloudship`, `tcole_horses`, `tcole_siege`) and `generate_horizontal.main()` is called with the remaining argv passed through. Everything else, every pipeline parameter, every constant, is unchanged.

This is the move the port has to support cleanly: a `Style` config that bundles LoRA path, scale, prefix, suffix, optional negative prompt, plus a separate `Subjects` config. Both should be plain data, not module-level mutations.

## What is currently parameterized

- Per-script `SUBJECTS` dict, with each subject containing A / B / C / A-return prompts. (The per-prompt `denoising` field present in every subject is **dead**: never read by the loop. Drop in the port.)
- Module-level `NEG_PROMPT` per entry-point script (single string, fresco-specific in the Choire scripts).
- Module-level `STYLE_PREFIX` / `STYLE_SUFFIX` in `generate_videos.py`, intended to be monkey-patched by adapter scripts.
- CLI flags on the entry points: `--subject`, `--tag`, `--smooth-sigma`, `--smooth-window`, `--transition-strength` (entry-point variants only), `--skip-boundary`, `--sinusoidal`, `--no-lora`, `--full` (subject_test only), `--lora-scale` and `--epoch` (tcole adapter only).

## What is not parameterized (and should be)

- Resolution. Hard-coded inside each entry-point's `main()`. The port should make orientation a config dial.
- The cycling steady strengths. Defined inline; should be a profile (`standard` / `calm` / custom).
- The transition ramp (currently flattened to a constant in the entry points). Should be a profile.
- The return scheme (three-phase pixel blend with different max values). Should be a profile.
- The `evolved_noise_blend` walk rate. Defined inline; should be config.
- The RIFE config (`passes`, `skip_boundary`, `sinusoidal`, edge crop). Defined per-script; should be config.

## What the port must preserve

- Four-phase sequential structure with no VRAM contention. Models loaded, used, unloaded.
- The img2img chain with the per-position cycling strength schedule (standard and calm profiles).
- The SLERP-of-embeddings + smoothstep-t recipe for transitions, applied to both regular and pooled SDXL embeddings.
- The `crops_coords_top_left` micro-conditioning plus the latent-edge masking callback. Both. They are not redundant; one is text-conditioning, the other is per-step latent surgery.
- Frequency-separated temporal smoothing with `sigma=1.5`, `window=8`, `blur_radius=16` as the default profile (and `sigma=1.8` for calm).
- Evolved noise (recipe B1) with a per-frame `walk_rate`, not per-frame independent random pixels. The latent-vs-pixel application question needs to be resolved during the port; the safe assumption is that the entry points apply it in pixel space because that is the input the script holds.
- Pre-frame structural decay (Gaussian blur radius 2) in standard mode, 0 in calm.
- RIFE v4.25 linear timestep, 6 passes, `skip_boundary=4`, skip-keyframes, 8 px edge crop.
- RIFE wrap-around loop closure between last and first keyframe.
- Anchor-frame mechanism: persist the first coherent frame post-warmup; pixel-blend toward it during return; append it as the final keyframe.
- H.264 yuv420p at 24 fps.

## What the port can drop or clean up

- Hard-coded paths into Choire v1 (`V1_VISUALS`, `RIFE_DIR`, `VISUALS_VENV_PACKAGES`, `LORA_CANDIDATES`). Resolve from config. See [dependencies.md](dependencies.md).
- The cross-venv ESRGAN import trick. Re-vendor `realesrgan` + `basicsr` cleanly in a single venv, or drop ESRGAN entirely until Renoir is tested.
- The `prompt_engine` import in `generate_videos.py`. The 54-excerpt scheduling logic is Choire v2 specific.
- The non-cloned `generate_crown_video` dependency. The port absorbs `evolved_noise_blend` and reimplements it from recipe B1 directly (15 lines of Python).
- The per-prompt `denoising` field in `SUBJECTS` (unused).
- The `coherent_noise_image` / `temporal_noise_blend` defined-but-unused code in `generate_videos.py`.
- The dead `ANCHOR_RETURN_STRENGTH` constant in `generate_videos.py`.
- The monkey-patch pattern in `generate_horizontal_tcole.py`. Replace with a `Style` config object.
- The "RIFE HDv3" / "RIFE 8x" misleading comments in `generate_videos.py`'s docstring. The actual config is v4.25 at 64x.
- `recursive_interp` (dead reference code; the binary-midpoint variant was the bug).
- `phase_d_encode_only` (kept for `--no-rife` mode; the port can collapse this into the main encode path).

## Known unknowns to investigate during the port and the Renoir release

- Whether the Renoir aesthetic survives Real-ESRGAN x2 better than the fresco aesthetic did. Test on a short clip before committing to native or upscaled output.
- Whether the cycling steady strengths should be clamped to Lightning's trained anchors (0.50 / 0.75) per research recipe B4. Could measurably improve temporal stability with no other change.
- Whether the engine's full transition strength ramp `[0.65, 0.72, 0.80, 0.80, 0.72, 0.65]` reads as more "musical" than the flat 0.65 the entry points settled on. The engine's choice was deliberate; the flat constant looks like a regression introduced during the horizontal port.
- Whether `sigma=1.5` and `window=8` need re-tuning for high-frequency floral subjects (flowers vs. plaster vs. landscapes).
- Whether the entry-point return scheme (20% max pixel blend) should be eased toward 30 to 40% for landscapes, where there is less risk of subject "snap" than there is in figured fresco closeups.
- The exact behavior of `evolved_noise_blend` (latent-space or pixel-space, internal renormalization) requires either recovering the original source or pinning it down empirically against the cloned outputs.

## Production status the legacy code shipped

- Choire v2 portrait sessions: 25 videos rendered, 19 approved, 6 reworked. Locked at 768 x 1344 native, no upscale, 24 fps, ~3 min loops. Catalogued at the bottom of [../legacy/choire-v2/research/video-pipeline-best.md](../legacy/choire-v2/research/video-pipeline-best.md).
- After Cole horizontal: 5 subjects (`tcole_ruins`, `tcole_valley`, `tcole_cloudship`, `tcole_horses`, `tcole_siege`), submitted to CtrlShift Visions as "The Course of Empire (After Cole)". Same pipeline, swapped LoRA + style + subjects.
- Horizontal fresco crossover: a small set of horizontal versions of the fresco subjects (harbour, notturno, E14_lake, E24_garden, siege_harbour) plus the calm variants for harbour and notturno. These are the cleanest A/B comparisons of the calm denoise profile.

## What didn't work (preserved from the research log)

Worth keeping accessible so the port does not relitigate settled experiments:

| Approach | Why rejected |
|---|---|
| SDXL Turbo at CFG=0 | Could not render figured subjects ("subject collapse") |
| Edge-weighted noise (heavy at borders) | Caused, not prevented, border artifacts |
| RIFE HDv3 recursive binary midpoint | 1.3 s rhythmic sharpness flash |
| Sinusoidal RIFE timestep spacing | Still felt paused at boundaries |
| `skip_boundary=6` | Made motion feel laggy overall |
| 30 fps playback | Made it worse |
| Unsharp mask post-process | Made it worse |
| hqdn3d ffmpeg post-process | Did not fix the rhythmic pulse (was caused upstream) |
| Naive temporal smoothing (per-pixel average across window) | Ghosting at frame boundaries |
| `sigma=2.0` smoothing | Lost texture breathing, abstracted subjects |
| Strength locked flat at 0.50 | Too static, blue color drift, lost visual interest |
| Strength locked flat at 0.42-0.55 (meditative) | Same |
| Real-ESRGAN x2 upscale (fresco) | Cubist look, geometric artifacts, 3/10 authenticity |
| SDXL img2img upscale at low strength | Worse than native, added noise to fresco texture |
| Blur keyframes (radius 1.5) | Overall too soft |
| 2x keyframe density + 8x RIFE | Video too fast, same flashing |
| 50/50 keyframe blend | Stalls, some ghosting |
| Compositing into a square + crop | Discards 44% of pixels, frames still appeared |

## Open research directions worth knowing (not currently implemented)

These are documented in `frame-interpolation.md` as untried and worth keeping on the radar:

- **Noise warping by optical flow** (NeurIPS 2024 "Warped Diffusion"): warp the previous frame's noise tensor by Farneback flow before each generation. More principled version of the noise walk.
- **EMA-VFI** or **FILM**: appearance-aware interpolators that may handle prompt-change boundaries better than RIFE's pure optical flow. RIFE for iteration, FILM or EMA-VFI for final-quality pass on flagged segments.
- **CogVideoX-Interpolation** or **LTX-Video**: generative video diffusion for keyframe in-betweening. Slow (15 to 30 min per segment on 8 GB) but produces true temporal coherence. Use as a selective pass on worst-pulse segments.
- **PAG (Perturbed Attention Guidance)** during SDXL inference: disrupts self-attention frame patterns, may reduce border bias without VRAM cost. Tested under `enable_pag=True, pag_scale=1.5`.
- **Topaz Starlight Mini**: commercial diffusion video enhancer with explicit temporal attention. Free tier supports testing on 3 clips.

None of these are necessary for the Renoir release. They are post-port exploration territory.

## Appendix: `evolved_noise_blend` (the production noise path)

Captured verbatim from `Choire-v2/generate_crown_video.py` (the non-cloned module referenced by all three entry-point scripts). The port absorbs this function and drops the external dependency.

```python
# Evolved noise walk — persistent noise tensor that slowly evolves
# instead of fresh random noise each frame (root cause of detail reinvention)
_persistent_noise = None

def evolved_noise_blend(img, blend_pct=0.08, walk_rate=0.05):
    """Blend image with slowly-evolving noise instead of fresh random noise.

    The noise tensor persists across frames: 95% previous noise + 5% fresh.
    This means fine details that depend on the noise pattern persist rather
    than being reinvented every frame.
    """
    global _persistent_noise
    from PIL import Image as PILImage
    arr = np.array(img).astype(np.float32)
    fresh = np.random.randn(*arr.shape).astype(np.float32)

    if _persistent_noise is None or _persistent_noise.shape != arr.shape:
        _persistent_noise = fresh.copy()
    else:
        # Evolve: mostly keep previous, add small amount of fresh
        _persistent_noise = (1.0 - walk_rate) * _persistent_noise + walk_rate * fresh
        # Renormalize to unit variance
        std = _persistent_noise.std()
        if std > 0:
            _persistent_noise = _persistent_noise / std

    # Scale noise to pixel range and blend
    noise_pixels = (_persistent_noise * 40 + 128).clip(0, 255)  # centered at 128, ~40 spread
    blended = arr * (1 - blend_pct) + noise_pixels * blend_pct
    return PILImage.fromarray(blended.clip(0, 255).astype(np.uint8))
```

Notes for the port:

- **Pixel-space**, not latent-space. Operates on RGB uint8 input via float32 intermediate. The research recipe B1 in `frame-interpolation.md` proposes a latent-space variant; the production scripts apply it in pixel space, so the port should default to pixel space to match the sample outputs.
- **Gaussian** (`np.random.randn`), not uniform. Mean 0, unit variance after renormalization.
- The noise tensor is **shape-keyed**: if `img.size` changes between calls, the noise restarts from a fresh tensor. The port should preserve this so orientation changes (or test renders at different resolutions) do not inherit stale state.
- Output mapping `noise * 40 + 128`: the noise pixels land near mid-gray with a ~40-unit Gaussian spread (about +/- 2 sigma covers +/- 80 around 128, comfortably inside [0, 255]). The `clip(0, 255)` is defensive.
- Module-global `_persistent_noise` is a session-lived singleton. In the port, scope this to the `Pipeline` instance (per-run state, not per-process).
- Defaults `blend_pct=0.08`, `walk_rate=0.05` match the legacy entry-point standard mode. Calm passes `blend_pct=0.04`, `walk_rate=0.02`. Transition frames pass the per-position transition noise as `blend_pct`.

`generate_crown_video.py` also re-exports `TRANSITION_STRENGTHS` and `TRANSITION_NOISE_RAMP` from `generate_videos.py` (it does not redefine them; it imports them at the top). The horizontal entry-point scripts import the names from `generate_crown_video`, so the dependency chain is `generate_horizontal -> generate_crown_video -> generate_videos`. As noted earlier, the horizontal scripts then ignore the ramp values they imported, so dropping `generate_crown_video` removes one indirection without changing behavior.
