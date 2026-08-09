---
name: render-sweep
description: Run a comparison sweep of slow-interpolation renders that actually answers a question. Use when the user asks to test settings, compare variants, tune a render, or "try X and see". Covers isolating one variable, validating configs before spending, dispatching to Modal, verifying completion properly, and reporting negative results as first-class. Encodes the coupled-dial rules whose violation caused three separate regressions on 2026-08-08.
---

# Render sweep

A sweep is only worth its GPU time if the result is attributable. Most of the wasted
renders on 2026-08-08 moved two things at once.

## Before you spend anything

**Isolate one variable.** If you must move two, say so in the config comment and expect
an unattributable result. `rc_base_held` changed backbone AND guidance and its failure
could not be assigned to either.

**Respect the coupled dials.** Each of these caused a real regression:

| Raising | Requires lowering | Why |
|---|---|---|
| `num_inference_steps` | `steady_strengths` | more authority per frame becomes more drift |
| keyframe count | `steady_strengths` | total drift is roughly K x per-frame change |
| keyframe count | `structural_decay_radius` | decay fires once per keyframe and accumulates |

**Check the integer boundary.** Diffusers runs `int(num_inference_steps * strength)`.
At 12 steps, 0.44 gives 5 real steps and 0.39 gives 4. That silent 20% loss caused an
entire render's blur. Print the real step count when validating.

**Validate before dispatch**, always, it is free:

- CLIP tokens on **both** SDXL tokenizers, take the max, target <= 62 of 77. A prompt
  overran once and silently truncated the drift term, which was the whole subject.
- `expected_keyframe_count(cfg)` and `K * (2**passes - 1 - 2*skip_boundary) - 1`
  against `conform.py`'s **300-frame floor**.
- Every referenced file exists: control maps, anchor images, LoRA paths.

## Dispatch

```
modal run -m cloud.batch --configs "a.yaml,b.yaml,c.yaml"
```

Comma-separated, not a glob: the shell expands a glob before Modal sees it and the CLI
rejects the extra arguments. On Git Bash prefix `MSYS2_ARG_CONV_EXCL='*'`.

Variants that differ only in YAML body batch into one parallel `.map()`. Anything in the
`modal:` block (`gpu`, `preserve_staging`, `skip_keyframes`) is part of the grouping key
and splits the batch, so keep those uniform across a sweep.

Set `preserve_staging: true` when you want the keyframes back, which is whenever
sharpness or per-stage behaviour is the question.

## Verify, do not trust the exit code

`modal run` can exit 0 on a partial batch, and a dropped connection returns the shell
while the remote work continues. Use `python tools/modal_status.py --contains <prefix> --count <n>`,
which checks server-side app state plus artifact presence.

Then `python tools/sync_outputs.py --prefix <name>` to pull AND rebuild. Count what
arrived: a download silently lost one rung's keyframes once because the destination
parent did not exist and modal's error was a Windows codepage crash on its own
checkmark, swallowed by `2>/dev/null`.

## Judge

Follow the `visual-diagnosis` skill. In short: measure per stage, per region and over
time; never from a frame average; and get `tools/gemini_review.py` to score it, because
when the metrics and the perceptual read disagree about whether something looks good,
the perceptual read has been right every time.

## Report

**Negative results are first-class.** The two most informative renders of 2026-08-08
scored worst: `v10` proved the LoRA was not the cause of the instability, and `v3b`
proved that a 3.5x sharpness gain can look worse. Say what was refuted.

State the prediction BEFORE the result where you have one, so it cannot be reinterpreted
afterwards. And when a measurement contradicts what the user reports seeing, assume the
measurement is measuring the wrong thing until proven otherwise; that was true four
times out of five.
