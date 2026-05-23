# Upscale-source resolution: 1344x768 vs 1536x896

Date: 2026-05-18.
Branch: main (post-Modal infra, pre-Renoir-LoRA arrival).
Companion: [border-crop.md](border-crop.md) (parent decision EDGE_CROP=0).

## Question

Upscale-target releases sit above SDXL's training-bucket resolutions:

- 1920x1080 (16:9 HD): the standard delivery format for short-loop demonstrators and grant submissions.
- Renoir release: 2048x1152 or 4K (TBD with the release curator).

[planning/progress.md](../planning/progress.md) decision 2026-05-16
locks in: render at SDXL native 1344x768 (the 16:9 training bucket),
upscale to 1920x1080 with lanczos post-RIFE pre-encode. SDXL native
1920x1080 reintroduces border artifacts (Obstacle 1 of
`legacy/choire-v2/research/video-generation-iterations.md`).

But SDXL has a larger 16:9 training bucket too: **1536x896**. If border
behavior holds at 1536x896 with `edge_crop=0`, the upscale source
increases by 33 % (more pixels into the lanczos), the upscale ratio
to 1920x1080 drops from 1.43x to 1.25x, and the final reads sharper.
The Renoir upscale target inherits the same gain.

**Does 1536x896 stay clean at `edge_crop=0` on the Cole LoRA, the same
way 1344x768 did in the [border-crop.md](border-crop.md) probe?**

## Hypothesis

Yes. The two upstream mitigations (`crops_coords_top_left` SDXL
micro-conditioning + `edge_suppression_callback` latent surgery) are
resolution-relative, not absolute-pixel, so they scale with the larger
canvas. The increased frame area gives a tiny amount of extra room for
border-bias artifacts to manifest, but the bias itself is a function
of the text-conditioning + LoRA distribution, not of pixel count.

## Test design

Single render. Same Cole pastoral subject + negative prompt as
[examples/configs/border-test/tcole_pastoral_20s_nocrop.yaml](../../examples/configs/border-test/tcole_pastoral_20s_nocrop.yaml).
Only deltas: resolution 1344x768 to 1536x896, GPU L40S to A100-80GB
(larger VRAM headroom for the larger frame area).

Config: [examples/configs/border-test/tcole_pastoral_1536_a100.yaml](../../examples/configs/border-test/tcole_pastoral_1536_a100.yaml).
Output: `outputs/from-modal/border-test/tcole_pastoral_1536_a100.mp4`.

Modal render telemetry:

| Metric | Value |
|---|---|
| GPU | A100-80GB |
| Wall time | 78.8 s |
| Cost | 0.07 USD |
| Output resolution | 1536x896 |
| Output duration | 22.88 s |
| FPS | 24 |
| Codec | H.264 yuv420p |

## Verdict

**PASS. 1536x896 is clean. Use it as the new default source
resolution for upscale-target releases.**

Visual inspection (Luca, 2026-05-18):

- Border edges (top, bottom, sides): natural sky, hills, valley, tree
  line extending corner to corner. No decorative arch. No vignette.
  No painted frame.
- Composition framing: wide valley fills the canvas, distant village
  still tiny, the "tiny subject in deep distance" aesthetic preserved.
  Aspect change did not pull the subject to center.
- Loop closure: continuous color and light transition; no cut.
- Surface: oil-on-canvas painterly feel matches the Phase 2C and
  border-crop reference renders. No over-detailing from the larger
  canvas.

No artifacts beyond what 1344x768 already showed (none material).

## Implications for production

### 1920x1080 upscale target

- New default: render at 1536x896 native, lanczos upscale to 1920x1080.
- Upscale ratio drops from 1.43x to **1.25x**. Less interpolation,
  sharper final.
- Modal GPU bumps from L40S (1344x768) to A100-80GB (1536x896). Cost
  per 60s loop estimate: ~78 s * (60/22.88) ratio extrapolated = ~205 s
  on A100-80GB at $2.78/hr = **~$0.16 per 60s loop**. Still under the
  $5 ceiling by 30x.
- Any config targeting 1920x1080 should set `resolution: {1536, 896}`,
  `modal.gpu: A100-80GB`, `edge_crop: 0`.

### Renoir release (2048x1152 or 4K target)

- Inherits the same gain. Render at 1536x896, upscale to whatever
  the release curator locks in.
- One caveat: this probe used the Thomas Cole LoRA. **Renoir LoRA
  needs its own 1536x896 probe** before locking in the larger source
  for the release. Run alongside T1#2 (Renoir flower-field border
  probe) when the LoRA lands.

### Default for new configs

- Reference configs and templates still use 1344x768 (the
  conservative default that has been validated across more LoRAs).
- 1536x896 is the **opt-in upgrade for upscale targets**. Document it
  in `docs/modal.md` as a noted alternative once the first 1920x1080
  upscale-target config lands.

## Caveats and what would change the verdict

- **A new LoRA**, especially Renoir. Re-probe.
- **A second SDXL training bucket** (1216x832, 1216x1024, etc.) was
  not tested. 1536x896 is the only "larger than default" 16:9 bucket
  probed. Other buckets behave per their own training data
  distribution and would each need their own probe.
- **The render is 22.88 s, not 60 s.** The composition envelope reads
  the same across the segments, so loop length is not expected to
  affect the verdict, but a full-length 60 s Renoir-specific render
  should be the second confirmation before committing the release
  to 1536x896.
- **Single subject (pastoral landscape, distant subjects).** Foreground-
  heavy or close-up subjects were not tested at 1536x896.
  [border-crop.md](border-crop.md) Renoir caveat applies: vase-of-
  flowers closeups historically trigger "framed picture" mode. If the
  Renoir release includes any closeup subject, probe that subject at
  1536x896 specifically.

## Source artefacts

- [outputs/from-modal/border-test/tcole_pastoral_1536_a100.mp4](../../outputs/from-modal/border-test/tcole_pastoral_1536_a100.mp4)
  (1.5+ MB, 1536x896, 549 frames, 22.88 s)
- `outputs/from-modal/border-test/tcole_pastoral_1536_a100.manifest.json`
  (full run manifest with model SHAs, phase times, cost)
- Modal dashboard run: `ap-eG6Q8xTptjzwxzsP8JLvMd`
- Config: [examples/configs/border-test/tcole_pastoral_1536_a100.yaml](../../examples/configs/border-test/tcole_pastoral_1536_a100.yaml)

## What this finding feeds into

- [Modal workstream](../planning/workstreams/modal/progress.md) T3#11: closes the ticket. Marks the probe as PASSED in the followup-plan.
- Any 1920x1080-target config: should set 1536x896 + A100-80GB.
- Renoir release config template: candidate for the upgrade pending the Renoir-LoRA-specific re-probe (T1#2 companion).
- Parent chat [planning/progress.md](../planning/progress.md) decisions log: carries the 2026-05-18 entry "1536x896 + A100-80GB is the new source-resolution path for 1920x1080+ upscale targets".

---
*This finding was contributed via the Modal workstream during T3#11
execution. Future related findings: a Renoir-LoRA-specific 1536x896
re-probe will likely live at `findings/renoir-border-probe.md` after
T1#2 fires.*
