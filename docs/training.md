# Modal LoRA training (pointer)

> **This page is a pointer.** It used to be a 344-line conceptual overview; it was trimmed 2026-05-18 to avoid duplicating [`manual/train-lora-on-modal.md`](manual/train-lora-on-modal.md). All content moved or was retired.

The canonical agent-facing operational protocol for training SDXL LoRAs on Modal is at:

- [`docs/manual/train-lora-on-modal.md`](manual/train-lora-on-modal.md)

Status: Modal is the canonical training path for this repo since 2026-05-18. The CivitAI worked example for the Renoir LoRA is preserved at [`docs/findings/lora-training.md`](findings/lora-training.md) as Renoir-specific notes; for any new domain LoRA, follow the Modal protocol.

For the artist-side reference (mission, technique, release context), see:

- [`docs/technique.md`](technique.md)
- [`docs/context.md`](context.md)
- [`README.md`](../README.md)

For the cold-run validation report and exit criteria, see the Modal-trainer workstream log (kept in the maintainer's private planning folder during the v0.1 ramp-up; will surface publicly in v0.2 alongside the LoRA art release).

This file will be deleted at Phase D3 once external link discovery confirms no inbound references.
