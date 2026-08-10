---
name: control-map
description: Author a structural control map for SDXL ControlNet so a render puts a specific composition or landmark on screen. Use when a prompt cannot make the model draw a place, a geometry, or a recurring anchor, or when a narrative cycle needs different structure per stage. The most transferable craft from 2026-08-08: six prompt generations failed to produce a composition that one drawn depth map produced immediately.
---

# Authoring a control map

Prompts describe. Control maps **assert**. When six prompt generations across three
LoRA scales cannot put a landmark on screen, stop rewriting the prompt.

## Why this layer and not another

Two cheaper things were tried first and both failed, for the same reason:

- **Seeding the warmup** (`anchor_image`) works but **decays**. The landmark appears in
  the first second and morphs away by the fourth, because it only conditions frame zero.
- **Blending each frame back toward an anchor** (`render.anchor_reassert`) is worse. It
  fights the diffusion in pixel space, adds motion rather than damping it, and smears the
  surface, because averaging toward a fixed image is lossy and compounds over a chain.

ControlNet injects residuals **at every denoising step of every frame**, so structure is
part of what the model paints rather than something applied to the result. Nothing to
fight, nothing to smear.

## Depth, not canny

`diffusers/controlnet-depth-sdxl-1.0`. Canny prints hard edges that read as line art
under paint, which is the same failure as an over-strong anchor.

## Draw the map, do not photograph it

`tools/make_massing.py` draws them with PIL polygons. This is better than depth-estimating
a photo on two counts: it is exact, and for a commercial release there is **no rights
question at all**. A depth map of a composition is simple geometry.

Convention: **white = near, black = far.**

## The rules that cost renders to learn

**Assert only what must be there. Leave the rest BLACK.**
Any grey value in a region reads to the model as a surface to stand things on. A water
region given a near-bright to far-dark ramp became a receding lawn; flattened to a mid
value it became a field. Both times the foreground ate the picture. Black means far,
means unconstrained, means the model paints it freely.

**Soften the map.** At blur radius 4 a vector diagram gets traced: crisp slab edges print
straight through as flat planes. Use `--soften 10` to 14 so boundaries become ramps the
model interprets as form.

**Prefer few large masses to many small ones.** Twelve slender towers is an *inventory*
the model cannot keep consistent; five broad masses of the same silhouette envelope is
stable and scored the best image quality of the run. This is the single most useful
finding: **fewer things to keep consistent beats better weights to draw them with.**

**A narrative cycle needs one map per stage.** `control.images` takes a list, cross-faded
on the same `t` as the prompt SLERP so structure and text change together. One fixed map
forces one geometry on every stage, which is how a wilderness stage came back with a city
in it. Keep every shared element at **byte-identical coordinates** across the maps: that
is what makes an anchor persist.

## Tuning

`guidance_end` matters more than `scale`. Around **0.6** the structure is applied over the
first part of each frame's denoising and the model paints freely afterwards. Held to 0.8
it traces the map. Scale around **0.55 to 0.65**; 0.45 asserts nothing, 0.70 over-imposes.

Both need more denoising than the shipped default: with `int(steps * strength)` = 2 real
steps, `guidance_end` partitions nothing. Use 12 to 20 steps, and lower strengths to match
(see `render-sweep`).

## What it cannot fix

**Content the model cannot hold.** ControlNet will make it DRAW a modern skyline; it will
not make it PAINT one consistently. Halving `lora_scale` on those stages changed the
instability by 0%, so this is content complexity rather than a LoRA limitation, and no
conditioning strength fixes it. Simplify the content instead.

Verify by looking at the map before rendering. A map that reads wrong to you reads wrong
to the model.

## Value distribution is load-bearing (2026-08-09, measured)

The maps that work measure **~56 to 66% black, ~21% above 200**. The delivery-aspect
maps that failed kept the black fraction but pushed the near field to 48 to 54%, and
both renders painted an enormous foreground wall with the horizon shoved out of frame.
A depth map half at maximum brightness says "a wall in front of the camera". Check
`mean / black% / near%` against a known-good map before spending.

## The border, four ways to smear

The corner artefact lives in the KEYFRAMES (Phase A), not RIFE, and it appears whenever
the map asks the border to be featureless or false. All four of these failed in one day:
smooth ramps to the edge; a flat grey ring; a black ring cutting through solid rock
(semantic nonsense paints as mud); a tall UNIFORM bright column at the edge (repetitive
fill collapses into smear). The only borders that render clean carry **varied or
semantically continuous content running to the frame edge**, like a bay map's shelf.
Also: screen A's conform crop keeps the central 506 px, so judge delivered corners from
the conformed file, never the raw card.

## No straight lines where the LoRA expects a frame

A RECTANGLE at the bottom of the canvas was painted by the Cole LoRA as a gilded picture
frame standing in the pool. Structural assertion beats the negative prompt every time it
has been tested. Spray, shores, basins: overlapping irregular billows, never a rectangle.

## Per-keyframe maps exist, and what they cannot do

`control.keyframe_images` cycles one map per KEYFRAME (index, not prompt), for structure
that must change through the clip; author phase i/K so map K equals map 0 and the loop
closes in the conditioning. Built for motion, where it still failed (see
`motion-compositing`), but it is the right tool for per-keyframe structural evolution
generally. `images` remains a per-PROMPT cross-fade, and a cross-fade is a dissolve.
