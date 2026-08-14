"""Author keyframes with an OPEN-WEIGHT image-edit model on Modal.

Drop-in sibling of `tools/banana_keyframes.py`. Same CLI, same output layout, same
`manifest.json`; the only difference is `--model`, which names a candidate in
`cloud/edit.py` instead of a Gemini model id.

    python tools/edit_keyframes.py --model klein \\
        --out outputs/arendt/labor_hands/keyframes \\
        --base-image outputs/arendt/labor_embers/keyframes/0000.png \\
        --edit "the hands rotate slightly, one palm turned up" \\
        --edit "the hands rub together, water sheeting off"

    python tools/edit_keyframes.py --model klein --bridge a.png b.png \\
        --bridge-at "two thirds of the way" --out bridge.png

Three things that differ from the Gemini path, and they are not cosmetic:

- **The whole chain runs inside ONE Modal container.** The pipeline is resident
  (`@modal.enter()` in `cloud/edit.py`), so a 10-keyframe chain pays the model load
  once. Do not loop this script per keyframe; that is the expensive way to do it.
- **The seed is real.** Gemini gave no seed, so a rerun re-rolled the frame. Here
  `--seed` (1087 by default) makes a chain reproducible, which is what makes
  `--base-image` tail-repair exact rather than approximate.
- **The preamble is optional.** `--bare` sends the change clause alone. Qwen-family
  guidance is that short specific prompts beat long ones and klein's card warns that
  prompt following is phrasing-sensitive, so the long "keep ABSOLUTELY EVERYTHING
  identical" preamble that Gemini reasons over may cost preservation rather than buy
  it. Which form wins per candidate is recorded in
  `docs/findings/image-edit-model-alternatives.md`.

Output size is pinned to the base image on every call unless `--width`/`--height`
say otherwise. Both candidate families downsample the CONDITIONING image to a 1 MP
budget internally whatever you pass, so the pinned size controls the canvas, not the
detail that survives; see the finding's Q2 section.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EDIT_PREAMBLE = (
    "Edit this image. Keep ABSOLUTELY EVERYTHING identical: the setting, the "
    "lighting, the palette, the brushwork, the camera. Change ONLY this: {change}. "
    "The result must look like the SAME painting a moment later.")

BRIDGE_PROMPT = (
    "These two images are the SAME painting at two different moments. "
    "Paint the exact in-between moment, {at} from the first to the second. "
    "Keep the setting, the composition, the camera and the brushwork identical to "
    "both; only the changing element should sit between its two states. Do not "
    "invent anything present in neither.")

# Candidates that can synthesise keyframe 0 from text alone. The edit-only ones
# must be given --base-image.
TEXT_TO_IMAGE = {"klein"}


def _load_app():
    spec = importlib.util.spec_from_file_location("cloud_edit", ROOT / "cloud" / "edit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", help="prompt for keyframe 0000 (text-to-image candidates only)")
    ap.add_argument("--base-image", dest="base_image",
                    help="reuse an existing PNG as keyframe 0000 instead of generating "
                         "one. Use this to re-author the TAIL of a chain whose early "
                         "keyframes are good. Mutually exclusive with --base.")
    ap.add_argument("--edit", action="append", default=[],
                    help="sequential edit; repeatable, one per keyframe")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="klein",
                    help="candidate key in cloud/edit.py: klein | firered | mageflow")
    ap.add_argument("--bridge", nargs=2, metavar=("FROM", "TO"),
                    help="two image paths; writes ONE in-between frame to --out "
                         "(a file path, not a directory).")
    ap.add_argument("--bridge-at", default="halfway",
                    help="'halfway', 'one third of the way', 'two thirds of the way'")
    ap.add_argument("--seed", type=int, default=1087)
    ap.add_argument("--steps", type=int, default=None, help="override the candidate default")
    ap.add_argument("--guidance", type=float, default=None, help="override the candidate default")
    ap.add_argument("--width", type=int, default=None)
    ap.add_argument("--height", type=int, default=None)
    ap.add_argument("--bare", action="store_true",
                    help="send the change clause alone, without the preservation preamble")
    a = ap.parse_args()

    import modal
    from PIL import Image

    E = _load_app()
    if a.model not in E.EDITORS:
        raise SystemExit(f"--model must be one of {sorted(E.EDITORS)}")
    defaults = E.DEFAULTS[a.model]
    steps = a.steps if a.steps is not None else defaults["steps"]
    guidance = a.guidance if a.guidance is not None else defaults["guidance"]

    out = Path(a.out)
    if not a.bridge:
        if bool(a.base) == bool(a.base_image):
            raise SystemExit("pass exactly one of --base or --base-image")
        if a.base and a.model not in TEXT_TO_IMAGE:
            raise SystemExit(f"--model {a.model} is edit-only; pass --base-image")
        out.mkdir(parents=True, exist_ok=True)
    else:
        out.parent.mkdir(parents=True, exist_ok=True)

    sizes: list[list[int]] = []

    with modal.enable_output():
        with E.app.run():
            editor = E.EDITORS[a.model]()

            def call(images: list[Path], prompt: str, dest: Path, w, h):
                r = editor.edit.remote(
                    images=[p.read_bytes() for p in images], prompt=prompt,
                    width=w, height=h, steps=steps, guidance=guidance, seed=a.seed)
                dest.write_bytes(r["png"])
                got = (r["width"], r["height"])
                flag = "" if (w, h) == got or w is None else f"  REQUESTED {w}x{h}"
                print(f"{dest.name}  {got[0]}x{got[1]}  {r['seconds']:.1f}s{flag}")
                return got

            if a.bridge:
                first, second = (Path(p) for p in a.bridge)
                w = a.width or Image.open(first).size[0]
                h = a.height or Image.open(first).size[1]
                call([first, second], BRIDGE_PROMPT.format(at=a.bridge_at), out, w, h)
                print(f"bridge {a.bridge_at}: {first.name} -> {second.name}")
                return

            if a.base_image:
                cur = Path(a.base_image)
                img = Image.open(cur).convert("RGB")
                img.save(out / "0000.png")
                cur = out / "0000.png"
                print(f"0000.png  {img.size[0]}x{img.size[1]}  (reused from {a.base_image})")
                w = a.width or img.size[0]
                h = a.height or img.size[1]
                sizes.append([w, h])
            else:
                w = a.width or 1408
                h = a.height or 768
                cur = out / "0000.png"
                got = call([], a.base, cur, w, h)
                sizes.append(list(got))

            for i, change in enumerate(a.edit, start=1):
                prompt = change if a.bare else EDIT_PREAMBLE.format(change=change)
                nxt = out / f"{i:04d}.png"
                sizes.append(list(call([cur], prompt, nxt, w, h)))
                cur = nxt

    (out / "manifest.json").write_text(json.dumps({
        "model": a.model,
        "model_id": E.EDITORS[a.model].MODEL_ID,
        "base": a.base,
        "base_image": a.base_image,
        "edits": a.edit,
        "edit_preamble": None if a.bare else EDIT_PREAMBLE,
        "seed": a.seed,
        "steps": steps,
        "guidance": guidance,
        "sizes": sizes,
    }, indent=2), encoding="utf-8")

    print(f"{1 + len(a.edit)} keyframes in {out}. Eye them BEFORE interpolating.")


if __name__ == "__main__":
    sys.exit(main())
