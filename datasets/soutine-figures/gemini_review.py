"""Gemini visual triage of every image in raw/.

Inherits the Renoir review pattern (datasets/renoir-flowers/gemini_review.py)
but combines triage (is this even a Soutine figure?) with the standard
framing audit (cropping, watermarks). The Soutine candidate set was sourced
broadly from Wikimedia Commons categories that include non-Soutine works,
non-paintings, and non-figure Soutine subjects (landscapes, carcasses,
still lifes), all of which must be filtered out.

For each image, ask Gemini 2.5 Flash to return structured JSON. Decisions:

  TRIAGE
    is_painting:       photograph / sculpture rejection
    by_soutine:        other-artist rejection (Modigliani, Degas, etc)
    figure_visible:    landscape / still life / carcass rejection
    subject_kind:      figure pose taxonomy
    figure_isolated:   the figure is alone, not in a crowd

  FRAMING (same as Renoir)
    has_physical_frame, has_white_or_paper_border, has_watermark
    watermark_description
    needs_crop
    painting_bbox_pct

  DECISION
    keep_for_training: overall yes/no
    rejection_reason: short tag when keep_for_training == false

Output: review.json. Resumable: skips files already present and free of
errors on re-run.
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
import time
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
OUT = ROOT / "review.json"


def _load_env_key() -> str | None:
    """Walk the known .env locations and return the first Gemini key found.

    Avoids depending on python-dotenv since the system Python has a broken
    dependency chain. Simple key=value parser is enough for our needs.
    """
    for env_path in [
        Path("C:/Users/lucaa/OneDrive/Desktop/RNMW-agent/.env"),
        Path("C:/Users/lucaa/OneDrive/Desktop/Choire-v2/.env"),
        ROOT.parents[1] / ".env",
    ]:
        if not env_path.exists():
            continue
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k in ("GEMINI_API_KEY", "GOOGLE_API_KEY") and v:
                    return v
        except Exception:
            continue
    return os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")


API_KEY = _load_env_key()
if not API_KEY:
    sys.exit("no GOOGLE_API_KEY / GEMINI_API_KEY in env")

MODEL = "gemini-2.5-flash"
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

PROMPT = """You are auditing a training dataset of figure paintings by
Chaim Soutine (1893-1943, French expressionist). The dataset was sourced
by a Wikimedia Commons category walk; it contains many false positives that
must be filtered out:

  - photos of real people (not paintings)
  - paintings BY OTHER ARTISTS (Modigliani, Degas, Cezanne, Fantin-Latour,
    Benson; some of which depict Soutine himself)
  - Soutine landscapes, still lifes, vases of flowers, and his famous
    Carcass series (sides of beef, dead poultry, hanging rabbits)

We want ONLY paintings by Soutine showing a single isolated human figure
(or rarely two figures), suitable for training a figure-LoRA.

Return STRICT JSON, no markdown:

{
  "is_painting": bool,                  // false for photos, sculpture
  "by_soutine": bool,                   // attributed to Chaim/Chaim Soutine
  "figure_visible": bool,               // human figure is the primary subject
  "subject_kind": str,                  // one of: standing_figure, seated_figure,
                                        //   kneeling_figure, portrait_bust,
                                        //   self_portrait, group, carcass,
                                        //   landscape, still_life, other
  "figure_isolated": bool,              // single figure, no crowd, neutral or simple bg

  "has_physical_frame": bool,
  "has_white_or_paper_border": bool,
  "has_watermark": bool,
  "watermark_description": str,
  "needs_crop": bool,
  "painting_bbox_pct": {"x": float, "y": float, "w": float, "h": float},

  "keep_for_training": bool,            // overall: include in Soutine figure LoRA
  "rejection_reason": str,              // empty if keep_for_training=true;
                                        // otherwise short tag like "not_soutine",
                                        // "carcass", "landscape", "still_life",
                                        // "photo", "low_quality", "group"
  "notes": str                          // 1 short sentence
}

Decision rule for keep_for_training:
  - MUST be is_painting=true AND by_soutine=true AND figure_visible=true
  - subject_kind in {standing_figure, seated_figure, kneeling_figure,
    portrait_bust, self_portrait}
  - figure_isolated preferred but not strictly required

For painting_bbox_pct, if uncertain or the image is already cleanly cropped,
return {x:0, y:0, w:100, h:100}.

Be CONSERVATIVE on framing: do NOT crop unless there is a clear non-painted
border. Soutine's brushwork extends to the canvas edge.
"""


def load_done() -> dict:
    if OUT.exists():
        return json.loads(OUT.read_text(encoding="utf-8"))
    return {}


def save(done: dict) -> None:
    OUT.write_text(json.dumps(done, ensure_ascii=False, indent=2), encoding="utf-8")


def downscale_for_review(fp: Path, max_side: int = 1024) -> bytes:
    with Image.open(fp) as im:
        im = im.convert("RGB")
        w, h = im.size
        scale = min(1.0, max_side / max(w, h))
        if scale < 1.0:
            im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85)
        return buf.getvalue()


def review_one(fp: Path) -> dict:
    img_bytes = downscale_for_review(fp)
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": base64.b64encode(img_bytes).decode("ascii"),
                        }
                    },
                    {"text": PROMPT},
                ]
            }
        ],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.0,
        },
    }
    headers = {"Content-Type": "application/json", "x-goog-api-key": API_KEY}
    r = requests.post(ENDPOINT, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    js = r.json()
    try:
        text = js["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        return {"error": "no-candidates", "raw": json.dumps(js)[:200]}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        i, j = text.find("{"), text.rfind("}")
        if i >= 0 and j > i:
            return json.loads(text[i : j + 1])
        return {"error": "json-decode-failed", "raw": text[:200]}


def main() -> int:
    done = load_done()
    files = sorted(p.name for p in RAW.glob("*.jpg"))
    todo = [n for n in files if n not in done or "error" in done.get(n, {})]
    print(f"total: {len(files)}, already done: {len(files) - len(todo)}, to review: {len(todo)}")

    for i, name in enumerate(todo, 1):
        fp = RAW / name
        try:
            result = review_one(fp)
        except Exception as e:
            result = {"error": str(e)[:200]}
        done[name] = result
        decision = "KEEP" if result.get("keep_for_training") else f"DROP({result.get('rejection_reason', '?')})"
        kind = result.get("subject_kind", "?")
        print(f"[{i}/{len(todo)}] {name}: {decision} kind={kind}")
        if i % 10 == 0:
            save(done)
        time.sleep(0.4)
    save(done)
    print(f"wrote {OUT}")

    # Summary
    keep = [n for n, v in done.items() if v.get("keep_for_training")]
    drop = [n for n, v in done.items() if not v.get("keep_for_training")]
    print(f"\nkept {len(keep)}, dropped {len(drop)} of {len(done)}")
    from collections import Counter
    reasons = Counter(v.get("rejection_reason", "unknown") for n, v in done.items() if not v.get("keep_for_training"))
    print("rejection breakdown:")
    for reason, count in reasons.most_common():
        print(f"  {count:>3}  {reason}")
    kinds = Counter(v.get("subject_kind", "unknown") for n, v in done.items() if v.get("keep_for_training"))
    print("kept-set subject kinds:")
    for kind, count in kinds.most_common():
        print(f"  {count:>3}  {kind}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
