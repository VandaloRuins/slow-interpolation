"""Build the final metadata.csv from the surviving raw/ images.

For each file present in raw/, look up its row in _commons_meta.csv, then
fetch fresh extmetadata from Commons (DateTimeOriginal / Credit / Artist /
ObjectName) to nail down year and collection. Write the brief-spec columns:

    filename, title, year, collection, source_url,
    original_width, original_height, public_domain_status

Plus a few helper columns for the captioning + training-playbook phases:

    direct_url, sha1, license_short, notes
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote

import requests

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
SRC_META = ROOT / "_commons_meta.csv"
OUT = ROOT / "metadata.csv"

API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "slow-interpolation/renoir-dataset (info@romenewmediaweek.com)"}

YEAR_RX = re.compile(r"\b(1[89]\d{2})\b")
RANGE_RX = re.compile(r"\b(1[89]\d{2})\s*[-–to]+\s*(\d{2,4})\b", re.IGNORECASE)
# Renoir lived 1841 to 1919. Anything outside that window is an accession
# number, a bookkeeping date, or noise. Treat 1862 to 1919 as the painting-
# active window (Renoir's first surviving works are c.1862).
PAINTING_MIN, PAINTING_MAX = 1862, 1919


def load_src() -> dict[str, dict]:
    rows = {}
    with SRC_META.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows[r["filename"]] = r
    return rows


def fetch_extmetadata_batch(titles: list[str]) -> dict[str, dict]:
    out = {}
    for i in range(0, len(titles), 30):
        batch = titles[i : i + 30]
        params = {
            "action": "query",
            "titles": "|".join(batch),
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "format": "json",
        }
        r = requests.get(API, params=params, headers=HEADERS, timeout=60)
        r.raise_for_status()
        for page in r.json().get("query", {}).get("pages", {}).values():
            if "imageinfo" not in page:
                continue
            out[page["title"]] = page["imageinfo"][0].get("extmetadata", {})
        time.sleep(0.4)
    return out


def html_to_text(s: str) -> str:
    """Strip simple HTML, decode entities, and drop the Wikibase QS:P...
    date assertions that Commons embeds inside hidden divs."""
    if not s:
        return ""
    # Wikibase date assertions like "QS:P571,+1912-00-00T00:00:00Z/9,P1480,Q5727902"
    # leak ISO dates that fool year-range regexes. Strip them outright.
    s = re.sub(r"QS:[^<\s]+", " ", s)
    s = re.sub(r"\+\d{4}-\d{2}-\d{2}T[\d:]+Z(?:/\d+)?", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"&nbsp;", " ", s)
    s = re.sub(r"&amp;", "&", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _valid_year(y: int) -> bool:
    return PAINTING_MIN <= y <= PAINTING_MAX


def parse_year(title: str, datetime_original: str) -> str:
    """Best-effort year. Try DateTimeOriginal first, fall back to title.

    Filter out accession numbers and post-mortem dates by clamping to
    Renoir's painting-active window (1862 to 1919).
    """
    candidates = [datetime_original or "", title or ""]
    for s in candidates:
        s = html_to_text(s)
        m = RANGE_RX.search(s)
        if m:
            y1_str, y2_str = m.group(1), m.group(2)
            if len(y2_str) == 2:
                y2_str = y1_str[:2] + y2_str
            y1, y2 = int(y1_str), int(y2_str)
            if _valid_year(y1) and _valid_year(y2):
                return f"{y1_str} to {y2_str}"
        # All bare years in the string, take first valid one.
        for raw in YEAR_RX.findall(s):
            y = int(raw)
            if _valid_year(y):
                return raw
    return "undated"


COLLECTION_HINTS = [
    ("barnes foundation", "Barnes Foundation"),
    ("art institute of chicago", "Art Institute of Chicago"),
    ("aic", "Art Institute of Chicago"),
    ("metropolitan museum", "Metropolitan Museum of Art"),
    ("met museum", "Metropolitan Museum of Art"),
    ("metmuseum", "Metropolitan Museum of Art"),
    ("cleveland museum", "Cleveland Museum of Art"),
    ("national gallery of art", "National Gallery of Art (Washington)"),
    ("nga", "National Gallery of Art (Washington)"),
    ("musee d'orsay", "Musée d'Orsay"),
    ("musée d'orsay", "Musée d'Orsay"),
    ("orangerie", "Musée de l'Orangerie"),
    ("musée des beaux-arts de la ville de paris", "Petit Palais, Paris"),
    ("petit palais", "Petit Palais, Paris"),
    ("clark art institute", "Clark Art Institute"),
    ("fogg museum", "Fogg Museum, Harvard"),
    ("fogg art museum", "Fogg Museum, Harvard"),
    ("dallas museum of art", "Dallas Museum of Art"),
    ("indianapolis museum", "Indianapolis Museum of Art"),
    ("buehrle", "Foundation E.G. Bührle Collection"),
    ("bührle", "Foundation E.G. Bührle Collection"),
    ("bhrle", "Foundation E.G. Bührle Collection"),
    ("museum of fine arts", "Museum of Fine Arts"),
    ("limoges", "Musée des Beaux-Arts de Limoges"),
    ("hermitage", "State Hermitage Museum"),
    ("pushkin", "Pushkin Museum"),
    ("national museum", "National Museum"),
    ("musee de l'orangerie", "Musée de l'Orangerie"),
    ("nelson-atkins", "Nelson-Atkins Museum"),
    ("guggenheim", "Solomon R. Guggenheim Museum"),
]


def parse_collection(title: str, credit: str) -> str:
    blob = (html_to_text(credit) + " | " + (title or "")).lower()
    for needle, label in COLLECTION_HINTS:
        if needle in blob:
            return label
    # auctioneer / sale signals — these are catalogue scans
    for needle, label in [("sotheby", "private collection (Sotheby's catalogue)"),
                           ("christie", "private collection (Christie's catalogue)"),
                           ("bonham", "private collection (Bonhams catalogue)")]:
        if needle in blob:
            return label
    return "unknown / unattributed"


def main() -> int:
    src = load_src()
    surviving = sorted(p.name for p in RAW.glob("*.jpg"))
    print(f"surviving images: {len(surviving)}")

    # Cross-ref via filename slug
    missing = [n for n in surviving if n not in src]
    if missing:
        print(f"[warn] {len(missing)} files have no row in _commons_meta.csv")
        for n in missing[:10]:
            print(f"   {n}")

    # Reconstruct the canonical Commons File: title from the description URL,
    # which always ends with /wiki/File:<exact-title>.
    rebuilt = []
    for n in surviving:
        if n not in src:
            continue
        url = src[n].get("source_url", "")
        if "/wiki/" not in url:
            continue
        title_full = unquote(url.split("/wiki/", 1)[1]).replace("_", " ")
        rebuilt.append((n, title_full))

    em_map: dict[str, dict] = {}
    titles_only = [t for _, t in rebuilt]
    em_map = fetch_extmetadata_batch(titles_only)
    print(f"fetched extmetadata for {len(em_map)} files")

    rows = []
    for n, title_full in rebuilt:
        em = em_map.get(title_full, {})
        s = src[n]
        # Use the slug-derived clean title from the source CSV. Commons
        # ObjectName is unreliable: it bundles multilingual variants ("title
        # ... label ... label ...") that mojibake when html-stripped.
        title_disp = s["title"]
        artist = html_to_text(em.get("Artist", {}).get("value", ""))
        credit = html_to_text(em.get("Credit", {}).get("value", ""))
        dt_orig = em.get("DateTimeOriginal", {}).get("value", "")
        license_short = em.get("LicenseShortName", {}).get("value", "") or s.get("license", "")
        usage = em.get("UsageTerms", {}).get("value", "")
        ls_lower = (license_short + " " + usage).lower()
        if "public domain" in ls_lower or "pd-" in ls_lower or "cc0" in ls_lower or "cc-0" in ls_lower:
            pd_status = "public domain (Renoir d. 1919)"
        elif "cc-by" in ls_lower or "cc by" in ls_lower:
            # Underlying painting is PD-old (Renoir d. 1919). The CC tag is the
            # reproduction-photo claim, which under US PD-art doctrine is moot
            # for faithful 2D reproductions but should be noted for credit.
            pd_status = f"underlying work PD; reproduction photo {license_short}"
        else:
            pd_status = f"verify: {license_short} / {usage}".strip()

        year = parse_year(s["title"], dt_orig)
        collection = parse_collection(s["title"], credit)

        rows.append({
            "filename": n,
            "title": title_disp.replace("File:", "").rsplit(".", 1)[0],
            "year": year,
            "collection": collection,
            "source_url": s.get("source_url", ""),
            "original_width": s.get("original_width", ""),
            "original_height": s.get("original_height", ""),
            "public_domain_status": pd_status,
            "direct_url": s.get("direct_url", ""),
            "sha1": s.get("sha1", ""),
            "license_short": license_short,
            "artist_recorded": artist,
            "credit_line": credit,
        })

    rows.sort(key=lambda r: r["filename"])
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"[done] wrote {len(rows)} rows -> {OUT.relative_to(ROOT.parent.parent)}")

    # Brief stats
    by_year = {}
    by_col = {}
    for r in rows:
        by_year[r["year"][:4] if r["year"] != "undated" else "undated"] = by_year.get(r["year"][:4] if r["year"] != "undated" else "undated", 0) + 1
        by_col[r["collection"]] = by_col.get(r["collection"], 0) + 1
    print("\nby decade-ish:")
    for k in sorted(by_year):
        print(f"  {k}: {by_year[k]}")
    print("\nby collection:")
    for k, v in sorted(by_col.items(), key=lambda kv: -kv[1]):
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
