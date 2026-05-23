"""
generate_horizontal.py -- Horizontal (landscape) fork of generate_subject_test.py.
Only difference: resolution swapped to 1344x768 (16:9) and frame counts for ~60s output.

Usage:
    python generate_horizontal.py --subject E14
    python generate_horizontal.py --subject E14 --tag v2
"""

import sys
import os
os.environ['PYTHONUNBUFFERED'] = '1'

from pathlib import Path
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

# Import the crown script's main generation logic by reusing generate_crown_video
# but with different prompts

SUBJECTS = {
    "throne": {
        "name": "E12_throne",
        "prompts": [
            {
                "label": "A: Throne hall wide",
                "prompt": "a vast stone throne room with a solitary king sunk deep into a gilded throne, his hand pressed to his ear, amber torchlight on vaulted stone ceiling, empty hall stretching into darkness",
                "denoising": 0.470,
            },
            {
                "label": "B: Ear closeup",
                "prompt": "extreme closeup of a king's ear pressed against cold stone wall, gold earring catching candlelight, aged skin and grey hair, deep shadows around the ear canal",
                "denoising": 0.480,
            },
            {
                "label": "C: Throne from behind",
                "prompt": "a gilded throne seen from behind, the back of a crowned king's head visible above the high seat, stone columns receding into a dark hall, warm amber light from a distant window",
                "denoising": 0.500,
            },
            {
                "label": "A (return): Throne hall wide",
                "prompt": "a vast stone throne room with a solitary king sunk deep into a gilded throne, his hand pressed to his ear, amber torchlight on vaulted stone ceiling, empty hall stretching into darkness",
                "denoising": 0.470,
            },
        ],
    },
    "city": {
        "name": "E28_city",
        "prompts": [
            {
                "label": "A: City rooftops",
                "prompt": "a medieval city seen from above at dusk, terracotta rooftops and bell towers, narrow streets with torchlight processions, warm amber sky fading to deep blue, stone walls and wooden shutters",
                "denoising": 0.470,
            },
            {
                "label": "B: Street procession",
                "prompt": "a torchlit street procession through a narrow medieval alley, hooded figures carrying lanterns, warm firelight on stone walls, deep shadows between buildings, cobblestone street",
                "denoising": 0.480,
            },
            {
                "label": "C: Woman at window",
                "prompt": "a woman singing at an open stone window at night, candlelight illuminating her face from below, dark city rooftops visible behind her, warm golden light on aged plaster wall",
                "denoising": 0.500,
            },
            {
                "label": "A (return): City pre-dawn",
                "prompt": "a medieval city seen from above at dawn, terracotta rooftops and bell towers, first light touching the highest spires, warm amber glow on stone facades, quiet empty streets below",
                "denoising": 0.470,
            },
        ],
    },
    # --- 15 curated session subjects ---
    "E05": {
        "name": "E05_banquet",
        "prompts": [
            {"label": "A: Banquet amber", "prompt": "a lavish banquet table in a palace dining hall, food and wine untouched on silver platters, goblets gleaming, tall candelabra lit along the table, frescoed ceiling with painted garlands above, empty carved wooden chairs on both sides, warm amber candlelight", "denoising": 0.470},
            {"label": "B: Banquet candlelit", "prompt": "a lavish banquet table in a palace dining hall, food and wine untouched on silver platters, goblets gleaming, tall candelabra lit along the table, frescoed ceiling with painted garlands above, empty carved wooden chairs on both sides, warm flickering candlelight", "denoising": 0.475},
            {"label": "C: Banquet dusk", "prompt": "a lavish banquet table in a palace dining hall, food and wine untouched on silver platters, goblets gleaming, tall candelabra lit along the table, frescoed ceiling with painted garlands above, empty carved wooden chairs on both sides, fading dusk light from tall windows", "denoising": 0.480},
            {"label": "A (return)", "prompt": "a lavish banquet table in a palace dining hall, food and wine untouched on silver platters, goblets gleaming, tall candelabra lit along the table, frescoed ceiling with painted garlands above, empty carved wooden chairs on both sides, warm amber candlelight", "denoising": 0.470},
        ],
    },
    "E07": {
        "name": "E07_staircase",
        "prompts": [
            {"label": "A: Staircase amber", "prompt": "a grand spiral staircase in a palace tower, stone steps worn smooth by centuries, iron railing with scrollwork, frescoed walls curving upward showing painted clouds and sky, dim amber torchlight from iron brackets", "denoising": 0.470},
            {"label": "B: Staircase candlelit", "prompt": "a grand spiral staircase in a palace tower, stone steps worn smooth by centuries, iron railing with scrollwork, frescoed walls curving upward showing painted clouds and sky, warm candlelight from a carried taper", "denoising": 0.475},
            {"label": "C: Staircase dim", "prompt": "a grand spiral staircase in a palace tower, stone steps worn smooth by centuries, iron railing with scrollwork, frescoed walls curving upward showing painted clouds and sky, fading dim light from a high window", "denoising": 0.480},
            {"label": "A (return)", "prompt": "a grand spiral staircase in a palace tower, stone steps worn smooth by centuries, iron railing with scrollwork, frescoed walls curving upward showing painted clouds and sky, dim amber torchlight from iron brackets", "denoising": 0.470},
        ],
    },
    "E09": {
        "name": "E09_corridor",
        "prompts": [
            {"label": "A: Corridor amber", "prompt": "a long palace corridor with arched ceiling and stone pilasters on both sides, frescoed panels between the pilasters showing hunting scenes, marble floor reflecting amber torchlight, the corridor receding into warm golden haze at the far end", "denoising": 0.470},
            {"label": "B: Corridor bright", "prompt": "a long palace corridor with arched ceiling and stone pilasters on both sides, frescoed panels between the pilasters showing hunting scenes, marble floor reflecting bright daylight from tall windows on one side, the corridor receding into white light", "denoising": 0.475},
            {"label": "C: Corridor dusk", "prompt": "a long palace corridor with arched ceiling and stone pilasters on both sides, frescoed panels between the pilasters showing hunting scenes, marble floor in dim dusk light, the corridor receding into deep shadow at the far end", "denoising": 0.480},
            {"label": "A (return)", "prompt": "a long palace corridor with arched ceiling and stone pilasters on both sides, frescoed panels between the pilasters showing hunting scenes, marble floor reflecting amber torchlight, the corridor receding into warm golden haze at the far end", "denoising": 0.470},
        ],
    },
    "E11": {
        "name": "E11_hall",
        "prompts": [
            {"label": "A: Hall amber", "prompt": "a palace reception hall receding into depth, iron torches on stone walls with carved pilasters, frescoed vaulted ceiling with painted figures, marble floor reflecting amber light, tapestries between arched windows, the far end dissolving into golden haze", "denoising": 0.470},
            {"label": "B: Hall brighter", "prompt": "a palace reception hall receding into depth, iron torches on stone walls with carved pilasters, frescoed vaulted ceiling with painted figures, marble floor reflecting golden light, tapestries between arched windows, warm light filling from the far end", "denoising": 0.475},
            {"label": "C: Hall dimmer", "prompt": "a palace reception hall receding into depth, iron torches burning low on stone walls with carved pilasters, frescoed vaulted ceiling with painted figures, marble floor in dim amber light, tapestries between arched windows, deep shadows gathering", "denoising": 0.480},
            {"label": "A (return)", "prompt": "a palace reception hall receding into depth, iron torches on stone walls with carved pilasters, frescoed vaulted ceiling with painted figures, marble floor reflecting amber light, tapestries between arched windows, the far end dissolving into golden haze", "denoising": 0.470},
        ],
    },
    "E14": {
        "name": "E14_lake",
        "prompts": [
            {"label": "A: Lake dawn", "prompt": "a still lake at dawn surrounded by cypress trees and a distant hilltop village, perfectly calm water holding a mirror image of the landscape, reeds at the shore, warm amber light on the horizon, mist rising from the glassy surface", "denoising": 0.470},
            {"label": "B: Lake golden", "prompt": "a still lake at dawn surrounded by cypress trees and a distant hilltop village, perfectly calm water holding a mirror image of the landscape, reeds at the shore, warm golden light spreading across the water, thin mist dissolving", "denoising": 0.475},
            {"label": "C: Lake pale", "prompt": "a still lake at dawn surrounded by cypress trees and a distant hilltop village, perfectly calm water holding a mirror image of the landscape, reeds at the shore, pale grey-pink light on the horizon, dense mist blanketing the surface", "denoising": 0.480},
            {"label": "A (return)", "prompt": "a still lake at dawn surrounded by cypress trees and a distant hilltop village, perfectly calm water holding a mirror image of the landscape, reeds at the shore, warm amber light on the horizon, mist rising from the glassy surface", "denoising": 0.470},
        ],
    },
    "E15": {
        "name": "E15_apse",
        "prompts": [
            {"label": "A: Apse warm", "prompt": "a palace corridor ending in a large semicircular apse, ribbed stone vault above, frescoed walls with faded painted figures, stone floor worn smooth, iron candelabra along the walls, the curved apse wall smooth and warm in amber torchlight", "denoising": 0.470},
            {"label": "B: Apse candlelit", "prompt": "a palace corridor ending in a large semicircular apse, ribbed stone vault above, frescoed walls with faded painted figures, stone floor worn smooth, iron candelabra along the walls, the curved apse wall in warm candlelight", "denoising": 0.475},
            {"label": "C: Apse dim", "prompt": "a palace corridor ending in a large semicircular apse, ribbed stone vault above, frescoed walls with faded painted figures, stone floor worn smooth, iron candelabra along the walls, the curved apse wall in deep shadow with fading light", "denoising": 0.480},
            {"label": "A (return)", "prompt": "a palace corridor ending in a large semicircular apse, ribbed stone vault above, frescoed walls with faded painted figures, stone floor worn smooth, iron candelabra along the walls, the curved apse wall smooth and warm in amber torchlight", "denoising": 0.470},
        ],
    },
    "E16": {
        "name": "E16_bed",
        "prompts": [
            {"label": "A: Bed candlelit", "prompt": "a canopied bed in a palace chamber, covers disturbed but empty, a candle burned to its socket on a carved bedside table, stone walls hung with tapestries, a tall shuttered window, heavy wooden furniture, warm amber light filling the room", "denoising": 0.470},
            {"label": "B: Bed flickering", "prompt": "a canopied bed in a palace chamber, covers disturbed but empty, a candle burned to its socket on a carved bedside table, stone walls hung with tapestries, a tall shuttered window, heavy wooden furniture, flickering warm light casting moving shadows", "denoising": 0.475},
            {"label": "C: Bed near dark", "prompt": "a canopied bed in a palace chamber, covers disturbed but empty, a candle burned to its socket on a carved bedside table, stone walls hung with tapestries, a tall shuttered window, heavy wooden furniture, fading last light before darkness", "denoising": 0.480},
            {"label": "A (return)", "prompt": "a canopied bed in a palace chamber, covers disturbed but empty, a candle burned to its socket on a carved bedside table, stone walls hung with tapestries, a tall shuttered window, heavy wooden furniture, warm amber light filling the room", "denoising": 0.470},
        ],
    },
    "E17": {
        "name": "E17_fresco",
        "prompts": [
            {"label": "A: Fresco warm", "prompt": "a palace wall covered in frescoed garden scenes, painted birds perched on flowering branches, a glimpse of a painted fountain, the aged plaster cracked and warm, the real room dim around it with stone floor and carved cornice, amber light on the painted surface", "denoising": 0.470},
            {"label": "B: Fresco bright", "prompt": "a palace wall covered in frescoed garden scenes, painted birds perched on flowering branches, a glimpse of a painted fountain, the aged plaster cracked and warm, the real room dim around it with stone floor and carved cornice, bright daylight revealing every brushstroke", "denoising": 0.475},
            {"label": "C: Fresco dusk", "prompt": "a palace wall covered in frescoed garden scenes, painted birds perched on flowering branches, a glimpse of a painted fountain, the aged plaster cracked and warm, the real room dim around it with stone floor and carved cornice, fading dusk light softening the colours", "denoising": 0.480},
            {"label": "A (return)", "prompt": "a palace wall covered in frescoed garden scenes, painted birds perched on flowering branches, a glimpse of a painted fountain, the aged plaster cracked and warm, the real room dim around it with stone floor and carved cornice, amber light on the painted surface", "denoising": 0.470},
        ],
    },
    "E18": {
        "name": "E18_aerial",
        "prompts": [
            {"label": "A: Palace aerial warm", "prompt": "an aerial view of a palace complex, courtyards and wings around a central axis, terracotta rooftops with clay chimney pots, stone walls with arched loggias, cypress gardens between wings, a bell tower rising at one corner, warm amber afternoon light casting long shadows", "denoising": 0.470},
            {"label": "B: Palace aerial golden", "prompt": "an aerial view of a palace complex, courtyards and wings around a central axis, terracotta rooftops with clay chimney pots, stone walls with arched loggias, cypress gardens between wings, a bell tower rising at one corner, warm golden hour light, deep shadows across courtyards", "denoising": 0.475},
            {"label": "C: Palace aerial morning", "prompt": "an aerial view of a palace complex, courtyards and wings around a central axis, terracotta rooftops with clay chimney pots, stone walls with arched loggias, cypress gardens between wings, a bell tower rising at one corner, soft morning light with thin haze over the rooftops", "denoising": 0.480},
            {"label": "A (return)", "prompt": "an aerial view of a palace complex, courtyards and wings around a central axis, terracotta rooftops with clay chimney pots, stone walls with arched loggias, cypress gardens between wings, a bell tower rising at one corner, warm amber afternoon light casting long shadows", "denoising": 0.470},
        ],
    },
    "E19": {
        "name": "E19_bust",
        "prompts": [
            {"label": "A: Bust amber", "prompt": "a carved stone head and shoulders bust of a king on a pedestal in a palace niche, the face weathered and ancient, surrounded by frescoed panels showing palace corridors, carved stone pilasters on each side, vaulted ceiling above, warm amber torchlight", "denoising": 0.470},
            {"label": "B: Bust candlelit", "prompt": "a carved stone head and shoulders bust of a king on a pedestal in a palace niche, the face weathered and ancient, surrounded by frescoed panels showing palace corridors, carved stone pilasters on each side, vaulted ceiling above, warm candlelight", "denoising": 0.475},
            {"label": "C: Bust dim", "prompt": "a carved stone head and shoulders bust of a king on a pedestal in a palace niche, the face weathered and ancient, surrounded by frescoed panels showing palace corridors, carved stone pilasters on each side, vaulted ceiling above, fading dim light", "denoising": 0.480},
            {"label": "A (return)", "prompt": "a carved stone head and shoulders bust of a king on a pedestal in a palace niche, the face weathered and ancient, surrounded by frescoed panels showing palace corridors, carved stone pilasters on each side, vaulted ceiling above, warm amber torchlight", "denoising": 0.470},
        ],
    },
    "E20": {
        "name": "E20_portrait",
        "prompts": [
            {"label": "A: Portrait amber", "prompt": "a large oil portrait of a bearded king in a heavy gilded frame dominating a palace gallery wall, the king wearing a dark robe and crown, frescoed ceiling above, polished marble floor reflecting the frame, warm amber light from tall windows on the left", "denoising": 0.470},
            {"label": "B: Portrait candlelit", "prompt": "a large oil portrait of a bearded king in a heavy gilded frame dominating a palace gallery wall, the king wearing a dark robe and crown, frescoed ceiling above, polished marble floor reflecting the frame, warm candlelight from wall sconces", "denoising": 0.475},
            {"label": "C: Portrait dusk", "prompt": "a large oil portrait of a bearded king in a heavy gilded frame dominating a palace gallery wall, the king wearing a dark robe and crown, frescoed ceiling above, polished marble floor reflecting the frame, fading dusk light from tall windows", "denoising": 0.480},
            {"label": "A (return)", "prompt": "a large oil portrait of a bearded king in a heavy gilded frame dominating a palace gallery wall, the king wearing a dark robe and crown, frescoed ceiling above, polished marble floor reflecting the frame, warm amber light from tall windows on the left", "denoising": 0.470},
        ],
    },
    "E21": {
        "name": "E21_hearth",
        "prompts": [
            {"label": "A: Hearth amber", "prompt": "a wide view of a palace great hall with a massive stone hearth at centre, carved chimney breast with heraldic beasts rising to the frescoed ceiling, heavy tapestries hanging on both walls, wooden benches and iron candelabra flanking the hearth, a steady fire burning inside, warm amber firelight filling the vaulted space", "denoising": 0.470},
            {"label": "B: Hearth candlelit", "prompt": "a wide view of a palace great hall with a massive stone hearth at centre, carved chimney breast with heraldic beasts rising to the frescoed ceiling, heavy tapestries hanging on both walls, wooden benches and iron candelabra flanking the hearth, a steady fire burning inside, warm candlelight mixing with the fire glow", "denoising": 0.475},
            {"label": "C: Hearth embers", "prompt": "a wide view of a palace great hall with a massive stone hearth at centre, carved chimney breast with heraldic beasts rising to the frescoed ceiling, heavy tapestries hanging on both walls, wooden benches and iron candelabra flanking the hearth, a fire burning low to embers, deep red ember light in the dim vaulted hall", "denoising": 0.480},
            {"label": "A (return)", "prompt": "a wide view of a palace great hall with a massive stone hearth at centre, carved chimney breast with heraldic beasts rising to the frescoed ceiling, heavy tapestries hanging on both walls, wooden benches and iron candelabra flanking the hearth, a steady fire burning inside, warm amber firelight filling the vaulted space", "denoising": 0.470},
        ],
    },
    "E22": {
        "name": "E22_maproom",
        "prompts": [
            {"label": "A: Map room amber", "prompt": "a palace map room with large hand-painted navigation charts covering one wall, deep mahogany shelves on the others filled with leather-bound volumes, a heavy table scattered with folded documents, fresco of ships on a turbulent sea above the window, warm amber light", "denoising": 0.470},
            {"label": "B: Map room candlelit", "prompt": "a palace map room with large hand-painted navigation charts covering one wall, deep mahogany shelves on the others filled with leather-bound volumes, a heavy table scattered with folded documents, fresco of ships on a turbulent sea above the window, warm candlelight from brass holders", "denoising": 0.475},
            {"label": "C: Map room dusk", "prompt": "a palace map room with large hand-painted navigation charts covering one wall, deep mahogany shelves on the others filled with leather-bound volumes, a heavy table scattered with folded documents, fresco of ships on a turbulent sea above the window, fading dusk light through the window", "denoising": 0.480},
            {"label": "A (return)", "prompt": "a palace map room with large hand-painted navigation charts covering one wall, deep mahogany shelves on the others filled with leather-bound volumes, a heavy table scattered with folded documents, fresco of ships on a turbulent sea above the window, warm amber light", "denoising": 0.470},
        ],
    },
    "E23": {
        "name": "E23_reflection",
        "prompts": [
            {"label": "A: Reflection amber", "prompt": "closeup of a still body of water reflecting the face of a crowned king distorted by gentle ripples, water plants and reeds at the edges of the frame, the reflected face wavering in warm amber light, the surface of the water detailed with small insects and lily pads at the margins", "denoising": 0.470},
            {"label": "B: Reflection golden", "prompt": "closeup of a still body of water reflecting the face of a crowned king distorted by gentle ripples, water plants and reeds at the edges of the frame, the reflected face wavering in warm golden light, the surface of the water detailed with small insects and lily pads at the margins", "denoising": 0.475},
            {"label": "C: Reflection dusk", "prompt": "closeup of a still body of water reflecting the face of a crowned king distorted by gentle ripples, water plants and reeds at the edges of the frame, the reflected face wavering in fading dusk light, the surface of the water detailed with small insects and lily pads at the margins", "denoising": 0.480},
            {"label": "A (return)", "prompt": "closeup of a still body of water reflecting the face of a crowned king distorted by gentle ripples, water plants and reeds at the edges of the frame, the reflected face wavering in warm amber light, the surface of the water detailed with small insects and lily pads at the margins", "denoising": 0.470},
        ],
    },
    "E24": {
        "name": "E24_garden",
        "prompts": [
            {"label": "A: Garden amber", "prompt": "a formal palace garden seen from a high window, clipped box hedges in strict geometric parterre, gravel paths raked to uniformity, a central fountain still as glass, the palace facade with evenly spaced windows and stone pilasters filling the left edge, warm amber afternoon light", "denoising": 0.470},
            {"label": "B: Garden golden", "prompt": "a formal palace garden seen from a high window, clipped box hedges in strict geometric parterre, gravel paths raked to uniformity, a central fountain still as glass, the palace facade with evenly spaced windows and stone pilasters filling the left edge, warm golden hour light casting long shadows", "denoising": 0.475},
            {"label": "C: Garden morning", "prompt": "a formal palace garden seen from a high window, clipped box hedges in strict geometric parterre, gravel paths raked to uniformity, a central fountain still as glass, the palace facade with evenly spaced windows and stone pilasters filling the left edge, soft morning light with thin haze", "denoising": 0.480},
            {"label": "A (return)", "prompt": "a formal palace garden seen from a high window, clipped box hedges in strict geometric parterre, gravel paths raked to uniformity, a central fountain still as glass, the palace facade with evenly spaced windows and stone pilasters filling the left edge, warm amber afternoon light", "denoising": 0.470},
        ],
    },
    "E25": {
        "name": "E25_duel",
        "prompts": [
            {"label": "A: Duel wide amber", "prompt": "a wide palace courtyard framed by a frescoed arched colonnade on all sides, two identical kings in ornate plate armour crossing longswords at the centre, heraldic banners hanging from the gallery above, stone columns and carved balustrade, warm amber torchlight on polished steel and cobblestones", "denoising": 0.470},
            {"label": "B: Duel medium", "prompt": "a palace courtyard scene, two identical armoured kings dueling with longswords seen from the colonnade gallery above, the frescoed arches framing the combat below, heraldic banners and iron torch brackets along the gallery, warm golden light on the fighters and stone floor", "denoising": 0.475},
            {"label": "C: Duel close amber", "prompt": "two identical kings in ornate plate armour locked in swordfight in a palace courtyard, their crossed longswords at centre frame, the frescoed colonnade and heraldic banners visible behind them, stone cobblestones and fallen gauntlet on the ground, warm amber torchlight on steel", "denoising": 0.480},
            {"label": "A (return)", "prompt": "a wide palace courtyard framed by a frescoed arched colonnade on all sides, two identical kings in ornate plate armour crossing longswords at the centre, heraldic banners hanging from the gallery above, stone columns and carved balustrade, warm amber torchlight on polished steel and cobblestones", "denoising": 0.470},
        ],
    },
    "E26": {
        "name": "E26_wall",
        "prompts": [
            {"label": "A: Wall amber", "prompt": "a massive dressed-stone palace wall seen from a throne room, a single deep embrasure cutting through it showing five feet of solid thickness, frescoed figures on the room side looking toward the dark opening, warm amber torchlight on carved stone", "denoising": 0.470},
            {"label": "B: Wall candlelit", "prompt": "a massive dressed-stone palace wall seen from a throne room, a single deep embrasure cutting through it showing five feet of solid thickness, frescoed figures on the room side looking toward the dark opening, warm candlelight from iron sconces", "denoising": 0.475},
            {"label": "C: Wall dim", "prompt": "a massive dressed-stone palace wall seen from a throne room, a single deep embrasure cutting through it showing five feet of solid thickness, frescoed figures on the room side looking toward the dark opening, fading dim light from the embrasure", "denoising": 0.480},
            {"label": "A (return)", "prompt": "a massive dressed-stone palace wall seen from a throne room, a single deep embrasure cutting through it showing five feet of solid thickness, frescoed figures on the room side looking toward the dark opening, warm amber torchlight on carved stone", "denoising": 0.470},
        ],
    },
    "E28": {
        "name": "E28_gate",
        "prompts": [
            {"label": "A: Gate amber", "prompt": "a massive palace gate arch seen from inside, heavy iron-studded doors swung wide open, crowds of people in robes and cloaks streaming through the gate in both directions, the stone archway framing a bustling piazza with market stalls and a cathedral dome beyond, warm amber afternoon light flooding through the opening", "denoising": 0.470},
            {"label": "B: Gate golden", "prompt": "a massive palace gate arch seen from inside, heavy iron-studded doors swung wide open, crowds of people in robes and cloaks streaming through the gate in both directions, the stone archway framing a bustling piazza with market stalls and a cathedral dome beyond, warm golden hour light casting long shadows through the arch", "denoising": 0.475},
            {"label": "C: Gate morning", "prompt": "a massive palace gate arch seen from inside, heavy iron-studded doors swung wide open, crowds of people in robes and cloaks streaming through the gate in both directions, the stone archway framing a bustling piazza with market stalls and a cathedral dome beyond, soft morning light with the crowd beginning to arrive", "denoising": 0.480},
            {"label": "A (return)", "prompt": "a massive palace gate arch seen from inside, heavy iron-studded doors swung wide open, crowds of people in robes and cloaks streaming through the gate in both directions, the stone archway framing a bustling piazza with market stalls and a cathedral dome beyond, warm amber afternoon light flooding through the opening", "denoising": 0.470},
        ],
    },
    "E29": {
        "name": "E29_piazza",
        "prompts": [
            {"label": "A: Piazza amber", "prompt": "a city piazza with a central stone well, surrounding buildings of different heights forming a ring at each edge, long afternoon shadows stretching across cobblestones, a cat on the well rim, terracotta facades with shuttered windows, warm amber light", "denoising": 0.470},
            {"label": "B: Piazza golden", "prompt": "a city piazza with a central stone well, surrounding buildings of different heights forming a ring at each edge, long shadows stretching across cobblestones, a cat on the well rim, terracotta facades with shuttered windows, warm golden hour light", "denoising": 0.475},
            {"label": "C: Piazza dusk", "prompt": "a city piazza with a central stone well, surrounding buildings of different heights forming a ring at each edge, long shadows stretching across cobblestones, a cat on the well rim, terracotta facades with shuttered windows, fading dusk light with first oil lamps lit", "denoising": 0.480},
            {"label": "A (return)", "prompt": "a city piazza with a central stone well, surrounding buildings of different heights forming a ring at each edge, long afternoon shadows stretching across cobblestones, a cat on the well rim, terracotta facades with shuttered windows, warm amber light", "denoising": 0.470},
        ],
    },
    "E30": {
        "name": "E30_seafacing",
        "prompts": [
            {"label": "A: Sea room amber", "prompt": "a sea-facing palace room with a deep window recess looking out over a bay, the room's plastered walls and vaulted ceiling curving around the window like an ear around a canal, through the glass open water and sky, inside a fresco of Poseidon and waves on the curved wall, warm amber light", "denoising": 0.470},
            {"label": "B: Sea room bright", "prompt": "a sea-facing palace room with a deep window recess looking out over a bay, the room's plastered walls and vaulted ceiling curving around the window like an ear around a canal, through the glass open water and sky, inside a fresco of Poseidon and waves on the curved wall, bright marine light flooding in", "denoising": 0.475},
            {"label": "C: Sea room dusk", "prompt": "a sea-facing palace room with a deep window recess looking out over a bay, the room's plastered walls and vaulted ceiling curving around the window like an ear around a canal, through the glass open water and sunset sky, inside a fresco of Poseidon and waves on the curved wall, warm dusk light", "denoising": 0.480},
            {"label": "A (return)", "prompt": "a sea-facing palace room with a deep window recess looking out over a bay, the room's plastered walls and vaulted ceiling curving around the window like an ear around a canal, through the glass open water and sky, inside a fresco of Poseidon and waves on the curved wall, warm amber light", "denoising": 0.470},
        ],
    },
    "E31": {
        "name": "E31_musicroom",
        "prompts": [
            {"label": "A: Instruments amber", "prompt": "a closeup of a harpsichord and music stands in a palace music room, open sheet music with handwritten notes visible on the stands, the harpsichord lid open showing the strings, burned-down candelabra on the instrument, frescoed wall and gilded moulding behind, warm amber light", "denoising": 0.470},
            {"label": "B: Instruments candlelit", "prompt": "a closeup of a harpsichord and music stands in a palace music room, open sheet music with handwritten notes visible on the stands, the harpsichord lid open showing the strings, burned-down candelabra on the instrument, frescoed wall and gilded moulding behind, warm candlelight from the stubs", "denoising": 0.475},
            {"label": "C: Instruments dawn", "prompt": "a closeup of a harpsichord and music stands in a palace music room, open sheet music with handwritten notes visible on the stands, the harpsichord lid open showing the strings, burned-down candelabra on the instrument, frescoed wall and gilded moulding behind, pale dawn light from a window", "denoising": 0.480},
            {"label": "A (return)", "prompt": "a closeup of a harpsichord and music stands in a palace music room, open sheet music with handwritten notes visible on the stands, the harpsichord lid open showing the strings, burned-down candelabra on the instrument, frescoed wall and gilded moulding behind, warm amber light", "denoising": 0.470},
        ],
    },
    "notturno": {
        "name": "notturno_city",
        "prompts": [
            {"label": "A: City night amber", "prompt": "a medieval city at night seen from a rooftop, terracotta rooftops and bell towers under a dark sky with painted gold stars and a crescent moon, oil lamps glowing in distant windows, warm amber light on stone facades below", "denoising": 0.470},
            {"label": "B: City night silver", "prompt": "a medieval city at night seen from a rooftop, terracotta rooftops and bell towers under a dark sky with painted silver stars and a crescent moon, pale moonlight on the rooftops, faint oil lamps in windows far below", "denoising": 0.475},
            {"label": "C: City night deep", "prompt": "a medieval city at night seen from a rooftop, terracotta rooftops and bell towers under a deep dark sky with painted gold stars and a large crescent moon, warm glow rising from the streets below, the highest spires catching moonlight", "denoising": 0.480},
            {"label": "A (return)", "prompt": "a medieval city at night seen from a rooftop, terracotta rooftops and bell towers under a dark sky with painted gold stars and a crescent moon, oil lamps glowing in distant windows, warm amber light on stone facades below", "denoising": 0.470},
        ],
    },
    "siege": {
        "name": "siege_harbour",
        "prompts": [
            {"label": "A: Harbour fire amber", "prompt": "a wide panoramic view of a Roman harbour under attack, wooden warships burning with tall orange flames on dark water, thick black smoke choking a stormy sky, stone quays and a lighthouse in the middle distance, distant colonnaded buildings on fire, Thomas Cole painting style", "denoising": 0.470},
            {"label": "B: Harbour fire red", "prompt": "a wide panoramic view of a Roman harbour under attack, wooden warships burning with tall orange flames on dark water, thick black smoke billowing across a blood-red sky, stone quays and a lighthouse in the middle distance, distant colonnaded buildings glowing with fire, Thomas Cole painting style", "denoising": 0.475},
            {"label": "C: Harbour fire dark", "prompt": "a wide panoramic view of a Roman harbour under attack, wooden warships burning with tall orange flames on dark choppy water, dense black smoke obscuring a dark grey sky, stone quays and a lighthouse in the middle distance, distant colonnaded buildings smouldering, Thomas Cole painting style", "denoising": 0.480},
            {"label": "A (return)", "prompt": "a wide panoramic view of a Roman harbour under attack, wooden warships burning with tall orange flames on dark water, thick black smoke choking a stormy sky, stone quays and a lighthouse in the middle distance, distant colonnaded buildings on fire, Thomas Cole painting style", "denoising": 0.470},
        ],
    },
    "harbour": {
        "name": "harbour_market",
        "prompts": [
            {"label": "A: Harbour amber", "prompt": "a wide panoramic view of an open harbour with sailing ships moored at stone quays, a bustling market with stalls and crates along the waterfront, masts and rigging rising against soft clouds, distant hills beyond the harbour mouth, warm amber morning light on the water and stone buildings", "denoising": 0.470},
            {"label": "B: Harbour golden", "prompt": "a wide panoramic view of an open harbour with sailing ships moored at stone quays, a bustling market with stalls and crates along the waterfront, masts and rigging rising against soft clouds, distant hills beyond the harbour mouth, warm golden light spreading across the calm harbour water", "denoising": 0.475},
            {"label": "C: Harbour pale", "prompt": "a wide panoramic view of an open harbour with sailing ships moored at stone quays, a bustling market with stalls and crates along the waterfront, masts and rigging rising against soft pale clouds, distant hills beyond the harbour mouth, soft overcast light with silver reflections on the water", "denoising": 0.480},
            {"label": "A (return)", "prompt": "a wide panoramic view of an open harbour with sailing ships moored at stone quays, a bustling market with stalls and crates along the waterfront, masts and rigging rising against soft clouds, distant hills beyond the harbour mouth, warm amber morning light on the water and stone buildings", "denoising": 0.470},
        ],
    },
}

NEG_PROMPT = "angel, wings, halo, saint, nude, naked, bare chest, exposed skin, religious, crucifix, madonna, christ, biblical, cherub, putti"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", required=True, choices=list(SUBJECTS.keys()),
                        help="Subject to generate. Use --list to see all options.")
    parser.add_argument("--list", action="store_true", help="List all available subjects and exit")
    parser.add_argument("--tag", type=str, default="", help="Tag appended to filename")
    parser.add_argument("--smooth-sigma", type=float, default=1.5, help="Temporal smoothing sigma")
    parser.add_argument("--smooth-window", type=int, default=8, help="Temporal smoothing window")
    parser.add_argument("--transition-strength", type=float, default=0, help="Override transition strength")
    parser.add_argument("--skip-boundary", type=int, default=4, help="Skip first/last N RIFE frames per pair")
    parser.add_argument("--sinusoidal", action="store_true", help="Use sinusoidal timestep spacing")
    parser.add_argument("--no-lora", action="store_true", help="Skip LoRA loading")
    args = parser.parse_args()

    if args.list:
        print("Available subjects:")
        for k, v in SUBJECTS.items():
            print(f"  {k:8s}  {v['name']:20s}  {v['prompts'][0]['prompt'][:60]}...")
        return

    subject = SUBJECTS[args.subject]
    tag = f"_{args.tag}" if args.tag else ""
    name = f"{subject['name']}_horizontal{tag}"

    import torch
    import gc
    import time
    import numpy as np
    from PIL import Image

    from generate_videos import (
        LORA_SCALE, LORA_CANDIDATES,
        NUM_INFERENCE_STEPS, GUIDANCE_SCALE,
        CROPS_COORDS_TOP_LEFT, ORIGINAL_SIZE,
        NOISE_BLEND_TRANSITION, NOISE_BLEND_EDGE,
        STRUCTURAL_DECAY_RADIUS, EDGE_CROP, RIFE_PASSES,
        STYLE_PREFIX, STYLE_SUFFIX,
        random_noise_image, structural_decay,
        slerp_embeddings, encode_prompt, edge_suppression_callback,
        temporal_smooth_keyframes,
        load_rife, linear_interp, pil_to_tensor, tensor_to_np, crop_edges,
        archive_if_exists,
        V1_VISUALS, VISUALS_VENV_PACKAGES,
    )

    # --- ONLY DIFFERENCE: landscape resolution ---
    GEN_WIDTH = 1344
    GEN_HEIGHT = 768
    TARGET_SIZE = (GEN_WIDTH, GEN_HEIGHT)

    # Frame counts for ~60s output at 64x RIFE / 24fps / skip_boundary=4
    # 5 steady * 3 segments + 3 trans * 2 + 4 return + 1 anchor = 26 KFs -> ~59.6s
    STEADY_STRENGTHS = [0.55, 0.55, 0.60, 0.55, 0.55, 0.65, 0.55, 0.60]
    FPS = 24
    STEADY_FRAMES = 5
    TRANSITION_FRAMES = 3
    RETURN_FRAMES = 4
    WARMUP_FRAMES = 3

    OUTPUT_DIR = BASE_DIR / "videos" / "horizontal"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    STAGING_DIR = BASE_DIR / "videos" / "staging" / name
    kf_dir = STAGING_DIR / "keyframes"
    kf_dir.mkdir(parents=True, exist_ok=True)

    # Import evolved noise from crown script
    from generate_crown_video import evolved_noise_blend

    print("=" * 60)
    print(f"HORIZONTAL: {name}")
    print(f"Resolution: {GEN_WIDTH}x{GEN_HEIGHT} (landscape)")
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print("=" * 60)

    # Load pipeline (same as subject test)
    from diffusers import StableDiffusionXLImg2ImgPipeline, AutoencoderTiny, EulerDiscreteScheduler

    pipe = StableDiffusionXLImg2ImgPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        torch_dtype=torch.float16, variant="fp16",
    ).to("cuda")
    pipe.load_lora_weights("ByteDance/SDXL-Lightning",
                           weight_name="sdxl_lightning_4step_lora.safetensors")
    pipe.fuse_lora()
    pipe.unload_lora_weights()
    pipe.scheduler = EulerDiscreteScheduler.from_config(
        pipe.scheduler.config, timestep_spacing="trailing")
    pipe.vae = AutoencoderTiny.from_pretrained(
        "madebyollin/taesdxl", torch_dtype=torch.float16).to("cuda")
    pipe.safety_checker = None
    pipe.unet.to(memory_format=torch.channels_last)
    torch.cuda.empty_cache()

    # Fresco LoRA
    if not args.no_lora:
        lora_path = next((p for p in LORA_CANDIDATES if p.exists()), None)
        if lora_path:
            pipe.load_lora_weights(str(lora_path))
            pipe.fuse_lora(lora_scale=LORA_SCALE)
            pipe.unload_lora_weights()
            torch.cuda.empty_cache()
    print(f"  Pipeline loaded | VRAM: {torch.cuda.memory_allocated()/1024**3:.2f} GB")

    # Encode prompts
    prompts = subject["prompts"]
    all_embeds = []
    for p in prompts:
        full = f"{STYLE_PREFIX}{p['prompt']}{STYLE_SUFFIX}"
        embeds, pooled, neg_embeds, neg_pooled = encode_prompt(pipe, full, NEG_PROMPT)
        all_embeds.append((embeds, pooled, neg_embeds, neg_pooled))

    cfg_kwargs = {}
    if all_embeds[0][2] is not None:
        cfg_kwargs = {"negative_prompt_embeds": all_embeds[0][2],
                      "negative_pooled_prompt_embeds": all_embeds[0][3]}

    n_segments = len(prompts) - 1
    current_img = random_noise_image(w=GEN_WIDTH, h=GEN_HEIGHT)
    anchor_img = None
    frame_idx = 0

    # Warmup
    print(f"  Warmup...", end="", flush=True)
    embeds_cur, pooled_cur = all_embeds[0][0], all_embeds[0][1]
    for wi in range(WARMUP_FRAMES):
        strength = 0.85 if wi == 0 else 0.75
        input_img = evolved_noise_blend(current_img)
        result = pipe(
            prompt_embeds=embeds_cur, pooled_prompt_embeds=pooled_cur, **cfg_kwargs,
            image=input_img, strength=strength,
            num_inference_steps=NUM_INFERENCE_STEPS, guidance_scale=GUIDANCE_SCALE,
            crops_coords_top_left=CROPS_COORDS_TOP_LEFT,
            original_size=ORIGINAL_SIZE, target_size=TARGET_SIZE,
            callback_on_step_end=edge_suppression_callback,
            callback_on_step_end_tensor_inputs=["latents"],
        ).images[0]
        current_img = result
    print(" done")
    anchor_img = current_img.copy()

    # Generate segments (same logic as subject test)
    from generate_crown_video import TRANSITION_STRENGTHS, TRANSITION_NOISE_RAMP
    t0 = time.perf_counter()
    for seg_idx in range(n_segments):
        embeds_cur, pooled_cur = all_embeds[seg_idx][0], all_embeds[seg_idx][1]
        embeds_next, pooled_next = all_embeds[seg_idx + 1][0], all_embeds[seg_idx + 1][1]
        is_return = (seg_idx == n_segments - 1)

        if all_embeds[seg_idx][2] is not None:
            cfg_kwargs = {"negative_prompt_embeds": all_embeds[seg_idx][2],
                          "negative_pooled_prompt_embeds": all_embeds[seg_idx][3]}

        print(f"  Segment {seg_idx+1}/{n_segments}: {prompts[seg_idx]['label']}")

        for fi in range(STEADY_FRAMES):
            strength = STEADY_STRENGTHS[fi % len(STEADY_STRENGTHS)]
            input_img = evolved_noise_blend(structural_decay(current_img, STRUCTURAL_DECAY_RADIUS))
            result = pipe(
                prompt_embeds=embeds_cur, pooled_prompt_embeds=pooled_cur, **cfg_kwargs,
                image=input_img, strength=strength,
                num_inference_steps=NUM_INFERENCE_STEPS, guidance_scale=GUIDANCE_SCALE,
                crops_coords_top_left=CROPS_COORDS_TOP_LEFT,
                original_size=ORIGINAL_SIZE, target_size=TARGET_SIZE,
                callback_on_step_end=edge_suppression_callback,
                callback_on_step_end_tensor_inputs=["latents"],
            ).images[0]
            current_img = result
            current_img.save(kf_dir / f"{frame_idx:04d}.png")
            frame_idx += 1

        actual_trans_n = RETURN_FRAMES if is_return else TRANSITION_FRAMES
        print(f"    -> {'return' if is_return else 'transition'} ({actual_trans_n} frames)")

        for ti in range(actual_trans_n):
            t_linear = (ti + 1) / (actual_trans_n + 1)
            t = 3 * t_linear**2 - 2 * t_linear**3
            blended_embeds = slerp_embeddings(embeds_cur, embeds_next, t)
            blended_pooled = slerp_embeddings(pooled_cur, pooled_next, t)

            if is_return:
                # Very gentle return — spread blend across full segment, low ceiling
                progress = ti / max(1, actual_trans_n - 1)
                strength = 0.50 + progress * 0.10  # 0.50 -> 0.60
                # Gradual pixel blend: starts at 0, ramps to max 20% at final frame
                # Spread across full segment (not just second half)
                pixel_blend = progress * progress * 0.20  # quadratic ease-in, max 20%
                if pixel_blend > 0.01:
                    arr_cur = np.array(current_img).astype(np.float32)
                    arr_anchor = np.array(anchor_img).astype(np.float32)
                    blended_arr = arr_cur * (1 - pixel_blend) + arr_anchor * pixel_blend
                    current_img = Image.fromarray(blended_arr.clip(0, 255).astype(np.uint8))
            else:
                strength = args.transition_strength if args.transition_strength > 0 else 0.65

            trans_noise = NOISE_BLEND_TRANSITION
            input_img = evolved_noise_blend(
                structural_decay(current_img, STRUCTURAL_DECAY_RADIUS),
                blend_pct=trans_noise)

            result = pipe(
                prompt_embeds=blended_embeds, pooled_prompt_embeds=blended_pooled, **cfg_kwargs,
                image=input_img, strength=strength,
                num_inference_steps=NUM_INFERENCE_STEPS, guidance_scale=GUIDANCE_SCALE,
                crops_coords_top_left=CROPS_COORDS_TOP_LEFT,
                original_size=ORIGINAL_SIZE, target_size=TARGET_SIZE,
                callback_on_step_end=edge_suppression_callback,
                callback_on_step_end_tensor_inputs=["latents"],
            ).images[0]
            current_img = result
            current_img.save(kf_dir / f"{frame_idx:04d}.png")
            frame_idx += 1

    anchor_img.save(kf_dir / f"{frame_idx:04d}.png")
    frame_idx += 1
    print(f"  {frame_idx} keyframes in {time.perf_counter()-t0:.0f}s")

    del pipe
    gc.collect()
    torch.cuda.empty_cache()

    # Temporal smoothing
    temporal_smooth_keyframes(kf_dir, sigma=args.smooth_sigma, window=args.smooth_window)

    # RIFE 64x linear + skip keyframes
    print(f"\nRIFE {2**RIFE_PASSES}x linear + encode (skip keyframes)...")
    rife_model = load_rife()
    frame_paths = sorted(kf_dir.glob("*.png"))
    output_path = OUTPUT_DIR / f"{name}.mp4"
    archive_if_exists(output_path)

    import imageio
    writer = imageio.get_writer(str(output_path), fps=FPS, codec='libx264',
                                 quality=5, pixelformat='yuv420p')
    frame_count = 0
    prev_tensor = None
    prev_np = None
    first_np = None

    for i, fpath in enumerate(frame_paths):
        img = Image.open(fpath).convert("RGB")
        img_np = np.array(img)
        img_tensor = pil_to_tensor(img)
        if i == 0:
            first_np = img_np.copy()
        if prev_tensor is not None:
            with torch.no_grad():
                interps = linear_interp(rife_model, prev_tensor, img_tensor, RIFE_PASSES, skip_boundary=args.skip_boundary, sinusoidal=args.sinusoidal)
            for t in interps:
                f = tensor_to_np(t)
                cropped = crop_edges(f) if EDGE_CROP > 0 else f
                writer.append_data(cropped)
                frame_count += 1
            if i % 10 == 0 or i == 1:
                print(f"  RIFE pair {i}/{len(frame_paths)-1}")
        prev_tensor = img_tensor
        prev_np = img_np

    # Loop closure
    last_tensor = pil_to_tensor(Image.fromarray(prev_np))
    first_tensor = pil_to_tensor(Image.fromarray(first_np))
    with torch.no_grad():
        wrap_interps = linear_interp(rife_model, last_tensor, first_tensor, RIFE_PASSES, skip_boundary=args.skip_boundary, sinusoidal=args.sinusoidal)
    for wi, t in enumerate(wrap_interps):
        if wi == len(wrap_interps) - 1:
            break
        f = tensor_to_np(t)
        cropped = crop_edges(f) if EDGE_CROP > 0 else f
        writer.append_data(cropped)
        frame_count += 1

    writer.close()
    duration = frame_count / FPS
    size_mb = output_path.stat().st_size / 1024**2
    print(f"\n  {name}.mp4: {frame_count} frames, {duration:.1f}s at {FPS}fps, {size_mb:.1f} MB")
    print(f"  Output: {output_path}")


if __name__ == "__main__":
    main()
