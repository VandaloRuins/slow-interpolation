"""Draw a crude massing sketch to use as a structural anchor.

Six prompt generations failed to make the model draw the Times Square bowtie,
so stop describing the geometry and hand it over directly. This produces a
tonal block sketch, not a picture: two avenues converging into a triangular
plaza, a wedge tower at the apex crowned with a sphere, dark building masses
framing left and right, luminous sky behind.

It deliberately carries Cole's VALUE STRUCTURE as well as the geometry, since
that was the other thing missing: dark repoussoir in front, luminous centre,
hazy blue distance. img2img at a moderate strength then paints it.

    python tools/make_massing.py --out outputs/_anchors/times-square.png

No photograph, no copyright, no rights question for a commercial billboard.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def build(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h), (26, 26, 34))
    d = ImageDraw.Draw(img)

    horizon = int(h * 0.56)
    vx, vy = int(w * 0.50), horizon          # vanishing point at the apex

    # Sky: luminous band low, deepening upward. This is the value ladder's top.
    # NEUTRAL GREY on purpose. An earlier version baked a warm golden glow in
    # here, which seeded the palette as well as the geometry and pushed every
    # render toward terracotta. The anchor supplies STRUCTURE; colour must come
    # from the prompt and the LoRA, or you cannot tell which is which.
    for y in range(horizon):
        f = y / horizon
        v = int(34 + 120 * f ** 2)
        d.line([(0, y), (w, y)], fill=(v, v + 4, v + 10))
    glow = Image.new("RGB", (w, h), (0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [vx - w * 0.22, vy - h * 0.20, vx + w * 0.22, vy + h * 0.10],
        fill=(198, 200, 204))
    img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(90)), 0.55)
    d = ImageDraw.Draw(img)

    # Ground plane, lighter than the buildings so the streets read as openings.
    d.polygon([(0, h), (w, h), (w, horizon), (0, horizon)], fill=(54, 54, 56))

    # The two avenues converging on the apex: the bowtie.
    d.polygon([(int(w * -0.05), h), (int(w * 0.34), h), (vx, vy)], fill=(92, 92, 96))
    d.polygon([(int(w * 0.66), h), (int(w * 1.05), h), (vx, vy)], fill=(92, 92, 96))

    # Framing building masses, dark: the repoussoir.
    d.polygon([(0, h), (0, int(h * 0.10)), (int(w * 0.20), int(h * 0.20)),
               (int(w * 0.30), horizon), (int(w * 0.26), h)], fill=(28, 28, 30))
    d.polygon([(w, h), (w, int(h * 0.12)), (int(w * 0.82), int(h * 0.22)),
               (int(w * 0.71), horizon), (int(w * 0.75), h)], fill=(26, 26, 29))
    # Mid-distance blocks stepping down toward the apex.
    for i, (x0, x1, top) in enumerate([(0.30, 0.40, 0.33), (0.60, 0.70, 0.35),
                                       (0.40, 0.455, 0.40), (0.545, 0.60, 0.41)]):
        d.rectangle([int(w * x0), int(h * top), int(w * x1), horizon],
                    fill=(42 + i * 4, 42 + i * 4, 45 + i * 4))

    # THE ANCHOR: the wedge at the apex, crowned with a sphere.
    tw_top, tw_bot = int(w * 0.020), int(w * 0.052)
    tw_y = int(h * 0.11)
    d.polygon([(vx - tw_top, tw_y), (vx + tw_top, tw_y),
               (vx + tw_bot, horizon), (vx - tw_bot, horizon)], fill=(50, 50, 53))
    r = int(w * 0.019)
    d.ellipse([vx - r, tw_y - 2 * r, vx + r, tw_y], fill=(226, 228, 232))

    # Soften: this is massing, not architecture. Hard vector edges would fight
    # img2img and print through as CG geometry.
    return img.filter(ImageFilter.GaussianBlur(3))


def build_depth(w: int, h: int) -> Image.Image:
    """A true depth map for ControlNet: WHITE = near, BLACK = far.

    Drawn, not estimated. A depth map of the bowtie is simple geometry, and
    authoring it directly is both more precise than depth-estimating a
    photograph and free of any rights question for a commercial release.
    """
    img = Image.new("RGB", (w, h), (0, 0, 0))          # sky = infinitely far
    d = ImageDraw.Draw(img)
    horizon = int(h * 0.56)
    vx, vy = int(w * 0.50), horizon

    # Ground: near at the bottom of frame, receding to the apex.
    for y in range(horizon, h):
        f = (y - horizon) / max(1, h - horizon)
        v = int(20 + 210 * f)
        d.line([(0, y), (w, y)], fill=(v, v, v))

    # The two avenues run to the vanishing point, so they are the deepest part
    # of the ground plane: darken them back toward the apex.
    for i in range(60):
        f = i / 59
        y = int(h - (h - horizon) * f)
        halfw = int(w * (0.34 - 0.33 * f))
        v = int(200 * (1 - f) + 18)
        d.polygon([(vx - halfw, y), (vx + halfw, y),
                   (vx + int(halfw * .93), y - 6), (vx - int(halfw * .93), y - 6)],
                  fill=(v, v, v))

    # Framing masses: nearest objects in frame, so brightest.
    d.polygon([(0, h), (0, int(h * 0.10)), (int(w * 0.20), int(h * 0.20)),
               (int(w * 0.30), horizon), (int(w * 0.26), h)], fill=(238, 238, 238))
    d.polygon([(w, h), (w, int(h * 0.12)), (int(w * 0.82), int(h * 0.22)),
               (int(w * 0.71), horizon), (int(w * 0.75), h)], fill=(232, 232, 232))
    # Mid-distance blocks, stepping darker as they recede.
    for i, (x0, x1, top) in enumerate([(0.30, 0.40, 0.33), (0.60, 0.70, 0.35),
                                       (0.40, 0.455, 0.40), (0.545, 0.60, 0.41)]):
        v = 150 - i * 22
        d.rectangle([int(w * x0), int(h * top), int(w * x1), horizon], fill=(v, v, v))

    # The wedge at the apex: far, but a distinct mass against the black sky.
    tw_top, tw_bot = int(w * 0.020), int(w * 0.052)
    tw_y = int(h * 0.11)
    d.polygon([(vx - tw_top, tw_y), (vx + tw_top, tw_y),
               (vx + tw_bot, horizon), (vx - tw_bot, horizon)], fill=(96, 96, 96))
    r = int(w * 0.019)
    d.ellipse([vx - r, tw_y - 2 * r, vx + r, tw_y], fill=(112, 112, 112))

    return img.filter(ImageFilter.GaussianBlur(4))


def build_harbor_depth(w: int, h: int) -> Image.Image:
    """Depth map of the Narrows: Manhattan seen across the bay from a headland.

    This is Cole's own Course of Empire vantage. Every canvas in the cycle looks
    across a bay from a raised wooded foreground, with a distant shore opposite
    and a recurring rock landmark. The New York harbour view from Staten Island
    is the same composition, which is why the cycle transplants onto it without
    forcing.

    WHITE = near, BLACK = far. Drawn rather than traced from a photograph, so
    there is no rights question on a commercial release. To use a real photo
    instead, depth-estimate it and point `control.image` at the result.
    """
    img = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(img)
    horizon = int(h * 0.46)

    # Water: recedes from near (bottom, bright) to the far shore (dark).
    for y in range(horizon, h):
        f = (y - horizon) / max(1, h - horizon)
        v = int(16 + 150 * f)
        d.line([(0, y), (w, y)], fill=(v, v, v))

    # Far shore: a low band, and the distant city skyline standing on it.
    d.rectangle([0, horizon - int(h * 0.02), w, horizon + int(h * 0.02)], fill=(44, 44, 44))
    # MANHATTAN, not a generic skyline. The previous version was nine anonymous
    # rectangles, so of course no Manhattan appeared: nothing in the depth map
    # or the prompt ever asked for it. Lower Manhattan as seen from the Narrows
    # is a dense cluster with one dominant tapering tower.
    for x0, wd, ht in [(0.470, 0.016, 0.090), (0.492, 0.020, 0.130),
                       (0.518, 0.014, 0.105), (0.537, 0.026, 0.175),
                       (0.569, 0.018, 0.120), (0.592, 0.015, 0.150),
                       (0.612, 0.022, 0.100), (0.640, 0.016, 0.135),
                       (0.662, 0.019, 0.085), (0.687, 0.014, 0.110)]:
        d.rectangle([int(w * x0), int(horizon - h * ht), int(w * (x0 + wd)), horizon],
                    fill=(54, 54, 54))
    # The dominant tapering tower, slightly nearer so it reads as the apex.
    tx, tw_ = int(w * 0.552), int(w * 0.011)
    d.polygon([(tx - tw_, int(horizon - h * 0.255)), (tx + tw_, int(horizon - h * 0.255)),
               (tx + int(tw_ * 1.7), horizon), (tx - int(tw_ * 1.7), horizon)],
              fill=(64, 64, 64))

    # THE STATUE OF LIBERTY. Geographically correct for this vantage: Liberty
    # Island sits between Staten Island and Lower Manhattan, so from a headland
    # on the Narrows it is genuinely in front of the skyline, and therefore
    # NEARER, i.e. brighter in depth than the city behind it.
    lx = int(w * 0.335)
    ly = int(horizon + h * 0.085)                     # standing in the water
    d.rectangle([lx - int(w * 0.026), ly - int(h * 0.070),
                 lx + int(w * 0.011), ly], fill=(92, 92, 92))          # pedestal
    d.polygon([(lx - int(w * 0.014), ly - int(h * 0.070)),
               (lx + int(w * 0.014), ly - int(h * 0.070)),
               (lx + int(w * 0.009), ly - int(h * 0.228)),
               (lx - int(w * 0.009), ly - int(h * 0.228))],
              fill=(104, 104, 104))                                     # figure
    d.polygon([(lx + int(w * 0.007), ly - int(h * 0.214)),
               (lx + int(w * 0.030), ly - int(h * 0.293)),
               (lx + int(w * 0.039), ly - int(h * 0.279)),
               (lx + int(w * 0.016), ly - int(h * 0.205))],
              fill=(110, 110, 110))                                     # raised arm
    d.ellipse([lx + int(w * 0.026), ly - int(h * 0.316),
               lx + int(w * 0.044), ly - int(h * 0.279)], fill=(128, 128, 128))  # torch

    # THE LANDMARK: a rock crag on the near headland, left. Cole's fixed
    # reference, the thing that outlasts the empire. Same role as the wedge.
    d.polygon([(int(w * 0.06), h), (int(w * 0.02), int(h * 0.60)),
               (int(w * 0.115), int(h * 0.40)), (int(w * 0.20), int(h * 0.56)),
               (int(w * 0.26), h)], fill=(244, 244, 244))
    # Near headland shelf the viewer stands on: the brightest, nearest plane.
    d.polygon([(0, h), (0, int(h * 0.80)), (int(w * 0.34), int(h * 0.90)),
               (int(w * 0.30), h)], fill=(250, 250, 250))
    # A second headland right, framing the Narrows.
    d.polygon([(w, h), (w, int(h * 0.66)), (int(w * 0.86), int(h * 0.78)),
               (int(w * 0.90), h)], fill=(228, 228, 228))

    return img.filter(ImageFilter.GaussianBlur(4))


# Skyline profiles per stage. The crag, the headlands and Liberty's island stay
# at IDENTICAL coordinates in every map, which is what makes them persist across
# the cycle; only the far shore changes. Stage 3 is deliberately MODERN: tall
# slender towers of very different heights, which is what separates a Manhattan
# silhouette from a classical one.
SKYLINES = {
    "savage":      [],
    "arcadian":    [(0.500, 0.012, 0.038), (0.545, 0.010, 0.030), (0.585, 0.013, 0.045)],
    "modern":      [(0.455, 0.016, 0.150), (0.478, 0.013, 0.235), (0.497, 0.020, 0.185),
                    (0.523, 0.012, 0.300), (0.541, 0.017, 0.205), (0.564, 0.011, 0.395),
                    (0.581, 0.019, 0.250), (0.606, 0.013, 0.330), (0.625, 0.016, 0.195),
                    (0.647, 0.012, 0.275), (0.665, 0.018, 0.160), (0.689, 0.011, 0.225)],
    # Five broad masses instead of twelve slender ones. Same overall silhouette
    # envelope, a quarter of the elements to keep consistent.
    "modern_haze": [(0.452, 0.048, 0.175), (0.508, 0.040, 0.300),
                    (0.556, 0.034, 0.395), (0.598, 0.046, 0.245),
                    (0.652, 0.052, 0.160)],
    "destruction_haze": [(0.452, 0.048, 0.150), (0.508, 0.040, 0.255),
                         (0.556, 0.034, 0.330), (0.598, 0.046, 0.130),
                         (0.652, 0.052, 0.075)],
    "destruction": [(0.455, 0.016, 0.130), (0.478, 0.013, 0.215), (0.497, 0.020, 0.100),
                    (0.523, 0.012, 0.280), (0.541, 0.017, 0.120), (0.564, 0.011, 0.340),
                    (0.581, 0.019, 0.150), (0.606, 0.013, 0.090), (0.625, 0.016, 0.175),
                    (0.665, 0.018, 0.070)],
    "desolation":  [(0.478, 0.013, 0.075), (0.523, 0.012, 0.110), (0.564, 0.011, 0.060),
                    (0.606, 0.013, 0.095), (0.665, 0.018, 0.045)],
}


def build_stage_depth(w: int, h: int, stage: str = "modern") -> Image.Image:
    """Harbour depth map: two FIXED land strips with unconstrained water between.

    Redesigned after v4. Earlier versions gave the water a grey depth ramp, and
    any grey value in that region reads to the model as a surface to stand
    things on: at a steep ramp the bay became a receding lawn, at a flat mid
    value it became a field. Both times the foreground ate the picture and the
    waterline wandered, which is where the artefacts came from.

    So the water is now BLACK, i.e. far, i.e. unconstrained: the model paints it
    freely. What the map asserts instead is a stable ARMATURE that is byte
    identical in all five stages:

        bottom band   Staten Island shore, full width, brightest (nearest)
        the crag      rising from it, the landmark that outlasts the empire
        black middle  the bay, unconstrained
        horizon band  Manhattan's strip of land, a constant mid value
        black above   sky

    Only the skyline standing ON Manhattan's strip changes per stage. That makes
    the horizon and both waterlines fixed for the whole cycle while the five
    stages play out on top of them.
    """
    img = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(img)
    horizon = int(h * 0.52)
    shore_y = int(h * 0.78)                 # top edge of the near shore

    # MANHATTAN'S STRIP: constant, full width, clearly brighter than the water.
    strip_h = int(h * 0.030)
    d.rectangle([0, horizon - strip_h, w, horizon + strip_h], fill=(84, 84, 84))

    # Per-stage skyline standing on that strip.
    hazy = stage.endswith("_haze")
    tower_v = 90 if hazy else 96          # closer to the strip's 84 = flatter, hazier
    for x0, wd, ht in SKYLINES.get(stage, []):
        d.rectangle([int(w * x0), int(horizon - strip_h - h * ht),
                     int(w * (x0 + wd)), horizon - strip_h + 2], fill=(tower_v,) * 3)

    # Liberty on her island, in the bay. Present from arcadian, broken by V.
    base = stage.replace("_haze", "")
    if base != "savage":
        lx, ly = int(w * 0.30), int(h * 0.635)
        top = 0.150 if base != "desolation" else 0.070
        d.ellipse([lx - int(w * 0.030), ly - int(h * 0.012),
                   lx + int(w * 0.030), ly + int(h * 0.016)], fill=(120, 120, 120))
        d.polygon([(lx - int(w * 0.010), ly),
                   (lx + int(w * 0.010), ly),
                   (lx + int(w * 0.006), ly - int(h * top)),
                   (lx - int(w * 0.006), ly - int(h * top))], fill=(134, 134, 134))
        if base != "desolation":
            d.polygon([(lx + int(w * 0.005), ly - int(h * 0.140)),
                       (lx + int(w * 0.022), ly - int(h * 0.196)),
                       (lx + int(w * 0.030), ly - int(h * 0.186)),
                       (lx + int(w * 0.013), ly - int(h * 0.132))], fill=(140, 140, 140))
            d.ellipse([lx + int(w * 0.020), ly - int(h * 0.214),
                       lx + int(w * 0.036), ly - int(h * 0.184)], fill=(158, 158, 158))

    # STATEN ISLAND: the near shore the viewer stands on. Full width, brightest,
    # with a soft depth roll so it reads as ground rather than a flat cut-out.
    for y in range(shore_y, h):
        f = (y - shore_y) / max(1, h - shore_y)
        v = int(196 + 58 * f)
        d.line([(0, y), (w, y)], fill=(v, v, v))
    # Its top edge, irregular so the waterline is not a ruler-straight line.
    d.polygon([(0, shore_y + 6), (int(w * 0.14), shore_y - int(h * 0.018)),
               (int(w * 0.33), shore_y + int(h * 0.010)),
               (int(w * 0.52), shore_y - int(h * 0.012)),
               (int(w * 0.74), shore_y + int(h * 0.014)),
               (w, shore_y - int(h * 0.008)), (w, shore_y + 30), (0, shore_y + 30)],
              fill=(200, 200, 200))

    # THE CRAG: the fixed reference, rising from the near shore.
    d.polygon([(int(w * 0.055), h), (int(w * 0.020), int(h * 0.735)),
               (int(w * 0.098), int(h * 0.585)), (int(w * 0.175), int(h * 0.730)),
               (int(w * 0.225), h)], fill=(246, 246, 246))

    return img.filter(ImageFilter.GaussianBlur(4))


# ---------------------------------------------------------------------------
# Delivery-aspect maps for the LED wall. These are NOT adaptations of the 16:9
# harbour map above; they are re-authored, because the delivery crops discard
# most of the frame the harbour armature lives in.
#
#   Screen A   render 896x1536, edge_crop 8, crop 506x1520 at x=187
#              -> only the CENTRAL 506 px column is delivered
#   Screen B/C render 1536x896, edge_crop 8, crop 1520x474 at y=0
#              -> only the TOP 474 px is delivered, i.e. y 8..482 of 896
#
# The harbour map puts the near shore at 0.78h and the crag from 0.585h down.
# All of that falls below the B/C cut. Everything here is authored against the
# region that survives, and the rest of the frame is paint-out that supports
# the visible sliver and is then thrown away.
# ---------------------------------------------------------------------------

# Where the delivered band ends, in render pixels, for the 16:5 screens. The
# crop takes y 0..474 of the edge-cropped frame, which is y 8..482 of the
# render. Author to 482 and the last few pixels are margin.
WIDE_BAND_PX = 482

# Broken stumps on the far shore for stage V. Left of centre so they never
# collide with the crag, which sits right in screen C. (x0, width, height) as
# fractions of the width and of the delivered band.
DESOLATION_STUMPS = [
    (0.200, 0.030, 0.081), (0.300, 0.024, 0.128), (0.400, 0.020, 0.069),
    (0.520, 0.026, 0.107), (0.640, 0.022, 0.056),
]

# Stump value against the far shore's 84. v9 used a 6-point separation on a
# 768-tall frame where the towers ran to 0.395h; here they are 27 to 62 px in
# an 896-tall frame, so 6 points is invisible to ControlNet and the map asserts
# nothing. 112 separates them clearly while staying far below the crag's 246,
# and five low masses is still inside v9's "fewer, larger" rule.
STUMP_VALUE = 112


def build_portal_depth(w: int, h: int) -> Image.Image:
    """Screen A, 1:3 portrait. The view BACK, from inside the empire.

    A 1:3 frame composes in horizontal bands, not vertical ones. Two earlier
    versions of this map got that backwards. The first put piers left and
    right, a lintel above and steps below, all at 232 to 250; after softening
    they merged into one continuous white surround and the map was literally a
    picture frame, which is the artifact `negative_prompt` has fought since the
    empire run. The second replaced them with a near column and a receding one,
    which subdivided a 506 px delivered band into four ~125 px vertical zones
    and read as stripes. The delivered column is 506 wide by 1520 tall: there
    is no room to divide it sideways.

    So the structure is the banked billboard's, which is already proven at this
    exact bucket: a heavy near mass capping the top, a heavy near mass holding
    the bottom, and one luminous band between them carrying the whole subject.

    And the subject in that band is the HEADLAND, not a city. This is the view
    back across the water from inside the empire, so the empire is present as
    the architecture you stand in rather than as a distant skyline. B and C
    look from the headland toward the city; A looks from the city toward the
    headland. Three screens, one continuous space, and the dense-city failure
    is designed out rather than tuned at: nothing distant is ever itemised.

    Four masses.
    """
    img = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(img)

    cap_y = int(h * 0.280)                 # underside of the portico above
    terrace_y = int(h * 0.780)             # the terrace you stand on
    strip_top, strip_bot = int(h * 0.580), int(h * 0.601)

    # THE CAP. Near, and it holds the top of a very tall frame shut. Gradient
    # runs nearer at the top: a single flat value over 28% of the frame paints
    # as a featureless slab.
    for y in range(cap_y):
        f = y / max(1, cap_y)
        v = int(248 - 22 * f)
        d.line([(0, y), (w, y)], fill=(v, v, v))

    # THE TERRACE. Nearest plane in frame, gradient running nearer toward the
    # bottom edge for the same reason.
    for y in range(terrace_y, h):
        f = (y - terrace_y) / max(1, h - terrace_y)
        v = int(238 + 16 * f)
        d.line([(0, y), (w, y)], fill=(v, v, v))

    # THE BAND between them stays black: sky above the horizon, water below.
    # Any grey in the water region reads as a surface to stand things on,
    # which is how a bay became a lawn in v4.

    # The far headland: the one grey the water rule permits, because it is
    # land. Same constant strip the 16:5 screens use, seen from the other side.
    d.rectangle([0, strip_top, w, strip_bot], fill=(84, 84, 84))

    # THE CRAG, centred, standing on that shore. Far and small here; the same
    # rock is near and large on B and C. One landmark seen from a rotating
    # viewpoint is Cole's own device and the only thing tying the three
    # screens together.
    cx, base = w // 2, int(h * 0.596)
    d.polygon([(cx - int(w * 0.082), base), (cx - int(w * 0.050), int(h * 0.545)),
               (cx, int(h * 0.508)), (cx + int(w * 0.046), int(h * 0.551)),
               (cx + int(w * 0.078), base)], fill=(104, 104, 104))

    return img.filter(ImageFilter.GaussianBlur(4))


def build_wide_depth(w: int, h: int, stage: str = "savage",
                     mirror: bool = False, band: int = WIDE_BAND_PX) -> Image.Image:
    """Screens B and C, 16:5. The same headland vantage, before and after.

    Everything meaningful is authored inside y 0..`band`; below that is
    paint-out. The waterline, the horizon and the shelf sit at identical
    fractions in both screens, so B and C read as one place at two moments.

    `mirror` flips the crag to the right-hand side for screen C. The stumps are
    NOT mirrored: they are authored left of centre precisely so that they clear
    the crag in either position.
    """
    img = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(img)

    def by(f: float) -> int:            # fraction of the delivered band
        return int(band * f)

    strip_top, strip_bot = by(0.415), by(0.485)
    shelf_y = by(0.892)

    # FAR SHORE: a constant low strip, full width, identical in both screens.
    d.rectangle([0, strip_top, w, strip_bot], fill=(84, 84, 84))

    # Stage V's broken stumps stand on that strip. Value close to the strip's
    # own, which is v9's lesson: flatter contrast reads as haze and gives the
    # chain less to keep consistent.
    if stage == "desolation":
        for x0, wd, ht in DESOLATION_STUMPS:
            d.rectangle([int(w * x0), strip_top - by(ht),
                         int(w * (x0 + wd)), strip_top + 2], fill=(STUMP_VALUE,) * 3)

    # THE BAY stays black between the strip and the shelf. Unconstrained.

    # NEAR SHELF: the ground the viewer stands on. Only its top ~50 px are
    # delivered, as a dark repoussoir band along the bottom edge; the rest runs
    # off the cut and exists so the model paints something coherent above it.
    for y in range(shelf_y, h):
        f = (y - shelf_y) / max(1, h - shelf_y)
        v = int(196 + 54 * min(1.0, f * 3.0))
        d.line([(0, y), (w, y)], fill=(v, v, v))
    # Irregular top edge, so the near waterline is not a ruler-straight line.
    d.polygon([(0, shelf_y + 4), (int(w * 0.19), shelf_y - by(0.022)),
               (int(w * 0.41), shelf_y + by(0.012)),
               (int(w * 0.63), shelf_y - by(0.016)),
               (int(w * 0.84), shelf_y + by(0.018)),
               (w, shelf_y - by(0.010)), (w, shelf_y + 24), (0, shelf_y + 24)],
              fill=(200, 200, 200))

    # THE CRAG: near, brightest, and it breaks the horizon. That is what makes
    # it read as monumental rather than as a rock in the water, and it is the
    # element the 1:3 screen shows far away through the portico.
    crag = [(0.013, 1.080), (0.020, 0.620), (0.062, 0.340), (0.098, 0.228),
            (0.140, 0.400), (0.196, 0.600), (0.215, 1.080)]
    pts = [(int(w * (1 - fx)) if mirror else int(w * fx), by(fy)) for fx, fy in crag]
    d.polygon(pts, fill=(246, 246, 246))

    return img.filter(ImageFilter.GaussianBlur(4))


def soften(img: Image.Image, radius: int) -> Image.Image:
    """Blur the map hard, and break the flat fills with a faint gradient.

    At blur 4 the map is a vector diagram, and ControlNet traced it: crisp
    slab edges printed straight through as flat marble planes. Heavier blur
    turns hard boundaries into ramps the model can interpret as form rather
    than copy as geometry, and a slight vertical gradient stops each mass
    reading as one constant depth.
    """
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    h = a.shape[0]
    ramp = np.linspace(-8, 8, h, dtype=np.float32)[:, None, None]
    a = np.clip(a + ramp, 0, 255).astype(np.uint8)
    return Image.fromarray(a).filter(ImageFilter.GaussianBlur(radius))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("outputs/_anchors/times-square.png"))
    ap.add_argument("--depth", action="store_true",
                    help="emit a ControlNet depth map instead of a tonal sketch")
    ap.add_argument("--stage", choices=list(SKYLINES), default=None,
                    help="emit a per-stage harbour depth map")
    ap.add_argument("--scene", choices=["bowtie", "harbor", "portal", "wide"], default="bowtie",
                    help="bowtie = Times Square; harbor = the Narrows from a headland; "
                         "portal = LED screen A (1:3); wide = LED screens B/C (16:5)")
    ap.add_argument("--wide-stage", choices=["savage", "desolation"], default="savage",
                    help="--scene wide only: savage (screen B) or desolation (screen C)")
    ap.add_argument("--mirror", action="store_true",
                    help="--scene wide only: put the crag right instead of left (screen C)")
    ap.add_argument("--band", type=int, default=WIDE_BAND_PX,
                    help="--scene wide only: last render row that survives the 16:5 crop")
    ap.add_argument("--soften", type=int, default=0,
                    help="extra blur radius; use ~14 to stop ControlNet tracing edges")
    ap.add_argument("--width", type=int, default=1344)
    ap.add_argument("--height", type=int, default=768)
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.stage:
        out = build_stage_depth(args.width, args.height, args.stage)
        if args.soften:
            out = soften(out, args.soften)
        out.save(args.out)
        print(f"{args.width}x{args.height} {args.stage} depth map -> {args.out}")
        return 0
    if args.scene == "portal":
        out = build_portal_depth(args.width, args.height)
    elif args.scene == "wide":
        out = build_wide_depth(args.width, args.height, args.wide_stage,
                               mirror=args.mirror, band=args.band)
    else:
        if args.scene == "harbor":
            if not args.depth:
                raise SystemExit("--scene harbor is depth-only; pass --depth")
            maker = build_harbor_depth
        else:
            maker = build_depth if args.depth else build
        out = maker(args.width, args.height)
    if args.soften:
        out = soften(out, args.soften)
    out.save(args.out)
    if args.scene in ("portal", "wide"):
        kind = f"{args.scene} depth map"
    else:
        kind = "depth map" if args.depth else "massing sketch"
    soft = f", softened r={args.soften}" if args.soften else ""
    print(f"{args.width}x{args.height} {kind}{soft} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
