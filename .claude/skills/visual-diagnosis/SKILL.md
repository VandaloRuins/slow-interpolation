---
name: visual-diagnosis
description: Diagnose what is actually wrong with a rendered video, when the user says it looks blurry, jumpy, stepped, washed out, or "not right". Use before proposing any fix. Encodes the three blind spots of frame-average metrics and the noise confound that between them sent the agent after the wrong cause repeatedly on 2026-08-08.
---

# Visual diagnosis

The user reports a symptom. Your job is to find the mechanism before touching a dial.
The single biggest time sink on 2026-08-08 was proposing fixes for causes that
measurement had not established.

## A frame average is never the answer

It hides three things, and all three were the real cause at some point:

**Temporal structure.** Sharpness peaks at every keyframe and troughs at RIFE's
midpoint, because an invented frame is a blend of two images that disagree. Swing was
30% of the mean and completely invisible in the clip average. It reads as the image
breathing in and out of focus, which the user describes as "blurry moments" rather than
"a blurry video". `tools/pulse_plot.py` draws it.

**Regional structure.** A dense city carries the frame average while sky and water stay
soft. Measure in bands.

**Per-stage structure.** A cycle that is sharp for 20 s and soft for 50 s reports as
fine. **Always split by stage** on any multi-segment render.

## Two rhythms, not one

Distinguish them, because they have opposite fixes:

- **Sharpness pulse** — the image goes soft mid-pair. Reads as intermittent blur.
- **Velocity rhythm** — motion slows at each keyframe and accelerates between. Reads as
  stepping rather than flow.

`skip_boundary` trades one for the other: raising it discards the frames nearest each
keyframe, which are both the sharpest and the slowest, so the sharpness curve flattens
and the velocity curve gets worse. `passes: 5` with `skip_boundary: 4` is the better
balance; 8 only if breathing bothers the user more than stepping.

## Laplacian variance is confounded by noise

It rewards high-frequency energy regardless of source. `structural_decay_radius: 0`
scored **3.5x** on it while reading as a digital render. Always cross-check with an FFT
high-frequency ratio, which is far less noise-biased. If Laplacian rises sharply and the
FFT ratio does not, you have added grain, not detail.

Also: pixel-delta metrics (motion, loop wrap) scale with sharpness, so comparing motion
across renders of different sharpness is confounded. Report absolute values, not only
ratios normalised by the median.

## The instruments

| Tool | Answers |
|---|---|
| `tools/motion_profile.py` | per-frame deltas; loop breaks and speed spikes BY TIMESTAMP |
| `tools/analyse_ladder.py` | per-render sheets plus detail / hf_ratio / drift / loop / decay |
| `tools/pulse_plot.py` | sharpness or velocity over time; makes a rhythm visible |
| `tools/gemini_review.py` | scores subject, loop, motion, image; catches what metrics miss |

## When metrics and eyes disagree

**The eye wins on "does it look good". The metric wins on "what changed".** Gemini
contradicted the numbers repeatedly on 2026-08-08 and was right every time about
quality, while the numbers were right every time about mechanism.

If the user reports a symptom your metric does not show, **suspect the viewing path
first**: a proxy at CRF 26, a 3x downscaled contact sheet, or a page that was never
rebuilt. Three of the reported "blurry" complaints came from those, not from the render.
