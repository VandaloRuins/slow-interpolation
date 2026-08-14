"""Re-inspect user-flagged files for residual frame / border / mat / artefact.

Input: gallery-flags.json -> review_frame list.
Output: review_userflags.json with a tight painting_bbox_pct for any
residual non-painted border.

Stricter prompt than pass-2: ANY visible margin (white, cream, dark grey
wall, gilded wood, paper, mat, conservation strip, sliver of frame) must
be cropped out. The bbox should be the tightest rectangle that contains
only painted canvas.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
FLAGS = ROOT / "user-flags-2026-05-17.json"
OUT = ROOT / "review_userflags.json"


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

PROMPT = """Inspect this image. A user has flagged it for residual non-
painted margin (white paper border, cream catalogue mat, dark wall margin,
thin wooden frame sliver, museum-conservation strip, color-calibration
strip). Your job: return the TIGHTEST bounding box that contains only the
painted canvas itself.

Strict JSON:
{
  "has_residual_margin": bool,        // any non-painted border still visible
  "margin_type": str,                 // "white_paper" / "cream_mat" / "dark_wall" / "gilded_frame" / "calibration_strip" / "none"
  "painting_bbox_pct": {"x": float, "y": float, "w": float, "h": float},
  "notes": str
}

Be AGGRESSIVE: it is fine to lose a 2-3 mm sliver of canvas edge in exchange
for a clean painted rectangle. Never include any white/cream/gilded/dark-
grey margin in the bbox. Preserve any visible artist signature; if the
signature is in the corner of the canvas, your bbox should include it.

If the image is already a clean painting corner-to-corner, set
has_residual_margin=false and bbox to {x:0, y:0, w:100, h:100}.
"""


def downscale(fp: Path, max_side: int = 1280) -> bytes:
    """Use slightly larger preview than pass-1 so thin borders are clearer."""
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(fp) as im:
        im = im.convert("RGB")
        w, h = im.size
        s = min(1.0, max_side / max(w, h))
        if s < 1.0:
            im = im.resize((int(w*s), int(h*s)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=88)
        return buf.getvalue()


def main() -> int:
    data = json.loads(FLAGS.read_text(encoding="utf-8"))
    targets = data.get("review_frame", [])
    print(f"reviewing {len(targets)} user-flagged files")

    client = genai.Client(api_key=API_KEY)
    out = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}

    for i, name in enumerate(targets, 1):
        if name in out:
            continue
        fp = RAW / name
        if not fp.exists():
            out[name] = {"error": "not in raw/"}
            print(f"[{i}/{len(targets)}] {name}: MISSING")
            continue
        try:
            resp = client.models.generate_content(
                model=MODEL,
                contents=[types.Part.from_bytes(data=downscale(fp), mime_type="image/jpeg"), PROMPT],
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.0),
            )
            j = json.loads(resp.text or "{}")
        except Exception as e:
            j = {"error": str(e)[:200]}
        out[name] = j
        bb = j.get("painting_bbox_pct", {})
        flag = "RESIDUAL" if j.get("has_residual_margin") else "clean"
        mt = j.get("margin_type", "")
        print(f"[{i}/{len(targets)}] {name}: {flag} [{mt}]  ({bb.get('x',0):.0f},{bb.get('y',0):.0f} {bb.get('w',100):.0f}x{bb.get('h',100):.0f})")
        if i % 4 == 0:
            OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(0.3)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    n_residual = sum(1 for v in out.values() if v.get("has_residual_margin"))
    print(f"\nresidual margins detected: {n_residual} / {len(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
