# models/

Local LoRA checkpoints and any other large model assets the pipeline needs.

The `loras/` subtree is **gitignored** (LoRA checkpoints are 200+ MB each, change per release, and live outside source control). The directory itself is preserved via `loras/.gitkeep`. Users (or release scripts) populate it.

## Expected layout

```
models/
  loras/
    Thomas_Cole_epoch_10.safetensors   ~218 MB, default for After Cole renders
    Thomas_Cole_epoch_1.safetensors    ~218 MB, light style fallback
    <renoir-flowers>.safetensors        trained; see findings/lora-training.md
    <other domain LoRAs>.safetensors
```

## Where the originals live

- **Thomas Cole** (epoch 1, epoch 10): trained for the After Cole CtrlShift submission. Master copies at `c:/Users/lucaa/OneDrive/Desktop/After Cole/lora-dataset/checkpoints/`.
- **Casa del Suono fresco** (epoch 3, epoch 4): trained for Choire v2. Master copies at `c:/Users/lucaa/OneDrive/Desktop/Choire/visuals/lora_weights/`. Not vendored here by default; copy in if rendering fresco subjects.
- **Renoir flowers**: not yet trained. Phase 3 of the roadmap.

## How configs reference these

YAML configs under `examples/configs/` use repo-relative paths like
`models/loras/Thomas_Cole_epoch_10.safetensors`. The path is resolved by the
`load_pipeline_config` loader without modification, so absolute paths also work
if you want to point at the originals instead of duplicating.

## Policy

No sibling-folder dependencies. Configs that ship in this repo must reference
either `models/loras/*` or HuggingFace IDs, never `../Choire/` or `../After Cole/`.
See [docs/dependencies.md](../docs/dependencies.md).

## Hammershoi Interiors (vhm) — added 2026-08-12

`models/loras/Hammershoi_Interiors_epoch_{1..10}.safetensors` (also on the
`slow-interp-loras` volume). Trigger `vhm`, default **epoch 10 at lora_scale 0.80**
(chosen by instrument sweep on the SDXL-base backbone). Floral preset (rank 16 /
alpha 8). Dataset: 115 public-domain works (SMK CC0 + Wikimedia Commons), curated by
the maintainer through the dataset-mosaic gallery. **Caveat: the corpus contains no
nocturnes; the LoRA renders night prompts as pale daylight.** Training config:
`examples/configs/training/hammershoi_interiors.yaml`.
