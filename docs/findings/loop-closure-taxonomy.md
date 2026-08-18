# Closing a 10-second loop: choose the closure from the phenomenon

**Status: measured 2026-08-14 across nine ledwall pieces.** Supersedes the single
"close by palindrome" rule in the edit-model-loop skill, which was right for one of
the three cases and silently wrong for the other two.

You are building a loop and deciding how it returns to frame 0. **This decision is made
when you choose the SUBJECT, not when you reach the wrap.** Pick the wrong closure and
no amount of bridging rescues it: the worst piece of the day reached 0.85 after five
extra calls, while the best reached 0.986 on the first try with none.

The instrument throughout is structure `r`: pearson correlation on a contrast-normalised
sigma-12 low pass. Consecutive SSIM alone is not sufficient (see §5).

---

## 1. The three closures

| the phenomenon | closure | what you author | measured wrap |
|---|---|---|---|
| **Self-erasing**: its own process returns it to the start | none needed | the whole arc, ending at frame 0 | **r 0.986 to 0.989** |
| **Reversible**: it runs forward and backward through the same states | palindrome | the forward half only | pixel-exact |
| **Asymmetric**: forward and return are different processes | frame-0-anchored bridges | forward arc, then bridges | **r 0.85, after 5 extra calls** |

### Self-erasing, the best case. Author the whole arc.

Snowfall filling footprints (`ledB_snow_v3`, wrap **r 0.989**), tide covering ripple
marks. The subject's own physics undoes it, so the last authored state IS frame 0 and
the loop closes for free. `--no-palindrome`.

**Prefer these subjects.** Both of the session's cleanest loops were of this kind, both
closed first try with no bridges and no re-authoring.

**And prefer a medium that VEILS over one that REPLACES.** This is a separate axis from
closure and it decides whether the geometry survives at all. A veil (mist, shade, a light
patch, wetness) leaves the thing it covers visible and readable underneath. A replacement
(snow lying on stone treads, foliage swallowing a wall) removes the very reference the
model needs to hold, and once it is gone the model re-invents it. Measured 2026-08-14:
`labor_vert_steps` walked its staircase, gaining treads and re-proportioning the flight,
in BOTH versions, **despite an explicit "CRITICAL: the SAME number of steps" clause in
every edit** — a verbal preservation clause does not hold geometry the subject has hidden.
The same day, `action_mist` veiled an entire valley and its foreground wall stayed pixel-
stable, and `labor_vert_shadow` darkened a wall whose plaster read straight through the
shade. Both scored 10/10/10/9 and 8/9/6/9 with no geometry work at all.

### Reversible, the exact case. Author half.

Frost forming and melting, a light arc, a shadow crossing a wall. Author the forward
half and reverse it: the seam is pixel-exact because the return frames ARE the forward
frames. Halves the spend as a side effect.

**The trap that cost a chain**: do not author the return leg for a reversible
phenomenon. Asked to paint a thaw as "a small clear patch opens at the centre with
beads of meltwater", the edit model painted **a hole punched through the glass**, six
panes of a broken window. It reads "clear patch opens in an opaque surface" as breakage,
not melting. Palindrome was correct from the start and would have avoided it.

### Asymmetric, the expensive case. Expect to pay.

Ivy growing and then withering: growth and decay are genuinely different processes, so
neither of the above applies. The return leg must be authored, and sequential edits are
blind to frame 0, so it drifts. The fix is **bridges anchored on frame 0** (see §3),
which converge instead of walking away. Best achieved: r 0.85.

Budget for this before you start, or pick a different subject.

---

## 2. Palindrome is WRONG for a chain that already returns

`loop_render.py` palindromed by default and produced 448 frames from a 15-state ivy
chain that already ran bare to full to bare. It replayed the entire arc backwards,
doubling the piece. Caught by the frame count, not by watching it.

**Test before rendering:** does the last authored state already equal frame 0? If yes,
`--no-palindrome`. If the states are a one-way half-arc, palindrome.

---

## 3. The dual-image bridge, and where it stops working

Hand the model two states and ask for the moment between. It is anchored to both ends,
so unlike a sequential edit it CANNOT drift, which is what makes it the right tool for
a return leg and for splitting an oversized step.

Measured gains, splitting the worst pairs:

| chain | before | after |
|---|---|---|
| `ledA_window` 2 to 3 | r 0.839 | 0.943 / 0.948 |
| `ledB_snow` 2 to 3 | r 0.911 | 0.991 / 0.946 |
| `ledA_window_v3` worst pair | r 0.421 | 0.514 (mean 0.678 to 0.818) |

**It collapses onto an endpoint when the gap is very large.** On a night-to-dawn step it
returned a near-copy of one side (r 0.996 and 0.999 to that endpoint) while the real gap
stayed at 0.525. A second bridge clones the endpoint again. Above roughly r 0.5, bridging
stops buying anything and the problem is the arc, not the density.

**It collapses on a COLOUR gap too, and there `--bridge-at` is inert.** On a gold-to-twilight
step (§4) five bridges at three different `--bridge-at` settings all returned near-copies of
the cool endpoint. Structure r was never the problem there: it read 0.985. Since the bridge
is a compositing operation rather than an interpolation, it has nothing to composite when
the two states differ mainly in hue.

This matches what the PL17 bake-off measured independently: the bridge is a
**compositing** operation, not an interpolation. Even nano banana's own bridge sits
further from both endpoints than the endpoints sit from each other.

---

## 4. Some transitions are thresholds and cannot be smoothed

**Night to dawn is one.** Every authored intermediate landed on the dawn side, making the
first step larger rather than smaller:

| approach | worst pair r |
|---|---|
| no inserts | 0.542 |
| one dual-image bridge | 0.525 |
| two authored sequential states | **0.428** |

Adding keyframes made it worse. Design around it: dusk to night is safe, and a light
cycle that goes day to night and back through dusk never crosses the threshold.

**Gold to twilight is the second one** (measured 2026-08-15 on `labor_bedroom`). The
golden-hour state and the blue-twilight state are separated by a chroma delta of 22.9
(see §5), and the model has no in-between to give. **Seven** authored intermediates were
spent on that single gap, both dual-image bridges and sequential edits, at `one third of
the way`, `halfway` and `two thirds of the way` — every one of them landed on the cool
side, and the gap stayed at **19**. `--bridge-at` has no purchase here at all.

The tell is the same as night-to-dawn: an intermediate that comes back as a near-copy of
one endpoint. When you see it twice, stop authoring and change something else — the
subject, the light range, or the render (§5).

So the list of un-smoothable light transitions is now **two**, and both are crossings of a
colour temperature rather than of a brightness. Brightness alone interpolates fine: the
kiln's dark-to-firelit chain crosses a far larger luminance range and holds.

---

## 5. Read the numbers against the subject

Consecutive SSIM measures step size and is blind to a monotonic walk away from the
original (see `edit-model-loop` skill §3, and the PL17 result where a dying chain's
consecutive SSIM went UP). Always pair it with drift against frame 0.

But **a moving frame-0 ratio is usually the subject, not a fault**:

| piece | surface energy vs frame 0 | what it is |
|---|---|---|
| `ledC_ruin` | climbs to 2.71x | bare masonry genuinely becoming dense foliage |
| `action_path_vert_wood` | falls to 0.46x | ferns genuinely replaced by smooth bare earth |
| `ledB_snow` | 1.71x then back to 1.24x | trampling, then fresh snow |
| FireRed, PL17 | 0.64 to 7.55 in one turn | **the actual failure** |

The kill signal is a fast monotonic climb past about 3x **with the consecutive ladder
improving underneath it**. Non-monotonic movement that tracks the subject is health.

Likewise low SSIM with high structure r is usually a light or texture change, not drift:
`ledA_window` measured SSIM 0.39 to 0.47, which reads as a broken chain, while structure
r ran 0.995 / 0.972 / 0.839 / 0.892 / 0.990. A dusk-to-night event moves every pixel's
luminance and SSIM cannot tell that from collapse.

### The blind spot: both instruments above are GRAYSCALE

Structure r is a contrast-normalised low pass and SSIM is computed on luminance. **Neither
can see hue.** So a pair can score a perfectly healthy 0.985 while carrying a colour
rotation large enough to break the render, and nothing in §5 above will warn you.

Measured 2026-08-15 on `labor_bedroom`, using mean Lab (a,b) distance per pair:

| chroma delta | result in the rendered loop |
|---|---|
| 1.2 | clean |
| 11.0 | clean |
| **22.9** | **mottled** |

The failure is not in the keyframes, which is what makes it easy to miss. **On a keyframe
the frame is clean; at the MIDPOINT of the same pair the flat surfaces break into blue and
orange blotches.** It is RIFE flow error made visible by colour difference: on a wall or a
floor the flow is ambiguous, so patches blend from different source regions, which is
invisible when both endpoints share a hue and glaring when they do not.

**So measure chroma delta alongside structure r on any chain that changes light**, and keep
it under about 11 per pair. If the phenomenon will not allow that (see §4, gold to
twilight), the fix is not more keyframes — it is to let RIFE carry luminance and structure
and cross-fade the colour analytically between the two endpoints. That is a light-event
remedy only: where content genuinely MOVES between endpoints, an unwarped chroma fade
ghosts.

---

## 6. Frame arithmetic: prefer duplication to a drop near 1.5

`total_frames / 300` decides the retime. Print it BEFORE encoding.

- **Drop ratios near 1.5 are the documented judder.** A 15-state chain at 5 passes gave
  448 frames, a 1.49x drop, sitting exactly on it.
- Dropping to 4 passes gave 224 frames, a 1.34x **duplication**, which is invisible.
- Duplication is the safe side. `minterpolate mci` is refused: it smears painterly content.

Pairs = states (closed loop, wrap included), or `2 x states - 2` under palindrome.
Frames per pair = `2^passes`.

---

## 7. Decision procedure

1. Name the phenomenon. Does its own process return it to the start (self-erasing),
   run backwards through the same states (reversible), or neither (asymmetric)?
2. Pick the closure from the table in §1. Self-erasing and reversible are cheap and
   exact; asymmetric is neither. **Prefer the first two when choosing subjects at all.**
3. Author. Keep any sequential run to about five edits (see the edit-model-loop skill).
4. Measure consecutive structure r AND drift against frame 0.
5. Bridge pairs below about 0.85, but stop if a bridge returns a near-copy of an
   endpoint: above that gap the arc is wrong, not the density.
6. Compute the retime ratio, choose passes so it duplicates rather than drops near 1.5.
7. Verify the served artefact, never the build log.
