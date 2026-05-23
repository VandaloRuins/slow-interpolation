# Expressionist style preset for the Modal LoRA trainer

Date: 2026-05-18.
Scope: hyperparameter preset for training SDXL LoRAs on **expressionist or gestural styles** under the Modal trainer ([`../../cloud/train_app.py`](../../cloud/train_app.py)). The trainer's default hyperparameters (set during the Renoir cold-run for floral / atmospheric style) under-fit expressionist styles; this finding documents the alternative preset that recovers them.

Companion docs:
- [`kohya-vs-ai-toolkit-renoir.md`](kohya-vs-ai-toolkit-renoir.md): the floral preset, validated on Renoir.
- The Soutine-LoRA workstream cold-run produced this finding (v1 failure + v2 fix). Workstream log lives in the maintainer's private planning folder during v0.1; surfaces in v0.2 with the Soutine art release.
- [`../manual/train-lora-on-modal.md`](../manual/train-lora-on-modal.md): the canonical training protocol; "Step 3: Author the training YAML" cross-references this finding for preset selection.

## Two presets, one trainer

| Preset | Default for | Network rank | Network alpha | UNet LR | Repeats | Wall (80-110 imgs, L40S) | Cost |
|---|---|---|---|---|---|---|---|
| **Floral** (default) | Atmospheric, low-frequency style (impressionism, tonalism, broken-color florals) | 16 | 8 | 3.0e-5 | 6 | 24-47 min | $0.80-1.50 |
| **Expressionist** | High-frequency / gestural style (Soutine, Kokoschka, Schiele, Bacon, mark-making heavy) | 32 | 32 | 5.0e-4 | 2 | 10-15 min | $0.30-0.50 |

Everything else stays identical: AdamW8bit, bf16, cosine_with_restarts (4 cycles), 10 epochs, save_every_n_epochs 1, batch 2, gradient accumulation 4, min_snr_gamma 5.0, network_train_unet_only true, 1024 resolution, bucketing 768-1344.

The expressionist preset is **faster and cheaper** than the floral preset (fewer repeats), at the cost of 2x checkpoint size (170 MB vs 85 MB at Dim 32 vs 16).

## How to pick

| Domain | Preset | Tell |
|---|---|---|
| Florals (any artist) | Floral | Broken color, soft transitions, subject is a bouquet / arrangement |
| Impressionist landscapes / gardens | Floral | Loose handling but low high-frequency content |
| Tonalist or Hudson River School landscapes | Floral | Atmospheric, smooth value transitions |
| Soutine figures / carcasses / landscapes | Expressionist | Twisted silhouettes, dragging brush, charged surface |
| Bacon figures | Expressionist | Smeared faces, gestural distortion |
| Schiele / Kokoschka portraits | Expressionist | Angular distortion, raw mark-making |
| Van Gogh | Expressionist | Heavy impasto, directional strokes |
| Cezanne | Likely Floral, test both | Structured strokes but low-frequency overall |
| Modern abstract / gestural | Expressionist | Mark-making is the subject |
| Photographic / realist | Neither preset directly; consider higher rank + low LR; not validated by either cold-run | Goal is subject fidelity, not style; the LoRA primarily encodes subject identity |

When in doubt: try **floral first** (cheaper to ship, smaller files). If the cold-run validation shows the style did not transfer (target style markers are missing from epoch-10 renders even at scale 0.85), re-train with **expressionist** preset. The Soutine workstream did exactly this: v1 with floral preset failed on style; v2 with expressionist preset succeeded; cost of the failed-then-redone path was $1.13 total, well under the $4 ceiling for a single training run.

## Evidence

### Soutine v1 (floral preset) vs v2 (expressionist preset)

Same dataset (80 images, `stn` trigger), same engine (Kohya `sd-scripts` commit `502cc3fab2aa`), same validation prompts (11 human figures, 832×1216 portrait, scale 0.85, Lightning 4-step, seed 42).

| Prompt | v1 (floral preset) | v2 (expressionist preset) |
|---|---|---|
| O1 street musician | Academic portrait, smooth | Twisted face, charged surface |
| O2 old woman shawl | Dignified seated, soft handling | Distorted features, dragging brush in folds |
| O3 fisherman on quay | Dark interior background (subject drift) | Maritime background, distorted figure |
| O4 cellist | Dark suit, dark background | Twisted body around cello, expressionist face |
| O5 young woman blue | Standing academic | Standing distorted, more Soutine-character |
| O6 priest | Arms crossed clean | Gender ambiguous (HIGH-LR subject drift) |
| H1 page boy | Adult-male reading | Young-boy reading, characteristic Soutine head |
| H2 butcher's boy | Clean white apron (subject drift) | Distorted features, less of the red staining |
| H3 chorister | White surplice clean | More expressionist face, posture preserved |
| H4 self-portrait | Neat head + shoulders | **Strongly Soutine: elongated head, mournful eyes, green coat, brown palette** |
| H5 bellhop | Red jacket + red pants seated | Red jacket + dark pants, pointed-head distortion |

v2 wins style on 11/11 cells. v2 loses subject fidelity on 1-2 cells (O6 priest, partial drift on H2 staining + bellhop pants). Net headline: **expressionist preset captures Soutine; floral preset does not.**

Visual evidence: 3-row side-by-side PNGs (off-distribution + hold-out tracks) and an interactive 3-way HTML viewer live under `outputs/validation/` on the maintainer's machine (gitignored). They will be published on HuggingFace Hub alongside the Soutine LoRA model card in v0.2.

### Mechanism (working theory)

Three contributors, not isolated:
1. **Dim 32 / Alpha 32** gives the LoRA capacity for high-frequency marks. Soutine's dragged brush + twisted silhouette + charged surface are all high-frequency style features. Renoir florals are low-frequency (broken color, soft transitions); Dim 16 was sufficient.
2. **LR 5e-4** (17x higher than floral's 3e-5) is needed to overwrite SDXL's strong prior on figure prompts. SDXL has been trained on millions of portrait photographs; a portrait prompt without a strong LoRA push reverts to neoclassical / photographic register. Floral prompts have weaker priors; lower LR was sufficient there.
3. **2 repeats** (vs floral's 6) prevents subject overfit at the high LR. With 6 repeats at LR 5e-4 the LoRA would memorize specific training images, defeating generalization.

Disentangling these would require single-variable A/B (Dim only, LR only, repeats only). Not done. The production decision does not depend on the isolation; the combined preset works.

### Cost comparison

Expressionist preset is **cheaper** than floral, not more expensive:

| Aspect | Floral preset (Renoir) | Expressionist preset (Soutine v2) |
|---|---|---|
| Total optimisation steps (105 imgs / 6 repeats / batch 2 / grad-acc 4) | 787 | 100 |
| Wall on L40S | 45-47 min | 10-12 min |
| Cost | $1.50 | $0.34 |
| Checkpoint size (per epoch) | 85 MB | 170 MB |
| Storage per 10-epoch run | 850 MB | 1.7 GB |

The 2x checkpoint size is the only material cost. For workshop use this is negligible; for a workshop with N students × M domains, storage adds up but stays under tens of GB.

## How to use in a training YAML

Just override the four fields in the relevant `examples/configs/training/<family>.yaml`:

```yaml
training:
  network_rank: 32        # was 16
  network_alpha: 32       # was 8
  unet_lr: 5.0e-4         # was 3.0e-5
  repeats: 2              # was 6
  # everything else unchanged from the floral preset
```

Worked example: [`../../examples/configs/training/soutine_figures_v2.yaml`](../../examples/configs/training/soutine_figures_v2.yaml).

## Open questions

1. **Floral-and-expressionist hybrid styles** (e.g. late Monet water lilies, where atmospheric soft transitions coexist with thick impasto marks): neither preset has been tested. Hypothesis: split the difference (Dim 24 / Alpha 16 / LR 1e-4 / 4 repeats), or train two LoRAs and ensemble at render time.
2. **Pure subject LoRAs** (a specific person, a specific object): not in scope. The Modal trainer is a style-LoRA trainer; subject LoRAs likely want even higher rank + higher LR but also dreambooth-style techniques outside the current pipeline.
3. **Per-image weights** for expressionist datasets (down-weight noisy training samples to bias the LoRA toward the cleanest stylistic exemplars): blocked on a `per_image_repeats` v2 implementation in the Modal-trainer workstream.

## What this finding does NOT claim

- The expressionist preset is correct for every "expressionist" artist. It is validated on Soutine figures (n=1). Bacon, Schiele, Kokoschka, Van Gogh are likely candidates but unverified.
- The hyperparameters are optimal. They are CivitAI AI Toolkit's defaults under our Kohya engine, and they work; isolated single-variable A/B might find a better combination.
- The preset replaces the floral preset. Both are first-class; the choice depends on the domain's style frequency content.
