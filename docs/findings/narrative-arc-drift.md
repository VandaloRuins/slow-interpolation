# Narrative-arc slow drift on off-distribution endpoints

Date: 2026-05-18.
Branch: main.
Status: Findings 1 and 2 confirmed (v5). Finding 3 in flight (v6 banded-noise render dispatched, verdict pending).

## Question

The default pipeline parameters were tuned for slow palette drift on a stable composition (the Choire v2 and After Cole canonical loops: same vase, same valley, light shifts across A/B/C/A). When the A/B/C/A arc instead carries a **narrative biological transformation** (bare stems to full bloom to wilted dead to bare stems), three failure modes appear that the defaults do not handle:

1. The video opens on full bloom even when the A prompt says "bare stems, no flowers". The LoRA's training-distribution centre dominates the first frame.
2. The loop close from C (wilted) back to A (bare stems) reads as a hard cut, not a drift, because the rendered content has drifted far from the saved anchor.
3. Detail softens at prompt-change moments and on RIFE-warped transitions, because SLERP-blended embeddings between two off-distribution prompts produce uncertain guidance.

This finding documents three interventions, two confirmed and one in flight, and ships a schema extension to support intervention 1.

## Evidence: the roses lifecycle test

Subject: a porcelain vase of pink roses, A/B/C/A arc as **bare stems -> full bloom -> withered dead -> bare stems** (loop closes on the bare-plant state). Rendered through six iterations against the Renoir flowers LoRA epoch 10 at scale 0.80, on Modal L40S, 1344x768, RIFE 6-pass linear, 24 fps.

| Version | Change from prior | Result |
|---|---|---|
| v1 | Baseline (3-light-palette mod of `roses_vase_60s.yaml` with lifecycle prompts) | Soft, all-pink wash, state change barely legible |
| v2 | Front-loaded state language in prompts; grey background; +1 steady, +1 transition | Still soft; state change marginally clearer |
| v3 | `render.structural_decay_radius: 0` | Slightly sharper, still soft; state legible but not strong |
| v4 | `lora_scale 0.80 -> 0.65`; bigger arc (bare -> bloom -> dead -> bare) | Lost Renoir brushwork; A frame still opened on full bloom |
| v5 | **Per-prompt anti-bloom negative on A and A-return**; lora_scale back to 0.80; `frames.return_ 4 -> 10`, `return_pixel_blend_max 0.20 -> 0.55`, `return_strength_end 0.60 -> 0.45` | **Loop close clean (Luca verdict).** A-frame adherence improved. Brushstrokes still soft at prompt-change moments. |
| v6 | Swap noise to `banded_renoir_tuned` (Worley cd=3000 + Perlin fs=16 + low-weight FBM); `frames.transition 5 -> 7` | Dispatched, verdict pending |

Configs at [examples/configs/renoir/roses_bloom_cycle_60s{,_v2,_v3,_v4,_v5,_v6}.yaml](../../examples/configs/renoir/). Outputs at [outputs/creative-tests/roses-bloom-cycle/](../../outputs/creative-tests/roses-bloom-cycle/). Modal logs at `outputs/_harness_logs/roses-bloom-cycle-v*.log`. Total Modal spend across the six iterations + smoke: ~$0.30 through v5, v6 expected to add ~$0.80-1.00 (dense Worley component).

## Finding 1: Per-prompt CFG negatives suppress LoRA distribution bias at off-distribution endpoints

The Renoir flowers LoRA was trained almost exclusively on full-bloom paintings. When the A prompt asks for "bare leafy stems, no flowers at all", the positive language alone fails: the LoRA's training-distribution attractor + the trigger word `rfl,` + the impressionist style suffix all bias the diffusion step toward full-bloom imagery. v1 through v4 demonstrated this; v3 with structural_decay_radius=0 confirmed the bias is upstream of the decay step.

The fix is **classifier-free guidance pressure in the opposite direction**: a strong per-prompt negative prompt enumerates the LoRA-aligned content ("roses, blooms, full bloom, open petals, flowers, petals, floral, blossoms, buds, pink") on the A and A-return frames only. B and C keep the style-level default negative so their full-bloom positives and wilted positives are not fought.

This requires a schema extension: a per-prompt negative override that falls back to the style-level negative when unset.

### Schema change shipped 2026-05-18

[`PromptConfig`](../../src/slow_interpolation/config.py) gained an optional field:

```python
@dataclass
class PromptConfig:
    label: str
    prompt: str
    negative_prompt: str | None = None   # NEW. Overrides style.negative_prompt for this segment only.
```

[`keyframes.generate_keyframes`](../../src/slow_interpolation/keyframes.py) uses the per-prompt negative when set:

```python
for full, p_cfg in zip(full_prompts, subject.prompts):
    neg = p_cfg.negative_prompt if p_cfg.negative_prompt is not None else style.negative_prompt
    e, p, ne, np_ = encode_prompt(pipe, full, neg, guidance_scale)
    all_embeds.append((e, p, ne, np_))
```

Backwards compatible: every existing config that omits `negative_prompt` continues to use `style.negative_prompt`. Verified by re-loading v1-v4 configs after the change.

### When to use per-prompt negatives

Use a per-prompt negative when **the A or A-return frame describes content far from the LoRA's training distribution AND the positive prompt alone is being overridden by the LoRA's bias**. Symptoms: the A frame consistently opens on the LoRA's modal content (e.g. full-bloom roses for a flowers LoRA, daylit landscapes for a sky LoRA) regardless of prompt language. Frame-leading and synonym expansion in the positive have already been tried.

Do not use per-prompt negatives as a substitute for clearer positive prompts. Try positive-language reframes first; the negative is the last lever before code changes to LoRA scaling.

The per-prompt negative on B and C is rarely useful: B (peak state) and C (off-peak state) are usually within the LoRA's distribution and need style-level defaults.

## Finding 2: Loop-closure defaults are tuned for palette drift, not content drift

[`keyframes.py`](../../src/slow_interpolation/keyframes.py) saves an anchor frame after warmup and uses a return segment that combines a strength ramp (`return_strength_start` -> `return_strength_end`) with a quadratic pixel-blend toward the anchor (`return_pixel_blend_max`). The defaults are:

- `return_strength_start: 0.50`
- `return_strength_end: 0.60`
- `return_pixel_blend_max: 0.20`
- `frames.return_: 4`

These defaults were tuned on the Choire v2 and After Cole reference loops, where the A/B/C/A arc carries a palette / light drift on a stable composition. Pixel content at C is close to pixel content at A; a 4-frame return with 20% max pixel-blend toward anchor is enough to close the loop smoothly.

When A/B/C/A carries a **content arc** (here: bare stems to wilted dead is ~80% pixel turnover from A), the defaults under-converge. v1 through v4 closed the loop with a visible hard cut at the wraparound. v5 with:

- `return_pixel_blend_max: 0.55`
- `return_strength_end: 0.45`
- `frames.return_: 10`

closes cleanly. Luca verdict on v5: "loop now reads much more smooth, congratulations."

### Rule of thumb

If the loop arc carries a content drift (subject identity, biological state, or composition change between A and C), override the return-segment parameters in YAML:

```yaml
frames:
  return_: 10         # was 4

render:
  return_pixel_blend_max: 0.55   # was 0.20
  return_strength_end: 0.45      # was 0.60
```

The numbers above are an empirical starting point from the rose lifecycle. They are not claimed as universal optima. Tune `return_pixel_blend_max` between 0.40 and 0.65 to balance loop-close softness (higher = more anchor pull = smoother loop, but the C->A return frames look more like A than like C). Tune `frames.return_` between 8 and 14 to balance smooth approach to the anchor vs total clip length. Tune `return_strength_end` between 0.40 and 0.50 to weight anchor pull (lower) vs diffusion authority (higher) in the final frames.

The defaults stay as they are. The palette-drift case is still the majority of slow-interpolation use, and the defaults work for it. Content-drift configs override.

## Finding 3 (in flight): Banded noise injects detail through prompt transitions

The remaining v5 failure mode is detail loss at prompt-change moments and on some RIFE-warped transitions. Mechanism: transition frames use SLERP-blended embeddings between two adjacent prompts (e.g. "full bloom" SLERP'd with "withered dead"). The blended embedding describes neither state coherently, so the diffusion step has uncertain guidance and produces a soft frame. RIFE then has to warp between softer keyframes, amplifying the loss.

The default walking noise (`EvolvedNoiseWalk`) injects spectrally flat white-ish noise. It does not actively push high-spatial-frequency detail back into the chain.

`banded_renoir_tuned` ([Round 4 winner per `noise-sources.md`](noise-sources.md)) is a `frequency_banded` recipe (Worley cd=3000 + Perlin fs=16 + low-weight FBM) that injects fine Renoir-relevant texture every step. Expected effect on the prompt-change blur: the chain gets fresh high-spatial-frequency content during transitions, partially compensating for the SLERP'd embedding's softness.

v6 is rendering now to test this. Verdict will be added here when it returns.

Cost note: dense Worley cd=3000 is the expensive component, $0.80 to $1.40 per render vs $0.05 for evolved-walk. Worth the cost for release-quality renders; not for fast iteration loops. A cheaper cd=1000 variant exists (Round 5 sweep, ~$0.25); visual equivalence to cd=3000 not yet verified by Luca.

## Finding 4: Warmup is text2img in disguise, the A prompt and the LoRA both dominate it

Mechanistic context for Finding 1 (not a separate intervention).

The first frame of every render comes from the warmup loop at [`keyframes.py:215-218`](../../src/slow_interpolation/keyframes.py#L215-L218):

```python
current_img = _random_noise_image(res.width, res.height)
for wi in range(frames.warmup):
    strength = 0.85 if wi == 0 else 0.75
    input_img = noise_walker.blend(current_img, blend_pct=render.steady_noise_blend)
    current_img = _pipe_call(input_img, embeds_cur, pooled_cur, cfg_kw, strength)
```

The first warmup pass runs img2img at strength 0.85 on a pure-random-pixel canvas. At that strength, img2img-from-random-pixels is effectively text2img: the model has no usable image structure to preserve, so it composes from the prompt embedding alone. The LoRA + trigger word + style suffix are all active. Subsequent passes at 0.75 settle the composition.

The output of the warmup loop is then saved as `anchor_img` and used as the seed for the entire chain. The first frame of the saved video is the first steady frame, generated from the anchor by another img2img step at the steady strength.

**Implication for A-frame prompt adherence**: text2img conditions are exactly where LoRA bias is strongest. The A prompt has to fight the LoRA's distribution attractor without any prior image content to lean on. Strong negatives (Finding 1) are the only intervention that does not require touching the LoRA itself.

## Verdict (preliminary)

For narrative-arc slow drift with off-distribution endpoints:

1. **Add per-prompt anti-LoRA negatives on A and A-return**. Confirmed effective on rose lifecycle v5. Schema extension shipped.
2. **Override return-segment defaults for content-drift loops** (`return_pixel_blend_max 0.55`, `return_strength_end 0.45`, `frames.return_ 10` as a starting point). Confirmed effective on v5 (Luca verdict: clean loop close).
3. **Use banded noise for release-quality narrative renders** to counter SLERP-blend chain-softness. In flight (v6).

The defaults in [`config.py`](../../src/slow_interpolation/config.py) stay as they are. They serve the palette-drift case correctly. Narrative-arc configs override.

## What would change the verdict

- v6 returns soft: per-prompt negative gets the A frame right but the SLERP-blend softness is intrinsic to the transition mechanism. Next step is a per-prompt LoRA scale override (unfuse/refuse cycle on the fused LoRA), which is deferred until v6 evidence is in.
- A future narrative-arc test fails Finding 2 on a different content topology (e.g. a perspective shift A->C rather than a biological state shift). The `0.55 / 0.45 / 10` numbers are a starting point, not a universal optimum.
- A future LoRA is open-distribution enough that Finding 1 is not needed. The schema extension is harmless when unused (defaults to style negative). Document the threshold ("if the A frame opens on the prompt's literal content without negatives, you do not need this finding").

## Source artefacts

- [src/slow_interpolation/config.py](../../src/slow_interpolation/config.py) PromptConfig (negative_prompt field)
- [src/slow_interpolation/keyframes.py](../../src/slow_interpolation/keyframes.py) lines 172-177 (per-prompt encode)
- [examples/configs/renoir/roses_bloom_cycle_60s_v5.yaml](../../examples/configs/renoir/roses_bloom_cycle_60s_v5.yaml) (the confirmed-working narrative-arc config)
- [examples/configs/renoir/roses_bloom_cycle_60s_v6.yaml](../../examples/configs/renoir/roses_bloom_cycle_60s_v6.yaml) (in-flight noise sweep)
- [outputs/creative-tests/roses-bloom-cycle/](../../outputs/creative-tests/roses-bloom-cycle/) (v1-v5 MP4s + manifests; v6 lands when render completes)
- Modal logs: `outputs/_harness_logs/roses-bloom-cycle-v*.log`

---
*Did you reproduce this and observe something different? Counter-findings welcome. See [CONTRIBUTING.md](../../CONTRIBUTING.md) shape 4 and the [finding issue template](../../.github/ISSUE_TEMPLATE/finding.md).*
