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
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EDIT_PREAMBLE = (
    "Edit this image. Keep ABSOLUTELY EVERYTHING identical: the setting, the "
    "lighting, the palette, the brushwork, the camera. Change ONLY this: {change}. "
    "The result must look like the SAME painting a moment later.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", help="prompt for keyframe 0000")
    ap.add_argument("--base-image", dest="base_image",
                    help="reuse an existing PNG as keyframe 0000 instead of generating "
                         "one. Use this to re-author the TAIL of a chain whose early "
                         "keyframes are good: paying to regenerate validated frames also "
                         "re-rolls them, and a validated frame is worth more than the call "
                         "it costs. Mutually exclusive with --base.")
    ap.add_argument("--edit", action="append", default=[],
                    help="sequential edit; repeatable, one per keyframe")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="gemini-3.1-flash-image")
    # The dual-image bridge. Sequential edits are BLIND to any frame but the
    # previous one, so an edit asked to "return to the start" drifts and a large
    # transition asked to happen in one step lands as a jump. Handing the model
    # BOTH endpoints and asking for the moment between is what closed
    # action_chairs' wrap 0.758 -> 0.953 and repaired four chains in one day.
    # It was doctrine before it was reachable from the CLI.
    ap.add_argument("--bridge", nargs=2, metavar=("FROM", "TO"),
                    help="two image paths; writes ONE in-between frame to --out "
                         "(a file path, not a directory). Use for a wrap seam or "
                         "any transition too large for one sequential step.")
    ap.add_argument("--bridge-at", default="halfway",
                    help="where between the two the moment sits: 'halfway', "
                         "'one third of the way', 'two thirds of the way'")
    a = ap.parse_args()

    spec = importlib.util.spec_from_file_location("gr", ROOT / "tools" / "gemini_review.py")
    gr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gr)
    from google import genai
    from google.genai import types
    from PIL import Image

    client = genai.Client(api_key=gr.api_key())
    out = Path(a.out)
    if not a.bridge:
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

    if a.bridge:
        first, second = (Image.open(p).convert("RGB") for p in a.bridge)
        prompt = (
            "These two images are the SAME painting at two different moments. "
            f"Paint the exact in-between moment, {a.bridge_at} from the first to "
            "the second. Keep the setting, the composition, the camera and the "
            "brushwork identical to both; only the changing element should sit "
            "between its two states. Do not invent anything present in neither.")
        out.parent.mkdir(parents=True, exist_ok=True)
        img = gen([first, second, prompt], out)
        print(f"{out.name}  {img.size}  (bridge {a.bridge_at}: "
              f"{Path(a.bridge[0]).name} -> {Path(a.bridge[1]).name})")
        return

    if bool(a.base) == bool(a.base_image):
        raise SystemExit("pass exactly one of --base or --base-image")

    sizes = []
    if a.base_image:
        cur = Image.open(a.base_image).convert("RGB")
        cur.save(out / "0000.png")
        print(f"0000.png  {cur.size}  (reused from {a.base_image}, not generated)")
    else:
        cur = gen([a.base], out / "0000.png")
        print(f"0000.png  {cur.size}")
    sizes.append(list(cur.size))
    for i, change in enumerate(a.edit, start=1):
        cur = gen([cur, EDIT_PREAMBLE.format(change=change)], out / f"{i:04d}.png")
        sizes.append(list(cur.size))
        print(f"{i:04d}.png  {cur.size}")

    # Manifest. Without this the prompts are unrecoverable, which on 2026-08-14
    # made it impossible to re-run three photographic chains changing only the
    # style clause: the originals were gone and had to be re-authored from
    # scratch. The keyframes are the record of the render; this is the record of
    # the keyframes. No key or secret is written here.
    (out / "manifest.json").write_text(json.dumps({
        "model": a.model,
        "base": a.base,
        "base_image": a.base_image,
        "edits": a.edit,
        "edit_preamble": EDIT_PREAMBLE,
        "sizes": sizes,
    }, indent=2), encoding="utf-8")

    print(f"{1 + len(a.edit)} keyframes in {out}. Eye them BEFORE interpolating.")


if __name__ == "__main__":
    main()
