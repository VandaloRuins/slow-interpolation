"""Validate newly-sourced images with Gemini.

For each file present in raw/ but not yet present in review.json, ask
Gemini: is this a painting by Renoir? Are flowers visible in the
composition? If not, move to rejected/expanded-mismatch/ with reason.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
REJECTED = ROOT / "rejected" / "expanded-mismatch"
REVIEW = ROOT / "review.json"
TRIAGE_OUT = ROOT / "triage_expanded.json"

load_dotenv(Path("C:/Users/lucaa/OneDrive/Desktop/Choire-v2/.env"))
API_KEY = os.environ["GOOGLE_API_KEY"]
MODEL = "gemini-2.5-flash"

PROMPT = """Inspect this image for a Renoir floral dataset. Strict JSON:
{
  "is_painting": bool,                  // false if photograph, drawing, ceramic, plaque, statue, museum-room photo
  "by_renoir": bool,                    // true if it looks like a Renoir painting (1860s-1919 impressionist style)
  "flowers_visible": bool,              // are flowers a notable element (vase, bouquet, garden bed, flower-hat, blossoming tree, hand-held bouquet)
  "subject": str,                       // one short phrase: "still life", "figure with bouquet", "garden landscape", "mother and child in garden", "museum exterior photograph", etc.
  "keep_for_dataset": bool,             // is_painting && by_renoir && flowers_visible
  "reason_to_drop": str                 // empty if keep_for_dataset, otherwise short reason
}
Be strict: if flowers are barely there or only suggested, set flowers_visible=false. If the image is clearly a photograph (modern colours, sharp edges, blue sky, garden architecture, museum signage), set is_painting=false."""


def downscale(fp: Path, max_side: int = 1024) -> bytes:
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(fp) as im:
        im = im.convert("RGB")
        w, h = im.size
        s = min(1.0, max_side / max(w, h))
        if s < 1.0:
            im = im.resize((int(w*s), int(h*s)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
        return buf.getvalue()


def main() -> int:
    REJECTED.mkdir(parents=True, exist_ok=True)
    seen = set(json.loads(REVIEW.read_text(encoding="utf-8"))) if REVIEW.exists() else set()
    todo = sorted([p.name for p in RAW.glob("*.jpg") if p.name not in seen])
    print(f"new files to triage: {len(todo)}")

    client = genai.Client(api_key=API_KEY)
    results = json.loads(TRIAGE_OUT.read_text(encoding="utf-8")) if TRIAGE_OUT.exists() else {}

    for i, name in enumerate(todo, 1):
        if name in results:
            continue
        fp = RAW / name
        try:
            resp = client.models.generate_content(
                model=MODEL,
                contents=[types.Part.from_bytes(data=downscale(fp), mime_type="image/jpeg"), PROMPT],
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.0),
            )
            j = json.loads(resp.text or "{}")
        except Exception as e:
            j = {"error": str(e)[:200]}
        results[name] = j
        keep = j.get("keep_for_dataset", False)
        subj = j.get("subject", "")
        reason = j.get("reason_to_drop", "")
        verdict = "KEEP" if keep else f"DROP ({reason})"
        print(f"[{i}/{len(todo)}] {name}: {verdict}  [{subj}]")
        if i % 5 == 0:
            TRIAGE_OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(0.3)
    TRIAGE_OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    # Move drops
    n_moved = 0
    for name, r in results.items():
        if not r.get("keep_for_dataset", True):  # default True if errored
            src = RAW / name
            if src.exists():
                shutil.move(str(src), str(REJECTED / name))
                n_moved += 1
                print(f"  moved to rejected/expanded-mismatch/: {name}")
    print(f"\ndropped {n_moved} non-keepers; remaining in raw/: {len(list(RAW.glob('*.jpg')))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
