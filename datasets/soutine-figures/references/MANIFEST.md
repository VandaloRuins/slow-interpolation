# Soutine reference set, manifest

Curated reference set for the Soutine figure LoRA. 10 paintings selected from Chaïm Soutine's (1893 to 1943) body of work, biased toward full-body or substantial-body figures with strong silhouette legibility, against backgrounds the Renoir + Soutine LoRA blend can leverage.

This is the **reference set**, not the training set. The training set is generated synthetically from these references via Nano Banana + GPT image-1 (see [docs/compositing-design.md](../../../docs/compositing-design.md) "Figure LoRA training" section). These references are the style anchors.

## Selection criteria

- **Full body or substantial body coverage.** Tight-cropped portraits are excluded; the LoRA must learn whole-figure silhouettes for use inside slow-interpolation compositing.
- **Palette diversity within Soutine's range.** Cap with red liveries (bellboys, pastry cooks, choirboys) bias the LoRA toward that subset; we balance with non-uniformed figures.
- **Pose and gender diversity.** Standing, seated, kneeling. Male and female sitters.
- **Brushwork legibility.** Dragging impasto, twisting body axes, dark red / ochre / brown / dark orange dominant. The defining Soutine surface.
- **Date range.** 1918 to 1934. Covers the peak figurative period.

## Reference set (10 paintings)

| # | Title | Year | Source / collection | Subject | Pose | Palette notes |
|---|---|---|---|---|---|---|
| 1 | Le Groom (The Bellboy) | 1928 | Centre Pompidou, Paris | Young male bellboy in red livery | Standing, frontal, hands on hips | Carmine red coat against dull green-grey ground. Iconic. |
| 2 | Page Boy at Maxim's | 1925 | Tel Aviv Museum of Art | Young male page in red and gold livery | Standing, slight three-quarter | Crimson red, ochre, dark olive ground |
| 3 | Le Petit Pâtissier (The Pastry Cook) | 1919 | Barnes Foundation, Philadelphia | Pastry cook in white uniform | Standing, frontal, hand on hip | White uniform pulled toward warm yellows + browns; deep burgundy ground |
| 4 | Choirboy in Red (Enfant de choeur) | 1928 | Private collection | Choirboy in red robe | Standing, frontal | Deep saturated red robe, smoky brown surround |
| 5 | La Première Communiante (The Communicant) | 1925 | Private collection | Young female in white communion dress | Standing, frontal | White dress modeled in greys and yellows, dark red-brown setting |
| 6 | L'Homme en Prière (Praying Man) | 1921 | Private collection | Older male figure in prayer | Kneeling, three-quarter | Dark browns + ochres, raw umber ground |
| 7 | Portrait of Madeleine Castaing | 1929 | Metropolitan Museum, New York | Female sitter (Soutine's patroness) | Seated, three-quarter | Black-violet dress, blood-red ground, smoke-blue accents |
| 8 | Young English Girl (Jeune Anglaise) | 1934 | Private collection | Young female sitter | Seated, frontal | Cool ivory dress, sienna ground, dark orange accents |
| 9 | Self-Portrait | 1918 | Princeton University Art Museum | Soutine himself, young | Half-body, three-quarter, hand near face | Heavy browns + dark green; touchstone for the painter's own face |
| 10 | Portrait of a Schoolboy (Le Petit Écolier) | c.1928 | Private collection | Young male in school uniform | Standing, frontal | Navy + ochre + carmine, dark brown ground |

## Acquisition method

Download high-resolution reproductions from:

- **WikiArt** ([wikiart.org/en/chaim-soutine](https://www.wikiart.org/en/chaim-soutine)): primary source. Covers entries 1, 2, 3, 4, 5, 6, 9 reliably; quality varies but is usable for style anchoring.
- **Museum collection pages** (Centre Pompidou, Met, Barnes, Princeton): higher resolution where available. Use these for entries 1, 3, 7, 9.
- **Auction-house archives** (Christie's, Sotheby's): the private-collection entries (4, 5, 8, 10) appear here with high-resolution reproductions when works went to sale. Search by painting title + Soutine.

Save each as `datasets/soutine-figures/raw/<id>_<short-title>.jpg`. Target ~2000 px on the long side or better. The `raw/` subdir is gitignored per repo policy (datasets/**/raw/).

## Copyright note

Soutine died 1943. Public domain in most jurisdictions where copyright term is life + 70 years (expired 2013). Some jurisdictions (US: life + 95 for works first published before 1978 abroad) may still hold residual claims. Treat the reference set as research / training data, not as redistribution of the originals. Synthetic generations from these anchors (the actual LoRA training data) carry no inherited copyright concern.

## Diversity audit

Composition of the 10 references:

- Uniform / livery figures: 4 (entries 1, 2, 3, 4)
- Non-uniformed figures: 6
- Standing: 7
- Seated: 2
- Kneeling: 1
- Male sitters: 7 (incl. the boys and Soutine himself)
- Female sitters: 3
- Frontal: 6
- Three-quarter: 4
- Date range: 1918 to 1934

The red-livery bias (4 of 10) is acceptable because the synthetic-data generation step (Nano Banana + GPT image-1) will broaden pose, color, and clothing far beyond the reference set's distribution. The references anchor brushwork and palette temperature, not specific costumes.

## Next steps

1. Download the 10 references at the highest resolution practical. Land at `datasets/soutine-figures/raw/`.
2. When the Renoir mosaic-protocol export lands, run the synthetic-generation step using these 10 as style anchors. Both Nano Banana and GPT image-1 are exercised per sample. Target output: ~80 captioned synthetic samples post-filter.
3. Caption with trigger word `stn` + Kohya-style suffix template (see compositing-design.md).
4. CivitAI training run by Luca.
