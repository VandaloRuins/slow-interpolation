# Thomas Cole SDXL LoRA — Usage Reference

## Trigger Word

`tcole`

## Checkpoint Files

Trained on CivitAI, stored locally at [checkpoints/](checkpoints/):

| File | Epoch | Notes |
|------|-------|-------|
| `Thomas_Cole_epoch_1.safetensors` | 1 | Light touch — style hint without overpowering composition. Better for subtle Cole atmosphere on non-Cole subjects. |
| `Thomas_Cole_epoch_10.safetensors` | 10 | Strong style — full Hudson River School / Romantic landscape look. Use for direct Thomas Cole style emulation. |

**When to use which:**
- **Epoch 1** — mixing tcole atmosphere with other concepts, subtle style transfer, compositions Cole never painted
- **Epoch 10** — full Thomas Cole pastiche, traditional landscape scenes, maximum style fidelity

Try both with weight 0.7-0.9 and pick per use case.

## Prompt Structure

Always lead with the trigger word, followed by a natural language scene description:

```
tcole, [scene type], [key subjects], [lighting/atmosphere], [composition], [style markers]
```

## Vocabulary That Works (from training captions)

### Scene Types
- wilderness landscape, pastoral landscape, romantic landscape
- architectural view, allegorical scene, coastal landscape
- seascape, river valley, mountainous wilderness

### Key Subjects
- towering cliffs, rocky gorge, cascading waterfall, winding river
- ancient ruins, crumbling tower, classical columns, medieval castle
- dense forest, gnarled tree, autumnal foliage, rolling green hills
- lone figure, shepherd, angel, small boat
- calm lake, natural bridge, distant mountains

### Lighting & Atmosphere
- golden hour, soft dawn light, dramatic storm clouds
- luminous sky, twilight, misty mountains, hazy distance
- warm earth tones, deep greens, golden light breaking through
- dark shadows, pale sky, stormy sky, sunset glow

### Style Markers
- oil painting, Hudson River School, romantic landscape
- luminism, pastoral, Romantic

## Example Prompts

**Dramatic landscape:**
```
tcole, a dramatic wilderness landscape with towering storm clouds over rocky cliffs, dense forest in foreground, golden light illuminating distant mountains, oil painting
```

**Pastoral scene:**
```
tcole, a pastoral landscape at golden hour with a winding river reflecting luminous sky, rolling green hills, shepherd with flock in foreground, distant ruins on hilltop, romantic landscape
```

**Allegorical/mystical:**
```
tcole, an allegorical river scene with a radiant angel guiding a golden boat through a dark gorge, luminous white robes reflecting in still water, dense foliage and cliffs, oil painting
```

**Ruins:**
```
tcole, crumbling Roman ruins overgrown with vegetation on a sunlit hillside, classical columns and arches, distant mountains under pale sky, warm earth tones, Hudson River School
```

**Night/twilight:**
```
tcole, a moonlit wilderness landscape with rugged snow-capped mountains under deep blue twilight sky, still lake reflecting starlight, lone figure on rocky outcrop, romantic landscape
```

## LoRA Settings (recommended starting points)

- **Weight:** 0.7-0.9 (too high may overcook the style)
- **Base model:** SDXL 1.0 or any SDXL finetune
- **CFG:** 5-8 for natural results
- **Sampler:** DPM++ 2M Karras or Euler a

## Dataset

90 images covering the full range of Thomas Cole's work:
- The Course of Empire series (5 paintings)
- The Voyage of Life series (4 paintings)
- Hudson River School wilderness landscapes
- Pastoral and architectural scenes
- Italian ruins and allegorical works

Trained on CivitAI. Trigger word embedded in all 90 caption files.
