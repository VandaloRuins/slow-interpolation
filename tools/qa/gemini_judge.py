"""Gemini-as-judge. QA tool 4 of the slow-interpolation compositing toolkit.

Sends a rendered frame (and, for compositing pieces, its figure alpha matte) to
Gemini with a four-axis rubric: edge-wrap legibility, palette friction,
painterly read, seam visibility. Returns 1-to-10 grades per axis plus a single
sentence of reasoning per axis. v0 single-frame mode only; multi-frame motion
smoothness rubric is left for v0.2 (the optical-flow tool at
`tools/qa/motion_continuity.py` covers the temporal axis today).

This tool is NOT a gatekeeper. Luca's eye remains the lock. The grades surface
candidates for review and flag regressions across the 25-piece release.

The rubric:

    edge_wrap (1-10): Does brushwork cross the figure-ground silhouette? A
        slap-on figure scores low; a painted-into-the-painting figure scores
        high. Anchored on design.md "Edge-wrap specification".

    palette_friction (1-10): Does the figure region read as Soutine (carcass
        red, raw umber, dragging impasto) while the surround reads as Renoir
        (pink, ivory, broken impasto)? A unified palette scores low; the
        deliberate two-painter friction scores high.

    painterly_read (1-10): Does the whole frame read as one painting (not a
        composite of two renders, not an alpha overlay)? A photoreal or
        digital-art read scores low; a "made of paint, one canvas" read scores
        high.

    seam_visibility (1-10, INVERTED): How visible is the figure-ground seam as
        a technical artefact? 1 = totally invisible seam (best); 10 = obvious
        cut-out (worst). Inverted scale so all other axes are "higher is
        better" and seam is "lower is better".

Usage:
    # Single rendered frame, no alpha
    python -m tools.qa.gemini_judge \\
        --frame outputs/<piece>/keyframes/0042.png \\
        --output-json outputs/<piece>/qa/judge_0042.json

    # Compositing frame with figure alpha for region-aware grading
    python -m tools.qa.gemini_judge \\
        --frame outputs/<piece>/keyframes/0042.png \\
        --alpha outputs/<piece>/alpha/0042.png \\
        --output-json outputs/<piece>/qa/judge_0042.json

    # Batch a directory of frames; emits per-frame JSON + an aggregate.json
    python -m tools.qa.gemini_judge \\
        --frame-dir outputs/<piece>/keyframes/ \\
        --output-dir outputs/<piece>/qa/judge/

Outputs:
    Single-frame mode: JSON with grades (4 axes), reasoning sentences,
    model + timestamp.

    Batch mode: per-frame JSONs, plus aggregate.json with per-axis mean / std
    / min / max across the batch, plus the list of weakest frames per axis
    (for targeted re-review).

API: Gemini REST endpoint directly via requests (no SDK; matches the pattern
in datasets/soutine-figures/gemini_review.py to dodge system-Python pydantic
breakage).
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
from pathlib import Path

import requests
from PIL import Image

TOOL_NAME = "gemini_judge"
TOOL_VERSION = "0.1.0"

DEFAULT_MODEL = "gemini-2.5-flash"  # gemini-3-flash returned 404 on 2026-05-18; revisit when GA
ENDPOINT_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

RUBRIC_PROMPT = """You are grading rendered frames from a slow-interpolation
diffusion pipeline. The artistic target combines two painters in one frame:
Renoir (impressionist florals, pink and ivory palette, broken impasto petals,
soft luminous handling) and Soutine (expressionist figures, carcass red and
raw umber palette, dragging impasto, twisted forms). Strategy C / D pieces
have a Soutine-painted figure inside a Renoir-painted surround. Strategy B
pieces have a single Renoir-painted figure inside a Renoir surround.

If a figure alpha matte is provided (separate input image, white = figure,
black = surround), use it to identify the figure region precisely. Otherwise
infer the figure region from the frame.

Grade four axes. Return STRICT JSON, no markdown, no surrounding prose:

{
  "edge_wrap": <int 1-10>,
  "edge_wrap_reason": "<one short sentence>",
  "palette_friction": <int 1-10>,
  "palette_friction_reason": "<one short sentence>",
  "painterly_read": <int 1-10>,
  "painterly_read_reason": "<one short sentence>",
  "seam_visibility": <int 1-10>,
  "seam_visibility_reason": "<one short sentence>"
}

Axis definitions:

- edge_wrap (higher is better): Do brushstrokes cross the figure-ground
  boundary so the figure reads as painted INTO the canvas? Score 10 if a
  Renoir petal-stroke clearly flicks across the silhouette or a Soutine smear
  bleeds half a centimeter into the surround. Score 1 if the boundary reads
  as a hard alpha cut-out.

- palette_friction (higher is better): Does the figure region read in
  Soutine palette (or Renoir palette for strategy-B pieces named as such)
  while the surround reads in Renoir palette? Score 10 when the two
  registers are clearly distinct and intentional. Score 1 when one register
  has saturated the whole frame.

- painterly_read (higher is better): Does the whole frame read as one
  painting? Score 10 for a coherent oil-painting surface. Score 1 for a
  photoreal, digital-art, or composited read.

- seam_visibility (LOWER is better, scale is inverted): How visible is the
  figure-ground boundary as a TECHNICAL artefact? Score 1 if no seam is
  visible at all. Score 10 if the figure looks pasted on top of the
  background.

Reasoning sentences must be one sentence each, specific to the frame, no
boilerplate.
"""


def _load_env_key() -> str | None:
    """Walk the known .env locations for a Gemini key. Mirrors the pattern
    in datasets/soutine-figures/gemini_review.py to dodge system-Python
    pydantic breakage."""
    for env_path in [
        Path("C:/Users/lucaa/OneDrive/Desktop/RNMW-agent/.env"),
        Path("C:/Users/lucaa/OneDrive/Desktop/Choire-v2/.env"),
        Path(__file__).resolve().parents[2] / ".env",
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


def _image_to_b64(path: Path, max_side: int = 1280) -> tuple[str, str]:
    """Load image, downsample if larger than max_side on the longest side,
    return (mime_type, base64_data). Downsampling keeps the API payload
    reasonable; Gemini does not need 4K input to grade a painterly frame."""
    img = Image.open(path).convert("RGB")
    w, h = img.size
    longest = max(w, h)
    if longest > max_side:
        scale = max_side / longest
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return "image/jpeg", base64.b64encode(buf.getvalue()).decode("ascii")


def _alpha_to_b64(path: Path, max_side: int = 1280) -> tuple[str, str]:
    """Load alpha as grayscale, downsample, return (mime, b64). Always JPEG
    for transport; the alpha is just a visual cue for the model, not a
    pixel-precise mask."""
    img = Image.open(path).convert("L")
    w, h = img.size
    longest = max(w, h)
    if longest > max_side:
        scale = max_side / longest
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=92)
    return "image/jpeg", base64.b64encode(buf.getvalue()).decode("ascii")


def _parse_json_response(text: str) -> dict:
    """Tolerant JSON parse. Gemini occasionally wraps the JSON in a code
    fence even when instructed not to."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip("`").strip()
    return json.loads(text)


def grade_frame(
    api_key: str,
    frame_path: Path,
    alpha_path: Path | None,
    model: str = DEFAULT_MODEL,
    max_retries: int = 2,
) -> dict:
    """Send one frame (and optional alpha) to Gemini; return the parsed
    rubric dict + metadata."""
    parts: list[dict] = [{"text": RUBRIC_PROMPT}]
    mime, b64 = _image_to_b64(frame_path)
    parts.append({"inline_data": {"mime_type": mime, "data": b64}})
    if alpha_path is not None:
        a_mime, a_b64 = _alpha_to_b64(alpha_path)
        parts.append(
            {"text": "The image below is the figure alpha matte (white = figure, black = surround):"}
        )
        parts.append({"inline_data": {"mime_type": a_mime, "data": a_b64}})

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.2},
    }
    url = ENDPOINT_TEMPLATE.format(model=model) + f"?key={api_key}"

    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            r = requests.post(url, json=payload, timeout=60)
            r.raise_for_status()
            data = r.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = _parse_json_response(text)
            return {
                "tool": TOOL_NAME,
                "version": TOOL_VERSION,
                "model": model,
                "frame": str(frame_path),
                "alpha": str(alpha_path) if alpha_path else None,
                "grades": parsed,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                time.sleep(2 * (attempt + 1))
            continue
    raise RuntimeError(f"gemini_judge failed after {max_retries + 1} attempts: {last_err}")


def _aggregate(grades_list: list[dict]) -> dict:
    """Per-axis mean/std/min/max + weakest-frame list across a batch."""
    axes = ["edge_wrap", "palette_friction", "painterly_read", "seam_visibility"]
    valid = [g for g in grades_list if "grades" in g and all(a in g["grades"] for a in axes)]
    if not valid:
        return {"n": 0, "note": "no valid grades to aggregate"}

    summary: dict = {"n": len(valid), "axes": {}}
    for ax in axes:
        vals = [g["grades"][ax] for g in valid]
        summary["axes"][ax] = {
            "mean": sum(vals) / len(vals),
            "min": min(vals),
            "max": max(vals),
            "std": (sum((v - sum(vals) / len(vals)) ** 2 for v in vals) / len(vals)) ** 0.5,
        }

    weakest: dict[str, list[str]] = {}
    for ax in axes:
        worst_value = 10 if ax == "seam_visibility" else 1
        sorted_frames = sorted(
            valid,
            key=lambda g: g["grades"][ax],
            reverse=(ax == "seam_visibility"),
        )
        weakest[ax] = [g["frame"] for g in sorted_frames[:5]]
    summary["weakest_per_axis"] = weakest
    return summary


def _gather_frames(frame_dir: Path) -> list[Path]:
    return sorted(p for p in frame_dir.iterdir() if p.suffix.lower() in EXTENSIONS)


def _alpha_for(frame_path: Path, alpha_dir: Path | None) -> Path | None:
    """Locate the alpha for a given frame in alpha_dir. Matches by stem; if
    no match, returns None and the frame is graded without alpha."""
    if alpha_dir is None:
        return None
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        candidate = alpha_dir / f"{frame_path.stem}{ext}"
        if candidate.exists():
            return candidate
    return None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--frame", type=Path, help="Single rendered frame to grade.")
    g.add_argument("--frame-dir", type=Path, help="Directory of frames to batch-grade.")
    p.add_argument("--alpha", type=Path, default=None, help="Figure alpha matte (single-frame mode).")
    p.add_argument(
        "--alpha-dir",
        type=Path,
        default=None,
        help="Directory of alphas, matched by stem (batch mode).",
    )
    p.add_argument("--output-json", type=Path, default=None, help="JSON output path (single-frame mode).")
    p.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for per-frame JSONs + aggregate.json (batch mode).",
    )
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"Gemini model id (default: {DEFAULT_MODEL}).")
    p.add_argument(
        "--max-retries", type=int, default=2, help="Retry count on transient API errors."
    )
    args = p.parse_args(argv)

    api_key = _load_env_key()
    if not api_key:
        print("error: no GEMINI_API_KEY / GOOGLE_API_KEY in env", file=sys.stderr)
        return 2

    if args.frame is not None:
        if not args.frame.exists():
            print(f"error: frame not found: {args.frame}", file=sys.stderr)
            return 2
        result = grade_frame(api_key, args.frame, args.alpha, model=args.model, max_retries=args.max_retries)
        out_path = args.output_json or args.frame.with_suffix(".judge.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"graded -> {out_path}")
        for ax, val in result["grades"].items():
            if not ax.endswith("_reason"):
                print(f"  {ax}: {val}")
        return 0

    # Batch mode
    if args.output_dir is None:
        print("error: --output-dir required in batch mode", file=sys.stderr)
        return 2
    frames = _gather_frames(args.frame_dir)
    if not frames:
        print(f"error: no frames in {args.frame_dir}", file=sys.stderr)
        return 2
    args.output_dir.mkdir(parents=True, exist_ok=True)

    grades_list: list[dict] = []
    for i, frame in enumerate(frames, 1):
        alpha = _alpha_for(frame, args.alpha_dir)
        try:
            res = grade_frame(api_key, frame, alpha, model=args.model, max_retries=args.max_retries)
        except Exception as e:
            print(f"  [{i}/{len(frames)}] {frame.name}: ERROR {e}", file=sys.stderr)
            grades_list.append({"frame": str(frame), "error": str(e)})
            continue
        out_path = args.output_dir / f"{frame.stem}.judge.json"
        out_path.write_text(json.dumps(res, indent=2), encoding="utf-8")
        grades_list.append(res)
        ew = res["grades"].get("edge_wrap", "?")
        pf = res["grades"].get("palette_friction", "?")
        pr = res["grades"].get("painterly_read", "?")
        sv = res["grades"].get("seam_visibility", "?")
        print(f"  [{i}/{len(frames)}] {frame.name}: ew={ew} pf={pf} pr={pr} sv={sv}")

    agg = _aggregate(grades_list)
    (args.output_dir / "aggregate.json").write_text(json.dumps(agg, indent=2), encoding="utf-8")
    print(f"\naggregate -> {args.output_dir / 'aggregate.json'}")
    if "axes" in agg:
        for ax, stats in agg["axes"].items():
            print(f"  {ax}: mean={stats['mean']:.2f} min={stats['min']} max={stats['max']} std={stats['std']:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
