---
name: video-review
description: Actually see what is in a rendered video, using Gemini multimodal review plus deliberate frame extraction. Use before judging any render, when the user asks "what do you think", or when a report needs evidence rather than metrics. Covers review-prompt design, the four scoring axes, which frames to extract and at what scale, and where Gemini is reliably right and reliably wrong.
---

# Reviewing a video

Metrics say what changed. They do not say whether it is good. A two-minute render at
30 fps is 3,600 frames and you cannot look at them all, so **which frames you extract is
the whole craft.**

## Gemini review

`python tools/gemini_review.py <video...> --subject "<what it is meant to be>"`

Roughly 40 s and fractions of a cent per clip. Key is read at runtime from
`RNMW-agent/.env`, never printed or stored. Writes `gallery-feedback.json`, which the
gallery loads onto the back of each card so Luca can edit the notes.

**The `--subject` string is the most important input.** State the intent explicitly and
in full. If you write "a Course of Empire cycle" you get a review of a Course of Empire
cycle; if you write the bowtie, the wedge tower, the sphere and which stage should
linger, you get told precisely which of those is absent. Vague subject, useless review.

**The prompt already demands three things**, and keep them if you edit it: score on four
axes, cite **timestamps** for anything flagged, and be critical rather than encouraging.
Without the last instruction the review is worthless praise.

### The four axes and what each actually catches

| Axis | Catches |
|---|---|
| **subject** | whether the intended thing is on screen at all. Started at 1/10 and reached 8/10 over ten renders; the single best progress signal |
| **loop** | wrap discontinuities, which it detects far more reliably than a pixel-delta metric |
| **motion** | rubbery morphing, shimmer, stepping. Usually names the exact element and second |
| **image** | painterly versus digital. The axis metrics are worst at, and it is right |

## Where it is right, and where it is not

**Trust it on quality.** It contradicted the numbers repeatedly and was right every time
about whether something looked good. When `structural_decay_radius: 0` measured 3.5x
sharper, this called it "a smooth digital render". That was correct.

**Do not trust it on presence.** It reported that a modern skyline "never appears" when
the keyframe plainly contained one. It judges the **dominant impression in motion**, not
the best frame. So when it says something is absent, check the keyframes before
believing it, and report the discrepancy rather than picking a side.

It also cannot see below its own sampling. It will not find a one-frame spike; use
`tools/motion_profile.py` for that.

## Frame extraction: pick by structure, not by clock

**Stage sheet.** One frame from the middle of each narrative segment, so you see each
intended state rather than whatever lands on an even time division. Compute the indices
from the segment layout, not by dividing the duration.

**Arc montage.** N frames evenly across the duration, for reading drift and composition
stability. `tools/analyse_ladder.py` builds these.

**1:1 crops.** An identical region at native resolution across variants. This is the ONLY
honest way to judge surface.

**Bands.** Horizontal strips (sky / horizon / mid / foreground) when the question is
regional.

## The rule that cost the most

**Never judge sharpness from a montage.** A sheet panel at 440 px from a 1344 px source
retains **34%** of the detail. Luca called a render blurry from one of these and the
render was fine; the montage was the problem. When sharpness is the question, give a 1:1
crop and say explicitly that it is uncropped and unscaled.

Same trap in the gallery: the web proxy is CRF 26 and retains 57 to 96% of the original
depending on content. If the user reports blur, establish which file they watched before
diagnosing the render.

## Reporting

Put the score table first, then the mechanism, then what is still wrong. Quote the review
directly when it disagrees with your measurement, and say which one you believe and why.
