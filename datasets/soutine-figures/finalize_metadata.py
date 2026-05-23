"""Build metadata.csv for the Soutine dataset in the Renoir schema.

Renoir-schema columns (matches datasets/renoir-flowers/metadata.csv so the
shared build_gallery.py can consume both without modification):

    filename, title, year, collection, source_url,
    original_width, original_height, saved_width, saved_height,
    processed, processed_ops,
    flags_frame, flags_white_bg, flags_watermark,
    public_domain_status, direct_url, sha1, license_short,
    artist_recorded, credit_line, review_notes

Sources for Soutine:
    _commons_meta.csv      - sourcing fields (title, url, dimensions, sha1, license)
    processed.json         - crop / upscale audit + status
    review.json            - Gemini flags + notes

Year is parsed from titles via regex (4-digit year, 1893 to 1943 valid range
plus 1944-2099 catalogue dates). Collection is best-effort from title trail
"<collection name>" patterns and explicit institution keywords. Both fields
fall back to empty when not derivable.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMMONS_META = ROOT / "_commons_meta.csv"
PROCESSED = ROOT / "processed.json"
REVIEW = ROOT / "review.json"
RAW = ROOT / "raw"
OUT = ROOT / "metadata.csv"


# Year extraction. Soutine worked 1913-1943; accept anything 1850-2099
# (museum/auction catalogue dates can drift into the 2000s but the painting
# year is the earliest match in the title).
YEAR_RE = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")

# Collection hints. Match in priority order (first hit wins).
COLLECTION_HINTS = [
    (re.compile(r"barnes\s*foundation|barnes-foundation|cahim-soutine.*barnes", re.I), "Barnes Foundation, Philadelphia"),
    (re.compile(r"centre\s*pompidou|musee\s*national\s*d.*art\s*moderne|mnam", re.I), "Centre Pompidou, Paris"),
    (re.compile(r"musee.*orangerie|orangerie", re.I), "Musée de l'Orangerie, Paris"),
    (re.compile(r"princeton.*art.*museum|princeton.university.*art", re.I), "Princeton University Art Museum"),
    (re.compile(r"metropolitan.*museum.*art|met.museum|the.met|metmuseum", re.I), "Metropolitan Museum of Art, New York"),
    (re.compile(r"cleveland.*museum.*art|cma", re.I), "Cleveland Museum of Art"),
    (re.compile(r"worcester.*art.*museum", re.I), "Worcester Art Museum"),
    (re.compile(r"albertina", re.I), "Albertina, Vienna"),
    (re.compile(r"tel\s*aviv.*museum", re.I), "Tel Aviv Museum of Art"),
    (re.compile(r"israel.*museum", re.I), "Israel Museum, Jerusalem"),
    (re.compile(r"national.*gallery.*art.*washington|nga", re.I), "National Gallery of Art, Washington"),
    (re.compile(r"chartres.*musee.*beaux.*arts|musee.*beaux.*arts.*chartres", re.I), "Musée des Beaux-Arts de Chartres"),
    (re.compile(r"bemberg", re.I), "Fondation Bemberg, Toulouse"),
    (re.compile(r"thyssen", re.I), "Museo Thyssen-Bornemisza, Madrid"),
    (re.compile(r"musee.*beaux.*arts", re.I), "Musée des Beaux-Arts (unspecified)"),
]


def parse_year(title: str) -> str:
    m = YEAR_RE.search(title)
    return m.group(1) if m else ""


def parse_collection(title: str) -> str:
    for pat, name in COLLECTION_HINTS:
        if pat.search(title):
            return name
    return ""


def main() -> int:
    if not COMMONS_META.exists():
        sys.exit("_commons_meta.csv missing; run source_commons.py first")
    if not RAW.exists():
        sys.exit("raw/ missing")

    commons_rows: dict[str, dict] = {}
    with COMMONS_META.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            commons_rows[row["filename"]] = row

    processed = json.loads(PROCESSED.read_text(encoding="utf-8")) if PROCESSED.exists() else {}
    review = json.loads(REVIEW.read_text(encoding="utf-8")) if REVIEW.exists() else {}

    files_on_disk = sorted(p.name for p in RAW.glob("*.jpg"))
    print(f"{len(files_on_disk)} files on disk; {len(commons_rows)} rows in _commons_meta.csv")

    rows = []
    for fn in files_on_disk:
        c = commons_rows.get(fn, {})
        p = processed.get(fn, {})
        r = review.get(fn, {})

        title = c.get("title", "") or Path(fn).stem.replace("-", " ")
        year = parse_year(title)
        collection = parse_collection(title)
        license_short = c.get("license", "")
        # Soutine d. 1943; standard PD-old in most life+70 jurisdictions.
        pd_status = license_short or "public domain (Soutine d. 1943)"

        # Saved (current) dims: read from disk if processed, else from
        # commons_rows (downloaded dims).
        if p.get("status") == "done":
            saved_w = p.get("after_w", c.get("saved_width", ""))
            saved_h = p.get("after_h", c.get("saved_height", ""))
            processed_flag = "yes"
            processed_ops = ", ".join(p.get("operations", []))
        else:
            saved_w = c.get("saved_width", "")
            saved_h = c.get("saved_height", "")
            processed_flag = "no"
            processed_ops = ""

        rows.append({
            "filename": fn,
            "title": title,
            "year": year,
            "collection": collection,
            "source_url": c.get("source_url", ""),
            "original_width": c.get("original_width", ""),
            "original_height": c.get("original_height", ""),
            "saved_width": saved_w,
            "saved_height": saved_h,
            "processed": processed_flag,
            "processed_ops": processed_ops,
            "flags_frame": "yes" if r.get("has_physical_frame") else "no",
            "flags_white_bg": "yes" if r.get("has_white_or_paper_border") else "no",
            "flags_watermark": "yes" if r.get("has_watermark") else "no",
            "public_domain_status": pd_status,
            "direct_url": c.get("direct_url", ""),
            "sha1": c.get("sha1", ""),
            "license_short": license_short,
            "artist_recorded": "Chaim Soutine",
            "credit_line": "",
            "review_notes": r.get("notes", ""),
        })

    fieldnames = [
        "filename", "title", "year", "collection", "source_url",
        "original_width", "original_height", "saved_width", "saved_height",
        "processed", "processed_ops",
        "flags_frame", "flags_white_bg", "flags_watermark",
        "public_domain_status", "direct_url", "sha1", "license_short",
        "artist_recorded", "credit_line", "review_notes",
    ]
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {OUT} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
