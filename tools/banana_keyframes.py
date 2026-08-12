"""Author keyframes with an image-EDIT model, so only the acting element moves.

The capability Luca asked for on 2026-08-12, in his words: first frame is someone
washing their hands in a sink, camera looking down, and every later keyframe keeps
everything the same, changing only the position of the hands and the flow and
splash of the water. Then interpolation animates ONLY the acting element, because
the keyframes agree everywhere else.

The first probe validated it end to end: five keyframes (base + four sequential
edits, gemini-3.1-flash-image), background SSIM 0.83 to 0.94 between consecutive
frames with the hands masked, RIFE Phase C run locally over them, and the result
gated **10/9/9/9**, the highest scores of the project, with NO LoRA and NO
diffusion chain. The rubbery-morphing complaint that dogged every chained render
is absent by construction: there is nothing disagreeing between keyframes except
the thing that is supposed to move.

    python tools/banana_keyframes.py --out outputs/arendt/labor_hands/keyframes \\
        --base "oil painting ... hands under a tap ..." \\
        --edit "the hands rotate slightly, one palm turned up" \\
        --edit "the hands rub together, water sheeting off"

    # then Phase C locally (no Modal): see docs, RIFE needs w and h % 64 == 0.

Rules learned in the probe:
- Edits are SEQUENTIAL: each edit receives the PREVIOUS output, not the base, so
  the scene accumulates a history and the loop reads as one continuous act.
- Say "keep ABSOLUTELY EVERYTHING identical" and name what may change; the model
  still takes small liberties (the probe's last frame drained the basin), so eye
  the set before interpolating.
- The wrap pair (last keyframe back to the first) is what closes the loop; author
  the last edit to land NEAR the base state or the wrap carries the biggest step.
- The key comes from the same env as gemini_review.py; never printed or stored.
"""

from __future__ import annotations

import argparse
import importlib.util
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EDIT_PREAMBLE = (
    "Edit this image. Keep ABSOLUTELY EVERYTHING identical: the setting, the "
    "lighting, the palette, the brushwork, the camera. Change ONLY this: {change}. "
    "The result must look like the SAME painting a moment later.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="prompt for keyframe 0000")
    ap.add_argument("--edit", action="append", default=[],
                    help="sequential edit; repeatable, one per keyframe")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="gemini-3.1-flash-image")
    a = ap.parse_args()

    spec = importlib.util.spec_from_file_location("gr", ROOT / "tools" / "gemini_review.py")
    gr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gr)
    from google import genai
    from google.genai import types
    from PIL import Image

    client = genai.Client(api_key=gr.api_key())
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    def gen(contents, path):
        r = client.models.generate_content(
            model=a.model, contents=contents,
            config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]))
        for part in r.candidates[0].content.parts:
            if getattr(part, "inline_data", None):
                img = Image.open(io.BytesIO(part.inline_data.data)).convert("RGB")
                img.save(path)
                return img
        texts = [getattr(p, "text", "")[:120] for p in r.candidates[0].content.parts]
        raise RuntimeError(f"no image returned for {path.name}: {texts}")

    cur = gen([a.base], out / "0000.png")
    print(f"0000.png  {cur.size}")
    for i, change in enumerate(a.edit, start=1):
        cur = gen([cur, EDIT_PREAMBLE.format(change=change)], out / f"{i:04d}.png")
        print(f"{i:04d}.png  {cur.size}")
    print(f"{1 + len(a.edit)} keyframes in {out}. Eye them BEFORE interpolating.")


if __name__ == "__main__":
    main()
