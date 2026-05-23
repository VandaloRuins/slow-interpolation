# Renoir flowers LoRA, training playbook

> **CANONICAL TRAINING PATH UPDATED 2026-05-18.** Modal is now the canonical training path; see [docs/manual/train-lora-on-modal.md](../manual/train-lora-on-modal.md) for the agent-facing protocol. This document remains as the **Renoir-specific worked example**: trigger word, captioning template, dataset assumptions, expected outcomes, validation grid, observed failure modes. The CivitAI commands below are archival; use the Modal protocol unless you have a specific reason to deviate. The generic, subject-agnostic recipe is being authored at `docs/findings/lora-pipeline.md` and will reference this file as the worked example.

Push-button instructions for training the Renoir floral SDXL LoRA from the dataset and captions delivered under [datasets/renoir-flowers/](../../datasets/renoir-flowers/). Mirrors the Thomas Cole LoRA pattern documented at [legacy/after-cole/LORA-USAGE.md](../../legacy/after-cole/LORA-USAGE.md). This document is the recipe, not the executor.

Reference for the dataset itself: [docs/renoir-dataset-progress.md](../planning/workstreams/renoir-dataset/progress.md).
Reference for the inference pipeline that consumes the trained LoRA: [docs/pipeline.md](../pipeline.md) and [src/slow_interpolation/keyframes.py](../../src/slow_interpolation/keyframes.py).
**For deeper theory and hands-on tools beyond CivitAI** (kohya_ss, OneTrainer, Ostris AI Toolkit, hyperparameter rationale by objective, validation protocol, failure-mode diagnostics): [docs/findings/lora-training-deep-dive.md](lora-training-deep-dive.md).

> **Hand-off note:** when training completes, export a generic LoRA pipeline recipe to [docs/findings/lora-pipeline.md](lora-pipeline.md) so future domain LoRAs (next Renoir / Cézanne / other) can be trained without re-deriving the recipe. This Renoir-specific playbook stays as the worked example. See [docs/progress.md](../progress.md) "LoRA pipeline export plan" for the full hand-off spec.

## 1. Trigger word and tagging convention

| Field | Value |
|---|---|
| Trigger | `rfl` |
| Style markers in every caption | `oil painting, impressionist` |
| Caption template | `rfl, [subject], [composition], [palette / light], [brushwork / surface], oil painting, impressionist` |
| Word count per caption | 33 to 39 words (within the 30 to 60 brief window) |

The trigger `rfl` is short, lowercase, and orthogonal to any real word the SDXL text encoder will treat as a noun. It parallels `tcole` (Thomas Cole) and `cds` (Casa del Suono) at the slow-interpolation pipeline's interface.

## 2. Dataset packaging for CivitAI

CivitAI's training UI accepts a single ZIP whose contents are image / caption pairs sharing a basename. Build that ZIP from the delivered dataset before uploading:

```bash
# from repo root
cd datasets/renoir-flowers
python package_for_civitai.py            # writes renoir-flowers-civitai.zip
```

If [package_for_civitai.py](../../datasets/renoir-flowers/package_for_civitai.py) is not yet present, the equivalent one-shot:

```bash
cd datasets/renoir-flowers
mkdir -p _civitai_staging
cp raw/*.jpg _civitai_staging/
python -c "
import csv, pathlib
out = pathlib.Path('_civitai_staging')
with open('captions.txt', encoding='utf-8') as f:
    for line in f:
        name, cap = line.rstrip('\n').split('\t', 1)
        (out / (pathlib.Path(name).stem + '.txt')).write_text(cap, encoding='utf-8')
"
cd _civitai_staging && zip -r ../renoir-flowers-civitai.zip . && cd ..
```

Result: `renoir-flowers-civitai.zip` with 102 .jpg / 102 .txt pairs, total around 1 to 1.5 GB.

### Image preprocessing — do NOT pre-resize

CivitAI's training resizes images to the bucket resolution automatically (1024 px short side for SDXL). Pre-resizing strips information you paid for at sourcing time. The only pre-processing worth doing:

- Confirm every image is RGB (the sourcing pipeline already saves JPEG q=95 RGB).
- Confirm no image is below 1024 px short side; if any is (the dataset has 9 entries between 776 and 1024 px), expect CivitAI to bucket those into a smaller bucket. Optional: re-source those 9 entries from a higher-res scan, or accept the bucket mix.

### Validation hold-out (5 images)

Pull these 5 images out of the training set and keep them as a visual yardstick. Train without them, then at every checkpoint render the same five prompts on the LoRA and grade subjectively. They cover the full subject distribution and one off-distribution case:

| Filename | Subject | Why this image |
|---|---|---|
| `pierre-auguste-renoir-roses-in-a-vase-1941-14-cleveland-museum-of-art.jpg` | canonical roses in a vase | Cleveland Museum scan, the single most "Renoir rose bouquet" image in the set. If the LoRA cannot reproduce this, it has not learned the style. |
| `pierre-auguste-renoir-mixed-flowers-in-an-earthenware-pot-google-art-project.jpg` | mixed bouquet, earthenware pot | Google Art Project ultra-high-res. Tests whether the LoRA learns the loose-bouquet idiom or only the cut-flower-in-a-vase one. |
| `pierre-auguste-renoir-anemones-an-mones-bf1167-barnes-foundation.jpg` | anemones, single-flower-family | Barnes Foundation scan. Tests subject specificity. Anemones look nothing like roses; the LoRA should switch petal shape and palette. |
| `pierre-auguste-renoir-chrysanthemums-1933-1173-art-institute-of-chicago.jpg` | chrysanthemums | AIC scan. The 5-image chrysanthemum subset is small enough that holding this out tests whether the LoRA can generalise on minimal evidence. |
| `pierre-auguste-renoir-geraniums-in-a-copper-basin-11521194565.jpg` | geraniums in a pot | The only "potted plant" composition in the set. Held out to verify that the LoRA does not catastrophically misclassify it as a cut-flower bouquet at inference time. |

Run the move and the validation captions through:

```bash
cd datasets/renoir-flowers
mkdir -p validation
for f in \
  pierre-auguste-renoir-roses-in-a-vase-1941-14-cleveland-museum-of-art.jpg \
  pierre-auguste-renoir-mixed-flowers-in-an-earthenware-pot-google-art-project.jpg \
  pierre-auguste-renoir-anemones-an-mones-bf1167-barnes-foundation.jpg \
  pierre-auguste-renoir-chrysanthemums-1933-1173-art-institute-of-chicago.jpg \
  pierre-auguste-renoir-geraniums-in-a-copper-basin-11521194565.jpg ; do
    mv "_civitai_staging/$f" "validation/$f"
    mv "_civitai_staging/${f%.jpg}.txt" "validation/${f%.jpg}.txt"
done
# Re-zip with 97 image/caption pairs:
cd _civitai_staging && zip -r ../renoir-flowers-civitai.zip . && cd ..
```

Training set after the hold-out: 97 image / caption pairs.

## 3. CivitAI training settings (recommended starting points)

Mirror the Thomas Cole run, with one modification (lower LR) because Renoir's surface is softer and more easily over-fit than Cole's dramatic chiaroscuro. Two checkpoints planned (light + strong), same as Cole.

| Parameter | Recommended | Rationale |
|---|---|---|
| Base model | **SDXL 1.0** | Same backbone the pipeline uses everywhere ([src/slow_interpolation/config.py](../../src/slow_interpolation/config.py) `model_path`). |
| Network rank (dim) | **16** | Style LoRAs do not need rank 64+. Rank 8 is too tight for Renoir's broken-colour variation; rank 16 is the sweet spot the Cole LoRA settled into. |
| Network alpha | **8** | Half of rank, the Kohya default that scales LR per parameter cleanly. |
| Learning rate (UNet) | **3e-5** | Lower than the Cole run (1e-4). Renoir's surface is fragile; high LR over-fits to the auction-catalogue colour cast in 24 hours. |
| Text-encoder LR | **0** (off) | The pipeline applies LoRA UNet-only at inference (see `keyframes.py` UNet-only fallback). Training the text encoder is wasted compute that the consumer cannot load anyway. |
| Optimizer | AdamW8bit | CivitAI default. Memory-friendly. |
| Train batch size | **2** | Effective batch via gradient accumulation 4 to 8 if CivitAI exposes it. Effective batch 8 is the proven Cole / Casa del Suono setting. |
| Image resolution | **1024 x 1024** with bucketing on | SDXL native. Bucketing handles the mixed aspect ratios in the dataset (portraits, squares, wide landscapes). |
| Repeats per image | **6** | 97 training images x 6 repeats = 582 steps per epoch. |
| Epochs | **10** | Same as Cole. Save every epoch. |
| Save format | safetensors | What the pipeline loads. |
| Mixed precision | bf16 | Stable on SDXL. |
| Min SNR gamma | 5.0 | Recommended for SDXL fine-tunes. |
| Gradient checkpointing | on | Reduces VRAM. |
| Caption shuffle | off | Captions are structured and ordered (subject first, suffix last). Shuffling would scramble that structure. |
| Caption tag dropout | 0 | Same reason. |

Training cost on CivitAI's standard SDXL training: 1 to 2 Buzz-credits per epoch typically. 10 epochs is comfortably inside a Buzz top-up.

## 4. Which checkpoints to keep

Save every epoch. Discard most. For the slow-interpolation pipeline we need exactly two, paralleling the Cole release:

| Checkpoint | When to use | Pipeline scale |
|---|---|---|
| `Renoir_Flowers_epoch_1.safetensors` | Light style — Renoir atmosphere on non-floral or partly-floral subjects (the Renoir LoRA running on landscape-with-flowers prompts, fresco-fragment prompts, anywhere we want Renoir colour without full pastiche) | `lora_scale: 0.40 to 0.60` |
| `Renoir_Flowers_epoch_10.safetensors` | Strong style — direct Renoir floral pastiche, the objkt labs release primary subjects | `lora_scale: 0.70 to 0.90` |

The intermediate epochs (2 to 9) are training byproducts. Keep them archived for diagnostic re-renders if epoch 10 over-cooks or epoch 1 under-cooks; otherwise unused at inference.

## 5. Expected outcomes per checkpoint

Mirror the Cole calibration in [legacy/after-cole/LORA-USAGE.md](../../legacy/after-cole/LORA-USAGE.md):

### Light (epoch 1, scale 0.4 to 0.6)
- Adds Renoir's palette family (warm pinks, blush whites, terracotta backgrounds) without forcing the subject into a vase.
- Loses identity on a portrait or a fresco fragment if pushed above 0.7.
- Good for "Renoir-tinged Casa del Suono" mash-up renders, if we ever want them.

### Strong (epoch 10, scale 0.7 to 0.9)
- Full pastiche of Renoir's floral idiom. Bouquet compositions, broken-colour petals, soft scumbled backgrounds.
- Likely over-applies the trigger at scale 1.0+; the bouquet eats the entire canvas regardless of the prompt's composition cue.
- Settle on 0.75 to 0.80 for the release renders. Stay below 0.85 unless a specific clip needs the bouquet to dominate.

If the Cole / Casa del Suono pattern holds, epoch 5 will be a hidden third option. Run it once if epoch 1 feels too restrained for a specific subject; otherwise ignore.

## 6. Subject-distance note (carrying over from the border-crop finding)

This is the most important caveat in the playbook, because the slow-interpolation pipeline regularly uses a LoRA on subjects the LoRA was not trained on. From [docs/findings/border-crop.md](border-crop.md) and the Casa del Suono lesson:

> **LoRA scale should be subject-distance-aware.**
>
> The Casa del Suono fresco LoRA at scale 0.35 had been calibrated on the fresco subject distribution it was trained on. The same scale on a nature closeup (frog pond, lillypads) lost most of the LoRA's character because the LoRA was steering the model toward fresco surface, and the model was already a long way from fresco surface when the LoRA's contribution started. Scale 0.35 was a starvation diet for off-distribution subjects.

Concrete prediction for the Renoir LoRA: at scale 0.40 to 0.60 on a floral subject (in distribution) you get a soft Renoir flavour. At those same scales on a non-floral subject (a landscape, a portrait, a still life of fruit only) you get nothing visible. To get the Renoir character on off-distribution subjects, scale UP, not down. Practical values:

- In-distribution (flower bouquet, vase of flowers, single bloom): start at 0.75, push toward 0.85 if the bouquet idiom is wanted; pull back to 0.55 if the prompt is composition-led and you only want the palette.
- Cross-domain (a Cole landscape with floral foreground, a Casa del Suono fresco with bouquet inset): start at 0.85, push to 1.0 if needed. Below 0.7 the LoRA disappears.

This is opposite to the intuitive direction. Keep it in the playbook so future-Luca does not "fix" a too-faint LoRA by lowering the scale and end up with nothing.

## 7. Border-artifact probe for the Renoir LoRA

[docs/findings/border-crop.md](border-crop.md) locked `EDGE_CROP=0` as the new default for SDXL-bucket renders, conditional on a per-LoRA re-probe. Renoir is the first LoRA after that decision. Re-run the border-test with the Renoir LoRA at strong scale before the release renders.

Test config:

```yaml
# examples/configs/border-test/renoir_vase_20s_nocrop.yaml
# (Phase 3 parent chat will create this; spec'd here.)
edge_crop: 0
lora:
  path: models/loras/Renoir_Flowers_epoch_10.safetensors
  scale: 0.80
subjects:
  A: { prompt: "rfl, a porcelain vase of roses on a table, centered still life, warm afternoon light, oil painting, impressionist" }
  B: { prompt: "rfl, a porcelain vase of roses on a table, soft natural daylight, deeper crimson palette, oil painting, impressionist" }
  C: { prompt: "rfl, a porcelain vase of roses on a table, cool studio light, blue-grey background, oil painting, impressionist" }
duration_seconds: 22.9
```

Probe success criterion: gradient-magnitude border-band metric stays below 1.5x interior across all keyframes (same yardstick as the border-crop finding). Floral subjects historically tempt SDXL to paint decorative frames around the bouquet; if it happens here, raise `edge_crop` to 8 for the Renoir release configs only and document the regression in `docs/progress.md`.

## 8. Inference notes for slow-interpolation

How the trained LoRA gets referenced from the port at [src/slow_interpolation/](../../src/slow_interpolation/).

### File placement

```
models/loras/
  Renoir_Flowers_epoch_1.safetensors
  Renoir_Flowers_epoch_10.safetensors
```

`models/loras/*` is gitignored (see [`.gitignore`](../../.gitignore)). Same convention as the existing Cole and Casa del Suono checkpoints.

### YAML config reference

The parent chat owns `examples/configs/renoir/*.yaml`. Spec for those configs:

```yaml
# examples/configs/renoir/roses_vase_60s.yaml
seed: null
output: outputs/renoir_roses_vase.mp4
model_path: stabilityai/stable-diffusion-xl-base-1.0
lora:
  path: models/loras/Renoir_Flowers_epoch_10.safetensors
  scale: 0.80           # see "Recommended LORA_SCALE values" below
edge_crop: 0            # default after border probe in section 7
resolution: [1344, 768] # SDXL 16:9 training bucket; transpose to [768, 1344] for portrait
subjects:
  A:
    prompt: "rfl, a porcelain vase of pink roses on a marble side table, centered still life, soft natural daylight, blush pinks and ivory against a slate-grey background, visible brushstrokes, oil painting, impressionist"
    negative: "frame, vignette, panel, ornament, photograph, modern, sharp, photoreal"
  B:
    prompt: "rfl, the same vase, blooms opening further, warm afternoon light, creamy whites and rose against a deep terracotta ground, layered impasto petals, oil painting, impressionist"
    negative: "frame, vignette, panel, ornament, photograph, modern, sharp, photoreal"
  C:
    prompt: "rfl, the same vase, petals at full bloom, cool studio light, blue-greys and lavenders with green leaves catching highlights, loose painterly handling, oil painting, impressionist"
    negative: "frame, vignette, panel, ornament, photograph, modern, sharp, photoreal"
# Standard segments A / B / C / A-return; full schedule in src/slow_interpolation/pipeline.py.
```

### Recommended `lora_scale` values

| Render intent | lora_scale | Notes |
|---|---|---|
| Pure Renoir release piece (bouquet of roses, vase of mixed flowers, anemones) | 0.75 to 0.85 | Default release range. 0.80 is the working median. |
| Slow drift across three rose-bouquet prompts (the objkt labs primary loop) | 0.75 | Lower end of the range; the prompt scaffolding does the heavy lifting, the LoRA holds palette. |
| Renoir on a Cole-style landscape (cross-stylesheet exploration) | 0.90 to 1.00 | See subject-distance note. The Renoir LoRA on a landscape is off-distribution and needs to be pushed up. |
| Renoir on a Casa del Suono fresco (cross-LoRA experiment) | 0.85 to 1.00 | Mix at your own risk. Untested combination. |
| Subtle Renoir-tinged palette overlay on non-floral subjects | 0.55 to 0.65 + epoch 1 checkpoint | Use the light checkpoint. |

### Prompt vocabulary

Subjects (use one as the noun-phrase root of each A/B/C prompt):

- `a porcelain vase of pink roses` / `of crimson roses` / `of white roses` / `of yellow roses`
- `a porcelain vase of mixed flowers` / `a tin pot of mixed flowers` / `an earthenware pot of mixed flowers`
- `a bouquet of mixed garden flowers laid on a table`
- `a bouquet of anemones in a small vase` / `a vase of anemones`
- `a bouquet of chrysanthemums and a Japanese fan` (Met Museum subject, training-data reference)
- `a vase of gladioli` / `a bouquet of dahlias`
- `a bouquet of tulips`
- `a spring bouquet of mixed garden flowers`
- `a planter of geraniums on a window ledge`
- `a single peony in close-up`

Compositions:

- `centered still life on a table`
- `bouquet laid across the frame, fabric or table cloth in the foreground`
- `close-cropped fragment, flowers filling the frame edge to edge`
- `potted plant on a window ledge`
- `frieze of blooms across the width of the canvas`

Palette / light:

- `warm afternoon light, creamy whites and pinks against a deep rose ground`
- `soft natural daylight, blush pinks and ivory against a slate-grey background`
- `cool studio light, blue-greys and lavenders with green leaves catching highlights`
- `rich impasto reds and crimsons against a tobacco-brown ground`
- `buttery cream and apricot tones, dappled garden light`
- `ochre and umber backdrop, pale petals catching the front-light`
- `warm interior light, brick reds, terracotta and gilt`
- `powdery blue and pale rose, light from a curtained window`
- `tawny golden ground, petals carrying full chromatic saturation`
- `cool morning light, white petals against a celadon green wall`
- `earthy plum and olive backdrop, blossoms holding a warmer key`
- `diffuse north-facing studio light, low contrast, pastel keying`

Surface / brushwork:

- `visible brushstrokes, layered impasto petals`
- `loose painterly handling, broken colour across the petals`
- `thick impasto highlights, soft scumbled background`
- `feathered brushwork on the leaves, wet-into-wet petal blending`
- `loose impressionist touch, vibrating edges between forms`

Style markers (always close with these, mirroring the training caption suffix):

- `oil painting, impressionist`

### Negative prompt boilerplate (recommended)

```
frame, vignette, ornament, panel, photoreal, photograph, modern, sharp, digital, vector, logo, text, watermark
```

Optional additions when you want the LoRA to behave specifically:

- `+ fruit, peaches, oranges, onions` — if the LoRA over-pulls from the still-life-with-fruit subset.
- `+ portrait, woman, figure, child` — defensive against the small set of fleurs-et-femme leak-throughs.

## 9. Sign-off checklist (before objkt labs release renders)

- [ ] CivitAI training completed, all 10 epoch checkpoints downloaded.
- [ ] Visual review of validation hold-out at epoch 1, 5, 10 (subjective grade by Luca).
- [ ] `Renoir_Flowers_epoch_1.safetensors` and `Renoir_Flowers_epoch_10.safetensors` copied to [models/loras/](../../models/loras/).
- [ ] Border-artifact probe run per section 7. Decision recorded on `edge_crop: 0` vs raising for Renoir.
- [ ] Parent chat ([docs/progress.md](../progress.md)) notified that the LoRA is ready, with the chosen default scale and any border-config caveats. After that, the parent chat writes `examples/configs/renoir/*.yaml` and renders.

## 10. Out of scope here

- The actual training run (Luca, on CivitAI).
- Writing the `examples/configs/renoir/*.yaml` (parent chat).
- A/B/C subject locking for the release (artist + curator, on the locking call).
- Caption refinements via VLM (deferred; see Phase B "open question" in [docs/renoir-dataset-progress.md](../planning/workstreams/renoir-dataset/progress.md)).


---
*Did you reproduce this and observe something different? Counter-findings welcome. See [CONTRIBUTING.md](../../CONTRIBUTING.md) shape 4 and the [finding issue template](../../.github/ISSUE_TEMPLATE/finding.md).*
