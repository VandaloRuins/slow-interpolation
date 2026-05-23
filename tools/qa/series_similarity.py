"""Cross-piece similarity matrix. QA tool 5 of the slow-interpolation toolkit.

For a series of rendered pieces (the 25-piece objkt labs release, or any
batch of stills / videos), computes pairwise visual similarity using image
embeddings and emits both a matrix and a flag list. Useful for two
purposes:

- **Series coherence check.** Outliers (pieces too different from the
  series median) flag as off-brand candidates worth re-rendering or
  dropping. Near-duplicates (pieces too similar to a sibling) flag as
  redundant.
- **Diff against an external anchor.** Run a piece's CLIP embedding
  against, say, a single Soutine reference frame to verify the figure
  region is reading as Soutine. Or against a Renoir composite to verify
  the surround is reading as Renoir.

Embedding backend: CLIP ViT-B/32 by default (via `transformers` if
available, falls back to `open_clip` if installed). DINOv2 path stubbed in
but commented out; can be enabled once Modal infra has the right image
because DINOv2 weights are >300 MB and not appropriate to lazy-load on
every local run.

Inputs are PNG / JPEG / WEBP stills OR MP4 videos (in which case the tool
samples N evenly-spaced frames and pools their embeddings).

Usage:
    # Build a similarity matrix across a series
    python -m tools.qa.series_similarity \\
        --inputs outputs/release/*.mp4 \\
        --output-json outputs/release/qa/series_similarity.json \\
        --output-plot outputs/release/qa/series_similarity_matrix.png

    # Single-pair score
    python -m tools.qa.series_similarity \\
        --inputs piece_a.mp4 piece_b.mp4 \\
        --output-json /dev/stdout
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image

TOOL_NAME = "series_similarity"
TOOL_VERSION = "0.1.0"

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
DEFAULT_VIDEO_SAMPLES = 8

OUTLIER_LOW = 0.35
DUPLICATE_HIGH = 0.95


def _sample_video_frames(path: Path, n: int) -> Iterable[Image.Image]:
    import cv2

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video {path}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        cap.release()
        return
    samples = np.linspace(0, max(total - 1, 0), n).astype(int)
    last = -1
    for idx in samples:
        if idx == last:
            continue
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, frame = cap.read()
        if not ok:
            continue
        rgb = frame[:, :, ::-1]
        yield Image.fromarray(rgb)
        last = idx
    cap.release()


def _input_iter(path: Path, video_samples: int) -> list[Image.Image]:
    ext = path.suffix.lower()
    if ext in VIDEO_EXTS:
        return list(_sample_video_frames(path, video_samples))
    if ext in IMAGE_EXTS:
        return [Image.open(path).convert("RGB")]
    raise ValueError(f"unsupported input format {ext} for {path}")


def _load_clip_model():
    """Try transformers first, fall back to open_clip. Return (model, preprocess, encode_fn)."""
    try:
        import torch
        from transformers import CLIPModel, CLIPProcessor

        name = "openai/clip-vit-base-patch32"
        model = CLIPModel.from_pretrained(name)
        processor = CLIPProcessor.from_pretrained(name)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = model.to(device).eval()

        def encode(images: list[Image.Image]) -> np.ndarray:
            with torch.no_grad():
                inputs = processor(images=images, return_tensors="pt").to(device)
                feats = model.get_image_features(**inputs)
                feats = feats / feats.norm(dim=-1, keepdim=True)
                return feats.cpu().numpy()

        return encode, "transformers/clip-vit-base-patch32"
    except Exception as e:
        last_err = e

    try:
        import open_clip
        import torch

        model, _, preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="openai"
        )
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = model.to(device).eval()

        def encode(images: list[Image.Image]) -> np.ndarray:
            with torch.no_grad():
                batch = torch.stack([preprocess(im) for im in images]).to(device)
                feats = model.encode_image(batch)
                feats = feats / feats.norm(dim=-1, keepdim=True)
                return feats.cpu().numpy()

        return encode, "open_clip/ViT-B-32-openai"
    except Exception as e2:
        raise RuntimeError(
            "Need transformers+torch or open_clip for embeddings. "
            f"transformers err: {last_err}; open_clip err: {e2}"
        )


def embed_inputs(paths: list[Path], video_samples: int) -> tuple[np.ndarray, list[str], str]:
    encode, backend = _load_clip_model()
    vectors = []
    labels = []
    for p in paths:
        frames = _input_iter(p, video_samples)
        if not frames:
            continue
        feats = encode(frames)
        pooled = feats.mean(axis=0)
        pooled = pooled / (np.linalg.norm(pooled) + 1e-12)
        vectors.append(pooled)
        labels.append(p.name)
    if not vectors:
        raise RuntimeError("no embeddings produced; check input paths")
    return np.stack(vectors), labels, backend


def similarity_matrix(vectors: np.ndarray) -> np.ndarray:
    return vectors @ vectors.T


def _flag_outliers_duplicates(sim: np.ndarray, labels: list[str]) -> tuple[list[str], list[tuple[str, str, float]]]:
    n = sim.shape[0]
    flags_outliers = []
    flags_duplicates = []
    if n <= 1:
        return flags_outliers, flags_duplicates
    # outliers: pieces whose mean similarity to peers is < OUTLIER_LOW
    for i in range(n):
        peers = np.concatenate([sim[i, :i], sim[i, i + 1 :]])
        mean_peer = float(peers.mean()) if peers.size else 1.0
        if mean_peer < OUTLIER_LOW:
            flags_outliers.append(
                f"outlier: {labels[i]} mean-peer-similarity={mean_peer:.3f} (below {OUTLIER_LOW})"
            )
    # duplicates: pairs whose similarity > DUPLICATE_HIGH
    for i in range(n):
        for j in range(i + 1, n):
            if sim[i, j] > DUPLICATE_HIGH:
                flags_duplicates.append((labels[i], labels[j], float(sim[i, j])))
    return flags_outliers, flags_duplicates


def _plot_matrix(sim: np.ndarray, labels: list[str], out_path: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return
    fig, ax = plt.subplots(figsize=(max(6, 0.5 * len(labels)), max(6, 0.5 * len(labels))))
    im = ax.imshow(sim, cmap="viridis", vmin=0.0, vmax=1.0)
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    short = [l[:30] for l in labels]
    ax.set_xticklabels(short, rotation=75, ha="right", fontsize=7)
    ax.set_yticklabels(short, fontsize=7)
    fig.colorbar(im, ax=ax, label="cosine similarity")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", nargs="+", type=Path, required=True)
    parser.add_argument("--video-samples", type=int, default=DEFAULT_VIDEO_SAMPLES)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--output-plot", type=Path, default=None)
    args = parser.parse_args()

    vectors, labels, backend = embed_inputs(args.inputs, args.video_samples)
    sim = similarity_matrix(vectors)
    outliers, duplicates = _flag_outliers_duplicates(sim, labels)

    result = {
        "tool": TOOL_NAME,
        "version": TOOL_VERSION,
        "backend": backend,
        "video_samples_per_input": args.video_samples,
        "labels": labels,
        "similarity_matrix": sim.tolist(),
        "outlier_flags": outliers,
        "duplicate_pairs": [
            {"a": a, "b": b, "similarity": s} for a, b, s in duplicates
        ],
        "summary": {
            "n_inputs": len(labels),
            "mean_offdiag_similarity": float(
                (sim.sum() - np.trace(sim)) / max(1, len(labels) * (len(labels) - 1))
            ),
        },
    }

    if args.output_json:
        if str(args.output_json) == "/dev/stdout":
            print(json.dumps(result, indent=2))
        else:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_json.write_text(json.dumps(result, indent=2))
    if args.output_plot:
        _plot_matrix(sim, labels, args.output_plot)

    s = result["summary"]
    print(
        f"backend={backend} n={s['n_inputs']} "
        f"mean_offdiag={s['mean_offdiag_similarity']:.3f} "
        f"outliers={len(outliers)} duplicates={len(duplicates)}"
    )


if __name__ == "__main__":
    main()
