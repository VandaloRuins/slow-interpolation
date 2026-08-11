"""Benchmark a render on speed, smoothness, focus and artefacts.

The measurement half of the publish gate. `review_gate.py` asks Gemini whether a
clip is any good; this says what it is DOING, in numbers that are comparable
between clips and that carry a known run-to-run floor and a known sensitivity.

    python tools/analyse_render.py outputs/nyc-billboard/led/*__bc_1728x540.mp4
    python tools/analyse_render.py --against led19_renoir_base <clip>   # A/B
    python tools/analyse_render.py --keyframes <clip>                   # + the cause

Judge the DELIVERED file. Raw and conformed differ: the retime is a real
processing step with real artefacts of its own.

EVERY NUMBER HERE HAS BEEN VALIDATED against known artefact amplitudes by
`tools/detector_bench.py`, which injects a defect at a stated size and checks the
measure moves with it. That is the difference between this file and the eight
detectors invented and withdrawn on 2026-08-11. Sensitivities below are the
smallest injected amplitude whose score moves more than the run-to-run floor.

  focus_mean/trough/p05   blur detected from sigma 1.0
  speed                   deformation detected from 0.5 px
  rigid                   deformation detected from 1.0 px
  warp_resid, coherence   deformation detected from 2.0 px
  jitter                  decimation detected from ratio 1.10; flicker from 1%
  flicker                 dropped frames detected from 1 per boundary
  b_detail                canvas edge detected from a 16 px band, WITHIN SUBJECT

THE ONE RULE THAT MATTERS FOR READING THIS OUTPUT
-------------------------------------------------
`b_detail` and the focus columns are **within-subject** measures. Comparing them
across different subjects is meaningless and actively misleading: on the real
corpus, `focus_mean` appears to separate four defective clips from four clean
ones by a factor of four, and that is entirely because the defective four are
Renoir and Soutine while the clean four are Cole and Casa. Confounded, not
detected. Use `--against` to compare a render with another render of the SAME
subject, which is the comparison that survived validation.

Superseded `tools/pulse_plot.py` (448x256 Laplacian, the wrong instrument at the
wrong resolution) and the sharpness half of `tools/motion_profile.py`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Load the measurement core WITHOUT importing the package __init__, which pulls in
# Pipeline -> torch -> ~2 GB of CUDA DLL mappings this tool never uses. On a loaded
# machine that is the difference between running and "the paging file is too small".
def _load_quality():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "si_quality", Path(__file__).resolve().parents[1]
        / "src" / "slow_interpolation" / "quality.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


_Q = _load_quality()
features, keyframe_features = _Q.features, _Q.keyframe_features


# Floors from re-running one config unchanged (led15_c_repro against
# led13_c_realloc_soft). A difference smaller than the floor is not a result.
FLOORS = {"lurch": 0.02, "focus_mean": 0.013, "focus_trough": 0.016, "loop": 0.08}

COLUMNS = [
    ("speed", "speed", "{:6.3f}"),
    ("rigid", "rigid%", "{:6.1%}"),
    ("warp_resid", "warp", "{:6.2f}"),
    ("lurch", "lurch", "{:6.2f}"),
    ("jitter", "jit", "{:5.2f}"),
    ("flicker", "flick", "{:5d}"),
    ("focus_mean", "focus", "{:7.4f}"),
    ("focus_trough", "TROUGH", "{:8.4f}"),
    ("b_detail", "b_detail", "{:8.3f}"),
]


def fmt(v, spec):
    try:
        return spec.format(v)
    except (ValueError, TypeError):
        return f"{str(v):>6}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", nargs="+")
    ap.add_argument("-K", "--keyframes-count", type=int, default=10)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--against", help="a clip of the SAME subject, to diff against")
    ap.add_argument("--keyframes", action="store_true",
                    help="also read outputs/staging/<name>/keyframes/, the CAUSE side")
    ap.add_argument("--json")
    a = ap.parse_args()

    base = None
    if a.against:
        p = Path(a.against)
        if not p.exists():
            cand = list((ROOT / "outputs/nyc-billboard/led").glob(f"{a.against}*.mp4"))
            p = cand[0] if cand else p
        base = features(p, K=a.keyframes_count, limit=a.limit)
        print(f"baseline: {base['clip']}\n")

    hdr = f"{'clip':<30}" + "".join(f"{h:>9}" for _, h, _ in COLUMNS)
    print(hdr)
    print("-" * len(hdr))
    rows = []
    for v in a.videos:
        p = Path(v)
        if not p.exists():
            print(f"{p.name:<30} MISSING")
            continue
        r = features(p, K=a.keyframes_count, limit=a.limit)
        name = r["clip"].replace("__bc_1728x540.mp4", "").replace(".mp4", "")
        line = f"{name:<30}"
        for key, _, spec in COLUMNS:
            line += f"{fmt(r.get(key), spec):>9}"
        print(line)
        if base:
            d = f"{'  vs baseline':<30}"
            for key, _, _ in COLUMNS:
                x, y = r.get(key), base.get(key)
                if isinstance(x, (int, float)) and isinstance(y, (int, float)) and y:
                    pct = 100 * (x - y) / abs(y)
                    floor = FLOORS.get(key, 0.0) * 100
                    mark = "*" if abs(pct) > floor else " "
                    d += f"{pct:+6.0f}%{mark}".rjust(9)
                else:
                    d += f"{'':>9}"
            print(d)
        if a.keyframes:
            kf = ROOT / "outputs" / "staging" / name / "keyframes"
            k = keyframe_features(kf) if kf.exists() else {}
            if k:
                print(f"{'  keyframes RIFE was given':<30} "
                      f"n={k['kf_count']}  ssim {k['kf_ssim']:.3f} "
                      f"(worst {k['kf_ssim_worst']:.3f})  travel {k['kf_flow']:.2f}px  "
                      f"ceiling hf {k['kf_hf']:.4f}")
            else:
                print(f"{'  keyframes':<30} not on disk; "
                      f"modal volume get slow-interp-outputs staging/{name}/keyframes/NNNN.png")
        rows.append(r)

    print("\nfloors: lurch +-2%  focus +-1.3%  trough +-1.6%  loop +-8%.  "
          "* = outside the floor.")
    print("b_detail and focus are WITHIN-SUBJECT only. Across subjects they measure "
          "the subject, not the defect.")
    if a.json:
        Path(a.json).write_text(json.dumps(rows, indent=1), encoding="utf-8")
        print(f"wrote {a.json}")


if __name__ == "__main__":
    main()
