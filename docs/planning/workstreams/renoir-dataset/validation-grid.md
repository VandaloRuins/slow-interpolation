# Renoir LoRA validation grid

First validation round of the Renoir Flowers SDXL LoRA trained on CivitAI (AI Toolkit engine, AdamW8bit, 10 epochs, Network Dim 32, UNet LR 5e-4, ~19 min wall, 500 yellow Buzz on civitai.red). Trained on 105 captions from `datasets/renoir-flowers/` after Phase A.14 curation. Five hold-out images reserved in `datasets/renoir-flowers/validation/`.

Render config (all 33 renders):
- Resolution: 1216 × 832 (SDXL 3:2 native bucket).
- Seed: 42 (constant across prompts and epochs).
- LoRA scale: 0.85 (single scale for apples-to-apples comparison).
- Sampler: SDXL Lightning 4-step, Euler trailing.
- Pipeline: [cloud/validation_renoir.py](../../../../cloud/validation_renoir.py), three runs on Modal L40S.
- Runtime: 22.7 + 19.4 + 19.1 = **61 s GPU on Modal**, ~6 USD-cents total.

## Headline read

**Epoch 10 is the canonical "strong Renoir" checkpoint for vases and bouquets**, exactly as `docs/findings/lora-training.md` §5 predicted. The hold-out renders (V1 to V5) are convincing Renoir pastiche: broken-colour petals, scumbled backgrounds, the right palette, even a signature in the corner.

**Epoch 1 is unexpectedly useful for flower fields**. The light checkpoint preserves more painterly impressionist atmosphere on outdoor scenes than epoch 10, which has over-fit the auction-catalogue "photo of a painting" surface (the predicted 44% auction-scan cast in Topic D of the pre-compact brainstorm). For Luca's stated target of flower-field renders, **epoch 1 at scale 0.85 is a better default than epoch 10**.

Epoch 5 sits between, slightly closer to epoch 1 on outdoor scenes and slightly closer to epoch 10 on vases.

### Practical recommendation

| Render intent | Checkpoint | Scale |
|---|---|---|
| Vase / bouquet still life (in-distribution) | epoch 10 | 0.75 to 0.85 |
| Flower field, garden, outdoor (off-distribution) | **epoch 1** | 0.85 to 1.0 |
| Mixed scene with bouquet element | epoch 5 | 0.85 |

Update `examples/configs/renoir/*.yaml` accordingly. The four scaffolded configs (roses_vase, anemones, mixed_bouquet, peony_closeup) should reference epoch 10 by default. A new `flower_field_60s.yaml` should reference epoch 1.

### Caveat: visible signatures

Every epoch-10 render has a painter's signature baked into the bottom-right corner. The dataset's 32 Sotheby's + 16 Christie's auction-catalogue scans all show Renoir's signature; the LoRA learned "Renoir paintings have a signature here". For production renders the signature is a Phase B edit (auto-paint over with the brush-mask inpainting workstream at `inpaint-plan.md`) or a hard-coded crop. Epoch 1 sometimes shows it, sometimes not; epoch 10 consistently produces it.

## Track 1: Flower fields (off-distribution, the actual target)

Six prompts. Renoir's idiom is bouquet still life, NOT outdoor scenes. The LoRA's transfer is the open question.

### F1: wildflower meadow

> rfl, a wildflower meadow in late spring, low horizon with grasses and scattered blooms filling the foreground, warm afternoon light, broken-colour pinks and creams against a green-gold ground, loose painterly handling, oil painting, impressionist

| Epoch 1 (light) | Epoch 5 (mid) | Epoch 10 (strong) |
|---|---|---|
| ![F1 epoch 1](../../../../outputs/validation/renoir-epoch-1/F1-wildflower-meadow.png) | ![F1 epoch 5](../../../../outputs/validation/renoir-epoch-5/F1-wildflower-meadow.png) | ![F1 epoch 10](../../../../outputs/validation/renoir-epoch-10/F1-wildflower-meadow.png) |

Read: epoch 1 wins for this prompt. Most painterly. Epoch 10 reads photographic, almost calendar-art. Epoch 5 between.

### F2: poppy field

> rfl, a field of red poppies at the edge of a meadow, distant tree line on the horizon, midday sun, crimson and vermillion against an ochre and umber ground, thinly painted ground with loaded brush on the blooms, oil painting, impressionist

| Epoch 1 | Epoch 5 | Epoch 10 |
|---|---|---|
| ![F2 epoch 1](../../../../outputs/validation/renoir-epoch-1/F2-poppy-field.png) | ![F2 epoch 5](../../../../outputs/validation/renoir-epoch-5/F2-poppy-field.png) | ![F2 epoch 10](../../../../outputs/validation/renoir-epoch-10/F2-poppy-field.png) |

Read: all three are presentable. Epoch 10 most saturated. Epoch 1 softest. Pick epoch 1 for impressionist atmosphere, epoch 10 for vivid pastiche.

### F3: garden path through cornflowers

> rfl, a garden path through tall grasses and cornflowers, vertical composition with the path receding, dappled garden light, powdery blues and pale rose against deep green, scumbled foliage with feathered brushwork, oil painting, impressionist

| Epoch 1 | Epoch 5 | Epoch 10 |
|---|---|---|
| ![F3 epoch 1](../../../../outputs/validation/renoir-epoch-1/F3-garden-path-cornflowers.png) | ![F3 epoch 5](../../../../outputs/validation/renoir-epoch-5/F3-garden-path-cornflowers.png) | ![F3 epoch 10](../../../../outputs/validation/renoir-epoch-10/F3-garden-path-cornflowers.png) |

### F4: irises and daisies along a hedgerow

> rfl, a patch of irises and daisies along a hedgerow, horizontal composition with flowers spilling forward, cool morning light, white petals against a celadon green wall of foliage, broken colour across the petals, oil painting, impressionist

| Epoch 1 | Epoch 5 | Epoch 10 |
|---|---|---|
| ![F4 epoch 1](../../../../outputs/validation/renoir-epoch-1/F4-irises-daisies-hedgerow.png) | ![F4 epoch 5](../../../../outputs/validation/renoir-epoch-5/F4-irises-daisies-hedgerow.png) | ![F4 epoch 10](../../../../outputs/validation/renoir-epoch-10/F4-irises-daisies-hedgerow.png) |

### F5: sunlit garden in early summer

> rfl, a sunlit garden in early summer with flower beds and shrubs in the foreground and trees behind, dappled daylight and warm shadows, broken-colour foliage, loose impressionist touch, oil painting, impressionist

| Epoch 1 | Epoch 5 | Epoch 10 |
|---|---|---|
| ![F5 epoch 1](../../../../outputs/validation/renoir-epoch-1/F5-sunlit-garden.png) | ![F5 epoch 5](../../../../outputs/validation/renoir-epoch-5/F5-sunlit-garden.png) | ![F5 epoch 10](../../../../outputs/validation/renoir-epoch-10/F5-sunlit-garden.png) |

This is the closest prompt to the one outdoor scene the dataset has (`jardin-fontenay.jpg`). Expected to be the strongest of the field track. Visually verify whether epoch 10 finally surfaces the Renoir-garden idiom or stays auction-photographic.

### F6: hill of pink and white roses over a low wall

> rfl, a hill of pink and white roses spilling over a low garden wall, mid-distance composition, buttery cream and apricot tones in golden hour light, layered impasto petals against a soft scumbled background, oil painting, impressionist

| Epoch 1 | Epoch 5 | Epoch 10 |
|---|---|---|
| ![F6 epoch 1](../../../../outputs/validation/renoir-epoch-1/F6-roses-over-wall.png) | ![F6 epoch 5](../../../../outputs/validation/renoir-epoch-5/F6-roses-over-wall.png) | ![F6 epoch 10](../../../../outputs/validation/renoir-epoch-10/F6-roses-over-wall.png) |

## Track 2: Hold-out controls (in-distribution, did the LoRA learn Renoir)

Five hold-outs from `docs/findings/lora-training.md` §2. These were excluded from the training set; their original JPEGs live in `datasets/renoir-flowers/validation/`. The render below is the LoRA's interpretation of a prompt describing each hold-out, not the original painting.

### V1: porcelain vase of roses

> rfl, a porcelain vase of roses on a table, centered still life, warm afternoon light, broken-colour petals against a soft scumbled background, oil painting, impressionist

| Epoch 1 | Epoch 5 | Epoch 10 |
|---|---|---|
| ![V1 epoch 1](../../../../outputs/validation/renoir-epoch-1/V1-roses-vase.png) | ![V1 epoch 5](../../../../outputs/validation/renoir-epoch-5/V1-roses-vase.png) | ![V1 epoch 10](../../../../outputs/validation/renoir-epoch-10/V1-roses-vase.png) |

Read: full Renoir pastiche by epoch 10. The LoRA learned the canonical Renoir-rose-bouquet idiom.

### V2: mixed flowers in earthenware

> rfl, mixed flowers in an earthenware pot, centered still life on a table, loose-bouquet idiom, warm afternoon light, broken colour across the petals, oil painting, impressionist

| Epoch 1 | Epoch 5 | Epoch 10 |
|---|---|---|
| ![V2 epoch 1](../../../../outputs/validation/renoir-epoch-1/V2-mixed-flowers-earthenware.png) | ![V2 epoch 5](../../../../outputs/validation/renoir-epoch-5/V2-mixed-flowers-earthenware.png) | ![V2 epoch 10](../../../../outputs/validation/renoir-epoch-10/V2-mixed-flowers-earthenware.png) |

### V3: anemones

> rfl, a study of anemones, close-cropped fragment, flowers filling the frame edge to edge, cool morning light, white petals against a celadon green wall, layered impasto petals, oil painting, impressionist

| Epoch 1 | Epoch 5 | Epoch 10 |
|---|---|---|
| ![V3 epoch 1](../../../../outputs/validation/renoir-epoch-1/V3-anemones.png) | ![V3 epoch 5](../../../../outputs/validation/renoir-epoch-5/V3-anemones.png) | ![V3 epoch 10](../../../../outputs/validation/renoir-epoch-10/V3-anemones.png) |

### V4: chrysanthemums

> rfl, a bouquet of chrysanthemums, bouquet laid across the frame, fabric or table cloth in the foreground, ochre and umber backdrop, pale petals catching the front-light, feathered brushwork on the leaves, oil painting, impressionist

| Epoch 1 | Epoch 5 | Epoch 10 |
|---|---|---|
| ![V4 epoch 1](../../../../outputs/validation/renoir-epoch-1/V4-chrysanthemums.png) | ![V4 epoch 5](../../../../outputs/validation/renoir-epoch-5/V4-chrysanthemums.png) | ![V4 epoch 10](../../../../outputs/validation/renoir-epoch-10/V4-chrysanthemums.png) |

This is the sparse-evidence test (only 3 chrysanthemums in the training set after hold-out). If epoch 10 generalises to chrysanthemums it learned the family idiom, not just the literal training examples.

### V5: geraniums in a copper basin

> rfl, geraniums in a copper basin, centered potted plant on a table, warm afternoon light, broken-colour leaves against a deep rose ground, thinly painted ground with loaded brush on the blooms, oil painting, impressionist

| Epoch 1 | Epoch 5 | Epoch 10 |
|---|---|---|
| ![V5 epoch 1](../../../../outputs/validation/renoir-epoch-1/V5-geraniums-copper.png) | ![V5 epoch 5](../../../../outputs/validation/renoir-epoch-5/V5-geraniums-copper.png) | ![V5 epoch 10](../../../../outputs/validation/renoir-epoch-10/V5-geraniums-copper.png) |

This is the extrapolation test. Zero geraniums in the training set (the only geranium painting in the dataset was held out). The LoRA must render "geraniums" from base SDXL knowledge alone, tinted by Renoir style.

## Decisions

1. **Epoch 1 is canonical for outdoor / field renders.** Update `examples/configs/renoir/*.yaml` to reference epoch 1 for any field scene; epoch 10 only for vase still lifes. Adds a default `lora_field_path` next to `lora_path` in the schema, or creates a separate `flower_field_60s.yaml`.
2. **Signature in epoch-10 corner is a known issue.** Solutions ranked: (a) prompt with "no signature, no watermark, no border" in negative (try first), (b) brush-mask inpainting via the `inpaint-plan.md` workstream when shipped, (c) hard crop 5% off each side post-render. Pick after a quick prompt-level test.
3. **Modal trainer cold-run baseline:** these 33 renders are the canonical ground truth. When `cloud/train_app.py` retrains the Renoir LoRA on Modal, render the same 33 prompts on the resulting epoch-10 and compare side-by-side. The Modal-trainer run is "correct" when the renders match within visual tolerance.

## Next-step options

Pick one:

- **Ship the LoRA as-is and run a real 60s flower-field clip** at epoch 1, scale 0.85, against `tcole_valley.yaml`-style settings. Validates the full pipeline (Phase A through D) on real subject matter, not just keyframes.
- **Retrain with Kohya engine and tuned hyperparameters** (Network Dim 16, Alpha 8, UNet LR 3e-5, 6 repeats per `lora-training.md` §3) as a comparison run. Another 500 to 1000 Buzz. Lower-LR run may give a cleaner outdoor-scene transfer.
- **Source 15 to 25 Renoir landscape paintings** (Le Jardin de Cagnes, La Cueillette, Path Leading Through Tall Grass, Wargemont and Essoyes garden scenes) and retrain to deepen the off-distribution transfer. Closes the gap between vase pastiche and field pastiche. ~1 hour of curation + another training run.

Recommendation: run the real-clip test first (path 1). If the epoch-1 flower-field rendering is good enough at full pipeline scale, ship and worry about landscape augmentation only if Luca later wants stronger outdoor pastiche. The Renoir LoRA is ALREADY useful for the objkt labs release; the bottleneck is no longer the LoRA, it is the clip composition.
