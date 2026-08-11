---
name: motion-compositing
description: Add real directional motion (falling water, drifting cloud) to a slow-interpolation render. Use when the user asks for water that falls, waves that move, or any in-frame motion beyond light drift. Encodes the 2026-08-09 result that the diffusion chain CANNOT carry motion (five mechanisms built and measured dead), the compositing route that works, and the measurement discipline that burned seven instruments in one day.
---

# Motion by compositing

**The headline, so nobody re-runs a dead experiment: the img2img chain cannot carry
directional motion.** Five mechanisms were built and measured on 2026-08-09
(quality-first log, "directional motion" entries):

| mechanism | result |
|---|---|
| displace the masked region between keyframes | water never moved (median 0.00 px of an intended 154); the SUBJECT moved instead, the fall shortened from the top |
| advect only the high band (hp_sigma 6) | 99% of frames identical: everything finer than ~8 px is RE-INVENTED every keyframe (r = 0.05) and cannot carry anything |
| band-pass 10 to 80 px, chosen from measured band survival | +1 px against an intended +154 |
| animate the conditioning, dim streaks (34 to 54) | invisible to ControlNet: phase-following 3/10 at r ~ 0.1 |
| animate the conditioning, bright streaks, K=20, no pixel advection | phase-following 2/20 at r = 0.05 |

The reason is structural: the feedback loop re-derives texture from the low band, the
prompt and the map, and inherits its own history over any injectable signal. Lower
strength does not help; the issue is what DETERMINES the repaint, not how much repaints.

**What works: paint the scene with diffusion, move the water outside it.**
`tools/animate_fall.py`, applied to the raw render before conform:

1. Mask from the PAINTED APPEARANCE, not the control map: the model paints rock inside
   the map's channel, and a geometry mask advects rock. Water = the cool-and-bright
   percentile of the median frame (fall lum 65 to 104 overlaps rock 72 to 87; what
   separates them is r minus b). `--top-guard` excludes a sky vista, which is also
   cool and bright.
2. Band-pass 10 to 90 px moves; the silhouette (coarser) and the grain (finer, which
   the chain reinvents anyway) stay.
3. Roll cyclically WITHIN EACH COLUMN'S OWN MASKED RUN, shift = round(n * m / N) of its
   own run length: texture passes behind rock between tiers, never samples non-water,
   and every column closes its loop exactly. A full-frame roll fed rock texture into
   mid-tier water; do not regress to it.
4. `--gain` ~1.5 and `--damp-fine` ~0.5: measured at gain 1.0 the moved band correlates
   0.60 vs the static grain's 0.91, so the eye locks onto what does not move.

## Waves: `--mode oscillate`

A fall traverses; a wave advances and returns. Same masked-run machinery, but the shift
follows `A * sin(2 pi * cycles * i / n)` instead of a ramp. A sine is zero at both ends
of the loop, so closure holds for any integer `--cycles`, and its zero velocity at the
extremes is correct rather than a compromise: swash does pause before it drains.

**Clamp at the run ends, never wrap.** This is the one real trap. Wrapping is right for a
fall, where water leaving the bottom genuinely re-enters at the top. On an oscillation it
drags content across the entire run at both ends, and it printed as **three hard
crescents in the slit-scan, one per wave period**. `np.clip` instead of `% m` smears the
edge pixel, which is what water piling against the top of its swash looks like.

**Size the excursion against the measured run, not by feel.** `--amplitude` is a fraction
of each column's own masked run, so its pixel value depends entirely on the mask. On
`led13_b_realloc_soft` the foam mask is 4.3% of frame with a median run of 93 px, so 0.10
is only 9 px. Measure the run first:

```python
runs = (mask > 0.5).sum(axis=0); nz = runs[runs > 0]   # median, p90, max
```

**`--perspective` trades physics for resampling.** At 0 the whole water body slides
rigidly, which reads wrong under perspective; above 0 the shift varies along the run so
near water travels further, which is what swash does, but it stretches rather than rolls
and resamples unevenly. Generate both and judge by eye.

**Get the loop-seam control before calling a seam a regression.** The composited clip
measured a seam 4.44x the adjacent-frame step, against the fall's documented 1.4x, which
looks like a bad regression. The SOURCE clip measured **4.77x** on the same column: the
seam was the underlying render's and compositing slightly improved it. The 1.4x benchmark
belongs to a different clip and is not a threshold.

Config side: **`skip_boundary: 0` for any motion clip** (it inserts a positional jump of
~`2*skip/2^passes` of the step at every keyframe), which is the OPPOSITE of the
light-drift tuning; the two cannot share a preset. Static regions cost nothing: flow is
zero there, so RIFE copies them sharp.

Verified numbers to hold new work against: slit-scan diagonals at the designed slope,
loop seam |f_last - f_0| ≈ 1.4x an adjacent-frame step (2.94 vs 2.09 on candidate5).

## Measurement discipline, seven instruments died here in one day

**Every failed instrument failed the same way: it correlated against something static.**
The static mask, the codec noise floor, a zero-delta reference (frame 0's delta IS zero
by construction), the raw-luminance base under a moving band. Before trusting any
motion number, ask: *what static structure could this metric be locked onto?*

Instruments that work:
- **Slit-scan** (one column over time): diagonals = motion, horizontals = still. The
  eye reads it instantly and it cannot pin.
- **Rank-space profiles**: index the masked pixels of a column as a 1D run, band-pass
  ALONG the run before correlating (subtract a gaussian along rank), or the static
  base dominates.
- **Delta fields against a NONZERO reference**: flow minus original at frame i,
  compared against the same delta at a mid-clip frame rolled by the DESIGNED shift.
  Never frame 0.
- **Band-survival table** (correlate consecutive KEYFRAMES per spatial band) tells you
  which scales the chain preserves at all: here, 8 to 240 px survives (r 0.82 to
  0.99), finer than 8 px does not (r 0.05 to 0.31).

When a deterministic pixel operation "measures zero motion", the instrument is broken,
not the operation. That sentence would have saved three hours.
