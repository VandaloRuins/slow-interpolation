# Next exploration steps

Read this only after the consolidation + port work is complete. It describes the four new directions Luca wants to take the pipeline once we have a clean, scripted core to extend.

These are not a strict order. They share infrastructure but each can be approached independently. The point of writing them down now is so we keep the consolidation focused and don't let the new ideas creep into the port.

## 1. Noise patterns as authoring surface

Right now the pipeline's only "noise" input is the small uniform Gaussian blend (0.08 inside steady segments, ramped 0.15 to 0.35 during transitions). That noise is doing more aesthetic work than its size suggests, because img2img re-encodes the previous frame through VAE and the noise is what allows the model to find a new local minimum each step.

The exploration is to make that noise an authoring surface, not just a hyperparameter.

**Things to try.**

- Structured noise sources: Perlin, Worley/cellular, simplex, FBM. Each has a different spatial frequency profile and will push the model toward different micro-behaviors.
- Image-derived noise: encode a still image through the VAE and use the resulting latent (or its high-frequency residual) as the noise tensor.
- Video-derived noise: same idea, but the noise tensor changes per frame from a source clip.
- Frequency-banded noise: apply different noise in different spatial frequency bands so coarse motion and fine motion can be controlled independently.

**What we are looking for.**

- New visual registers (e.g. impressionist-broken vs. fresco-smooth) emerging from noise choice alone, holding everything else constant.
- A reliable way to use noise to suggest a *secondary* subject without invoking it in the prompt (the depth-noise exploration in section 3 below is a special case of this).

**Deliverable.** A `noise/` module with a `NoiseSource` interface, and a comparison harness that renders the same A/B/C subject across 5+ noise sources and writes a contact sheet.

## 2. Webcam depth as noise (live)

The first move from offline rendering into a live, embodied loop. The body in front of the camera becomes the spatial structure of the noise.

**Pipeline sketch.**

- Webcam frame at 30 fps.
- Depth estimator on each frame (Depth-Anything v2, ZoeDepth, or MiDaS DPT depending on latency vs. quality on the studio GPU).
- The depth map becomes the spatial structure of the per-frame noise tensor: noise variance is scaled by depth, or noise is warped by depth, or noise statistics differ between near and far regions.
- A realtime sampler (StreamDiffusion is the obvious backbone) runs SDXL Lightning img2img with the previous output as the source and the depth-modulated noise as the perturbation.

**Critical concerns.**

- Latency budget: end-to-end (webcam to display) must stay under ~200 ms to feel embodied. This bounds the depth model choice.
- Temporal stability: depth jitter must not become flicker. Heavy temporal smoothing on the depth tensor before it enters the noise path.
- VRAM: SDXL Lightning + depth model + StreamDiffusion may need int8 or fp16 weight loading and a careful sequential dispatch.

**Deliverable.** `live/depth_as_noise.py` that runs at sub-second-per-frame on the studio machine and produces a coherent drifting image driven by the body in front of the camera.

## 3. Dual-prompt, dual-noise compositing

Two prompts living in one frame at the same time. One is the background world. The other is the depth-tracked subject who enters that world.

**Pipeline sketch.**

- Two parallel diffusion paths each step:
  - Path A: prompt A ("an Italian valley at dusk") with its own noise source, generates the background latent.
  - Path B: prompt B ("a figure of bone and brass") with a depth-mask-shaped noise source, generates the subject latent only where the depth signal puts the viewer.
- Compose at each step (latent space, not pixel space), with the depth mask as the alpha. Optionally feather the mask in latent space so the subject blends rather than collages.

**Conceptual reading.**

This is the move where the technique stops being landscape painting and starts being theater. The viewer authors the subject layer by standing in front of the camera. The background was already there. The viewer is the figure walking into the painting.

**Critical concerns.**

- The two paths must share enough state (timestep, scheduler) to produce coherent global lighting. The mask is spatial, but the composition is shared.
- Subject prompt drift over time: probably yes (section 4 below applies).
- Identifying "subject" reliably: depth alone is rough. We may want depth + segmentation (e.g. Sapiens segmentation, MediaPipe) for a tighter alpha.

**Deliverable.** `compositing/dual_layer.py` that takes two prompts, a webcam feed, and a depth/segmentation source, and produces a live composited drift.

## 4. Anchored live prompting

The performer types prompts during the live session. The scene slowly evolves toward what they type. But certain landmarks survive: the horizon, the silhouette of a mountain, the position of a window. The world drifts; the bones of the world stay.

**Mechanism candidates.**

- **Blended embeddings.** Hold a base prompt embedding at low weight and let the live prompt drift on top. The base contributes structural cues without dominating.
- **Img2img feedback from an anchor frame.** Mix the previous output with a frozen "landmark frame" at every step at low strength (5 to 10%). The anchor pulls the image back toward itself enough to preserve large-scale structure, but the live prompt has authority over everything else.
- **Latent anchor.** Maintain an "anchor latent" that drifts slowly toward the live prompt's mean. The current frame is steered by both the anchor and the live prompt.
- **ControlNet from a static reference.** A Canny or depth map of the landmark, kept fixed, fed in as a ControlNet condition at low strength.

These are not mutually exclusive. The likely winning approach is some combination, with the *weights* of each contribution exposed as performance controls.

**Performance interface.**

- Prompt typing surface (live).
- Slider 1: drift speed (how fast the prompt embedding moves).
- Slider 2: anchor strength (how much the landmark survives).
- Slider 3: maybe noise blend amount.

The interface should be minimal, opinionated, and fast. This is a performer-facing tool.

**Deliverable.** A working live-session tool that can sustain a 20+ minute performance arc with a coherent visual identity that evolves from prompt to prompt without resetting.

## 5. Alternative diffusion / interpolation backbones

Captured 2026-05-18 during a Renoir + Soutine sanity check. Three backbone alternatives to the current SDXL Lightning + img2img + RIFE 64x stack:

- FLUX backbone with retrained LoRAs (texture preservation upgrade).
- AnimateDiff with the existing style LoRAs (native temporal coherence instead of RIFE interpolation).
- Per-region RIFE composite (figure at 16x, surround at 64x, encode-stage composite) to deliver the frenetic-Soutine vs glacial-Renoir speed contrast the compositing design currently cannot.

Full framing, costs, comparison-render specs, and promotion criteria live in the alt-techniques brainstorm (maintainer's private planning folder during v0.1; surfaces in v0.2 if any of the three techniques promotes). Per-region RIFE is the cheapest and should be tested first; AnimateDiff is a half-day comparison before release lock; FLUX retrain is post-release v2 territory.

## Cross-cutting concerns

These thread through all four explorations.

- **Latency.** Section 2 onward needs realtime. The offline pipeline (SDXL Lightning 4-step + 64x RIFE) is too slow; we will probably skip RIFE in the live path and rely on the diffusion process to produce 24 to 30 generated frames per second.
- **Backbone library.** StreamDiffusion is a strong candidate for the live work. Investigate first whether its SDXL support is mature enough or if we'd be better off building on raw `diffusers` with manual KV caching.
- **Composability.** The exploration document is more important than the artifacts that come out of it. We should write up findings (what each noise type does, where depth-as-noise fails, what anchored prompting feels like in practice) as we go, in `docs/findings/`.
- **What gets released.** The release content is produced by the *offline* pipeline (Phase 3 of the roadmap); which style and subject carry it is still under exploration. The live work is a separate output, probably destined for performance or installation contexts. Do not let live ambitions slow the release.
