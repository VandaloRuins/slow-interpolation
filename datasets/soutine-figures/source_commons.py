"""Source Soutine figure paintings from Wikimedia Commons.

Mirror of datasets/renoir-flowers/source_commons.py, inverted: instead of
keeping flower stills and rejecting figures, this script keeps figures /
portraits and rejects landscapes, carcasses (the famous Soutine subject we
do NOT want for figure-LoRA training), still lifes, fish, fowl.

Soutine (1893 to 1943) died long enough ago that all his work is PD-art in
most life+70 jurisdictions. Commons should have a substantial set under
"Category:Paintings by Chaim Soutine" plus sub-categories.

Outputs:
    datasets/soutine-figures/raw/<slug>.jpg  (gitignored)
    datasets/soutine-figures/_commons_meta.csv  (intermediate)
    datasets/soutine-figures/_commons_rejects.csv

Run from repo root: python datasets/soutine-figures/source_commons.py
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
import sys
import time
from pathlib import Path
from typing import Iterable

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
REJECTED = ROOT / "rejected"
RAW.mkdir(parents=True, exist_ok=True)
META_OUT = ROOT / "_commons_meta.csv"
REJECTS_OUT = ROOT / "_commons_rejects.csv"

API = "https://commons.wikimedia.org/w/api.php"
UA = "slow-interpolation/soutine-dataset (luca martinelli; info@romenewmediaweek.com)"
HEADERS = {"User-Agent": UA}

# Lowered from 768 to 600 for the Phase A.6 expansion pass: the canonical
# Soutine reproductions in Commons (Le Petit Patissier, Maria Lani,
# Le Patissier de Cagnes, Paulette Jourdain, La Folle, L'Homme en bleu,
# Seated Choir Boy) all sit at 600 to 750 short side. The apply_crops step
# upscales sub-768 keepers with LANCZOS to recover the SDXL training-bucket
# minimum. Style anchors tolerate this; subject realism would not.
MIN_SHORT_SIDE = 600

SEARCH_QUERIES = [
    # English / generic
    "Soutine portrait", "Soutine figure", "Soutine boy", "Soutine girl",
    "Soutine man", "Soutine woman", "Soutine child", "Soutine painting",
    "Chaim Soutine portrait", "Chaim Soutine figure", "Chaïm Soutine portrait",
    # Specific subject types (English)
    "Soutine bellboy", "Soutine groom", "Soutine page boy", "Soutine pastry cook",
    "Soutine choirboy", "Soutine communicant", "Soutine schoolboy",
    "Soutine praying man", "Soutine self-portrait", "Soutine valet",
    "Soutine bridegroom", "Soutine bride", "Soutine waiter", "Soutine cook",
    "Soutine seated woman", "Soutine standing man", "Soutine seated boy",
    # French (Soutine's working language; most museum titles are French)
    "Soutine petit patissier", "Soutine pâtissier", "Soutine pâtissier de Cagnes",
    "Soutine garçon d'étage", "Soutine garçon d'honneur",
    "Soutine enfant de choeur", "Soutine première communiante",
    "Soutine petit écolier", "Soutine homme en prière", "Soutine autoportrait",
    "Soutine femme", "Soutine homme", "Soutine jeune fille", "Soutine jeune anglaise",
    "Soutine Madeleine Castaing", "Soutine Maria Lani", "Soutine Eva",
    "Soutine Paulette Jourdain", "Soutine femme en bleu", "Soutine femme en rouge",
    "Soutine valet de chambre", "Soutine domestique", "Soutine servante",
    "Soutine homme assis", "Soutine femme assise", "Soutine fille assise",
    "Soutine la folle", "Soutine le fou", "Soutine vieillard", "Soutine vieille",
    # Italian (catalogue titles for many late-period works)
    "Soutine ritratto", "Soutine ragazzo", "Soutine ragazza", "Soutine bambino",
    "Soutine donna", "Soutine uomo", "Soutine piccolo pasticcere",
    "Soutine ragazzo di coro", "Soutine ragazzo ai piani", "Soutine fidanzata",
    "Soutine donna seduta", "Soutine donna in blu", "Soutine donna in rosso",
    "Soutine testimone di nozze",
    # German (Tel Aviv and Stuttgart hold several)
    "Soutine Bildnis", "Soutine Knabe", "Soutine Mädchen", "Soutine Junge",
    "Soutine Selbstbildnis",
    # Russian (Soutine's birth context; rare on Commons but worth probing)
    "Сутин портрет", "Сутин",
    # Style + period
    "Soutine 1918", "Soutine 1920", "Soutine 1925", "Soutine 1928", "Soutine 1929",
    "Soutine expressionism", "Soutine expressionnisme",
]

CATEGORIES = [
    "Category:Paintings by Chaim Soutine",
    "Category:Paintings by Chaïm Soutine",
    "Category:Portraits by Chaim Soutine",
    "Category:Portraits by Chaïm Soutine",
    "Category:Paintings by Chaim Soutine in the Metropolitan Museum of Art",
    "Category:Paintings by Chaim Soutine in the Barnes Foundation",
    "Category:Paintings by Chaim Soutine in the Centre Pompidou",
    "Category:Paintings by Chaim Soutine in the Cleveland Museum of Art",
    "Category:Paintings by Chaim Soutine in the Albertina",
    "Category:Paintings by Chaim Soutine in Israel",
    "Category:Self-portraits by Chaim Soutine",
    "Category:Self-portraits by Chaïm Soutine",
]

# Strong figure signals in the title. Bilingual (English + French) since
# Soutine worked in Paris and many catalogue titles are French.
FIGURE_TOKENS = [
    "portrait", "self-portrait", "self portrait", "autoportrait",
    "figure", "figures",
    "man ", "men ", "woman", "women", "boy", "girl", "child", "children",
    "homme", "femme", "garcon", "garçon", "fille", "enfant",
    "bellboy", "bell-boy", "bell boy", "groom",
    "page", "pageboy", "page boy", "page-boy",
    "pâtissier", "patissier", "pastry cook", "pastry-cook", "petit patissier",
    "choirboy", "choir-boy", "choir boy", "enfant de chœur", "enfant de choeur",
    "communicant", "communiante", "communion",
    "schoolboy", "school-boy", "écolier", "ecolier",
    "praying", "pray", "prière", "priere", "homme en prière",
    "valet", "servante", "maid", "domestique",
    "young", "jeune", "old", "vieux", "vieille",
    "anglais", "anglaise", "english",
    "lani", "castaing", "soutine",
    "personnage", "personnages",
]

# Hard rejects: subjects we do NOT want for a figure LoRA on neutral
# backgrounds. Carcasses are Soutine's famous side, but they are not
# figures and the dragged-meat texture would actively confuse the LoRA.
# Landscapes (Ceret, Cagnes, etc.), still lifes (gladioli, fish, poultry),
# religious-architecture pieces all out.
REJECT_TOKENS = [
    # carcass / animal / meat (the bête noire for figure training)
    "carcass", "carcasse", "carcassa", "beef", "boeuf", "boef",
    "ox ", "bœuf", "side of beef", "flayed", "écorché", "ecorche",
    "dindon", "turkey", "dinde", "rabbit", "lapin", "lièvre", "lievre",
    "hare", "pheasant", "faisan", "perdrix", "partridge",
    "poulet", "chicken", "fowl", "poultry", "volaille",
    "fish", "poisson", "hareng", "herring", "raie",
    # landscapes (Soutine's other major subject)
    "landscape", "landscapes", "paysage", "paysages",
    "ceret", "céret", "cagnes", "cagnes-sur-mer",
    "view of", "vue de", "vue sur", "village",
    "town", "ville", "hill", "colline", "tree", "arbre",
    "road", "route", "chemin", "river", "rivière",
    "house", "maison", "stairs", "escalier",
    "cathedral", "cathédrale", "cathedrale", "church", "église",
    # still life of objects only
    "still life", "still-life", "nature morte",
    "gladiolus", "gladioli", "glaïeul", "glaieul",
    "flower", "flowers", "bouquet", "fleur", "fleurs",
    "fruit", "fruits", "pomme", "apple", "citron", "lemon",
    "tomate", "tomato", "vase",
    # framed studies and non-paintings
    "sketch", "study of", "drawing", "dessin",
    "etching", "lithograph", "estampe",
    "frame", "framed",
]

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
    parts = [license_short, usage]
    return " | ".join(p for p in parts if p)


def download(info: dict, dest: Path) -> tuple[int, int]:
    url = info.get("url")
    r = requests.get(url, headers=HEADERS, timeout=120, stream=True)
    r.raise_for_status()
    raw = r.content
    img = Image.open(io.BytesIO(raw))
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.save(dest, format="JPEG", quality=95, optimize=True)
    return img.width, img.height


def main() -> int:
    candidates: dict[str, str] = {}

    # Categories first (catalogue-level, lowest noise)
    for cat in CATEGORIES:
        try:
            titles = category_members(cat)
        except Exception as e:
            print(f"[warn] category '{cat}' failed: {e}", file=sys.stderr)
            continue
        for t in titles:
            candidates.setdefault(t, cat)
        print(f"[category] {cat}: +{len(titles)} (total unique {len(candidates)})")
        time.sleep(0.4)

    # Keyword searches for stragglers
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

    # Heuristic title filter
    kept_titles, rejected_titles = [], []
    for title, q in candidates.items():
        title_l = title.lower()
        is_figure = has_token(title_l, FIGURE_TOKENS)
        is_rejected = has_token(title_l, REJECT_TOKENS) and not is_figure
        # Category-sourced titles get a benefit of the doubt: even without a
        # figure token in the title, they entered via a "Portraits by"
        # category and are likely on-target. Still apply REJECT_TOKENS.
        from_category = q.startswith("Category:")
        if is_rejected:
            rejected_titles.append((title, q, "reject-token"))
            continue
        if not is_figure and not from_category:
            rejected_titles.append((title, q, "no-figure-token"))
            continue
        kept_titles.append(title)

    print(f"[filter] kept {len(kept_titles)} / rejected {len(rejected_titles)} on title heuristic")

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
        if has_token(title.lower(), THUMB_HINTS):
            rejects.append({
                "title": title,
                "reason": "thumbnail-source",
                "url": ii.get("descriptionurl", ""),
            })
            continue
        slug = slugify(title.replace("File:", "").rsplit(".", 1)[0])
        dest = RAW / f"{slug}.jpg"
        # If this slug was already triaged out in a prior run (carcass,
        # not_soutine, photo, etc.), skip the re-download. The file sits
        # under rejected/<reason>/<slug>.jpg and re-fetching would just
        # re-import the same garbage.
        rejected_hit = None
        if REJECTED.exists():
            for r in REJECTED.rglob(f"{slug}.jpg"):
                rejected_hit = r
                break
        if rejected_hit:
            rejects.append({
                "title": title,
                "reason": f"already-triaged under {rejected_hit.parent.name}",
                "url": ii.get("descriptionurl", ""),
            })
            continue
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

    if rows:
        with META_OUT.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"[meta] {len(rows)} keepers -> {META_OUT.name}")
    if rejects:
        with REJECTS_OUT.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rejects[0].keys()))
            w.writeheader()
            w.writerows(rejects)
        print(f"[rejects] {len(rejects)} -> {REJECTS_OUT.name}")

    print(f"[done] kept={len(rows)} rejected={len(rejects)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
