"""Gemini visual review of every image in raw/.

For each image, ask Gemini 2.5 Flash to return structured JSON:
  - frame: bool + bbox of the painting inside the frame
  - white_border: bool + bbox of the painting inside the border
  - watermark: bool + location + text (if visible)
  - notes: short free-text

Output: review.json keyed by filename. Resumable: on re-run, skips files
already present in review.json.
"""
from __future__ import annotations

import base64
import importlib.util
import io
import json
import os
import sys
import time
from pathlib import Path

from PIL import Image
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
OUT = ROOT / "review.json"


def _load_env_key() -> str:
    """Resolve this project's OWN Gemini key via tools/gemini_review.py.

    Copy-safe: walks up from this file to find tools/gemini_review.py, so it
    still works when copied into a new datasets/<name>/ folder, which
    docs/manual/dataset-curation.md tells you to do. Key policy lives in that
    one file; this is only a locator.

    Never reads a sibling project's .env. Google bills the GCP project that
    owns the key, not the code that calls it, so borrowing one charges the
    lender. This file used to do exactly that, billing an unrelated project
    for our dataset triage.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "tools" / "gemini_review.py"
        if cand.is_file():
            spec = importlib.util.spec_from_file_location("gr", cand)
            gr = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(gr)
            return gr.api_key()
    sys.exit(f"could not find tools/gemini_review.py above {here}")


API_KEY = _load_env_key()

MODEL = "gemini-2.5-flash"

PROMPT = """You are auditing a training dataset of Pierre-Auguste Renoir's
floral paintings. Look at this image and decide whether it needs cropping
to isolate the painting itself.

Return STRICT JSON, no markdown, with these fields:

{
  "has_physical_frame": bool,           // ornate/wood/gilded frame visible around the painting
  "has_white_or_paper_border": bool,    // catalogue-style white/cream border around the painting
  "has_watermark": bool,                // any logo, text overlay, copyright stamp, museum tag burned in
  "watermark_description": str,         // empty if none; otherwise short "Sotheby's lot tag bottom-left" etc.
  "needs_crop": bool,                   // true if any of the above three need cropping out
  "painting_bbox_pct": {                // bbox of the actual painting as percentage of image
    "x": float,  // left edge, 0 to 100
    "y": float,  // top edge, 0 to 100
    "w": float,  // width, 0 to 100
    "h": float   // height, 0 to 100
  },
  "notes": str                          // 1 short sentence on what's wrong, empty if clean
}

If the image is already a clean reproduction of the painting (no frame, no
white border, no watermark), set has_*=false, needs_crop=false, and
painting_bbox_pct to {x:0, y:0, w:100, h:100}.

Be CONSERVATIVE on framing: do NOT crop unless there is a clear non-painted
border. A painted dark margin inside the canvas is part of the painting.
Renoir's signature is often in the corner of the canvas; do NOT crop into it.
"""


def load_done() -> dict:
    if OUT.exists():
        return json.loads(OUT.read_text(encoding="utf-8"))
    return {}


def save(done: dict) -> None:
    OUT.write_text(json.dumps(done, ensure_ascii=False, indent=2), encoding="utf-8")


def downscale_for_review(fp: Path, max_side: int = 1024) -> bytes:
    """Send a small preview to Gemini. We only need composition info, not
    pixel-perfect detail. Saves cost and latency."""
    with Image.open(fp) as im:
        im = im.convert("RGB")
        w, h = im.size
        scale = min(1.0, max_side / max(w, h))
        if scale < 1.0:
            im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85)
        return buf.getvalue()


def review_one(client: genai.Client, fp: Path) -> dict:
    img_bytes = downscale_for_review(fp)
    resp = client.models.generate_content(
        model=MODEL,
        contents=[
            types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
            PROMPT,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
        ),
    )
    text = resp.text or "{}"
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # try to recover the first {...} block
        i, j = text.find("{"), text.rfind("}")
        if i >= 0 and j > i:
            return json.loads(text[i : j + 1])
        return {"error": "json-decode-failed", "raw": text}


def main() -> int:
    client = genai.Client(api_key=API_KEY)
    done = load_done()
    files = sorted(p.name for p in RAW.glob("*.jpg"))
    todo = [n for n in files if n not in done or "error" in done.get(n, {})]
    print(f"total: {len(files)}, already done: {len(files) - len(todo)}, to review: {len(todo)}")

    for i, name in enumerate(todo, 1):
        fp = RAW / name
        try:
            result = review_one(client, fp)
        except Exception as e:
            result = {"error": str(e)[:200]}
        done[name] = result
        flags = []
        if result.get("has_physical_frame"): flags.append("FRAME")
        if result.get("has_white_or_paper_border"): flags.append("WHITE-BG")
        if result.get("has_watermark"): flags.append("WATERMARK")
        bbox = result.get("painting_bbox_pct", {})
        flag_str = ",".join(flags) if flags else "ok"
        bbox_str = f"({bbox.get('x',0):.0f},{bbox.get('y',0):.0f} {bbox.get('w',100):.0f}x{bbox.get('h',100):.0f})" if bbox else ""
        print(f"[{i}/{len(todo)}] {name}: {flag_str} {bbox_str}")
        if i % 5 == 0:
            save(done)
        time.sleep(0.4)
    save(done)
    print(f"wrote {OUT}")

    # summary
    n_frame = sum(1 for v in done.values() if v.get("has_physical_frame"))
    n_white = sum(1 for v in done.values() if v.get("has_white_or_paper_border"))
    n_wm = sum(1 for v in done.values() if v.get("has_watermark"))
    n_crop = sum(1 for v in done.values() if v.get("needs_crop"))
    print(f"\nsummary: frame={n_frame} white-bg={n_white} watermark={n_wm} needs-crop={n_crop} / {len(done)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
