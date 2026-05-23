---
name: Experiment report
about: You ran an experiment end-to-end and want the numbers preserved.
title: "[experiment] "
labels: experiment-report
---

## Experiment

One sentence: what did you run, what question were you answering?

## Setup

| Field | Value |
|---|---|
| Hardware (GPU + VRAM) | |
| OS / Python | |
| Config file used | `examples/configs/...` |
| LoRA (name + scale + epoch) | |
| Noise source (kind + params) | |
| Other deviations from default | |

## Procedure

What command did you run? Did you modify the source first? If so, what changed?

```bash
# command here
```

## Result

Numbers (frames generated, wall time, VRAM peak, output resolution, file size). Concrete observations about visual quality. Failure modes if any.

| Metric | Value |
|---|---|
| Phase A wall time | |
| Phase A.5 wall time | |
| Phase C + D wall time | |
| Output resolution | |
| Output duration | |
| Output size | |
| Visual verdict | |

## Comparison to docs prediction

What does the relevant `docs/findings/*.md` say should happen, and does your run match? If it diverges, this is a counter-finding; please also tick the relevant box in the finding template.

## Artifacts

Link any artifacts you can share publicly: an MP4 hosted externally, a screenshot, a contact-sheet PNG. Do not paste large binaries.

## Are you opening a PR?

- [ ] Yes, PR linked: #___
- [ ] No, just preserving the numbers here.

---
*See [CONTRIBUTING.md](../../CONTRIBUTING.md) and [AGENTS.md](../../AGENTS.md). If you are an AI agent and the result diverges from the docs, please also file a counter-finding.*
