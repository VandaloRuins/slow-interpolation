# LoRA training, deep dive

A more detailed companion to [lora-training.md](lora-training.md) (the Renoir-specific CivitAI recipe) and [dataset-practice.md](dataset-practice.md) (the dataset workflow). Use this when you want to know *why* a setting is the value it is, when you want hands-on control beyond CivitAI's wizard, or when you're tuning a LoRA whose objective differs from "style transfer".

Contents:

1. [What a LoRA actually does to SDXL](#1-what-a-lora-actually-does-to-sdxl)
2. [Four LoRA objectives and how they change everything downstream](#2-four-lora-objectives-and-how-they-change-everything-downstream)
3. [Dataset curation, by objective](#3-dataset-curation-by-objective)
4. [Captioning, by objective](#4-captioning-by-objective)
5. [Hyperparameters that actually matter](#5-hyperparameters-that-actually-matter)
6. [Training tools beyond CivitAI](#6-training-tools-beyond-civitai)
7. [Validation protocol](#7-validation-protocol)
8. [Failure modes and their diagnostics](#8-failure-modes-and-their-diagnostics)
9. [Recipes per objective (cheat sheets)](#9-recipes-per-objective-cheat-sheets)

## 1. What a LoRA actually does to SDXL

LoRA stands for Low-Rank Adaptation. The underlying observation: full fine-tuning of a 2.6 B-parameter model like SDXL is wasteful when the change you want is small and concentrated. Most concepts can be expressed as a low-rank perturbation to the existing weights.

Mathematically: instead of updating a weight matrix `W` of shape `(d_out, d_in)` directly, you learn two small matrices `A` (shape `d_out × r`) and `B` (shape `r × d_in`) and apply `W' = W + (alpha / r) · A · B` at inference time. `r` is the rank (LoRA "dim"), typically 4 to 128. `alpha` is a scaling factor that controls how strongly the LoRA's update is mixed in.

Three practical consequences flow from this:

- **File size is tiny.** A rank-16 SDXL LoRA is ~50 MB versus ~6.5 GB for a full fine-tune.
- **LoRAs stack.** You can load a Renoir LoRA and a "rim lighting" LoRA at the same time and their `A·B` deltas add.
- **The base model is the floor.** A LoRA can move the output distribution but cannot teach the base model anything truly outside its training data. SDXL never saw a 17th-century Vermeer in pristine high-resolution scans; a Vermeer LoRA built on top of SDXL will always have a slight SDXL-ish artefact in the brushwork. This is why FLUX-based pipelines exist for use cases where SDXL's base distribution is the limiting factor.

SDXL is structurally important here. It has:
- Two text encoders (OpenCLIP-G + CLIP-L) — most modern training recipes train only the UNet because (a) the text encoders are 80% of the parameters, (b) different inference stacks load them differently, (c) training them hurts more than it helps for style and concept LoRAs.
- 2.6 B UNet parameters across cross-attention blocks (where text-image alignment lives) and self-attention blocks (where spatial structure lives). LoRA usually targets all attention blocks; some advanced setups target only cross-attention for concept LoRAs or only self-attention for style LoRAs.
- A 1024×1024 native resolution with bucketing support for non-square aspect ratios. SDXL's training buckets are: 1024×1024 (square), 1152×896, 1216×832, 1344×768 (16:9), 896×1152, 832×1216, 768×1344 (9:16), plus a few intermediates. Train at these buckets; bucket mismatches teach the LoRA to fight the base model's positional encodings.

## 2. Four LoRA objectives and how they change everything downstream

Almost every LoRA-related decision (dataset size, captioning, rank, learning rate, scale at inference) is downstream of a single question: **what is this LoRA for?**

Four broad objectives, each with characteristic settings:

| Objective | Example | What it tries to learn | Inference scale | Typical rank |
|---|---|---|---|---|
| **Style** | Renoir flowers, Thomas Cole landscapes, watercolour, woodcut | A consistent surface (palette, brushwork, lighting) on arbitrary subjects | 0.6–0.9 | 16–32 |
| **Subject** | Casa del Suono fresco (the specific painted ceiling), a specific museum's interior, a recognisable building | A specific scene or motif the model can recompose | 0.7–0.95 | 16–32 |
| **Character** | A consistent face / body / costume across new compositions | A specific identity, robust to angle, lighting, expression | 0.85–1.0 | 16–64 |
| **Concept** | "Sausage-roll-shaped objects", an abstract relationship, a procedural geometry | A novel concept the base model doesn't have a token for | 0.7–0.9 | 32–128 |

Hybrid LoRAs (style + concept; subject + character) work but always under-fit relative to a focused LoRA at the same training budget. Prefer one objective per LoRA; stack two LoRAs at inference time if you need both.

The Renoir flowers LoRA in this project is a **style LoRA** (the recipe at [lora-training.md](lora-training.md) is calibrated for it). The Casa del Suono fresco LoRA was a **subject + style hybrid** that's why it behaves erratically at low scale on off-distribution subjects. The Thomas Cole LoRA was also **style**.

## 3. Dataset curation, by objective

The single most important predictor of a good LoRA is the dataset. Hyperparameters can dial in a result; bad data caps the ceiling.

The five-phase recipe in [dataset-practice.md](dataset-practice.md) describes the *how* (sourcing, vision audit, cropping, human-in-the-loop refinement, captioning, packaging). This section is the *what to put in* per objective.

### Style LoRA

**Goal:** capture the artist's hand without locking in a specific subject.

- **Size:** 80 to 200 images. Below 80, the LoRA over-fits whichever subjects dominate (you end up with "Renoir bouquets" not "Renoir style"). Above 250 the marginal gain flattens.
- **Subject diversity is the whole game.** If you train Renoir on 100 bouquets, the LoRA will paint everything as bouquets. If you train Renoir on 30 bouquets + 30 figures + 30 gardens + 10 portraits, the LoRA learns the style as the invariant across subjects. Our Renoir build has 96 still-life + 22 scenes-with-flowers; the scenes-with-flowers are the leverage point for subject generalisation.
- **Resolution floor:** 1024 px short side (SDXL native bucket). 768 to 1024 will be bucket-downsampled into smaller buckets; the data is half-wasted.
- **Surface diversity matters more than count.** Two paintings with the same composition but different lighting teach more about *style* than ten identical compositions.

### Subject LoRA

**Goal:** a specific scene or building the model can place into new contexts.

- **Size:** 20 to 60 images. Subject LoRAs need fewer images because the subject itself is the invariant; the model just needs to memorise it.
- **Angle and distance diversity are the whole game.** Five photos of the same fresco from the same angle teach the model "this is one painting in a museum". The same fresco from five different angles, different lighting conditions, different distances, teaches the model "this is a 3D scene I can rotate".
- **Backgrounds should vary.** If the subject always appears against the same wall, the LoRA learns the wall too. Use crops to remove identifiable surroundings, or include images shot in different settings.

### Character LoRA

**Goal:** a consistent identity across new compositions.

- **Size:** 15 to 50 face / head images, ideally 30+ for robustness.
- **Identity-cue diversity is the whole game.** Different expressions, angles, lighting, ages, outfits. The LoRA should learn the structural face geometry that's invariant under all of those.
- **Crop tight on the face for half the dataset, looser for the other half** so it can do both close-ups and full-body.
- **Caption strategy:** describe everything except the identity-relevant features. The trigger word + the absence of identity captions teaches the model "this is the part I should fill in".

### Concept LoRA

**Goal:** a new concept the base model doesn't already have a token for.

- **Size:** 30 to 80 images.
- **Compositional diversity is the whole game.** The concept must appear in different contexts so the LoRA learns the concept itself, not the context.
- **High caption count.** Captions should describe everything around the concept and use the trigger word as the only label for the new thing.

## 4. Captioning, by objective

Captioning is the lever for *what* the LoRA learns. The rule is counter-intuitive: **describe everything except what you want the LoRA to memorise**.

The text encoder learns associations between caption tokens and image content. Anything mentioned in the caption gets attached to the corresponding token. Anything in the image but not in the caption gets absorbed by the trigger word (the only token that can hold it). So:

- For a **style LoRA**: caption the subject and composition in detail; let the style fall through to the trigger word. Renoir example: `rfl, a porcelain vase of roses, centered still life on a table, warm afternoon light, ..., oil painting, impressionist`. The composition is captioned; "Renoir-ness" is the trigger.
- For a **subject LoRA**: caption everything except the subject's identifying features. If training a LoRA on the Casa del Suono fresco, mention the architecture, lighting, viewing angle, but NOT the specific motifs of the fresco. Those get absorbed by the trigger.
- For a **character LoRA**: caption clothing, pose, expression, environment — NOT the face. The face goes into the trigger.
- For a **concept LoRA**: caption everything around the concept exhaustively. The concept itself appears as the trigger.

Captioning length:

- 30 to 60 words per caption for style / subject LoRAs (matches our Renoir recipe).
- 15 to 40 words for character / concept LoRAs (shorter, more focused captions train the model faster on the trigger).

Captioning consistency:

- All captions should start with the trigger word.
- All captions should end with a fixed style suffix (`oil painting, impressionist` for Renoir; `Hudson River School` for Cole; `painted ceiling fresco` for Casa del Suono). This gives the text encoder a clean "this is the LoRA's territory" signal.
- Don't shuffle captions during training. The text encoder learns positional patterns (trigger-first, suffix-last); shuffling scrambles them.

Caption generation:

- **Rule-based, deterministic** (what we did for Renoir): cheap, debuggable, byte-identical on re-runs. Right starting point for a tight subject family.
- **Vision-language pass** (Gemini 2.5 Pro / Claude with vision): higher accuracy on subjects too generic for keyword matching. Run as a second pass if the first-training-pass LoRA shows specific failure modes (can't distinguish anemones from roses, mislabels lilacs as bouquets, etc.).
- **Caption-with-pixels approach** (BLIP-2 / LLaVA / Florence-2): runs locally without API cost. Lower quality than Gemini / Claude but good enough for many datasets.

## 5. Hyperparameters that actually matter

The CivitAI wizard exposes ~10 settings. Most are noise; six actually matter.

### Network rank (dim)

Controls the LoRA's capacity. Higher rank can express more, but also over-fits faster.

- **Style LoRAs:** 16 (default Renoir setting), occasionally 32 for very rich brushwork variation.
- **Subject LoRAs:** 16 to 32.
- **Character LoRAs:** 32 (best balance), 64 for very high identity fidelity needs.
- **Concept LoRAs:** 32 to 128. Higher when the concept is structurally complex (a new kind of geometry, a procedural pattern).

Rank 8 is too tight for SDXL except for the simplest concepts. Rank 128+ is wasteful for style / subject and starts producing visible JPEG-like artefacts at high LoRA scale.

### Network alpha

The scaling factor `(alpha / rank)`. Confusingly, alpha is *not* a strength setting — it's a normalisation that interacts with learning rate.

- Standard practice: **alpha = rank / 2** (so the scaling factor is 0.5). Renoir uses rank 16, alpha 8.
- Alternative: alpha = rank (scaling factor 1.0). Equivalent to running at 2x the learning rate; saves a hyperparameter to tune but is harder to debug.
- LoRA+ (the 2024 enhancement): different alpha for A and B matrices, with the ratio (alpha_B / alpha_A) typically 16x. This is now the default in modern training recipes; if your trainer supports it, turn it on.

### Learning rate (UNet)

The single most-tuned hyperparameter. Style and subject LoRAs are more forgiving than character LoRAs.

- **Style LoRAs:** 1e-4 (Cole-style aggressive) to 3e-5 (Renoir-style conservative). Higher LR overshoots the auction-catalogue colour cast or the dominant subject in 24 hours of training.
- **Subject LoRAs:** 5e-5.
- **Character LoRAs:** 1e-4 to 1e-5. Identity is fragile; lower LR + more epochs is safer.
- **Concept LoRAs:** 1e-4 typically.

For automatic LR setting, the Prodigy optimizer adapts itself: set LR=1.0 and let Prodigy find the right effective LR per layer. This is the easiest path for someone new to LoRA training. Adafactor is the alternative (less common for LoRA, more common for full fine-tuning).

### Text-encoder learning rate

Almost always: **zero (text encoder frozen)**. SDXL has two text encoders and training them produces LoRAs that are incompatible with consumer UIs (which load LoRAs UNet-only by default). Training the text encoder also tends to teach the model captions instead of pixels.

The exception: when training a concept LoRA for a completely novel idea where the base model has no related tokens, a tiny text-encoder LR (e.g. 1e-5, 10x lower than UNet LR) can help anchor the trigger word. We've never needed this for the slow-interpolation project.

### Batch size + repeats

`effective_batch = train_batch_size × gradient_accumulation_steps × num_gpus`

- Style / subject LoRAs: effective batch 8 is the proven setting. Most consumer GPUs need `batch=2, accum=4` to reach it.
- Character LoRAs: effective batch 4 (gentler updates).
- Repeats per image: 6 for style, 10 for character, 4 for concept.

`steps_per_epoch = images × repeats / batch`. For Renoir: 97 × 6 / 8 = 73 steps per epoch.

### Epochs + save schedule

- 10 epochs is the standard target for style. Save every epoch, evaluate visually, pick the best.
- Character LoRAs sometimes plateau at epoch 4 to 6; running longer over-fits.
- Save 2 to 3 checkpoints (light + medium + strong) and use them at different LoRA scales for different render intents.

## 6. Training tools beyond CivitAI

CivitAI's on-site trainer is the easiest path: upload ZIP, set a few sliders, push button, wait. The trade-offs are: limited visibility into the training process, no live loss / validation monitoring, no advanced features (LoRA+, fused passes, Prodigy), and one fixed set of optimisation defaults.

If you want hands-on control, four credible tools as of 2026:

### Kohya_ss + sd-scripts

The reference implementation. Almost every other tool is a wrapper around this.

- **What it is:** Python scripts from kohya-ss/sd-scripts. The bmaltais/kohya_ss fork wraps them in a Gradio UI.
- **Strengths:** every parameter is exposed. LoRA+, fused backward pass, Prodigy, Adafactor, regularisation images, network train UNet-only, save-every-N-steps, weight decay, gradient clipping, snr-gamma, all of it. The community standard.
- **Weaknesses:** the UI is dense; understanding what every field does takes a Saturday. Setting up the Python environment with the right CUDA / xformers versions is fiddly.
- **VRAM:** 10 GB for SDXL with fused backward pass + bf16. 24 GB for comfortable training without fusing.
- **Default for serious SDXL work.** If we want to train the Renoir LoRA ourselves rather than on CivitAI, this is the tool.

Install: `git clone https://github.com/bmaltais/kohya_ss; cd kohya_ss; ./setup.sh` (or `setup.bat` on Windows). Launch the GUI: `./gui.sh`.

Best entry path: load one of the bundled "LoRA" presets, change only the dataset path and trigger word, run. Then iterate.

### OneTrainer

A newer alternative with a cleaner UI.

- **What it is:** standalone trainer with a desktop GUI (not a wrapper around sd-scripts).
- **Strengths:** simpler interface, better defaults out of the box, integrated tensorboard / sample-image generation during training. Closer to "click and go" while still exposing the important knobs.
- **Weaknesses:** smaller community; some advanced sd-scripts features lag behind kohya_ss by months.
- **Verdict:** good first tool for someone who wants more than CivitAI but isn't ready for kohya_ss's intensity.

### AI Toolkit (Ostris)

The 2024 to 2026 darling of the FLUX training community, also supports SDXL.

- **What it is:** standalone Python library + web UI from Ostris. Built primarily for FLUX, then back-ported to SDXL.
- **Strengths:** opinionated defaults that are very good. Beautiful web UI. The Ostris training recipes are widely cited and benchmarked.
- **Weaknesses:** less flexible than kohya_ss for unusual configurations. SDXL is a second-class citizen; FLUX support is primary.
- **Verdict:** if we ever switch from SDXL to FLUX for the slow-interpolation pipeline, this is the trainer. For SDXL, kohya_ss is more battle-tested.

### Cloud trainers with control: fal.ai / Replicate

When you want kohya_ss's flexibility but not the GPU rental.

- **fal.ai `fal-ai/flux-lora-fast-training`:** FLUX training endpoint. Pass a ZIP of images, get a LoRA in 5 to 15 minutes. ~$2 to $5 per training run. For SDXL the equivalent is less well-developed; Replicate is better for SDXL.
- **Replicate `replicate/sdxl-lora-training`:** SDXL training. Pass a ZIP + caption template + a few hyperparameters. ~$1 to $3 per run.
- **Hugging Face training jobs:** newer offering, more transparent (you see the actual sd-scripts logs). More expensive per run.

Use cloud trainers when:
- You want to iterate fast and don't have a local GPU.
- You're training many LoRAs (e.g., one per artist in a series) and the per-LoRA setup time matters.

Don't use cloud trainers when:
- You're tuning hyperparameters tightly; iteration latency is higher than local.
- You want the LoRA never to leave your machine (some commissions / IP-sensitive work).

### Recommendation for this project

| Phase | Tool | Why |
|---|---|---|
| First Renoir training run | CivitAI | Push-button, the playbook is already calibrated. |
| If first run is unsatisfactory | Kohya_ss locally | Tune LR, rank, repeats with full visibility. |
| Future LoRAs in the series | Kohya_ss locally | Once you've learned the tool, it's faster than re-uploading to CivitAI every time. |
| If we switch to FLUX | AI Toolkit | FLUX-native, current SOTA recipes. |

## 7. Validation protocol

A LoRA is only as good as its validation. The CivitAI playbook ([lora-training.md](lora-training.md) section 2) specifies 5 hold-out images; this section is the protocol.

### Pick the hold-outs

- 1 canonical case (the most prototypical example of what you're trying to learn).
- 1 minority case (a subject family with very few training examples, to test generalisation).
- 1 off-distribution case (a composition the LoRA wasn't trained on but should still work, to test the limits of the style transfer).
- 2 random samples from the training distribution, to spot over-fitting.

For Renoir these were: Cleveland roses-in-a-vase, AIC chrysanthemums, the geraniums-in-a-copper-basin, two Barnes Foundation bouquets.

### Render at every epoch

Generate the same 5 images at:
- LoRA off (base model, sanity baseline).
- Epoch 1 at scale 0.5.
- Epoch 5 at scale 0.7.
- Epoch 10 at scale 0.7, 0.85, and 1.0.

That's 5 × 6 = 30 renders. ~10 minutes on a 4090.

### Grade subjectively, write it down

Score each render 1 to 5 on:
- Style match (does it look like the artist?)
- Subject fidelity (did the prompt get rendered correctly?)
- Surface quality (impasto, broken colour, no JPEG artefacts?)
- No leakage (does the LoRA accidentally render frames, signatures, watermarks?)

Pick the epoch / scale combination with the best aggregate score. That's your release checkpoint.

### Save the grading

A simple markdown file `docs/findings/<lora-name>-validation.md`:

```
| Epoch | Scale | Test 1 | Test 2 | Test 3 | Test 4 | Test 5 | Avg | Notes |
|---|---|---|---|---|---|---|---|---|
| 1  | 0.5  | 2/5/3/5 | 1/5/2/5 | ... | 2.4 | too weak |
| 5  | 0.7  | 4/5/4/5 | 3/4/3/5 | ... | 3.6 | good middle ground |
| 10 | 0.85 | 5/4/5/5 | 5/3/4/5 | ... | 4.2 | release candidate |
```

This becomes invaluable when training the next LoRA in the series.

## 8. Failure modes and their diagnostics

Translated from the experience of training Cole, Casa del Suono, and (planned) Renoir.

| Symptom | Likely cause | Diagnostic | Fix |
|---|---|---|---|
| LoRA paints frames at scale ≥ 0.7 | Training data had visible frames | Re-inspect 5 random training images at full resolution. Check for any decorative border. | Re-crop the dataset more aggressively. The Phase A.7 / A.8 browser tools in this repo are for exactly this. |
| Output has an auction-catalogue colour cast | Sotheby's / Christie's scans dominate the dataset | Count by `collection` field in metadata.csv. If > 30 % is catalogue scans, expect this. | Mark catalogue scans as a separate concept group with lower repeats. Or remove them entirely if you have enough non-catalogue images. |
| LoRA disappears on cross-domain prompts | LoRA scale calibrated for in-distribution. See subject-distance note in [lora-training.md](lora-training.md) §6. | Render the same prompt at LoRA scales 0.5, 0.7, 0.85, 1.0. If 1.0 is the only one that shows the style, the LoRA is calibrated for in-distribution. | Scale UP, not down. Use 0.9 to 1.0 for cross-domain. Counter-intuitive but correct. |
| LoRA over-paints — every subject becomes the dominant training subject | Subject homogeneity in dataset | Compute per-subject counts. If one subject is > 40 % of dataset, expect over-painting. | Either rebalance the dataset (add more of other subjects) or train fewer epochs. |
| Trigger word doesn't activate the LoRA | Caption inconsistency (some captions don't lead with trigger) or trigger word collision with a real word | Audit captions.txt: does every line start with `<trigger>,`? Is the trigger unique in SDXL's vocabulary? | Fix captions, retrain. If trigger collides, pick a new one (3 to 4 random lowercase letters). |
| LoRA produces blurry / muddy outputs | Learning rate too high, over-fit | Loss curve should decrease then flatten. If it spikes erratically late in training, LR is too high. | Reduce LR by 2x, retrain. |
| LoRA scale > 1.2 is required to see any effect | Learning rate too low, under-fit | Loss curve is still decreasing at end of training. | Increase LR by 2x or train longer. |
| Identity drift (character LoRA) | Caption mentioned identity features that should have been absorbed by trigger | Re-audit captions: does any caption say "blonde hair" or "blue eyes" for a character whose identity includes those? | Remove those tokens from captions, retrain. |
| LoRA renders captions instead of pixels | Text encoder was trained alongside UNet | Check trainer config: `text_encoder_lr` should be 0 for SDXL style / subject / character LoRAs. | Retrain with text encoder frozen. |
| First-pass test renders look great but real prompts under-perform | Test prompts too similar to training captions | Always validate on prompts that *don't* mirror caption patterns. | Add a "wild prompt" to the validation set: something you'd actually want to render. |

## 9. Recipes per objective (cheat sheets)

Concrete starting hyperparameters per objective. Adjust based on validation.

### Style LoRA (SDXL, Renoir-class)

```
base_model: stabilityai/stable-diffusion-xl-base-1.0
network_module: networks.lora
network_dim: 16
network_alpha: 8
unet_lr: 3e-5
text_encoder_lr: 0
optimizer: AdamW8bit
lr_scheduler: cosine_with_restarts
lr_scheduler_num_cycles: 4
train_batch_size: 2
gradient_accumulation_steps: 4
repeats: 6
epochs: 10
resolution: 1024
enable_bucket: true
min_bucket_reso: 768
max_bucket_reso: 1344
bucket_no_upscale: true
mixed_precision: bf16
gradient_checkpointing: true
min_snr_gamma: 5
caption_extension: .txt
shuffle_caption: false
caption_tag_dropout_rate: 0
network_train_unet_only: true
save_every_n_epochs: 1
save_model_as: safetensors
```

### Subject LoRA (SDXL, Casa del Suono-class)

Same as style, except:

```
network_dim: 32
network_alpha: 16
unet_lr: 5e-5
repeats: 8
epochs: 8
```

Plus add ~10 to 15 regularisation images (generic SDXL renders of related-but-distinct subjects) at `reg_repeats: 1` to prevent the LoRA from collapsing onto the subject.

### Character LoRA (SDXL)

```
network_dim: 32
network_alpha: 16
unet_lr: 1e-4
text_encoder_lr: 0
repeats: 10
epochs: 6
optimizer: Prodigy
unet_lr: 1.0   (Prodigy adapts from here)
```

Plus ~30 regularisation images of `1girl` / `1boy` to prevent identity bleed.

### Concept LoRA (SDXL)

```
network_dim: 64
network_alpha: 32
unet_lr: 1e-4
repeats: 4
epochs: 12
```

No regularisation usually; the concept is too novel.

## Further reading

- [kohya-ss/sd-scripts SDXL training docs](https://github.com/kohya-ss/sd-scripts/blob/main/docs/train_SDXL-en.md) — the canonical reference.
- [bmaltais/kohya_ss](https://github.com/bmaltais/kohya_ss) — the GUI wrapper.
- [Ostris AI Toolkit](https://github.com/ostris/ai-toolkit) — the FLUX-first trainer.
- [Hugging Face advanced LoRA training blog](https://huggingface.co/blog/sdxl_lora_advanced_script) — Pivotal Tuning, DoRA, LoRA+.
- [Apatero: Subject vs Style LoRA parameters](https://apatero.com/blog/lora-training-parameters-subject-vs-style-guide-2025) — short reference on the objective split.
- [SECourses LoRA tips](https://www.patreon.com/posts/excellent-tips-108426133) — exhaustive empirical notes from someone who has run hundreds of training jobs.
- [Civitai SDXL training overview](https://education.civitai.com/sdxl-1-0-training-overview/) — the on-site trainer's defaults explained.

Sources:
- [LoRA Training 2025 Ultimate Guide · sanj.dev](https://sanj.dev/post/lora-training-2025-ultimate-guide)
- [SDXL LoRA Guide · multic.com](https://www.multic.com/guides/sdxl-lora-guide/)
- [Comprehensive SDXL LoRA training guide · Guillaume Bieler / Medium](https://medium.com/@guillaume.bieler/a-comprehensive-guide-to-training-a-stable-diffusion-xl-lora-optimal-settings-dataset-building-844113a6d5b3)
- [Detailed Stable Diffusion LoRA training guide · ViewComfy](https://www.viewcomfy.com/blog/detailed-LoRA-training-guide-for-Stable-Diffusion)
- [Training a Character LoRA with Kohya_ss · Digital Zoom Studio](https://digitalzoomstudio.net/2026/03/training-a-character-lora-with-kohya_ss-automatic1111/)
- [Ostris AI Toolkit · GitHub](https://github.com/ostris/ai-toolkit)
- [Prodigy is ALL YOU NEED · Civitai](https://civitai.com/articles/1022/update-sdxl-scriptbdsqlsz-lora-training-advanced-tutorial2prodigy-is-all-you-need)
- [LoRA training scripts of the world, unite! · Hugging Face](https://huggingface.co/blog/sdxl_lora_advanced_script)
