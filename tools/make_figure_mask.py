"""Procedural figure-shaped feathered mask generator.

Produces a PNG mask suitable for SDXL inpaint passes in the compositing sketch
flow. The mask is a soft-edged human figure silhouette composited from
ellipses (head, torso, legs). Not a real segmentation; the point is to test
how an SDXL inpaint pass with a Soutine LoRA reads inside a Renoir-painted
surround, before real figure videos exist.

For the actual release the mask is replaced by BiRefNet / RMBG-2.0 alphas
computed on a real figure video. See design.md section 1 and section 4 in
docs/planning/workstreams/compositing/layering-study.md.

Output: PNG, white = figure (inpaint here), black = surround (keep
untouched), soft Gaussian feather at the boundary.

Usage:
    python -m tools.make_figure_mask \\
        --width 832 --height 1216 \\
        --figure-height-frac 0.35 \\
        --head-center-y-frac 0.44 \\
        --center-x-frac 0.50 \\
        --feather-frac 0.03 \\
        --output datasets/compositing/masks/sketch01_distant_back_view.png

Position-class presets (from docs/planning/workstreams/compositing/layering-study.md
section 2.1):
    centered_full    : figure-height 0.80, head-center 0.16, center-x 0.50
    centered_compact : figure-height 0.55, head-center 0.32, center-x 0.50
    offset_third     : figure-height 0.65, head-center 0.25, center-x 0.33 or 0.67
    figure_distant   : figure-height 0.30 to 0.40, head-center 0.40 to 0.50

`figure_distant` is the small-figure-in-vast-field case (sketch01) and is
added here to support the "high distance flower field" scene.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


TOOL_NAME = "make_figure_mask"
TOOL_VERSION = "0.1.0"


def _draw_figure(
    canvas_size: tuple[int, int],
    figure_height_px: int,
    head_center_y_px: int,
    center_x_px: int,
) -> Image.Image:
    """Draw a crude full-body silhouette using ellipses + a torso polygon.

    Proportions follow the standard 7.5-head adult canon, adjusted for
    legibility at small absolute pixel sizes:
        head height   = figure_height / 7
        shoulder span = head_height * 3.0
        torso height  = figure_height * 0.38
        leg length    = figure_height * 0.50
    """
    w, h = canvas_size
    img = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(img)

    head_h = max(int(figure_height_px / 7), 12)
    head_w = int(head_h * 0.82)

    shoulder_span = int(head_h * 3.0)
    hip_span = int(head_h * 2.2)

    torso_h = int(figure_height_px * 0.38)
    leg_h = int(figure_height_px * 0.50)
    leg_w = max(int(head_w * 0.85), 8)

    # Head: ellipse centered at (center_x, head_center_y)
    draw.ellipse(
        [
            center_x_px - head_w // 2,
            head_center_y_px - head_h // 2,
            center_x_px + head_w // 2,
            head_center_y_px + head_h // 2,
        ],
        fill=255,
    )

    # Neck: short rectangle
    neck_top = head_center_y_px + head_h // 2 - 2
    neck_h = max(int(head_h * 0.25), 4)
    neck_w = max(int(head_w * 0.45), 6)
    draw.rectangle(
        [
            center_x_px - neck_w // 2,
            neck_top,
            center_x_px + neck_w // 2,
            neck_top + neck_h,
        ],
        fill=255,
    )

    # Torso: trapezoid (shoulder wide, hip narrower)
    shoulder_y = neck_top + neck_h
    hip_y = shoulder_y + torso_h
    draw.polygon(
        [
            (center_x_px - shoulder_span // 2, shoulder_y),
            (center_x_px + shoulder_span // 2, shoulder_y),
            (center_x_px + hip_span // 2, hip_y),
            (center_x_px - hip_span // 2, hip_y),
        ],
        fill=255,
    )

    # Two legs: left + right rectangles, slight outward splay
    leg_top_y = hip_y
    leg_bottom_y = leg_top_y + leg_h
    left_leg_x = center_x_px - int(hip_span * 0.28)
    right_leg_x = center_x_px + int(hip_span * 0.28)
    draw.rectangle(
        [left_leg_x - leg_w // 2, leg_top_y, left_leg_x + leg_w // 2, leg_bottom_y],
        fill=255,
    )
    draw.rectangle(
        [right_leg_x - leg_w // 2, leg_top_y, right_leg_x + leg_w // 2, leg_bottom_y],
        fill=255,
    )

    # Arms: short downward rectangles at shoulder corners (back view, arms at sides)
    arm_w = max(int(head_w * 0.55), 7)
    arm_h = int(torso_h * 0.85)
    left_arm_x = center_x_px - shoulder_span // 2 + arm_w // 2
    right_arm_x = center_x_px + shoulder_span // 2 - arm_w // 2
    draw.rectangle(
        [left_arm_x - arm_w // 2, shoulder_y, left_arm_x + arm_w // 2, shoulder_y + arm_h],
        fill=255,
    )
    draw.rectangle(
        [right_arm_x - arm_w // 2, shoulder_y, right_arm_x + arm_w // 2, shoulder_y + arm_h],
        fill=255,
    )

    return img


def make_mask(
    width: int,
    height: int,
    figure_height_frac: float,
    head_center_y_frac: float,
    center_x_frac: float,
    feather_frac: float,
) -> Image.Image:
    """Return a feathered grayscale mask PNG. White = figure region."""
    figure_height_px = int(height * figure_height_frac)
    head_center_y_px = int(height * head_center_y_frac)
    center_x_px = int(width * center_x_frac)

    binary = _draw_figure(
        (width, height),
        figure_height_px,
        head_center_y_px,
        center_x_px,
    )

    # Feather radius is a fraction of the figure's shorter dimension. For a
    # body-shaped silhouette the shorter dim is figure_height / 3 (~shoulder
    # span). Match design.md's edge-wrap spec: 2 to 4% of figure shorter dim.
    shorter_dim = figure_height_px / 3
    feather_px = max(int(shorter_dim * feather_frac), 4)
    sigma = feather_px / 3.0

    feathered = binary.filter(ImageFilter.GaussianBlur(radius=sigma))
    return feathered


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--width", type=int, default=832)
    p.add_argument("--height", type=int, default=1216)
    p.add_argument(
        "--figure-height-frac",
        type=float,
        default=0.35,
        help="Figure height as fraction of frame height. Default 0.35 (figure_distant class).",
    )
    p.add_argument(
        "--head-center-y-frac",
        type=float,
        default=0.44,
        help="Head center y as fraction of frame height (0=top). Default 0.44, just below typical horizon.",
    )
    p.add_argument(
        "--center-x-frac",
        type=float,
        default=0.50,
        help="Figure horizontal center as fraction of frame width. Default 0.50.",
    )
    p.add_argument(
        "--feather-frac",
        type=float,
        default=0.03,
        help="Feather radius as fraction of figure shorter dimension. Default 0.03 (3%).",
    )
    p.add_argument("--output", type=Path, required=True, help="Output PNG path.")
    args = p.parse_args(argv)

    mask = make_mask(
        width=args.width,
        height=args.height,
        figure_height_frac=args.figure_height_frac,
        head_center_y_frac=args.head_center_y_frac,
        center_x_frac=args.center_x_frac,
        feather_frac=args.feather_frac,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    mask.save(args.output)

    # Compute coverage and report
    arr = np.array(mask) / 255.0
    coverage = float(arr.mean())
    print(f"mask written -> {args.output}")
    print(f"  size: {args.width}x{args.height}")
    print(f"  figure height: {args.figure_height_frac:.2f} of frame ({int(args.height * args.figure_height_frac)} px)")
    print(f"  coverage (avg alpha): {coverage:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
