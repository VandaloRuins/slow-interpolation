# Picking a noise source (for agents)

You are an AI agent picking a noise source for a slow-interpolation render on behalf of a user. The pipeline blends a small noise tensor into each img2img input (8 percent steady, 15 percent transition by default); the noise source controls **how the scene moves frame to frame**, not the composition shifts (those come from prompts).

## The default: `evolved`

**Use `kind: evolved`. It is the only noise source validated against production renders across every LoRA family we have shipped** (Thomas Cole, Casa del Suono fresco, Renoir flowers, Soutine figures). It produces the soft, continuous, breath-like drift the technique is built around. Every reference clip in the repo uses it.

If you do not have a strong reason to deviate, set:

```yaml
render:
  noise:
    kind: evolved
```

Or omit the `render.noise` block entirely; `evolved` is the implicit default.

## Why this is the recommendation (and not a decision table)

The repo also ships six alternative noise sources (`perlin`, `worley`, `simplex`, `fbm`, `image_derived`, `frequency_banded`) under `src/slow_interpolation/noise/sources/`. They were authored during the 2026-05 noise research as an authoring-surface experiment. The exploratory finding ([`../findings/noise-sources.md`](../findings/noise-sources.md)) hypothesised a "spatial-frequency lever" that would let an author choose motion character per render.

**That hypothesis did not validate in production.** The alternative sources produce visually plausible single-frame outputs but none of them improved on `evolved` for any LoRA we shipped against. They remain in the repo as **experimental authoring tools** for researchers who want to extend the technique, not as peers of `evolved` in a production decision.

When you (the agent) are setting up a render for a user, do not present the alternatives as options unless the user explicitly asks for an experimental noise source. Default to `evolved`.

## When to deviate from `evolved`

Three legitimate reasons. In all three cases, surface the choice to the user before committing.

1. **The user explicitly asks for a different source by name.** They have read the findings doc, they know what they want, they want it. Use the kind they named.
2. **The user wants a specific reference image's surface to bleed into the render.** That is the `image_derived` use case (and only that case). Set `kind: image_derived, params: {source_image: <path>}`.
3. **The user is doing exploratory research.** They want to see what the alternatives read like. Render the same config with two or three sources and contact-sheet the result. Frame the output as exploratory, not as a tuning recommendation.

For all other cases, `evolved` is the answer.

## YAML syntax

The selector lives under `render.noise`. Two fields: `kind` and `params`. `walk_rate` inherits from `RenderProfile.noise_walk_rate` (default 0.05).

Default (and recommended):

```yaml
render:
  noise:
    kind: evolved
```

`evolved` takes no required params; the legacy behaviour is the production setting.

If you must use an experimental source:

```yaml
render:
  noise:
    kind: perlin
    params:
      feature_size: 32
```

For `frequency_banded`, `params.sources` is a list of `{kind, params}` recursive sub-source specs. The sub-sources must be `WalkingNoiseSource` instances (`evolved`, `perlin`, `simplex`, `worley`, `fbm`; NOT `image_derived`):

```yaml
render:
  noise:
    kind: frequency_banded
    params:
      band_sigmas: [0.0, 4.0, 16.0]
      band_weights: [0.5, 1.0, 0.7]
      sources:
        - {kind: worley, params: {cell_density: 1000}}
        - {kind: perlin, params: {feature_size: 64}}
        - {kind: fbm, params: {feature_size: 128, octaves: 4}}
```

## Composition motion comes from elsewhere

Noise modulates HOW scene change reads at the pixel level, not WHETHER scene change happens. If a user wants more scene change, the levers are:

- **Prompt semantic distance**: how different A, B, C are from each other. Edit the subject prompts.
- **`render.transition_strength`** (defaults to 0.65): raise to 0.75 for bolder transitions.
- **`frames.transition`** (defaults to 3): raise to 5 or 6 for longer crossfades.
- **`frames.steady`** (defaults to 5): lower to 3 for less dwell per segment.

Do not reach for an experimental noise source to fix a "scene does not change enough" complaint. Diagnose first; recommend the prompt-distance or transition-strength fix.

## When something looks wrong

| Symptom in the render | Likely cause | Action |
|---|---|---|
| Frames flicker / texture pops between keyframes | An experimental noise source paired with a fine-brushwork LoRA | Switch to `evolved` |
| Scene feels too static even at high `transition_strength` | Confusing noise-driven texture with composition motion | Don't change noise; raise `transition_strength` or `frames.transition`, or widen prompt semantic distance |
| Output looks "rendered" rather than "painterly" | LoRA + noise pairing fighting | Switch to `evolved` |
| Composition shifts visibly mid-segment ("jumpy") | Low-frequency experimental noise paired with steady segments | Switch to `evolved` |

The pattern: when in doubt, return to `evolved`. The experimental sources have not yet earned a "use X when Y" recommendation.

## Surface to the user

After picking, tell the user in one line what you chose. If you picked `evolved` (the default), one sentence is enough:

> "Using the validated default `evolved` noise. Override if you want to experiment with an alternative source."

If the user asked for an experimental source by name, name the trade-off:

> "Setting `kind: perlin, feature_size: 32` per your request. Note that this is experimental and was not validated against the shipped LoRAs; results may differ from the reference clips."

## Cross-links

- [`../findings/noise-sources.md`](../findings/noise-sources.md): the exploratory research that produced the six experimental sources + the spatial-frequency lever hypothesis (which did not validate in production).
- [`../../src/slow_interpolation/noise/`](../../src/slow_interpolation/noise/): the implementation. `evolved_walk.py` is the production source; `sources/` contains the experimental alternatives.
