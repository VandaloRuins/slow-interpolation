# Workstream: keyframe-authoring

**Opened** 2026-08-14. **Status: research plan, nothing built.**

You are being asked to remove the nano banana dependency from Phase A and replace it with a
**LoRA-conditioned, locally-run, cheaper keyframe author** that carries the painterly register
in trained weights rather than in a prompt clause.

Read this file before proposing any probe. It exists mainly to stop you re-running an
experiment the project has already closed.

---

## 1. What is already settled, and must not be re-run

**PL17 closed as a clean negative on 2026-08-14.** All three open-weight *edit* models failed
and the verdict was "stay on nano banana", at a cost of $1.53. Do not reopen it in that shape:

| candidate | outcome |
|---|---|
| klein | died on the painterly gate at the FIRST edit, six times nano's warm cast |
| Mage-Flow | died at the first edit, painted visible directional brushstrokes into a sky |
| FireRed | survived Q1, detonated into chroma noise at turn 3 |

Three research corrections that invalidate the obvious next move: FireRed is **57.7 GB, not
~30 GB**, so it does not fit an L40S; the Microsoft Mage-Flow repo **404s** rather than gates;
and the `transformers>=4.57` pin is **unresolvable** against diffusers main.

**The economics were never there either.** FireRed costs ~$0.60 per chain against nano banana's
~$0.67. The 10x saving existed only in the two 4B models, and both failed on their first edit.
`cloud/edit.py` and `tools/edit_keyframes.py` are kept and validated, so re-probing a future
candidate is a one-class change. `slow-interp-edit-cache` holds ~91 GB awaiting a delete-or-keep
call.

**Why this workstream is nonetheless different.** PL17 asked "is there a cheaper drop-in EDIT
model?" and the answer is no. This workstream asks a different question: **can a LoRA-conditioned
GENERATOR, structurally anchored, author the chain instead?** That mechanism was never tested,
and L47 already proved its load-bearing half.

---

## 2. The evidence that makes this plausible

**L47, measured 2026-08-14 at $0.06 for the pair.** With the anchor at YAML root and the log line
verified:

- A **banana-authored composition survives an SDXL+LoRA chain intact**: the chair's dark-column
  span sat 3px off the anchor at frame 0 and returned exactly at frame 308.
- The out-of-register case (a firelit nocturne, a register vhm's corpus lacks) held: mean luma
  43.7 to 68.9 to 43.7 with **0.0% of pixels above 128 in every frame sampled**.

That refuted L44. **The corpus gap is real; anchoring routes around it.** So an SDXL+LoRA chain
can hold a composition it was handed. What is unproven is whether it can *author the sequence of
states* that banana currently authors.

---

## 3. What a keyframe author must actually do

Derive the acceptance criteria from measured failures, not from taste. Every row below is
something that broke a real chain in this project.

| requirement | evidence it matters |
|---|---|
| Hold geometry across a sequential run | `labor_vert_steps` walked its staircase twice, gaining treads and re-proportioning, in BOTH versions. A verbal "SAME number of steps" clause did not hold it. |
| Never let the covering medium hide its own reference | Same failure. Snow on treads erases the treads, so the model re-invents them. Veils and lights are safe; replacements are not. |
| Supply intermediates across a colour-temperature change | **Nano banana cannot.** Seven authored intermediates on `labor_bedroom`, both dual-image bridges and sequential edits, at one third / halfway / two thirds, ALL collapsed onto the cool endpoint. The gap stayed at 19. |
| Not volunteer a signature or a canvas edge | `work_kiln` came back signed in all ten states. `labor_vert_steps` came back painted as a canvas with a tacking margin. `BASE_SUFFIX` now suppresses both, but `work_bricks` still produced a monogram: **1 in 6 slipped even with an explicit "NO monogram" negative.** |
| Respond to coverage stated as a fraction | Incremental language produces changes too small to read as the subject. |
| Carry the painterly register without a prompt clause | **This is the prize.** With no LoRA the register lives only in words, and three verticals rendered photographic because the clause was dropped. Trained weights cannot be forgotten. |

**The crux, and the thing the research must answer first.** Banana gives sequential editing for
free: consistency is the DEFAULT and change is AUTHORED. That inversion is the entire reason the
edit-model route was invented, because the img2img chain gives the opposite. Any replacement must
reproduce it. Do not spend on style quality before this is settled.

---

## 4. Phased plan, with a kill gate on every phase

Each phase ends in a go/no-go. Stop at the first no-go and record the negative; a closed negative
is a result, as PL17 was.

### Phase 0. Decide what "cheaper" has to mean (no spend)

Today's session used roughly 50 banana calls across nine chains. Establish the real per-chain
cost and the break-even against a `$1.16` LoRA retrain plus local GPU time. **If the honest
saving is under about 3x, the artistic argument has to carry the whole case**, exactly as it did
in PL17 where the saving turned out to be nil. State that before building.

### Phase 1. Can a LoRA chain author a controlled DELTA at all? (kill gate)

The minimal probe, and the only question that matters:

- Take one validated banana keyframe as the anchor, at YAML root, log line verified.
- Produce state N+1 differing in ONE named respect (a light level, a coverage fraction), with
  everything else held.
- Measure with the tools that already exist: `tools/chain_stats.py` for consecutive structure r
  and drift against frame 0, plus the chroma delta.

**Go if** consecutive structure r >= 0.9 and the named element actually changed by eye.
**No-go if** the chain drifts the way the pre-banana img2img chains drifted, in which case this
route is closed and the finding is worth as much as PL17's.

Candidate mechanisms, cheapest first: img2img at low denoise over the previous frame with the
LoRA and a root anchor; the same plus a ControlNet map derived from the previous frame; masked
inpainting confined to the changing region; IP-Adapter for identity carry. **Try them in that
order and stop at the first that clears the gate.**

### Phase 2. The five-edit run

A single delta proves nothing about accumulation. Run five sequential deltas and check for the
geometry walk that killed `labor_vert_steps`. Same instruments, plus an eye pass on the strip.

### Phase 3. The colour-temperature test, which banana FAILS

This is where a replacement could beat the incumbent outright rather than merely match it. Ask
for a gold-to-twilight intermediate. Banana cannot produce one at any `--bridge-at`. If a LoRA
chain can, that alone justifies the route, because the current workaround is an analytic chroma
cross-fade applied after the fact.

### Phase 4. Register and cost

Only now compare painterly quality against banana, via `tools/review_gate.py` on a full built
loop against the keeper floor, and settle the true cost per chain.

---

## 5. Instruments to use, and one you must not trust alone

- `tools/chain_stats.py` (landed 2026-08-14) for consecutive structure r paired with drift
  against frame 0. Consecutive SSIM alone is blind to a monotonic walk: in PL17 a dying chain's
  consecutive SSIM went UP and beat nano banana's on garbage.
- **Chroma delta per pair, which the above CANNOT see.** Structure r and SSIM are computed on
  grayscale. Measured on `labor_bedroom`: delta 1.2 clean, 11.0 clean, **22.9 mottles**. A pair
  scored a healthy 0.985 structurally while carrying a hue rotation that broke the render.
- The eye, on both edge strips and a native-resolution crop. Every defect that mattered today was
  found at native resolution and under-weighted or missed by the gate.

---

## 6. Open decisions for Luca

1. **`--chroma-blend` on `loop_render`.** The analytic chroma cross-fade that fixed
   `labor_bedroom` lives in the scratchpad, not the repo. Every light-event piece in this series
   crosses a colour temperature, so this recurs. Proposed as opt-in, never default, because on a
   pair where content genuinely moves an unwarped chroma fade would ghost.
2. **A routine signature audit.** 1 in 6 chains still signs itself despite the negative. Proposed
   as a cheap corner check folded into the critique step, plus the existing median patch.
3. **The ~91 GB `slow-interp-edit-cache`**, still awaiting delete-or-keep from PL17.

---

## 7. What NOT to do

- Do not re-probe klein, Mage-Flow or FireRed. Closed, measured, documented above.
- Do not start with style quality. Phase 1 is a control question, not an aesthetic one.
- Do not assume a saving. PL17's saving evaporated on inspection and this one might too.
- Do not test on a subject whose covering medium hides its own geometry. Use a veil or a light,
  per the taxonomy, or you will be measuring the subject's failure rather than the model's.
