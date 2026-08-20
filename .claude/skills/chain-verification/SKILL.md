---
name: chain-verification
description: Catch defects in an authored keyframe chain BEFORE rendering, and in the encoded video before showing it to anyone. Use whenever a chain has been built or bridged, before any render, before any publish or send, and whenever the founder reports something wrong in a finished piece. Encodes the 2026-08-19/20 session in which seven defects reached a finished render, every one of them invisible to every metric and every one caught by looking at one region across all states.
---

# Verifying an authored chain

On 2026-08-19/20 a single piece shipped a finished, encoded, delivered video that
contained a **poem the model had written about its own task, carved into a
gravestone**, and later a set of **human faces sculpted into the same stone**. The
chain measured `mean struct r 0.953` at the time. Both were found by the founder
and by one contact sheet, never by a number.

This skill exists because measuring is not checking.

## The one law

**Every content defect this project has recorded came from a BRIDGE. None came
from an anchor.**

An anchor is made by editing a real previous image, so it inherits. A bridge is
asked to invent an in-between, and inventing is where the model takes liberties.
Worse, `banana_keyframes.py` builds the `--bridge` prompt internally and accepts
**no caller text**, so every preservation clause you write into `--edit` reaches
the anchors and **none of it reaches the bridges**.

Recorded bridge defects, 8 in ~130 calls:

| defect | piece |
|---|---|
| a POEM about the bridge's own task, carved on the stone | `labor_not_here` |
| an invented epitaph, "IN LOVING MEMORY OF THOMAS FINCH" | `labor_not_here` |
| **human faces sculpted into the headstone** | `labor_vigil` |
| ivy climbing a stone that neither endpoint has | `labor_vigil` |
| a swirling vortex warped into the grass | `labor_vigil` |
| the bouquet leaving the frame entirely | `labor_vigil` |
| the bouquet jumping ~50 px sideways, twice | `labor_vigil` |
| withered brown roses turning pink | `labor_vigil` |
| one bloom growing much larger than its neighbours | `labor_vigil` |

The bridge prompt DOES contain "do not add a signature, lettering, text". It
failed twice in 28 calls. Treat it as ~93% effective, never as a guarantee.

## The fix, and it is free

**Blend the endpoints instead of generating.** Where two endpoints are close, a
50/50 average IS the correct in-between, costs nothing, and cannot hallucinate:

```python
a = np.asarray(Image.open(prev).convert("RGB"), dtype=float)
b = np.asarray(Image.open(next).convert("RGB"), dtype=float)
Image.fromarray(((a + b) / 2).astype(np.uint8)).save(bridge_path)
```

**Threshold: endpoint mean-abs-diff under 12.** Blends measured from 2.3 to 10.5
were all invisible. **Do not set it at 10.** A gap of 10.08 missed a cutoff of 10
by 0.08, was handed to the model, and came back with a vortex painted into the
grass. Borderline gaps are exactly the ones where a blend is safest and a model
bridge is pointless.

On a 14-anchor / 56-state chain this leaves ~28 of 42 bridges as blends and only
the genuine light transitions as model calls.

## Re-rolling is the wrong reflex

A re-roll draws a NEW random failure; it does not converge. Measured: a bouquet
58 px off was re-rolled and came back **70 px off in the other direction**.

**Roll and keep the best MEASURED candidate**, never the first that returns:

```python
best = 1e9
for k in range(3):
    generate(tmp)
    d = score(tmp)              # distance from target / from neighbour midpoint
    if d < best: best = d; shutil.copy(tmp, out)
    if d < threshold: break     # good enough, stop paying
```

## What each instrument is blind to

Every one of these cost real time. None of them is a gate.

| instrument | blind to |
|---|---|
| `chain_stats` structure r | It is a **sigma-12 low pass**. Carved text, faces, small shape changes and signatures all live in the band it discards. It read 0.953 on the chain with faces on the stone. |
| consecutive SSIM | step size only; a monotonic walk away from frame 0 raises it as the chain dies |
| a **centroid** of the subject | **breaks silently once the subject leaves the measurement box** — "brightest 8%" then locks onto grass and returns a healthy number. Reported fine on the state where the bouquet had left frame. |
| a **position** check | blind to SIZE and SHAPE. An enlarged bloom sat in exactly the right place. Score the region against the mean of its two neighbours instead. |
| a **darkness centroid** | **invalid at night.** When the whole ground darkens it measures the night, not the shadow. |
| neighbour-deviation | conflates legitimate fast change with defect. On a clean chain the median was 0.4, so the MAD was tiny and 27 of 56 states tripped it, all of them real change. |
| saturation / detail outlier scoring | missed both real faults on the one chain with a known answer, and flagged an unrelated state. Engraved grey text on grey stone is neither saturated nor high-contrast. |

**Corollary: a statistical detector you just wrote is unproven.** Test it against
a chain whose answer you already know before you trust it. Mine failed that test
and I kept it only as a hint.

## The gate: one region, every state, at legible size

This is the whole method and it takes two minutes:

```bash
py -3.11 tools/chain_guard.py --dir <accum> --region x0,y0,x1,y1 --strip out.png
```

Then OPEN IT. Read the surface in every tile.

- Choose the region that **must not change**: the slab face, the wall, the object.
- Add a second pass on the **bottom band** for volunteered signatures.
- Add a third on any element with a **locked identity** (a bouquet, a figure's
  hands) — checking position AND shape.
- Thumbnails lie. A 640 px strip made me report a headstone's top had changed
  shape when at native resolution it was identical throughout. Crop tight and
  render each tile large enough to read.

## Check EVERY ring, not only the last

The faces entered at **round 1** and were found only after round 2 had built 24
more states on top of them. Checking `ring24` would have caught it for the cost of
one look, and would have saved a re-render and ~$1.

```
anchors  -> CHECK -> ring(2n) -> CHECK -> ring(4n) -> CHECK -> render -> CHECK
```

## Then check the ENCODED VIDEO, not the states

The states are not what ships. Sweep the file:

```bash
ffmpeg -v error -y -i out.mp4 -vf "select='not(mod(n\,28))',scale=300:-1" -vsync 0 sweep/f%03d.png
```

Contact-sheet it and read it. **Sample density matters**: at every 28th frame a
fault lasting under a second can hide between samples. When the founder reports a
timestamp, convert it and sweep that region at every 8th frame:

```
state = round(seconds * fps / frames_per_pair)
```

## Two traps in the render path itself

**`loop_render.py` hard-codes a 300-frame encode.** Give it a 56-state chain and
it builds all 1792 frames correctly, then **drops them 2.99x into a 10-second
file**, printing `896 frames -> 300 : DROP 2.99x` as a judder warning rather than
an error. Exit code 0. The line `verified: 1408,768,300` reads like success. For
anything that is not a 10 s loop, render with `--keep-frames` and encode the
frames yourself:

```bash
ffmpeg -y -framerate 30 -i <piece>.frames/%05d.png -c:v libx264 -crf 16 -pix_fmt yuv420p out.mp4
```

**An exit code is not a result.** Probe the artefact: frame count, duration,
resolution. A DNS drop killed one bridge mid-run and the surrounding script
carried on happily.

## Reporting

Say which states, what the defect is, and where it came from — anchor or bridge,
round 1 or round 2. `accum[2k] = ring[k]`, `accum[2k+1] = bridge b_k`, so an odd
index is always the later round's bridge. Tracing it that way is what makes the
fix one call instead of a re-author.

Never report a piece as clean on metrics alone. If you have not opened the strip
and the encoded sweep, the honest sentence is "measured clean, not yet eyed".
