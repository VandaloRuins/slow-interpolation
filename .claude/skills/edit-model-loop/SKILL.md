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
invisible; frame-DROP ratios near 1.5 are the documented judder.

**Do NOT reach for `minterpolate mci` on long chains** (this reverses the earlier
guidance, measured 2026-08-13). It is block-based motion compensation and it smears
soft painterly content: `grow_farmhouse` FAILED the gate at image 7 under mci and
PASSED **9/10/9/9** re-encoded from the same frames with plain frame-drop. If a chain
is long enough to worry about, densify the KEYFRAMES rather than the encode. Where an
exact-300 needs a nudge, `tpad=stop_mode=clone:stop=N` clones a tail frame, which is
invisible on a slow loop.

## 5. Gate, then eyes, then publish

- `python tools/review_gate.py <mp4> --subject "..."` — median-of-3 Gemini vote
  against the keeper floor (subject>=7, loop>=9, motion>=5, image>=8). Flags are
  reported, not fatal. The gate emits PENDING-EYE; nothing passes on scores.
- Eye signoff is mandatory and means files were OPENED: both edge strips, a
  native-res mid-loop frame, and the worst-flagged moment. Then
  `review_gate.py --signoff <clip> --edges-clean --detail-ok`.
- **Name the file notion-first**: `labor_*`, `work_*`, `action_*`. The gallery
  clusters by the Arendt notion in the STEM (`glance_export.py --cluster-by notion`),
  so a motif name like `grow_well2` or `vert_facade` lands in `unsorted`. Measured
  2026-08-13: 14 assets stranded that way in one day. Assets are keyed by path, so a
  later rename mints a new key and resurrects anything excluded under the old one:
  name it right at birth.
- Publish EVERYTHING new (Luca curates from his phone; failures stay visible with
  verdicts recorded): `python tools/curation_sync.py --apply` (ALWAYS apply before
  export, never check-then-export: shell pipelines ate the check's exit code twice)
  then glance_export with `--spec 1408x768` among the specs, glance_deploy, and
  **verify the SERVED catalogue count over the tunnel**, never the build log.

## Known boundaries (do not rediscover)

- **No human hands, ever** (Luca, 2026-08-13). Objects and places, at most
  crowds; never hands active in a task ("it does not convert well, while the
  chair slowly aging by itself looked very promising"). The acting element is
  the thing itself: the chair, the light, the cloth, the chairs-as-crowd.
  Hand chains also carry a measured aging drift (smooth hands turn veined over
  8+ sequential edits and never return).
- **Sequential edits are blind to frame 0**, so a "return to the start" edit
  drifts (chairs never reset, textures accumulate as swirl). Author the return
  leg with MULTI-image edits: hand the model the previous keyframe AND frame 0
  and ask for the in-between at one/two thirds. This closed action_chairs'
  wrap from 0.758 to 0.953 and labor_dishes' from 0.736 to 0.837 in one pass
  each.
- **Stage transitions densely** (Luca, 2026-08-13): any large light or state
  transition (dusk to night, night to dawn, peak to first-return) gets 2-3
  authored keyframes of its own, not one step plus a reactive tween. Every
  single-keyframe transition this far has needed a tween after the fact.
- **The standing objective is fluidity** (Luca, 2026-08-13): the loop should
  read as ONE continuous movement, never as interpolation between staged
  frames. More keyframes with smaller deltas beats fewer with big deltas;
  even semantic velocity per pair matters more than any individual frame.
- **Environmental coherence** (Luca, 2026-08-13, from grow_well): when time
  alters the subject (overgrowth, weathering, aging), the SURROUND must
  register the same passage, proportionally. Name it in the edits themselves
  ("the beds swelling, the gravel narrowing under moss") or the subject ages
  inside a frozen world and the result reads as an effect on an object, not
  as time passing through a place. Light-cycle pieces satisfy this for free
  (the light touches everything); object-in-landscape pieces do not.
- **RIFE cannot invent particulate motion.** Dust, spray, snowfall-as-particles
  morph as blobs (`labor_sweep`, motion 4). Author such media as per-keyframe
  STATES (settled / lifted / settled), or avoid.
- **A LoRA cannot render a register its dataset lacks** (vhm has no nocturnes; the
  dusk facade stayed daylight). Check the corpus before promising a register.
- **A caption prior is a composition force**: vhm's "bare walls" erased a window
  grid that an anchor alone was pinning. The fix is a DRAWN ControlNet map (three
  derived maps failed; drawn won immediately) at scale 0.65.
- **`anchor_image` must sit at YAML ROOT.** Nested under `render:` it parses into
  `RenderProfile` and is SILENTLY IGNORED, because the loader reads
  `raw.get("anchor_image")` at the root and `keyframes.py` reads `config.anchor_image`.
  Corrected 2026-08-13: the "full-bleed anchor at 0.45 / warmup 1" half of the v3
  recipe above **never loaded**, so that result was carried by the drawn map alone.
  Hoisting the key made the container log `seeded from ... at strength 0.45`, and the
  anchored render then passed first try. Verify the log line rather than the YAML.
- Gemini flagged plank grain as a border artefact and dough elasticity as
  rubberiness: the eye owns final calls, both directions.
