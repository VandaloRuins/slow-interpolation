"""Generate natural-language captions for the Renoir floral dataset.

Convention (matches the brief and the Thomas Cole LoRA precedent):

    rfl, [subject], [composition], [palette / light], oil painting, impressionist

- Trigger word `rfl` first, always.
- 30 to 60 words per caption.
- No em dashes.
- One line per image in captions.txt, filename order.
- captions.json carries the structured fields for human inspection.

Subject is parsed from the cleaned title (which is the slug-derived clean
form built by finalize_metadata.py). Composition is inferred from aspect
ratio plus subject family. Palette/light is drawn from a small impressionist
vocabulary, biased by inferred subject so the LoRA sees consistent palette
language without every caption being identical.

The generator is deterministic. Re-running on the same metadata.csv
produces byte-identical captions.txt.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
META = ROOT / "metadata.csv"
RAW = ROOT / "raw"
TXT_OUT = ROOT / "captions.txt"
JSON_OUT = ROOT / "captions.json"

TRIGGER = "rfl"
SUFFIX = "oil painting, impressionist"

# Brushwork / surface descriptor inserted between palette and suffix so the
# caption template carries a consistent style cue and the word count lands
# in the 30 to 60 window for every entry.
BRUSHWORK = [
    "visible brushstrokes, layered impasto petals",
    "loose painterly handling, broken colour across the petals",
    "thick impasto highlights, soft scumbled background",
    "feathered brushwork on the leaves, wet-into-wet petal blending",
    "thinly painted ground, loaded brush on the blooms",
    "loose impressionist touch, vibrating edges between forms",
    "delicate broken brushwork, optical mixing in the petals",
    "soft scumbled background, ripe impasto in the bouquet center",
]


# --- Subject parsing ---------------------------------------------------------
#
# Order matters. Earlier hits take precedence so that compound titles
# ("roses and peonies in a vase") resolve to the more specific family.

SUBJECT_RULES = [
    # --- scenes WITH flowers (figures, gardens, landscapes) ---
    (r"\bcamille\s+monet|\btapisserie\s+dans\s+le\s+parc", "a woman seated in a garden working at a tapestry frame surrounded by flowers"),
    (r"\bclaude\s+monet.*garden|\bmonet.*painting\s+in\s+his\s+garden|\bargenteuil.*garden", "an artist at his easel painting in a flowering garden"),
    (r"\bin\s+the\s+garden|\bjeunes?\s+filles?\s+dans\s+un\s+jardin", "two young figures in a sunlit garden with flowers"),
    (r"\bcueillette\s+des\s+fleurs|\bpicking\s+flowers|\bgathering\s+flowers|\bfemme\s+cueillant\s+des\s+fleurs|\bgirls?\s+picking\s+flowers", "a young woman gathering flowers in a sunlit meadow"),
    (r"\bjardin\s+fontenay|\bjardin\s+sorrent|\bjardin\s+d.*alger|\bdes\s+collettes|\bun\s+jardin|\bgarden\s+landscape|\bgothenburg.*garden|^garden", "a Mediterranean garden landscape with flowering plants in midday sun"),
    (r"\bwoman\s+at\s+the\s+garden|\bwoman.*garden|\bnini\s+in\s+the\s+garden", "a woman seated in a garden of climbing flowers"),
    (r"\bportrait\s+de\s+coco.*fleurs|\bcoco\s+et\s+fleurs", "a small child with a vase of flowers on a table"),
    (r"\bwoman\s+with\s+lilac|\bfemme\s+aux\s+lilas", "a young woman holding a sprig of lilacs"),
    (r"\bvase\s+de\s+fleurs\s+et\s+femme|\bvase\s+of\s+flowers\s+and\s+woman", "a woman with a vase of flowers on the table beside her"),
    (r"\bfleurs?\s+et\s+chats?|\bflowers?\s+and\s+cats?", "a still life of mixed flowers in a vase with two cats curled at the table edge"),
    (r"\bpaysage\s+avec\s+fleurs|\blandscape\s+with\s+flowers|\bfleurs\s+et\s+fond\s+de\s+mer", "a coastal landscape with a foreground of garden flowers and a sea horizon"),

    # specific-flower-first stories (existing)
    (r"\brose[s]?(?:.*peon|.*dahlia)|\broses?\s+and\s+peon|\broses?\s+and\s+dahlia", "a mixed bouquet of roses and other late-summer blooms"),
    (r"\bnarcisse[s]?\s+et\s+rose[s]?|\bnarcissus.*rose|\brose.*narcissus", "a bouquet of narcissi and roses"),
    (r"\banemone[s]?\s+et\s+rose[s]?|\banemonen?\s+und\s+rosen", "a bouquet of anemones and roses"),
    (r"\bgladiol(a|i|us|en|es|ies)?\s+and\s+dahlia[s]?|\bgladio.*dahlia", "a bouquet of gladioli and dahlias"),
    (r"\bfleurs?\s+rouges?\s+et\s+blanches?|\bred\s+and\s+white\s+flower", "an arrangement of red and white flowers with orchids"),
    (r"\bfleurs?\s+et\s+fruit|\bflowers?\s+and\s+fruit|\bnature\s+morte\s+fleurs?\s+et\s+fruits?|\bpanneau\s+de\s+fruits?\s+et\s+fleurs?", "a still life of flowers and ripe fruit"),

    # single-flower-family titles
    (r"\bchrysanth", "a bouquet of chrysanthemums"),
    (r"\bdahlia", "a bouquet of dahlias"),
    (r"\bgladiol", "a vase of gladioli"),
    (r"\btulip", "a bouquet of tulips"),
    (r"\bpeon", "a bouquet of peonies"),
    (r"\bgeranium", "a planter of geraniums"),
    (r"\blilac|\blilas", "a bouquet of lilacs"),
    (r"\banemone[s]?\s+dans\s+un\s+vase|\banemones?\s+in\s+a\s+vase|\banemonen", "a vase of anemones"),
    (r"\banemone|\banémones?|\ban-mone|\bles\s+an-mones", "a study of anemones"),
    (r"\bnarcisse|\bnarcissus", "a bouquet of narcissi"),

    # roses, dominant subject in the dataset
    (r"\bvase\s+de\s+roses?|\bvase\s+of\s+roses?|\broses?\s+in\s+a\s+vase|\broses?\s+dans\s+un\s+vase", "a porcelain vase of roses"),
    (r"\bbouquet\s+de\s+roses?|\bbouquet\s+of\s+roses?", "a bouquet of roses on a table"),
    (r"\broses?\s+blanches?|\bwhite\s+roses?", "a cluster of white roses"),
    (r"\bles\s+roses?\s+rouges?|\bred\s+roses?", "a cluster of crimson roses"),
    (r"\broses?", "a study of roses"),

    # generic "flowers / bouquet" titles
    (r"\bvase\s+of\s+flower|\bvase\s+de\s+fleurs?|\bflowers?\s+in\s+a.*vase|\bfleurs?\s+dans\s+un.*vase|\bflowers?\s+in\s+a.*pot|\bmixed\s+flowers?\s+in\s+an?\s+earthenware|\bjardini|\bcorbeille\s+de\s+fleurs?", "a porcelain vase of mixed flowers"),
    (r"\bbouquet\s+printanier|\bspring\s+bouquet", "a spring bouquet of mixed garden flowers"),
    (r"\bbouquet|\bin\s+a\s+vase|\bdans\s+un\s+vase|\bin\s+un\s+vaso", "a bouquet of mixed flowers in a vase"),
    (r"\besquisse\s+de\s+fleurs?|\bstudy.*flowers?|\bfleurs?\s+varies?|\bfleurs?\s+variées", "a loose painterly study of garden flowers"),
    (r"\bfleurs?|\bflowers?", "a cluster of garden flowers"),
]

# Fallback subject if nothing matches.
DEFAULT_SUBJECT = "a study of cut flowers on a table"

# --- Composition ------------------------------------------------------------

def composition_for(subject: str, w: int, h: int) -> str:
    """Pick a composition phrase from the subject family and aspect ratio."""
    aspect = w / max(h, 1)
    portrait = aspect < 0.95
    square = 0.95 <= aspect <= 1.1
    landscape = aspect > 1.1

    # Scene-with-flowers compositions
    if "garden landscape" in subject or "mediterranean garden" in subject:
        if portrait:
            return "vertical garden view with foliage filling the frame, distant trellis or wall in the background"
        return "horizontal garden landscape, flowering plants in the foreground, path or wall mid-frame"
    if "artist at his easel" in subject:
        return "figure painting outdoors in a garden, easel in the mid-ground, foliage all around"
    if "tapestry frame" in subject:
        return "figure seated in a garden, tapestry frame in the foreground, flowers and foliage behind"
    if "two young figures" in subject or "young woman gathering" in subject or "young woman holding" in subject:
        if portrait:
            return "vertical figure composition, flowers in the hand or at the waist, garden behind"
        return "horizontal genre scene, figures occupying the lower two thirds, flowering meadow or hedge above"
    if "small child" in subject:
        return "child in the lower frame with the vase of flowers in the upper frame, soft domestic interior"
    if "woman seated" in subject or "woman with a vase" in subject:
        return "interior scene, figure on the left or right, flowering arrangement balancing the composition"
    if "coastal landscape" in subject:
        return "horizontal landscape, flowering foreground, sea or sky horizon in the upper third"
    if "two cats" in subject:
        return "still life on a table, vase of flowers center frame, two cats coiled at the table edge"

    # Pot / vase compositions
    if "vase" in subject or "porcelain" in subject or "earthenware" in subject:
        if portrait:
            return "centered still life on a table, vase rising in the frame"
        if square:
            return "centered still life on a table, full vase contained in the frame"
        return "still life on a table, vase set against a soft interior background"

    if "planter" in subject or "geranium" in subject:
        return "potted plant on a window ledge"

    if "bouquet" in subject:
        if portrait:
            return "bouquet rising in the center of the frame, table edge at the lower margin"
        return "bouquet laid across the frame, fabric or table cloth in the foreground"

    if "study" in subject or "loose painterly" in subject:
        return "close-cropped fragment, flowers filling the frame edge to edge"

    if "cluster" in subject:
        if landscape:
            return "frieze of blooms across the width of the canvas"
        return "tight cluster of blooms in the center of the frame"

    if "still life of flowers and ripe fruit" in subject:
        return "still life on a table, flowers in a vase with fruit in front"

    # Default
    if portrait:
        return "centered still life, soft interior backdrop"
    if landscape:
        return "horizontal still life across the width of the canvas"
    return "still life arrangement filling the square frame"


# --- Palette / light --------------------------------------------------------

# Sequence indexed by hash(filename) so the distribution is even across the
# dataset rather than bunching all "warm afternoon" together.
PALETTES = [
    "warm afternoon light, creamy whites and pinks against a deep rose ground",
    "soft natural daylight, blush pinks and ivory against a slate-grey background",
    "cool studio light, blue-greys and lavenders with green leaves catching highlights",
    "rich impasto reds and crimsons against a tobacco-brown ground",
    "buttery cream and apricot tones, dappled garden light",
    "ochre and umber backdrop, pale petals catching the front-light",
    "warm interior light, brick reds, terracotta and gilt",
    "powdery blue and pale rose, light from a curtained window",
    "tawny golden ground, petals carrying full chromatic saturation",
    "cool morning light, white petals against a celadon green wall",
    "earthy plum and olive backdrop, blossoms holding a warmer key",
    "diffuse north-facing studio light, low contrast, pastel keying",
]


def palette_for(filename: str, subject: str) -> str:
    """Pick a palette phrase. Bias toward warm/cool by inferred subject."""
    h = sum(ord(c) for c in filename)
    if "white" in subject:
        bias = [1, 4, 7, 9, 11]
    elif "crimson" in subject or "rich impasto reds" in subject or "red" in subject:
        bias = [0, 3, 6, 8]
    elif "anemone" in subject or "delft" in filename:
        bias = [2, 7, 9, 11]
    elif "chrysanth" in subject or "dahlia" in subject:
        bias = [0, 5, 6, 10]
    elif "lilac" in subject:
        bias = [2, 7, 9]
    elif "tulip" in subject or "narciss" in subject or "spring" in subject:
        bias = [4, 7, 11]
    elif "fruit" in subject:
        bias = [0, 3, 6, 10]
    else:
        bias = list(range(len(PALETTES)))
    return PALETTES[bias[h % len(bias)]]


# --- Caption assembly -------------------------------------------------------

def parse_subject(title: str, filename: str) -> str:
    blob = (title + " " + filename).lower()
    # normalize a few mojibake patterns from the slugifier
    blob = blob.replace("an-mones", "anemones").replace("an mones", "anemones")
    for rx, subj in SUBJECT_RULES:
        if re.search(rx, blob):
            return subj
    return DEFAULT_SUBJECT


def brushwork_for(filename: str) -> str:
    h = sum(ord(c) * 7 for c in filename)
    return BRUSHWORK[h % len(BRUSHWORK)]


def build_caption(subject: str, composition: str, palette: str, brushwork: str) -> str:
    return f"{TRIGGER}, {subject}, {composition}, {palette}, {brushwork}, {SUFFIX}"


def word_count(s: str) -> int:
    return len(s.split())


def main() -> int:
    rows = list(csv.DictReader(META.open(encoding="utf-8")))
    rows.sort(key=lambda r: r["filename"])

    captions_txt = []
    captions_json = []
    short_count = 0
    long_count = 0

    for r in rows:
        fn = r["filename"]
        title = r["title"]
        w, h = int(r["original_width"]), int(r["original_height"])

        subject = parse_subject(title, fn)
        composition = composition_for(subject, w, h)
        palette = palette_for(fn, subject)
        brushwork = brushwork_for(fn)
        caption = build_caption(subject, composition, palette, brushwork)

        wc = word_count(caption)
        if wc < 30:
            short_count += 1
        if wc > 60:
            long_count += 1

        captions_txt.append(f"{fn}\t{caption}")
        captions_json.append({
            "filename": fn,
            "caption": caption,
            "trigger": TRIGGER,
            "subject": subject,
            "composition": composition,
            "palette_light": palette,
            "brushwork": brushwork,
            "suffix": SUFFIX,
            "word_count": wc,
            "source_title": title,
            "aspect_ratio": round(w / max(h, 1), 3),
        })

    TXT_OUT.write_text("\n".join(captions_txt) + "\n", encoding="utf-8")
    JSON_OUT.write_text(
        json.dumps(captions_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {len(rows)} captions")
    print(f"  short (<30 words): {short_count}")
    print(f"  long  (>60 words): {long_count}")
    print(f"  -> {TXT_OUT.name}")
    print(f"  -> {JSON_OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
