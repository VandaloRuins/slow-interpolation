"""Generate captions for the Soutine STYLE LoRA dataset.

Decision (2026-05-18): this is a style LoRA, not a subject LoRA. Soutine's
production spans figures, landscapes (Ceret, Cagnes), carcasses, and a few
still lifes; the dataset reflects that breadth so the LoRA learns the
painter's surface (dragging impasto, dark palette, twisted axis, raw
brushwork) across subjects. At inference time the prompt drives subject;
the LoRA drives surface.

Convention (mirrors Renoir captions.py):

    stn, [subject phrase], [lighting], [palette], [brushwork], oil painting, expressionist, dark palette

- Trigger `stn` first, always.
- 30 to 50 words per caption.
- No em dashes.
- One line per image in captions.txt, filename order.
- captions.json carries structured fields for inspection.
- captions.json is a LIST (not a dict) to match Renoir's shape and the
  shared build_gallery.py expectations.

Subject phrase is picked deterministically (hashed by filename) from a pool
keyed by subject family. Family is inferred from the filename:

  - named figure (Castaing, Maria Lani, etc.) via NAME_OVERRIDES
  - landscape (paesaggio, paysage, albero, village, Ceret, Cagnes, ...)
  - carcass / animal (carcass, tacchino, pollo, faisan, hareng, ...)
  - still life (nature morte, natura morta, lampe, bouquet, ...)
  - generic figure fallback (matches Gemini-flagged subject_kind, or
    filename keywords like "portrait", "boy", "femme", "uomo")

Reads:
    raw/         (the keeper set, post-gallery-triage)
    review.json  (optional; gives prior Gemini subject_kind if present)

Writes:
    captions.txt   filename<TAB>caption
    captions.json  list of per-image structured caption records
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
REVIEW = ROOT / "review.json"
TXT_OUT = ROOT / "captions.txt"
JSON_OUT = ROOT / "captions.json"

TRIGGER = "stn"
SUFFIX = "oil painting, expressionist, dark palette"


# ---------------------------------------------------------------------------
# Subject family classification (by filename)
# ---------------------------------------------------------------------------

LANDSCAPE_PATTERNS = re.compile(
    r"paesaggio|paysage|landscape|albero|arbre|tree|"
    r"maisons|case|casa|village|villaggio|paese|"
    r"veduta|view|c-ret|ceret|cagnes|hill|colline|"
    r"toits|roofs|platanes|chemin|fontaine|"
    r"paisagem|rvores",
    re.IGNORECASE,
)

CARCASS_PATTERNS = re.compile(
    r"carcass|carcasse|boeuf|beef|b-uf|"
    r"tacchino|turkey|dindon|duck|canard|"
    r"pollo|chicken|spiumato|plucked|"
    r"fagiano|pheasant|faisan|fasan|"
    r"coniglio|rabbit|lapin|lievre|hare|"
    r"hareng|herring|raie|fish|poisson|"
    r"volaille|fowl|pendue|hung|hanging",
    re.IGNORECASE,
)

STILL_LIFE_PATTERNS = re.compile(
    r"nature.morte|natura.morta|still.life|"
    r"lampe|lamp|harengs.et.oignons|oignons|onions|"
    r"pomodori|tomates|bouquet|fleurs|"
    r"rose.la.statue|statue.de.platre|plaster.statue",
    re.IGNORECASE,
)


def subject_family(filename: str, gemini_kind: str = "") -> str:
    """Return one of: figure, landscape, carcass, still_life.

    Figure-name overrides win first: a title like "le-patissier-de-cagnes"
    is a Pastry-Cook-of-Cagnes (figure), not a Cagnes landscape, even
    though "cagnes" appears in LANDSCAPE_PATTERNS.
    """
    low = filename.lower()
    for pattern, _ in FIGURE_NAME_OVERRIDES:
        if re.search(pattern, low):
            return "figure"
    # Carcass before landscape: "natura-morta-con-fagiano" is a carcass
    # painting, not a generic still life.
    if CARCASS_PATTERNS.search(low):
        return "carcass"
    if LANDSCAPE_PATTERNS.search(low):
        return "landscape"
    if STILL_LIFE_PATTERNS.search(low):
        return "still_life"
    if gemini_kind in {"standing_figure", "seated_figure", "kneeling_figure",
                       "portrait_bust", "self_portrait"}:
        return "figure"
    return "figure"  # default; figure is the most common Soutine subject


# ---------------------------------------------------------------------------
# Subject phrases per family
# ---------------------------------------------------------------------------

# Figure: bust / seated / standing / etc., default by Gemini subject_kind
KIND_PHRASE = {
    "standing_figure": "a single full-body figure standing",
    "seated_figure": "a single seated figure",
    "kneeling_figure": "a single kneeling figure",
    "portrait_bust": "a portrait of a single figure, bust length",
    "self_portrait": "a self-portrait of the painter, bust length",
}

# Figure: NAME_OVERRIDES take precedence over KIND_PHRASE.
FIGURE_NAME_OVERRIDES = [
    (r"groom|bellboy|bell.boy|gar.on.d.tage|garcon.detage", "a bellboy in red livery, standing full body"),
    (r"page.boy|piano|ragazzo.ai.piani|piani", "a young page boy in livery, seated near a piano"),
    (r"patissier|pasticcere|pastry.cook|piccolo.pasticcere|p.tissier", "a pastry cook in white uniform, standing full body"),
    (r"choir.boy|choirboy|enfant.de.choeur|ragazzo.di.coro|grand.enfant.de.choeur", "a choirboy in red robes, standing"),
    (r"communi.ant|comuni.ante|premi.re.commun", "a young communicant in white dress, standing"),
    (r"praying|en.pri.re|priere|preghiera|man.praying", "an older figure kneeling in prayer, hands clasped"),
    (r"schoolboy|coli.r|petit.colier|ragazzino|petit.ecolier", "a young schoolboy, three-quarter length"),
    (r"madeleine.castaing|castaing", "Madeleine Castaing seated, in a dark dress against a deep red ground"),
    (r"maria.lani|lani", "Maria Lani, three-quarter portrait against a dark ground"),
    (r"jeune.anglaise|english.girl|young.english|giovane.inglese", "a young English girl seated, three-quarter view"),
    (r"jeune.fille|young.girl|ragazzina|paulette|dreaming.girl", "a young girl seated, three-quarter view"),
    (r"butcher|garcon.boucher|gar.on.boucher", "a butcher's boy in apron, standing full body"),
    (r"valet", "a valet in dark uniform, standing"),
    (r"servante|maid|domestique", "a young housemaid, seated"),
    (r"fidanzata", "a young bride seated, three-quarter view"),
    (r"testimon.|wedding|witness", "a wedding witness in formal dress, seated"),
    (r"profile.of.a.man|profile.head|profilo.di.uomo", "a profile portrait of a man's head"),
    (r"folle|mad.woman|idiot", "a portrait of a figure in psychological distress"),
    (r"d.ch.ance|deche", "an older woman in dark dress, seated three-quarter view"),
    (r"donna.con.abito.blu|woman.in.blue|femme.en.bleu|blue.dress|abito.blu", "a woman in a blue dress, seated three-quarter view"),
    (r"woman.in.red|young.girl.in.red|abito.rosso", "a young woman in red, three-quarter view"),
    (r"woman.in.pink|femme.en.rose", "a woman in a pink dress, seated three-quarter view"),
    (r"self.portrait|autoportr|autoritratt|selbst|self-portrait", "a self-portrait of the painter"),
    (r"gar.on.russe|russian.boy|russo", "a Russian boy in dark clothes, seated"),
    (r"man.with.horse", "a single male figure standing beside a horse"),
    (r"poup.e|doll|woman.with.doll", "a woman holding a doll, seated"),
    (r"portrait.de.madame.x|portrait.dune.dame|portrait.d.une.dame", "a portrait of an unnamed woman, seated three-quarter view"),
    (r"lejeune|emile.lejeune", "a portrait of Émile Lejeune, three-quarter view"),
    (r"eva", "a portrait of a woman named Eva, three-quarter view"),
    (r"yellow.hat|hat.boy", "a young boy in a yellow hat, seated"),
    (r"black.tie|young.man.wearing", "a young man in a black tie, three-quarter portrait"),
    (r"dreaming|sognante", "a young figure with downcast eyes, three-quarter view"),
]

# Landscape: NAME-style overrides first (specific subjects from filename),
# generic fallback pool last.
LANDSCAPE_NAME_OVERRIDES = [
    (r"albero.piegato|bent.tree", "a bent tree alone on a windswept hillside"),
    (r"grande.albero|great.blue.tree|albero.blu", "a great blue tree dominating a hillside, foliage churning"),
    (r"villaggio|village", "a hillside village under heavy sky, houses crowding the slope"),
    (r"casa.bianca|white.house", "a white house perched on a slope, dim daylight"),
    (r"le.case|maisons|houses", "tilted houses on a hill, walls leaning into each other"),
    (r"toits.rouges|red.roofs|red.rooftops", "red rooftops crowding a slope against a brooding ground"),
    (r"platanes|plane.trees", "an avenue of plane trees, foliage churning at the top"),
    (r"c-ret|ceret|veduta.di.c", "a Ceret hillside view, twisted houses and red roofs"),
    (r"cagnes", "a Cagnes landscape, southern light on terracotta roofs"),
    (r"chemin|fontaine|road", "a road descending through a southern landscape, low light"),
    (r"paesaggio.con.un.personaggio|landscape.with.a.figure", "a stark landscape with a single figure crossing the slope"),
    (r"paisagem|rvores.ao.vento|trees.in.wind", "a landscape of trees bowed by wind"),
    (r"paesaggio|paysage|landscape", "a southern hillside landscape, deep ground under brooding sky"),
]

# Carcass: subject-specific overrides (turkey != rabbit != ox).
CARCASS_NAME_OVERRIDES = [
    (r"carcass.of.beef|boeuf|beef|b-uf|corche", "a flayed ox carcass hanging against a dark ground"),
    (r"tacchino|turkey|dindon", "a hanging turkey, head down, feathers catching warm light"),
    (r"pollo|chicken.hung|chicken|spiumato|plucked", "a plucked chicken hanging from a hook against a darkened wall"),
    (r"duck|canard", "a hanging duck against a dim interior wall"),
    (r"coniglio|rabbit|lapin", "a dead rabbit laid across a wooden table"),
    (r"fagiano|pheasant|faisan|fasan", "a pheasant lying on a dark cloth, feathers catching warm light"),
    (r"hareng|herring|harengs.et.oignons", "a still life of herrings and onions on a kitchen board"),
    (r"raie|fish|poisson", "a hanging fish on a darkened wall"),
    (r"volaille|fowl|pendue|hanging.poultry|hanging.fowl", "a hanging fowl, neck twisted, against a deep red interior"),
]

# Still life: specific subject hints, otherwise generic dark-interior table.
STILL_LIFE_NAME_OVERRIDES = [
    (r"lampe|lamp", "a still life with an oil lamp on a dark interior table"),
    (r"bouquet.de.rose|rose.la.statue|statue.de.platre|plaster.statue", "a bouquet of roses beside a plaster statue on a dark table"),
]
STILL_LIFE_FALLBACK = "a dark interior still life, simple objects under low light"


# ---------------------------------------------------------------------------
# Palette / brushwork / lighting pools (shared across subjects)
# ---------------------------------------------------------------------------

PALETTES = [
    "carcass reds and smoldering ochre against a dark ground",
    "raw umber and dark orange ground, the subject carrying the warm key",
    "blood red, tobacco brown, and bruised violet ground",
    "ochre, sienna, and dark green tones",
    "burnt orange and dark brown ground with pale highlights",
    "smoke grey ground, the subject in deep red and ochre",
    "dark plum and olive backdrop, the subject carrying the warmth",
    "earth reds and umbers, low ambient light",
    "muted ochre and slate-grey ground, restrained but charged",
    "warm tobacco brown ground, dragged reds across the subject",
]

BRUSHWORK = [
    "dragging impasto, twisted axes, expressionist",
    "thick laden brush, distorted contours, visible facture",
    "dragged paint across the surface, broken edges, restless texture",
    "loaded brush, twisted vertical axis, raw scumble in the ground",
    "violent brushwork, scumbled ground, palette knife traces",
    "dragged ochres and reds, distorted proportions, expressionist handling",
    "thick impasto on the highlights, heavy scumble on the surround",
    "twisted silhouette, dragging brush, charged surface",
]

LIGHTING_INDOOR = [
    "low ambient light",
    "indoor studio light from the left",
    "diffuse north-facing studio light",
    "dim interior light",
    "low side-light catching the form",
    "warm interior glow",
    "muted overhead light",
]

LIGHTING_OUTDOOR = [
    "low brooding sky overhead",
    "fading daylight across the slope",
    "stormy light raking across the scene",
    "dull overcast above the hill",
    "the last light of day on the rooftops",
]


# ---------------------------------------------------------------------------
# Captioning
# ---------------------------------------------------------------------------


def _pick(pool: list[str], key: str) -> str:
    """Deterministic pick from a pool, keyed on a hash of the filename + tag."""
    h = int(hashlib.md5(key.encode("utf-8")).hexdigest()[:8], 16)
    return pool[h % len(pool)]


def _match_first(filename: str, table: list[tuple[str, str]], fallback: str) -> str:
    """Return the first NAME_OVERRIDE phrase matching the filename; else fallback."""
    low = filename.lower()
    for pattern, phrase in table:
        if re.search(pattern, low):
            return phrase
    return fallback


def figure_subject(filename: str, gemini_kind: str) -> str:
    """Pick the noun phrase for a figure painting."""
    fallback = KIND_PHRASE.get(gemini_kind or "", "a single figure")
    return _match_first(filename, FIGURE_NAME_OVERRIDES, fallback)


def caption_for(filename: str, gemini_kind: str) -> dict:
    family = subject_family(filename, gemini_kind)
    if family == "figure":
        subject = figure_subject(filename, gemini_kind)
        lighting = _pick(LIGHTING_INDOOR, filename + "/l")
    elif family == "landscape":
        # Specific-name overrides first; rare generic fallback.
        subject = _match_first(filename, LANDSCAPE_NAME_OVERRIDES,
                               "a southern hillside landscape under heavy sky")
        lighting = _pick(LIGHTING_OUTDOOR, filename + "/l")
    elif family == "carcass":
        subject = _match_first(filename, CARCASS_NAME_OVERRIDES,
                               "a hanging carcass against a dark interior wall")
        lighting = _pick(LIGHTING_INDOOR, filename + "/l")
    else:  # still_life
        subject = _match_first(filename, STILL_LIFE_NAME_OVERRIDES,
                               STILL_LIFE_FALLBACK)
        lighting = _pick(LIGHTING_INDOOR, filename + "/l")

    palette = _pick(PALETTES, filename + "/p")
    brushwork = _pick(BRUSHWORK, filename + "/b")
    text = f"{TRIGGER}, {subject}, {lighting}, {palette}, {brushwork}, {SUFFIX}"
    return {
        "filename": filename,
        "trigger": TRIGGER,
        "subject_family": family,
        "subject_phrase": subject,
        "lighting": lighting,
        "palette": palette,
        "brushwork": brushwork,
        "suffix": SUFFIX,
        "caption": text,
    }


def main() -> int:
    review = json.loads(REVIEW.read_text(encoding="utf-8")) if REVIEW.exists() else {}
    available = sorted(p.name for p in RAW.glob("*.jpg"))

    records: list[dict] = []
    lines: list[str] = []
    word_counts = []
    families: dict[str, int] = {}
    for name in available:
        info = review.get(name, {})
        gemini_kind = info.get("subject_kind", "") if isinstance(info, dict) else ""
        rec = caption_for(name, gemini_kind)
        rec["word_count"] = len(rec["caption"].split())
        records.append(rec)
        lines.append(f"{name}\t{rec['caption']}")
        word_counts.append(rec["word_count"])
        families[rec["subject_family"]] = families.get(rec["subject_family"], 0) + 1

    TXT_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    JSON_OUT.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"captioned {len(records)} files")
    print(f"families: " + ", ".join(f"{k}={v}" for k, v in sorted(families.items())))
    print(f"word count: min={min(word_counts)} median={sorted(word_counts)[len(word_counts)//2]} max={max(word_counts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
