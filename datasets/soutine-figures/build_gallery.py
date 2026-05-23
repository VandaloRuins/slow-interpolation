"""Build a self-contained mosaic gallery of the Soutine dataset.

Each card is an image; click to flip and reveal the caption. Reads
metadata.csv + captions.json, writes gallery.html next to raw/, opens it
in the default browser.

Card ordering: perceptual-hash clustering pulls near-duplicates adjacent
in the mosaic so they are easy to spot and trim. The cluster id is also
emitted on each card as a small badge when the cluster has > 1 member.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
import webbrowser
from html import escape
from pathlib import Path

from PIL import Image
import imagehash  # type: ignore

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
META = ROOT / "metadata.csv"
CAPTIONS = ROOT / "captions.json"
OUT = ROOT / "gallery.html"
PHASH_CACHE = ROOT / "phashes.json"


def port_for_dataset(name: str) -> int:
    """Deterministic per-dataset port in the 8765 to 8864 range.

    Lets multiple gallery servers (renoir, soutine, future LoRAs) coexist
    without colliding on a single shared port. Both build_gallery.py and
    serve.py call this with `ROOT.name` so the HTML's probe URL matches
    the port the server actually binds.
    """
    h = int(hashlib.md5(name.encode("utf-8")).hexdigest()[:8], 16)
    return 8765 + (h % 100)


PORT = port_for_dataset(ROOT.name)

# Hamming distance below which two images are treated as near-duplicates.
# Matches the dedup.py threshold; tighten if false-positives appear.
DUP_THRESHOLD = 10


def compute_phashes(filenames: list[str]) -> dict[str, str]:
    """Return {filename: phash_hex}. Cached to phashes.json keyed by
    (size, mtime) per file so re-runs are near-instant."""
    Image.MAX_IMAGE_PIXELS = None
    cache: dict[str, dict] = {}
    if PHASH_CACHE.exists():
        try:
            cache = json.loads(PHASH_CACHE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    out: dict[str, str] = {}
    misses = 0
    for fn in filenames:
        fp = RAW / fn
        if not fp.exists():
            continue
        st = fp.stat()
        key = f"{st.st_size}:{int(st.st_mtime)}"
        entry = cache.get(fn)
        if entry and entry.get("key") == key and entry.get("phash"):
            out[fn] = entry["phash"]
            continue
        try:
            with Image.open(fp) as im:
                h = imagehash.phash(im)
        except Exception as e:
            print(f"[phash skip] {fn}: {e}", file=sys.stderr)
            continue
        hex_ = str(h)
        out[fn] = hex_
        cache[fn] = {"key": key, "phash": hex_}
        misses += 1
    PHASH_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    print(f"phash: {len(out)} files ({misses} (re)computed)")
    return out


def _hex_to_phash(s: str) -> imagehash.ImageHash:
    return imagehash.hex_to_hash(s)


def cluster_order(filenames: list[str], phashes: dict[str, str]) -> tuple[list[str], dict[str, int]]:
    """Return (ordered_filenames, {filename: cluster_id}).

    Union-find groups files whose pHash Hamming distance is below
    DUP_THRESHOLD. Within each cluster, members are sorted alphabetically.
    Clusters are ordered by their first member's filename so the overall
    ordering looks like the alphabetical default with near-duplicates
    pulled together.
    """
    files = [f for f in filenames if f in phashes]
    n = len(files)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    hashes = [_hex_to_phash(phashes[f]) for f in files]
    for i in range(n):
        for j in range(i + 1, n):
            if (hashes[i] - hashes[j]) <= DUP_THRESHOLD:
                union(i, j)

    clusters: dict[int, list[str]] = {}
    for i, f in enumerate(files):
        clusters.setdefault(find(i), []).append(f)
    # Within-cluster: alphabetical. Cross-cluster: by first member.
    sorted_clusters = sorted(
        (sorted(members) for members in clusters.values()),
        key=lambda c: c[0]
    )
    ordered: list[str] = []
    cluster_of: dict[str, int] = {}
    cid = 0
    for members in sorted_clusters:
        for m in members:
            ordered.append(m)
            cluster_of[m] = cid
        cid += 1
    # Files with no pHash (decode failure) appended at the end.
    missing = [f for f in filenames if f not in phashes]
    for f in missing:
        ordered.append(f)
        cluster_of[f] = cid
        cid += 1

    multi = sum(1 for members in sorted_clusters if len(members) > 1)
    dups = sum(len(members) - 1 for members in sorted_clusters if len(members) > 1)
    print(f"clusters: {len(sorted_clusters)} total, {multi} with >1 member, {dups} potential duplicates")
    return ordered, cluster_of


def main() -> int:
    meta = {r["filename"]: r for r in csv.DictReader(META.open(encoding="utf-8"))}
    caps = {c["filename"]: c for c in json.load(CAPTIONS.open(encoding="utf-8"))}

    # Filter to files that actually exist in raw/. metadata.csv can lag the
    # filesystem when the user removes images via the × button (the file
    # moves but metadata.csv isn't rewritten); listing raw/ is the source
    # of truth for what to show.
    on_disk = {p.name for p in RAW.glob("*.jpg")}
    stale = [fn for fn in meta if fn not in on_disk]
    if stale:
        print(f"skipping {len(stale)} cards whose file isn't in raw/: " + ", ".join(stale[:3]) +
              (" ..." if len(stale) > 3 else ""))
    meta = {fn: m for fn, m in meta.items() if fn in on_disk}

    # Perceptual-hash clustering: pulls near-duplicates adjacent in the
    # mosaic. Cached to phashes.json so re-runs cost nothing unless the
    # underlying JPEG bytes changed.
    phashes = compute_phashes(list(meta.keys()))
    ordered_filenames, cluster_of = cluster_order(list(meta.keys()), phashes)
    # Count cluster sizes so the JS can render an indicator only on multi-
    # member clusters (singletons need no indicator).
    cluster_sizes: dict[int, int] = {}
    for cid in cluster_of.values():
        cluster_sizes[cid] = cluster_sizes.get(cid, 0) + 1

    cards = []
    for fn in ordered_filenames:
        if fn not in meta:
            continue
        m = meta[fn]
        c = caps.get(fn, {})
        title = m["title"] or fn
        year = m["year"]
        coll = m["collection"]
        caption = c.get("caption", "")
        url = m["source_url"]
        cards.append({
            "filename": fn,
            "title": title,
            "year": year,
            "collection": coll,
            "caption": caption,
            "source_url": url,
            "processed": m.get("processed", "no") == "yes",
            "processed_ops": m.get("processed_ops", ""),
            "flag_frame": m.get("flags_frame", "no") == "yes",
            "flag_white_bg": m.get("flags_white_bg", "no") == "yes",
            "flag_watermark": m.get("flags_watermark", "no") == "yes",
            "saved_w": m.get("saved_width", ""),
            "saved_h": m.get("saved_height", ""),
            "original_w": m.get("original_width", ""),
            "original_h": m.get("original_height", ""),
            "cluster_id": cluster_of.get(fn, -1),
            "cluster_size": cluster_sizes.get(cluster_of.get(fn, -1), 1),
        })

    cards_json = json.dumps(cards, ensure_ascii=False)
    html = TEMPLATE.replace("__CARDS__", cards_json).replace(
        "__PORT__", str(PORT)
    ).replace(
        "__COUNT__", str(len(cards))
    )
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT}")
    webbrowser.open(OUT.as_uri())
    return 0


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Soutine Figures Dataset (__COUNT__ images)</title>
<style>
  :root {
    --bg: #0e0b08;
    --ink: #f0e8d8;
    --ink-dim: #b8a98a;
    --accent: #c4a86a;
    --rose: #b6708a;
    --paper: #1a1612;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0;
    background: radial-gradient(ellipse at top, #1b1612 0%, var(--bg) 60%);
    color: var(--ink);
    font-family: "Cormorant Garamond", "Garamond", Georgia, serif;
    min-height: 100vh;
  }
  header {
    text-align: center;
    padding: 56px 24px 24px;
    border-bottom: 1px solid rgba(196,168,106,0.18);
  }
  header h1 {
    margin: 0 0 8px 0;
    font-weight: 500;
    font-size: clamp(28px, 4vw, 44px);
    letter-spacing: 0.04em;
    color: var(--ink);
  }
  header h1 em {
    font-style: italic;
    color: var(--rose);
  }
  header p {
    margin: 0;
    color: var(--ink-dim);
    font-size: 15px;
    letter-spacing: 0.06em;
  }
  header p a {
    color: var(--accent);
    text-decoration: none;
    border-bottom: 1px dotted rgba(196,168,106,0.4);
  }
  .legend {
    font-size: 13px;
    color: var(--ink-dim);
    margin-top: 18px;
    letter-spacing: 0.04em;
    font-style: italic;
  }
  main {
    padding: 36px clamp(16px, 4vw, 56px);
    column-gap: 16px;
    column-count: 1;
  }
  @media (min-width: 640px)  { main { column-count: 2; } }
  @media (min-width: 960px)  { main { column-count: 3; } }
  @media (min-width: 1280px) { main { column-count: 4; } }
  @media (min-width: 1680px) { main { column-count: 5; } }
  @media (min-width: 2100px) { main { column-count: 6; } }

  .card {
    break-inside: avoid;
    margin: 0 0 16px 0;
    perspective: 1400px;
    cursor: pointer;
    position: relative;
  }
  .card-inner {
    position: relative;
    width: 100%;
    transition: transform 0.7s cubic-bezier(0.4, 0.0, 0.2, 1);
    transform-style: preserve-3d;
  }
  .card.flipped .card-inner {
    transform: rotateY(180deg);
  }
  .face {
    backface-visibility: hidden;
    -webkit-backface-visibility: hidden;
    border-radius: 4px;
    overflow: hidden;
    box-shadow:
      0 1px 2px rgba(0,0,0,0.4),
      0 8px 24px rgba(0,0,0,0.5),
      inset 0 0 0 1px rgba(196,168,106,0.08);
    background: var(--paper);
  }
  .face.front {
    position: relative;
  }
  .face.front img {
    display: block;
    width: 100%;
    height: auto;
    transition: filter 0.4s ease;
  }
  /* Crop preview: card front becomes the cropped aspect; img is scaled and
     translated so the cropped region fills it. Real file is unchanged
     until apply_browser_crops.py runs. */
  .face.front.has-crop {
    overflow: hidden;
  }
  .face.front.has-crop img {
    position: absolute;
    max-width: none;
    /* width / left / top set inline by JS based on the saved crop bbox */
  }
  .face.front.has-crop::before {
    content: "PREVIEW";
    position: absolute;
    bottom: 8px; right: 8px;
    z-index: 2;
    background: rgba(20,40,20,0.85);
    color: #b6e0a6;
    font-size: 9px;
    letter-spacing: 0.15em;
    padding: 3px 7px;
    border-radius: 999px;
    pointer-events: none;
    font-family: monospace;
  }
  .card:hover .face.front img {
    filter: brightness(1.05) saturate(1.05);
  }
  .meta-strip {
    position: absolute;
    left: 0; right: 0; bottom: 0;
    padding: 28px 14px 12px 14px;
    background: linear-gradient(to top, rgba(14,11,8,0.92) 0%, rgba(14,11,8,0.0) 100%);
    color: var(--ink);
    font-size: 12px;
    letter-spacing: 0.04em;
    opacity: 0;
    transition: opacity 0.3s ease;
    pointer-events: none;
  }
  .card:hover .meta-strip { opacity: 1; }
  .meta-strip .t {
    display: block;
    font-style: italic;
    color: var(--ink);
    font-size: 14px;
    margin-bottom: 2px;
    line-height: 1.2;
  }
  .meta-strip .y {
    color: var(--accent);
    font-size: 11px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }
  .face.back {
    position: absolute;
    inset: 0;
    transform: rotateY(180deg);
    padding: 22px 22px 18px 22px;
    color: var(--ink);
    background:
      linear-gradient(135deg, rgba(196,168,106,0.07), rgba(182,112,138,0.05)),
      var(--paper);
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    font-family: "Cormorant Garamond", Georgia, serif;
  }
  .back-trigger {
    font-family: "Cormorant Garamond", Georgia, serif;
    font-style: italic;
    color: var(--accent);
    font-size: 22px;
    margin-bottom: 10px;
    letter-spacing: 0.04em;
  }
  .back-trigger::before {
    content: "stn,";
    color: var(--rose);
    margin-right: 6px;
    font-weight: 600;
  }
  .back-trigger.is-trigger::before { content: ""; margin: 0; }
  .back-caption {
    font-size: 15px;
    line-height: 1.55;
    color: var(--ink);
    font-style: italic;
    overflow-y: auto;
    flex: 1;
  }
  .back-footer {
    margin-top: 14px;
    padding-top: 12px;
    border-top: 1px solid rgba(196,168,106,0.2);
    font-size: 11px;
    color: var(--ink-dim);
    letter-spacing: 0.06em;
    line-height: 1.5;
  }
  .back-footer .t {
    color: var(--ink);
    font-style: italic;
    font-size: 13px;
    margin-bottom: 4px;
    display: block;
  }
  .back-footer a {
    color: var(--accent);
    text-decoration: none;
    border-bottom: 1px dotted rgba(196,168,106,0.4);
  }
  .back-footer a:hover { color: var(--rose); }
  .corner {
    position: absolute;
    top: 10px; right: 14px;
    font-size: 11px;
    color: var(--ink-dim);
    letter-spacing: 0.08em;
    font-family: "Cormorant Garamond", Georgia, serif;
    font-style: italic;
  }
  .badge {
    position: absolute;
    top: 8px; left: 8px;
    display: flex;
    gap: 4px;
    z-index: 2;
    pointer-events: none;
  }
  .badge .pill {
    display: inline-block;
    padding: 2px 7px;
    font-size: 10px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    border-radius: 999px;
    color: var(--ink);
    background: rgba(14,11,8,0.7);
    border: 1px solid rgba(196,168,106,0.35);
    backdrop-filter: blur(4px);
  }
  .badge .pill.cropped { color: var(--accent); border-color: var(--accent); }
  .badge .pill.frame   { color: #e8a87c; border-color: #e8a87c; }
  .badge .pill.bg      { color: #c4d1ff; border-color: #c4d1ff; }
  .badge .pill.water   { color: var(--rose); border-color: var(--rose); }
  .badge .pill.dup {
    color: #ffb37a;
    border-color: #ffb37a;
    background: rgba(60,30,10,0.7);
    font-weight: 600;
  }
  /* Subtle separator between clusters in the column flow so the eye
     groups duplicates together. */
  .card[data-cluster-end="1"] { margin-bottom: 28px; }
  .ops-line {
    font-size: 10px;
    color: var(--ink-dim);
    margin-top: 8px;
    letter-spacing: 0.04em;
    font-family: monospace;
    font-style: normal;
    line-height: 1.4;
    word-break: break-word;
  }
  .filters {
    text-align: center;
    margin-top: 16px;
    font-size: 12px;
    letter-spacing: 0.08em;
    color: var(--ink-dim);
  }
  .filters button {
    background: transparent;
    color: var(--ink-dim);
    border: 1px solid rgba(196,168,106,0.2);
    padding: 5px 12px;
    margin: 0 4px 6px 4px;
    cursor: pointer;
    font: inherit;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    border-radius: 999px;
    transition: all 0.2s ease;
  }
  .filters button:hover,
  .filters button.active {
    color: var(--accent);
    border-color: var(--accent);
  }
  .filters button[data-filter="user-review"] { color: #e8c87c; border-color: rgba(232,200,124,0.3); }
  .filters button[data-filter="user-review"]:hover,
  .filters button[data-filter="user-review"].active { border-color: #e8c87c; }
  .filters button[data-filter="user-crop"] { color: #b6e0a6; border-color: rgba(182,224,166,0.3); }
  .filters button[data-filter="user-crop"]:hover,
  .filters button[data-filter="user-crop"].active { border-color: #b6e0a6; }

  /* Per-card flag buttons, top-right corner */
  .flag-bar {
    position: absolute;
    top: 8px; right: 8px;
    display: flex;
    gap: 6px;
    z-index: 3;
  }
  .flag-bar .flag-btn {
    width: 30px; height: 30px;
    border-radius: 50%;
    border: 1px solid rgba(255,255,255,0.25);
    background: rgba(14,11,8,0.7);
    color: var(--ink-dim);
    font-size: 16px;
    line-height: 28px;
    text-align: center;
    cursor: pointer;
    padding: 0;
    backdrop-filter: blur(4px);
    transition: all 0.18s ease;
    user-select: none;
  }
  .flag-bar .flag-btn:hover {
    transform: scale(1.1);
  }
  .flag-bar .flag-btn[data-flag="remove"]:hover,
  .flag-bar .flag-btn[data-flag="remove"].active {
    color: #ff5757;
    border-color: #ff5757;
    background: rgba(80,0,0,0.6);
  }
  .flag-bar .flag-btn[data-flag="review"]:hover,
  .flag-bar .flag-btn[data-flag="review"].active {
    color: #e8c87c;
    border-color: #e8c87c;
    background: rgba(60,40,0,0.6);
  }

  /* Card removal animation: fade and collapse out of the masonry flow */
  .card.removing {
    transition: opacity 0.35s ease, transform 0.35s ease;
    opacity: 0;
    transform: scale(0.92);
    pointer-events: none;
  }
  .card.user-review .face.front {
    box-shadow: 0 0 0 3px #e8c87c,
      0 1px 2px rgba(0,0,0,0.4),
      0 8px 24px rgba(0,0,0,0.5);
  }

  /* Toolbar: counts + export */
  .toolbar {
    position: sticky;
    top: 0;
    z-index: 50;
    background: rgba(14,11,8,0.92);
    backdrop-filter: blur(8px);
    border-bottom: 1px solid rgba(196,168,106,0.18);
    padding: 10px 24px;
    display: flex;
    gap: 16px;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    letter-spacing: 0.08em;
    color: var(--ink-dim);
  }
  .toolbar .count {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .toolbar .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
  .toolbar .dot.remove { background: #ff5757; }
  .toolbar .dot.review { background: #e8c87c; }
  .toolbar button {
    background: transparent;
    color: var(--accent);
    border: 1px solid var(--accent);
    border-radius: 999px;
    padding: 5px 14px;
    cursor: pointer;
    font: inherit;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }
  .toolbar button:hover { background: var(--accent); color: var(--bg); }
  .toolbar button.clear { color: var(--ink-dim); border-color: rgba(196,168,106,0.3); }
  .toolbar button.clear:hover { background: var(--paper); color: var(--ink); border-color: var(--ink-dim); }
  .sync-badge {
    display: inline-block;
    padding: 3px 9px;
    font-size: 10px;
    letter-spacing: 0.18em;
    font-family: monospace;
    border-radius: 999px;
    border: 1px solid;
    cursor: help;
  }
  .sync-badge.ok      { color: #b6e0a6; border-color: #b6e0a6; background: rgba(20,40,20,0.4); }
  .sync-badge.err     { color: #ff8a8a; border-color: #ff8a8a; background: rgba(60,10,10,0.4); }
  .sync-badge.offline { color: #e8c87c; border-color: rgba(232,200,124,0.5); background: rgba(60,40,0,0.3); }

  /* Undo toast */
  .toast {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%) translateY(120%);
    z-index: 2000;
    background: rgba(20,16,12,0.96);
    border: 1px solid rgba(196,168,106,0.4);
    color: var(--ink);
    padding: 12px 22px;
    border-radius: 999px;
    display: flex;
    align-items: center;
    gap: 14px;
    font-size: 13px;
    letter-spacing: 0.04em;
    box-shadow: 0 12px 32px rgba(0,0,0,0.5);
    backdrop-filter: blur(8px);
    transition: transform 0.3s cubic-bezier(0.4,0,0.2,1), opacity 0.3s ease;
    opacity: 0;
  }
  .toast.show {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }
  .toast .toast-msg {
    font-style: italic;
    color: var(--ink-dim);
  }
  .toast .toast-msg b {
    font-style: normal;
    color: var(--ink);
    font-weight: 500;
    font-family: monospace;
    font-size: 12px;
  }
  .toast button {
    background: transparent;
    color: var(--accent);
    border: 1px solid var(--accent);
    border-radius: 999px;
    padding: 4px 12px;
    cursor: pointer;
    font: inherit;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 11px;
  }
  .toast button:hover { background: var(--accent); color: var(--bg); }
  .toast .toast-progress {
    position: absolute;
    bottom: 2px;
    left: 16px;
    right: 16px;
    height: 1px;
    background: rgba(196,168,106,0.2);
    overflow: hidden;
  }
  .toast .toast-progress::after {
    content: "";
    position: absolute;
    inset: 0;
    background: var(--accent);
    transform-origin: left;
    animation: toast-bar 5s linear forwards;
  }
  @keyframes toast-bar {
    from { transform: scaleX(1); }
    to   { transform: scaleX(0); }
  }

  /* Manual cropper modal */
  .cropper {
    position: fixed;
    inset: 0;
    z-index: 1000;
    background: rgba(8,6,4,0.94);
    display: none;
    flex-direction: column;
    backdrop-filter: blur(8px);
  }
  .cropper.open { display: flex; }
  .cropper-bar {
    padding: 12px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    color: var(--ink);
    font-size: 13px;
    letter-spacing: 0.06em;
    border-bottom: 1px solid rgba(196,168,106,0.2);
    background: rgba(14,11,8,0.7);
  }
  .cropper-bar .title {
    font-style: italic;
    color: var(--ink-dim);
    max-width: 50vw;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .cropper-bar .info {
    font-family: monospace;
    font-size: 11px;
    color: var(--accent);
  }
  .cropper-bar button {
    background: transparent;
    color: var(--ink-dim);
    border: 1px solid rgba(196,168,106,0.3);
    padding: 6px 14px;
    cursor: pointer;
    font: inherit;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    border-radius: 999px;
    margin-left: 6px;
  }
  .cropper-bar button:hover { color: var(--accent); border-color: var(--accent); }
  .cropper-bar button.save { color: #b6e0a6; border-color: rgba(182,224,166,0.4); }
  .cropper-bar button.save:hover { color: #fff; background: #4a7a3a; border-color: #b6e0a6; }
  .cropper-bar button.cancel { color: #ff8a8a; border-color: rgba(255,138,138,0.3); }
  .cropper-bar button.cancel:hover { color: #fff; background: #7a3a3a; border-color: #ff8a8a; }
  .cropper-bar button.rot { font-size: 16px; padding: 4px 10px; }
  .cropper-bar .rot-pill {
    font-family: monospace;
    font-size: 11px;
    color: var(--ink-dim);
    padding: 4px 8px;
    border: 1px solid rgba(196,168,106,0.18);
    border-radius: 999px;
    margin-left: 6px;
  }
  .cropper-stage {
    flex: 1;
    position: relative;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .cropper-canvas-wrap {
    position: relative;
    max-width: 95%;
    max-height: 95%;
  }
  .cropper-canvas-wrap img {
    display: block;
    max-width: 95vw;
    max-height: calc(100vh - 90px);
    width: auto;
    height: auto;
    user-select: none;
    -webkit-user-drag: none;
  }
  .crop-rect {
    position: absolute;
    border: 1.5px solid var(--accent);
    box-shadow: 0 0 0 9999px rgba(0,0,0,0.55);
    box-sizing: border-box;
    cursor: move;
  }
  .crop-rect::before,
  .crop-rect::after {
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
  }
  .crop-rect::before {
    border-left: 1px dashed rgba(196,168,106,0.5);
    border-right: 1px dashed rgba(196,168,106,0.5);
    left: 33.33%;
    right: 33.33%;
    width: 33.33%;
  }
  .crop-rect::after {
    border-top: 1px dashed rgba(196,168,106,0.5);
    border-bottom: 1px dashed rgba(196,168,106,0.5);
    top: 33.33%;
    bottom: 33.33%;
    height: 33.33%;
  }
  .crop-handle {
    position: absolute;
    width: 14px;
    height: 14px;
    background: var(--accent);
    border: 2px solid #0e0b08;
    border-radius: 50%;
    z-index: 2;
  }
  .crop-handle[data-h="tl"] { top: -8px; left: -8px; cursor: nwse-resize; }
  .crop-handle[data-h="tr"] { top: -8px; right: -8px; cursor: nesw-resize; }
  .crop-handle[data-h="bl"] { bottom: -8px; left: -8px; cursor: nesw-resize; }
  .crop-handle[data-h="br"] { bottom: -8px; right: -8px; cursor: nwse-resize; }
  .crop-handle[data-h="t"]  { top: -8px; left: 50%; transform: translateX(-50%); cursor: ns-resize; }
  .crop-handle[data-h="b"]  { bottom: -8px; left: 50%; transform: translateX(-50%); cursor: ns-resize; }
  .crop-handle[data-h="l"]  { top: 50%; left: -8px; transform: translateY(-50%); cursor: ew-resize; }
  .crop-handle[data-h="r"]  { top: 50%; right: -8px; transform: translateY(-50%); cursor: ew-resize; }

  /* Scissors button on card */
  .flag-bar .flag-btn[data-flag="crop"]:hover,
  .flag-bar .flag-btn[data-flag="crop"].active {
    color: #b6e0a6;
    border-color: #b6e0a6;
    background: rgba(20,40,20,0.6);
  }
  .card.user-crop .face.front {
    box-shadow: 0 0 0 3px #b6e0a6,
      0 1px 2px rgba(0,0,0,0.4),
      0 8px 24px rgba(0,0,0,0.5);
  }
  footer {
    text-align: center;
    padding: 32px 24px 60px;
    color: var(--ink-dim);
    font-size: 13px;
    letter-spacing: 0.05em;
  }
  footer code {
    color: var(--accent);
    font-family: "Cormorant Garamond", Georgia, serif;
    font-style: italic;
  }
</style>
</head>
<body>
<div id="file-warning" style="display:none; background:#3a2a1a; color:#ffc88a; text-align:center; padding:12px 16px; font-size:13px; letter-spacing:0.04em; gap:14px; align-items:center; justify-content:center; flex-wrap:wrap;">
  <span id="file-warning-msg">
    Opened via <code>file://</code> — saves are local-only, rotation will not work.
  </span>
  <button id="switch-synced" style="display:none; padding:7px 16px; border-radius:999px; background:#3a6b3a; color:#fff; border:1px solid #6ec46e; cursor:pointer; font:inherit; letter-spacing:0.1em; text-transform:uppercase; font-size:12px;">
    Switch to synced version →
  </button>
  <code id="file-warning-cmd" style="display:none; color:#ffd9a8;">py -3.11 datasets/soutine-figures/serve.py</code>
  <button id="retest-server" style="display:none; padding:5px 12px; border-radius:999px; background:transparent; color:#ffc88a; border:1px solid rgba(255,200,140,0.4); cursor:pointer; font:inherit; letter-spacing:0.1em; text-transform:uppercase; font-size:11px;">
    Re-check
  </button>
</div>
<header>
  <h1>Soutine Figures <em>— Dataset Mosaic</em></h1>
  <p>__COUNT__ figure paintings sourced from Wikimedia Commons for the <code style="color:var(--accent);font-family:inherit;font-style:italic">stn</code> SDXL LoRA</p>
  <p class="legend">Click any image to flip and read its caption. Per-card buttons: <b>✂</b> open manual cropper · <b>⚐</b> flag for frame review · <b>×</b> remove from dataset (file moves to <code>rejected/user-removed/</code>; 5-second undo). Shortcuts while hovering a card: <b>R</b>=remove, <b>F</b>=flag, <b>C</b>=open cropper.</p>
  <div class="filters">
    <button data-filter="all" class="active">All</button>
    <button data-filter="processed">Cropped / upscaled</button>
    <button data-filter="frame">Was framed</button>
    <button data-filter="bg">White background</button>
    <button data-filter="water">Watermark</button>
    <button data-filter="user-review">My: review frame</button>
    <button data-filter="user-crop">My: cropped</button>
  </div>
</header>
<div class="toolbar">
  <span id="sync-badge" class="sync-badge offline" title="">LOCAL-ONLY</span>
  <button id="reconnect-btn" style="display:none; padding:4px 10px; border-radius:999px; background:transparent; color:#ff8a8a; border:1px solid #ff8a8a; cursor:pointer; font-family:monospace; font-size:11px; letter-spacing:0.1em; text-transform:uppercase;" title="Re-test the connection to gallery-server">Reconnect</button>
  <span class="count"><span class="dot review"></span> <span id="review-count">0</span> flagged for frame review</span>
  <span class="count"><span class="dot" style="background:#b6e0a6"></span> <span id="crop-count">0</span> manual crops</span>
  <button id="export-flags">Export flags + crops</button>
  <button id="clear-flags" class="clear">Clear all flags</button>
</div>

<!-- Undo toast -->
<div class="toast" id="undo-toast" role="status" aria-live="polite">
  <span class="toast-msg" id="undo-msg">removed <b id="undo-filename">—</b></span>
  <button id="undo-btn">Undo</button>
  <div class="toast-progress"></div>
</div>

<!-- Manual cropper modal -->
<div class="cropper" id="cropper" role="dialog" aria-label="Manual cropper">
  <div class="cropper-bar">
    <span class="title" id="cropper-title">—</span>
    <span class="info" id="cropper-info">—</span>
    <span>
      <button class="rot" id="cropper-rot-ccw" title="Rotate 90° counter-clockwise">↺</button>
      <button class="rot" id="cropper-rot-cw" title="Rotate 90° clockwise">↻</button>
      <span class="rot-pill" id="cropper-rotation">0°</span>
      <button id="cropper-reset">Reset</button>
      <button id="cropper-clear">Clear saved</button>
      <button class="save" id="cropper-save">Save crop</button>
      <button class="cancel" id="cropper-cancel">Cancel</button>
    </span>
  </div>
  <div class="cropper-stage">
    <div class="cropper-canvas-wrap" id="cropper-wrap">
      <img id="cropper-img" alt="">
      <div class="crop-rect" id="crop-rect">
        <div class="crop-handle" data-h="tl"></div>
        <div class="crop-handle" data-h="tr"></div>
        <div class="crop-handle" data-h="bl"></div>
        <div class="crop-handle" data-h="br"></div>
        <div class="crop-handle" data-h="t"></div>
        <div class="crop-handle" data-h="b"></div>
        <div class="crop-handle" data-h="l"></div>
        <div class="crop-handle" data-h="r"></div>
      </div>
    </div>
  </div>
</div>
<main id="grid"></main>
<footer>
  <code>slow-interpolation / Soutine LoRA training set</code>
</footer>

<script>
const CARDS = __CARDS__;

function el(tag, attrs={}, ...children) {
  const e = document.createElement(tag);
  for (const k in attrs) {
    if (k === "class") e.className = attrs[k];
    else if (k === "html") e.innerHTML = attrs[k];
    else if (k.startsWith("on") && typeof attrs[k] === "function") e.addEventListener(k.substring(2), attrs[k]);
    else e.setAttribute(k, attrs[k]);
  }
  for (const c of children) {
    if (c == null) continue;
    e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return e;
}

// File:// banner with server-availability detection. The port is per-dataset
// (deterministically derived from the dataset folder name in build_gallery.py)
// so multiple gallery servers can coexist on different ports without state
// collision. If the server for THIS dataset is actually running, show the
// green "Switch to synced version" button.
const SYNCED_PORT = __PORT__;
const SYNCED_URL = `http://localhost:${SYNCED_PORT}/gallery.html`;

function pingSyncedServer(timeoutMs) {
  return new Promise(resolve => {
    const t = setTimeout(() => resolve(false), timeoutMs || 1200);
    // no-cors: the response is opaque but the promise still resolves
    // when the network round-trip succeeds, so we get a clean yes/no.
    fetch(`http://localhost:${SYNCED_PORT}/api/state`, {mode: "no-cors", cache: "no-store"})
      .then(() => { clearTimeout(t); resolve(true); })
      .catch(() => { clearTimeout(t); resolve(false); });
  });
}

async function refreshFileWarning() {
  const banner = document.getElementById("file-warning");
  if (!banner) return;
  const msg = document.getElementById("file-warning-msg");
  const btn = document.getElementById("switch-synced");
  const cmd = document.getElementById("file-warning-cmd");
  const retest = document.getElementById("retest-server");
  banner.style.display = "flex";
  msg.textContent = "Checking for the local server…";
  btn.style.display = "none";
  cmd.style.display = "none";
  retest.style.display = "none";
  const alive = await pingSyncedServer(1200);
  if (alive) {
    msg.innerHTML = "Server is running. Click to switch to the synced version:";
    btn.style.display = "inline-block";
  } else {
    msg.innerHTML = 'Opened via <code>file://</code> — saves are local-only, rotation will not work. Run:';
    cmd.style.display = "inline-block";
    retest.style.display = "inline-block";
  }
}

if (location.protocol === "file:") {
  refreshFileWarning();
  document.addEventListener("click", (ev) => {
    if (ev.target.id === "switch-synced") {
      window.location.href = SYNCED_URL;
    } else if (ev.target.id === "retest-server") {
      refreshFileWarning();
    }
  });
}

// Cache of rotated data URLs: key = filename + ":" + deg. Declared here
// (before the card-build loop) because applyFlagToCard -> applyCropPreview
// -> rotatedURL reads from it during card construction.
const ROT_CACHE = new Map();

const LS_KEY = "soutine-gallery-flags-v1";
const LS_CROPS = "soutine-gallery-crops-v1";

// Disk-backed state: when the gallery is served from http://localhost via
// serve.py, every change auto-syncs to gallery-state.json on disk. The
// disk file is the source of truth; localStorage is a cache + offline
// fallback. SYNC_OK tracks whether the API is reachable; if not, we fall
// back to localStorage only and surface a warning.
const HAS_SERVER = location.protocol !== "file:";
let SYNC_OK = false;        // flips true after a successful GET /api/state
let SYNC_LAST_ERR = null;

function loadFlags() {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || "{}"); }
  catch { return {}; }
}
function loadCrops() {
  try { return JSON.parse(localStorage.getItem(LS_CROPS) || "{}"); }
  catch { return {}; }
}
function persistLocal() {
  localStorage.setItem(LS_KEY, JSON.stringify(FLAGS));
  localStorage.setItem(LS_CROPS, JSON.stringify(CROPS));
}
function saveFlags(f) { FLAGS = f; persistLocal(); syncFull(); }
function saveCrops(c) { CROPS = c; persistLocal(); syncFull(); }

let FLAGS = loadFlags();
let CROPS = loadCrops();

// Debounce full replacements so a flurry of clicks doesn't hammer the API.
let SYNC_TIMER = null;
function syncFull() {
  if (!HAS_SERVER) return;
  clearTimeout(SYNC_TIMER);
  SYNC_TIMER = setTimeout(() => {
    fetch("/api/state", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({flags: FLAGS, crops: CROPS}),
    }).then(r => r.json()).then(j => {
      SYNC_OK = (j && j.status === "ok");
      SYNC_LAST_ERR = SYNC_OK ? null : (j && j.error) || "sync error";
      updateSyncBadge();
    }).catch(err => {
      SYNC_OK = false;
      SYNC_LAST_ERR = String(err);
      updateSyncBadge();
    });
  }, 300);
}

function updateSyncBadge() {
  const b = document.getElementById("sync-badge");
  const r = document.getElementById("reconnect-btn");
  if (!b) return;
  if (!HAS_SERVER) {
    b.className = "sync-badge offline";
    b.textContent = "LOCAL-ONLY (run serve.py)";
    b.title = "Saves live in browser localStorage only. Run serve.py and reopen via http://localhost to persist to disk.";
    if (r) r.style.display = "none";
  } else if (SYNC_OK) {
    b.className = "sync-badge ok";
    b.textContent = "SYNCED";
    b.title = "Every change is written to gallery-state.json on disk.";
    if (r) r.style.display = "none";
  } else {
    b.className = "sync-badge err";
    b.textContent = "SYNC ERROR";
    b.title = SYNC_LAST_ERR || "could not reach /api/state";
    if (r) r.style.display = "inline-block";
  }
}

// Wire the reconnect button once the DOM is ready.
window.addEventListener("DOMContentLoaded", () => {
  const r = document.getElementById("reconnect-btn");
  if (r) {
    r.addEventListener("click", () => {
      hydrateFromDisk();
      syncFull();  // also flush in-memory state if there's anything pending
    });
  }
});

// Boot-time state hydration. If the disk file has any entries, it overrides
// localStorage (the disk is the source of truth across origins/refreshes).
// If the disk file is empty and localStorage has entries, upload them once
// so future devices/origins see the same state (migration aid).
async function hydrateFromDisk() {
  if (!HAS_SERVER) {
    SYNC_OK = false;
    updateSyncBadge();
    return;
  }
  try {
    const r = await fetch("/api/state", {cache: "no-store"});
    if (!r.ok) throw new Error("status " + r.status);
    const disk = await r.json();
    const diskHasData = (Object.keys(disk.flags || {}).length +
                         Object.keys(disk.crops || {}).length) > 0;
    if (diskHasData) {
      FLAGS = disk.flags || {};
      CROPS = disk.crops || {};
      persistLocal();
    } else {
      // disk is empty: push localStorage up as a one-shot migration
      const localHasData = (Object.keys(FLAGS).length + Object.keys(CROPS).length) > 0;
      if (localHasData) {
        await fetch("/api/state", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({flags: FLAGS, crops: CROPS}),
        });
      }
    }
    SYNC_OK = true;
    SYNC_LAST_ERR = null;
  } catch (err) {
    SYNC_OK = false;
    SYNC_LAST_ERR = String(err);
  }
  updateSyncBadge();
  // Refresh every card visible to reflect any disk-loaded state.
  document.querySelectorAll(".card").forEach(card => {
    applyFlagToCard(card, card.dataset.filename);
  });
  updateCounts();
}

function updateCounts() {
  let v = 0;
  for (const k in FLAGS) {
    if (FLAGS[k] === "review") v++;
  }
  document.getElementById("review-count").textContent = v;
  document.getElementById("crop-count").textContent = Object.keys(CROPS).length;
}

function applyFlagToCard(card, fn) {
  card.classList.remove("user-review", "user-crop");
  const f = FLAGS[fn];
  if (f === "review") card.classList.add("user-review");
  if (CROPS[fn]) card.classList.add("user-crop");
  const tags = (card.dataset.tags || "").split(" ").filter(t => !t.startsWith("user-"));
  if (f) tags.push("user-" + f);
  if (CROPS[fn]) tags.push("user-crop");
  card.dataset.tags = tags.join(" ");
  const reviewBtn = card.querySelector('.flag-btn[data-flag="review"]');
  const cropBtn   = card.querySelector('.flag-btn[data-flag="crop"]');
  if (reviewBtn) reviewBtn.classList.toggle("active", f === "review");
  if (cropBtn) cropBtn.classList.toggle("active", !!CROPS[fn]);
  applyCropPreview(card, fn);
}

// Live in-browser crop preview. Reshapes the card's front face to the
// cropped aspect ratio and translates / scales the img so only the
// cropped region is visible. If the saved crop has a rotation, the img's
// src is swapped for a rotated data URL (cached). The JPEG on disk is
// unchanged until apply_browser_crops.py runs over the exported JSON.
function applyCropPreview(card, fn) {
  const front = card.querySelector(".face.front");
  const img = front && front.querySelector("img");
  if (!front || !img) return;
  const inner = card.querySelector(".card-inner");
  const back = card.querySelector(".face.back");
  const crop = CROPS[fn];

  const resetStyles = () => {
    front.classList.remove("has-crop");
    front.style.aspectRatio = "";
    img.style.position = "";
    img.style.width = "";
    img.style.height = "";
    img.style.left = "";
    img.style.top = "";
    img.style.maxWidth = "";
  };

  const rotation = crop && crop.rotation ? crop.rotation : 0;

  // Source URL: original raw/ path, or rotated data URL when rotation set.
  // Only swap the img.src when truly needed; otherwise just wait for load.
  const setSrcAndRun = (then) => {
    rotatedURL(fn, rotation).then(url => {
      const isDataNow = img.src.startsWith("data:");
      const srcIsCorrect = rotation === 0 ? !isDataNow : (img.src === url);
      const runWhenReady = () => {
        if (img.complete && img.naturalWidth) then();
        else {
          const onLoad = () => { img.removeEventListener("load", onLoad); then(); };
          img.addEventListener("load", onLoad);
        }
      };
      if (srcIsCorrect) {
        runWhenReady();
      } else {
        const onLoad = () => { img.removeEventListener("load", onLoad); then(); };
        img.addEventListener("load", onLoad);
        img.src = url;
        // Synchronously-cached re-set: cover the case where load won't fire.
        if (img.complete && img.naturalWidth && img.src === url) {
          img.removeEventListener("load", onLoad);
          then();
        }
      }
    }).catch(() => {/* keep current src */});
  };

  if (!crop) {
    resetStyles();
    setSrcAndRun(() => {
      requestAnimationFrame(() => {
        if (inner && back) {
          const h = front.offsetHeight;
          if (h > 0) { inner.style.minHeight = h + "px"; back.style.height = h + "px"; }
        }
      });
    });
    return;
  }

  const apply = () => {
    const natW = img.naturalWidth, natH = img.naturalHeight;
    if (!natW || !natH) return;
    const {x, y, w, h} = crop;
    const ar = (w * natW) / (h * natH);
    front.classList.add("has-crop");
    front.style.aspectRatio = String(ar);
    img.style.position = "absolute";
    img.style.maxWidth = "none";
    img.style.width = (10000 / w) + "%";
    img.style.height = "auto";
    img.style.left = (-100 * x / w) + "%";
    img.style.top  = (-100 * y / h) + "%";
    requestAnimationFrame(() => {
      if (inner && back) {
        const ho = front.offsetHeight;
        if (ho > 0) { inner.style.minHeight = ho + "px"; back.style.height = ho + "px"; }
      }
    });
  };
  setSrcAndRun(apply);
}

const grid = document.getElementById("grid");
// Mark the last card of each cluster so CSS can add a small gap after it.
for (let i = 0; i < CARDS.length; i++) {
  const next = CARDS[i + 1];
  CARDS[i]._lastInCluster = (!next || next.cluster_id !== CARDS[i].cluster_id);
}
for (const c of CARDS) {
  // The caption is the full "stn, ..." sentence; split off the first segment
  // ("stn, [subject]") for the trigger styling.
  const cap = c.caption || "";
  const [firstSeg, ...restSegs] = cap.split(", ");
  // firstSeg is "stn" alone; subject begins at restSegs[0]
  const subject = restSegs.length ? restSegs[0] : "";
  const rest = restSegs.slice(1).join(", ");

  const card = el("div", {class: "card", title: "Click to flip"});

  const badges = el("div", {class: "badge"});
  if (c.cluster_size > 1) badges.appendChild(el("span", {class: "pill dup", title: "Near-duplicate group — sibling card(s) are adjacent in the mosaic"}, "dup " + c.cluster_size));
  if (c.processed) badges.appendChild(el("span", {class: "pill cropped"}, "cropped"));
  if (c.flag_frame) badges.appendChild(el("span", {class: "pill frame"}, "frame"));
  if (c.flag_white_bg) badges.appendChild(el("span", {class: "pill bg"}, "white-bg"));
  if (c.flag_watermark) badges.appendChild(el("span", {class: "pill water"}, "watermark"));

  const removeBtn = el("button", {
    class: "flag-btn",
    "data-flag": "remove",
    title: "Mark for removal",
    "aria-label": "Mark for removal"
  }, "×");
  const reviewBtn = el("button", {
    class: "flag-btn",
    "data-flag": "review",
    title: "Flag for frame / artefact review",
    "aria-label": "Flag for frame review"
  }, "⚐");
  const cropBtn = el("button", {
    class: "flag-btn",
    "data-flag": "crop",
    title: "Manually crop this image",
    "aria-label": "Manual crop"
  }, "✂");
  const flagBar = el("div", {class: "flag-bar"}, cropBtn, reviewBtn, removeBtn);

  const front = el("div", {class: "face front"},
    badges,
    flagBar,
    el("img", {src: "raw/" + c.filename, loading: "lazy", alt: c.title}),
    el("div", {class: "meta-strip"},
      el("span", {class: "t"}, c.title),
      el("span", {class: "y"}, c.year + " · " + (c.collection || "—")),
    ),
  );

  // × removes the file (move to rejected/user-removed/ on disk, fade card)
  removeBtn.addEventListener("click", (ev) => {
    ev.stopPropagation();
    removeCard(card, c.filename, c.title);
  });
  reviewBtn.addEventListener("click", (ev) => {
    ev.stopPropagation();
    const kind = "review";
    if (FLAGS[c.filename] === kind) delete FLAGS[c.filename];
    else FLAGS[c.filename] = kind;
    saveFlags(FLAGS);
    applyFlagToCard(card, c.filename);
    updateCounts();
  });
  cropBtn.addEventListener("click", (ev) => {
    ev.stopPropagation();
    openCropper(c.filename, c.title);
  });

  const opsLine = c.processed_ops
    ? el("div", {class: "ops-line"}, "processed: " + c.processed_ops)
    : null;

  const back = el("div", {class: "face back"},
    el("div", {class: "corner"}, c.year || ""),
    el("div", {class: "back-trigger"}, subject),
    el("div", {class: "back-caption"}, rest),
    el("div", {class: "back-footer"},
      el("span", {class: "t"}, c.title),
      el("span", {}, c.collection || ""),
      c.source_url ? el("br") : null,
      c.source_url ? el("a", {href: c.source_url, target: "_blank", rel: "noopener"}, "source on Wikimedia Commons →") : null,
      opsLine,
    ),
  );

  const inner = el("div", {class: "card-inner"}, front, back);
  card.appendChild(inner);

  card.addEventListener("click", (ev) => {
    // Let anchor clicks pass through without flipping.
    if (ev.target.closest("a")) return;
    card.classList.toggle("flipped");
  });

  // Ensure the back face has the same height as the front by waiting for the
  // image to load and copying the rendered height to the card.
  const img = front.querySelector("img");
  img.addEventListener("load", () => {
    const h = front.offsetHeight;
    inner.style.minHeight = h + "px";
    back.style.height = h + "px";
  });

  // Tag the card for filtering
  const tags = [];
  if (c.processed) tags.push("processed");
  if (c.flag_frame) tags.push("frame");
  if (c.flag_white_bg) tags.push("bg");
  if (c.flag_watermark) tags.push("water");
  card.dataset.tags = tags.join(" ");
  card.dataset.filename = c.filename;
  card.dataset.clusterId = c.cluster_id;
  card.dataset.clusterSize = c.cluster_size;
  if (c._lastInCluster && c.cluster_size > 1) card.dataset.clusterEnd = "1";
  applyFlagToCard(card, c.filename);

  grid.appendChild(card);
}
updateCounts();
updateSyncBadge();
hydrateFromDisk();

// Filter buttons
const buttons = document.querySelectorAll(".filters button");
buttons.forEach(btn => {
  btn.addEventListener("click", () => {
    buttons.forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    const f = btn.dataset.filter;
    document.querySelectorAll(".card").forEach(card => {
      const tags = (card.dataset.tags || "").split(" ");
      card.style.display = (f === "all" || tags.includes(f)) ? "" : "none";
    });
  });
});

// Export flags + crops JSON
document.getElementById("export-flags").addEventListener("click", () => {
  const review = [];
  for (const k in FLAGS) {
    if (FLAGS[k] === "review") review.push(k);
  }
  review.sort();
  const payload = {
    exported_at: new Date().toISOString(),
    review_frame: review,
    crops: CROPS,   // {filename: {x, y, w, h, rotation?} in percent}
    total_review: review.length,
    total_crops: Object.keys(CROPS).length,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "gallery-flags.json";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

// Clear flags
document.getElementById("clear-flags").addEventListener("click", () => {
  if (!confirm("Clear all flags AND saved crops? This cannot be undone.")) return;
  FLAGS = {};
  CROPS = {};
  saveFlags(FLAGS);
  saveCrops(CROPS);
  document.querySelectorAll(".card").forEach(card => {
    applyFlagToCard(card, card.dataset.filename);
  });
  updateCounts();
});

// ===== Manual cropper =====
const cropper = document.getElementById("cropper");
const cropperImg = document.getElementById("cropper-img");
const cropperWrap = document.getElementById("cropper-wrap");
const cropRect = document.getElementById("crop-rect");
const cropperTitle = document.getElementById("cropper-title");
const cropperInfo = document.getElementById("cropper-info");
const cropperRotPill = document.getElementById("cropper-rotation");
// {filename, imgW, imgH, x, y, w, h, rotation} -- x,y,w,h PERCENT, rotation in degrees CW (0/90/180/270)
let cropState = null;

function rotatedURL(filename, deg) {
  if (!deg) return Promise.resolve("raw/" + filename);
  const key = filename + ":" + deg;
  if (ROT_CACHE.has(key)) return Promise.resolve(ROT_CACHE.get(key));
  return new Promise((resolve, reject) => {
    const im = new Image();
    // crossOrigin only helps when served over http with CORS. For file://,
    // setting it actively breaks the load. Leave it unset and rely on
    // same-origin canvas readback (works under http://localhost, fails
    // gracefully under file:// — see catch in toDataURL).
    im.onload = () => {
      const w = im.naturalWidth, h = im.naturalHeight;
      const c = document.createElement("canvas");
      if (deg === 90 || deg === 270) { c.width = h; c.height = w; }
      else { c.width = w; c.height = h; }
      const ctx = c.getContext("2d");
      ctx.save();
      if (deg === 90)      { ctx.translate(h, 0); ctx.rotate( Math.PI / 2); }
      else if (deg === 180){ ctx.translate(w, h); ctx.rotate( Math.PI); }
      else if (deg === 270){ ctx.translate(0, w); ctx.rotate(-Math.PI / 2); }
      ctx.drawImage(im, 0, 0);
      ctx.restore();
      let url;
      try {
        url = c.toDataURL("image/jpeg", 0.92);
      } catch (e) {
        const isFile = location.protocol === "file:";
        reject(new Error(isFile
          ? `Canvas readback blocked by file:// origin. Run \`python datasets/soutine-figures/serve.py\` and reopen at http://localhost:${SYNCED_PORT}/gallery.html`
          : ("Canvas readback failed: " + e.message)));
        return;
      }
      ROT_CACHE.set(key, url);
      resolve(url);
    };
    im.onerror = () => reject(new Error("image failed to load: " + filename));
    im.src = "raw/" + filename;
  });
}

function updateRotationPill() {
  cropperRotPill.textContent = (cropState ? cropState.rotation : 0) + "°";
}

function openCropper(filename, title) {
  cropperTitle.textContent = title;
  cropperInfo.textContent = "loading…";
  cropper.classList.add("open");
  const existing = CROPS[filename];
  const rotation = existing ? (existing.rotation || 0) : 0;
  const bb = existing
    ? {x: existing.x, y: existing.y, w: existing.w, h: existing.h}
    : {x: 5, y: 5, w: 90, h: 90};
  cropState = {filename, imgW: 0, imgH: 0, rotation, ...bb};
  updateRotationPill();
  loadCropperImage();
}

function loadCropperImage() {
  if (!cropState) return;
  const setupFromImg = () => {
    if (!cropperImg.naturalWidth) return;
    cropState.imgW = cropperImg.naturalWidth;
    cropState.imgH = cropperImg.naturalHeight;
    requestAnimationFrame(() => {
      placeCropRect();
      updateCropInfo();
    });
  };
  cropperImg.onload = setupFromImg;
  cropperImg.onerror = () => { cropperInfo.textContent = "image failed to load"; };
  rotatedURL(cropState.filename, cropState.rotation).then(url => {
    // Cache-bust raw URLs but not data URLs (rotated -> data:image/jpeg, no need)
    const next = url.startsWith("data:") ? url : (url + "?v=" + Date.now());
    if (cropperImg.src !== next) {
      cropperImg.src = next;
      if (cropperImg.complete && cropperImg.naturalWidth) setupFromImg();
    } else {
      setupFromImg();
    }
  }).catch((err) => {
    cropperInfo.textContent = (err && err.message) || "rotation render failed";
  });
}

function rotateCropper(deltaDeg) {
  if (!cropState) return;
  cropState.rotation = ((cropState.rotation + deltaDeg) % 360 + 360) % 360;
  // Bbox is defined in the rotated coordinate frame; reset on rotation
  // so the user re-defines it cleanly. (Mapping the old bbox through the
  // rotation transform is doable but rarely what the user wants.)
  cropState.x = 5; cropState.y = 5; cropState.w = 90; cropState.h = 90;
  updateRotationPill();
  loadCropperImage();
}

function placeCropRect() {
  if (!cropState) return;
  const r = cropperImg.getBoundingClientRect();
  const wr = cropperWrap.getBoundingClientRect();
  if (r.width === 0 || r.height === 0) return;  // not visible yet
  const left = r.left - wr.left;
  const top = r.top - wr.top;
  cropRect.style.left = (left + (cropState.x / 100) * r.width) + "px";
  cropRect.style.top = (top + (cropState.y / 100) * r.height) + "px";
  cropRect.style.width = (cropState.w / 100 * r.width) + "px";
  cropRect.style.height = (cropState.h / 100 * r.height) + "px";
}

function updateCropInfo() {
  if (!cropState) return;
  const px = Math.round(cropState.x / 100 * cropState.imgW);
  const py = Math.round(cropState.y / 100 * cropState.imgH);
  const pw = Math.round(cropState.w / 100 * cropState.imgW);
  const ph = Math.round(cropState.h / 100 * cropState.imgH);
  cropperInfo.textContent = `${pw}x${ph} px  @  (${px},${py})  /  full ${cropState.imgW}x${cropState.imgH}`;
}

function closeCropper() {
  cropper.classList.remove("open");
  cropState = null;
}

// Drag / resize the crop rect
let dragMode = null; // null | "move" | "tl" | "tr" | ... | "t" | ...
let dragStart = null;

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

function applyDrag(clientX, clientY) {
  if (!cropState || !dragMode) return;
  const r = cropperImg.getBoundingClientRect();
  const dx = (clientX - dragStart.clientX) / r.width * 100;  // delta in percent
  const dy = (clientY - dragStart.clientY) / r.height * 100;
  let {x, y, w, h} = dragStart;
  if (dragMode === "move") {
    x = clamp(x + dx, 0, 100 - w);
    y = clamp(y + dy, 0, 100 - h);
  } else {
    if (dragMode.includes("l")) { const nx = clamp(x + dx, 0, x + w - 1); w = w - (nx - x); x = nx; }
    if (dragMode.includes("r")) { w = clamp(w + dx, 1, 100 - x); }
    if (dragMode.includes("t")) { const ny = clamp(y + dy, 0, y + h - 1); h = h - (ny - y); y = ny; }
    if (dragMode.includes("b")) { h = clamp(h + dy, 1, 100 - y); }
  }
  cropState.x = x; cropState.y = y; cropState.w = w; cropState.h = h;
  placeCropRect();
  updateCropInfo();
}

cropRect.addEventListener("mousedown", (ev) => {
  ev.preventDefault();
  const handle = ev.target.closest(".crop-handle");
  dragMode = handle ? handle.dataset.h : "move";
  dragStart = {clientX: ev.clientX, clientY: ev.clientY, x: cropState.x, y: cropState.y, w: cropState.w, h: cropState.h};
});

window.addEventListener("mousemove", (ev) => {
  if (!dragMode) return;
  applyDrag(ev.clientX, ev.clientY);
});
window.addEventListener("mouseup", () => { dragMode = null; dragStart = null; });

// Touch support
cropRect.addEventListener("touchstart", (ev) => {
  if (!ev.touches[0]) return;
  ev.preventDefault();
  const t = ev.touches[0];
  const handle = ev.target.closest(".crop-handle");
  dragMode = handle ? handle.dataset.h : "move";
  dragStart = {clientX: t.clientX, clientY: t.clientY, x: cropState.x, y: cropState.y, w: cropState.w, h: cropState.h};
}, {passive: false});
window.addEventListener("touchmove", (ev) => {
  if (!dragMode || !ev.touches[0]) return;
  ev.preventDefault();
  applyDrag(ev.touches[0].clientX, ev.touches[0].clientY);
}, {passive: false});
window.addEventListener("touchend", () => { dragMode = null; dragStart = null; });

// Reposition crop rect on window resize
window.addEventListener("resize", () => {
  if (cropState) placeCropRect();
});

document.getElementById("cropper-save").addEventListener("click", () => {
  if (!cropState) return;
  const entry = {
    x: +cropState.x.toFixed(2),
    y: +cropState.y.toFixed(2),
    w: +cropState.w.toFixed(2),
    h: +cropState.h.toFixed(2),
  };
  if (cropState.rotation) entry.rotation = cropState.rotation;
  CROPS[cropState.filename] = entry;
  saveCrops(CROPS);
  const card = document.querySelector(`.card[data-filename="${cropState.filename}"]`);
  if (card) applyFlagToCard(card, cropState.filename);
  updateCounts();
  closeCropper();
});

document.getElementById("cropper-rot-cw").addEventListener("click", () => rotateCropper(90));
document.getElementById("cropper-rot-ccw").addEventListener("click", () => rotateCropper(-90));

document.getElementById("cropper-cancel").addEventListener("click", closeCropper);

document.getElementById("cropper-reset").addEventListener("click", () => {
  if (!cropState) return;
  cropState.x = 5; cropState.y = 5; cropState.w = 90; cropState.h = 90;
  placeCropRect();
  updateCropInfo();
});

document.getElementById("cropper-clear").addEventListener("click", () => {
  if (!cropState) return;
  delete CROPS[cropState.filename];
  saveCrops(CROPS);
  const card = document.querySelector(`.card[data-filename="${cropState.filename}"]`);
  if (card) applyFlagToCard(card, cropState.filename);
  updateCounts();
  closeCropper();
});

// Esc to close
window.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && cropper.classList.contains("open")) {
    closeCropper();
  }
});

// Keyboard shortcuts: press r/f/c over a hovered card
document.addEventListener("keydown", (ev) => {
  if (ev.target.tagName === "INPUT" || ev.target.tagName === "TEXTAREA") return;
  const hovered = document.querySelector(".card:hover");
  if (!hovered) return;
  const fn = hovered.dataset.filename;
  if (!fn) return;
  const titleEl = hovered.querySelector(".meta-strip .t");
  const title = titleEl ? titleEl.textContent : fn;
  if (ev.key === "r" || ev.key === "R") {
    removeCard(hovered, fn, title);
    ev.preventDefault();
    return;
  } else if (ev.key === "f" || ev.key === "F") {
    FLAGS[fn] = (FLAGS[fn] === "review") ? undefined : "review";
    if (!FLAGS[fn]) delete FLAGS[fn];
  } else if (ev.key === "c" || ev.key === "C") {
    openCropper(fn, title);
    ev.preventDefault();
    return;
  } else { return; }
  saveFlags(FLAGS);
  applyFlagToCard(hovered, fn);
  updateCounts();
  ev.preventDefault();
});

// ===== Cluster badge bookkeeping =====
// Recompute the "dup N" pill on each card based on the currently-visible
// siblings in the same cluster. Call after any change that affects which
// cards are in the mosaic (remove, undo restore).
function updateClusterBadges() {
  const groups = {};
  document.querySelectorAll(".card").forEach(card => {
    if (card.style.display === "none") return;
    const cid = card.dataset.clusterId;
    if (cid === undefined) return;
    (groups[cid] = groups[cid] || []).push(card);
  });
  for (const cid in groups) {
    const members = groups[cid];
    const size = members.length;
    members.forEach(card => {
      card.dataset.clusterSize = String(size);
      let pill = card.querySelector(".pill.dup");
      if (size > 1) {
        if (!pill) {
          const badges = card.querySelector(".badge");
          if (badges) {
            pill = document.createElement("span");
            pill.className = "pill dup";
            pill.title = "Near-duplicate group — sibling card(s) are adjacent in the mosaic";
            badges.insertBefore(pill, badges.firstChild);
          }
        }
        if (pill) pill.textContent = "dup " + size;
      } else if (pill) {
        pill.remove();
      }
    });
  }
}

// ===== Remove + undo =====
// Server-side: file moves to rejected/user-removed/, can be restored
// within ~5s via the toast.
let UNDO_TIMER = null;
let UNDO_CB = null;
const toastEl = document.getElementById("undo-toast");
const undoBtn = document.getElementById("undo-btn");
const undoMsg = document.getElementById("undo-filename");

async function removeCard(card, filename, title) {
  if (!HAS_SERVER) {
    alert("Run serve.py to enable removal (the gallery needs to write to disk).");
    return;
  }
  card.classList.add("removing");
  // Wait for fade then collapse the card from layout
  setTimeout(() => { card.style.display = "none"; }, 350);
  let movedTo = "";
  try {
    const r = await fetch("/api/remove", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({filename}),
    });
    const j = await r.json();
    if (j.status !== "ok") throw new Error(j.error || "remove failed");
    movedTo = j.moved_to || "";
  } catch (err) {
    // Roll back the card visibility
    card.style.display = "";
    card.classList.remove("removing");
    alert("Remove failed: " + err.message);
    return;
  }
  // Clear any flag/crop state for this file (the server already did it on disk)
  delete FLAGS[filename];
  delete CROPS[filename];
  persistLocal();
  updateCounts();
  // Refresh duplicate badges on the remaining siblings: if this was one
  // of two near-duplicates, the survivor's "dup 2" pill becomes stale and
  // should disappear.
  updateClusterBadges();

  showUndoToast(title || filename, async () => {
    try {
      const r = await fetch("/api/restore", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({filename, moved_to: movedTo}),
      });
      const j = await r.json();
      if (j.status !== "ok") throw new Error(j.error || "restore failed");
    } catch (err) {
      alert("Undo failed: " + err.message);
      return;
    }
    // Restore the card from collapsed state
    card.style.display = "";
    card.classList.remove("removing");
    // Force the front-face img to re-fetch in case it got 404'd
    const img = card.querySelector(".face.front img");
    if (img) img.src = "raw/" + filename + "?v=" + Date.now();
    // The cluster regained a member; restore its dup pill if applicable.
    updateClusterBadges();
  });
}

function showUndoToast(label, undoFn) {
  if (UNDO_TIMER) clearTimeout(UNDO_TIMER);
  UNDO_CB = undoFn;
  undoMsg.textContent = label;
  // Restart the CSS progress bar animation
  const bar = toastEl.querySelector(".toast-progress");
  if (bar) {
    bar.style.animation = "none";
    void bar.offsetWidth;  // reflow
    bar.style.animation = "";
  }
  toastEl.classList.add("show");
  UNDO_TIMER = setTimeout(() => {
    toastEl.classList.remove("show");
    UNDO_CB = null;
  }, 5000);
}

undoBtn.addEventListener("click", () => {
  if (UNDO_CB) UNDO_CB();
  if (UNDO_TIMER) clearTimeout(UNDO_TIMER);
  toastEl.classList.remove("show");
  UNDO_CB = null;
});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    sys.exit(main())
