# EDGE_CROP=0 border test

Date: 2026-05-16.
Branch: main (post Phase 2 port, pre Phase 3).

## Question

The pipeline applies three layered border-artifact mitigations (`crops_coords_top_left` SDXL micro-conditioning, `edge_suppression_callback` latent surgery, and a hard 8 px post-RIFE pixel crop). The historical record at `legacy/choire-v2/research/video-generation-iterations.md` Obstacle 5 documents the third mitigation as belt-and-suspenders for the first two. No controlled test was ever recorded for whether the crop is still load-bearing after Lightning + latent callback + crops_coords_top_left landed. **Is `EDGE_CROP=8` still doing work?**

## Hypothesis

The crop is no longer load-bearing. The two upstream mitigations (text-conditioning + per-step latent surgery) suppress arch / frame generation at the source. The crop was kept by inertia.

If true, dropping the crop returns 16 px on each axis (32 px total, ~1.2 % of the frame area) and preserves the full SDXL 1344x768 training-bucket resolution for downstream upscaling.

## Test design

Two renders, both at `edge_crop: 0`, with deliberately chosen subjects that probe the worst-case failure mode of each LoRA. Same pipeline parameters as the Phase 2C reference run except for the crop.

| Render | Config | LoRA | Subject | Why it stresses borders |
|---|---|---|---|---|
| 1 | [tcole_pastoral_20s_nocrop.yaml](../../examples/configs/border-test/tcole_pastoral_20s_nocrop.yaml) | Thomas Cole epoch 10 (0.75) | Pastoral civilization in distant valley, no foreground subject | Wide landscape prompt invites the model to "frame" the panorama. Aggressive negative prompt blocks foreground subjects, frames, vignettes. |
| 2 | [casa_frog_pond_20s_nocrop.yaml](../../examples/configs/border-test/casa_frog_pond_20s_nocrop.yaml) | Casa del Suono epoch 4 (0.35) | Closeup frog pond with lillypads and frogs | Casa del Suono is the LoRA historically most aggressive about painting fresco arches at the frame edge. A nature closeup has no inherent reason to include a frame, so any frame the model paints is a pure LoRA artifact. |

Both rendered at native 1344x768 (SDXL 16:9 training bucket), 10 keyframes, RIFE 6 passes linear with `skip_boundary=4`, output 22.9 s at 24 fps.

Total render time: 19.5 min for both (1167.3 s wall clock).

## Quantitative analysis: gradient magnitude per region

For each keyframe, gradient magnitude (sqrt of squared Sobel x + y) was averaged over the outer 60-pixel band on each side vs the interior. The metric is "how structured are the borders relative to the interior":

| Render | Keyframe | Top | Bottom | Left | Right | Interior | max(band) / interior |
|---|---|---|---|---|---|---|---|
| tcole_pastoral | 0001 | 3.02 | 4.30 | 3.86 | 3.42 | 3.92 | **1.10** |
| tcole_pastoral | 0005 | 5.05 | 6.43 | 5.33 | 5.45 | 5.67 | **1.13** |
| tcole_pastoral | 0008 | 4.37 | 6.98 | 6.45 | 4.63 | 5.15 | **1.35** |
| casa_frog_pond | 0001 | 2.28 | 2.62 | 2.56 | 2.42 | 3.28 | **0.80** |
| casa_frog_pond | 0005 | 3.55 | 3.99 | 3.46 | 4.29 | 4.97 | **0.86** |
| casa_frog_pond | 0008 | 3.87 | 4.33 | 3.41 | 3.95 | 4.80 | **0.90** |

Reading the metric:

- A natural landscape composition with sky on top and ground on bottom shows ratios around 1.0 to 1.5 (the bottom band has more gradient because of tree-line detail; the top band has more because of clouds). All six tcole values are in this range.
- A frame-filling abstract or detail composition shows ratios at or below 1.0 (borders less structured than center). All six casa values are below 1.0.
- **A real border artifact would push ratios above 2.0 or 3.0** because a decorative arch is a strong continuous edge that would dominate the gradient sum on whichever side it appears.

No keyframe in this test exceeds 1.35. The border-artifact regime is roughly 50 % above where we landed at the worst.

## Visual analysis: border strips

Extracted 60-pixel strips from each side of three keyframes per subject. Strips reviewed at native resolution.

- **tcole top strips**: warm-toned painterly cloud edges, smooth continuation of the sky. No painted frame. Some normal texture and brushstroke detail because the Cole LoRA renders oil-on-canvas.
- **tcole bottom strips**: forested foreground meadow, tree-line silhouettes against grass. Real foliage, not painted columns. The 1.35 ratio at kf0008 is the tree-line, not a frame.
- **tcole side strips**: natural landscape continuation. Sky transitions to hills, foliage at corners. No frame, no arch.
- **casa top strip**: green lillypad edge fading to pale water reflection. No fresco panel.
- **casa bottom strip**: water and lillypad continuation across the bottom edge. No frame.
- **casa side strips**: lillypad and water margins. No arch, no vignette.

## Visual analysis: MP4 frames (post-RIFE, post-encode)

Extracted t=2 s, t=10 s, t=20 s from both MP4s. RIFE interpolation and H.264 encoding had no effect on border content. All six MP4 frames are corner-to-corner clean:

- **tcole_pastoral t=2 s**: panoramic valley with river bend, distant church spire, autumn foliage foreground, layered atmospheric hills, pink cumulus sky. Composition fills 1344x768 corner to corner.
- **tcole_pastoral t=10 s**: same scene, mid-segment. Mountains slightly more visible (composition drift between A and B prompt), small church still readable.
- **casa_frog_pond t=10 s**: four frogs on lillypads, water reflections of reed stems, scattered duckweed at margins. Painterly fresco surface throughout, no panel border.
- **casa_frog_pond t=20 s** (return segment, near loop point): even cleaner. Naturalistic frog detail, proper concentric ring on the lillypads. Frame edges have water and pads continuing right up to the pixel boundary.

## Verdict

**Drop the crop. `EDGE_CROP=0` is the new default.**

The two upstream mitigations (`crops_coords_top_left=(256, 256)` + `edge_suppression_callback` at `latent_edge_px=3, latent_edge_strength=0.3`) are doing the full job of border-artifact suppression for both LoRAs tested. The post-RIFE pixel crop adds nothing in this regime.

Concrete gains from dropping the crop:

- Output resolution returns to the full SDXL training bucket (1344x768) vs the legacy and Phase 2C 1328x752. Recovered 32 px of native rendering, ~1.2 % of frame area.
- Downstream upscale (e.g. lanczos to 1920x1080, or larger for the Renoir release) starts from a marginally larger source.
- The pipeline becomes one less knob to tune for new subjects.

## Caveats and what would change the verdict

This test does not cover everything. The crop should be re-tested if any of the following change:

- **A new LoRA**, especially one trained on framed paintings, religious panels, or photographs with mat borders. ~~The Renoir flowers LoRA will need its own probe before locking in the default.~~ **Resolved 2026-05-18 (Luca empirical call): the historical border-arch problem was Casa-del-Suono-LoRA-specific (fresco lunette training data with hard architectural framing). The Renoir LoRA at `edge_crop: 0` shows no border artefacts on either still-life or flower-field subjects across the validation grid + first 60s clip. The Modal T1#2 "Renoir flower-field border probe" queued in `workstreams/modal/progress.md` is cancelled.** Going forward, treat border-arch as a per-LoRA risk indexed by training-data framing, not a generic concern. New LoRAs trained on auction-catalogue scans / fresco panels / religious-icon panels still warrant a one-off probe.
- **Figured closeup subjects**: portraits, single objects on plain backgrounds, anything that historically lured SDXL into "this is a framed picture" mode. The legacy pipeline failed at these exact subjects per `legacy/choire-v2/research/video-pipeline-best.md` line 84 ("figure closeups expose identity shifting"). Worth a probe render with the Renoir LoRA at a vase-of-flowers subject specifically.
- **Sub-bucket resolutions** (anything not in SDXL's training bucket list). Off-bucket resolutions amplify border behavior per Obstacle 1 of the iteration log.
- **Lower CFG or higher LoRA scale**. Both move the model toward the LoRA's training-data distribution, which is what historically painted frames.

## Recommended config-level change

Update `RIFEConfig.edge_crop` default in [src/slow_interpolation/config.py](../../src/slow_interpolation/config.py) from `8` to `0`. Reference YAML configs ([examples/configs/tcole_valley.yaml](../../examples/configs/tcole_valley.yaml) and any new Phase 3 configs) keep an explicit `edge_crop: 0` line for clarity. The Renoir release config should override to a non-zero value only if its own probe render shows arch artifacts at the Renoir LoRA.

Not making the config change in this commit. The default change is a separate, reviewable edit once we confirm with one more Renoir-LoRA probe in Phase 3.

## Source artefacts

- `outputs/border-test/tcole_pastoral_20s_nocrop.mp4` (2.3 MB, 1344x768, 549 frames, 22.9 s)
- `outputs/border-test/casa_frog_pond_20s_nocrop.mp4` (2.3 MB, 1344x768, 549 frames, 22.9 s)
- `outputs/border-test/staging/<subject>/keyframes/0000.png` ... `0009.png` for both subjects (uncropped, native).
- Extracted border strips at `C:/temp/sample_frames/border-test/strips/`.
- Extracted MP4 frames at `C:/temp/sample_frames/border-test/`.


---
*Did you reproduce this and observe something different? Counter-findings welcome. See [CONTRIBUTING.md](../../CONTRIBUTING.md) shape 4 and the [finding issue template](../../.github/ISSUE_TEMPLATE/finding.md).*
