# SDXL inpaint figure emergence: pure parameter tuning cannot bridge "figure emerges" + "edge wraps"

Date: 2026-05-18.
Workstream of origin: Compositing (Phase 3 workstream #4).
Branch: main.

## Claim

For dual-LoRA compositing sketches via sequential LoRA-swap SDXL inpaint (Renoir background pass → unfuse → Soutine inpaint pass), there is NO combination of mask-coverage × inpaint_strength in the pure parameter space that produces both:

- a recognisable figure inside the mask, AND
- a soft brushwork transition across the figure-ground boundary (edge wrap, not edge slap).

The compositing sketch's goal of "Renoir reads as Renoir, Soutine reads as Soutine, only meeting at the feather band" requires structural conditioning (init-image prior, ControlNet OpenPose, or regional cross-attention with proper Attention Couple). Pure parameter tuning is a dead end.

This finding is from the sketch01 to sketch04 dial sweep on 2026-05-18.

## Evidence

Four sketches, all on `cloud/compositing_sketch.py`, Modal L40S, SDXL Lightning 4-step Euler trailing, seed 42, Renoir epoch 1 @ 0.85 (constant), 832 x 1216, sketch01/02 prompt = `stn, a single standing figure seen from behind, back to the viewer, full body, looking toward the distant horizon, dark heavy coat, twisted silhouette, dragging brush, raw umber and crimson, charged surface, oil painting, expressionist`.

| Sketch | Mask coverage | Inpaint strength | Soutine scale | Prompt | Figure emerged? | Edge wrap? | wrap_score | edge_step | Gemini edge_wrap | Gemini seam (low=good) |
|---|---|---|---|---|---|---|---|---|---|---|
| sketch01 | 4.77% | 0.85 | 0.85 | dark coat | NO | n/a | 0.337 | 0.006 | 9 | 2 |
| sketch02 | 11.82% | 1.00 | 0.85 | dark coat | YES (figure with hat, dark coat) | NO (slap) | 0.522 | 0.573 | 4 | 7 |
| sketch03 | 11.82% | 0.75 | 1.00 | butcher's boy (apron, contradicts back-view) | NO (abstract) | n/a | 0.435 | 0.345 | 6 | 7 |
| sketch04 | 11.82% | 0.90 | 1.00 | dark coat | PARTIAL (small figure at mask edge, rest reverted to field) | NO (slap on the partial figure) | 0.448 | 0.384 | 2 | 9 |

Artefacts at `outputs/compositing-sketch/sketch{01_distant_back_view, 02_centered_compact, 03_butchers_boy, 04_strength_090}/`. Side-by-side viewer at `outputs/compositing-sketch/viewer.html`.

## What each axis tells you

### Mask coverage: there is a subject-emergence floor

Sketch01's 4.77% mask coverage was below SDXL's empirical subject-emergence floor of ~10% frame area (in this configuration: SDXL base + Lightning + LoRA, 4-step). Below the floor, the inpaint prefers texture continuation (field) over discrete subject (figure) regardless of how strong the prompt is.

Above 10% (sketches 02/03/04 at 11.82%) the model CAN render a figure when other parameters permit, but does not always do so.

**Decision rule**: target ~12 to 18% mask coverage for the figure region in compositing sketches. Below 10% defer to a different architecture (regional cross-attention, depth composite).

### Inpaint strength: failure modes at both extremes

- **Strength 0.75 (sketch03)**: too much carryover from the field-coloured underlying noise. The figure prompt cannot overpower the residual bias. Figure regresses to abstract or to nothing.
- **Strength 0.85 (sketch01 small mask)**: figure cannot emerge inside a small mask; conflated with the mask-coverage failure.
- **Strength 0.90 (sketch04)**: partial figure (small, off-centre), rest of the mask reverts to field. Hard edge where the figure renders.
- **Strength 1.00 (sketch02)**: figure fills the mask, but renders from pure noise with zero context carryover. The boundary is a brush stopping point, not a brushwork transition. edge_step jumps from ~0.006 (no figure) to ~0.573 (way above the 0.15-0.40 target band): hard color discontinuity.

The middle of the dial (0.85 to 0.95) is a transitional dead zone where the figure half-emerges with a hard seam.

**Decision rule**: do NOT operate in 0.80 to 0.95 strength range for this architecture. Either run at 1.00 (accept edge slap, fix elsewhere) or escalate to structural conditioning.

### Prompt specificity: subjects that contradict the pose break the render

Sketch03's "butcher's boy in white apron stained with red, seen from behind" combines a Soutine-canonical subject (butcher's boy, hold-out validation prompt H2) with a back-view pose. The apron is by definition on the front of the body. The prompt and the pose are anatomically inconsistent.

Result: SDXL produced neither the apron nor a clean back-view. Confounded with the strength regression so we cannot attribute the failure cleanly, but the prompt design was wrong regardless.

**Decision rule**: for back-view figure prompts, choose Soutine subjects whose canonical depiction is back-compatible (a standing figure in a dark heavy coat, a figure in a dark cassock or surplice, a figure in a worker's smock). Avoid prompts that name front-only garments (aprons, jackets-with-buttons, brooches, ties).

## What the QA toolkit got right and wrong

The four-sketch run was the QA toolkit's first calibration pass against real renders. Findings:

### What the QA toolkit caught

- **edge_step (QA tool 1)** correctly flagged sketch02's edge-slap at 0.573 (target 0.15-0.40).
- **Palette histogram two-region (QA tool 2)** correctly noted the figure region scored 0.751 vs Soutine reference and 0.739 vs Renoir reference (essentially equidistant): the figure that emerged did not actually adopt a strongly Soutine palette. The "register friction" we thought we'd achieve was minimal in pixel-statistics terms even when Gemini scored palette_friction 10/10.
- **Gemini-judge seam_visibility** correctly jumped 2 → 7 → 7 → 9 across sketches 01-04 as the seam got progressively worse.

### What the QA toolkit MISSED

- **Subject-presence**: sketch01's QA grades (Gemini edge_wrap 9, painterly_read 9, seam_visibility 2) read as a strong pass even though the figure subject failed to emerge entirely. The toolkit grades register-coherence and brushwork but not "does the prompted subject actually appear?". This is a calibration gap.

**Recommended fix**: add a fifth axis to `tools/qa/gemini_judge.py`: `subject_realisation` (1-10): "Does the figure prompt's named subject (a standing figure / a bellboy / etc) actually appear as a recognisable form in the masked region? 10 = unambiguous, 1 = no figure visible." Score-aggregation should weight subject_realisation as a gate: if it scores below 5, the other axes' high scores are noise.

Filed as CR-J in the compositing workstream (maintainer's private planning folder during v0.1).

## Decision: escalate to init-image prior (sketch05)

The next sketch in the compositing workstream pivots architecture, not parameters:

- Paint a dark figure-shaped fill into the masked region of the Renoir background BEFORE the inpaint pass.
- The painted shape uses Soutine-coded tones (raw umber + dark crimson) so the underlying noise is already palette-biased toward the LoRA's register.
- Run inpaint at moderate strength (~0.65 to 0.75) over the primed background. The retained 25 to 35% of underlying noise carries the figure structure AND Soutine-coded pixels, so strokes can bleed across the boundary while the figure stays.

Requires Modal entrypoint extension: optional `--primed-background-path-on-volume` that skips pass 1 and uses the uploaded image. ~30 lines on the Modal side.

This is the closest sketch approximation to the design.md production architecture (figure video → BiRefNet alpha → composited into a rendered background → Soutine-LoRA repaint). The init-image is a procedural stand-in for the segmented-figure-video alpha.

## Out of scope here

- **Regional cross-attention (Attention Couple, strategy C)** is the eventual production approach but blocked on REQUEST 0 (dual-LoRA simultaneous load) + `compositing/regional_attn.py` (~250 lines). The compositing workstream's regional-prompt survey covers this; the workstream log lives in the maintainer's private planning folder during v0.1.
- **Depth composite + dual diffusion (strategy D)** is the escalation when occlusion is structural. Out of scope for sketch tests.
- **ControlNet OpenPose conditioning** is the heaviest weapon (forces an explicit skeleton) but requires Modal entrypoint changes plus a pose source per piece. Defer until init-image prior fails.

## Calibration thresholds for future inpaint sketches

| Metric | Target band | Reads as |
|---|---|---|
| `wrap_score` | 0.45 to 0.75 | Healthy brushwork crossing the boundary |
| `edge_step` | 0.15 to 0.40 | Some palette friction at the seam, no hard step |
| `stroke_crossing` | 0.50 to 0.80 | Strokes naturally cross alpha contour |
| Palette inside-vs-figure-reference | > 0.78 | Figure region adopted figure-painter palette (target above background-painter similarity by > 0.04) |
| Gemini `edge_wrap` | >= 7 | Visible brushwork wrap |
| Gemini `palette_friction` | >= 7 | Two registers read as distinct |
| Gemini `painterly_read` | >= 8 | Single painting, not composite |
| Gemini `seam_visibility` | <= 3 | Boundary not visible as technical artefact |
| Gemini `subject_realisation` (proposed) | >= 6 | Figure subject actually appears |

A sketch passes if 7 of 9 metrics land in band AND `subject_realisation` >= 5 (gate).

---
*Did you reproduce this and observe something different? Counter-findings welcome. See [CONTRIBUTING.md](../../CONTRIBUTING.md) shape 4 and the [finding issue template](../../.github/ISSUE_TEMPLATE/finding.md).*
