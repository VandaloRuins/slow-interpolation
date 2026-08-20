---
name: interpolation-curves
description: Manage the smoothness of RIFE-interpolated motion in slow-interpolation. Use when a render breathes in and out of focus, steps rather than flows, smears at the frame edges, or when choosing passes / skip_boundary / keyframe count. Covers the frame arithmetic, the two independent curves and their opposite fixes, and how to hold duration constant while changing pair length.
---

# Interpolation curves

Between every pair of real keyframes, RIFE invents N frames by warping pixels along an
estimated flow field. Everything here follows from that one fact: **an invented frame is
a blend, not a painting.**

## The arithmetic, memorise it

```
frames_per_pair = 2**passes - 1 - 2*skip_boundary
total_frames    = K * frames_per_pair - 1          # K = keyframes, incl. the wrap pair
duration        = total_frames / fps
```

`conform.py` **refuses below 300 frames**. Check this before every dispatch; it is the
most common reason a sweep config is invalid.

**That arithmetic is the CONFIG pipeline's. `tools/loop_render.py` uses a different
one** — `frames = K * 2**passes`, with `skip_boundary` fixed at 0 and every pair of
the closed ring counted. Verified against real chains: `grow_farmhouse` 14 states →
448, `labor_embers` 8 → 256, `action_snow` 10 → 320 plus its 10-frame held beat =
330. Using the config formula on a banana chain gives 278/309/371 and is wrong every
time. Check which tool built the piece before you predict a frame count.

To change pair length while holding duration, scale K inversely. Typical points:

| passes | skip | per pair | K for ~120 s at 30 fps |
|---|---|---|---|
| 6 | 8 | 47 | 77 |
| 5 | 4 | **23** | **157** |
| 5 | 8 | 15 | 241 |

## Two curves, opposite fixes

Do not conflate these. They are separate defects with separate remedies, and the same
dial moves them in opposite directions.

**Sharpness pulse.** Sharpness peaks at each keyframe and troughs mid-pair, because the
midpoint is maximally committed to two images that disagree and their fine detail
cancels. Reads as the image **breathing in and out of focus**. Measured swing: 30% (47
frames/pair), 17% (23), 7.5% (15).

**Velocity rhythm.** Motion is slowest at each keyframe and fastest mid-pair. Reads as
**stepping rather than flow**. Measured variation: 79%, 58%, **97%**.

Note the third column of each: the setting with the flattest sharpness had the **worst**
stepping. `tools/pulse_plot.py` draws either.

## `skip_boundary` is the trade, not a quality dial

It discards the frames nearest each keyframe, which are simultaneously the **sharpest**
and the **slowest**. So raising it flattens the sharpness curve and worsens the velocity
curve.

**`passes: 5` with `skip_boundary: 4` is the default balance.** Go to 8 only if the user
says breathing bothers them more than stepping, and expect to hear about stepping.

Profile by **position within the pair**, never by absolute frame index:

```python
pos = np.arange(len(deltas)) % frames_per_pair
profile = [deltas[pos == k].mean() for k in range(frames_per_pair)]
```

A flat profile is smooth flow. The shape of that profile is the diagnosis.

## More keyframes is the real fix for mid-pair blur

Fewer invented frames per pair means the midpoint is never far from something real.
Going 47 to 23 lifted mid-pair sharpness from 68% to 77% of the pair edge.

**But it is not free**: more keyframes at the same strengths means more total drift, so
lower `steady_strengths` to compensate, and watch the `int(steps * strength)` boundary
while doing it. Overcorrecting there caused a worse blur than the one being fixed.

## Frame-edge smear

RIFE has no flow information beyond the frame border, so it stretches pixels there. It
shows at native resolution as a soft band on the left and right, and it is a **deficit**
of high-frequency energy, not an excess, so a test looking for artefacts finds the wrong
sign.

`edge_crop: 8` removes it (output becomes 1328x752 from 1344x768). `border-crop.md`
validated `0` as safe, but that predates ControlNet and this much motion; re-enable it
whenever per-frame change is high.

## What interpolation cannot fix

If consecutive **keyframes** disagree a lot, RIFE has more to invent and destroys more
detail doing it. Stage III's per-frame change of 1.23 against Savage's 0.83 is why its
interpolated frames were soft even after its keyframes got 76% sharper.

**Sharpening the keyframes cannot fix a stage whose content moves too much between
them.** Reduce the change per pair instead: simpler content, more keyframes, or lower
strengths. See `visual-diagnosis` for telling the two apart.

## Frames per pair is not the dial. Delta per pair is.

Measured 2026-08-19/20, and it reverses the obvious reading of the table above.
**64 frames/pair (`passes: 6`) produced the founder's stepping complaint on a
14-state chain, and was completely clean on a 56-state one.** Same setting,
opposite result, because 14 states across a whole year carry enormous deltas while
56 states across one day carry small ones. What the viewer reads as "stepping" is
the product of the two, never the frame count alone.

So when a piece reads as stepped, **add keyframes before you touch passes**. Then
`passes` is free to set the DURATION, since the same authored chain renders at any
length for the cost of local compute only:

| states | passes | frames/pair | frames | duration at 30 fps |
|---|---|---|---|---|
| 56 | 5 | 32 | 1792 | 59.7 s |
| 56 | 6 | 64 | 3584 | 119.5 s |

Both come from one authoring spend. Render both and let the founder choose; it
costs nothing but time.

**And beware picking a low `passes` for granularity.** Going to `passes: 4` (16
frames/pair) to chase smoothness lands near the flattest-sharpness / worst-velocity
corner of the table — the setting with the least focus breathing has the most
stepping. `passes: 5` is the safe default on this pipeline.
