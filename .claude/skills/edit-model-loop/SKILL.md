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

## THE BANANA INTERPOLATION BASELINE (v1, frozen 2026-08-18)

**This is the pipeline of record and it WORKS. Do not change it while alternatives are
being explored** (PL20, [`kickoff-keyframe-authoring.md`](../../../docs/planning/kickoff-keyframe-authoring.md)).
Luca, 2026-08-18: *"we can keep nano banana pipeline we have now, but ultimately i would
like to work to find cheaper solutions for the same quality and more creative control."*

Recall it by name: **banana interpolation**. Any replacement is measured **against** this
baseline, never merged into it. If a probe changes a step below, it is a different pipeline
and gets a different name.

| element | frozen value |
|---|---|
| keyframe author | `gemini-3.1-flash-image` (nano banana), **$0.067/image** |
| authoring | `tools/banana_keyframes.py` — `--base` / `--base-image` / `--bridge` + `--bridge-at`, `BASE_SUFFIX` on by default, `manifest.json` per chain |
| register | carried by a PROMPT CLAUSE, not by weights (this is the known weak point) |
| critique | `tools/chain_stats.py` (structure r + drift vs frame 0) + chroma delta + the eye at native res |
| interpolation | `tools/loop_render.py`, RIFE v4.25, `skip_boundary 0`, `edge_crop 0`, wrap included |
| closure | from the phenomenon, per `findings/loop-closure-taxonomy.md` |
| sizes | **1408x768** horizontal, **1024x1280** vertical, both %64 |
| encode | exactly 300 frames, 30 fps, h264 crf 16, yuv420p |
| gate | `tools/review_gate.py` keeper floor (7/9/5/8) + MANDATORY eye signoff |
| cost | **~$0.40 to $0.67 per chain, ~$4 per nine-piece day** |

**Reference ladders, what healthy looks like** (computed free from frames on disk, PL17
§10.10). Use these to judge any candidate replacement:

| chain | mean consecutive SSIM | wrap | note |
|---|---|---|---|
| `labor_embers` 1408x768 | **0.903** | 0.917 | the gated 10/10/9/9 piece |
| `ledB_snow` 1856x576 | 0.830 | 0.651 | two pairs already below the bridging threshold |
| `ledA_window` 592x1792 | 0.429 | 0.258 | dusk-to-night; SSIM is **not** usable here |

Best pieces produced by this baseline: `action_mist` **10/10/10/9**, `labor_embers`,
`labor_vert_wipe`, `labor_hands`, `action_snow`.

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

**Decide the CLOSURE before you write a single prompt.** It follows from the
phenomenon, not from the wrap, and picking wrong cannot be repaired later:
self-erasing subjects close themselves (wrap r 0.986 to 0.989, first try, no
bridges), reversible ones palindrome exactly, and asymmetric ones need anchored
bridges and still only reach ~0.85. Full taxonomy and decision procedure:
[docs/findings/loop-closure-taxonomy.md](../../../docs/findings/loop-closure-taxonomy.md).

**Three flags exist for this, all added 2026-08-14:**
- `--base-image PATH` reuses an existing PNG as keyframe 0 instead of generating
  one. Use it to re-author only the TAIL of a chain whose early states are good,
  and to resume after an API failure. Regenerating a validated frame re-rolls it.
- `--bridge FROM TO` with `--bridge-at` makes the dual-image call from the CLI.
- a `manifest.json` is written beside the keyframes recording base, edits,
  preamble, model and sizes. Its absence once made three photographic chains
  impossible to re-run with one clause changed; the prompts were simply gone.

- 9-10 keyframes, base + 8-9 SEQUENTIAL edits (each edit receives the previous
  output). Small deltas: "a few centimetres", "same hands, same finger count".
- **Keep any SEQUENTIAL run to about five edits.** At nine, geometry walks: a
  tall multi-pane window shrank to a small square by state 5 and grey masonry
  went smooth white by state 8, so the chain could not close. Author the first
  half sequentially, then reach for anchored bridges.
- **Never let the subject hide its own reference.** When ivy reached total
  coverage the wall was gone from the frame, and with no masonry left to
  preserve the model stopped preserving it. Capping the peak near 90% with the
  window always visible held the geometry through the whole chain.
- **Uniformity needs a NEGATIVE, not just a positive.** "Spread uniformly over
  the entire surface" still produced patches; adding "an even scattering and NOT
  a patch or a clump in one place" to every edit is what fixed it.
- **Name coverage as a fraction** ("roughly SIXTY-FIVE PERCENT") when the subject
  is an extent. Incremental language ("spreading further") produces changes too
  small to read as the subject.
- **Style now lives in a prompt clause, so it can be omitted.** With no LoRA the
  painterly register is only the words; three verticals rendered photographic
  because the clause was dropped. Trained weights could not be forgotten this
  way. Check every base prompt carries the full brief.
- Style brief that survived Luca's review: *soft tonal painting, smooth blended
  gradients, sfumato, no visible brushstrokes, muted palette*. Ban impasto in the
  negative sense of the prompt. He rejected the material/impasto register.
- Persistent elements must be present FROM FRAME 0 (a hand that materialises in
  one keyframe step reads as an apparition at 1 s; entry/exit need 3 keyframes
  each if they must happen at all).

## 3. Critique BEFORE interpolating, four instruments

> Instruments 1 and 1b are now a tool: `python tools/chain_stats.py --dir <accum>`
> (add `--wrap` for a self-closing chain). It prints the consecutive ladder, the
> drift against frame 0 and the surface ratio, and flags any pair under 0.85.

1. **SSIM ladder** (consecutive pairs at half scale): healthy chains sit 0.85-0.98;
   the wrap is the number that matters. Under ~0.75, bridge it.
   **This instrument alone is not sufficient, and 2026-08-14 showed how it fails.**
   In the PL17 bake-off, FireRed's chain detonated into chroma noise at turn 3, and
   its consecutive SSIM went *up* as it died: turns 6 to 9 scored 0.955 / 0.963 /
   0.970 / 0.975, its four best, and its mean of 0.8795 BEAT nano banana's 0.8297
   on a chain that was garbage. Consecutive SSIM measures step size, so it is
   structurally blind to a monotonic walk away from the original: once the frame
   is noise, neighbours agree because the noise is the attractor. Always pair it
   with instrument 1b.
1b. **Drift against FRAME 0, never against the neighbour.** Two numbers per state:
   SSIM to frame 0, and surface energy (laplacian variance) as a RATIO to frame 0.
   The kill signal is surface energy climbing fast and monotonically, with chroma
   going with it (FireRed: 0.64 at turn 2, 7.55 at turn 3, ~11x by turn 6). A wrap
   SSIM of 0.15 against frame 0 says the loop cannot close no matter what the
   consecutive ladder claims.
   **Read the ratio against the subject before calling it a fault.** A legitimate
   chain moves this number too, and the direction is meaningful: `ledC_ruin` climbs
   to 2.71x because bare masonry genuinely becomes dense foliage, and
   `action_path_vert_wood` FALLS to 0.46x because ferns are genuinely replaced by
   smooth bare earth. Both are the subject. What is never the subject is a fast
   monotonic climb past ~3x with the consecutive ladder improving underneath it.
   **Cheap forecast, one call:** per-edit surface ratio on a single edit predicts
   chain survival. FireRed's 1.38 compounds to ~5.5 over six edits (measured 11.2);
   nano banana's 1.21 compounds to nothing and ends at 0.88, because it re-blends
   rather than accumulating edge energy.
2. **Semantic velocity, by eye on the strip**: SSIM cannot see "no hand becomes
   full hand" (0.94 on exactly that). Ask WHAT changed per pair, not how much.
3. **Entity consistency**: finger counts, object counts, sleeves appearing. The
   edit model takes small liberties; catch them here, not in the gate.
4. **Chroma delta per pair, which instruments 1 and 1b CANNOT SEE.** Structure r is
   a contrast-normalised low pass and SSIM is computed on luminance, so both are
   **blind to hue**. Measured 2026-08-15 on `labor_bedroom`: a pair scoring a
   perfectly healthy 0.985 carried a colour rotation that broke the render into blue
   and orange blotches. Measure mean Lab (a,b) distance between consecutive states:
   **1.2 clean, 11.0 clean, 22.9 mottled.** Keep it under about 11 on any chain that
   changes light. If the phenomenon will not allow that, the fix is in the encode,
   not the prompt (see §4).

**Signature and canvas check, every chain, at both bottom corners.** The model
volunteers a painted signature or a canvas edge into frame 0 and every later state
inherits it. `BASE_SUFFIX` in `banana_keyframes.py` suppresses it about 5 times in 6,
so this is a check and not a formality: `work_bricks` produced a monogram with the
suffix active. Removal is a feathered median over the stroke box across every state
plus a re-render, which costs no API calls.

**Wrap bridge**: the edit model accepts MULTI-IMAGE input. Hand it the last
keyframe AND frame 0, ask for "the exact in-between moment". Halves the seam step.

## 3b. Bridges are the fault line. Blend the close ones.

**Every content defect this project has recorded came from a BRIDGE; none from an
anchor** (8 in ~130 calls, 2026-08-19/20: a poem carved on a gravestone, an
invented epitaph, human faces sculpted into stone, ivy neither endpoint had, a
vortex in the grass, a bouquet leaving frame, two sideways jumps, roses turning
pink, one bloom growing).

The cause is structural: an anchor edits a real previous image, so it inherits. A
bridge invents. And `banana_keyframes.py` builds the `--bridge` prompt internally
and takes **no caller text**, so every preservation clause you write into `--edit`
reaches the anchors and **none reaches the bridges**.

**So do not generate a bridge you can blend.** Where endpoint mean-abs-diff is
under **12**, a 50/50 average IS the correct in-between, is free, and cannot
hallucinate:

```python
Image.fromarray(((a + b) / 2).astype(np.uint8)).save(bridge_path)
```

Set the threshold at 12, not 10: a gap of 10.08 missed a cutoff of 10 by 0.08,
went to the model, and came back with a vortex painted into the grass. On a
14-anchor / 56-state chain this leaves ~28 of 42 bridges as blends and reserves
model calls for the genuine light transitions, which is where they earn their
keep.

**When you must generate, roll and keep the best MEASURED candidate**, never the
first that returns. A re-roll draws a new random failure rather than converging: a
bouquet 58 px off was re-rolled and came back 70 px off the other way. Score
candidates on distance from a target, or from the mean of the two neighbours, and
stop early when one is good enough.

**Verification of the built chain is its own discipline**, and it is the highest
defect-yield activity in the pipeline. See
[chain-verification](../chain-verification/SKILL.md): check every ring rather than
only the last, gate on a region strip rather than on any metric, and sweep the
encoded video before showing anyone anything.

## 4. Interpolate locally, encode to exactly 300

RIFE via `slow_interpolation.interpolation.RIFEInterpolator`, `n_passes=5`,
`skip_boundary=0`, `edge_crop=0`, wrap pair included. **Dimensions must be % 64**
(1408x768; banana emits 1376x768, resize). Action pieces: write 10 copies of the
last keyframe before the wrap pair (the held beat).

Encode: `-framerate <total/10> -vf fps=30 -frames:v 300`. Slight duplication is
invisible; frame-DROP ratios near 1.5 are the documented judder.

**`loop_render.py` hard-codes that 300-frame encode, and it will silently ruin a
long piece.** Given a 56-state chain it builds all 1792 frames correctly and then
drops them **2.99x into a 10-second file**, printing `896 frames -> 300 : DROP
2.99x` as a *judder warning* rather than an error, exiting 0, and signing off with
`verified: 1408,768,300` — which reads exactly like success. For anything that is
not a 10 s loop, pass `--keep-frames` and encode yourself at true rate:

```bash
ffmpeg -y -framerate 30 -i <piece>.frames/%05d.png -c:v libx264 -crf 16 -pix_fmt yuv420p out.mp4
```

Then probe the artefact. `K * 2**passes` is the frame count to expect; if the mp4
disagrees, the encode retimed it.

**Do NOT reach for `minterpolate mci` on long chains** (this reverses the earlier
guidance, measured 2026-08-13). It is block-based motion compensation and it smears
soft painterly content: `grow_farmhouse` FAILED the gate at image 7 under mci and
PASSED **9/10/9/9** re-encoded from the same frames with plain frame-drop. If a chain
is long enough to worry about, densify the KEYFRAMES rather than the encode. Where an
exact-300 needs a nudge, `tpad=stop_mode=clone:stop=N` clones a tail frame, which is
invisible on a slow loop.

**When a pair crosses a colour temperature, do not let RIFE interpolate the colour.**
Flow is ambiguous on flat surfaces, so patches blend from different source regions; that
is invisible when both endpoints share a hue and, above a chroma delta of about 11 (§3),
it prints as blue and orange mottling. The tell is exact: **a frame sitting ON a keyframe
is clean while the MIDPOINT of the same pair mottles.** Densifying does not fix it,
because gold-to-twilight is an un-smoothable threshold (see Known boundaries). The fix is
to keep RIFE's luminance and cross-fade the a,b channels linearly between the two endpoint
keyframes, leaving keyframe positions untouched. On `labor_bedroom` that cleared every
chroma flag and moved the gate to 9/9/6/9. **Light-event pairs only**: where content
genuinely MOVES between endpoints, an unwarped chroma fade ghosts. Render with
`--keep-frames`, correct, then re-encode.

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

- **A loop cannot contain irreversible change.** "The grave is ruined and
  weathered" cannot HAPPEN during the loop or it never returns to frame 0.
  Establish it as a PROPERTY at frame 0 and cycle the reversible thing over it
  (dirt and the care that removes it, lichen and its scrubbing). This is also the
  more Arendtian reading: what recurs is the labour, not the ruin.
- **Two changes must both advance in EVERY edit, or they take turns.** Asked for a
  sun crossing AND a wilting bouquet, the piece delivered them alternately: the
  shadow sat still at one centroid for 9 states, teleported 276 px, sat still for
  16 more. Correlation between the two motions was **+0.006**. The cause was in the
  prompts — some edits said "ONLY the sun moves", others "ONLY the flowers change".
  Name both in every single edit, then measure the correlation to confirm.
- **A discrete event, once bridged, becomes a morph.** A bouquet REPLACED between
  two anchors is bridged twice into a four-step brown-to-white blend, which reads
  as resurrection rather than as someone having visited. Either hide the swap where
  it cannot be read (inside the darkest states, or inside a large light change), or
  accept the morph. You cannot bridge a cut and keep it a cut.
- **Turning off `BASE_SUFFIX` removes the text ban from EVERYTHING, not just the
  base.** `--no-base-suffix` plus a hand-written replacement appended to `--base`
  leaves `EDIT_PREAMBLE` carrying no ban at all, and a preservation clause that
  only says "the inscription stays the same" never says "add no OTHER lettering".
  Result: runes, a second invented sentence, and a monogram. If a piece genuinely
  needs text, repeat the full ban in every `--edit` as well.
- **No human hands, ever** (Luca, 2026-08-13). Objects and places, at most
  crowds; never hands active in a task ("it does not convert well, while the
  chair slowly aging by itself looked very promising"). The acting element is
  the thing itself: the light, the ivy, the frost, the snow, the crowd of
  lit windows. Hand chains also carry a measured aging drift (smooth hands
  turn veined over 8+ sequential edits and never return).
- **No chair, and no Thomas Cole** (Luca, 2026-08-14). The chair was the
  original illustration of the rule above and is now itself excluded: "I would
  stop all outputs with the subject chair, not interested anymore". Five chair
  assets came off the field and an approved re-author was cancelled.
  **Consequence, now RESOLVED 2026-08-15:** the chair was the ONLY `work_*` piece,
  which left Work empty. Three durable non-furniture objects now carry it and the
  triad can be shown complete: `work_kiln` (a brick bottle kiln, the thing that
  MAKES durable things), `work_bell` and `work_bricks`. Cole is out too: ledwall and series pieces use the
  current Arendt subjects, "not the tcole arches and ruins". **Hammershoi
  (`Hammershoi_Interiors_epoch_10`) is the only LoRA in play**, and most series
  pieces use none at all.
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
- **TWO light transitions cannot be smoothed at all, and densifying makes them
  worse.** Night-to-dawn (measured 2026-08-14: 0.542 with no inserts, 0.525 with a
  bridge, **0.428** with two authored states) and **gold-to-twilight** (measured
  2026-08-15: seven intermediates, bridges AND sequential edits, at one third /
  halfway / two thirds, every one landing on the cool side, gap stuck at 19).
  Both are crossings of a colour temperature; brightness alone interpolates fine,
  and the kiln's dark-to-firelit chain crosses a far larger luminance range and
  holds. **Design around them:** day to night and back THROUGH DUSK never crosses
  either. If you must cross one, fix it in the encode (§4), not the prompt.
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
- **Prefer a medium that VEILS over one that REPLACES** (measured 2026-08-15). A
  veil — mist, shade, a light patch, wetness — leaves the thing it covers readable
  underneath. A replacement — snow lying on stone treads, foliage swallowing a wall
  — removes the reference the model needs to hold, and once it is gone the model
  re-invents it. `labor_vert_steps` walked its staircase in BOTH versions, gaining
  treads and re-proportioning the flight, **despite an explicit "CRITICAL: the SAME
  number of steps" clause in every edit**: a verbal preservation clause does not hold
  geometry the subject has hidden. Same session, `action_mist` veiled an entire
  valley with its foreground wall pixel-stable at 10/10/10/9. Cap any coverage peak
  well below the point where the reference disappears.
- **The model GROWS a shadow, it does not translate one.** Asking a cypress shadow to
  travel across a wall produced spreading and diffusion, worst pair 0.752 falling to
  **0.520** after a bridge that cloned its own endpoint. Re-authored as the same
  shadow CLIMBING and LENGTHENING up the wall, which is what a lowering sun does
  anyway, it rendered clean. Author the arc the model can draw: growth, lengthening
  and coverage all work; rigid translation of a soft shape does not. `work_bell`'s
  louvre bars lengthen across the bronze for the same reason.
- **"An even scattering" is read as literal DOTS.** It produced speckles on vertical
  wall faces. The uniformity NEGATIVE ("NOT a patch or a clump in one place") is still
  required, but pair it with "a smooth continuous settled layer" rather than
  "scattering", and add "no speckles, dots or spots" where a surface must stay clean.
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
