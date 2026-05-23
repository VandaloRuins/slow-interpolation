# Video Pipeline — Best Configuration (A1)

**Date:** 2026-03-31 (updated from 2026-03-24)
**Status:** CURRENT BEST — continuous motion, no frame pauses, no upscaling

## Winning Configuration: A1 (Throne test)

### Generation (Phase A)
- **Model:** SDXL base + Lightning 4-step LoRA + fresco LoRA (scale=0.35)
- **Scheduler:** EulerDiscreteScheduler, timestep_spacing="trailing"
- **CFG:** guidance_scale=1.5
- **Steps:** num_inference_steps=4
- **Steady strengths:** [0.55, 0.55, 0.60, 0.55, 0.55, 0.65, 0.55, 0.60]
- **Transition strengths:** [0.65, 0.72, 0.80, 0.80, 0.72, 0.65]
- **Noise:** uniform 8% (no edge weighting)
- **Structural decay:** radius=2
- **Border suppression:** crops_coords_top_left=(256,256) + latent edge masking callback
- **Negative prompt:** angel, wings, halo, saint, nude, naked, bare chest, exposed skin, shirtless, undressed, religious, crucifix, madonna, christ, biblical, cherub, putti, mythology, greek, roman god
- **STYLE_PREFIX:** "Italian fresco on aged plaster, warm chiaroscuro, visible brushwork, terracotta and ochre palette, "

### Temporal Smoothing (Phase A.5)
- **Type:** Frequency-separated (low-freq temporal blend, high-freq from center frame)
- **sigma:** 1.5
- **window:** 8 (was 5 in earlier tests)
- **blur_radius:** 16 (spatial blur for low-freq extraction)

### Upscale (Phase B) — REMOVED
- **No upscaling.** 768x1344 native resolution is the production output.
- ESRGAN x2 destroyed fresco aesthetic (3/10 authenticity per Gemini). SDXL img2img upscale (str=0.50) also degraded quality vs native. Both tested and rejected 2026-03-31.
- 768x1344 is sufficient for the vertical gallery screen at typical viewing distance.

### Interpolation (Phase C)
- **Model:** RIFE v4.25 (upgraded from HDv3)
- **Mode:** Linear timestep (NOT recursive binary) — eliminates midpoint artifact
- **Passes:** 6 (64x interpolation)
- **Skip keyframes:** YES — only interpolated frames written (eliminates sharpness stalls)
- **Skip boundary:** 4 frames per pair (eliminates deceleration zones at t<0.06 and t>0.94)
- **FPS:** 24

### Encoding (Phase D)
- H.264, quality=5, 24fps

## What Each Fix Solved

| Fix | Problem it solved |
|-----|-------------------|
| SDXL Turbo -> Lightning | Subject collapse (CFG=0 couldn't render figures) |
| crops_coords_top_left | Frame/arch border artifacts |
| Latent edge masking callback | Frame/arch border artifacts (belt-and-suspenders) |
| Negative prompt | Religious subjects from LoRA (angels, nudes) |
| Updated STYLE_PREFIX | "still life, no people" was blocking subject rendering |
| RIFE v4.25 linear timestep | 1.3s rhythmic detail flash (binary midpoint artifact) |
| Skip keyframes | Micro-stalls at keyframe boundaries (sharpness differential) |
| Skip boundary frames (4) | Pause/deceleration at RIFE pair boundaries |
| Frequency-separated smoothing | Ghosting from naive temporal blend |
| sigma=1.5 (not 2.0) | Over-smoothing lost texture detail and subject coherence |

## What Didn't Work (archived)

| Approach | Why it failed |
|----------|--------------|
| SDXL Turbo at CFG=0 | Can't render subjects at all |
| Edge-weighted noise (30% edges) | Actually caused frame artifacts |
| Naive temporal smoothing | Ghosting/overlay between frames |
| sigma=2.0 smoothing | Too aggressive, lost texture breathing and sharpness |
| Meditative strength (0.45-0.55) | Too static, lost visual interest, blue color drift |
| hqdn3d post-process | Didn't fix the rhythmic flash |
| Evolved noise walk | Didn't fix the rhythmic flash |
| Strength locked to 0.50 | Didn't fix the rhythmic flash |
| 2x keyframe density + 8x RIFE | Video too fast, same flashing |
| 50/50 keyframe blend | Still had stalls, some ghosting |
| Blur keyframes (r=1.5) | Overall image too soft |
| Sinusoidal timestep spacing | Still had visible frame pauses |
| sigma=2.0 + low transition (0.35) | Texture patina on transitions, subjects abstracting |
| Skip boundary 6 (instead of 4) | Made video worse overall |
| 30fps playback (instead of 24) | Made video worse overall |
| Unsharp mask post-process | Made video worse overall |
| Real-ESRGAN x2 upscale | Destroyed fresco aesthetic (3/10 Gemini score). Over-sharpened, geometric artifacts, cubist look |
| SDXL img2img upscale (str=0.50) | Native resolution still looked better. Upscale added noise to fresco texture |
| SDXL img2img upscale (str=0.26, 0.35) | Same issue — native 768x1344 remains superior |

## Observations

- Pipeline works best with **environmental/architectural subjects** (city scored 9/10 Gemini)
- **Figure closeups** (crown, faces) expose identity shifting between keyframes
- **Throne/seated figure** works well as a middle ground (8/10 with A1)
- **Interior corridors and figure gesture** subjects had blur/clarity issues at sigma=1.5
- The "texture breathing" (surface details subtly shifting) is a FEATURE not a bug
- **No upscaling needed** — 768x1344 native preserves fresco aesthetic best. Both ESRGAN and SDXL upscaling degraded quality
- Total generation time: ~8 min per 2-minute test clip on RTX 4060 Laptop (no upscale)

## Production Status (2026-04-05)

**25 videos generated, 19 approved, 6 need rework.**
Output: `videos/sessions/E{id}_{name}.mp4` | ~3 min each | 768x1344 | 24fps

### Approved (19)
| Video | Subject |
|-------|---------|
| E08_curtain | Curtained palace window, breeze |
| E09_sundial | Sundial on palace terrace |
| E10_watchtower | Watchtower battlement at dawn |
| E12_baldachin | Baldachin canopy from below |
| E13_hall | Palace reception hall receding |
| E14_lake | Still lake at dawn |
| E15_apse | Corridor ending in semicircular apse |
| E16_bed | Palace bed, disturbed covers |
| E17_fresco | Frescoed wall with painted garden |
| E18_aerial | Aerial view of palace complex |
| E19_bust | Stone bust of king in palace niche |
| E21_hearth | Palace great hall with massive hearth |
| E22_maproom | Palace map room library |
| E24_garden | Formal palace garden from window |
| E25_duel | Two identical kings dueling in courtyard |
| E26_wall | Massive palace wall with deep embrasure |
| E29_piazza | City piazza with central well |
| E30_seafacing | Sea-facing palace room, bay view |
| E31_musicroom | Palace music room, harpsichord closeup |

### Rework Queue (6)
| ID | Issue | New Subject |
|----|-------|-------------|
| E05 | Architecture dominated food | Banquet table surface closeup: food, wine, goblets, silverware |
| E06 | Just an arch morphing | 5-pointed golden crown on red velvet pillow, tight focus |
| E07 | Rough loop return | Long twisting road to distant palace, many kings in procession |
| E20 | Lost consistency, blurred | Portrait using E23's accidental portrait quality |
| E23 | Looks like portrait, not reflection | Fix: looking straight DOWN at dark pond, upside-down reflection |
| E28 | Arch dominates, people tiny | Crowd at eye level, figures large in centre, arch above |

## Prompting Rules (Learned from 25+ generations)

1. Fill ENTIRE frame with environmental detail — no empty/dark backgrounds
2. Subject should BE the environment, not an object IN an environment
3. A/B/C prompts: SAME subject, SAME composition, ONLY lighting varies
4. For figures: must be LARGE in frame, not distant/small
5. For conceptual subjects (reflection, shadow): describe PHYSICAL SETUP, not concept
6. Keep object-focus prompts SHORT — let fresco LoRA fill background naturally
7. Rich palace environments work best: frescoed walls, vaulted ceilings, stone columns

## Two Orientation Workflows

| | Vertical (installation) | Horizontal (portfolio) |
|---|---|---|
| Script | `generate_subject_test.py --full` | `generate_horizontal.py` |
| Resolution | 768x1344 (9:16) | 1344x768 (16:9) |
| Duration | ~3 min (17 steady frames) | ~60s (5 steady frames) |
| Output | `videos/sessions/` | `videos/horizontal/` |

## Test History (chronological)

### Session 2026-03-20: Model swap + border fix
- Replaced SDXL Turbo with Lightning 4-step (CFG=0 → 1.5)
- Added crops_coords_top_left + latent edge masking
- Updated STYLE_PREFIX, negative prompt for religious subjects
- Result: subjects visible, borders eliminated

### Session 2026-03-22: Noise and interpolation
- Removed edge-weighted noise (was causing border artifacts)
- Tested meditative strength (0.45-0.55) — too static
- Tested hqdn3d, noise walk, str=0.50 lock — none fixed rhythmic flash
- Confirmed keyframe-only video: SDXL itself reinvents details every frame

### Session 2026-03-24: RIFE breakthrough
- Gemini confirmed 1.3s rhythmic flash = RIFE binary midpoint artifact
- Switched to RIFE v4.25 linear timestep — flash eliminated
- Tested 64x RIFE at 24fps — meditative pace confirmed
- Skip keyframes — eliminated sharpness stalls
- Skip boundary 4 — eliminated deceleration pauses
- A1 configuration (sigma=1.5, skip-boundary-4) = continuous motion achieved
- Tested 5 subjects: city + nocturne amazing, corridor + fist had blur issues
- Tested C/D/E experiments (skip-6, 30fps, unsharp) — all made it worse

### Session 2026-03-31: Upscaling research
- ESRGAN x2: destroyed fresco (3/10 Gemini). Cubist/geometric artifacts
- SDXL img2img upscale (str=0.26/0.35/0.50): native still better
- Research: 11 upscalers evaluated, all rejected or inferior to native
- Decision: **no upscaling, 768x1344 native is production resolution**

### Session 2026-04-02: Overnight batch generation
- Text worker proposed 4 subjects per session, user selected one each
- 15 first sessions (E05-E20) + 10 additional sessions (E21-E31) = 25 total
- Rich-background prompts: frescoed walls, vaulted ceilings, stone columns, tapestries
- Overnight batch: 25 videos generated in ~3.5 hours total
- STEADY_FRAMES=17 for ~3 min videos (was 54 producing 7-min videos)
- Loop return softened: quadratic ease-in, max 20% pixel blend (was 40%)

### Session 2026-04-05: User review + rework planning
- 19/25 approved, 6 need rework
- **Failures:** E05 (food not prominent), E06 (arch not crown), E07 (loop rough), E20 (blurred), E23 (portrait not reflection), E28 (people too small)
- **Key learning:** isolated objects fail, environmental subjects excel
- **Prompting rules codified** (see section above)
- New subjects chosen for all 6 rework videos
- Creative director invoked for E23 (surreal proposals) — user chose king's reflection in water
- Horizontal workflow added: `generate_horizontal.py` (1344x768, ~60s loops)
- Editor.html updated: video preview panel shows session video on selection
