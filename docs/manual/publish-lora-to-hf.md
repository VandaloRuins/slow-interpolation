# Publish a LoRA to HuggingFace Hub (for agents)

You are an AI agent helping a student publish their freshly-trained LoRA to HuggingFace Hub so others can pull it via the slow-interpolation pipeline's `hf:<user>/<repo>` YAML syntax. This page is your operating manual.

This is the **last beat** of the dataset-to-render arc that [`dataset-curation.md`](dataset-curation.md) → [`train-lora-on-modal.md`](train-lora-on-modal.md) → [`validate-lora.md`](validate-lora.md) builds toward. By the time you reach this page, the student should have: a validated `.safetensors` checkpoint, a chosen keeper epoch, a calibrated `lora_scale` recommendation, and a clear sense of their dataset's provenance.

The two demo LoRAs that ship with the repo are the worked examples:

- [`huggingface.co/VRuins/thomas-cole-sdxl-lora`](https://huggingface.co/VRuins/thomas-cole-sdxl-lora) (Hudson River School, with a single trigger word `tcole`).
- [`huggingface.co/VRuins/casa-del-suono-sdxl-lora`](https://huggingface.co/VRuins/casa-del-suono-sdxl-lora) (Italian fresco, no trigger word; descriptive prefix activates the style).

Their model cards are the canonical shape; read one before authoring your student's.

## When to use this protocol

- The student is satisfied with their validation grid and wants to share the LoRA publicly.
- The student wants the slow-interpolation pipeline's auto-download path (`lora_path: hf:<user>/<repo>` in YAML) to work for their own LoRA without manual file shuffling.
- A workshop facilitator wants a uniform "everyone publishes" beat to close the session.

Do NOT use this protocol for LoRAs whose training data has unresolved provenance or licensing issues. Surface the gap to the student and pause until they confirm.

## Inputs the student owes you

Before any upload step, capture these from the student. Write them down once; you reuse them in the model card and the YAML frontmatter:

| Input | Example | Why you need it |
|---|---|---|
| HuggingFace handle | `VRuins` | Goes in the HF repo path: `<handle>/<repo-name>`. |
| Repo name (kebab-case) | `vermeer-interiors-sdxl-lora` | The slug part of the repo path. Convention: `<subject>-sdxl-lora`. |
| Trigger word (if any) | `vmr`, or `None (descriptive prefix activates the style)` | Goes into the model card "Recommended settings" + the `instance_prompt` YAML frontmatter. |
| Recommended `lora_scale` | `0.75` for subject + style mix; `0.35` for strong-style LoRAs | The calibrated default; copies into the model card. |
| Style summary (one or two sentences) | "Italian fresco surface, terracotta and ochre palette" | Goes in the model card lede. |
| Training data provenance | "Wikimedia Commons public-domain paintings", "synthetic dataset generated from study of online references", "the student's own photo set" | Goes in the model card "Training data" section. **Critical:** ask explicitly; do not infer. |
| License | MIT (recommended for unrestricted derivative use) | Goes in the YAML frontmatter + the "License" section. |
| One or two sample renders | PNG stills from the validation grid, or a 60s loop MP4 | Embedded in the model card for visual reference. |

If the student does not have an HF account, branch into the **account-setup walkthrough** below before anything else.

## The five phases

| Phase | Who does it |
|---|---|
| 0. HuggingFace account check | You verify the student is authenticated. Walk them through OAuth signup + write-scope token generation if they are not. |
| 1. Stage the LoRA + draft the model card | You copy the checkpoint to a staging folder, write the model card, surface the draft to the student for review. |
| 2. Create the empty HF repo | You run `hf repos create` once the model card is approved. |
| 3. Upload | You run `hf upload`; the student watches progress. |
| 4. Verify + cross-link | You navigate to the rendered page, screenshot it for the student, then update the slow-interpolation training docs to cite the new LoRA. |

## Phase 0: HuggingFace account + token

Check for existing auth:

```bash
hf auth whoami 2>&1
```

If it returns a username, the student is logged in. Confirm the username matches the handle they want for the publication (it usually does, but a student with multiple accounts may have logged in under a different one). If you need a different account, run `hf auth logout` and `hf auth login` with their target token.

If `whoami` errors:

1. **Surface the offer**: "HuggingFace Hub is free. Sign up at https://huggingface.co/join; the Starter plan covers hosting LoRAs publicly at no cost. Email + password OR GitHub / Google OAuth."
2. **Open the signup page** via your runtime's browser-control capability (Playwright MCP for Claude Code; equivalent for other runtimes). Navigate to `https://huggingface.co/join`.
3. **Default-deny on credentials**: stop at the signup form and let the student complete it. Same per-session-consent escalation as in [`modal-operations.md`](modal-operations.md) "Default-deny with consent escalation" if the student wants you to fill the form on their behalf.
4. **After signup + email verification**: walk them to https://huggingface.co/settings/tokens/new with **Write** scope pre-selected (URL: `https://huggingface.co/settings/tokens/new?tokenType=fineGrained`, then they pick `Write access to all repos under <handle>/`). Have them copy the token (starts with `hf_...`).
5. **CLI login**: in the repo's terminal:
   ```bash
   pip install -U huggingface_hub
   hf auth login --token <token-value> --add-to-git-credential
   ```
   Or interactively (the CLI prompts for the token):
   ```bash
   hf auth login
   ```
   Either way, the token writes to `~/.cache/huggingface/token` for `hf` commands. Verify with `hf auth whoami`.

If the user resists creating an account, document the LoRA + model card locally under `models/hf-staging/<handle>/<repo>/` and surface the staged state to them; they can upload later.

## Phase 1: Stage the LoRA + draft the model card

### Stage the file

The slow-interpolation training output lands at `models/loras/<Family>_<role>_epoch_<N>.safetensors`. The HF repo gets a renamed copy:

```bash
mkdir -p models/hf-staging/<handle>/<repo-name>
cp models/loras/<Family>_<role>_epoch_<N>.safetensors models/hf-staging/<handle>/<repo-name>/<repo-name>.safetensors
```

Renaming to match the repo name (`<repo-name>.safetensors`) keeps the `hf:<user>/<repo>` auto-download convention working (the resolver in `src/slow_interpolation/keyframes.py` defaults to `<repo-name>.safetensors` as the filename inside the HF repo unless `style.lora_filename` overrides it).

### Stage one or two sample assets

Cards with images get more attention than cards without. Extract a still frame from a validation render or a render you made with the LoRA:

```bash
ffmpeg -y -i outputs/<some-loop>.mp4 -ss 00:00:30 -frames:v 1 -q:v 2 models/hf-staging/<handle>/<repo-name>/sample_main.jpg
cp outputs/<some-loop>.mp4 models/hf-staging/<handle>/<repo-name>/sample_clip.mp4
```

Two assets is plenty. The model card embeds them.

### Draft the model card

The template below is a parameterised version of the worked examples. Replace `<bracketed>` placeholders with the student's inputs from the table above. Save as `models/hf-staging/<handle>/<repo-name>/README.md`.

```markdown
---
license: mit
tags:
  - text-to-image
  - stable-diffusion
  - stable-diffusion-xl
  - lora
  - diffusers
  - <subject-or-style-tag, e.g. art-style, landscape, portrait>
  - <subject-domain-tag, e.g. hudson-river-school, italian-fresco>
base_model: stabilityai/stable-diffusion-xl-base-1.0
instance_prompt: <trigger-word, OR omit this line if descriptive-prefix LoRA>
widget:
  - text: "<one-sentence prompt that activates the LoRA + names a vivid scene>"
  - text: "<a second prompt to show range>"
---

# <Subject + LoRA model name>

<one-paragraph lede: what the LoRA captures, what it's good for, what made you train it>

![<descriptive alt text>](sample_main.jpg)

*Above: still frame from a render with this LoRA. Full clip: [`sample_clip.mp4`](sample_clip.mp4) in the Files tab.*

This LoRA was trained as part of the [slow-interpolation](https://github.com/VandaloRuins/slow-interpolation) project's dataset-mosaic protocol. Train your own LoRA in any style by following the [`dataset-curation`](https://github.com/VandaloRuins/slow-interpolation/blob/main/docs/manual/dataset-curation.md) and [`train-on-Modal`](https://github.com/VandaloRuins/slow-interpolation/blob/main/docs/manual/train-lora-on-modal.md) protocols in that repo.

## Quick use

\`\`\`python
from diffusers import DiffusionPipeline, EulerDiscreteScheduler
import torch

pipe = DiffusionPipeline.from_pretrained(
    "stabilityai/stable-diffusion-xl-base-1.0",
    torch_dtype=torch.float16,
    variant="fp16",
).to("cuda")

pipe.load_lora_weights("ByteDance/SDXL-Lightning", weight_name="sdxl_lightning_4step_lora.safetensors")
pipe.fuse_lora()
pipe.unload_lora_weights()
pipe.scheduler = EulerDiscreteScheduler.from_config(pipe.scheduler.config, timestep_spacing="trailing")

pipe.load_lora_weights("<handle>/<repo-name>", weight_name="<repo-name>.safetensors")
pipe.fuse_lora(lora_scale=<recommended-scale>)
pipe.unload_lora_weights()

image = pipe(
    prompt="<trigger-word OR descriptive prefix>, <your subject>",
    num_inference_steps=4,
    guidance_scale=1.5,
).images[0]
\`\`\`

## Recommended settings

- **Trigger word:** `<trigger>` (lead every prompt with it). OR `None; activated by descriptive prefix "..."` for prefix-style LoRAs.
- **`lora_scale`:** `<recommended-scale>` (calibrated default). Range: `<min>` to `<max>` typical.
- **Base model:** `stabilityai/stable-diffusion-xl-base-1.0`.
- **Lightning backbone:** stack with `ByteDance/SDXL-Lightning` 4-step LoRA for fast keyframe rendering.
- **Resolution:** `<width>x<height>` (SDXL native training bucket).
- **Negative prompt** (recommended): `<keywords that suppress incidental bias from the training data>`.

## Training data

<two to four sentences naming the training set source, the curation method, how many images, public-domain status if applicable. Be precise about provenance; this is the section other readers will check first.>

The dataset was curated via the [dataset-mosaic 5-phase protocol](https://github.com/VandaloRuins/slow-interpolation/blob/main/docs/manual/dataset-curation.md).

## Training settings

- **Engine:** Kohya / sd-scripts on Modal (the canonical training engine for the slow-interpolation project).
- **Network rank:** `<rank>`, **alpha:** `<alpha>`.
- **UNet LR:** `<lr>`, **optimizer:** `<adamw8bit | adafactor>`, **repeats:** `<n>`, **epochs:** `<n>`.
- **Resolution:** `<training-resolution>`.
- **Cost on Modal L40S:** ~$`<cost>`, ~`<wall>` min wall.
- Full hyperparameter rationale: [`docs/findings/lora-training.md`](https://github.com/VandaloRuins/slow-interpolation/blob/main/docs/findings/lora-training.md).

The published checkpoint is **epoch <N>**, picked from the validation grid as the best balance of style strength vs. atmospheric flexibility.

## Provenance and attribution

LoRA trained by `<student name or handle>` as part of the slow-interpolation project. Released under <license>.

<one to two sentences on training-data attribution: who owns the source images, what license they sit under, what permissions the student has to derive from them>

## License

MIT for the LoRA weights. The underlying SDXL base model is licensed separately by Stability AI under the CreativeML OpenRAIL-M license; users must comply with both.

## Cite

> `<student>`, *<LoRA name>*, slow-interpolation derivative, <year>. https://huggingface.co/<handle>/<repo-name>

## Related work

- The slow-interpolation pipeline: https://github.com/VandaloRuins/slow-interpolation.
- The two demo LoRAs that informed this training: [`VRuins/thomas-cole-sdxl-lora`](https://huggingface.co/VRuins/thomas-cole-sdxl-lora), [`VRuins/casa-del-suono-sdxl-lora`](https://huggingface.co/VRuins/casa-del-suono-sdxl-lora).
```

### Surface the draft to the student

Before any upload:

> "Here's the model card I drafted. Read the **Training data** + **Provenance and attribution** sections in particular; those are what other readers will check first. If anything is wrong, tell me now and I'll revise. Otherwise I'll create the HF repo and push."

Wait for the student's approval. Do NOT upload without it. The model card is the public face of their work.

If they want edits, revise in place and resurface. Only proceed when they say go.

## Phase 2: Create the empty HF repo

Once the model card is approved:

```bash
hf repos create <handle>/<repo-name> --repo-type model
```

Output should confirm:

```
Successfully created <handle>/<repo-name> on the Hub.
Your repo is now available at https://huggingface.co/<handle>/<repo-name>
```

If you get `403 Forbidden: You don't have the rights to create a model under the namespace "<handle>"`, the active token does not have write scope or it is scoped to a different namespace. Branch back to Phase 0 token-regeneration.

## Phase 3: Upload

Upload the entire staging folder in one command:

```bash
hf upload <handle>/<repo-name> models/hf-staging/<handle>/<repo-name> . \
  --commit-message "Initial release of <LoRA name>"
```

The upload streams the `.safetensors` (~228 MB for SDXL LoRAs in fp16), the model card, and the sample assets. On a typical connection: 2 to 5 minutes wall.

For long uploads, the `hf upload` command is foreground-blocking by default. If your runtime supports background execution, dispatch with `run_in_background: true` so the agent can do other work while it streams; otherwise wait for completion.

## Phase 4: Verify + cross-link

### Verify the rendered page

Navigate via your runtime's browser-control capability to:

```
https://huggingface.co/<handle>/<repo-name>
```

Screenshot the page for the student. Confirm:

- Title + tags rendered correctly from the YAML frontmatter.
- Sample image displays inline.
- Recommended-settings section is readable.
- Quick-use code snippet has no syntax errors.

If anything is off, edit the staging README, re-upload (the second `hf upload` is incremental; only changed files transfer), re-verify.

### Cross-link from the slow-interpolation training notes

Surface to the student:

> "Your LoRA is live at https://huggingface.co/<handle>/<repo-name>. Anyone with the slow-interpolation pipeline can now use it by writing `lora_path: hf:<handle>/<repo-name>` in their YAML config; the pipeline auto-downloads it on first reference. Want me to add an entry to the slow-interpolation findings doc so other workshop students can find it?"

If yes, append an entry to `docs/findings/lora-training.md` (or open a PR to the upstream repo if the student is working in a fork) under a "Community LoRAs" section.

## Failure modes

| Symptom | Likely cause | Action |
|---|---|---|
| `hf upload` hits HTTP 401 | Token expired or wrong scope | Re-run Phase 0 token generation. |
| `hf repos create` returns 403 | Token has read-only scope | Generate a token with `Write` (or fine-grained Write to the namespace). |
| Model card renders without sample images | Image filenames in markdown do not match files in the repo, or images are too large | Confirm filenames; re-extract stills with ffmpeg if needed. |
| `widget:` block does not render auto-generated samples | HF Hub inference queue rate-limits; can take hours | Wait and revisit; or remove the `widget` block if not needed. |
| LoRA fails to load via `hf:<handle>/<repo-name>` in the pipeline | Filename inside the repo does not match `<repo-name>.safetensors` convention | Either rename the file in the repo to match, OR set `style.lora_filename: <actual-filename>.safetensors` in the YAML. |
| Public viewer reports `Files and versions` is empty | Upload silently failed | Re-run `hf upload`; check the dashboard at https://huggingface.co/<handle>/<repo-name>/tree/main. |

## What this protocol does NOT cover

- **Private LoRA hosting.** HuggingFace allows private model repos on paid plans; this protocol assumes public release. If the student wants private, set `--private` on `hf repos create` and skip the cross-linking step.
- **Multiple-checkpoint releases.** This protocol ships one keeper epoch. For multiple checkpoints (e.g. light + strong variants), include all `.safetensors` files in the staging folder; the model card explains which to pick.
- **Fine-grained LoRA versioning.** Subsequent training rounds produce new checkpoints. Convention: upload as new files (`<repo-name>-v2.safetensors`) and edit the model card to call out the recommended version. Heavyweight: create a separate `<repo-name>-v2` repo.
- **License changes.** This protocol defaults to MIT for unrestricted derivative use. If the student wants CC-BY, CC-BY-NC, or a custom license, change the YAML frontmatter `license:` field and the License section. Confirm the license is compatible with the training data's license.

## Cross-links

- [`dataset-curation.md`](dataset-curation.md): the 5-phase curation that produces the training ZIP.
- [`train-lora-on-modal.md`](train-lora-on-modal.md): the training step that produces the `.safetensors`.
- [`validate-lora.md`](validate-lora.md): the validation step that surfaces the keeper epoch.
- [`modal-operations.md`](modal-operations.md): the modal subagent's brief (account-setup pattern this page mirrors).
- The two demo LoRAs as worked examples: [`VRuins/thomas-cole-sdxl-lora`](https://huggingface.co/VRuins/thomas-cole-sdxl-lora), [`VRuins/casa-del-suono-sdxl-lora`](https://huggingface.co/VRuins/casa-del-suono-sdxl-lora).
