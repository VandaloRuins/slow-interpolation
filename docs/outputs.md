# Sample outputs

Annotated catalogue of every MP4 under [../examples/outputs/](../examples/outputs/). Each entry was inspected at a representative mid-clip frame (`ffmpeg -ss 30 -i <file> -frames:v 1`) and cross-checked against the relevant SUBJECT prompt in [../legacy/choire-v2/scripts/generate_horizontal.py](../legacy/choire-v2/scripts/generate_horizontal.py) or [../legacy/after-cole/generate_horizontal_tcole.py](../legacy/after-cole/generate_horizontal_tcole.py).

## Shared envelope

All 16 clips:

- **Codec:** H.264, yuv420p.
- **Resolution:** 1328 x 752. Confirms `EDGE_CROP=8` is applied (1344 - 16; 768 - 16).
- **Duration:** 59.54 s, 1429 frames at 24 fps.
- **Pipeline tag:** entry-point variant (horizontal, 5 / 3 / 4 / 3 frame counts, RIFE v4.25 64x linear, `skip_boundary=4`, skip-keyframes, RIFE wrap-around loop closure).

Bitrate varies 1.8x across the set (661 to 1189 kbps at the same `quality=5` libx264 setting). Bitrate here is an **aesthetic signal**: the encoder spends more bits on clips with sharper textures and higher frame-to-frame variation. Calm clips end up materially higher bitrate than their standard counterparts (e.g., `notturno_city_calm` 1133 vs standard 819 kbps; `harbour_market_calm` 1153 vs standard 803), because the calm profile turns off the pre-frame structural blur (`STRUCTURAL_DECAY_RADIUS=0`) and halves the noise blend, producing crisper frames that cost more to encode. This is a useful first-pass quality probe before opening anything.

## Choire v2 fresco horizontals

Italian fresco LoRA (Casa del Suono, scale 0.35), `STYLE_PREFIX = "Italian fresco on aged plaster, warm chiaroscuro, visible brushwork, terracotta and ochre palette, "`. Negative prompt blocks religious / angelic / nude imagery.

### The "calm" pair (the cleanest A/B in the set)

These are the four files that demonstrate the calm denoise profile as a pure aesthetic axis: same subject, same LoRA, same prompts; the only deltas are `STEADY_STRENGTHS` averaging ~0.51 vs ~0.575, transition strength 0.52 vs 0.65, steady noise 0.04 vs 0.08, transition noise 0.08 vs 0.15, `STRUCTURAL_DECAY_RADIUS` 0 vs 2, smoother `sigma` 1.8 vs 1.5. See [pipeline.md](pipeline.md) for the full delta table.

- **`harbour_market_horizontal.mp4`** (803 kbps, standard). Mediterranean fishing port in fresco palette. Mid-clip frame shows red-and-orange-sailed boats clustered before a sun-warmed harbour-front of pastel buildings, a small hill fortress in the middle distance, figures gathered on a stone quay. Reads as a single soft-focus oil-on-plaster painting. Masts and rigging blur into the building line. Atmospheric, less specific.

- **`harbour_market_horizontal_calm.mp4`** (1153 kbps, calm). Same harbour, same boats, but markedly more legible: discrete masts and rigging against a paler sky, individual sail folds, clearer architectural windows and tile rows on the harbour buildings, the figures on the quay readable as distinct silhouettes. The water reflection is crisper. Less haze, less drift, more "studio sketch" than "fresco fragment". This A/B is the single most informative pair in the set: it shows what the denoise schedule actually does to the work without changing anything else.

- **`notturno_city_horizontal.mp4`** (819 kbps, standard). Hilltop medieval city at dusk, slim crescent moon at top-left, amber sunset glow over the hills. Rooftops merge into a continuous terracotta mass; bell tower silhouettes are present but indistinct. Reads warm, ambient, smudged.

- **`notturno_city_horizontal_calm.mp4`** (1133 kbps, calm). The same city, transformed: a fully rendered full moon (not crescent), specific bell-tower and dome geometry, mountain ridges with separable peaks, individual rooftop tiles, distinct window arches. Sky has bands of amber to deep blue with painterly cloud strokes. The standard version reads as fresco patina; the calm version reads as a Romantic-period oil study. Both are valid; the calm direction may suit Renoir better because impressionist florals depend on surface specificity rather than ambient haze.

The recommendation buried in this A/B: the calm profile is not strictly "more painterly". It is **more representational**. The standard profile is what reads as fresco. The two profiles are aesthetic dialects, not quality grades. Treat them as named presets in the port.

### Other fresco horizontals

- **`E14_lake_horizontal.mp4`** (661 kbps, lowest in the set). A Tuscan lake at amber dawn: cypress-fronted villa on the right, two small fishing boats on glassy water with sharp building reflections, distant hills veiled in mist. The cypress-and-villa silhouette is one of the cleanest "still life landscape" frames in the catalogue and the cheapest to encode (huge low-frequency sky, smooth water). Demonstrates the pipeline working in its sweet spot: environmental subject, no figure closeup, slow color drift across A/B/C prompts.

- **`E24_garden_horizontal.mp4`** (698 kbps). Formal palace garden seen from a high window: ochre palace facade fills the upper half, fountain at center foreground, geometric box-hedge parterre. Static, symmetrical, almost diagrammatic. The pipeline holds the architecture rock-steady across the drift, which is what the prompt asks for. A useful counter-example to the more atmospheric clips: this one demonstrates the technique's ability to keep a strict perspective composition intact across A/B/C lighting changes.

- **`siege_harbour_horizontal.mp4`** (719 kbps). Roman harbour under attack: black smoke pillars, fires on the quayside, sailing vessels in silhouette across a glassy reflective harbour. The fresco LoRA pulls the fire and smoke toward a softer, more illustrative tone than the Cole-equivalent (`tcole_siege` below). The water reflection is luminous and ochre. This is one of two fresco subjects that explicitly invokes Thomas Cole in its prompt ("Thomas Cole painting style"), an early experiment that became the cross-pollination motif (see next two clips).

- **`cole_valley_horizontal.mp4`** (776 kbps, v1 cross-pollination test). Cole-style prompt (vast green valley with distant Roman aqueduct ruins) run through the **fresco LoRA**. The result is fresco-on-Cole: soft pastoral hills, scattered olive-like trees, a tiny village in the middle distance. The intended aqueduct ruins are absent at this mid-clip frame; the LoRA pulled toward generic Tuscan pastoral instead. Failure mode worth keeping: when prompt subject and LoRA training data disagree, the LoRA wins.

- **`cole_valley_horizontal_v2.mp4`** (675 kbps, v2). Same prompt re-run, now with the aqueduct clearly present in the foreground: golden-hour light raking across red brick arches, the village pushed to the middle distance, hill ruins in the upper left. v2 is the iteration that landed the subject. The improvement is composition-level, not pipeline-level (same parameters). Useful evidence that a stochastic re-roll on the same config can be the difference between subject-present and subject-absent at SDXL Lightning 4-step.

## After Cole (Hudson River School) horizontals

Thomas Cole SDXL LoRA (epoch 10 strong by default, scale 0.75), `STYLE_PREFIX = "tcole, romantic landscape oil painting, Hudson River School style, "`. Same pipeline structure as the fresco horizontals; only the style stack is swapped. This is the "minimum diff for a new style" demonstration that justifies the After Cole adapter pattern.

The palette and surface read distinctively differently from the fresco horizontals: deeper greens, naturalistic skies with structured cloud forms, oil-on-canvas surface (not plaster), sharper foliage detail, and the Hudson River School compositional cues (foreground tree as framing element, sweeping middle-ground diagonal, atmospheric mountain background).

- **`tcole_ruins_horizontal_test1.mp4`** (1111 kbps, second-highest in set). Classical temple ruins on a promontory: weathered Doric columns wreathed in greenery, a gnarled oak tree framing the left foreground, lake in the lower-left distance, jagged cliffs to the right. The "test1" tag dates this as an early subject calibration render; the clip is also the only sample without a v2, suggesting it was approved on the first pass. Compositionally the cleanest Cole-formula example in the catalogue: foreground tree + ruin block + atmospheric distance.

- **`tcole_valley_horizontal.mp4`** (1008 kbps, v1). A massive crumbling brick aqueduct fills the lower two thirds of the frame, golden hour raking along the brickwork. The prompt asks for a panoramic valley with **tiny ancient aqueduct ruins on the distant horizon**; this v1 renders the aqueduct as the dominant subject instead. The LoRA pulled toward its training-data center of mass.

- **`tcole_valley_horizontal_v2.mp4`** (869 kbps, v2). Same prompt, recomposed: now the aqueduct is in the middle distance at appropriate scale, mountain peaks behind it, structured cloud bank above, an actual rolling green valley filling the foreground. The corrected reading. The v1/v2 pair captures the practical problem with strong style LoRAs: they have an opinion about scale and you sometimes have to re-roll until prompt scale survives the LoRA's preference.

- **`tcole_cloudship_horizontal.mp4`** (832 kbps, v1). A galleon on a green hillock between mountains, dramatic late-afternoon cumulus stack above, lake at the bottom edge with a small boat. The galleon is grounded, not airborne; the prompt's conceit ("ship resting on clouds like an ocean") did not survive SDXL Lightning 4-step. The LoRA-pulled result is still a strong Cole-genre painting, just not the one specified.

- **`tcole_cloudship_horizontal_v2.mp4`** (829 kbps, v2). Recomposition: galleon now beached on a foreground bluff at left, deep river bend, mountain peak at right, more developed cloudscape. Still grounded, not floating. The v2 doesn't fix the cloud-ship concept but does land a stronger composition; the takeaway is that conceptual setups (ship-on-clouds, water-reflection-as-portrait, shadow-as-subject) are weak on this pipeline and need rewriting to a literal camera setup. This is documented as `Obstacle 14` in `legacy/choire-v2/research/video-generation-iterations.md`.

- **`tcole_horses_horizontal.mp4`** (1189 kbps, highest bitrate in the set). Tropical river through dense jungle canopy, three palomino horses walking single-file along the bank under late-afternoon light filtering through palms. Three horses correctly rendered. The high bitrate is earned: dense foliage texture across the entire frame, water shimmer, individual tree silhouettes. Demonstrates the pipeline working at maximum texture density, which is where the underlying LCM-distilled stack is most vulnerable. The fact that the clip holds together here is the strongest argument for the After Cole epoch-10 LoRA scale of 0.75.

- **`tcole_siege_horizontal.mp4`** (807 kbps). The Cole-LoRA cousin of `siege_harbour_horizontal.mp4`: same subject family (Roman harbour, burning ships, smoke towers, lighthouse), rendered through Cole instead of fresco. The deltas read as the LoRAs themselves: Cole gives darker smoke pillars with structured volume, harder rim-light on the fires, a more naturalistic dusk sky with cumulus, and a lighthouse rendered with specific architectural detail. The fresco version is hazier, brighter, more ochre. This pair (`siege_harbour_horizontal.mp4` next to `tcole_siege_horizontal.mp4`) is the second informative A/B in the catalogue: same prompt scaffold, two LoRAs, two visual languages.

## How to use this catalogue when working in the repo

Two pairs to spend the most time on:

1. **`notturno_city_horizontal.mp4` vs `notturno_city_horizontal_calm.mp4`** for understanding what the denoise schedule does. The standard profile is the fresco aesthetic the Choire v2 pipeline was tuned for; the calm profile points at where Renoir florals likely want to land (more representational, less ambient haze).

2. **`siege_harbour_horizontal.mp4` vs `tcole_siege_horizontal.mp4`** for understanding what the LoRA stack does at fixed pipeline parameters. Same subject family, two visual languages, no other change. This is the actual port-test target: when the new Pipeline can render both these clips from the same code with only `Style` config swapped, the After Cole pattern has been preserved.

For everything else, watch the `v1` clip first, then the `v2`. The pattern in this catalogue is consistent: v2 is the recomposition where prompt scale or subject identity survived the LoRA. The pipeline parameters did not change between them.

## Subjects that are absent from the catalogue but documented in the source

The After Cole `TCOLE_SUBJECTS` in [../legacy/after-cole/generate_horizontal_tcole.py](../legacy/after-cole/generate_horizontal_tcole.py) defines five subjects; all five are represented above. The Choire v2 horizontal `SUBJECTS` dict in [../legacy/choire-v2/scripts/generate_horizontal.py](../legacy/choire-v2/scripts/generate_horizontal.py) defines ~25; only 7 are sampled here (E14 lake, E24 garden, notturno city standard + calm, harbour market standard + calm, siege harbour). The 19 "approved" portrait sessions from `video-pipeline-best.md` are not in this clone (they are the 768 x 1344 versions, not the horizontals). For a full Choire v2 horizontal render across the subject grid, point the production scripts at the SUBJECT keys directly.
