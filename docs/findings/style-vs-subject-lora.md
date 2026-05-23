# Style LoRA vs subject LoRA: dataset composition determines which

Date: 2026-05-18.
Workstream of origin: Compositing (Phase 3 workstream #4).
Branch: main.

## Claim

In SDXL LoRA training, "style LoRA" and "subject LoRA" are NOT properties of the training algorithm. They are properties of the **dataset composition + caption strategy**. The trigger token gets associated with whatever is invariant across the dataset; everything that varies becomes vocabulary the SDXL text encoder can already steer. Mis-classify the LoRA you are about to train and you waste a Buzz cycle.

This finding is the rule we used to pick the Soutine training set shape on 2026-05-18.

## The two regimes

### Style LoRA regime

- **Dataset**: spans many subjects within ONE stylistic register (one artist, one process, one visual era).
- **Captions**: name the subject explicitly. Trigger token + style closer constant; subject phrase variable.
- **Trigger learns**: surface (brushwork, palette, facture, value structure, micro-texture).
- **Subject at inference**: comes from your prompt. SDXL already knows what a vase, a bellboy, a hillside is.
- **Working size**: 80 to 200 captioned samples per `dataset-practice.md`. Below 80 the LoRA under-fits; above 250 the auction-catalogue color cast risks dominating.

Worked examples: Renoir Flowers (110 keepers, all floral subjects, 5-slot caption template, trigger `rfl`). Thomas Cole (~80 keepers, all Hudson River School landscapes, trigger `tcole`). Casa del Suono frescoes (~70 keepers, trigger `cds`).

### Subject LoRA regime

- **Dataset**: focuses on ONE subject family across many surface treatments (50 photos of a specific cat from different angles and lightings).
- **Captions**: name the surface explicitly. Trigger token + subject identity constant; surface phrase variable.
- **Trigger learns**: the subject's identity (the specific cat's appearance).
- **Style at inference**: comes from your prompt. The LoRA does not generalize off the trained surface but produces the subject faithfully when invoked.
- **Working size**: 30 to 80 samples typically. Smaller datasets are tolerable because the surface variance helps the model factor the subject signal cleanly from lighting.

## What goes wrong if you confuse the two

1. **You train style on too few samples of a single subject.** Example: Soutine has roughly 37 standing-figure paintings on Wikimedia at adequate resolution. If you train a "Soutine figure" LoRA on those 37 alone, the model has no signal that separates "Soutine's surface" from "Soutine's figures". The trigger absorbs both, the LoRA memorises specific paintings, and outputs read as "looks like one specific painting" rather than "looks like Soutine paints a figure".

2. **You add un-captioned non-target subjects to a subject LoRA.** Example: training "specific bellboy character" on a mix of figures and landscapes. The trigger absorbs whatever leaks through the captions and the LoRA loses its subject identity.

3. **You assume the LoRA "knows the style" because it can paint the trained subject.** A subject LoRA at strong scale can produce surface artifacts that look style-correct on the trained subject and collapse on any other subject. Renoir's Cole LoRA (a style LoRA) generalizes to any landscape prompt. A Soutine-figure-only LoRA would not generalize to a Soutine-landscape prompt because it never trained on landscapes; the surface would not match the painter.

## Decision rule for picking the regime

Ask in order:

1. **What size of dataset can you actually source?**
   - Below 50 samples in any direction: subject LoRA is your only realistic option. Style learning needs more.
   - 50 to 80 samples of a single subject: borderline. You can train a subject LoRA, but expect overfitting. Subject vocabulary at inference will need to push toward the trained distribution.
   - 80+ samples across multiple subjects within one stylistic register: style LoRA. The natural fit.

2. **What does your downstream pipeline want at inference?**
   - "Render this prompt with this style applied" -> style LoRA. The prompt carries the subject; the LoRA carries the surface.
   - "Render this specific subject in any style" -> subject LoRA. Stack with a style LoRA at inference if you need to.

3. **Does the painter's body of work span genres?**
   - Yes (Soutine: figures + landscapes + carcasses; Manet: figures + still lifes + outdoor scenes; Bonnard: bathers + interiors + landscapes): style LoRA. Embrace the heterogeneity. The shared surface is what the LoRA learns.
   - No (a portrait painter who only painted portraits): subject LoRA may emerge naturally from a style-LoRA-shaped training run because the data is mono-subject by default.

## Worked example: Soutine, 2026-05-18

Phase A.6 source pass returned 85 plausible Soutine paintings after gallery triage. Breakdown by subject family inferred from filenames:

| Family | Count |
|---|---|
| Figure (named subjects: bellboy, patissier, Castaing, choirboy, Communiante, etc.) | 53 |
| Landscape (Ceret, Cagnes, red roofs, bent trees) | 14 |
| Carcass / dead animal (beef, turkey, rabbit, chicken, pheasant, fowl, herrings) | 15 |
| Still life (lamp, bouquet+statue) | 3 |
| Total | 85 |

The original compositing-design intent was a "Soutine figure" LoRA for the foreground in strategies C and D. With 37 figures alone (the manifest-style narrow subset), we sit BELOW the 80-image style-LoRA floor and ABOVE the size where a tight subject LoRA reads cleanly. Worst of both worlds.

Pivoted on 2026-05-18 to a Soutine STYLE LoRA on the broader 85-image set:

- Trigger `stn` + style closer `oil painting, expressionist, dark palette` constant across all 85 captions.
- Subject phrase variable per file, dispatched by subject family (figure -> "a bellboy in red livery, standing full body"; landscape -> "a Ceret hillside view, twisted houses and red roofs"; carcass -> "a hanging turkey, head down, feathers catching warm light"; still life -> "a still life with an oil lamp on a dark interior").
- Palette and brushwork pools shared across families. Lighting pool branches indoor vs outdoor.

Compositing strategy C / D regional prompting at inference time tells the figure region "stn, a butcher's boy standing full body, twisted body, expressionist". The LoRA paints the brushwork. The model's pre-trained figure knowledge handles anatomy. The fact that the LoRA also saw landscapes and carcasses in training does not hurt the figure region's output; the regional cross-attention routes the figure prompt to the figure region, and the LoRA's broader subject vocabulary is silent unless invoked.

Reference implementation: [datasets/soutine-figures/captions.py](../../datasets/soutine-figures/captions.py).

## Decision

For the Soutine LoRA on the compositing release:

- **Locked: style LoRA on 85 heterogeneous samples**, NOT a 37-figure subject LoRA.
- Trigger `stn`, suffix `oil painting, expressionist, dark palette`.
- Hyperparameters per `lora-training.md` (rank 16 alpha 8 if Kohya, or AI Toolkit defaults at rank 32 alpha 32; engine choice is a separate decision tracked in the Compositing decisions log).

For any future LoRA workstream:

- Apply the three-question rule above before sizing the dataset. If the answer points to style, source for 80 to 200 across multiple subjects within one register. If the answer points to subject, source 30 to 80 across multiple surfaces of one subject.
- If you find yourself with under 50 of your target subject and the artist painted across genres, expand the dataset to other genres rather than training a thin subject LoRA. The LoRA's job is the surface; let the subject vocabulary in the prompt do the rest.

## What this does NOT cover

- Stacking two LoRAs at inference (style + subject combined). The slow-interpolation pipeline does this in compositing strategy C (Renoir style + Soutine style, regional prompting at the cross-attention layer). That is an inference-time concern, not a training-time one. Covered by the compositing workstream (maintainer's private planning folder during v0.1; surfaces as `manual/compositing.md` in v0.2).
- LoRA training engines (Kohya vs AI Toolkit). Different default hyperparameters but the style-vs-subject distinction is engine-agnostic.
- Concept LoRAs (a specific costume, a fictional creature, a particular pose family). A hybrid case; treat as subject LoRA with subject-defining keywords pinned in caption.

## Out-of-scope cleanups for later

- `dataset-practice.md` Phase 4 ("Caption") could absorb the subject-family caption-branching pattern that this finding's worked example uses. Filed as CR-B in the compositing workstream (private during v0.1).
- `lora-training.md` could absorb the AI-Toolkit-vs-Kohya hyperparam distinction (orthogonal to this finding but adjacent). Filed as CR-C in the same workstream.

---
*Did you reproduce this and observe something different? Counter-findings welcome. See [CONTRIBUTING.md](../../CONTRIBUTING.md) shape 4 and the [finding issue template](../../.github/ISSUE_TEMPLATE/finding.md).*
