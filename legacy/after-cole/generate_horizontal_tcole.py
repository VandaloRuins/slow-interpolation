"""
generate_horizontal_tcole.py -- Horizontal video pipeline using Thomas Cole LoRA.

Swaps the Casa del Suono fresco LoRA for our locally trained Thomas Cole SDXL LoRA
and uses Cole's visual vocabulary (Hudson River School, romantic landscape, ruins in
nature). Everything else (SDXL Lightning 4-step, RIFE 64x, linear timestep, temporal
smoothing, ~60s loop) is inherited from generate_horizontal.py via monkey-patching.

Usage:
    python generate_horizontal_tcole.py --subject tcole_ruins
    python generate_horizontal_tcole.py --subject tcole_ruins --lora-scale 0.8 --tag v2
    python generate_horizontal_tcole.py --list
"""

import sys
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).parent

# ---------------------------------------------------------------------------
# Tom Cole LoRA paths + style
# ---------------------------------------------------------------------------
TCOLE_LORA_DIR = BASE_DIR / "visuals" / "lora-datasets" / "thomas-cole" / "checkpoints"
TCOLE_LORA_CANDIDATES = [
    TCOLE_LORA_DIR / "Thomas_Cole_epoch_10.safetensors",  # strong style (default)
    TCOLE_LORA_DIR / "Thomas_Cole_epoch_1.safetensors",   # light style (fallback)
]

# LoRA trigger word baked into the style prefix. The Thomas Cole LoRA was trained
# with "tcole, ..." as the caption format, so including "tcole" here activates it.
TCOLE_STYLE_PREFIX = "tcole, romantic landscape oil painting, Hudson River School style, "
TCOLE_STYLE_SUFFIX = ""

# LoRA scale -- tcole trained from scratch, so 0.7-0.8 gives full style without
# breaking SDXL Lightning's 4-step behavior (which was fused first at scale 1.0).
TCOLE_LORA_SCALE_DEFAULT = 0.75

# ---------------------------------------------------------------------------
# Thomas Cole subjects (A / B / C / A return pattern, lighting variations)
# ---------------------------------------------------------------------------
TCOLE_SUBJECTS = {
    "tcole_ruins": {
        "name": "tcole_ruins",
        "prompts": [
            {
                "label": "A: Ruins golden hour",
                "prompt": (
                    "the crumbling ruins of an ancient classical temple standing on a rocky promontory "
                    "overlooking a vast wilderness valley, broken marble columns entwined with climbing vines, "
                    "fallen stone blocks half-buried in wild grass and flowering weeds, a gnarled oak tree "
                    "framing the left foreground, a winding river catching light in the valley far below, "
                    "distant mountains shrouded in soft mist, warm golden sunset light on the weathered stone, "
                    "dramatic cumulus clouds in a luminous amber sky, oil painting, romantic wilderness landscape"
                ),
                "denoising": 0.470,
            },
            {
                "label": "B: Ruins stormy afternoon",
                "prompt": (
                    "the crumbling ruins of an ancient classical temple standing on a rocky promontory "
                    "overlooking a vast wilderness valley, broken marble columns entwined with climbing vines, "
                    "fallen stone blocks half-buried in wild grass and flowering weeds, a gnarled oak tree "
                    "framing the left foreground, a winding river catching light in the valley far below, "
                    "distant mountains shrouded in dark storm clouds, dramatic shafts of sunlight breaking through "
                    "heavy grey clouds onto the ruins, deep shadows in the valley, stormy sublime atmosphere, "
                    "oil painting, romantic wilderness landscape"
                ),
                "denoising": 0.480,
            },
            {
                "label": "C: Ruins misty dawn",
                "prompt": (
                    "the crumbling ruins of an ancient classical temple standing on a rocky promontory "
                    "overlooking a vast wilderness valley, broken marble columns entwined with climbing vines, "
                    "fallen stone blocks half-buried in wild grass and flowering weeds, a gnarled oak tree "
                    "framing the left foreground, a winding river catching light in the valley far below, "
                    "distant mountains dissolving into pale mist, cool pink-grey dawn light, dense fog "
                    "rising from the valley floor veiling the lower columns, soft luminous sky, "
                    "oil painting, romantic wilderness landscape, luminism"
                ),
                "denoising": 0.490,
            },
            {
                "label": "A (return): Ruins golden hour",
                "prompt": (
                    "the crumbling ruins of an ancient classical temple standing on a rocky promontory "
                    "overlooking a vast wilderness valley, broken marble columns entwined with climbing vines, "
                    "fallen stone blocks half-buried in wild grass and flowering weeds, a gnarled oak tree "
                    "framing the left foreground, a winding river catching light in the valley far below, "
                    "distant mountains shrouded in soft mist, warm golden sunset light on the weathered stone, "
                    "dramatic cumulus clouds in a luminous amber sky, oil painting, romantic wilderness landscape"
                ),
                "denoising": 0.470,
            },
        ],
    },
    "tcole_valley": {
        "name": "tcole_valley",
        "prompts": [
            {
                "label": "A: Valley amber",
                "prompt": (
                    "a sweeping panoramic view across a vast green valley of lush emerald grasslands, "
                    "open meadow filling the entire foreground and middle ground, "
                    "tiny ancient Roman aqueduct ruins with crumbling brick arches far away on the distant horizon, "
                    "hazy blue mountains behind, warm amber afternoon light, oil painting"
                ),
                "denoising": 0.470,
            },
            {
                "label": "B: Valley golden",
                "prompt": (
                    "a sweeping panoramic view across a vast green valley of lush emerald grasslands, "
                    "open meadow filling the entire foreground and middle ground, "
                    "tiny ancient Roman aqueduct ruins with crumbling brick arches far away on the distant horizon, "
                    "hazy blue mountains behind, warm golden hour light, oil painting"
                ),
                "denoising": 0.475,
            },
            {
                "label": "C: Valley morning",
                "prompt": (
                    "a sweeping panoramic view across a vast green valley of lush emerald grasslands, "
                    "open meadow filling the entire foreground and middle ground, "
                    "tiny ancient Roman aqueduct ruins with crumbling brick arches far away on the distant horizon, "
                    "pale misty mountains behind, soft morning light with mist, oil painting, luminism"
                ),
                "denoising": 0.480,
            },
            {
                "label": "A (return)",
                "prompt": (
                    "a sweeping panoramic view across a vast green valley of lush emerald grasslands, "
                    "open meadow filling the entire foreground and middle ground, "
                    "tiny ancient Roman aqueduct ruins with crumbling brick arches far away on the distant horizon, "
                    "hazy blue mountains behind, warm amber afternoon light, oil painting"
                ),
                "denoising": 0.470,
            },
        ],
    },
    "tcole_cloudship": {
        "name": "tcole_cloudship",
        "prompts": [
            {
                "label": "A: Cloud ship amber",
                "prompt": (
                    "a panoramic sky scene, a golden galleon with billowing sails flying high in the air "
                    "above thick white clouds, the ship resting on the clouds like an ocean, "
                    "green pastoral valley with tiny hills and river visible far below through gaps in the clouds, "
                    "warm amber sunset light, oil painting, sublime fantasy"
                ),
                "denoising": 0.470,
            },
            {
                "label": "B: Cloud ship golden",
                "prompt": (
                    "a panoramic sky scene, a golden galleon with billowing sails flying high in the air "
                    "above thick white clouds, the ship resting on the clouds like an ocean, "
                    "green pastoral valley with tiny hills and river visible far below through gaps in the clouds, "
                    "warm golden light breaking through, oil painting, sublime fantasy"
                ),
                "denoising": 0.475,
            },
            {
                "label": "C: Cloud ship dawn",
                "prompt": (
                    "a panoramic sky scene, a golden galleon with billowing sails flying high in the air "
                    "above thick pink and white clouds, the ship resting on the clouds like an ocean, "
                    "green pastoral valley with tiny hills and river visible far below through gaps in the clouds, "
                    "soft rose dawn light, oil painting, sublime fantasy, luminism"
                ),
                "denoising": 0.480,
            },
            {
                "label": "A (return)",
                "prompt": (
                    "a panoramic sky scene, a golden galleon with billowing sails flying high in the air "
                    "above thick white clouds, the ship resting on the clouds like an ocean, "
                    "green pastoral valley with tiny hills and river visible far below through gaps in the clouds, "
                    "warm amber sunset light, oil painting, sublime fantasy"
                ),
                "denoising": 0.470,
            },
        ],
    },
    "tcole_horses": {
        "name": "tcole_horses",
        "prompts": [
            {
                "label": "A: Jungle river amber",
                "prompt": (
                    "a wide panoramic view of a tropical river winding through dense jungle, "
                    "a herd of wild horses drinking and wading in the shallows in the middle distance, "
                    "lush green canopy and palm trees lining both banks, "
                    "warm amber afternoon light filtering through the trees, oil painting"
                ),
                "denoising": 0.470,
            },
            {
                "label": "B: Jungle river golden",
                "prompt": (
                    "a wide panoramic view of a tropical river winding through dense jungle, "
                    "a herd of wild horses drinking and wading in the shallows in the middle distance, "
                    "lush green canopy and palm trees lining both banks, "
                    "warm golden hour light reflecting on the river surface, oil painting"
                ),
                "denoising": 0.475,
            },
            {
                "label": "C: Jungle river morning",
                "prompt": (
                    "a wide panoramic view of a tropical river winding through dense jungle, "
                    "a herd of wild horses drinking and wading in the shallows in the middle distance, "
                    "lush green canopy and palm trees lining both banks, "
                    "soft morning light with mist rising from the river, oil painting, luminism"
                ),
                "denoising": 0.480,
            },
            {
                "label": "A (return)",
                "prompt": (
                    "a wide panoramic view of a tropical river winding through dense jungle, "
                    "a herd of wild horses drinking and wading in the shallows in the middle distance, "
                    "lush green canopy and palm trees lining both banks, "
                    "warm amber afternoon light filtering through the trees, oil painting"
                ),
                "denoising": 0.470,
            },
        ],
    },
    "tcole_siege": {
        "name": "tcole_siege",
        "prompts": [
            {
                "label": "A: Harbour fire amber",
                "prompt": (
                    "a wide panoramic view of a Roman harbour under attack, "
                    "wooden warships burning with tall orange flames on dark water, "
                    "thick black smoke choking a stormy sky, stone quays and a lighthouse "
                    "in the middle distance, distant colonnaded buildings on fire, "
                    "oil painting, romantic sublime landscape, dramatic destruction"
                ),
                "denoising": 0.470,
            },
            {
                "label": "B: Harbour fire red",
                "prompt": (
                    "a wide panoramic view of a Roman harbour under attack, "
                    "wooden warships burning with tall orange flames on dark water, "
                    "thick black smoke billowing across a blood-red sky, stone quays "
                    "and a lighthouse in the middle distance, distant colonnaded buildings "
                    "glowing with fire, oil painting, romantic sublime landscape, dramatic destruction"
                ),
                "denoising": 0.475,
            },
            {
                "label": "C: Harbour fire dark",
                "prompt": (
                    "a wide panoramic view of a Roman harbour under attack, "
                    "wooden warships burning with tall orange flames on dark choppy water, "
                    "dense black smoke obscuring a dark grey sky, stone quays and a lighthouse "
                    "in the middle distance, distant colonnaded buildings smouldering, "
                    "oil painting, romantic sublime landscape, dramatic destruction"
                ),
                "denoising": 0.480,
            },
            {
                "label": "A (return)",
                "prompt": (
                    "a wide panoramic view of a Roman harbour under attack, "
                    "wooden warships burning with tall orange flames on dark water, "
                    "thick black smoke choking a stormy sky, stone quays and a lighthouse "
                    "in the middle distance, distant colonnaded buildings on fire, "
                    "oil painting, romantic sublime landscape, dramatic destruction"
                ),
                "denoising": 0.470,
            },
        ],
    },
}


def main():
    # Parse our own args FIRST so we can strip --lora-scale before delegating
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--lora-scale", type=float, default=TCOLE_LORA_SCALE_DEFAULT,
                        help=f"Thomas Cole LoRA scale (default {TCOLE_LORA_SCALE_DEFAULT})")
    parser.add_argument("--epoch", type=int, default=10, choices=[1, 10],
                        help="Which Thomas Cole epoch to use (1=light, 10=strong)")
    our_args, passthrough_args = parser.parse_known_args()

    # Select checkpoint by epoch
    if our_args.epoch == 1:
        lora_path = TCOLE_LORA_DIR / "Thomas_Cole_epoch_1.safetensors"
    else:
        lora_path = TCOLE_LORA_DIR / "Thomas_Cole_epoch_10.safetensors"

    if not lora_path.exists():
        print(f"ERROR: LoRA checkpoint not found: {lora_path}")
        sys.exit(1)

    # Monkey-patch generate_videos BEFORE generate_horizontal imports from it
    import generate_videos as gv
    gv.LORA_CANDIDATES = [lora_path]
    gv.LORA_SCALE = our_args.lora_scale
    gv.STYLE_PREFIX = TCOLE_STYLE_PREFIX
    gv.STYLE_SUFFIX = TCOLE_STYLE_SUFFIX

    print(f"[tcole] LoRA:   {lora_path.name}")
    print(f"[tcole] Scale:  {our_args.lora_scale}")
    print(f"[tcole] Prefix: {TCOLE_STYLE_PREFIX!r}")

    # Now import generate_horizontal and inject our subjects
    import generate_horizontal as gh
    gh.SUBJECTS.update(TCOLE_SUBJECTS)

    # Rebuild sys.argv for generate_horizontal.main() to consume
    sys.argv = [sys.argv[0]] + passthrough_args

    gh.main()


if __name__ == "__main__":
    main()
