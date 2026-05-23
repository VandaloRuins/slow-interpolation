# LoRA validation protocol (for agents)

You are an AI agent running a LoRA validation pass on behalf of a user. A LoRA training run just produced three or more epoch checkpoints; the user wants to know which epoch reads strongest, where it over-fits, and which to ship. This page is your operating manual.

The output of the protocol is: PNGs under `outputs/validation/<family>/epoch-<N>/`, a `_manifest.json` per epoch, and (optionally) a side-by-side comparison HTML the user opens in a browser to make the visual call. A short verdict written into the workstream's `progress.md` closes the loop.

**This is the only documented LoRA validation path in this repo.** If you are about to render epoch comparisons by hand, by writing a one-off script, or by re-using `cloud/app.py`'s production renderer, stop and use [`cloud/validate_lora.py`](../../cloud/validate_lora.py) instead. It is family-agnostic: pass a config YAML, it does the rest.

## When to run this

| Situation | Run validation? |
|---|---|
| Just trained a new LoRA family (Renoir, Soutine, future) | **Yes.** Before any production render. |
| Second engine bake-off (CivitAI vs Modal on the same dataset) | **Yes.** Two passes, one per engine; assemble head-to-head HTML. |
| Cross-checkpoint comparison within a single family | **Yes.** Default to epoch 1, 5, 10. |
| Per-piece LoRA-scale tuning during render lock | No. That happens inside the production config, not via this protocol. |
| Single-config quick sanity render | No. Use `cloud.smoke` or a one-off `modal run -m cloud.app` instead. |

## Inputs the user owes you

Ask the user for these before dispatch. Do NOT guess:

- **Family name** in kebab-case (e.g. `renoir-flowers`, `soutine-figures`). Becomes the `family:` field in the YAML and the output folder name.
- **LoRA filename pattern.** Format string with `{epoch}` placeholder (e.g. `Renoir_Flowers_epoch_{epoch}.safetensors`). The renderer substitutes the epoch number to find the checkpoint on the Modal `slow-interp-loras` volume.
- **Trigger word.** 3 to 4 lowercase letters (e.g. `rfl`, `stn`). Lives inside every prompt's text.
- **Epoch list.** Default `[1, 5, 10]`. Skip 5 only if the user explicitly wants a 2-checkpoint compare.
- **Resolution and orientation.** Default `1216 x 832` landscape for outdoor / field LoRAs, `832 x 1216` portrait for figure LoRAs. The native SDXL 3:2 buckets keep border artifacts down per [`../findings/border-crop.md`](../findings/border-crop.md).
- **Subject families to probe.** Two tracks is the canonical shape: Track 1 off-distribution (does the style carry beyond the training subjects), Track 2 in-distribution hold-outs (did the LoRA learn the idiom at all). 5 to 6 prompts per track is enough.

If the LoRA was trained on more than one subject family (Soutine: figures + landscapes + carcasses + still lifes), add an optional **cross-family check** as a third track or a sidecar render set. Without it you cannot tell whether the LoRA collapsed to one family despite a heterogeneous training pool.

## The five phases

| Phase | Who does it |
|---|---|
| 0. Author the validation YAML | You. Copy `examples/configs/validation/renoir.yaml` or `soutine.yaml`, adapt. |
| 1. Confirm hardware routing | You. Run the routing protocol; this is a Modal job in almost all cases. |
| 2. Dispatch one Modal run per epoch | You. Background-execute, surface dashboard URL and ETA. |
| 3. Download artifacts + build viewer | You. Pull the PNGs and manifest from the Modal volume; assemble or refresh the comparison HTML. |
| 4. Hand back to the user with what-to-look-for | You. Open the HTML, walk them through the five-signal checklist below. |
| 5. Record the verdict | You. Write the headline read + per-subject recommendation into the workstream's `progress.md` and the `<family>-validation-grid.md` if it exists. |

## Phase 0: Author the validation YAML

Templates live at [`examples/configs/validation/`](../../examples/configs/validation/). Two canonical examples:

- [`renoir.yaml`](../../examples/configs/validation/renoir.yaml): landscape 1216 x 832, field + vase tracks, flower-themed negative prompt.
- [`soutine.yaml`](../../examples/configs/validation/soutine.yaml): portrait 832 x 1216, off + hold-out tracks, deliberately short negative prompt (Soutine's style IS distortion; suppressing it would fight the LoRA).

Copy whichever matches your orientation. Adapt: `family`, `lora_filename_template`, every prompt's text, `negative_prompt`, resolution. Keep `seed: 42` constant across the family so future re-renders compare apples-to-apples. Keep `lora_scale: 0.85` as the default; bump only when the user has a specific reason.

Strong opinion on negative prompts: keep them short and family-aware. Long negatives suppress the LoRA's signal. Renoir negatives reject still-life and frame artifacts; Soutine negatives reject photograph and 3D-render but **not** "deformed". Match the LoRA's idiom.

Prompts: include the trigger word at the start, then the subject, then 3 to 5 style anchors lifted from the training captions (e.g., "twisted silhouette, dragging brush, charged surface, oil painting, expressionist" for Soutine). Each prompt is one line; the renderer joins YAML multi-line strings.

When the YAML is ready, validate it parses: `python -c "import yaml; yaml.safe_load(open('examples/configs/validation/<name>.yaml'))"`.

## Phase 1: Hardware routing

LoRA validation at 12 prompts on SDXL Lightning 4-step lands at ~20 seconds wall + ~$0.015 USD per epoch on Modal L40S. Three epochs is one cup of coffee and one nickel.

Run [`hardware-routing.md`](hardware-routing.md). For validation specifically:

- **Modal is the default.** The LoRA already lives on the Modal `slow-interp-loras` volume after training; the data is co-located with the renderer. Pulling it down to render locally is wasteful.
- **Local is only sensible** when (a) the user has a 24 GB+ VRAM card free, (b) the LoRA already exists locally under `models/loras/`, and (c) they specifically want to iterate the validation YAML before committing to the Modal trio.
- **A100-80GB tier is overkill** for validation. Use L40S.

## Phase 2: Dispatch

One `modal run` per epoch. Background-execute, redirect stdout to `outputs/_harness_logs/`, surface the dashboard URL per [`../findings/monitoring-long-cloud-jobs.md`](../findings/monitoring-long-cloud-jobs.md):

```
modal run -m cloud.validate_lora --config examples/configs/validation/<family>.yaml --epoch 1
modal run -m cloud.validate_lora --config examples/configs/validation/<family>.yaml --epoch 5
modal run -m cloud.validate_lora --config examples/configs/validation/<family>.yaml --epoch 10
```

These are independent jobs; if the user is in a hurry, dispatch all three in parallel using three background calls. Modal will queue or fan out depending on the workspace's container limit.

Each run writes to `/root/slow-interpolation/outputs/validation/<family>/epoch-<N>/` on the `slow-interp-outputs` volume, including a `_manifest.json` with the prompts, timings, seed, scale, and LoRA filename.

If a run fails with `FileNotFoundError: LoRA not on volume`, the LoRA never made it to Modal. Either: (a) it was trained on Modal but `outputs_volume.commit()` missed it (unlikely), (b) it was trained on CivitAI / locally and `cloud/upload_weights.py` was never run, (c) the `lora_filename_template` is wrong. Most often (b). Fix and re-dispatch.

## Phase 3: Download artifacts and build the viewer

After all three runs complete:

```
modal volume get slow-interp-outputs validation/<family>/ outputs/validation/
```

This pulls the full family tree (all three epochs). Browse one folder to confirm PNGs landed:

```
ls outputs/validation/<family>/epoch-10/
```

Twelve or so PNGs (one per prompt) plus `_manifest.json`. If the count is wrong, the manifest tells you which prompts errored.

### The comparison viewer

Two assets work together:

1. **Markdown grid** at `docs/planning/workstreams/<workstream>/validation-grid.md`. Three-column table per prompt (epoch 1, 5, 10), one "Read:" line below each. The Renoir [`workstreams/renoir-dataset/validation-grid.md`](../planning/workstreams/renoir-dataset/validation-grid.md) is the canonical shape. **Path gotcha:** image refs must resolve from the markdown file's location. The actual renderer writes `outputs/validation/<family>/epoch-<N>/<slug>.png`. Do not invent flatter paths like `outputs/validation/<family>-epoch-<N>/`; that schema does not exist.

2. **Standalone HTML at `outputs/validation/comparison_<family>.html`.** Dark-theme, side-by-side, optional filter chips per track. Pattern: copy `outputs/validation/comparison_soutine.html` and rename. The Soutine HTML supports two engines (CivitAI + Modal-v2) head-to-head; if you only have one engine, hide one column. The HTML reads PNGs by relative path so it works without a server (`start outputs/validation/comparison_<family>.html` on Windows, `open` on macOS).

For a second-engine bake-off, run the renderer twice with the same YAML but a different `lora_filename_template` (e.g., `Soutine_Figures_civitai_epoch_{epoch}.safetensors` vs the Modal-trained pattern) and write outputs under `<family>-civitai/` and `<family>-modal-v2/`. Then assemble the head-to-head HTML.

## Phase 4: Walk the user through what to look for

Open the comparison HTML in their browser. Hand them this checklist, in order:

1. **Track 2 (in-distribution) first.** If the hold-out subjects do not read as the trained style, the LoRA failed and Track 1 is moot. For style LoRAs look for the idiom's named markers (Soutine: twisted silhouette, dragging brush, charged surface; Renoir: broken colour, atmospheric haze, loose painterly handling).
2. **Epoch curve.** Expect epoch 1 = atmosphere preserved, weak style; epoch 5 = balanced; epoch 10 = strong but at risk of over-fit. Identify which epoch best matches the user's intended render context.
3. **Over-fit signature.** Look for a recurring artifact across multiple prompts at the strongest epoch: a baked-in ground colour, a frame border, a signature in the corner (auction-catalogue cast, see Renoir epoch 10), a recurring composition habit. If present, demote that epoch and ship the one below.
4. **Generalisation (Track 1).** Do off-distribution prompts carry the style or revert to generic SDXL? If they revert, the LoRA needs a higher scale at compositing time, or the strong epoch is the better pick.
5. **Idiom-as-execution vs idiom-as-keyword.** The prompts include style keywords. Check whether the LoRA *executes* them (real distortion, real palette knife) or just included them in the caption while the figure comes out clean. The latter means under-trained; either re-train or accept the lighter cast.

For the Renoir family, an additional signal: **outdoor field vs vase still life can disagree.** The Renoir validation showed epoch 1 wins on fields, epoch 10 wins on vases. Multi-subject LoRAs may need a per-subject epoch map, not a single canonical pick. The Soutine LoRA may show similar splits across its four families (figures vs landscapes vs carcasses vs still lifes).

Wait for the user's call. Do not pick for them; you can recommend, they decide.

## Phase 5: Record the verdict

After the user decides, write the verdict in three places:

1. **The workstream's `progress.md`** as a dated decisions-log entry. Include: which epoch wins for which subject, any over-fit signature observed, recommended `lora_scale` if different from 0.85, and any per-subject epoch map.
2. **The `<family>-validation-grid.md`** "Headline read" section, with concrete one-line "Read:" entries per prompt.
3. **Coordination request** in `progress.md` for the parent chat to update `docs/planning/progress.md` decisions log if the verdict is repo-wide (e.g., "Modal beats CivitAI on Soutine"). Do not edit `docs/planning/progress.md` yourself; that file is parent-chat-owned.

If the verdict changes the production config defaults (e.g., a `examples/configs/<family>/*.yaml` is now pointing at the wrong epoch), file a coordination request to update those YAMLs. Same rule: do not edit them yourself if they live outside your workstream's write zone.

## Failure modes

| Symptom | Likely cause | Action |
|---|---|---|
| `FileNotFoundError: LoRA not on volume` | LoRA never uploaded to Modal | Run `python cloud/upload_weights.py models/loras/<file>` and re-dispatch. |
| `IndexError` from `pipe.load_lora_weights` | Kohya text-encoder key mismatch | None needed. The renderer's UNet-only fallback catches this. Verify the manifest reports successful renders. |
| All renders look generic SDXL Lightning | Trigger word missing from prompts, or `lora_scale` too low | Re-read your YAML. Trigger word must lead every prompt. Bump scale to 1.0 if needed. |
| Epoch 10 carries a corner signature or frame | Over-fit on training-data cast (auction scans, framed reproductions) | Document the cast in the validation-grid markdown. Recommend epoch 5 or below for clean renders. Flag the training set for re-curation if severe. |
| All epochs identical | LoRA file is corrupt or the same checkpoint was copied to all three filenames | Check file sizes and SHA on disk under `models/loras/`. Re-run training if needed. |
| Renders take >40 s each on L40S | TAESD VAE not loaded; pipeline fell back to the full SDXL VAE | Check the validation YAML; `taesd_vae: madebyollin/taesdxl` should be set. |
| Markdown grid image refs all broken | Path schema mismatch | Image files live at `outputs/validation/<family>/epoch-<N>/<slug>.png`, NOT `outputs/validation/<family>-epoch-<N>/`. Rewrite refs. |

## Cross-links

- [`train-lora-on-modal.md`](train-lora-on-modal.md) is the upstream protocol that produces the checkpoints you validate.
- [`hardware-routing.md`](hardware-routing.md) decides where validation runs.
- [`../findings/monitoring-long-cloud-jobs.md`](../findings/monitoring-long-cloud-jobs.md) is the Modal dispatch operating playbook.
- [`../findings/border-crop.md`](../findings/border-crop.md) is the reason validation defaults to native SDXL training-bucket resolutions.
- [`../findings/kohya-vs-ai-toolkit-renoir.md`](../findings/kohya-vs-ai-toolkit-renoir.md) is the worked example of a two-engine bake-off using this validation protocol.
- The pending [`../findings/lora-pipeline.md`](../findings/lora-pipeline.md) (Job 1 in flight) will reference this page as the canonical post-training step.
