# Video Generation Iterations — Obstacle Log

**Date range:** 2026-03-17 to 2026-03-20
**File:** `Choire-v2/generate_videos.py`
**Goal:** Pre-rendered seamless-loop MP4 videos per reading excerpt. Portrait format, fresco aesthetic, 3-minute loops, smooth morphing between AI-generated images.

---

## Current State (v14 / A1, 2026-04-05)

**Pipeline:** SDXL base + Lightning 4-step LoRA + fresco LoRA (0.35) + TAESD at 768x1344 → freq-separated temporal smoothing → RIFE v4.25 linear 64x → H.264 at 24fps. No upscaling.

**Production:** 25 session videos generated, 19 approved, 6 need rework. See `video-pipeline-best.md` for full spec and status.

**Scripts:** `generate_subject_test.py` (vertical 768x1344), `generate_horizontal.py` (horizontal 1344x768)

---

## Obstacle 1: Square Format (RESOLVED)

**Problem:** Videos were 512x512 square, need vertical for installation screen.

**Attempts:**
1. ~~576x1024 portrait~~ — off SDXL training grid, amplified border artifacts
2. ~~512x896 portrait~~ — also off-grid, VRAM tight at 7.62 GB
3. ~~768x768 square + center crop to 432x768~~ — works but discards 44% of pixels
4. **768x1344 native portrait** — official SDXL training bucket (4:7). TAESD at 6.80 GB, 1.20 GB headroom. **CURRENT**

---

## Obstacle 2: VAE Precision vs VRAM (RESOLVED)

**Problem:** Full SDXL VAE at portrait resolution either OOMs (fp32 upcast) or produces NaN (fp16).

**Attempts:**
1. ~~Full VAE fp16~~ — produces NaN (`invalid value encountered in cast`), all-black keyframes
2. ~~Full VAE fp32 upcast~~ — OOMs at 512x896 (>8 GB)
3. ~~Full VAE bf16~~ — works but 7-bit mantissa produces blurry output
4. ~~fp16 UNet + bf16 VAE~~ — dtype mismatch crash (`Half vs BFloat16`)
5. **TAESD (madebyollin/taesdxl)** — fp16, ~6.4-6.8 GB, fast decode, proven in 768_smooth. **CURRENT**

---

## Obstacle 3: Blurry Output (RESOLVED)

**Problem:** Videos were incredibly blurry.

**Root causes identified:**
- `structural_decay(radius=3)` — Gaussian blur compounding over 54 frames at 50% preservation
- `temporal_smooth_keyframes()` — Phase A.5 averaged ±3 neighboring keyframes, destroying detail
- bf16 VAE — 7-bit mantissa produced softer decode than fp16

**Fixes applied:**
1. Removed `temporal_smooth_keyframes()` call entirely
2. Reduced `STRUCTURAL_DECAY_RADIUS` from 3 to 2 (768_smooth value)
3. Switched to TAESD (eliminates VAE precision issue entirely)

---

## Obstacle 4: Rhythmic Speed Curvature / Steppiness (PARTIALLY RESOLVED)

**Problem:** Video motion had perceivable rhythmic pulsing — acceleration mid-interpolation, slowdown near keyframes.

**Root causes identified:**
1. Random pixel noise (not temporally coherent) — RIFE's optical flow detects false micro-motion
2. `REFRESH_INTERVAL=18` denoising spikes — creates periodic acceleration every 2.25s
3. Deterministic 3-frame jitter cycle `((fi % 3) - 1) * 0.02` — creates repeating visual pattern
4. RIFE HDv3 binary-tree interpolation — midpoint-only produces ease-in-ease-out curves

**Fixes applied:**
1. ~~Coherent simplex noise~~ — replaced random noise, but pure Python loop was catastrophically slow (12 hours). Vectorized version fixed speed but reverted to random noise (768_smooth proves random works)
2. Removed `REFRESH_INTERVAL` / `REFRESH_BOOST` — no more periodic denoising spikes
3. Replaced deterministic jitter with Gaussian random (σ=0.01) — later reverted to 768_smooth cycling schedule
4. RIFE 16x (4 passes) keeping all frames — 2x more interpolated frames for smoother motion
5. ~~RIFE 16x subsampled to 8x~~ — attempted to halve speed curvature amplitude, reverted to keeping all frames

**Current approach:** 768_smooth proven parameters (cycling strength schedule, 8% noise, 16x RIFE, 12fps). Steppiness reduced but not fully eliminated. Research identified RIFE v4 (rife47/rife49) with arbitrary timestep as the principled fix (not yet implemented).

---

## Obstacle 5: Frame / Arch Border Artifacts (UNRESOLVED)

**Problem:** Decorative arch-like frames appear at image edges, persist across entire video due to img2img chain propagation. Present with AND without LoRA.

**Root causes identified:**
1. SDXL training data associates "fresco", "painting", "Renaissance" with framed artworks
2. LoRA (trained on Casa del Suono frescoes with arched architecture) amplifies arch bias
3. Off-grid resolutions (576x1024, 512x896) trigger SDXL art-book layout defaults
4. img2img chain lock-in: once border appears in frame 1, it propagates at strength 0.42-0.55
5. Negative prompts have zero effect at CFG=0 (SDXL Turbo)

**Attempts:**
1. ~~`no frame, full bleed, no border` in positive prompt~~ — limited effect at CFG=0
2. ~~Removed LoRA entirely~~ — frames still appear (SDXL base bias)
3. ~~Edge crop 4px after RIFE~~ — too small, arches are larger
4. ~~Edge crop 8px~~ — slightly better but arches extend deeper
5. ~~768x768 square generation + portrait center crop~~ — discards 44% pixels, still had frames in square
6. ~~110% zoom-and-crop before portrait cut~~ — removes outer ring but wastes pixels
7. ~~Reduced LoRA scale from 0.7 to 0.35~~ — less arch bias but frames persist from base model
8. ~~768x1344 native portrait (on SDXL training grid)~~ — eliminates off-grid trigger but frames still appear
9. **Edge-weighted noise blend (30% at edges, 8% center, 64px gradient)** — CURRENT, disrupts edge lock-in but frames still appear

**Not yet tried:**
- Latent space masking via `callback_on_step_end` — noise-out outer latent pixels each denoising step
- Mirror padding of init image — reflect center content outward so model has no edge signal
- Post-generation edge replacement — replace outer ring with blurred inner content before next img2img step
- LoRA retraining with pre-cropped images and "no frame" captions
- Style prefix without "fresco" / "painting" (test if removing art-category words eliminates frame bias)

---

## Obstacle 6: Prompt Subjects Not Working (UNRESOLVED)

**Problem:** SDXL Turbo at 1-2 steps doesn't render specific objects reliably. Prompts produce generic walls, stairs, plaster textures instead of the intended Calvino narrative subjects.

**Root causes identified:**
1. At 1-2 inference steps, SDXL handles mood/atmosphere well but loses fine spatial details, counts, and specific object rendering
2. Tag-list prompts (SD 1.5 style) don't work — SDXL needs natural language sentences
3. Too many competing objects (6-8 props) — SDXL reliably handles 1-2 subjects at 1-2 steps
4. Action verbs ("tumbling", "scattered") ignored at 1-2 steps — only static states rendered
5. "Candlelight" becomes dominant subject (literal candles rendered) instead of light modifier
6. Literal isolated objects (stairs alone, staff alone) read as generic geometry

**Attempts:**
1. ~~Original prompts (tag lists, 8 objects)~~ — compositional failures, random object salad
2. ~~SDXL-optimized structure (style-first, mood-driven, 1-2 subjects)~~ — too abstract, generic plaster geometry
3. ~~Text-worker Calvino analysis (vertiginous stillness, unyielding weight)~~ — atmospheric but subjects unrecognizable
4. ~~Removed "candlelight"~~ — replaced with "warm amber light/glow", slightly better
5. **Story-grounded atmospheric (gilded seat + staff + stone steps in atmospheric context)** — CURRENT, subjects still collapse to walls and stairs

**Not yet tried:**
- Compel prompt weighting `(keyword:1.2)` to emphasize specific subjects
- Separate prompt engineering per segment (not reusing section base + phase concatenation)
- Hand-written prompts per excerpt (bypass prompt engine entirely for testing)
- Higher inference steps (3-4 instead of 2) for better prompt adherence
- Different base model (SDXL Lightning 4-step instead of Turbo 1-2 step)

---

## Obstacle 7: File Size (RESOLVED)

**Problem:** E01.mp4 was 1.5 GB for 3 minutes.

**Fix:** Changed encoding quality from 9 to 5 (CRF ~23). Current videos 26-93 MB depending on resolution.

---

## Obstacle 8: Seamless Loop (RESOLVED)

**Problem:** Video didn't loop back to first frame seamlessly.

**Fix:** 16-frame extended return transition with progressive convergence (SLERP embeddings + pixel blend up to 85% toward anchor) + anchor frame appended + RIFE wrap-around interpolation between last and first frames. Loop is seamless.

---

## Obstacle 9: Generation Speed (RESOLVED)

**Problem:** Coherent simplex noise made Phase A take 12 hours.

**Fix:** Vectorized opensimplex (`noise3array`), then reverted to random pixel noise entirely (768_smooth proves it works). TAESD also dramatically faster than full VAE (1-2 min for Phase A vs 20-30 min).

---

## Obstacle 10: RAM Exhaustion in Phase C (RESOLVED)

**Problem:** Holding 3055 frames at 1536x2688 in memory = ~37 GB RAM → numpy allocation error.

**Fix:** Streaming RIFE encoder — process pair-by-pair, write each interpolated frame directly to imageio writer. Constant ~50 MB RAM instead of 37 GB.

---

## What Worked Well

1. **768_smooth parameter recipe** — cycling strength schedule `[0.42, 0.42, 0.48, 0.42, 0.42, 0.55, 0.42, 0.48]`, 8% noise, 15% transition noise
2. **TAESD** — fast, no precision issues, 6.4 GB VRAM
3. **RIFE 16x at 12fps** — smoothest interpolation
4. **Noise sweep during transitions** `[0.15, 0.25, 0.35, 0.35, 0.25, 0.15]` — effectively reshapes composition between prompts
5. **Seamless loop** — anchor convergence + RIFE wrap-around works perfectly
6. **Streaming RIFE encoder** — constant RAM usage at any resolution
7. **SDXL training bucket resolutions** (768x768, 768x1344) — fewer artifacts than off-grid sizes

---

## Current Pipeline Summary

```
Phase A: SDXL Turbo + TAESD (fp16) at 768x1344
         LoRA 0.35 (Casa del Suono fresco style)
         Cycling strength schedule [0.42-0.55]
         Edge-weighted noise (8% center, 30% edges, 64px gradient)
         Structural decay radius=2
         54 steady + 6 transition + 16 return + 1 anchor = 191 keyframes
         ~2 min

Phase B: Real-ESRGAN x2 (768x1344 → 1536x2688)
         Tiled (384px), half precision
         ~7 min

Phase C: RIFE HDv3 16x (streaming pair-by-pair to H.264 encoder)
         8px edge crop after RIFE
         12fps, quality=5
         ~20 min

Total: ~29 min per excerpt, ~93 MB output
```

---

## Research References

- `Choire-v2/research/realtime-visuals.md` — SDXL Turbo benchmarks, resolution limits
- `Choire-v2/research/frame-interpolation.md` — RIFE benchmarks, HDv3 vs v4
- `Choire-v2/research/smooth-transitions.md` — compel prompt blending, transition techniques
- Research agent findings (2026-03-19): SDXL prompting best practices, RIFE v4 timestep control
- Research agent findings (2026-03-19): Frame artifact elimination techniques (latent masking, mirror padding, zoom-crop)

---

## Deep Research (2026-03-20) — New Tools & Approaches

### Implemented in v13

1. **SDXL Lightning 4-step LoRA** — [ByteDance/SDXL-Lightning](https://huggingface.co/ByteDance/SDXL-Lightning). Replaces Turbo. CFG=1.5 re-enables subject adherence. Same VRAM. Scheduler: EulerDiscreteScheduler, trailing timesteps.
2. **crops_coords_top_left=(256,256)** — SDXL micro-conditioning. Tells model "center crop" origin, correlates with frameless interior content in training data.
3. **Latent edge masking callback** — `callback_on_step_end` replaces outer 4 latent pixels with interior mean each denoising step. Feathered mask prevents halo.
4. **STYLE_PREFIX cleanup** — Removed "still life", "no people", "no frame, full bleed" which contradicted subject rendering.

### Available but not yet implemented

**Models:**
- Hyper-SDXL 4-step LoRA ([ByteDance/Hyper-SD](https://huggingface.co/ByteDance/Hyper-SD)) — best CLIP score, CFG=3.0, same VRAM. A/B test vs Lightning.
- DMD2 4-step LoRA ([tianweiy/DMD2](https://github.com/tianweiy/DMD2)) — NeurIPS 2024 Oral, highest photorealism FID.
- FLUX Schnell — superior subjects but REJECTED (40-60s/img on 8GB, too slow).

**Border artifact elimination:**
- PAG (Perturbed Attention Guidance) — [arXiv:2403.17377](https://arxiv.org/abs/2403.17377). Disrupts self-attention frame patterns. ~30% overhead. Zero VRAM. `enable_pag=True, pag_scale=1.5`.
- Late-stage circular padding — [Arrexel/pattern-diffusion](https://huggingface.co/Arrexel/pattern-diffusion). Activate circular conv padding after 65% of steps. Model can't perceive edges.
- ControlNet Tile — [xinsir/controlnet-tile-sdxl-1.0](https://huggingface.co/xinsir/controlnet-tile-sdxl-1.0). Structural constraint from blurred interior. +1.5 GB (needs venue GPU).
- Overscan+crop — Generate 1024x1344, crop center to 768x1344. Guaranteed frame removal, wastes 25% pixels.
- LoRA retraining — Pre-crop all training images 15-20% from edges before training.

**Subject anchoring:**
- Control-LoRA Rank 128 Canny — [stabilityai/control-lora](https://huggingface.co/stabilityai/control-lora). 380 MB, fits in VRAM (6.96 GB total). Pre-draw subject compositions, extract Canny edges, apply at scale=0.5.
- IP-Adapter + InstantStyle — [tencent-ailab/IP-Adapter](https://github.com/tencent-ailab/IP-Adapter). 848 MB, VRAM-tight. Activate only `down_blocks.2.attentions.1` for composition without style contamination.
- ADetailer two-pass — YOLO subject detection + inpaint crop at 4-6 steps. ~1-2s overhead per triggered frame.
- LayerDiffusion — [lllyasviel/sd-forge-layerdiffuse](https://github.com/lllyasviel/sd-forge-layerdiffuse). Pre-render transparent subject layers, composite in browser. Zero runtime VRAM.

**Pipeline upgrades:**
- RIFE v4.25 — [hzwer/Practical-RIFE](https://github.com/hzwer/Practical-RIFE). Two versions newer than HDv3. Drop-in upgrade.
- FLAVR — 3D CNN interpolator, no optical flow, single-pass multi-frame. May outperform RIFE on slow fresco content.
- SeedVR2 v2.5 — [ByteDance-Seed/SeedVR](https://github.com/ByteDance-Seed/SeedVR). Diffusion upscaling with temporal consistency. ESRGAN replacement. 8GB via GGUF.

**Looping:**
- Wan2.1 VACE — Post-process loop closure. Explicitly generates transition between last/first frames. Better than anchor convergence.
- Mobius latent shift — [YisuiTT/Mobius](https://github.com/YisuiTT/Mobius). SIGGRAPH 2025. Latent noise cycle for seamless looping. CogVideoX-5B base (16GB, not viable on 8GB). Concept transferable.

---

## Obstacle 11: ESRGAN Style Destruction (RESOLVED)

**Problem:** Real-ESRGAN x2 destroyed the fresco aesthetic when upscaling 768x1344 → 1536x2688. Gemini rated fresco authenticity 3/10 after ESRGAN vs 8/10 native. Over-sharpened edges, geometric artifacts, cubist appearance.

**Fix:** Removed upscaling entirely. 768x1344 native is production resolution. Also tested SDXL img2img upscale (str=0.26/0.35/0.50) — native still better. 11 upscalers evaluated, all rejected.

---

## Obstacle 12: Subject Drift Between Prompts (RESOLVED)

**Problem:** When A/B/C prompts described different framings of the same subject (wide/closeup/side view), SDXL drifted to completely different subjects during transitions. E.g., throne morphed into columns.

**Fix:** A/B/C prompts now describe the SAME composition with ONLY lighting variation (amber/candlelit/dusk). Subject text stays identical, only the lighting description at the end changes.

---

## Obstacle 13: Isolated Object Subjects (RESOLVED)

**Problem:** Prompts like "crown on plinth, dark background" left most of the frame empty. The videos lacked the richness of environmental scenes (city scored 9/10). Objects looked basic and uninteresting.

**Fix:** All prompts now embed subjects within rich palace environments (frescoed walls, vaulted ceilings, stone columns, tapestries). The environment fills the entire frame. Environmental/architectural subjects consistently outperform isolated objects.

---

## Obstacle 14: Water Reflection Prompt (UNRESOLVED)

**Problem:** Prompt "closeup of a still body of water reflecting the face of a crowned king distorted by gentle ripples" produced a portrait, not a water reflection. SDXL interpreted "reflection" as a style modifier, not a physical setup.

**Attempted fix:** Rewrote as "looking straight down at a dark still pond, the surface of the water filling the entire frame, water lily pads and reeds at the edges, the distorted upside-down reflection of a crowned king visible in the water" — awaiting test.

**Root cause:** SDXL at 4 steps cannot reliably render conceptual visual mechanisms (reflections, shadows as subjects). Prompts must describe the physical camera position and setup, not the concept.

---

## Obstacle 15: RIFE Binary Midpoint Flash (RESOLVED)

**Problem:** Gemini confirmed a rhythmic 1.3s "detail flash" in all generated videos. The flash cadence matched the RIFE binary recursive midpoint, not keyframe boundaries.

**Root cause:** RIFE's recursive binary splitting calls model.inference() at t=0.5 first (trained distribution peak), then t=0.25/0.75 (increasingly out-of-distribution). The t=0.5 frame is systematically sharper.

**Fix:** Replaced `recursive_interp()` with `linear_interp()` — calls RIFE with evenly-spaced timesteps [1/64, 2/64, ..., 63/64] directly. All frames generated from the same (img0, img1) pair with no error cascade. Upgraded from RIFE HDv3 to v4.25.

---

## Obstacle 16: Keyframe Sharpness Stalls (RESOLVED)

**Problem:** SDXL keyframes are sharper than RIFE-interpolated frames. When a keyframe appears in the output, it creates a visible "snap to clarity" every ~2.6 seconds.

**Fix:** Skip keyframes from output — write ONLY the RIFE interpolated frames. All frames now have consistent softness. Combined with skip-boundary-4 (drop first/last 4 RIFE frames per pair) to eliminate deceleration zones.

---

## Obstacle 17: Rough Loop Closure (RESOLVED)

**Problem:** The return-to-anchor segment used aggressive pixel blending (up to 85% toward anchor frame), creating a visible "snap" at the loop point.

**Fixes applied:**
1. Reduced max blend from 85% → 40% (first fix)
2. Further reduced to 20% with quadratic ease-in curve (final fix)
3. RIFE handles the remaining gap smoothly via wrap-around interpolation
