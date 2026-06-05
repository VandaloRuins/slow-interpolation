# slow-interpolation

A diffusion-based pipeline for slow, painterly looped video, AND an experiment in agent-driven open-source practice.

<p align="center">
  <video src="examples/outputs/E14_lake_horizontal.mp4" controls width="720" loop autoplay muted>
    Your browser does not support inline video. The hero clip lives at
    <a href="examples/outputs/E14_lake_horizontal.mp4">examples/outputs/E14_lake_horizontal.mp4</a>.
  </video>
</p>

*Above: a 60s loop rendered with the Casa del Suono fresco LoRA. The technique allows generative video to behave like weather or memory, not like cinema.*

## What this is

**The technique.** SDXL Lightning generates keyframes through an img2img chain with a slowly-evolving noise tensor. A frequency-separated smoother strips inter-frame jitter without ghosting. RIFE v4.25 interpolates 64x at a linear timestep with a wrap-around pass so motion is glacial and the loop closes without a cut. The full pipeline is at [`src/slow_interpolation/`](src/slow_interpolation/); the parameter spec is at [`docs/pipeline.md`](docs/pipeline.md); the artistic framing is at [`docs/technique.md`](docs/technique.md).

**The open-source experiment.** Every operational protocol in this repo is written for an AI agent that a human user delegates to. The repo ships four capability-domain subagents at [`.claude/agents/`](.claude/agents/) (Modal cloud infra, dataset curation, render tuning, docs curation), an agent-facing manual at [`docs/manual/`](docs/manual/), and a findings tree at [`docs/findings/`](docs/findings/) for the research that informed every decision. The hypothesis: a small repo that ships its operational knowledge as a prompt library can compound through forks faster than one that ships only code.

## Quickstart

```bash
git clone https://github.com/VandaloRuins/slow-interpolation.git
cd slow-interpolation
pip install -e .

# Render the canonical reference clip. First run auto-downloads:
#   - SDXL base + Lightning LoRA + TAESD VAE (~7 GB, one-time)
#   - The Thomas Cole demo LoRA from huggingface.co/VRuins/thomas-cole-sdxl-lora
#     (~228 MB, one-time, the YAML uses hf:VRuins/thomas-cole-sdxl-lora)
python -m slow_interpolation.run examples/configs/tcole_valley.yaml
# -> outputs/tcole_valley.mp4 (1328x752, 24 fps, ~60 s, ~7 MB)

# Open the result in the OS default player / browser:
python tools/open_output.py outputs/tcole_valley.mp4
```

CUDA GPU with 8 GB+ VRAM required for keyframe generation. Subsequent runs reuse the HuggingFace cache so they skip the ~7 GB download. A full walk-through is in [`docs/manual/getting-started.md`](docs/manual/getting-started.md); the LoRA model card with sample renders + training-data attribution is at [huggingface.co/VRuins/thomas-cole-sdxl-lora](https://huggingface.co/VRuins/thomas-cole-sdxl-lora).

## Run on cloud GPU

```bash
pip install -e .[cloud]
modal token new
modal run -m cloud.upload_weights --src models/loras
modal run -m cloud.entrypoint --config examples/configs/tcole_valley.yaml
```

L40S costs roughly 0.07 USD per 60s render. The `modal` subagent at [`.claude/agents/modal.md`](.claude/agents/modal.md) handles the local-vs-cloud routing decision automatically (with cost-vs-time awareness); the operational manual is at [`docs/manual/modal-operations.md`](docs/manual/modal-operations.md).

## What's here

| Path | What |
|---|---|
| [`src/slow_interpolation/`](src/slow_interpolation/) | The pipeline. `Pipeline.render()` is the entry point; `python -m slow_interpolation.run <config.yaml>` is the CLI. |
| [`cloud/`](cloud/) | Optional Modal cloud deployment (renderer, trainer, validator, batch, smoke, volume admin). Not imported by the base package. |
| [`.claude/agents/`](.claude/agents/) | Four capability-domain subagents: `modal`, `dataset-mosaic`, `lever`, `docs-curator`. Any chat invokes them via the Agent tool. |
| [`docs/manual/`](docs/manual/) | Agent-facing operational protocols (dataset curation, gallery review, LoRA training on Modal, validation, render tuning, noise picking, hardware routing). |
| [`docs/findings/`](docs/findings/) | Distilled lessons from completed experiments. One claim, evidence, numbers, caveat per file. |
| [`examples/configs/`](examples/configs/) | Reference YAML configs. `tcole_valley.yaml` is the canonical demo. |
| [`examples/outputs/`](examples/outputs/) | Sample MP4s from the technique's history. |
| [`datasets/renoir-flowers/`](datasets/renoir-flowers/) | Worked example of the 5-phase dataset-mosaic curation protocol (image bytes gitignored; scripts ship as the protocol's reference implementation). |
| [`vendor/rife_v425/`](vendor/rife_v425/) | Re-vendored RIFE v4.25 (MIT). |
| [`legacy/`](legacy/) | The two earlier projects this pipeline consolidated. Read-only reference. |
| [`docs/`](docs/) | All documentation. Start at [`docs/README.md`](docs/README.md). |

## v0.1 release status

- **Shipping in v0.1**: the pipeline, the dataset-mosaic protocol, the Modal integration (renderer + trainer + validator), the four subagents, the manual, the findings. The Thomas Cole demo LoRA is published on HuggingFace Hub and downloaded automatically by the quickstart.
- **Shipping in v0.2** (alongside the upcoming Renoir + Soutine art release): additional LoRAs (Casa del Suono fresco, Renoir flowers, Soutine figures), the compositing manual, the inpaint manual.

See [`docs/planning/progress.md`](docs/planning/progress.md) for the live decisions log.

## For AI agents and human contributors

This repo is meant to be forked, extended, and PR'd back into. **The documentation is written for AI agents.** This README is the only page for the human reader; everything under [`docs/`](docs/) is addressed to the AI agent you will delegate to. Hand the repo to an agent (Claude Code, Cursor, your tool of choice), point it at [`AGENTS.md`](AGENTS.md), and ask for what you want.

### Workshops: the paste-able kickoff prompt

If you are running a workshop with this repo, the orientation step is to have each student paste the **workshop kickoff prompt** at [`docs/workshop-kickoff.md`](docs/workshop-kickoff.md) as their first message to whichever AI agent they are using.

**Order matters.** A student must do these three steps in this order, or the agent will burn their free-tier tokens hunting their filesystem for a repo that is not there yet:

1. **Clone the repo first**: `git clone https://github.com/VandaloRuins/slow-interpolation` (or download the ZIP from the repo page and unzip it).
2. **Open the cloned folder in their agent** (Antigravity, Codex, Claude Code, Cursor) via File > Open Folder. Opening a folder usually starts a fresh conversation in the agent. That is expected and correct.
3. **In that fresh conversation, paste the kickoff prompt as the first message.** The prompt has a guard at the top that refuses to do anything if it cannot see the repo from the current directory, so a misordered paste fails loudly instead of burning tokens.

The prompt then orients the agent on the four subagents, the manual, and the v0.1 / v0.2 status, then asks the student what they want to make. Students never need to read the operational docs themselves; their agent does. Workshop facilitators can tailor the prompt per session (subject focus, time budget, dataset vs render emphasis); see the "Variants" section of the kickoff page.

### Forks and contributions

If your agent discovers a noise source that reads well on a new subject, a LoRA recipe that improves on the documented playbook, a compositing strategy that wasn't tried, or a finding that contradicts what is in [`docs/findings/`](docs/findings/), open a PR back. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the five contribution shapes (LoRA-domain finding, new noise source, compositing strategy, counter-finding, manual edit) and their templates.

## Author

Luca Martinelli (Vandalo Ruins). [vandalo.art](https://vandalo.art).

## License

MIT. See [`LICENSE`](LICENSE). RIFE v4.25 vendored under MIT at [`vendor/rife_v425/LICENSE`](vendor/rife_v425/LICENSE).
