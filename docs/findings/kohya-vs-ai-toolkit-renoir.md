# Kohya sd-scripts vs AI Toolkit on the Renoir dataset

Date: 2026-05-18.
Dataset: `datasets/renoir-flowers/renoir-flowers-civitai.zip`, 105 images, trigger `rfl`.
Scope: head-to-head comparison of the same dataset trained under two different SDXL LoRA engines, evaluated against the same 11-prompt validation grid at identical render config. Numbers are from production runs, not synthetic benchmarks.

This is the first findings doc that compares engines with measured outputs. Treat the verdict as load-bearing for the engine-selection decision in [`../manual/train-lora-on-modal.md`](../manual/train-lora-on-modal.md) Step 1, where the default trainer is set to Kohya on Modal.

## Trainers compared

| Aspect | CivitAI baseline | Modal trainer |
|---|---|---|
| Engine | AI Toolkit (CivitAI's current default) | Kohya `sd-scripts`, commit `502cc3fab2aa` |
| Host | civitai.red (yellow-Buzz queue) | Modal L40S (`slow-interpolation-trainer` app) |
| Network Dim / Alpha | 32 / 32 | 16 / 8 |
| UNet LR | 5e-4 | 3e-5 |
| Text encoder LR | (default) | 0 (UNet-only) |
| Optimizer | Adafactor | AdamW8bit |
| Repeats | 2 | 6 |
| Epochs | 10 | 10 |
| `save_every_n_epochs` | 1 (3 keepers: 1, 5, 10) | 1 (all 10 saved) |
| Mixed precision | (default fp16) | bf16 |
| Resolution / bucketing | 1024, bucketed | 1024, bucketed |
| Wall time | ~19 min | 46.6 min |
| Cost | 500 yellow Buzz (~$1.50) | $1.51 (manifest `estimated_cost_usd`) |
| Checkpoint size per epoch | 228 MB | 85 MB |
| Reproducibility | "trust civitai" | Manifest pins `trainer_version` SHA + `sdxl_base_revision` |
| Per-image weights | No | Schema reserved (`per_image_repeats`), v2 |
| Hand-off filename | manual (user uploads + renames) | automated via `publish.checkpoint_template` |

The two trainers are deliberately not at hyperparameter parity. Each uses its own engine's recommended defaults for SDXL LoRA on this scale of dataset. The comparison is "out-of-the-box engine A vs out-of-the-box engine B", not "controlled hyperparameter A/B".

## Render config (identical across both)

- Model: SDXL 1.0 base + SDXL-Lightning 4-step LoRA + TAESD VAE
- Resolution: 1216×832, landscape, 4 inference steps, guidance 1.5
- Seed: 42 (constant across all 33 renders per LoRA)
- LoRA scale: 0.85
- Negative prompt: same 14 token list across both
- Renderer: [`../../cloud/validate_lora.py`](../../cloud/validate_lora.py) via the [`../../examples/configs/validation/renoir.yaml`](../../examples/configs/validation/renoir.yaml) config

## Prompts (11)

Six off-distribution flower-field prompts (the actual production target for slow-interpolation) plus five in-distribution bouquet hold-outs. Defined in [`../../examples/configs/validation/renoir.yaml`](../../examples/configs/validation/renoir.yaml); see [`../planning/workstreams/renoir-dataset/validation-grid.md`](../planning/workstreams/renoir-dataset/validation-grid.md) for the original CivitAI-only writeup of the same prompt set.

## Verdict per prompt (epoch 10, lora_scale 0.85)

| Slug | CivitAI | Modal | Notes |
|---|---|---|---|
| F1 wildflower meadow | painterly, slightly muted | brighter greens, more confident broken-colour | Modal stronger |
| F2 poppy field | red poppies with trees, painterly | red poppies with dirt path, more saturated, twisted brushwork | Modal slightly stronger |
| F3 garden path cornflowers | cool blue florals, painterly | more vivid cornflower blue, dappled light | Modal stronger |
| F4 irises daisies hedgerow | small white florals, painterly | bold white florals, impasto, "Geraniums and Cats" handling | Modal stronger |
| F5 sunlit garden | pink/red beds, painterly | broken colour across full frame | Modal stronger |
| F6 roses over wall | pink roses, painterly | denser pink cluster on cottage wall, more painterly | Modal slightly stronger |
| V1 roses vase | pink roses, classical Renoir bouquet | pinker roses with yellow hints, painterly | parity |
| V2 mixed earthenware | dense bouquet, strong yellows / reds in dark pot | softer / looser handling | parity (Modal more "Renoir-loose") |
| V3 anemones | orange-red anemones, dark green wall | white / pale anemones | parity (different palette read, both Renoir) |
| V4 chrysanthemums | yellow / cream, very Renoir | similar, slightly looser bouquet | parity |
| V5 geraniums copper | red geraniums in copper basin | red geraniums in pot | parity |

**Headline**: Modal-trained matches CivitAI on bouquets (in-distribution) and visibly outperforms on flower fields (off-distribution, the actual production target for slow-interpolation drift videos).

## Why Modal wins on off-distribution prompts (working theory)

Two contributors, not yet isolated:
1. **More repeats** (6 vs 2): Kohya saw each training image ~3x more often per epoch, deeper convergence on the style transform.
2. **Lower UNet LR + AdamW8bit instead of Adafactor**: smaller step sizes + adaptive moments may yield a smoother loss surface, allowing the LoRA to encode style as separable from subject. AI Toolkit's higher LR + Adafactor may overfit the bouquet subject distribution at the expense of generalizable brushwork.

Disentangling these would require a controlled A/B (Kohya at AI Toolkit's hyperparameters, AI Toolkit at Kohya's hyperparameters). Not done. The production decision does not depend on the theory; the measured outcome is sufficient.

## Signature artifact: CivitAI bakes them in at epoch 10, Modal smoothed them out

Of the 105 training images, 48 are auction-catalogue scans with visible Renoir signatures in the bottom-right corner.

- **CivitAI epoch 10**: signatures bake into the bottom-right corner across multiple V renders. Documented in [`../planning/workstreams/renoir-dataset/validation-grid.md`](../planning/workstreams/renoir-dataset/validation-grid.md) headline.
- **Modal epoch 10**: visual sweep of the same V renders shows no obvious signature contamination. Not pixel-validated; the observation is qualitative.

The Modal trainer did not engineer this; no training-time negative prompt was wired. The smoothing is incidental, likely from the combination of lower LR + more repeats + UNet-only training (text-encoder un-touched, so caption-token associations are weaker). The inpaint workstream's planned signature-removal dataset patch may be partially redundant for the Modal-trained LoRA; verify before spending the inpaint API budget.

## Storage and load implications

| Cost dimension | CivitAI | Modal | Delta |
|---|---|---|---|
| Disk per checkpoint | 228 MB | 85 MB | -63% |
| Disk per 3-keeper set | 684 MB | 255 MB | -429 MB |
| LoRA load wall (validation_renoir.py) | similar | similar | parity (LoRA-load is bottlenecked on disk read + fusion, not parameter count at this scale) |

Smaller checkpoints are strictly better for distribution, cold-storage, and workshop-handout sizing. The artistic quality is the same or better.

## Production decision

For slow-interpolation production rendering: **Modal-trained Renoir is the chosen LoRA**. CivitAI baseline archived to `models/loras/archive/civitai-renoir-2026-05-17/` with a README documenting provenance and a restore script.

For workshop students: **Modal-trained is the canonical training path**. CivitAI is now optional / archival per [`../manual/dataset-curation.md`](../manual/dataset-curation.md) Phase 5 (rewritten 2026-05-18).

## What this finding does NOT claim

- Kohya is better than AI Toolkit in general. The comparison is on one dataset, one set of hyperparameters per engine, one render config. Other domains (figures, landscapes, abstracts) may behave differently.
- The Modal trainer is correct for every LoRA. It is correct for the Renoir cold-run shape (80 to 110 image dataset, single domain, style transfer goal). Soutine figures is the next test, staged at [`../../examples/configs/training/soutine_figures.yaml`](../../examples/configs/training/soutine_figures.yaml) (not yet run).
- The hyperparameter choices are universal. Per [`lora-training.md`](lora-training.md) §3, these are recommended starting points; specific domains may need adjustment.

## Reproducing the comparison

1. CivitAI baseline at `models/loras/archive/civitai-renoir-2026-05-17/Renoir_Flowers_epoch_{1,5,10}.safetensors`. Restore via the README in that folder.
2. Modal-trained at `models/loras/Renoir_Flowers_epoch_{1,5,10}.safetensors` (current local production) and on the `slow-interp-loras` Modal volume.
3. Side-by-side viewer: [`../../outputs/validation/comparison.html`](../../outputs/validation/comparison.html). Open in browser, filter by track, click any cell to zoom.
4. Static PNG comparison grids: `outputs/validation/comparison_e10_F.png` and `comparison_e10_V.png`.
5. Re-render either side via:
   ```powershell
   modal run -m cloud.validate_lora --config examples/configs/validation/renoir.yaml --epoch 10
   ```
   Outputs land at `outputs/validation/renoir-flowers/epoch-10/` on the slow-interp-outputs volume.
