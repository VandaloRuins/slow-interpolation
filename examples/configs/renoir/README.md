# Renoir LoRA config templates

Placeholder configs for the Renoir floral subjects. Schema is
production-ready; the LoRA file (`models/loras/Renoir_Flowers_epoch_10.safetensors`)
is **not yet checked in** because training is still running in a separate chat.

When Luca drops the trained checkpoints under `models/loras/`:

1. If the filename differs, update each YAML's `style.lora_path`.
2. Run one config: `python -m slow_interpolation.run examples/configs/renoir/roses_vase_60s.yaml`.
3. Inspect the output for border artifacts. If the bouquet attracts a
   decorative frame (the failure mode flagged in
   [docs/findings/lora-training.md](../../../docs/findings/lora-training.md)
   section 7), set `rife.edge_crop: 8` for the affected configs and note the
   regression in `docs/planning/progress.md`.

Trigger word: `rfl`. Caption template:
`rfl, [subject], [composition], [palette / light], [brushwork / surface], oil painting, impressionist`.

Defaults pinned here:

- `lora_scale: 0.80` (working median; range 0.75 to 0.85 per the playbook).
- `resolution: 1344 x 768` (SDXL 16:9 training bucket). Transpose for portrait.
- `edge_crop: 0` (post border-crop probe, see [docs/findings/border-crop.md](../../../docs/findings/border-crop.md)).
- Negative prompt: `frame, vignette, panel, ornament, photograph, modern, sharp, photoreal`.

Four subject templates are scaffolded; spawn more from the prompt vocabulary
in [docs/findings/lora-training.md](../../../docs/findings/lora-training.md)
section 8 (subjects + compositions + palettes).
