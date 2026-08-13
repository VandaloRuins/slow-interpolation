---
name: edit-model-loop
description: Build a 10-second slow-interpolation loop from edit-model (nano banana) keyframes, the validated Arendt-series pipeline. Use when the user asks for a new series piece, a loop where only one element moves, or any banana-keyframe chain. Covers the temporal staging doctrine per Arendt cluster, keyframe critique before interpolation, wrap bridges and held beats, the local RIFE pass, exact-300 encode, the keeper-floor gate with mandatory eye signoff, and apply-always publishing.
---

# The edit-model loop (validated 2026-08-12/13, Arendt series)

You are building a 10 s / 300-frame loop where an image-edit model authors the
keyframes and RIFE interpolates them. This inverts the diffusion chain: consistency
is the DEFAULT and change is AUTHORED. It produced the two best-gated pieces of the
project (`labor_hands`, `action_snow`, both 9/10/9/8 with zero surviving flags)
within a day of being invented. Trust the sequence below; every step earned its
place through a measured failure.

## 1. Stage the piece on its clock BEFORE any pixels

The 10-second loop means a different thing per Arendt cluster, and the seam is
doctrine, not preference (release-side canon:
`Ruins-agent/knowledge/research/arendt-vita-activa-series.md`):

| cluster | the loop is | edits | the seam |
|---|---|---|---|
| Labor | the time itself | uniform small deltas around the whole cycle | invisible; author the last edit to land near frame 0, bridge the rest |
| Work | the cycle of care around a durable thing | **ONE act only** | the caring gesture returning to its start |
| Action | the recurring capacity to begin | asymmetric: spark, spread, fade | ALLOWED to breathe: 10 dwell frames before the wrap |

**The over-plotting law (measured twice):** a 10 s loop cannot contain a plot.
Decay + entry + work + exit is four acts; every act above one is paid for in speed
(`work_chair` v1 failed at loop 3 twice). Cut to one act.

## 2. Author the chain

`python tools/banana_keyframes.py --out outputs/arendt/<name>/keyframes --base "..." --edit "..." ...`

- 9-10 keyframes, base + 8-9 SEQUENTIAL edits (each edit receives the previous
  output). Small deltas: "a few centimetres", "same hands, same finger count".
- Style brief that survived Luca's review: *soft tonal painting, smooth blended
  gradients, sfumato, no visible brushstrokes, muted palette*. Ban impasto in the
  negative sense of the prompt. He rejected the material/impasto register.
- Persistent elements must be present FROM FRAME 0 (a hand that materialises in
  one keyframe step reads as an apparition at 1 s; entry/exit need 3 keyframes
  each if they must happen at all).

## 3. Critique BEFORE interpolating, three instruments

1. **SSIM ladder** (consecutive pairs at half scale): healthy chains sit 0.85-0.98;
   the wrap is the number that matters. Under ~0.75, bridge it.
2. **Semantic velocity, by eye on the strip**: SSIM cannot see "no hand becomes
   full hand" (0.94 on exactly that). Ask WHAT changed per pair, not how much.
3. **Entity consistency**: finger counts, object counts, sleeves appearing. The
   edit model takes small liberties; catch them here, not in the gate.

**Wrap bridge**: the edit model accepts MULTI-IMAGE input. Hand it the last
keyframe AND frame 0, ask for "the exact in-between moment". Halves the seam step.

## 4. Interpolate locally, encode to exactly 300

RIFE via `slow_interpolation.interpolation.RIFEInterpolator`, `n_passes=5`,
`skip_boundary=0`, `edge_crop=0`, wrap pair included. **Dimensions must be % 64**
(1408x768; banana emits 1376x768, resize). Action pieces: write 10 copies of the
last keyframe before the wrap pair (the held beat).

Encode: `-framerate <total/10> -vf fps=30 -frames:v 300`. Slight duplication is
invisible; frame-DROP ratios near 1.5 are the documented judder. For long chains
(400+ frames) retime with minterpolate mci instead.

## 5. Gate, then eyes, then publish

- `python tools/review_gate.py <mp4> --subject "..."` — median-of-3 Gemini vote
  against the keeper floor (subject>=7, loop>=9, motion>=5, image>=8). Flags are
  reported, not fatal. The gate emits PENDING-EYE; nothing passes on scores.
- Eye signoff is mandatory and means files were OPENED: both edge strips, a
  native-res mid-loop frame, and the worst-flagged moment. Then
  `review_gate.py --signoff <clip> --edges-clean --detail-ok`.
- Publish EVERYTHING new (Luca curates from his phone; failures stay visible with
  verdicts recorded): `python tools/curation_sync.py --apply` (ALWAYS apply before
  export, never check-then-export: shell pipelines ate the check's exit code twice)
  then glance_export with `--spec 1408x768` among the specs, glance_deploy, and
  **verify the SERVED catalogue count over the tunnel**, never the build log.

## Known boundaries (do not rediscover)

- **RIFE cannot invent particulate motion.** Dust, spray, snowfall-as-particles
  morph as blobs (`labor_sweep`, motion 4). Author such media as per-keyframe
  STATES (settled / lifted / settled), or avoid.
- **A LoRA cannot render a register its dataset lacks** (vhm has no nocturnes; the
  dusk facade stayed daylight). Check the corpus before promising a register.
- **A caption prior is a composition force**: vhm's "bare walls" erased a window
  grid that an anchor alone was pinning. The fix is a DRAWN ControlNet map (three
  derived maps failed; drawn won immediately) at scale 0.65 with a full-bleed
  anchor at 0.45, warmup 1.
- Gemini flagged plank grain as a border artefact and dough elasticity as
  rubberiness: the eye owns final calls, both directions.
