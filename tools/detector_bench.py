"""Validate candidate detectors against synthetic ground truth, then against reality.

The point of this tool is to make it impossible to ship a detector the way eight
were shipped and withdrawn on 2026-08-11: invented, eyeballed against a handful
of clips, and believed. Here a candidate has to earn its place three times.

  1 MONOTONIC      does the score move with amplitude at all (Spearman)
  2 SENSITIVE      the smallest injected amplitude whose score leaves the clean
                   band, i.e. what the detector can actually see
  3 SPECIFIC       does it stay quiet on the other artefacts (cross-response)

and then the one that decides:

  4 TRANSFER       does it also separate the REAL hand-verified dirty clips from
                   the real clean ones. A detector that aces synthetic and misses
                   led18_renoir_field is a failed detector. This criterion was
                   written into the plan before the numbers existed, so it cannot
                   be rationalised away afterwards.

    python tools/detector_bench.py --sweeps                 # build the table
    python tools/detector_bench.py --transfer               # the real-clip check
    python tools/detector_bench.py --sweeps --transfer --json bench.json

Reads whatever `tools/artefact_sim.py --sweep` wrote into `outputs/_bench/`, so
generate the corpus first.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np


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

BENCH = ROOT / "outputs" / "_bench"
CACHE = BENCH / "_features.json"

# Which feature each artefact is SUPPOSED to move. Everything else it touches is
# cross-response, which is how a detector gets caught measuring the wrong thing.
TARGETS = {
    "canvas_edge": ["b_hf", "b_streak_sum", "b_streak_mean", "b_edgepeak",
                    "b_detail", "b_orient"],
    "morph": ["warp_resid", "rigid", "coherence", "speed"],
    "blur": ["focus_mean", "focus_trough", "focus_p05", "focus_swing"],
    "decimate": ["jitter", "flicker", "lurch"],
    "lurch": ["lurch", "jitter", "flicker"],
    "flicker": ["flicker", "jitter"],
}
ALL_FEATURES = sorted({f for v in TARGETS.values() for f in v})

# Hand-verified on 2026-08-11 by opening native-resolution edge strips, not by
# any metric and not by Gemini, which never flagged the edge at all.
REAL_DIRTY = ["led18_renoir_field", "led18_renoir_pond", "led18_soutine_trees",
              "led18_soutine_hill"]
REAL_CLEAN = ["led18_cole_woods", "led18_casa_plaster", "led17_c_dense",
              "led13_c_realloc_soft"]


def parse(name: str):
    m = re.match(r"(.+?)__(\w+)__([0-9p]+)\.mp4$", name)
    if not m:
        return None
    base, art, amp = m.groups()
    return base, art, float(amp.replace("p", "."))


def load_features(paths, cache: dict, limit=None) -> dict:
    for p in paths:
        if p.name in cache:
            continue
        try:
            cache[p.name] = features(p, K=10, limit=limit)
        except Exception as e:                       # a short or broken clip
            print(f"  ! {p.name}: {type(e).__name__} {e}")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    return cache


def spearman(x, y) -> float:
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3 or np.allclose(y, y[0]):
        return 0.0
    rx = np.argsort(np.argsort(x)).astype(float)
    ry = np.argsort(np.argsort(y)).astype(float)
    rx -= rx.mean(); ry -= ry.mean()
    d = np.sqrt((rx ** 2).sum() * (ry ** 2).sum())
    return float((rx * ry).sum() / d) if d else 0.0


def sweeps(cache: dict) -> list[dict]:
    rows = []
    by_art: dict[str, dict[str, list]] = {}
    for name, f in cache.items():
        p = parse(name)
        if not p:
            continue
        base, art, amp = p
        by_art.setdefault(art, {}).setdefault(base, []).append((amp, f))

    for art, bases in sorted(by_art.items()):
        for feat in ALL_FEATURES:
            rhos, seps, mins = [], [], []
            for base, pts in bases.items():
                pts = sorted(pts, key=lambda t: t[0])
                amps = [a for a, _ in pts]
                vals = [f.get(feat, float("nan")) for _, f in pts]
                if any(v != v for v in vals):
                    continue
                rhos.append(spearman(amps, vals))
                # clean band = the amp=0 control alone, so "leaves the band" means
                # it moves by more than the biggest run-to-run floor we measured (8%)
                ctl = vals[0]
                if abs(ctl) < 1e-12:
                    continue
                detect = None
                for a, v in zip(amps[1:], vals[1:]):
                    if abs(v - ctl) / abs(ctl) > 0.08:
                        detect = a
                        break
                mins.append(detect)
                seps.append(abs(vals[-1] - ctl) / abs(ctl))
            if not rhos:
                continue
            rows.append(dict(
                artefact=art, feature=feat,
                rho=float(np.mean(rhos)),
                span=float(np.mean(seps)) if seps else 0.0,
                min_amp=None if not mins or all(m is None for m in mins)
                        else max([m for m in mins if m is not None]),
                target=feat in TARGETS.get(art, []),
            ))
    return rows


def report_sweeps(rows):
    print("\nSENSITIVITY. rho = Spearman against amplitude (want |rho| ~ 1).")
    print("span = fractional change at max amplitude. min_amp = smallest amplitude")
    print("whose score moves more than the 8% run-to-run floor. '-' = never.\n")
    for art in sorted({r["artefact"] for r in rows}):
        sub = [r for r in rows if r["artefact"] == art and r["target"]]
        sub.sort(key=lambda r: -abs(r["rho"]))
        print(f"  {art}")
        for r in sub:
            ok = "OK " if (abs(r["rho"]) > 0.85 and r["min_amp"] is not None) else "   "
            print(f"    {ok}{r['feature']:<16} rho {r['rho']:+.2f}  span {r['span']*100:7.1f}%"
                  f"  min_amp {r['min_amp'] if r['min_amp'] is not None else '-'}")
        cross = [r for r in rows if r["artefact"] == art and not r["target"]
                 and abs(r["rho"]) > 0.85 and r["span"] > 0.20]
        if cross:
            print(f"       cross-response: {', '.join(sorted(set(c['feature'] for c in cross)))}")
    print()


def transfer(cache: dict, features_to_test=None):
    """The criterion that decides. Real clips, hand-verified, no synthetic anything."""
    feats = features_to_test or ALL_FEATURES
    print("\nTRANSFER. Real clips only, labels from opening native-resolution edge")
    print("strips by eye. A feature SEPARATES only if every dirty clip sits on one")
    print("side of every clean clip.\n")
    print(f"  {'feature':<16} {'dirty range':>22} {'clean range':>22}   separates")
    print("  " + "-" * 74)
    winners = []
    for f in feats:
        d = [cache[f"{n}__bc_1728x540.mp4"][f] for n in REAL_DIRTY
             if f"{n}__bc_1728x540.mp4" in cache]
        c = [cache[f"{n}__bc_1728x540.mp4"][f] for n in REAL_CLEAN
             if f"{n}__bc_1728x540.mp4" in cache]
        if len(d) < 3 or len(c) < 3:
            continue
        sep = "YES" if (max(d) < min(c) or min(d) > max(c)) else "no"
        if sep == "YES":
            winners.append(f)
        print(f"  {f:<16} {min(d):10.4f}..{max(d):<10.4f} {min(c):10.4f}..{max(c):<10.4f}   {sep}")
    print(f"\n  separating features: {winners if winners else 'NONE'}")
    return winners


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweeps", action="store_true")
    ap.add_argument("--transfer", action="store_true")
    ap.add_argument("--limit", type=int, default=150)
    ap.add_argument("--json")
    ap.add_argument("--refresh", action="store_true", help="ignore the feature cache")
    a = ap.parse_args()

    cache = {} if a.refresh or not CACHE.exists() else json.loads(
        CACHE.read_text(encoding="utf-8"))

    if a.sweeps:
        paths = sorted(BENCH.glob("*.mp4"))
        print(f"synthetic corpus: {len(paths)} clips")
        cache = load_features(paths, cache, limit=a.limit)
    if a.transfer:
        real = [ROOT / "outputs/nyc-billboard/led" / f"{n}__bc_1728x540.mp4"
                for n in REAL_DIRTY + REAL_CLEAN]
        cache = load_features([p for p in real if p.exists()], cache, limit=a.limit)

    rows = sweeps(cache) if a.sweeps else []
    if rows:
        report_sweeps(rows)
    if a.transfer:
        transfer(cache)
    if a.json:
        Path(a.json).write_text(json.dumps(
            {"sweeps": rows, "features": cache}, indent=1), encoding="utf-8")
        print(f"wrote {a.json}")


if __name__ == "__main__":
    main()
