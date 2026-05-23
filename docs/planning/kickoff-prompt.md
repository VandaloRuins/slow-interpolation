# Kickoff prompt for the first session in this repo

We run this in two steps. Step 1 is the consolidation: study what we already have and document every bit of it. Only when that is done do we move to Step 2, the exploration plan.

Paste **Step 1** at the start of the first chat. When Step 1 is finished and you've reviewed the output, paste **Step 2** in the same session.

---

## Step 1 -- Consolidation and documentation

```
You're picking up a new repo. The pipeline already exists, it was developed in two prior projects (Choire v2 and After Cole) and the source has been cloned into legacy/. Your first job is not to write new code. It is to study what we have and produce clear, accurate documentation, so we and any future contributor can understand the pipeline end to end without reading the legacy code.

Before doing anything else, read these in order:

1. CLAUDE.md
2. README.md
3. docs/technique.md
4. docs/pipeline.md
5. docs/inventory.md
6. docs/roadmap.md
7. docs/context.md
8. docs/dev-setup.md

Confirm in two or three sentences that you've understood the framing.

Then do the following, in order. After each numbered task, stop and report.

1. Read every script under legacy/choire-v2/scripts/ and legacy/after-cole/ line by line. Build per-file annotated notes and update docs/inventory.md with them. Each script should have: what it does end to end, its key module-level constants and what each one controls, its CLI surface, and how it relates to the other scripts. Flag any discrepancies between the code and docs/pipeline.md as you find them, and propose corrections to pipeline.md as a follow-up task (do not silently edit pipeline.md yet).

2. Read the three Choire v2 research docs under legacy/choire-v2/research/. Update docs/pipeline.md with any details they contain that the current draft of pipeline.md missed or got wrong. This is the moment to make pipeline.md airtight.

3. Watch (do not just read filenames -- if you can extract metadata or one representative frame per video, do that) the sample outputs under examples/outputs/. Produce a new doc docs/outputs.md with one short paragraph per file describing what it demonstrates technically and aesthetically. Group by source project (Choire v2 frescoes vs. After Cole landscapes). Highlight the "calm" pair (harbour_market_horizontal vs. _calm; notturno_city_horizontal vs. _calm) as the cleanest A/B comparison of the denoise schedule's aesthetic effect.

4. Map every external dependency the legacy scripts touch: paths into Choire v1's visuals folder, the LoRA weight locations, the RIFE checkpoint, the ESRGAN models, any cross-venv path tricks. Produce a section in docs/dev-setup.md (or a new docs/dependencies.md) that lists each dependency, where it currently lives on disk, what it does, and whether the port should re-vendor it or resolve it from config. Be specific about file paths.

5. Once all of the above is done, propose two or three targeted corrections or clarifications to the top-level docs (README.md, technique.md, roadmap.md) based on what you actually found. Present them as proposed edits, do not apply them silently.

Constraints throughout:

- Strong opinions, named trade-offs, no list-without-position.
- No em dashes. Use commas, periods, parentheses, or "to" for ranges.
- Do not write any code in src/slow_interpolation/. That comes after Step 1.
- Do not edit anything under legacy/. It is a read-only reference.
- Do not propose architectural refactors, port work, or new features yet. We are studying and documenting only.
- When in doubt about scope, stop and ask.

The exit criterion for Step 1: a reader new to the project can understand the pipeline end to end from the docs alone, without reading the legacy code.
```

---

## Step 2 -- Read the exploration brief and propose a plan

Paste this after Step 1 is complete and you've reviewed the outputs.

```
Step 1 is complete. Now read docs/next-exploration-steps.md in full. This is the brief for the new directions we want to take the pipeline.

When you've read it, produce a planning response that does the following:

1. Confirm your understanding of each of the four explorations (noise as authoring surface, webcam depth as noise, dual-prompt dual-noise compositing, anchored live prompting) in one paragraph each. If anything in the brief is ambiguous or seems weak, say so directly.

2. Order the explorations from most-likely-to-de-risk-the-rest to least, and recommend which one we start with. Name the trade-offs.

3. For the recommended starting exploration, propose: (a) the smallest possible first experiment that produces evaluable output, (b) where in the package it lives, (c) what new dependencies it adds, (d) the three biggest risks and how you'd de-risk each.

4. Identify what (if anything) needs to be true in src/slow_interpolation/ before we can start. If the answer is "the pipeline needs to be ported into src/ first", say so and propose the minimum port scope needed to unblock the exploration.

5. Flag where the Renoir flowers release (Phase 3 of the roadmap, the objkt labs deliverable) sits in your proposed order. Do not let exploration ambitions push the release.

Same constraints as Step 1. No code yet. No em dashes. Strong opinions with named trade-offs.
```

---

## What I expect after Step 1

- An updated `docs/inventory.md` with deep per-script notes.
- A tightened `docs/pipeline.md` reconciled against the actual code.
- A new `docs/outputs.md` annotating each sample.
- A new `docs/dependencies.md` (or appended section in `dev-setup.md`).
- A small set of proposed edits to top-level docs.
- A clear feeling that we now understand what we have.

## What I expect after Step 2

- A confirmation that the exploration brief makes sense.
- A recommended order with named trade-offs.
- A concrete first experiment proposal, with risk analysis and minimum-port scope.
- A clear placement of the Renoir release in the timeline.

Then I greenlight, and code starts.
