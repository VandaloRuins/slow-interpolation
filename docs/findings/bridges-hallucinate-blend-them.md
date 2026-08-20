# Bridges hallucinate, anchors do not. Blend the close ones.

**Status: measured 2026-08-19 across three chains (`labor_not_here`, `labor_return`,
`labor_vigil`), 8 defects in ~130 bridge calls.**

The dual-image bridge is the tool that fixed wrap seams and it is still the right
instrument for a large transition. But it is **the only unconstrained call in the
pipeline**, and every content defect of the session came from one.

## The record

| chain | states | defect | where |
|---|---|---|---|
| `labor_not_here` | 43 | a POEM about the bridge's own task, carved on the stone | bridge |
| `labor_not_here` | 53 | invented epitaph, "IN LOVING MEMORY OF THOMAS FINCH" | bridge |
| `labor_not_here` | 53 (re-roll) | cracks absent from both neighbours | bridge |
| `labor_vigil` | 29, 30, 31 | **human faces sculpted into the headstone** | bridge |
| `labor_vigil` | 3 | the bouquet left the frame | bridge |
| `labor_vigil` | 33 | withered brown roses turned pink | bridge |
| `labor_vigil` | 5, 47 | bouquet jumped ~50 px sideways | bridge |

**Anchors were clean every time.** The asymmetry has a cause: a preservation clause
written into `--edit` reaches only sequential edits. `--bridge` builds its prompt
inside `banana_keyframes.py` and takes no caller text, so *none* of the locks apply
to it. Its built-in prompt does say "do not add a signature, lettering, text" and
that failed twice in 28 calls on one chain, so treat it as ~93% effective, not a
guarantee.

## Re-rolling is the wrong reflex

A re-roll draws a NEW random failure; it does not converge. Measured on
`labor_vigil`: a bouquet 58 px off was re-rolled and came back **70 px off in the
other direction**. Two calls spent, worse result.

## The fix: blend the endpoints

When the two endpoints are close, a straight 50/50 average IS the correct
intermediate, it costs nothing, and it **cannot hallucinate**:

```python
a = np.asarray(Image.open(prev).convert("RGB"), dtype=float)
b = np.asarray(Image.open(next).convert("RGB"), dtype=float)
Image.fromarray(((a + b) / 2).astype(np.uint8)).save(bridge_path)
```

**Threshold, measured:** endpoint mean-abs-diff under about 10 blends invisibly.
Every blend used on `labor_vigil` sat between 2.57 and 7.57 and none ghosted. This
is the same reasoning as the chroma cross-fade in `edit-model-loop` §4: where
content does not move between endpoints, a blend beats a warp.

Reach for a MODEL bridge only when the endpoints genuinely differ (a wrap seam, a
day/night crossing). For a late-round bridge subdividing an already-small step, the
blend is strictly better.

## How to catch these

Not with a metric. `chain_stats` read **mean struct r 0.953** on the chain with faces
on the stone, and `chain_guard`'s statistical pass flagged an unrelated state and
missed the faces entirely. Engraved grey text on grey stone is neither saturated nor
high-contrast, and a sigma-12 low pass removes the band the defects live in.

**Run `chain_guard --region ... --strip` on EVERY ring, not just the final one.** The
faces entered at round 1 and were only found after round 2 had built 24 more states
on top of them. Checking `ring24` would have caught it for the cost of one look.

**And know when your own metric is lying.** A bouquet-centroid check reported healthy
on the state where the bouquet had left frame entirely: once the subject exits the
measurement box, "brightest 8%" locks onto grass and returns a plausible number. A
region metric is valid only while the subject is inside the region.
