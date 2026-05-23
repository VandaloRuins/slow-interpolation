# Decision: how to split `docs/pipeline.md` at Phase D3

Drafted 2026-05-17 by parent chat while waiting for D2 self-migrations. Captures the trade-off so D3 has a paved path, not a fresh debate.

## Status

**Decided: option B (split into manual tutorial + reference).** Execute at D3, after the Renoir release. Until then, the file stays at `docs/pipeline.md` and serves the developer-reference role.

## The problem

[docs/pipeline.md](../pipeline.md) is 361 lines of dense developer-reference: every parameter, every callback, every micro-conditioning trick, every legacy-variant difference, cross-referenced against the legacy scripts. It is the right file for someone who needs to understand the pipeline architecture deeply. It is the wrong file for someone who wants to run their first render.

The docs-strategy plan at [docs-strategy.md](docs-strategy.md) "Phase D3" step 1 says: "Move `docs/pipeline.md` -> `docs/manual/pipeline.md`. Polish for external read." That instruction is under-specified. There are three possible interpretations.

## Three options

### A. Move as-is, then rewrite

Move `pipeline.md` to `docs/manual/pipeline.md`, then heavily rewrite it for tutorial framing. Drop the legacy-variant comparisons, the parameter dumps, the cross-references to legacy scripts. End with a much shorter, friendlier document.

**Pros:** one file, clean manual tier, no duplication.

**Cons:** the deep reference content is lost from the repo. Anyone who needs to understand WHY a parameter is set to a specific value, or what the legacy variants did differently, has to read `src/` directly. The current `pipeline.md` is also the most-cited findings-context-providing doc; cutting it shallow severs those citations.

### B. Split into two files (recommended)

- `docs/manual/pipeline.md` (NEW, tutorial-shaped, 80 to 120 lines): what the four phases DO, the YAML knobs the user touches, worked examples, when to override which preset, cross-link to the reference for depth.
- `docs/reference/pipeline.md` (current `docs/pipeline.md`, moved as-is): the full developer reference. Stays the source of truth for parameter rationale, legacy-variant comparison, callback internals, micro-conditioning trick. Authoritative answer to "why is `crops_coords_top_left = (256, 256)`?"

**Pros:** matches the two-audience reality (downstream user vs developer / contributor / future agent reading the pipeline). Manual is approachable, reference is deep. Forward-references between them are stable.

**Cons:** two files where there was one. Risk of drift between them. Mitigation: the manual is short and cross-links to the reference for any non-trivial detail; the reference is the canonical doc and the manual is the welcome mat.

### C. Keep at `docs/pipeline.md` permanently

No move. `docs/pipeline.md` continues to serve both audiences via its current structure. Manual entry is via [docs/manual/getting-started.md](../manual/getting-started.md), which links to `docs/pipeline.md` for "deeper".

**Pros:** zero file moves. Zero duplication risk.

**Cons:** breaks the four-tier docs structure agreed at D1. The manual tier exists but has no `pipeline.md`. New readers landing on `docs/manual/` see a partial manual and have to navigate up a level for the central reference. The "polish for external read" instruction is also never executed.

## Recommendation: B

The two-audience split is real. A downstream user running their first Renoir render does not need to know that `transition_strength` was a `list[float]` ramp in the engine variant but a single value in the entry-point scripts. A developer hunting a denoise-schedule regression absolutely does. Forcing both audiences through the same doc punishes both.

The drift risk of two files is manageable because the manual will be short (tutorial-shaped, 80 to 120 lines) and explicitly cross-link to the reference for any deep question. The reference is the canonical source of truth; the manual is the friendly entry point.

## What goes where (sketch)

### `docs/manual/pipeline.md` (NEW, ~100 lines)

Sections:

1. **Overview**: the four phases in one diagram, what each produces, where outputs land. 20 lines.
2. **The keyframe segment shape (A/B/C/A-return)**: what the prompts mean, how transitions work, how the return closes the loop. 20 lines.
3. **The two render presets (`standard`, `calm`)**: when to use which. Worked example. 15 lines.
4. **Noise sources**: where to set `render.noise`, the catalog. Cross-link to `findings/noise-sources.md` for the deep reading. 10 lines.
5. **Common overrides**: changing resolution, switching LoRAs, tightening or loosening the drift, changing the loop length (via segment frame counts). 20 lines.
6. **When the render looks wrong**: pointer to `docs/manual/getting-started.md` troubleshooting, pointer to `docs/reference/pipeline.md` for parameter-level depth, pointer to `docs/findings/border-crop.md` for border issues. 10 lines.

What this file does NOT contain: legacy-variant comparison, callback internals, micro-conditioning rationale, the SLERP-of-embeddings math, the structural-decay-radius derivation, the entry-point-vs-engine-variant table. All of that goes in the reference.

### `docs/reference/pipeline.md` (moved from `docs/pipeline.md`, kept whole)

The current 361 lines, unchanged except:

- Header reframed: "Mechanical specification of the existing slow-interpolation pipeline. For a tutorial-shaped introduction see [../manual/pipeline.md](../manual/pipeline.md)."
- All legacy-script relative paths updated for the deeper folder (one more `../`).
- Cross-links to findings docs updated.

## Execution at D3

1. `mkdir -p docs/reference/`
2. Move `docs/pipeline.md` to `docs/reference/pipeline.md`. Fix internal relative paths (one more `../` for legacy refs, callback refs, etc.).
3. Write `docs/manual/pipeline.md` fresh, ~100 lines, per the sketch above.
4. Update `docs/manual/index.md` to point at the new manual page (currently points at `../pipeline.md`).
5. Update `docs/README.md` map: pipeline.md appears in BOTH the tier-1 manual section AND the tier-2 reference section, with a one-sentence note on the relationship.
6. Update `docs/manual/getting-started.md`: the "Next" section now points readers at `manual/pipeline.md`, not `../pipeline.md`.
7. Run `python tools/check_doc_links.py` and fix any rot.

## Why this lives in `docs/planning/` rather than `docs/reference/`

Decisions belong with the planning tier until they ship. After D3 executes, this file can either:
- Move to `docs/planning/history/2026-XX-pipeline-split.md` as a closed-out decision record, or
- Be deleted, since the result is visible in the tree.

Default: delete after D3. The decision is only interesting while it is pending.
