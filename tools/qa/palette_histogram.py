"""Palette histogram analysis. QA tool 2 of the slow-interpolation toolkit.

Computes color-distribution histograms in CIELAB space for an image or a
batch (a directory) and either:

- Builds a reference palette from a dataset (the `--build-reference` mode).
  Aggregates LAB histograms across every JPEG / PNG under the source path
  and saves the result as a reference JSON.
- Compares an input image or render against a previously-built reference
  palette and reports a similarity score and per-channel divergence.

Two reference palettes are expected for the compositing workstream:

    tools/qa/calibration/palette_histogram/renoir_reference.json
    tools/qa/calibration/palette_histogram/soutine_reference.json

The Renoir reference is buildable today from `datasets/renoir-flowers/raw/`.
The Soutine reference lands once the Soutine LoRA training set exists.

Usage:
    # Build a reference palette from the Renoir dataset
    python -m tools.qa.palette_histogram \\
        --build-reference \\
        --source datasets/renoir-flowers/raw \\
        --label renoir \\
        --output tools/qa/calibration/palette_histogram/renoir_reference.json

    # Score a rendered frame against the Renoir reference
    python -m tools.qa.palette_histogram \\
        --frame outputs/<piece>/keyframes/0042.png \\
        --reference tools/qa/calibration/palette_histogram/renoir_reference.json \\
        --output-json outputs/<piece>/qa/palette_0042.json

    # Score a frame's masked figure region against the Soutine reference
    # and the surround against the Renoir reference (compositing case)
    python -m tools.qa.palette_histogram \\
        --frame <frame.png> --alpha <alpha.png> \\
        --reference-inside soutine_reference.json \\
        --reference-outside renoir_reference.json \\
        --output-json <output.json>

The two-region mode is the compositing-strategy-C / D acceptance signal: each
region's color distribution should match its assigned painter, not the
other.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

TOOL_NAME = "palette_histogram"
TOOL_VERSION = "0.1.0"

LAB_BINS_L = 16
LAB_BINS_A = 16
LAB_BINS_B = 16

EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """Convert RGB uint8 (H, W, 3) to CIE LAB float (H, W, 3).

    Uses skimage if available (proper LAB), falls back to OpenCV otherwise.
    """
    try:
        from skimage.color import rgb2lab

        return rgb2lab(rgb.astype(np.float32) / 255.0)
    except ImportError:
        pass
    try:
        import cv2

        lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
        lab[..., 0] *= 100.0 / 255.0
        lab[..., 1] -= 128.0
        lab[..., 2] -= 128.0
        return lab
    except ImportError:
        pass
    raise RuntimeError(
        "Need skimage or opencv-python for LAB conversion; neither is installed."
    )


def _histogram(lab: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    """Return a 3-D LAB histogram (LAB_BINS_L x A x B), normalized."""
    if mask is not None:
        flat = lab[mask]
    else:
        flat = lab.reshape(-1, 3)
    edges_l = np.linspace(0, 100, LAB_BINS_L + 1)
    edges_a = np.linspace(-128, 128, LAB_BINS_A + 1)
    edges_b = np.linspace(-128, 128, LAB_BINS_B + 1)
    H, _ = np.histogramdd(
        flat,
        bins=(edges_l, edges_a, edges_b),
    )
    total = H.sum()
    if total > 0:
        H = H / total
    return H.astype(np.float32)


def _iter_image_paths(source: Path):
    if source.is_file():
        yield source
        return
    for ext in EXTENSIONS:
        yield from source.rglob(f"*{ext}")


def _load_rgb(path: Path) -> np.ndarray:
    img = Image.open(path).convert("RGB")
    return np.array(img)


def build_reference(source: Path, label: str) -> dict:
    """Aggregate LAB histograms across every image under `source`."""
    accum = np.zeros((LAB_BINS_L, LAB_BINS_A, LAB_BINS_B), dtype=np.float64)
    count = 0
    for p in _iter_image_paths(source):
        try:
            rgb = _load_rgb(p)
        except Exception:
            continue
        lab = _rgb_to_lab(rgb)
        H = _histogram(lab)
        accum += H
        count += 1
    if count == 0:
        raise RuntimeError(f"no images found under {source}")
    accum = accum / accum.sum()
    return {
        "tool": TOOL_NAME,
        "version": TOOL_VERSION,
        "kind": "reference",
        "label": label,
        "source": str(source),
        "n_images": int(count),
        "histogram_shape": [LAB_BINS_L, LAB_BINS_A, LAB_BINS_B],
        "histogram": accum.tolist(),
    }


def _jensen_shannon(p: np.ndarray, q: np.ndarray, eps: float = 1e-12) -> float:
    p = p.flatten() + eps
    q = q.flatten() + eps
    p = p / p.sum()
    q = q / q.sum()
    m = 0.5 * (p + q)
    kl = lambda a, b: np.sum(a * np.log(a / b))
    return float(0.5 * kl(p, m) + 0.5 * kl(q, m))


def _palette_score(hist: np.ndarray, reference_hist: np.ndarray) -> float:
    """JS-divergence to similarity. 1.0 = identical, 0.0 = far."""
    js = _jensen_shannon(hist, reference_hist)
    return float(1.0 / (1.0 + js))


def score_frame(
    frame_path: Path,
    reference: dict | None,
    alpha_path: Path | None = None,
    reference_inside: dict | None = None,
    reference_outside: dict | None = None,
) -> dict:
    rgb = _load_rgb(frame_path)
    lab = _rgb_to_lab(rgb)

    out: dict = {
        "tool": TOOL_NAME,
        "version": TOOL_VERSION,
        "input": {"frame": str(frame_path)},
        "metrics": {},
        "flags": [],
    }

    if alpha_path is not None and (reference_inside or reference_outside):
        alpha_img = Image.open(alpha_path).convert("L").resize(
            (rgb.shape[1], rgb.shape[0]), Image.BILINEAR
        )
        alpha = np.array(alpha_img).astype(np.float32) / 255.0
        inside_mask = alpha >= 0.95
        outside_mask = alpha <= 0.05
        out["input"]["alpha"] = str(alpha_path)

        if reference_inside is not None:
            inside_hist = _histogram(lab, inside_mask)
            ref_inside = np.array(reference_inside["histogram"], dtype=np.float32)
            score = _palette_score(inside_hist, ref_inside)
            out["metrics"]["inside_similarity_to_inside_ref"] = score
            out["metrics"]["inside_reference_label"] = reference_inside.get("label", "")
            if score < 0.6:
                out["flags"].append(
                    f"inside_palette_drift: figure region similarity to "
                    f"{reference_inside.get('label', 'inside ref')} = {score:.3f} "
                    f"(threshold 0.6)"
                )
        if reference_outside is not None:
            outside_hist = _histogram(lab, outside_mask)
            ref_outside = np.array(reference_outside["histogram"], dtype=np.float32)
            score = _palette_score(outside_hist, ref_outside)
            out["metrics"]["outside_similarity_to_outside_ref"] = score
            out["metrics"]["outside_reference_label"] = reference_outside.get("label", "")
            if score < 0.6:
                out["flags"].append(
                    f"outside_palette_drift: surround similarity to "
                    f"{reference_outside.get('label', 'outside ref')} = {score:.3f} "
                    f"(threshold 0.6)"
                )
        # Cross-check: figure region should NOT look like the surround reference
        if reference_outside is not None:
            cross_hist = _histogram(lab, inside_mask)
            ref_outside_arr = np.array(reference_outside["histogram"], dtype=np.float32)
            cross_score = _palette_score(cross_hist, ref_outside_arr)
            out["metrics"]["inside_similarity_to_outside_ref"] = cross_score
            if cross_score > 0.75:
                out["flags"].append(
                    f"register_bleed: figure region too similar to "
                    f"{reference_outside.get('label', 'outside ref')} = {cross_score:.3f}. "
                    f"Strategy C dual-LoRA may be bleeding."
                )
    elif reference is not None:
        hist = _histogram(lab)
        ref = np.array(reference["histogram"], dtype=np.float32)
        score = _palette_score(hist, ref)
        out["metrics"]["similarity_to_reference"] = score
        out["metrics"]["reference_label"] = reference.get("label", "")
        if score < 0.6:
            out["flags"].append(
                f"palette_drift: similarity {score:.3f} below threshold 0.6"
            )
    else:
        raise ValueError("provide either --reference or --reference-inside/-outside")

    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-reference", action="store_true")
    parser.add_argument("--source", type=Path, help="dataset path for --build-reference")
    parser.add_argument("--label", type=str, default="unlabeled")
    parser.add_argument("--output", type=Path, help="output path for --build-reference")
    parser.add_argument("--frame", type=Path)
    parser.add_argument("--alpha", type=Path, default=None)
    parser.add_argument("--reference", type=Path, default=None)
    parser.add_argument("--reference-inside", type=Path, default=None)
    parser.add_argument("--reference-outside", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, default=None)
    args = parser.parse_args()

    if args.build_reference:
        if not args.source or not args.output:
            parser.error("--build-reference requires --source and --output")
        data = build_reference(args.source, args.label)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(data))
        print(f"reference '{data['label']}' built from {data['n_images']} images -> {args.output}")
        return

    if not args.frame:
        parser.error("--frame required for scoring mode")

    reference = json.loads(args.reference.read_text()) if args.reference else None
    reference_inside = json.loads(args.reference_inside.read_text()) if args.reference_inside else None
    reference_outside = json.loads(args.reference_outside.read_text()) if args.reference_outside else None

    result = score_frame(
        args.frame,
        reference=reference,
        alpha_path=args.alpha,
        reference_inside=reference_inside,
        reference_outside=reference_outside,
    )

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(result, indent=2))
    print(json.dumps(result["metrics"], indent=2))
    if result["flags"]:
        print("flags:")
        for f in result["flags"]:
            print(f"  - {f}")


if __name__ == "__main__":
    main()
