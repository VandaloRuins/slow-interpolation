"""Second-pass Gemini review.

For images previously flagged as FRAME, re-inspect the post-crop result
and produce a fresh painting_bbox_pct if the frame is still present.
Writes review_pass2.json (same schema as review.json) for use by
apply_crops_pass2.py.

Sends a tighter prompt with explicit guidance to cut INSIDE the visible
inner edge of the frame.
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv  # type: ignore
from PIL import Image
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
PREV = ROOT / "review.json"
OUT = ROOT / "review_pass2.json"
LOG = ROOT / "processed.json"

load_dotenv(Path("C:/Users/lucaa/OneDrive/Desktop/Choire-v2/.env"))
API_KEY = os.environ.get("GOOGLE_API_KEY")
MODEL = "gemini-2.5-flash"

PROMPT = """Second-pass audit. The image has already been processed once;
some images still show a physical frame because the first crop was too
generous.

Look at this image. If a physical frame, mat, or museum-wall margin is
still visible around the painting, return a TIGHT bbox that crops just
INSIDE the inner edge of the frame.

Strict JSON, no markdown:
{
  "frame_still_present": bool,
  "painting_bbox_pct": {"x": float, "y": float, "w": float, "h": float},
  "notes": str
}

If the frame is fully gone (image is corner-to-corner painting), set
frame_still_present=false and bbox to {x:0,y:0,w:100,h:100}.

Be AGGRESSIVE about cutting frames. It is fine to lose a 2-3 mm sliver of
canvas edge in exchange for a clean rectangle of painting. NEVER include
gilded ornament, wooden frame border, or wall-shadow margin in the bbox.
"""


def downscale(fp: Path, max_side: int = 1024) -> bytes:
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(fp) as im:
        im = im.convert("RGB")
        w, h = im.size
        scale = min(1.0, max_side / max(w, h))
        if scale < 1.0:
            im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=88)
        return buf.getvalue()


def review_one(client: genai.Client, fp: Path) -> dict:
    img_bytes = downscale(fp)
    resp = client.models.generate_content(
        model=MODEL,
        contents=[types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"), PROMPT],
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.0),
    )
    text = resp.text or "{}"
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        i, j = text.find("{"), text.rfind("}")
        return json.loads(text[i : j + 1]) if i >= 0 and j > i else {"error": "decode"}


def main() -> int:
    prev = json.loads(PREV.read_text(encoding="utf-8"))
    log = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else {}
    # Targets: previously flagged FRAME AND processed=done
    targets = [
        name for name, v in prev.items()
        if v.get("has_physical_frame") and log.get(name, {}).get("status") == "done"
    ]
    print(f"pass-2 targets (post-crop frame check): {len(targets)}")
    client = genai.Client(api_key=API_KEY)

    out = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    for i, name in enumerate(sorted(targets), 1):
        if name in out:
            continue
        fp = RAW / name
        try:
            r = review_one(client, fp)
        except Exception as e:
            r = {"error": str(e)[:200]}
        out[name] = r
        status = "STILL-FRAMED" if r.get("frame_still_present") else "clean"
        bb = r.get("painting_bbox_pct", {})
        bb_s = f"({bb.get('x',0):.0f},{bb.get('y',0):.0f} {bb.get('w',100):.0f}x{bb.get('h',100):.0f})"
        print(f"[{i}/{len(targets)}] {name}: {status} {bb_s}")
        if i % 4 == 0:
            OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(0.3)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    n_still = sum(1 for v in out.values() if v.get("frame_still_present"))
    print(f"\nstill framed: {n_still} / {len(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
