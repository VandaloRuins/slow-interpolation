"""Expanded Commons search: scenes WITH flowers, not only floral still life.

Adds Renoir paintings where flowers are present in the composition but not
the dominant subject: gardens, figure-with-flowers, landscapes-with-blossom,
women picking flowers, mother-and-child garden scenes, etc.

Filters:
  KEEP: any title hit on a floral OR garden token AND on a Renoir token.
  REJECT: drawings, sketches, watercolours; obviously off-topic subjects
          (animals only, fruit-only still life, urban scenes without
          flowers).

De-duplicates against existing raw/ and rejected/non-renoir/ +
rejected/subject-mismatch/ + rejected/dupes/ by filename slug.
"""
from __future__ import annotations

import csv
import io
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
REJECTED = ROOT / "rejected"
META_OUT = ROOT / "_commons_meta_expand.csv"
SRC_META = ROOT / "_commons_meta.csv"

API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {
    "User-Agent": "slow-interpolation/renoir-dataset (info@romenewmediaweek.com)"
}
MIN_SHORT_SIDE = 768

# Broader queries: gardens, plein air, figure-in-garden, mother-and-child
# scenes that include flowers, plus any earlier rose / wisteria / lilac
# queries that we may have missed.
SEARCH_QUERIES = [
    "Renoir garden flowers",
    "Renoir flowering tree",
    "Renoir wisteria",
    "Renoir cherry blossom",
    "Renoir spring garden",
    "Renoir summer garden",
    "Renoir picking flowers",
    "Renoir gathering flowers",
    "Renoir mother child garden",
    "Renoir young girl flowers",
    "Renoir woman flowers",
    "Renoir bather flowers",
    "Renoir field flowers",
    "Renoir meadow flowers",
    "Renoir parc",
    "Renoir hollyhocks",
    "Renoir poppies",
    "Renoir Cagnes garden",
    "Renoir Essoyes garden",
    "Renoir rosebush",
    "Renoir flowering hedge",
    "Renoir flowering bush",
    "Renoir flower hat",
    "Renoir straw hat flowers",
    "Renoir bouquet hand",
    "Renoir umbrella flowers",
    "Renoir terrace flowers",
    "Renoir parterre",
    "Renoir floral landscape",
    "Renoir flowering branch",
]

# Strong "Renoir" signal: filename mentions the artist.
RENOIR_TOKENS = [
    "renoir", "auguste-renoir", "renoir-auguste", "renoir,", "renoir.",
    "pierre-auguste",
]

# Floral or garden signal anywhere in the title.
FLORAL_GARDEN_TOKENS = [
    # explicit flora
    "flower", "flowers", "bouquet", "rose", "roses", "fleur", "fleurs",
    "floral", "flowering", "blossom", "blooms", "bloom",
    "chrysanth", "dahlia", "peon", "anemone", "anémone", "gladiol", "tulip",
    "lilac", "lilas", "oeillet", "carnation", "geranium", "iris", "jasmin",
    "marigold", "primrose", "sunflower", "tournesol", "violet", "violette",
    "narcissus", "narcisse", "azalea", "magnolia", "wisteria", "glycine",
    "hollyhock", "poppy", "poppies", "coquelicot", "rosebush",
    # garden / setting signal
    "garden", "jardin", "parterre", "terrace", "terrasse", "park", "parc",
    "meadow", "champ", "field", "prairie",
    "essoyes", "cagnes", "Collettes",
]

# Hard rejects: not paintings, off-topic subjects, wrong medium.
REJECT_TOKENS = [
    "sketch", "study of woman", "drawing", "drawings",
    "watercolor", "watercolour", "aquarelle", "etching", "lithograph",
    "pastel",  # different medium
    "ceramic", "vase ceramic", "plate ", "plaque",
    "letter", "manuscript", "envelope",
    # photographs OF Renoir, not BY him
    "photograph of pierre", "renoir at his", "renoir in his",
    # not-by-Renoir items that pop up
    "after pierre", "imitator", "school of",
]

THUMB_HINTS = ["pinterestlarge", "!pinterest", "thumb"]

SLUG_NONWORD = re.compile(r"[^a-z0-9]+")


def slugify(s: str) -> str:
    s = s.lower()
    s = SLUG_NONWORD.sub("-", s).strip("-")
    return s[:120]


def has_token(text: str, tokens) -> bool:
    low = text.lower()
    return any(t in low for t in tokens)


def commons_search(query: str, limit: int = 60) -> list[str]:
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srnamespace": 6,
        "srlimit": limit,
        "format": "json",
    }
    r = requests.get(API, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return [h["title"] for h in r.json().get("query", {}).get("search", [])]


def fetch_imageinfo(titles: list[str]) -> dict[str, dict]:
    out = {}
    for i in range(0, len(titles), 40):
        batch = titles[i : i + 40]
        params = {
            "action": "query",
            "titles": "|".join(batch),
            "prop": "imageinfo",
            "iiprop": "url|size|mime|sha1|extmetadata",
            "format": "json",
        }
        r = requests.get(API, params=params, headers=HEADERS, timeout=60)
        r.raise_for_status()
        for page in r.json().get("query", {}).get("pages", {}).values():
            if "imageinfo" in page:
                out[page["title"]] = page["imageinfo"][0]
        time.sleep(0.3)
    return out


def already_known() -> set[str]:
    """Return slug names of every file we have already touched (kept,
    rejected, or moved)."""
    known = set()
    for sub in [RAW, REJECTED / "non-renoir", REJECTED / "subject-mismatch",
                REJECTED / "dupes"]:
        if sub.exists():
            for p in sub.glob("*.jpg"):
                known.add(p.stem)
    return known


def main() -> int:
    known = already_known()
    print(f"already-touched slugs: {len(known)}")

    candidates: dict[str, str] = {}
    for q in SEARCH_QUERIES:
        try:
            titles = commons_search(q)
        except Exception as e:
            print(f"[warn] search '{q}' failed: {e}")
            continue
        for t in titles:
            candidates.setdefault(t, q)
        print(f"[search] {q}: +{len(titles)} (unique {len(candidates)})")
        time.sleep(0.3)

    # Filter on title
    kept_titles = []
    for title, q in candidates.items():
        slug = slugify(title.replace("File:", "").rsplit(".", 1)[0])
        if slug in known:
            continue
        title_l = title.lower()
        if not has_token(title_l, RENOIR_TOKENS):
            continue
        if not has_token(title_l, FLORAL_GARDEN_TOKENS):
            continue
        if has_token(title_l, REJECT_TOKENS):
            continue
        if has_token(title_l, THUMB_HINTS):
            continue
        kept_titles.append(title)

    print(f"[filter] {len(kept_titles)} candidate titles past Renoir+flora filter")

    info = fetch_imageinfo(kept_titles)
    rows = []
    for title in kept_titles:
        ii = info.get(title)
        if not ii:
            continue
        w, h = ii.get("width", 0), ii.get("height", 0)
        if min(w, h) < MIN_SHORT_SIDE:
            continue
        slug = slugify(title.replace("File:", "").rsplit(".", 1)[0])
        dest = RAW / f"{slug}.jpg"
        if dest.exists():
            continue
        url = ii.get("url")
        try:
            r = requests.get(url, headers=HEADERS, timeout=120)
            r.raise_for_status()
            img = Image.open(io.BytesIO(r.content))
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(dest, format="JPEG", quality=95, optimize=True)
            sw, sh = img.size
            print(f"[dl] {dest.name} {sw}x{sh}")
            time.sleep(0.4)
        except Exception as e:
            print(f"[warn] dl failed {title}: {e}")
            continue
        em = ii.get("extmetadata", {})
        license_short = em.get("LicenseShortName", {}).get("value", "")
        usage = em.get("UsageTerms", {}).get("value", "")
        rows.append({
            "filename": dest.name,
            "title": title.replace("File:", "").rsplit(".", 1)[0],
            "source": "Wikimedia Commons",
            "source_url": f"https://commons.wikimedia.org/wiki/{title.replace(' ', '_')}",
            "direct_url": url,
            "original_width": w,
            "original_height": h,
            "saved_width": sw,
            "saved_height": sh,
            "license": f"{license_short} | {usage}".strip(" |"),
            "sha1": ii.get("sha1", ""),
            "matched_query": candidates.get(title, ""),
        })

    if rows:
        with META_OUT.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        # Append to _commons_meta.csv so finalize_metadata.py picks them up
        write_header = not SRC_META.exists()
        with SRC_META.open("a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            if write_header:
                w.writeheader()
            w.writerows(rows)
    print(f"[done] downloaded {len(rows)} new images")
    return 0


if __name__ == "__main__":
    sys.exit(main())
