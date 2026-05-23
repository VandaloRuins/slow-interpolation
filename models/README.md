# models/

Local LoRA checkpoints and any other large model assets the pipeline needs.

The `loras/` subtree is **gitignored** (LoRA checkpoints are 200+ MB each, change per release, and live outside source control). The directory itself is preserved via `loras/.gitkeep`. Users (or release scripts) populate it.

## Expected layout

```
models/
  loras/
    Thomas_Cole_epoch_10.safetensors   ~218 MB, default for After Cole renders
    Thomas_Cole_epoch_1.safetensors    ~218 MB, light style fallback
    <renoir-flowers>.safetensors        when trained, for objkt labs release
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
