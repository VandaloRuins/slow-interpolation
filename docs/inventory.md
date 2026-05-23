# Inventory

Annotated catalogue of every file under [../legacy/](../legacy/) and [../examples/outputs/](../examples/outputs/), built from a line-by-line read of the source. Where the code disagrees with [pipeline.md](pipeline.md), the discrepancy is flagged in the per-file notes and consolidated at the bottom.

## legacy/choire-v2/scripts/

Four Python scripts, ~3,000 lines total. `generate_videos.py` is the engine. The three `generate_*_*.py` siblings are entry points that load the engine, define their own `SUBJECTS` dict and frame counts, and run a self-contained pipeline (they reuse the engine's helpers but do not call its `phase_a/b/c/d` functions).

Two non-cloned dependencies are imported at runtime from the original Choire v2 repo:

- `prompt_engine` (imported by `generate_videos.py`). Used only when `generate_videos.py` is invoked directly (Phase A). The three entry-point scripts do not need it.
- `generate_crown_video` (imported by all three entry-point scripts). Supplies `evolved_noise_blend`, `TRANSITION_STRENGTHS`, `TRANSITION_NOISE_RAMP`. This module is **not** in the clone. The horizontal scripts cannot run as-is without it.

Both are tracked in [dependencies.md](dependencies.md).

### generate_videos.py (1364 lines)

The four-phase engine, written for portrait fresco generation of 54 Choire v2 excerpts (`E01`...`E31`, plus extras). Reads excerpts from `text/curated_excerpts.json` via the `prompt_engine` module. Used as a library by the three entry-point scripts (`generate_horizontal*.py`, `generate_subject_test.py`).

**End-to-end behavior when run directly.** Argparse selects excerpts (`--all`, `--excerpt`, `--section`). For each excerpt: pre-encode A/B/C/A prompt embeddings, do a 3-frame warmup from random noise, generate `STEADY_FRAMES` keyframes per segment with `STEADY_STRENGTHS` cycled per-position, then `TRANSITION_FRAMES` with SLERP-blended embeddings and a `TRANSITION_STRENGTHS` ramp, repeat for B and C, then a `RETURN_FRAMES` segment with a three-phase pixel-blend toward the anchor frame, append the anchor as the final keyframe. Apply `temporal_smooth_keyframes`. Optionally ESRGAN x2 upscale. Then RIFE pair-by-pair with `linear_interp` (RIFE_PASSES=6, 64x), encode straight to MP4 with `imageio` + libx264, append wrap-around interp frames between last and first keyframe for seamless loop closure, write `manifest.json`.

**Module-level constants.**

| Constant | Value | Controls |
|---|---|---|
| `V1_VISUALS` | `BASE_DIR.parent / "Choire" / "visuals"` | Root for all external assets (LoRA, RIFE, ESRGAN venv). Hard-coded relative path into Choire v1. |
| `RIFE_DIR` | `V1_VISUALS / "rife_v425" / "train_log"` | RIFE v4.25 repo dir added to `sys.path`. |
| `RIFE_TRAIN_LOG` | `RIFE_DIR / "train_log"` | Inner `train_log/` (yes, doubly nested) passed to `Model.load_model`. |
| `VISUALS_VENV_PACKAGES` | `V1_VISUALS / ".venv-sd" / "Lib" / "site-packages"` | Cross-venv import path for `realesrgan` / `basicsr`. |
| `LORA_CANDIDATES` | Casa del Suono epoch 4 then 3 | Fresco style LoRA fallback chain. |
| `GEN_WIDTH`, `GEN_HEIGHT` | 768 x 1344 | Portrait SDXL training bucket. |
| `FPS` | 24 | Output framerate. |
| `LORA_SCALE` | 0.35 | Fresco LoRA scale (overridden to 0.75 default by After Cole). |
| `NUM_INFERENCE_STEPS`, `GUIDANCE_SCALE` | 4, 1.5 | Lightning 4-step with CFG enabled. CFG was disabled in early Turbo experiments and reintroduced (the comment "root cause of subject collapse" preserves the lesson). |
| `CROPS_COORDS_TOP_LEFT`, `ORIGINAL_SIZE`, `TARGET_SIZE` | (256,256), (1024,1024), (W,H) | Micro-conditioning to suppress frame/border bias. |
| `STEADY_FRAMES`, `TRANSITION_FRAMES`, `RETURN_FRAMES`, `WARMUP_FRAMES` | 54, 6, 16, 3 | Per-segment frame counts in portrait mode. The entry-point scripts override these. |
| `STEADY_STRENGTHS` | `[0.55, 0.55, 0.60, 0.55, 0.55, 0.65, 0.55, 0.60]` | Per-position denoise within a steady segment. Cycled with modulo. |
| `NOISE_BLEND_CENTER`, `NOISE_BLEND_EDGE`, `NOISE_BLEND_TRANSITION` | 0.08, 0.08, 0.15 | Per-frame Gaussian noise blend into img2img input. Center and edge are equal (uniform); edge-weighting was tried and rejected. |
| `EDGE_NOISE_BORDER` | 64 | Border width for edge-weighted noise. Unused since center==edge. |
| `STRUCTURAL_DECAY_RADIUS` | 2 | Gaussian blur radius applied to the previous frame before re-encoding. Prevents texture runaway. |
| `TRANSITION_STRENGTHS` | `[0.65, 0.72, 0.80, 0.80, 0.72, 0.65]` | Per-step denoise during a 6-frame transition. Peak 0.80 mid-transition lets the image actually travel. Not used by the horizontal entry points, which import the values from `generate_crown_video` and override anyway. |
| `TRANSITION_NOISE_RAMP` | `[0.15, 0.25, 0.35, 0.35, 0.25, 0.15]` | Noise blend during transition (rises in the middle to reshape composition). |
| `ANCHOR_RETURN_STRENGTH` | 0.75 | Defined but **unused**: the actual return-segment strength is computed inline as a three-phase ramp in `_generate_keyframes_for_excerpt`. |
| `STYLE_PREFIX`, `STYLE_SUFFIX` | `"Italian fresco on aged plaster, ..."`, `""` | Concatenated around every prompt before encoding. Monkey-patched by After Cole to `"tcole, romantic landscape oil painting, ..."`. |
| `RIFE_PASSES`, `EDGE_CROP` | 6, 8 | 64x interpolation; 8 px trimmed from each side after RIFE to remove arch artifacts. |
| `ESRGAN_SCALE`, `ESRGAN_TILE`, `ESRGAN_TILE_PAD` | 2, 384, 10 | x2 upscale, tiled. |
| `EDGE_SUPPRESS_PX`, `EDGE_SUPPRESS_STRENGTH` | 3, 0.3 | Latent-edge suppression callback: blends ~3 latent pixels of border toward a mirror-padded interior at 30% strength, with a quadratic feather. Belt-and-suspenders alongside `crops_coords_top_left`. |
| `NOISE_LO_W`, `NOISE_LO_H`, `NOISE_SPATIAL_SCALE`, `NOISE_TIME_SCALE`, `NOISE_OCTAVES` | 128, 224, 0.02, 0.08, 3 | Coherent simplex-noise generator (`coherent_noise_image`) for the `temporal_noise_blend` path. **Not** the noise path used by the entry-point scripts (those use `evolved_noise_blend` from the missing `generate_crown_video`); used only by `temporal_noise_blend`, which is defined but not invoked anywhere in `generate_videos.py` either. Dead-ish code worth pruning during the port. |
| `PREVIEW_STEADY`, `PREVIEW_TRANSITION` | 4, 3 | Frame counts under `--preview`. |
| `VIDEOS_DIR`, `STAGING_DIR`, `ARCHIVE_DIR`, `MANIFEST_PATH` | `videos/`, `videos/staging/`, `videos/archive/`, `videos/manifest.json` | Output layout. Existing outputs are archived with a timestamp suffix rather than overwritten. |

**Key helpers.**

- `slerp_embeddings(a, b, t, dot_threshold=0.9995)`: spherical interp of SDXL prompt embeddings, with a linear fallback when the embeddings are nearly parallel. Used for transitions.
- `encode_prompt(pipe, prompt, neg)`: returns `(prompt_embeds, pooled, neg_embeds, neg_pooled)` for SDXL Img2Img with CFG.
- `edge_suppression_callback(pipe, step, timestep, callback_kwargs)`: latent-space callback invoked each step. Blends the outer 3 latent pixels toward a mirror-padded interior with 30% strength on a quadratic feather. Prevents the model from re-painting an arch around the frame.
- `coherent_noise_image(w, h, t)`: vectorized 3D simplex noise upscaled bicubically. Defined but not called by the entry-point scripts.
- `temporal_noise_blend(img, frame_idx, blend_pct=0.06)`: applies coherent noise. Defined, not used.
- `edge_weighted_noise_blend(img, center_pct, edge_pct, border)`: builds a per-pixel gradient mask (1 at edges, 0 at center) and blends pure-random uint8 noise; with center==edge the result is uniform random-noise blend. This is the noise path `generate_videos.py` actually uses. Note: pure random noise, not the simplex generator.
- `structural_decay(img, blur_radius=2)`: Gaussian blur of the previous frame before re-encoding.
- `load_rife()`: triple `sys.path` insert (the v4.25 repo nests `train_log/train_log/`), monkey-patches `torchvision.transforms.functional_tensor` to the modern `functional` module, then `from train_log.RIFE_HDv3 import Model`.
- `linear_interp(model, img0, img1, n_passes, skip_boundary=0, sinusoidal=False)`: produces `2^n_passes - 1` intermediate frames at evenly-spaced (or cosine-spaced) t values. **Defaults to `skip_boundary=0`** in this engine; the horizontal entry-point scripts pass `--skip-boundary 4` from the CLI. The recursive (binary-midpoint) variant `recursive_interp` is preserved as dead code for reference.
- `load_esrgan()`: pre-imports torchvision in the host venv to avoid the cross-venv version clobber, then optionally inserts the Choire v1 `.venv-sd` site-packages onto `sys.path` to find `realesrgan` and `basicsr`. Uses the public RealESRGAN_x2plus weights URL.
- `temporal_smooth_keyframes(kf_dir, sigma=1.0, window=5, blur_radius=16)`: frequency-separated smoother. Decomposes each frame into low (Gaussian blur radius 16) and high (residual); blends only the low-freq across +/- `window` frames with Gaussian weights of `sigma`; recombines with the center frame's high-freq. **Defaults are sigma=1.0, window=5**; `generate_videos.main()` calls it without arguments so portrait runs use those defaults. The horizontal entry-points pass `--smooth-sigma 1.5 --smooth-window 8` (or 1.8 for calm). Pipeline.md currently documents the horizontal-mode defaults as universal.

**Phase functions.**

- `phase_a_generate_keyframes(target_ids, steady_n, trans_n, return_n, no_lora, resume)`: loads SDXL base + Lightning 4-step LoRA (fuse + unload), `EulerDiscreteScheduler` with `timestep_spacing="trailing"`, swaps the VAE for `madebyollin/taesdxl`, then optionally fuses the Casa del Suono fresco LoRA at `LORA_SCALE`. Iterates excerpts and calls `_generate_keyframes_for_excerpt`. Unloads SDXL at the end.
- `_generate_keyframes_for_excerpt(...)`: the actual generation loop described above. The **return segment** uses an inline three-phase scheme (not the unused `ANCHOR_RETURN_STRENGTH`):
  - frames 0..5: strength 0.50 -> 0.58, no pixel blend.
  - frames 6..11: strength 0.60 -> 0.75, pixel-blend 0% -> 40% toward anchor.
  - frames 12+: strength 0.75 -> 0.80, pixel-blend 40% -> 85% toward anchor.
  Pixel blend is direct image-space alpha onto the saved `anchor_img`. Pipeline.md is wrong about this.
- `phase_b_upscale(...)`: Real-ESRGAN x2 over the keyframes dir.
- `phase_c_interpolate(...)`: RIFE pair-by-pair with `linear_interp(model, prev, curr, RIFE_PASSES)` (no `skip_boundary`, so it defaults to 0), **writes both source keyframes and interp frames** into the output, then computes a wrap-around set of interps between the last and first keyframe and appends them (minus the last, which equals the first frame) for seamless looping. `EDGE_CROP=8` is applied to every frame before write. Streams straight to the MP4 writer; no in-memory frame buffer.
- `phase_d_encode_only(...)`: writes keyframes directly to MP4 without RIFE.

**CLI surface (`main`).**

- `--all` / `--excerpt EID...` / `--section I..VII`: target selection.
- `--phase {A,B,C,D}`: run a single phase only.
- `--no-rife`, `--no-esrgan`, `--no-lora`: disable phases / fresco LoRA.
- `--preview`: short test run.
- `--benchmark`: loads SDXL + Lightning, generates 3 test frames, prints peak VRAM, exits.
- `--quality N` (0..10): libx264 quality slider.
- `--resume`: skip already-completed phases per excerpt.

**Relationship to other scripts.** Engine. `generate_subject_test.py` and the two horizontal scripts import a curated subset of helpers from it. After Cole monkey-patches its module-level constants (`LORA_CANDIDATES`, `LORA_SCALE`, `STYLE_PREFIX/SUFFIX`) before delegating.

### generate_horizontal.py (573 lines)

Horizontal (1344 x 768) landscape variant. The file's own docstring is misleading ("only difference: resolution"). It also overrides frame counts dramatically and uses a gentler return scheme. Imports the SDXL helpers from `generate_videos.py` and the `evolved_noise_blend` / `TRANSITION_STRENGTHS` / `TRANSITION_NOISE_RAMP` from the **missing** `generate_crown_video` module.

**Module-level state.** A single `SUBJECTS` dict with ~25 subjects: most are `EXX_topic` keys (E05 through E31) plus three named ones used in the sample outputs:

- `notturno` (notturno_city)
- `siege` (siege_harbour)
- `harbour` (harbour_market)

Each subject is a list of 4 prompts (A, B, C, A-return) with a per-prompt `denoising` value (0.470 to 0.500 range) that is **read but never used** by the generation loop (which uses `STEADY_STRENGTHS` instead). The per-prompt field is leftover from an older non-cycling scheme; safe to drop in the port.

Also a module-level `NEG_PROMPT` (a single string disallowing religious / angelic / nude imagery) passed to `encode_prompt`.

**`main()` constants (after argparse).**

| Constant | Value | Controls |
|---|---|---|
| `GEN_WIDTH`, `GEN_HEIGHT`, `TARGET_SIZE` | 1344, 768, (1344,768) | Landscape resolution. |
| `STEADY_FRAMES` | 5 | Per-segment steady frames. ~10x fewer than portrait (54). The math: 5 steady * 3 segments + 3 trans * 2 + 4 return + 1 anchor = 26 keyframes; at RIFE 64x with `skip_boundary=4` that yields ~60s at 24 fps. |
| `TRANSITION_FRAMES`, `RETURN_FRAMES`, `WARMUP_FRAMES` | 3, 4, 3 | Transition / return / warmup. |
| `STEADY_STRENGTHS` | `[0.55, 0.55, 0.60, 0.55, 0.55, 0.65, 0.55, 0.60]` | Same cycle as `generate_videos.py`. |
| `OUTPUT_DIR` | `videos/horizontal/` | |
| `STAGING_DIR` / `kf_dir` | `videos/staging/<name>/keyframes/` | |

**CLI surface.**

- `--subject KEY` (required, choices = `SUBJECTS.keys()`).
- `--list`: print subjects and exit.
- `--tag STR`: appended to output filename.
- `--smooth-sigma FLOAT` (default 1.5), `--smooth-window INT` (default 8): passed to `temporal_smooth_keyframes`.
- `--transition-strength FLOAT` (default 0): if >0, overrides the constant 0.65 used during inter-segment transitions.
- `--skip-boundary INT` (default 4): RIFE `t<=4` and `t>=59` frames are dropped per pair, cutting the deceleration zones.
- `--sinusoidal`: cosine spacing of RIFE timesteps (rarely used).
- `--no-lora`: skip fresco LoRA.

**Departures from pipeline.md and from `generate_videos.py`.**

- Uses a **single** transition strength (0.65 or `--transition-strength`), not the `[0.65, 0.72, 0.80, 0.80, 0.72, 0.65]` ramp documented in pipeline.md. Despite importing `TRANSITION_STRENGTHS`, the value is unused.
- Uses a **single** transition noise (`NOISE_BLEND_TRANSITION` = 0.15), not the `[0.15, 0.25, 0.35, 0.35, 0.25, 0.15]` ramp.
- Return segment is much gentler than `generate_videos.py`: strength ramps 0.50 -> 0.60 linearly with `progress`, pixel-blend ramps quadratically to a **max of 20%** (not 85%).
- Noise blend uses `evolved_noise_blend(img, blend_pct=...)` from the missing `generate_crown_video`, not the `edge_weighted_noise_blend` defined in `generate_videos.py`. The shape and behavior of `evolved_noise_blend` is therefore opaque from the clone alone.
- `linear_interp` is called with `skip_boundary=args.skip_boundary` (default 4) **and** keyframes are not written to the output (only the interpolated frames are). Pipeline.md's "skip keyframes" description matches this path, but `generate_videos.py` itself does the opposite.
- Wrap-around loop closure: yes, last->first interp appended (minus final t=1 frame).

### generate_horizontal_calm.py (572 lines)

Single-character diff: a calmer denoise schedule and noise budget. Used for `harbour_market_horizontal_calm.mp4` and `notturno_city_horizontal_calm.mp4`.

**Deltas vs `generate_horizontal.py`.**

| Field | horizontal | calm |
|---|---|---|
| `STEADY_STRENGTHS` | `[0.55, 0.55, 0.60, ...]` (avg ~0.575) | `[0.50, 0.50, 0.52, 0.50, 0.50, 0.54, 0.50, 0.52]` (avg ~0.51) |
| `NOISE_BLEND_CALM` | n/a (uses `NOISE_BLEND_CENTER`=0.08) | 0.04 (half) |
| `NOISE_BLEND_TRANSITION_CALM` | 0.15 | 0.08 (half) |
| `STRUCTURAL_DECAY_RADIUS` | 2 | 0 (no pre-blur, prevents focus loss) |
| `NOISE_WALK_RATE_CALM` | n/a | 0.02 (slower noise temporal evolution; param of `evolved_noise_blend`) |
| Return strength ramp | 0.50 -> 0.60 | 0.48 -> 0.55 |
| Transition strength | 0.65 | 0.52 |
| `--smooth-sigma` default | 1.5 | 1.8 |
| `SUBJECTS` | E05..E31 + notturno + siege + harbour | E05..E31 + notturno + harbour (siege dropped) |

These five constants (`NOISE_BLEND_CALM`, `NOISE_BLEND_TRANSITION_CALM`, `STRUCTURAL_DECAY_RADIUS_CALM`, `NOISE_WALK_RATE_CALM`, plus the calmer `STEADY_STRENGTHS` and the lower transition/return ceilings) define what "calm" is. They're the cleanest A/B baseline for the port: a calm-mode boolean (or denoise profile) should toggle them as a group.

### generate_subject_test.py (574 lines)

Portrait subject-test harness. Same body as `generate_horizontal.py` minus the resolution swap. Inherits portrait `GEN_WIDTH`/`GEN_HEIGHT` from `generate_videos.py`.

**Deltas vs `generate_horizontal.py`.**

- Portrait resolution (768 x 1344).
- `--full` flag: when set, `STEADY=17, TRANSITION=6, RETURN=16` (~3 min at 64x). When unset (test mode), `STEADY=12, TRANSITION=3, RETURN=6`. Both larger than horizontal's 5/3/4.
- Output to `videos/sessions/` if `--full`, else `videos/`.
- `SUBJECTS` overlaps with `generate_horizontal.py` but has additional entries (E06, E08, E10, E12, E13...) and lacks the horizontal-only `siege`/`harbour`/`notturno` keys.
- No `--no-lora` flag. LoRA is always fused if found.
- Otherwise identical loop. Same import from the missing `generate_crown_video`.

**Relationship.** The progenitor of `generate_horizontal.py`. The header docstring of `generate_horizontal.py` confirms this ("Horizontal fork of generate_subject_test.py"). For the port, either is a fine starting template; the two should collapse into one orientation-parameterized renderer.

## legacy/after-cole/

The thinnest possible cross-project wrapper, demonstrating the "minimum diff for a new style" pattern.

### generate_horizontal_tcole.py (326 lines)

Adapter that swaps the fresco stack for a Thomas Cole stack and delegates to `generate_horizontal.main()`.

**Module-level state.**

| Constant | Value | Controls |
|---|---|---|
| `TCOLE_LORA_DIR` | `BASE_DIR / "visuals" / "lora-datasets" / "thomas-cole" / "checkpoints"` | Where the Thomas Cole epoch checkpoints live. Note this is **inside the After Cole repo**, not under Choire v1 `visuals/`. |
| `TCOLE_LORA_CANDIDATES` | `Thomas_Cole_epoch_10.safetensors`, `Thomas_Cole_epoch_1.safetensors` | Strong then light fallback. The `--epoch` flag picks one. |
| `TCOLE_STYLE_PREFIX` | `"tcole, romantic landscape oil painting, Hudson River School style, "` | Trigger word `tcole` is the LoRA's caption format. |
| `TCOLE_LORA_SCALE_DEFAULT` | 0.75 | Higher than fresco's 0.35 because Thomas Cole was trained from scratch on the SDXL base, not on top of a domain-tuned base. |
| `TCOLE_SUBJECTS` | five subjects: `tcole_ruins`, `tcole_valley`, `tcole_cloudship`, `tcole_horses`, `tcole_siege` | Each A/B/C/A-return as long oil-painting prompts. |

**Adapter logic in `main()`.**

1. Parse `--lora-scale` and `--epoch` with `add_help=False` and `parse_known_args`, keep the rest as `passthrough_args`.
2. Pick the epoch checkpoint, fail if missing.
3. **Monkey-patch** `generate_videos`'s module-level constants:
   - `gv.LORA_CANDIDATES = [lora_path]`
   - `gv.LORA_SCALE = our_args.lora_scale`
   - `gv.STYLE_PREFIX = TCOLE_STYLE_PREFIX`
   - `gv.STYLE_SUFFIX = TCOLE_STYLE_SUFFIX`
4. Import `generate_horizontal` (which imports those constants from `generate_videos`) and `dict.update` its `SUBJECTS` with `TCOLE_SUBJECTS`.
5. Rewrite `sys.argv` to `passthrough_args` and call `generate_horizontal.main()`.

**CLI surface.**

- `--lora-scale FLOAT` (default 0.75): own arg.
- `--epoch {1,10}` (default 10): own arg.
- Anything else: passed through to `generate_horizontal.main()` (`--subject`, `--tag`, `--smooth-sigma`, `--smooth-window`, `--transition-strength`, `--skip-boundary`, `--sinusoidal`, `--no-lora`).

**Relationship.** The After Cole pattern. It demonstrates that swapping LoRA + prefix + subjects is sufficient to retarget the pipeline. The port should preserve this capability without monkey-patching: a `Style` config object that bundles LoRA path, scale, prefix, suffix, negative prompt.

### generate_thomas_cole_video.py (191 lines)

Pre-pipeline prototype. Different stack entirely: SDXL **Turbo** (not Lightning), `guidance_scale=0.0`, RIFE **HDv3 3 passes (8x)** recursive (not v4.25 64x linear), output 8 fps. PROMPTS is a flat list of 5 narrative phases (morning / golden hour / overcast / sunset / twilight) with no A/B/C structure and no SLERP. LoRA from `visuals/lora_weights/thomas_cole.safetensors` (not the After Cole epoch tree). No anchor return, no temporal smoothing, no edge suppression, no SLERP, no wrap-around loop closure.

This is an earlier experiment kept for reference. It is **not** the technique. Inventory.md previously suggested it was an "alternative entry point" to After Cole; it isn't. Treat it as archaeological.

### LORA-USAGE.md

Reference card for the Thomas Cole SDXL LoRA: trigger word `tcole`, two checkpoints (epoch 1 light at 0.4 to 0.6 scale, epoch 10 strong at 0.7 to 0.9), prompt vocabulary (Hudson River School, Cole's own subjects, common modifiers), known limitations, dataset notes. The Renoir LoRA should have an equivalent doc once trained.

## legacy/choire-v2/research/

Three Choire v2 docs cloned for their direct bearing on this technique. Step 2 of the kickoff session reads these closely and back-feeds them into `pipeline.md`.

| File | Purpose |
|---|---|
| `video-pipeline-best.md` | THE canonical reference. Dated 2026-03-31. The "A1 best" configuration, every parameter, what each fix solved, and an extensive "what didn't work" list. The primary input for [pipeline.md](pipeline.md). |
| `video-generation-iterations.md` | Iteration log: why each setting is what it is. |
| `frame-interpolation.md` | RIFE selection and configuration notes. |

## legacy/comfy-archive/

`interpolate-easy.original.json` and a README. Unrelated SD 1.5 + AnimateLCM + IPAdapter experiment. Different stack, different aesthetic, kept for reference only. **Not** the technique this repo is built around.

## examples/outputs/

Detailed annotations are in [outputs.md](outputs.md).

### From After Cole (Hudson River School, horizontal, 1344 x 768)

`tcole_cloudship_horizontal.mp4`, `tcole_cloudship_horizontal_v2.mp4`, `tcole_horses_horizontal.mp4`, `tcole_ruins_horizontal_test1.mp4`, `tcole_siege_horizontal.mp4`, `tcole_valley_horizontal.mp4`, `tcole_valley_horizontal_v2.mp4`.

### From Choire v2 (Italian fresco, horizontal, 1344 x 768)

`cole_valley_horizontal.mp4`, `cole_valley_horizontal_v2.mp4`, `harbour_market_horizontal.mp4`, `harbour_market_horizontal_calm.mp4`, `notturno_city_horizontal.mp4`, `notturno_city_horizontal_calm.mp4`, `siege_harbour_horizontal.mp4`, `E14_lake_horizontal.mp4`, `E24_garden_horizontal.mp4`.

The two `_calm` pairs (`harbour_market` and `notturno_city`) are the cleanest A/B comparisons of the calm-vs-standard denoise schedule.

## What is NOT in this repo

Deliberately excluded:

- Adjacent narrative projects by the same author (out of scope for this repo).
- Choire v2 audio / voice / installation code (RVC, ace-step, CosyVoice, assolo, carriers).
- LoRA training datasets (Renoir dataset will be built fresh).
- LoRA `.safetensors` checkpoints (large binaries, gitignored).
- The `prompt_engine.py` and `generate_crown_video.py` modules the legacy scripts import. They live in the source Choire v2 repo. The port resolves this by absorbing the small handful of helpers it actually needs (`evolved_noise_blend`, transition ramps) and dropping the `prompt_engine` dependency entirely (we don't need 54-excerpt scheduling).

## Pipeline.md discrepancies (resolved in Step 2)

To be applied to [pipeline.md](pipeline.md) after the Step 2 research-doc read:

1. **Resolution.** Pipeline.md gives portrait dimensions for Choire v2 but doesn't state that the horizontal entry points (the ones that produced every cloned sample output) flip to 1344 x 768 and run with much smaller frame counts (5/3/4 vs. 54/6/16). All `examples/outputs/` mp4s are horizontal.
2. **Frame counts.** Pipeline.md cites the portrait engine values (54 / 6 / 16). The actual horizontal-pipeline values are 5 / 3 / 4 (with 3 segments => 26 keyframes => ~60s at 64x RIFE / 24 fps / skip_boundary 4). Add an orientation table.
3. **Anchor return.** Pipeline.md says "Anchor return strength: 0.75" (single value). Reality:
   - `generate_videos.py` engine: three-phase ramp (0.50 -> 0.58 / 0.60 -> 0.75 / 0.75 -> 0.80) with pixel-space alpha blend toward anchor rising to **85%** in the final phase.
   - `generate_horizontal.py`: gentler. Linear 0.50 -> 0.60 strength with quadratic pixel blend capped at **20%**.
   - `generate_horizontal_calm.py`: gentler still. 0.48 -> 0.55 strength, same 20% pixel cap.
   The `ANCHOR_RETURN_STRENGTH = 0.75` constant in the engine is dead code.
4. **Transition strengths.** Pipeline.md gives the engine's `[0.65, 0.72, 0.80, 0.80, 0.72, 0.65]` ramp. The horizontal entry points (everything that produced the sample outputs) instead use a **single constant 0.65** (or 0.52 in calm), and ignore the ramp.
5. **Transition noise.** Same story. Engine ramps `[0.15, 0.25, 0.35, 0.35, 0.25, 0.15]`. Horizontal scripts use a single constant 0.15 (or 0.08 in calm).
6. **Skip keyframes.** Pipeline.md says "only the interpolated frames are written into the final sequence (the source keyframes are discarded)". This is true for the horizontal scripts. The `generate_videos.py` engine, by contrast, writes both keyframes and interp frames into the MP4. The "skip keyframes" recipe lives in the entry points, not the engine.
7. **Skip boundary.** Pipeline.md says "4 frames at each end of every pair are dropped". True for the horizontal scripts (`--skip-boundary 4` default). The engine calls `linear_interp` without `skip_boundary`, defaulting to 0.
8. **Temporal smoother defaults.** Pipeline.md cites `sigma=1.5, window=8`. These are the horizontal-script CLI defaults. The engine function defaults are `sigma=1.0, window=5`. Calm uses `sigma=1.8`.
9. **Noise path.** Pipeline.md says "uniform Gaussian noise". The actual horizontal-script path is `evolved_noise_blend` from the missing `generate_crown_video` module, with a `walk_rate` parameter (0.05 standard, 0.02 calm) suggesting temporally evolving noise rather than per-frame independent random pixels. Until we recover this module's source, the noise model is partly opaque. The engine's `edge_weighted_noise_blend` (uniform per-frame uint8) is **not** the production path that made the sample outputs.
10. **Loop closure.** Pipeline.md doesn't mention the **RIFE wrap-around** at the end of phase C: a 63-frame interp sequence between the final keyframe and the first keyframe (minus the t=1 frame, which is the first frame) appended to the MP4 so the loop closes seamlessly. Critical to how the videos play; should be in the spec.
11. **LoRA scale range.** Pipeline.md says "0.35 to 0.75". Concrete values: fresco at 0.35, Thomas Cole at 0.75 default (was trained from scratch). Worth stating both, with the reason for the gap.
12. **LCM dropping.** The script imports of `EulerDiscreteScheduler` with `timestep_spacing="trailing"` and the comment "CFG re-enabled (Turbo was 0.0 — root cause of subject collapse)" tell the story: the lineage went Turbo -> Lightning, not LCM. Pipeline.md is correct on Lightning but `docs/dev-setup.md` and `docs/context.md` still reference the SD1.5 + AnimateLCM stack from `comfy-archive/`. Those two docs need correcting in Step 5.
