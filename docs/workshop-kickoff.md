# Workshop kickoff prompt

This page exists for one purpose: to be **pasted into an AI agent chat by a workshop student** so the agent can orient itself and start operating the `slow-interpolation` repo on the student's behalf.

The repo is built for an unusual interaction: the human does not read the operational docs directly. The human reads the [README](../README.md), decides what they want to make, and then hands the work to an AI agent (Claude Code, Cursor, Antigravity, whatever they use). The agent reads the manual pages and the findings tree, calls the four subagents when relevant, and walks the human through the work step by step.

This kickoff prompt is the bridge.

## How a student uses this page

The order matters. Doing these steps out of order is the most common failure mode at the workshop: the agent starts hunting the student's whole computer for a repo that isn't there yet, burning their free-tier tokens.

1. **Clone the repo to your computer** (or download the ZIP from the GitHub page and unzip it):
   `git clone https://github.com/VandaloRuins/slow-interpolation`
2. **Open your AI agent** (Antigravity, Codex, Claude Code, Cursor) and use **File > Open Folder** to open the cloned `slow-interpolation` folder.
   Note: opening a folder usually starts a fresh conversation in the agent. That is expected and correct. The kickoff prompt below is designed to be the first thing you say in that fresh conversation.
3. **In that fresh conversation, paste the kickoff prompt below as your first message.**
4. The agent reads the listed entry points, summarises what it can do, and asks the student what they want to make.

That is the whole workflow. The student does not need to read [`docs/manual/`](manual/), [`docs/findings/`](findings/), or `.claude/agents/` themselves; the agent does that.

## The paste-able kickoff prompt

```
You are an AI agent helping me operate the slow-interpolation repo on my behalf. The repo is a diffusion-based pipeline for slow, painterly looped video, designed so that I (the human) delegate the operational work to you (the agent) while I make the artistic decisions.

FIRST CHECK before reading anything else: try to read README.md from your current working directory. If it does not exist, or if its first lines do not mention "slow-interpolation", STOP IMMEDIATELY. Do not search the filesystem. Do not guess where the repo might be. Do not run find / dir / Get-ChildItem to hunt for it. Reply only with this message and then stop:

"I cannot see the slow-interpolation repo from this conversation. Please do these three steps:
1. Clone the repo: git clone https://github.com/VandaloRuins/slow-interpolation  (or download the ZIP from https://github.com/VandaloRuins/slow-interpolation and unzip it).
2. Open the cloned slow-interpolation folder in your agent. In Antigravity / Codex / Claude Code / Cursor this is File > Open Folder. This will usually start a fresh conversation without our current context. That is expected and correct.
3. In that new conversation, paste this kickoff prompt again as your first message."

Do not do anything else until I confirm I am in the cloned folder. Burning my tokens to hunt the filesystem is the failure mode this guard exists to prevent.

Once README.md is readable from the current directory, please read these entry points in order:

1. README.md (repo root): what the project is, the quickstart, the v0.1 status.
2. AGENTS.md (repo root): the agent-facing entry point. Read the "Documentation audience convention", "Scan the manual before improvising", and "The four subagents" sections in particular.
3. docs/README.md: the map of the docs tree.
4. docs/manual/index.md: the "Available protocols" dispatcher. This is the authoritative list of what you (the agent) know how to do without improvising.
5. .claude/agents/: the four capability-domain subagents (modal, dataset-mosaic, lever, docs-curator). You invoke them via the Agent tool when a task matches their domain.
6. docs/context.md: project background + the artist's framing.

Then read CLAUDE.md (repo root) for the conventions and natural-language invocation map.

If a CLAUDE.local.md sidecar exists, it is the maintainer's local-only notes and is not part of this workshop's repo state; ignore it.

Once you have read those, check the tutorial-completion marker at `~/.cache/slow-interpolation/tutorial-status.json`. If it does NOT exist OR does not show both `casa-del-suono-fresco` and `cole-valley` in its `steps_completed` array, this is my first session and I should run the first-runs tutorial at [`docs/tutorial-first-runs.md`](tutorial-first-runs.md). The tutorial walks me through one Casa del Suono fresco image (single PNG, my subject choice) and one Thomas Cole slow loop (60s video, the canonical reference). Roughly 5 minutes total on Modal, 25 to 40 minutes locally. Propose the tutorial to me; if I accept, follow the tutorial doc step by step. If the marker shows the tutorial is already complete, skip it.

Then do three things:

1. Tell me in 3 to 5 sentences what this repo does, what is shipping in v0.1 vs v0.2, and what you (the agent) can do for me.
2. List the four subagents and what each is for.
3. Ask me what I want to make today. Common starting points:
   - "Render the Thomas Cole valley reference clip to confirm my install works" (the quickstart path).
   - "Build a dataset for a new LoRA on subject X" (invokes dataset-mosaic).
   - "Train a LoRA on Modal with a dataset I already have" (dataset-mosaic + modal).
   - "Validate a LoRA I already trained" (dataset-mosaic).
   - "Render a clip with the Renoir / Casa del Suono / Thomas Cole LoRA from HuggingFace Hub" (modal + lever).
   - "Tune the noise / RIFE / lora_scale for a specific render I have in mind" (lever).
   - "I want to extend the technique with my own experiment" (you walk me through CONTRIBUTING.md and we open a PR back).

Do not start any of these before I confirm which one I want. Do not improvise outside the documented protocols; if I ask for something that has no matching protocol, surface that and we will decide together whether to build a new one or adapt an existing one. If a task involves Modal cloud GPU, invoke the modal subagent for routing (it knows when local is cheaper); if a task involves dataset work, invoke dataset-mosaic; if it involves per-render tuning, invoke lever; if it involves documentation health, invoke docs-curator.

A few conventions to inherit:
- No em dashes in any output. Use commas, periods, or "to" for ranges.
- Terse responses. Strong opinions with named trade-offs. No premature abstractions.
- Pause and ask me before destructive operations (mass deletes, force-push, dropping LoRAs).
- For LoRA weights: the demo LoRAs (Thomas Cole, and in v0.2 also Casa del Suono fresco, Renoir flowers, Soutine figures) live on HuggingFace Hub under the maintainer's account; the quickstart auto-downloads via the HF cache.
- For render hardware: before dispatching any render, invoke the modal subagent for a routing recommendation. Apply workshop-context attention-budget thresholds: if local would take more than 5 minutes for an image or 30 minutes for a video, push to Modal even when local is technically possible. The modal subagent surfaces both numbers (local wall + free, Modal wall + cost) and recommends. Modal Starter is free with $30/month of compute credit (GitHub or Google OAuth signup; Modal asks for a card on file at signup as identity verification, it is not charged unless I explicitly upgrade); at the measured $0.046 per 60s loop on L40S, that covers about 650 loops per month.
- If I do not have a Modal account, the modal subagent walks me through OAuth signup at https://modal.com/signup using whichever browser-control capability you have (Playwright MCP for Claude Code, equivalent for Cursor / Antigravity / Continue). Default behaviour: the agent stops at the OAuth form + ToS checkbox and lets me complete auth myself. If I'd rather you do it (paste credentials + accept ToS), say so when you ask and you'll escalate with my per-session consent. Never retain credentials across sessions. Full procedure in `docs/manual/modal-operations.md` "Modal account-setup walkthrough".

Begin by reading the entry points and producing the three-part briefing above.
```

## What this prompt is doing

The structure is deliberate:

- **Reading order** that hands the agent the agent-facing-docs convention before anything else, so the agent doesn't accidentally over-engineer or improvise.
- **Pointer to the four subagents** so the agent knows it has specialists available rather than implementing capabilities from scratch.
- **Concrete starting-point list** with each tied to the subagent it invokes. This is the workshop's discovery surface; a student who does not know what is possible reads the list and picks one.
- **Behavioural conventions** named explicitly so the agent inherits the project's working style without re-deriving.
- **Anchored to the v0.1 / v0.2 split** so the agent knows which LoRAs are public on HF Hub today vs which ones land later.
- **A pause-before-act instruction** so the agent confirms with the student before starting work, which matches the prompt-library framing the docs use throughout.

## Variants

Workshop facilitators may want to tailor the prompt. Common variants:

- **Workshop-specific subject focus**: append "Today's workshop focuses on X. If I ask for an arbitrary subject, suggest X instead unless I push back." Useful for a session targeting a specific domain.
- **Time-bounded session**: append "We have N hours. Recommend a starting point that is achievable in that window and surface time estimates as we work." Useful for short workshops.
- **Pre-trained LoRA shortcut**: append "Skip the dataset-curation track unless I explicitly ask for it. Default to rendering with the published LoRAs from HuggingFace Hub." Useful for non-training-focused workshops.

Keep the variant short. The base prompt above is already calibrated; appended text should only narrow the scope.

## What this prompt is NOT

- Not a substitute for the agent reading [`docs/manual/`](manual/) and [`docs/findings/`](findings/). The prompt only orients the agent; the docs are the operational substrate.
- Not a guarantee that an agent will handle every request well. Counter-findings are welcome ([`CONTRIBUTING.md`](../CONTRIBUTING.md) shape 4).
- Not the only way to use the repo. A more experienced user can skip this prompt entirely and address the agent directly per [`AGENTS.md`](../AGENTS.md).

## When to update this prompt

When any of the following change:

- The four subagents (new agent added, capability boundary moved).
- The set of published LoRAs (new family ships on HF Hub).
- The v0.1 / v0.2 split (a deferred capability promotes).
- The set of natural-language invocations in `CLAUDE.md` if a new entry point becomes common.

Treat the kickoff prompt as a versioned artifact. Workshop facilitators using a previous variant should be told when a new one supersedes it.
