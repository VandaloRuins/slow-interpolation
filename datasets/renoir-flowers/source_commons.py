"""Source Renoir floral paintings from Wikimedia Commons.

Queries Commons via the MediaWiki API for files whose title or category
suggests a Renoir flower painting, fetches imageinfo for each, filters by
resolution and obvious-fruit-only titles, downloads keepers, and emits
metadata rows for inclusion in metadata.csv.

Outputs:
    datasets/renoir-flowers/raw/<slug>.jpg  (gitignored)
    datasets/renoir-flowers/_commons_meta.csv  (intermediate, this script only)

Run from repo root: python datasets/renoir-flowers/source_commons.py
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sys
import time
from pathlib import Path
from typing import Iterable
from urllib.parse import quote

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
RAW.mkdir(parents=True, exist_ok=True)
META_OUT = ROOT / "_commons_meta.csv"
REJECTS_OUT = ROOT / "_commons_rejects.csv"

API = "https://commons.wikimedia.org/w/api.php"
UA = "slow-interpolation/renoir-dataset (luca martinelli; info@romenewmediaweek.com)"
HEADERS = {"User-Agent": UA}

MIN_SHORT_SIDE = 768

# Search queries: cast a wide net for floral subjects in Renoir's oeuvre.
# Each is a Commons search restricted to file namespace.
SEARCH_QUERIES = [
    "Renoir bouquet",
    "Renoir flowers vase",
    "Renoir roses",
    "Renoir chrysanthemums",
    "Renoir dahlias",
    "Renoir peonies",
    "Renoir anemones",
    "Renoir gladioli",
    "Renoir tulipes",
    "Renoir fleurs",
    "Renoir vase fleurs",
    "Renoir nature morte fleurs",
    "Renoir flowering",
    "Renoir bouquet de roses",
    "Renoir floral",
    "Renoir mixed flowers",
    "Renoir spring flowers",
    "Renoir bunch of flowers",
    "Renoir oeillets",
    "Renoir lilac",
    "Renoir geraniums",
]

# Strong floral signals in the title.
FLORAL_TOKENS = [
    "flower", "flowers", "bouquet", "rose", "roses", "fleur", "fleurs",
    "chrysanth", "dahlia", "peon", "anemone", "anémone", "gladiol", "tulip",
    "lilac", "lilas", "oeillet", "carnation", "geranium", "iris", "jasmin",
    "marigold", "primrose", "sunflower", "tournesol", "violet", "violette",
    "narcissus", "narcisse", "azalea", "magnolia", "wisteria", "glycine",
    "jardiniere", "jardinière", "floral",
]

# Hard rejects: portraits, figures, landscapes, animals, pure-fruit still
# lifes. Anything matched here is dropped before download.
REJECT_TOKENS = [
    "portrait", "girl", "boy", "woman", "man", "child", "children",
    "danse", "dance", "baigneuse", "bather", "nu ", "nude", "nus ",
    "torse", "jeune fille", "femme", "homme",
    "landscape", "paysage", "valley", "river", "bord de", "shore",
    "pheasant", "faisan", "perdrix", "partridge", "perdrices",
    "swan", "cygne",
    # pure-fruit-only stills (no flowers visible from title)
    "onion", "oignon", "courgette", "aubergine", "pepper", "poivron",
    "tomate", "tomato", "melon", "peach", "peche", "pêch", "cherries",
    "cerise", "fig", "figue", "plum", "prune", "pomegranate", "grenade",
    "almond", "amande", "strawberr", "fraise", "banana", "banane",
    "orange", "mandarin", "raisin", "grape", "pear", "poire", "apple",
    "pomme", "cauliflower", "chou-fleur", "artichoke", "artichaut",
    "ananas", "pineapple", "compotier",
    # objects, sketches, sculpture
    "pitcher", "cruche", "jug", "sucrier", "sugar bowl", "cafetiere",
    "cafetière", "coffee pot", "tasse", "cup", "teapot", "théière",
    "statuette", "faience", "faïence", "maillol",
    "sketch", "study of", "studies", "drawing",
    # framed pictures, photographs of paintings in situ
    "frame", "framed",
]

# Substrings that strongly hint a thumbnail / web-scraped scan, not an
# institutional file. Keep but flag for manual review.
THUMB_HINTS = ["pinterestlarge", "!pinterest", "thumb"]

SLUG_NONWORD = re.compile(r"[^a-z0-9]+")


def slugify(s: str) -> str:
    s = s.lower()
    s = SLUG_NONWORD.sub("-", s).strip("-")
    return s[:120] or hashlib.md5(s.encode()).hexdigest()[:16]


def has_token(title: str, tokens: Iterable[str]) -> bool:
    low = title.lower()
    return any(tok in low for tok in tokens)


def commons_search(query: str, limit: int = 50) -> list[str]:
    """Return File: titles for the query (file namespace)."""
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
    js = r.json()
    return [hit["title"] for hit in js.get("query", {}).get("search", [])]


def category_members(cat: str) -> list[str]:
    titles, cont = [], None
    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": cat,
            "cmlimit": 500,
            "cmtype": "file",
            "format": "json",
        }
        if cont:
            params["cmcontinue"] = cont
        r = requests.get(API, params=params, headers=HEADERS, timeout=30)
        r.raise_for_status()
        js = r.json()
        titles.extend(m["title"] for m in js.get("query", {}).get("categorymembers", []))
        cont = js.get("continue", {}).get("cmcontinue")
        if not cont:
            break
    return titles


def fetch_imageinfo(titles: list[str]) -> dict[str, dict]:
    """Batch imageinfo lookup. Returns {title: info_dict}."""
    out: dict[str, dict] = {}
    BATCH = 40
    for i in range(0, len(titles), BATCH):
        batch = titles[i : i + BATCH]
        params = {
            "action": "query",
            "titles": "|".join(batch),
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata|sha1",
            "iiurlwidth": 2048,
            "format": "json",
        }
        r = requests.get(API, params=params, headers=HEADERS, timeout=60)
        r.raise_for_status()
        js = r.json()
        for page in js.get("query", {}).get("pages", {}).values():
            if "imageinfo" not in page:
                continue
            out[page["title"]] = page["imageinfo"][0]
        time.sleep(0.4)
    return out


def good_size(info: dict) -> bool:
    w, h = info.get("width", 0), info.get("height", 0)
    return min(w, h) >= MIN_SHORT_SIDE


def pd_status(info: dict) -> str:
    em = info.get("extmetadata", {})
    license_short = em.get("LicenseShortName", {}).get("value", "")
    usage = em.get("UsageTerms", {}).get("value", "")
    # Renoir d. 1919 — anything correctly tagged is PD-old / PD-art.
    parts = [license_short, usage]
    return " | ".join(p for p in parts if p)


def download(info: dict, dest: Path) -> tuple[int, int]:
    url = info.get("url")
    r = requests.get(url, headers=HEADERS, timeout=120, stream=True)
    r.raise_for_status()
    raw = r.content
    # Re-encode to JPEG if not already (drops .tiff, .png, .webp etc to a
    # uniform training input). Also strips EXIF and probes for corruption.
    img = Image.open(io.BytesIO(raw))
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.save(dest, format="JPEG", quality=95, optimize=True)
    return img.width, img.height


def main() -> int:
    candidates: dict[str, str] = {}  # title -> first matching query
    for q in SEARCH_QUERIES:
        try:
            titles = commons_search(q)
        except Exception as e:
            print(f"[warn] search '{q}' failed: {e}", file=sys.stderr)
            continue
        for t in titles:
            candidates.setdefault(t, q)
        print(f"[search] {q}: +{len(titles)} (total unique {len(candidates)})")
        time.sleep(0.4)

    # Heuristic filter on titles
    kept_titles, rejected_titles = [], []
    for title, q in candidates.items():
        # Must look floral OR have come from an explicitly floral query and
        # not look like an obvious non-floral subject.
        title_l = title.lower()
        is_floral = has_token(title_l, FLORAL_TOKENS)
        is_rejected = has_token(title_l, REJECT_TOKENS) and not is_floral
        if is_rejected or not is_floral:
            rejected_titles.append((title, q, "title-filter"))
            continue
        kept_titles.append(title)

    print(f"[filter] kept {len(kept_titles)} / rejected {len(rejected_titles)} on title heuristic")

    # Batch fetch imageinfo
    info = fetch_imageinfo(kept_titles)

    rows, rejects = [], []
    for title, q in candidates.items():
        if title not in info:
            continue
        ii = info[title]
        if not good_size(ii):
            rejects.append({
                "title": title,
                "reason": f"resolution {ii.get('width')}x{ii.get('height')}",
                "url": ii.get("descriptionurl", ""),
            })
            continue
        # Lazy: skip files explicitly flagged thumb (PinterestLarge etc)
        if has_token(title.lower(), THUMB_HINTS):
            rejects.append({
                "title": title,
                "reason": "thumbnail-source (pinterest scrape)",
                "url": ii.get("descriptionurl", ""),
            })
            continue
        slug = slugify(title.replace("File:", "").rsplit(".", 1)[0])
        dest = RAW / f"{slug}.jpg"
        if dest.exists():
            w, h = Image.open(dest).size
        else:
            try:
                w, h = download(ii, dest)
                print(f"[dl] {dest.name} {w}x{h}")
                time.sleep(0.6)
            except Exception as e:
                print(f"[warn] download {title}: {e}", file=sys.stderr)
                rejects.append({"title": title, "reason": f"download-failed: {e}",
                                "url": ii.get("descriptionurl", "")})
                continue
        rows.append({
            "filename": dest.name,
            "title": title.replace("File:", "").rsplit(".", 1)[0],
            "source": "Wikimedia Commons",
            "source_url": ii.get("descriptionurl", ""),
            "direct_url": ii.get("url", ""),
            "original_width": ii.get("width"),
            "original_height": ii.get("height"),
            "saved_width": w,
            "saved_height": h,
            "license": pd_status(ii),
            "sha1": ii.get("sha1", ""),
            "matched_query": q,
        })

    # Save intermediate metadata
    if rows:
        with META_OUT.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    if rejects:
        with REJECTS_OUT.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["title", "reason", "url"])
            w.writeheader()
            w.writerows(rejects)

    print(f"[done] kept {len(rows)} images / {len(rejects)} rejected at imageinfo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
