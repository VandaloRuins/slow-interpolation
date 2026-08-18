# Kickoff: a cheaper, LoRA-controlled keyframe pipeline

**Paste this into a FRESH chat in `Desktop/slow-interpolation/`.**
Row of record: **PL20**. Plan of record:
[`workstreams/keyframe-authoring/design.md`](workstreams/keyframe-authoring/design.md).
Predecessor, closed: **PL17**, [`findings/image-edit-model-alternatives.md`](../findings/image-edit-model-alternatives.md).

---

## The standing instruction, 2026-08-18

Luca: *"we can keep nano banana pipeline we have now, but ultimately i would like to work
to find cheaper solutions for the same quality and more creative control."*

So this is **exploration alongside a working pipeline, not a migration under deadline.**
The incumbent is frozen and named **banana interpolation v1** at the top of
[`.claude/skills/edit-model-loop/SKILL.md`](../../.claude/skills/edit-model-loop/SKILL.md).
**Do not modify it.** Anything you build is measured *against* it and carries a different
name. He is **open to cloud models, other APIs, or Modal**; this is not a self-hosting
purity exercise. The bar is *"match result at a significant fraction of a cost"*.

---

## The decomposition that organises this

Nano banana currently does **two different jobs** in one dependency, and they have
different failure modes and different fixes:

| job | what it is | current weak point |
|---|---|---|
| **A. Generate keyframe 0** | text to image, from scratch | the painterly register is carried by a **prompt clause**, so it can be forgotten. **Three verticals rendered photographic** exactly that way |
| **B. Author each delta** | image edit, "keep everything, change only this" | the cost centre: 5 to 9 calls per chain at $0.067 each, every retry at full price |

**Splitting them is the point of this brief.** Job A is where *creative control* lives and
a LoRA fixes it outright. Job B is where *cost* lives. They can be won separately, and a
**hybrid is a legitimate and probably the strongest outcome**: a LoRA-conditioned generator
for the base, a cheap editor for the deltas.

The three tracks below are Luca's, in his order.

---

## The synthesis that reframes all of it, and why this is not PL17 again

PL17 asked "is there a cheaper drop-in EDIT model?" and answered no, at $1.53. But read its
economics next to its verdicts:

| candidate | per 10-keyframe chain | why it died |
|---|---|---|
| klein 4B (L40S) | **~$0.06** | painterly gate, edit ONE |
| Mage-Flow 4B (L40S) | **~$0.06** | painterly gate, edit ONE |
| FireRed 20B (A100-80) | ~$0.60 | chain collapse at turn 3 |
| nano banana | **$0.67** | incumbent |

**The two candidates that deliver the 10x saving failed on register, and register is
precisely what a LoRA supplies.** They were tested bare, with no style conditioning at all.
The finding's own §10.9 already names "a LoRA trained on our own corpus" as the first of
three things that would change the answer. **That test has never been run.**

Supporting evidence that conditioning works here: **L47**. A banana-authored composition
survived an SDXL+Hammershoi chain sitting 3px off the anchor at frame 0 and returning
exactly at frame 308, and an out-of-register nocturne held at 0.0% of pixels above 128 in
every frame sampled. The corpus gap is real; anchoring routes around it.

---

## TRACK 1 — Image GENERATION with prompt control and a recognisable LoRA

**The question:** what generates keyframe 0 in our register, reliably, with the style in
**weights rather than words**, and with enough prompt control to place a specific subject?

Why it matters more than it looks: every chain inherits frame 0. A base that drifts
photographic poisons the whole loop, and that is a **measured** failure here, not a
hypothetical.

What to establish:

- **Backbone + LoRA options.** `Hammershoi_Interiors_epoch_10` already exists (trained for
  $1.16, the only LoRA in play) and is SDXL. Is SDXL still the right backbone, or does a
  newer one justify a retrain? Price a retrain on each candidate before recommending it.
- **Is one LoRA enough?** The series spans interiors, landscapes, shores, brickyards. A
  single style LoRA carrying "soft tonal oil, sfumato, no visible brushstrokes, muted" may
  generalise better than an interiors-specific one. Say whether a **new style-only LoRA
  trained on the Arendt corpus** is the better artefact.
- **Prompt control**, concretely: can it place a named subject, hold a stated composition,
  and honour **exact non-square dimensions** (1408x768, 1024x1280, both %64)? Assume silent
  bucket-snapping until disproved; every diffusers-family model tested did it.
- **Recognisability.** Luca's test is whether the output reads as *his* register. Judge it
  by eye at native resolution against `action_mist` and `labor_embers`, not by a benchmark.
- **ControlNet interaction.** Structural control already exists in this repo
  (`skills/control-map`, `tools/make_massing.py`) and a drawn map beat three derived maps
  outright. Note whether the candidate keeps that lever.

---

## TRACK 2 — Image EDITING, the keyframe authoriality, at a fraction of the cost

**The question:** what performs "keep ABSOLUTELY EVERYTHING identical, change ONLY this"
across 5 to 9 sequential edits, at materially under $0.067 per image?

This is the cost centre and the harder problem. Consistency-by-default is what the whole
edit-model loop is built on and what the img2img chain could never do.

Start from PL17 §3.3, which eliminated a long list **with reasons**. Already out on hard
constraints: GLM-Image (80 GB floor), LongCat (1 MP ceiling), Step1X (legacy), Fibo-Edit and
FLUX klein 9B / FLUX.2 dev / Kontext dev (**non-commercial licence, and output goes into a
paid edition**), Z-Image-Edit (does not exist), Bernini, Boogu.

**One PL17 requirement is now SOFTER, which widens the field.** Requirement #2 was
"multi-image input, load-bearing", justified by bridges repairing four chains. The
2026-08-14/15 session weakens that: bridges repeatedly returned near-copies of an endpoint,
and on a colour-temperature gap they were useless — **seven** intermediates, dual-image and
sequential, at one third / halfway / two thirds, every one landing on the cool side, gap
stuck at 19. The bridge is a compositing operation, not an interpolation. So multi-image is
worth having for step-size repair but is **no longer a disqualifier on its own**, and
candidates cut *solely* for being single-image are back in scope. Re-check §3.3 rather than
assuming.

The live candidates, and the specific question for each:

1. **klein 4B or Mage-Flow 4B + a style LoRA.** The direct test of the synthesis above.
   ~$0.06/chain bare. **Does a LoRA close the register gap that killed them at edit one?**
   Mage-Flow is the only candidate with true native resolution and no bucket snapping.
2. **Qwen-Image-Edit.** Held in reserve by §3.3 precisely because **it is the one model we
   could realistically fine-tune**. Documented weakness is pixel drift, which attacks our
   instruments directly, so measure drift against frame 0 from turn one.
3. **A hosted API cheaper than $0.067/image.** Legitimate under "open to cloud models and
   other APIs", but it re-buys the fragility that bit us twice, so it must win clearly.

Settled, and expensive to rediscover: do **not** port the Gemini `EDIT_PREAMBLE` verbatim
(a bare imperative beat it on FireRed); **always pass explicit `height`/`width`**; the
conditioning path downsamples even when the canvas is exact; explicit reference numbering
in a bridge prompt measured **worse** than plain.

---

## TRACK 3 — Put it together and test a new pipeline

Only after 1 and 2 have candidates. **The kill gate comes first** (design.md Phase 1): can
the chosen route author a **controlled delta at all**, one named change with everything else
held? That is what the img2img chain historically could not do and the entire reason the
edit-model loop exists. Do not spend on style quality before that is settled.

Then, in order, each stopping on a no-go:

1. **One delta**, measured with `tools/chain_stats.py`. Go at consecutive structure r >= 0.9
   with the named element visibly changed.
2. **A five-edit run**, checking for the geometry walk that killed `labor_vert_steps` twice.
3. **A full 300-frame loop** through the existing `tools/loop_render.py`, which is
   pipeline-agnostic and should not need changing.
4. **The gate**, `tools/review_gate.py` against the keeper floor, then mandatory eye signoff.
5. **A head-to-head against banana interpolation v1** on the SAME subject, published side by
   side on the field so Luca judges them together.

Name the result something other than `edit-model-loop`, and leave the baseline untouched.

---

## Acceptance criteria, from measured failures

| gate | instrument | bar |
|---|---|---|
| Painterly register | 1:1 crop of a region the edit did NOT name, by eye at native res | **hard stop gate** (PL17 §10.2). Luca rejects the unblended/impasto register |
| Preservation | `tools/chain_stats.py` consecutive structure r | >= 0.9; bridge below 0.85 |
| Chain survival | drift against **frame 0**, same tool | consecutive SSIM alone is blind and actively misleading (§10.6) |
| Colour | **chroma delta per pair**, mean Lab (a,b) | **under ~11.** 22.9 mottles. The two instruments above are grayscale and cannot see this |
| Cheap forecast | per-edit lapvar ratio in an untouched region, ONE call | banana 1.21 compounds to nothing; FireRed 1.38 compounded to x11 |
| Delivered | `tools/review_gate.py` + eye signoff | subject>=7, loop>=9, motion>=5, image>=8 |

---

## The cost baseline, so "too expensive" has a number

- nano banana **$0.067/image**, so **~$0.40 to $0.67 per chain**, **~$4 per nine-piece day**.
  PL17 records ~$20 for a heavier 30-chain day.
- `review_gate.py` **also** runs on Gemini, so the same meter gates publishing.

**Say plainly in your review that the absolute figure is modest.** The three arguments that
actually hold are: **creative control** (the register is a forgettable prompt clause today),
**cost per experiment** (every retry, collapsed bridge and dead chain pays full price), and
**fragility** (the meter depleted mid-production once, stopping keyframes and the gate
together, then failed again as an invalid key that read exactly like depletion).

## Constraints

- **Commercial licence is non-negotiable.** Output goes into a paid objkt labs edition and
  this repo is public and workshop-facing.
- Sizes **1408x768** and **1024x1280**, both %64. Ledwall specs are retired.
- No human hands, no chair, Hammershoi is the only existing LoRA.
- **Verify pricing and availability live.** PL17's own research carried three material errors
  found only on contact: FireRed is 57.7 GB not ~30 and does not fit an L40S, the Microsoft
  Mage-Flow repo 404s, and its `transformers` pin was unresolvable. Treat every number in
  this brief as needing confirmation.
- Budget **$2 to $5** for review plus first probe; route dispatches through the `modal`
  subagent and say so before spending.
- **~91 GB `slow-interp-edit-cache` still exists** (DT19). If you re-probe klein or Mage-Flow
  the weights are already there; if you do not, it should be deleted.

## Deliverable

A recommendation per track, one cost table covering all three, a named first probe, and an
honest statement of what is still unknown. **A clean negative is a first-class outcome** —
PL17 was one, and it is the most useful document in this workstream.
