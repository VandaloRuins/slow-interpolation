# Train an SDXL LoRA on Modal (for agents)

You are an AI agent training a domain LoRA for the user. This is the canonical Modal training protocol; it shipped 2026-05-18 after the Renoir cold-run validated all 5 kickoff exit criteria. Use this for every new dataset coming out of the dataset-mosaic protocol ([`dataset-curation.md`](dataset-curation.md) Phase 5 hand-off).

The CivitAI path is now optional / archival. Modal is the canonical training path for this repo.

## When you do this

Trigger any of:

- Phase 5 of the dataset-curation protocol just produced a fresh `datasets/<name>/<name>-civitai.zip`.
- The user names a new LoRA family ("let's train a Soutine LoRA", "let's try Vermeer").
- An existing family needs a re-train (dataset re-curated, hyperparameter A/B, new trigger).

What you do NOT do here: dataset curation. That is its own protocol with its own user-in-the-loop steps. If the ZIP does not exist yet, go to [`dataset-curation.md`](dataset-curation.md) first.

## The five steps

| Step | What you do | User involvement |
|---|---|---|
| 1. Confirm prerequisites | Verify Modal CLI auth + Renoir cold-run done (proof-of-mechanics) | None |
| 2. Upload dataset to Modal | `modal run -m cloud.upload_dataset --src <zip>` | None |
| 3. Author the training YAML | Copy `_template.yaml`, fill 4 TODO fields | Confirms trigger word + family name |
| 4. Author the validation YAML | Copy renoir.yaml or soutine.yaml as exemplar, build 6+5 prompts | Approves the 11 prompts before render-spend |
| 5. Run training + validation | `train_entrypoint`, then `validate_lora`, then compare | Visual review of contact sheet |

Walk these in order. Each step has a hard gate.

## Step 1: Prerequisites

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
modal app list 2>&1 | Select-Object -First 5
```

If the list is empty or errors with auth issues: `modal token new` (opens a browser, OAuth flow). The user does this once per machine; you do not have credentials.

If the renderer has never been smoke-tested on this machine: run `modal run -m cloud.smoke` first. It costs ~$0.02 and rules out auth, image-build, and volume-mount regressions before you spend ~$1.50 on the real training. Defer to [`../modal.md`](../modal.md) for renderer-side prerequisites.

If you have not validated the Modal trainer specifically on this codebase before: confirm `cloud/train_app.py` SHA is pinned (not `"main"`). The constant lives at the top of [`../../cloud/train_app.py`](../../cloud/train_app.py); should look like `SD_SCRIPTS_COMMIT = "502cc3fab2aa"` (current pin, captured during the Renoir G3 cold-run).

## Step 2: Upload the dataset ZIP

The dataset ZIP is the Phase-5 hand-off from the dataset-curation protocol. Always at `datasets/<name>/<name>-civitai.zip`.

```powershell
modal run -m cloud.upload_dataset --src datasets/<name>/<name>-civitai.zip
```

Idempotent (re-uploading overwrites; the volume keys by filename). The ZIP itself is referenced by basename in the training YAML's `dataset.zip` field.

## Step 3: Author the training YAML

```powershell
cp examples/configs/training/_template.yaml examples/configs/training/<name>.yaml
```

The template carries the 4 TODO fields. You fill them; nothing else changes unless the user explicitly asks for a hyperparameter A/B.

| TODO | What goes there | Source of truth |
|---|---|---|
| `dataset.zip` | Basename of the uploaded ZIP, e.g. `vermeer-interiors-civitai.zip` | Step 2 output |
| `dataset.trigger` | 3 to 4-letter trigger token, e.g. `vmr`, `stn`, `rfl` | Dataset's `_civitai_staging/*.txt` captions start with this token; confirm with user before committing |
| `validation.prompts` | 3 short prompts that exercise the target subject, each starting with the trigger | Subjects from the dataset's caption corpus; pick ones that test the LoRA at-train-time |
| `publish.checkpoint_template` | `"<PascalCase>_<Subject>_epoch_{epoch}.safetensors"` | Must match the validation YAML's `lora_filename_template` exactly |

Worked examples to crib from:
- [`../../examples/configs/training/renoir_flowers.yaml`](../../examples/configs/training/renoir_flowers.yaml): 105 images, trigger `rfl`, template `"Renoir_Flowers_epoch_{epoch}.safetensors"`. **Floral preset.**
- [`../../examples/configs/training/soutine_figures_v2.yaml`](../../examples/configs/training/soutine_figures_v2.yaml): 80 images, trigger `stn`, template `"Soutine_Figures_epoch_{epoch}.safetensors"`. **Expressionist preset.**
- [`../../examples/configs/training/soutine_figures.yaml`](../../examples/configs/training/soutine_figures.yaml): the v1 attempt at Soutine with the floral preset. **Failed**; kept as documentation of the wrong-preset failure mode.

### Pick the preset BEFORE you copy the template

The four hyperparameters `network_rank`, `network_alpha`, `unet_lr`, `repeats` are **preset-dependent**. There are two validated presets; pick before authoring the YAML:

| Preset | Use when the target style is... | `network_rank` | `network_alpha` | `unet_lr` | `repeats` | Wall (80-110 imgs, L40S) | Cost |
|---|---|---|---|---|---|---|---|
| **Floral** (default) | atmospheric / low-frequency / soft transitions / broken color (Renoir, Monet, tonalism, Hudson River School, impressionist landscape) | 16 | 8 | 3.0e-5 | 6 | 24-47 min | $0.80-1.50 |
| **Expressionist** | gestural / high-frequency / mark-making / distortion (Soutine, Bacon, Schiele, Kokoschka, Van Gogh, Munch) | 32 | 32 | 5.0e-4 | 2 | 10-15 min | $0.30-0.50 |

**Decision tree**:
1. Open 3-5 representative images from the dataset.
2. If the style markers are **soft transitions, broken color, atmospheric light, blended brushwork**: floral preset.
3. If the style markers are **dragging brush, twisted silhouettes, charged surface, deliberate distortion, heavy impasto, gestural marks**: expressionist preset.
4. If mixed (late Monet water lilies, Cezanne) or unsure: try floral first (cheaper to ship, smaller files). If the cold-run validation grid shows the style did not transfer at epoch 10 (target style markers missing even at scale 0.85), re-train with expressionist preset and keep the floral run archived as the negative-result baseline.

**Full evidence for the preset choice**: [`../findings/expressionist-style-preset.md`](../findings/expressionist-style-preset.md). Read it once if you've never selected a preset before; it has the per-prompt Soutine v1 (floral preset) vs v2 (expressionist preset) verdict that established the table.

**Cost of getting the preset wrong**: ~$0.50-1.50 + ~25 min wasted, plus the time to inspect the failed renders and notice the style did not transfer. Mitigation: skim the dataset preview before authoring the YAML and pick deliberately.

**Do NOT change anything else**: optimizer, lr_scheduler, lr_scheduler_num_cycles, batch_size, gradient_accumulation, epochs, save_every_n_epochs, mixed_precision, min_snr_gamma, gradient_checkpointing, caption_shuffle, caption_tag_dropout, resolution, bucket settings, network_train_unet_only. These are the cold-run-validated constants across both presets. If the user wants an A/B beyond preset selection, document the deviation as a separate config (`<family>_v2.yaml`) and post a workstream-progress entry with the rationale + verdict.

## Step 4: Author the validation YAML

Validation is two-layer:

1. **Trainer-inline** (cheap, runs every train job): 3 prompts × 3 epochs, 1024×1024, 30-step standard SDXL. Lives in the training YAML's `validation` block. Cost: ~30s on top of train wall.
2. **Production-grade grid** (cloud/validate_lora.py): 11 prompts × 3 epochs, 1216×832 (or 832×1216 portrait), Lightning 4-step at the same render config the slow-interpolation pipeline uses. Cost: ~25s per epoch (~$0.01 each).

The production grid lives at `examples/configs/validation/<family>.yaml` and is driven by [`../../cloud/validate_lora.py`](../../cloud/validate_lora.py). Author it after the trainer YAML.

```powershell
cp examples/configs/validation/renoir.yaml examples/configs/validation/<family>.yaml
```

Fields to edit:

| Field | What to do |
|---|---|
| `family` | Kebab-case family name. Used as the outputs directory on the volume (`outputs/validation/<family>/epoch-<N>/`). |
| `lora_filename_template` | Must match the training YAML's `publish.checkpoint_template` EXACTLY. The validator looks up the LoRA on the slow-interp-loras volume by this name. |
| `render.width / height` | Aspect ratio the production pipeline uses. Landscape (1216×832) for floral / landscape LoRAs, portrait (832×1216) for figure LoRAs. |
| `negative_prompt` | Keep short. Aggressive negatives fight stylistic LoRAs (especially expressionist styles where "distortion" is the goal). |
| `tracks` | TWO tracks: `name=off` or `field` for off-distribution probe (the actual production target, subjects the LoRA didn't train on), `name=hold` or `vase` for in-distribution hold-outs (subjects the LoRA did train on, the "did it learn" check). 6 prompts in off + 5 in hold is the conventional shape; deviate only with reason. |

Each prompt has `slug` (filename-safe) and `text` (full prompt, starting with the trigger).

**Before render-spend**: skim the 11 prompts with the user. Cost is trivial but a wrong prompt set means re-rendering, which wastes their attention more than money.

## Step 5: Run training + validation + compare

### 5a. Train

```powershell
modal run -m cloud.train_entrypoint --config examples/configs/training/<family>.yaml
```

Expected wall: ~45 min on L40S for 80 to 110 images. Expected cost: $1.20 to $1.80. The CLI prints the run-id and the manifest path at the end:

```
[train] run_id:         <family>_<utc-ts>_<sha>
[train] estimated cost: $X.XX
[train] checkpoints:    10
[train] manifest:       runs/<run-id>/manifest.json
```

If cost lands over $2.50, something is off (slower step time than expected, retries, big-image dataset). Check the run log via `modal app logs <app-id>` before assuming anything.

### 5b. Download trainer-inline contact sheet (sanity check)

```powershell
modal volume get slow-interp-train-artifacts runs/<run-id> ./train-artifacts/runs/
```

Open `train-artifacts/runs/<run-id>/validation.png`. This is the 3 × 3 trainer-inline grid (3 epochs × 3 prompts at 1024×1024). Quick read: does the LoRA recognise the trigger by epoch 1, do the prompts look like the target style by epoch 5, do they hold at epoch 10? If yes, proceed; if no, suspect dataset / trigger / config and surface to the user.

### 5c. Production-grade validation grid

```powershell
modal run -m cloud.validate_lora --config examples/configs/validation/<family>.yaml --epoch 1
modal run -m cloud.validate_lora --config examples/configs/validation/<family>.yaml --epoch 5
modal run -m cloud.validate_lora --config examples/configs/validation/<family>.yaml --epoch 10
```

Three short runs (~25s + ~$0.01 each). Each renders all 11 prompts to `outputs/validation/<family>/epoch-<N>/` on the outputs volume.

Download:

```powershell
modal volume get slow-interp-outputs validation/<family> ./outputs/validation/
```

### 5d. Build the comparison viewer (optional but recommended)

If a CivitAI baseline exists for the same family, mirror the Renoir `outputs/validation/comparison.html` structure:

1. Copy `outputs/validation/comparison.html` to `outputs/validation/comparison_<family>.html`.
2. Edit the PROMPTS array to match the new family's prompt slugs + titles.
3. Edit the image paths to load from `<family>/epoch-N/<slug>.png` and `archive/<civitai-baseline-dir>/epoch-N/<slug>.png` (if a CivitAI baseline exists).
4. Open in browser. Lightbox + track filter inherit for free.

For families with no CivitAI baseline (every new family from now on), skip the comparison; just write a Markdown report in `docs/planning/workstreams/<family>-lora/validation-grid.md` with thumbnails and a headline verdict, then ask the user for visual approval.

## Exit criteria (when you say "done")

Mirror the Renoir cold-run table:

| # | Criterion | How to check |
|---|---|---|
| 1 | End-to-end no crashes | manifest.json exists, `lora_checkpoints` has 10 entries |
| 2 | In-distribution hold-outs (5) read as the target style at epoch 10 at scale 0.85 | Visual; ≥ 4/5 |
| 3 | Off-distribution prompts (6) carry the style at epoch 1 (or whichever epoch the user picks for fields) | Visual; ≥ 3/6 |
| 4 | Cost ≤ $4 | Manifest `estimated_cost_usd` |
| 5 | LoRAs load via `cloud/validate_lora.py` unchanged | You just used it in 5c, so this is automatic if the publish-block template matches the validation-config template |

Post the verdict + the 5-row table in a new entry of `docs/planning/workstreams/<family>-lora/progress.md`. Cross-link from the master log [`../planning/progress.md`](../planning/progress.md).

## Production swap (if the trained LoRA replaces an existing baseline)

If the trained LoRA replaces a previous version (CivitAI baseline, earlier Modal run, etc.), follow the Renoir pattern:

1. Move the previous local files into `models/loras/archive/<provenance>-<date>/` (preserve, don't delete).
2. Write an `archive/<dir>/README.md` documenting: provenance, hyperparameters, validation grid link, why archived, how to restore.
3. Download the new Modal-trained checkpoints to replace the local production copies:
   ```powershell
   modal volume get slow-interp-loras <Family>_<Subject>_epoch_1.safetensors models/loras/
   modal volume get slow-interp-loras <Family>_<Subject>_epoch_5.safetensors models/loras/
   modal volume get slow-interp-loras <Family>_<Subject>_epoch_10.safetensors models/loras/
   ```
4. The Modal volume copy is already canonical (publish block did this at train time). The renderer reads from the volume; no further action needed for cloud rendering. The local copies are for personal reference, dev work, and offline rendering.

## Troubleshooting

| Symptom | First check |
|---|---|
| Image build fails on a backslash-looking path inside a `RUN` step | You are on Windows and a `pathlib.Path` leaked into an f-string. Use `.as_posix()`. See [`../findings/modal-sdk-quirks.md`](../findings/modal-sdk-quirks.md) #10. |
| `pip install -r .../requirements.txt` fails with "does not appear to be a Python project" | sd-scripts's requirements.txt last line is `.` (self-install). Replace the requirements-file install with explicit `.pip_install(...)` of the deps. Already done in `cloud/train_app.py`; this should only resurface if you point at a different sd-scripts fork. |
| sd-scripts logs "0 image files" then errors "train_data_dir must be the parent..." | The dataset TOML's `image_dir` is pointing at the parent of the `<N>_<concept>` folder. Must point at the leaf. Already fixed in `cloud/train_app.py`. |
| Validation skips the final epoch | `_parse_checkpoint_epoch` returned None for the un-suffixed final checkpoint. Already fixed; if it resurfaces, check that `total_epochs` is being passed into `_run_validation`. |
| Trainer-inline contact sheet looks photographic, not stylised | Trigger token missing or wrong. Open a couple of captions in the unpacked dataset on Modal (`modal volume get slow-interp-datasets <name>-civitai.zip /tmp/` then inspect); first comma-separated token in every caption must equal `dataset.trigger`. |
| Production grid via `cloud/validate_lora.py` errors "LoRA not on volume" | The publish block did not run (training YAML missing `publish.checkpoint_template`) or the template does not match the validation YAML's `lora_filename_template`. Check both; re-train if you set publish wrong (cheap workaround: download checkpoint from `runs/<run-id>/` and re-upload at the convention name with `cloud/upload_weights.py`). |
| Visual quality at epoch 10 is worse than CivitAI baseline | Cold-run regressed somehow. Read manifest's `trainer_version` SHA and compare to the pinned one in `cloud/train_app.py`. Read `sdxl_base_revision`. If both match Renoir's, suspect dataset (captions, image quality, mis-labelled trigger). |
