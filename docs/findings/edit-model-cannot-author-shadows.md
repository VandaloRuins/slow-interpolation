# The edit model will not author a cast shadow you specify

**Status: measured 2026-08-19 across three prompt formulations and one controlled
probe, on the `labor_sundial` and `labor_vigil` chains.**

You are staging a piece where the sun crosses and the subject's own shadow sweeps,
the way `work_chair_day` moves a patch of window light across a room. It will not
work. The edit model holds a **lighting mood** reliably and places a **cast shadow**
not at all, and the two are easy to confuse because the moods are convincing.

---

## What was asked, and what came back

| formulation | instruction | result |
|---|---|---|
| 1, `labor_sundial` anchors | "a LONG SOFT SHADOW thrown across the grass to the LEFT", per state | shadow **teleported twice** and was static in between |
| 2, `labor_vigil` anchors | direction AND length named per state, coupled to a second change | present in **5 of 12** states, never reversed |
| 3, probe | "a dark band from the base of the stone reaching ALL THE WAY TO THE LEFT EDGE, unmistakable and hard-edged" | **no change at all** against the input frame |

The third is the decisive one. It was a single edit against a validated frame, with
nothing else asked for, in the most concrete language available. The output was
essentially identical to the input.

## The measurement that names it

Track the luminance-weighted **darkness centroid** across a foreground strip; its
x-position is where the shadow mass sits.

```python
g = np.asarray(im.crop(GRASS), dtype=float).mean(axis=2)
g = g / g.mean()                       # normalise out day/night brightness
dark = np.clip(1.0 - g, 0, None)
col  = dark.sum(axis=0)
centroid = (col * np.arange(len(col))).sum() / col.sum()
```

On `labor_sundial` (36 states) it read ~430 px for states 0-8, **jumped 276 px in a
single pair**, sat at ~660 for sixteen states, then jumped back. Mean movement
26.8 px/pair against a max of 275.9. That is a teleport with long dead stretches,
which is exactly what the founder saw and described as "the day night cycle stops".

**The metric is invalid at night** and this cost an hour. When the whole ground
darkens, a darkness centroid measures the night, not the shadow. Confirm night
states by eye; the number will look plausible and mean nothing.

## Why this is not a prompting problem

It is the same limit as [chained-diffusion-limits](chained-diffusion-limits.md) and
[motion-compositing](../../.claude/skills/motion-compositing/SKILL.md): **the chain
cannot carry directional motion.** A shadow sweeping across ground is directional
motion of a large soft region, and asking for it per-keyframe does not convert it
into something the model will place. Lighting *mood* is a global tone shift, which
the model does hold: dawn, noon, warm dusk and blue night all rendered convincingly
in the same chains that refused the shadow.

## What to do instead

1. **Let the light cycle carry the time.** Dawn to noon to dusk to night reads
   clearly and costs nothing extra. This is what shipped.
2. **Give the loop a second element that DOES convert.** On `labor_vigil` a bouquet
   locked to one species and one position, wilting monotonically, carried the whole
   piece. Locking it took an explicit clause in every edit: same flowers, same
   count, same position, same arrangement, only freshness changes. That moved the
   bouquet's positional drift from **118 px to 18 px**.
3. **If the shadow choreography is the point, composite it.** Render under flat
   light and lay a geometrically-correct moving shadow over the frames. That is the
   documented route for directional motion and it is a build, not a render.

## Do not confuse this with the shadow pieces that worked

`work_chair_day` (gate 9/9/7/8) and `work_chair_slow_trim` (9/10/10/9, the project's
first motion 10) both have moving light and both passed. They were authored by a
**different pipeline** and, in the chair pieces, the shadow IS the subject filling
the frame rather than a small element asked to move across a large one. Do not read
their success as evidence that the edit model will do this.
