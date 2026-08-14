"""Multimodal video review of renders, via Gemini.

Complements `motion_profile.py` rather than replacing it. That tool measures
(it found the frame-329 loop break); this one watches, and answers the
judgement questions statistics cannot: does the subject read, does the loop
feel closed, does it look like a painting.

Writes `gallery-feedback.json` at the repo root, which `tools/gallery.py` loads
onto the back of each card. Notes are a starting point for you to edit, not a
verdict.

    python tools/gemini_review.py outputs/course-of-empire/*.mp4
    python tools/gemini_review.py --all              # every mp4 under outputs/
    python tools/gemini_review.py --all --subject "Times Square"

The key is read from this project's own tools/.env at runtime and is never
printed or stored.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
FEEDBACK = ROOT / "gallery-feedback.json"
MODEL = "gemini-2.5-flash"


def api_key() -> str:
    """Resolve THIS project's own Gemini key. Canonical resolver for the repo.

    Reads tools/.env then the repo root via media_store.load_env(); a real
    environment variable wins over both.

    There is deliberately NO fallback to any sibling project's .env. Google
    bills a Gemini call to the GCP project that owns the key, not to the code
    that made the call, so borrowing a key silently charges the lender. This
    file used to read a sibling project's .env first and put EUR 21 of
    keyframe generation on that project's bill in August 2026. A missing key is a hard
    failure here precisely so it can never quietly become someone else's.
    """
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))
    import media_store

    key = (media_store.load_env().get("GEMINI_API_KEY") or "").strip()
    if key:
        return key
    print(
        f"GEMINI_API_KEY not found. Put this project's OWN key in {TOOLS_DIR / '.env'}\n"
        "(create one at https://aistudio.google.com/apikey).\n"
        "Do NOT point this at another project's .env: it bills them, not us.",
        file=sys.stderr,
    )
    raise SystemExit(1)


PROMPT = """You are reviewing a short looping video from an art project called
slow-interpolation. The technique chains SDXL img2img keyframes through a domain
LoRA (Thomas Cole, 19th century Hudson River School landscape painting), then
interpolates them with RIFE into a seamless loop. It is shown on an LED billboard
at night, seen for about 10 seconds by people walking past.

{subject_line}

Watch the whole clip and rate it on FOUR axes. Be specific and critical. Name
timestamps for anything you flag. Do not be encouraging; the value here is
accurate criticism.

1. SUBJECT RECOGNITION (1-10): is the intended subject clearly legible? What do
   you actually see? If the intended subject is named above and it is NOT there,
   say so bluntly and say what it looks like instead.
2. LOOP LOGIC (1-10): does it loop seamlessly? Is there a visible jump, blur,
   or speed change at the wrap? Give the timestamp if so.
3. MOTION QUALITY (1-10): is the drift smooth and even, or does it pulse,
   stutter, or rush? Does anything morph in a rubbery way?
4. IMAGE QUALITY (1-10): does it read as an oil painting with real brushwork and
   a strong value structure, or as smooth digital render? Comment on the palette.

Then: ONE SENTENCE on the single biggest problem, and one on the biggest strength.

Reply as compact JSON only, no markdown fence:
{{"subject":N,"subject_note":"...","loop":N,"loop_note":"...","motion":N,
"motion_note":"...","image":N,"image_note":"...","worst":"...","best":"..."}}"""


def review(path: Path, key: str, subject: str) -> dict | None:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key)
    up = client.files.upload(file=str(path))
    for _ in range(60):                      # video files need processing first
        f = client.files.get(name=up.name)
        if f.state.name == "ACTIVE":
            break
        if f.state.name == "FAILED":
            print(f"  upload failed: {path.name}", file=sys.stderr)
            return None
        time.sleep(2)

    subject_line = (f"The intended subject is: {subject}." if subject else
                    "The intended subject is not specified; infer it.")
    resp = client.models.generate_content(
        model=MODEL,
        contents=[f, PROMPT.format(subject_line=subject_line)],
        config=types.GenerateContentConfig(temperature=0.2),
    )
    raw = (resp.text or "").strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def as_note(d: dict) -> str:
    if "raw" in d:
        return d["raw"]
    return (
        f"GEMINI REVIEW\n"
        f"Subject {d.get('subject','?')}/10 - {d.get('subject_note','')}\n"
        f"Loop {d.get('loop','?')}/10 - {d.get('loop_note','')}\n"
        f"Motion {d.get('motion','?')}/10 - {d.get('motion_note','')}\n"
        f"Image {d.get('image','?')}/10 - {d.get('image_note','')}\n"
        f"Worst: {d.get('worst','')}\n"
        f"Best: {d.get('best','')}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", nargs="*", type=Path)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--subject", default="")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    vids = list(args.videos)
    if args.all:
        vids = [p for p in (ROOT / "outputs").rglob("*.mp4")
                if "_gallery" not in p.parts and "archive" not in p.parts]
    if args.limit:
        vids = vids[: args.limit]
    if not vids:
        print("no videos given")
        return 1

    key = api_key()
    store = json.loads(FEEDBACK.read_text(encoding="utf-8")) if FEEDBACK.exists() else {}
    scores = []

    for v in sorted(vids):
        print(f"reviewing {v.stem} ...", flush=True)
        try:
            d = review(v, key, args.subject)
        except Exception as exc:
            print(f"  error: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        if not d:
            continue
        store[v.stem] = as_note(d)
        FEEDBACK.write_text(json.dumps(store, indent=2), encoding="utf-8")
        if "raw" not in d:
            tot = sum(int(d.get(k, 0) or 0) for k in ("subject", "loop", "motion", "image"))
            scores.append((tot, v.stem, d))
            print(f"  subject {d.get('subject')} loop {d.get('loop')} "
                  f"motion {d.get('motion')} image {d.get('image')}  total {tot}/40")

    if scores:
        print("\nRANKED (subject + loop + motion + image)")
        for tot, name, d in sorted(scores, reverse=True):
            print(f"  {tot:>3}/40  {name:<28} s{d.get('subject')} l{d.get('loop')} "
                  f"m{d.get('motion')} i{d.get('image')}")
    print(f"\nnotes -> {FEEDBACK.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
