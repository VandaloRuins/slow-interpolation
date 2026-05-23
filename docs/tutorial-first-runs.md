# First-runs tutorial (for the student-agent pair)

This page is the tutorial the agent walks the student through on their first session with the repo. Two LoRAs (Casa del Suono fresco, then Thomas Cole landscape), each shown at two scales: a single image first (fast feedback) and a 60-second slow loop (the technique at full scale). The student picks their own subject for each LoRA; the agent provides the technical context and dispatches.

The agent runs this tutorial **on the student's first session only**. Completion is tracked in `~/.cache/slow-interpolation/tutorial-status.json`; subsequent sessions skip the tutorial unless the student asks to re-run it.

## How the agent uses this page

This is the operational manual for the tutorial walk. Read it once on first invocation, then operate from it. The page assumes:

- The repo is cloned and `pip install -e .` has run.
- The Casa del Suono and Thomas Cole LoRAs are published on HuggingFace Hub (auto-downloaded on first reference).
- The `modal` subagent's routing protocol is available.

If any assumption fails, surface the gap to the student and fix it before starting the tutorial.

## The completion marker

Before starting, check `~/.cache/slow-interpolation/tutorial-status.json`:

```python
from pathlib import Path
import json

status_path = Path.home() / ".cache" / "slow-interpolation" / "tutorial-status.json"
if status_path.exists():
    status = json.loads(status_path.read_text())
    # If all four sub-steps are in steps_completed, skip the tutorial unless
    # the student explicitly says "run the tutorial again".
```

The four sub-step keys: `casa-del-suono-image`, `casa-del-suono-loop`, `cole-image`, `cole-loop`. If all are present, the tutorial is done. Greet the student normally and ask what they want to make.

If the marker is absent or partial, propose the tutorial:

> "It looks like this is your first session in the repo. There's a short tutorial that walks you through both demo LoRAs at two scales each (single image, then 60s slow loop). The four renders together take roughly 8 to 10 minutes on Modal (about $0.15 of your free credit) or 1 to 2 hours on a local card. Want to run it?"

Wait for the student's answer. If yes, proceed to Step 1. If no, write the marker with `skipped: true` and proceed to the normal "what do you want to make?" flow.

## Step 1: Casa del Suono fresco

### Context to share with the student

> "First LoRA: Casa del Suono. Casa del Suono is a music museum in Parma, Italy, housed in a 16th to 18th century palazzo whose ceiling and wall frescoes have a distinctive aesthetic: oil-on-plaster surface, warm chiaroscuro, terracotta and ochre palette, the kinds of compositions a ceiling-fresco painter would arrange. This LoRA was trained on a synthetic dataset generated to study and emulate that style. (That's a pattern you can reuse for your own LoRAs: study a style from reference, generate a synthetic dataset that matches what you found, train the LoRA on the synthetic set. The dataset-mosaic protocol in this repo walks you through it.)
>
> We'll do two renders with this LoRA: one still image, then one 60-second looping video. Same subject for both, so you see how the LoRA reads at both scales.
>
> Imagine a scene you would paint on a ceiling at Casa del Suono if you had been one of the original fresco painters. It does not have to be historically accurate; in fact, the more your idea contrasts with what an 18th century fresco painter would do, the more interesting the output. Some prompts to get you started:
>
> - 'a quiet garden at dusk, with low mist and a single lit window'
> - 'a stormy seascape framed by stone columns'
> - 'a satellite seen from a small balcony, holding a vine that drifts to the ground'
> - 'three people sleeping on a riverbank, summer afternoon'
> - 'a forgotten cathedral interior, dust in the air'
>
> Tell me your subject in one or two sentences."

Wait for the student's response. Capture the subject verbatim; you'll use it in both 1a (image) and 1b (loop).

### Brief technical context

Before dispatching, give the student this short explanation:

> "Here's what's about to happen, briefly. The base model is Stable Diffusion XL. The 'LoRA' is a small adaptation layer that teaches SDXL to think in fresco-language: palette, brushwork, surface. The Casa del Suono LoRA does not use a single trigger word like most LoRAs; instead it activates when the prompt opens with the descriptive style sentence. So your prompt becomes:
>
> `Italian fresco on aged plaster, warm chiaroscuro, visible brushwork, terracotta and ochre palette, <your subject here>`
>
> For the image, we render once. For the loop, we render three slightly different versions of your scene (early morning, midday, late afternoon) and let the pipeline drift between them, returning to the start without a cut."

### Step 1a: Casa del Suono fresco image

Build a one-prompt validation YAML in `outputs/_tutorial/casa-del-suono-image.yaml`:

```yaml
family: tutorial-casa-del-suono
lora_filename_template: "casa-del-suono-sdxl-lora.safetensors"
default_epochs: [1]

render:
  width: 1344
  height: 768
  seed: 42
  lora_scale: 0.35
  guidance_scale: 1.5
  num_inference_steps: 4
  base_model: stabilityai/stable-diffusion-xl-base-1.0
  lightning_lora: ByteDance/SDXL-Lightning
  lightning_weight: sdxl_lightning_4step_lora.safetensors
  taesd_vae: madebyollin/taesdxl

negative_prompt: >
  photograph, 3D render, anime, cartoon, digital art, signature, watermark, text,
  angel, wings, halo, saint, religious, crucifix, biblical, cherub

tracks:
  - name: tutorial
    label: "Tutorial fresco image"
    prompts:
      - slug: student-fresco-image
        text: "Italian fresco on aged plaster, warm chiaroscuro, visible brushwork, terracotta and ochre palette, <STUDENT_SUBJECT>"
```

Note: `validate_lora.py` expects the LoRA on the Modal `slow-interp-loras` volume. For the workshop flow, we use the HF Hub auto-download path in the full pipeline (Step 1b) but for the validation-grid step, the LoRA needs to be on the Modal volume. **Pre-flight check the volume** with `python -m cloud.volume_admin list`; if `casa-del-suono-sdxl-lora.safetensors` is not present, the student needs to either (a) download it locally with `hf download VRuins/casa-del-suono-sdxl-lora` then `modal run -m cloud.upload_weights --src models/loras`, or (b) skip Step 1a and proceed to Step 1b (which uses HF auto-download). Frame this choice to the student transparently if it surfaces.

Invoke the `modal` subagent for routing (validation is cheap; Modal almost always wins). Dispatch:

```bash
modal run -m cloud.validate_lora --config outputs/_tutorial/casa-del-suono-image.yaml --epoch 1
```

Wait for completion. Pull artifact:

```bash
modal volume get slow-interp-outputs validation/tutorial-casa-del-suono/epoch-1/student-fresco-image.png ./outputs/_tutorial/
```

Open the PNG for the student via the cross-platform helper:

```bash
python tools/open_output.py outputs/_tutorial/validation/tutorial-casa-del-suono/epoch-1/student-fresco-image.png
```

The helper dispatches the PNG to the OS default image viewer or browser. Then say:

> "Here's your fresco. Look at the surface: the way the colors sit on aged plaster, the chiaroscuro, the brushwork. That's the LoRA. The base model gave you the subject; the LoRA gave you the fresco-ness.
>
> Now we run the same subject as a 60-second looping video."

Write the partial completion marker (add `casa-del-suono-image` to `steps_completed`).

### Step 1b: Casa del Suono slow loop

Build a one-shot pipeline YAML in `outputs/_tutorial/casa-del-suono-loop.yaml` based on `examples/configs/tcole_valley.yaml`. Adapt:

- `style.lora_path`: `hf:VRuins/casa-del-suono-sdxl-lora`
- `style.lora_scale`: `0.35`
- `style.prefix`: `"Italian fresco on aged plaster, warm chiaroscuro, visible brushwork, terracotta and ochre palette, "`
- `style.negative_prompt`: `"angel, wings, halo, saint, religious, crucifix, biblical, cherub, photograph, 3D render, anime, cartoon, digital art, signature, watermark"`
- `subject.prompts`: A/B/C/A drift on the student's subject. Construct three variations along ONE atmosphere axis (typically light + time of day); keep composition and species locked. Example for a "garden at dusk" subject:
  - A: `"<student subject> at early evening, low warm light, dust catching the last rays"`
  - B: `"<student subject> at full evening, the colour just before dark, single window lit"`
  - C: `"<student subject> at twilight, blue hour, last edges of warmth"`
  - A (return): same as A.

Surface the three variations to the student before rendering so they can adjust if the atmosphere axis doesn't match their imagined scene.

Invoke the `modal` subagent for routing. For a 60-second loop, the workshop threshold (30 min) applies; Modal usually wins. Dispatch:

```bash
modal run -m cloud.entrypoint --config outputs/_tutorial/casa-del-suono-loop.yaml
```

Or local:

```bash
python -m slow_interpolation.run outputs/_tutorial/casa-del-suono-loop.yaml
```

Watch the agent's progress streams. On Modal, surface the dashboard URL. On local, surface phase milestones (Phase A keyframes, Phase A.5 smoother, Phase C RIFE, Phase D encode).

When the MP4 lands, open it for the student via the helper:

```bash
python tools/open_output.py outputs/casa-del-suono-loop.mp4
```

Then say:

> "Same subject as your fresco image, now alive. A few things to watch on first viewing:
>
> - The light drifts across the loop (your A to B to C atmospheres) but the composition holds. The surface stays painterly through every frame.
> - There are no cuts. The loop closes by drifting back to the starting frame at the end.
> - The brushwork persists frame to frame; that's the slow-evolving noise tensor doing its work. SDXL alone would flicker.
> - The motion is slow on purpose. The technique is built to let images behave like weather or memory, not like cinema."

Write `casa-del-suono-loop` into the completion marker.

## Step 2: Thomas Cole landscape

### Context to share with the student

> "Second LoRA: Thomas Cole. Cole (1801 to 1848) was the founder of the Hudson River School, an American romantic landscape painting movement of the mid-1800s. His vocabulary: vast wilderness, sweeping valleys, distant blue ridges, atmospheric light, occasional Roman aqueduct ruins as allegorical anchors, golden-hour skies, untouched nature as a kind of moral teacher. The painters he influenced (Asher Durand, Frederic Church, Albert Bierstadt, Thomas Moran) widened the scope to include the American West and the storm-light sublime. This LoRA learned from all of them.
>
> What Cole and the Hudson River School do well: scale, weather, light moving across geography, the sense that the land is older than the people in it.
>
> What they don't do: contemporary scenes, interiors, figures as the primary subject, abstraction.
>
> Imagine an evocative natural subject in their vocabulary. It does not have to be American or 19th century; the LoRA generalises. Some prompts to get you started:
>
> - 'a wide alpine valley at dawn with low mist over a river, distant blue mountains'
> - 'a forested coastline at sunset with a single cloudship breaking through the orange sky'
> - 'a vast canyon under a thunderstorm, distant rain visible, late afternoon'
> - 'a meadow at the edge of a forest in autumn, golden hour, scattered ruins suggesting time'
> - 'a high lake in the mountains, mirror-still, the moment before dawn'
>
> Tell me your subject in one or two sentences. Same as before, we'll do an image first, then a 60-second slow loop."

Wait for the student's response. Capture the subject verbatim.

### Brief technical context

> "This LoRA does use a trigger word (`tcole`). Your prompt becomes:
>
> `tcole, romantic landscape oil painting, Hudson River School style, <your subject>`
>
> Recommended scale is 0.75 (this LoRA is calibrated for moderate strength; Cole's atmospheric work needs room for the base model to handle scale and depth)."

### Step 2a: Cole landscape image

Build `outputs/_tutorial/cole-image.yaml` mirroring the Casa del Suono image YAML, but with:

- `family: tutorial-cole`
- `lora_filename_template: "thomas-cole-sdxl-lora.safetensors"`
- `render.lora_scale: 0.75`
- `negative_prompt`: drop the religious-bias suppressions (Cole's training data doesn't carry that risk); keep the generic anti-noise terms.
- The single prompt: `"tcole, romantic landscape oil painting, Hudson River School style, <STUDENT_SUBJECT>, oil on canvas, atmospheric perspective"`

Same volume-presence pre-flight as Step 1a (the Cole LoRA also needs to be on the Modal volume for `validate_lora.py`).

Dispatch via `modal run -m cloud.validate_lora --config outputs/_tutorial/cole-image.yaml --epoch 10`.

Pull the artifact and open it for the student:

```bash
python tools/open_output.py outputs/_tutorial/validation/tutorial-cole/epoch-10/student-cole-image.png
```

Then say:

> "Here's your Cole landscape. Look at how the light reads across the scene: the foreground detail, the middle ground softening, the distance dissolving into atmosphere. That's the Hudson River School handle on space. Cole and his contemporaries called it 'atmospheric perspective'; the LoRA picked it up from the training data."

Write `cole-image` into the completion marker.

### Step 2b: Cole slow loop

Build `outputs/_tutorial/cole-loop.yaml` based on `examples/configs/tcole_valley.yaml`. Adapt:

- `style.prefix`: `"tcole, romantic landscape oil painting, Hudson River School style, "`
- `style.lora_scale`: `0.75`
- `subject.prompts`: A/B/C/A drift on the student's natural subject. Light + time-of-day axis is canonical for Cole:
  - A: `"<student subject>, warm afternoon light, oil painting"`
  - B: `"<student subject>, golden hour light, oil painting"`
  - C: `"<student subject>, soft morning light with mist, oil painting, luminism"`
  - A (return): same as A.

Surface the three variations to the student. Note that this is the same A/B/C structure as the canonical `examples/configs/tcole_valley.yaml` (which the student can read later if curious about the worked example).

Invoke `modal` for routing. Dispatch:

```bash
modal run -m cloud.entrypoint --config outputs/_tutorial/cole-loop.yaml
```

When the MP4 lands, open it via the helper:

```bash
python tools/open_output.py outputs/cole-loop.mp4
```

Then say:

> "Your Cole slow loop. Compared to the Casa del Suono loop you made earlier, notice the differences:
>
> - The surface is different: oil-on-canvas, not oil-on-plaster. The brushwork is finer, the chroma cleaner.
> - The depth is different: Cole's atmospheric perspective makes the distance dissolve. The Casa del Suono LoRA tends to flatten into a fresco surface; this one opens it up.
> - The light drift reads differently. Cole's vocabulary makes the time-of-day axis feel narrative; the fresco vocabulary makes the same drift feel decorative.
>
> Same technique, same pipeline, two completely different LoRAs. That's the lever you have when you build your own."

Write `cole-loop` into the completion marker. Mark `completed_at` to the current UTC timestamp.

## Completion handoff

After all four sub-steps complete, open the tutorial outputs folder so the student can see everything together:

```bash
python tools/open_output.py outputs/_tutorial --folder
```

Then say:

> "Tutorial complete. You've now seen both demo LoRAs at both scales. The folder I just opened has all four files (two images, two videos) so you can flip between them. From here we can do a few different things:
>
> - **Iterate on either piece** (change subject, scale, atmosphere axis). Quick; minutes per render on Modal.
> - **Train your own LoRA** in a style you care about. Call the dataset-mosaic subagent; they walk you through the 5-phase curation protocol.
> - **Pick a different subject** for either LoRA and render at production scale (multiple A/B/C variations, longer loops, higher resolution). Call the lever subagent for per-render tuning.
> - **Experiment outside the tutorial vocabulary**. The two LoRAs ship as starting points, not prescriptions.
>
> What's next?"

Write the completion marker (final form):

```python
status = {
    "tutorial_version": "v0.1",
    "completed_at": "<UTC timestamp>",
    "steps_completed": [
        "casa-del-suono-image",
        "casa-del-suono-loop",
        "cole-image",
        "cole-loop",
    ],
    "student_casa_del_suono_subject": "<verbatim from step 1>",
    "student_cole_subject": "<verbatim from step 2>",
    "outputs": {
        "casa_del_suono_image": "<path>",
        "casa_del_suono_loop": "<path>",
        "cole_image": "<path>",
        "cole_loop": "<path>",
    },
}
status_path.parent.mkdir(parents=True, exist_ok=True)
status_path.write_text(json.dumps(status, indent=2))
```

Subsequent sessions read this file at start and skip the tutorial unless the student explicitly asks to re-run it.

## When to re-run the tutorial

If the student asks any of:

- "Run the tutorial again."
- "Let's go through the intro again."
- "I want to do the fresco / valley again from scratch."
- "Restart the tutorial."

Re-run from Step 1. The completion marker updates each time; the most recent run's details overwrite the previous ones.

If they want a partial re-run (e.g., just the Cole loop with a different subject), do that directly without rerunning the whole tutorial; the marker tracks the most recent subject choices.

## What this tutorial does NOT teach

The tutorial is a hand-off, not a curriculum. It does NOT cover:

- Training a new LoRA (call [`dataset-mosaic`](../.claude/agents/dataset-mosaic.md) and walk through the dataset-curation manual).
- Tuning per-render knobs in depth (call [`lever`](../.claude/agents/lever.md) when the student wants a specific aesthetic and needs the YAML adjusted).
- Building a Modal app (call [`modal`](../.claude/agents/modal.md) for any new cloud capability).
- Compositing multiple LoRAs (deferred to v0.2; not in scope for the workshop's first session).

When the student's question maps to one of those, hand off to the relevant subagent or manual page.

## Failure modes

| Symptom | Likely cause | Action |
|---|---|---|
| LoRA download fails | HF Hub network issue or wrong repo ref | Verify the repo URLs render: https://huggingface.co/VRuins/casa-del-suono-sdxl-lora and https://huggingface.co/VRuins/thomas-cole-sdxl-lora. |
| Casa del Suono `validate_lora` errors with "LoRA not on volume" | LoRA needs to be on Modal's `slow-interp-loras` volume for `validate_lora.py`; HF auto-download only works for the full pipeline (entrypoint.py) | Run `hf download VRuins/casa-del-suono-sdxl-lora casa-del-suono-sdxl-lora.safetensors --local-dir models/loras/` then `modal run -m cloud.upload_weights --src models/loras`. Re-dispatch. |
| Fresco prompt produces a generic image with no fresco quality | Descriptive prefix dropped or `lora_scale` too low | Confirm the prompt begins with the full `"Italian fresco on aged plaster, warm chiaroscuro, visible brushwork, terracotta and ochre palette,"` prefix. If still weak, bump `lora_scale` from 0.35 to 0.5. |
| Cole prompt produces a generic image with no painterly quality | Trigger word missing or `lora_scale` too low | Confirm the prompt starts with `tcole`. If still weak, bump `lora_scale` from 0.75 to 0.9. |
| Slow loop render produces flickering / strobing | Local-CUDA mismatch or stale HF cache | Have the student run `pip install -e . --upgrade-strategy only-if-needed` and retry. If still strobing, dispatch to Modal as a fallback (same config, no edits). |
| Student wants to skip Step 2 | Tutorial is two LoRAs; one is enough for a short session | Offer to mark `cole-image` and `cole-loop` as `skipped` in the completion marker. Surface that they can run Step 2 later by asking. |
| Student has no time for a full slow loop on either side | Loops are the long part | Offer to render at 30s instead of 60s (edit `frames.steady` and `frames.transition` down) or to skip the loops and only do the two images. |

## Cross-links

- [`workshop-kickoff.md`](workshop-kickoff.md) is the paste-able prompt students give their agent at session start. It auto-invokes this tutorial on first run.
- [`manual/modal-operations.md`](manual/modal-operations.md) is the modal subagent's operating manual including the workshop-context time thresholds and the OAuth-signup walkthrough.
- The Casa del Suono LoRA's model card: https://huggingface.co/VRuins/casa-del-suono-sdxl-lora.
- The Thomas Cole LoRA's model card: https://huggingface.co/VRuins/thomas-cole-sdxl-lora.
- `examples/configs/tcole_valley.yaml` is the canonical Cole worked example the loop step adapts.
