"""Build a local browser gallery of every render under outputs/.

Scans outputs/ for MP4s, pulls whatever generation metadata exists for each
(cloud runs write a sibling .manifest.json with the full config embedded; local
runs write nothing, so we match a config by subject name), probes the file with
ffprobe, extracts a poster frame, and writes a single self-contained page.

    python tools/gallery.py            # build and report
    python tools/gallery.py --open     # build and open in the browser
    python tools/gallery.py --refresh  # re-extract posters even if cached

Output: gallery.html at the repo root. No external assets, no network, no build
step. Works straight off file://.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML is required (pip install pyyaml)", file=sys.stderr)
    raise

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
CONFIG_DIRS = [ROOT / "examples" / "configs"]
POSTER_DIR = OUTPUTS / "_gallery" / "posters"
PREVIEW_DIR = OUTPUTS / "_gallery" / "previews"
# Renders come out of the pipeline at ~40 Mbps (encoding.quality 9), so a 75 s
# clip is 363 MB. That will not stream to a phone over a tunnel no matter how
# correct the server is. Anything above this gets a web-friendly proxy for
# playback; the original stays on disk untouched.
PREVIEW_OVER_MB = 25
PAGE = ROOT / "gallery.html"
# Notes you type in the gallery. The page cannot write to disk from file://, so
# it keeps them in localStorage and exports this file on demand; the builder
# reads it back so a rebuild never loses them. Tell the agent to read it.
FEEDBACK = ROOT / "gallery-feedback.json"


def load_feedback() -> dict[str, str]:
    if FEEDBACK.exists():
        try:
            return {k: str(v) for k, v in json.loads(
                FEEDBACK.read_text(encoding="utf-8")).items()}
        except Exception:
            pass
    return {}

# Delivery specs we know about, so a conformed file can be badged pass/fail
# instead of the viewer having to remember the numbers.
DELIVERY_SPECS = {
    (912, 2736): {"name": "NY-1087-A", "frames": 300, "fps": 30},
    (1728, 540): {"name": "NY-1087-B/C", "frames": 300, "fps": 30},
}

STYLE_TAGS = {
    "thomas_cole": "cole",
    "tcole": "cole",
    "renoir": "renoir",
    "casa": "casa-del-suono",
    "soutine": "soutine",
}


# --------------------------------------------------------------------- probing

def ffprobe(path: Path) -> dict | None:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
             "-show_entries",
             "stream=width,height,nb_read_frames,r_frame_rate,codec_name,pix_fmt",
             "-show_entries", "format=duration,size",
             "-of", "json", str(path)],
            capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    data = json.loads(out)
    if not data.get("streams"):
        return None
    s = data["streams"][0]
    fmt = data.get("format", {})
    num, _, den = s.get("r_frame_rate", "0/1").partition("/")
    fps = float(num) / float(den) if den and float(den) else 0.0
    frames = int(s.get("nb_read_frames") or 0)
    return {
        "width": int(s["width"]),
        "height": int(s["height"]),
        "frames": frames,
        "fps": round(fps, 3),
        "codec": s.get("codec_name", ""),
        "pix_fmt": s.get("pix_fmt", ""),
        "duration": round(frames / fps, 3) if fps else float(fmt.get("duration", 0) or 0),
        "size": int(fmt.get("size", 0) or 0),
    }


def poster_for(video: Path, info: dict, refresh: bool) -> Path | None:
    POSTER_DIR.mkdir(parents=True, exist_ok=True)
    rel = video.relative_to(OUTPUTS).with_suffix("")
    dest = POSTER_DIR / (str(rel).replace("\\", "__").replace("/", "__") + ".jpg")
    if dest.exists() and not refresh:
        return dest
    mid = max(0.0, (info.get("duration") or 1.0) / 2)
    try:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", f"{mid:.3f}", "-i", str(video),
             "-frames:v", "1", "-vf", "scale=560:-2", str(dest)],
            check=True, capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return dest if dest.exists() else None


# -------------------------------------------------------------------- metadata

def preview_for(video: Path, info: dict) -> Path | None:
    """Web-playable proxy for oversized renders. Returns None if not needed."""
    size_mb = info.get("size", 0) / 1048576
    if size_mb <= PREVIEW_OVER_MB:
        return None
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    rel = video.relative_to(OUTPUTS).with_suffix("")
    dest = PREVIEW_DIR / (str(rel).replace("\\", "__").replace("/", "__") + ".mp4")
    if dest.exists() and dest.stat().st_mtime >= video.stat().st_mtime:
        return dest
    try:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(video),
             "-vf", "scale='min(1280,iw)':-2",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
             "-pix_fmt", "yuv420p",
             # faststart puts the moov atom first, without which a browser must
             # download the whole file before it can begin playback.
             "-movflags", "+faststart", "-an", str(dest)],
            check=True, capture_output=True, timeout=1800)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return dest if dest.exists() else None


def load_configs() -> dict[str, dict]:
    """Map subject name -> parsed config, for local runs that write no manifest."""
    index: dict[str, dict] = {}
    for base in CONFIG_DIRS:
        if not base.exists():
            continue
        for path in base.rglob("*.yaml"):
            try:
                cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(cfg, dict):
                continue
            name = (cfg.get("output_name")
                    or (cfg.get("subject") or {}).get("name"))
            if name:
                cfg["__config_path"] = str(path.relative_to(ROOT)).replace("\\", "/")
                index.setdefault(str(name), cfg)
    return index


def base_stem(stem: str) -> str:
    """Strip a conform suffix: billboard_a_arch__a_912x2736 -> billboard_a_arch."""
    return stem.split("__", 1)[0]


_GENERATED_AT: dict[str, tuple[float, bool]] = {}


def generated_at(video: Path) -> tuple[float, bool]:
    """When the render was GENERATED, not when its file last changed.

    File mtime is the wrong sort key. `sync_outputs.py` pulls from the Modal
    volume and every downloaded file gets an mtime of now, so a sync silently
    re-orders the whole gallery and puts old renders on top of today's work.
    That is not a display quirk: it makes the newest renders unfindable in a
    290-card page, which is exactly how they get reported as missing.

    The manifest's `started_at_utc` is the real generation time and survives
    any number of re-downloads. Renders with no manifest (local runs, older
    work) fall back to mtime and are labelled differently on the card, so a
    wrong date is visible rather than silently mixed in with correct ones.

    Returns (epoch_seconds, exact).
    """
    key = str(video)
    if key in _GENERATED_AT:
        return _GENERATED_AT[key]
    result = (video.stat().st_mtime, False)
    manifest = video.with_suffix("").with_suffix(".manifest.json")
    if not manifest.exists():
        manifest = video.with_name(video.stem + ".manifest.json")
    if manifest.exists():
        try:
            ts = json.loads(manifest.read_text(encoding="utf-8")).get("started_at_utc")
            if ts:
                result = (datetime.fromisoformat(ts).timestamp(), True)
        except Exception:
            pass
    _GENERATED_AT[key] = result
    return result


def metadata_for(video: Path, configs: dict[str, dict]) -> tuple[dict, dict]:
    """Return (config, run) where run holds manifest-only fields."""
    run: dict = {}
    manifest = video.with_suffix("").with_suffix(".manifest.json")
    if not manifest.exists():
        manifest = video.with_name(video.stem + ".manifest.json")
    if manifest.exists():
        try:
            m = json.loads(manifest.read_text(encoding="utf-8"))
            run = {k: m.get(k) for k in
                   ("started_at_utc", "ended_at_utc", "git_commit", "gpu",
                    "cost_usd", "wall_time_s") if m.get(k) is not None}
            raw = m.get("config_yaml")
            if raw:
                cfg = yaml.safe_load(raw)
                if isinstance(cfg, dict):
                    cfg["__config_path"] = f"embedded in {manifest.name}"
                    return cfg, run
        except Exception:
            pass
    return configs.get(base_stem(video.stem), {}), run


def tags_for(video: Path, info: dict, cfg: dict) -> list[str]:
    tags: list[str] = []
    blob = " ".join([
        str((cfg.get("style") or {}).get("name", "")),
        str((cfg.get("style") or {}).get("lora_path", "")),
        str((cfg.get("style") or {}).get("prefix", "")),
    ]).lower()
    for needle, tag in STYLE_TAGS.items():
        if needle in blob:
            tags.append(tag)
            break

    # `.get` rather than `[...]`: still-set cards pass a partial info dict.
    w, h = info.get("width"), info.get("height")
    if w and h:
        ar = w / h
        tags.append("square" if abs(ar - 1) < 0.02 else
                    "portrait" if ar < 1 else "landscape")
        tags.append(f"{w}x{h}")

    spec = DELIVERY_SPECS.get((w, h))
    if spec:
        tags.append("delivery")
        tags.append(spec["name"])
    elif "__" in video.stem:
        tags.append("conformed")
    else:
        tags.append("source")

    parts = video.relative_to(OUTPUTS).parts
    if len(parts) > 1:
        tags.append(parts[0])
    if info.get("duration"):
        tags.append("10s" if abs(info["duration"] - 10) < 0.05 else
                    f"{round(info['duration'])}s")
    return list(dict.fromkeys(t for t in tags if t))


def png_size(path: Path) -> tuple[int | None, int | None]:
    """Width and height straight out of the PNG IHDR chunk. No PIL dependency."""
    try:
        with path.open("rb") as f:
            head = f.read(24)
        if head[:8] != b"\x89PNG\r\n\x1a\n":
            return None, None
        return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
    except Exception:
        return None, None


def png_dirs() -> list[tuple[Path, list[Path]]]:
    """Every directory under outputs/ holding PNGs, with its images sorted by name.

    Keyframe staging dirs and validation grids both land here. Sorting by name
    keeps `0000.png` first and `0006.png` last, which is the comparison that
    matters for a chained render.
    """
    found: dict[Path, list[Path]] = {}
    for p in OUTPUTS.rglob("*.png"):
        if "_gallery" in p.parts or "archive" in p.parts:
            continue
        found.setdefault(p.parent, []).append(p)
    return [(d, sorted(ps)) for d, ps in found.items() if ps]


def variant_rows(cfg: dict) -> list[tuple[str, str]]:
    """Spec rows for the dials that differ BETWEEN variants of a sweep.

    A sweep is unreadable if every card shows the same spec block. These are the
    knobs a comparison run actually varies: sampling budget, backbone, VAE, the
    RIFE timestep scheme, the segment frame counts, and the render profile.
    Rows are emitted only when the value is non-default, so ordinary renders stay
    uncluttered.
    """
    rows: list[tuple[str, str]] = []

    sampling = cfg.get("sampling") or {}
    steps = sampling.get("num_inference_steps", 4)
    guidance = sampling.get("guidance_scale", 1.5)
    # Actual denoising steps = int(steps * strength); surface the steady-strength
    # case because it is what the eye is judging.
    render = cfg.get("render") if isinstance(cfg.get("render"), dict) else {}
    strengths = render.get("steady_strengths") or [0.55]
    real = int(steps * strengths[0])
    rows.append(("sampling", f"{steps} steps @ g{guidance:g} -> {real} real"))

    models = cfg.get("models") or {}
    if "lightning_lora" in models and not models["lightning_lora"]:
        rows.append(("backbone", "SDXL base (no Lightning)"))
    elif models.get("lightning_weight_name"):
        rows.append(("backbone", str(models["lightning_weight_name"]).replace(".safetensors", "")))
    if models.get("vae_kind") == "full":
        rows.append(("vae", f"full KL ({models.get('vae_full', 'sdxl-vae')})"))

    rife = cfg.get("rife") or {}
    if rife:
        scheme = "sinusoidal" if rife.get("sinusoidal") else "linear"
        rows.append(
            ("rife", f"{rife.get('passes', '?')} passes, {scheme}, "
                     f"skip {rife.get('skip_boundary', '?')}")
        )

    frames = cfg.get("frames") or {}
    if frames:
        rows.append((
            "frames",
            f"steady {frames.get('steady', '?')} / trans {frames.get('transition', '?')} "
            f"/ return {frames.get('return_', '?')}",
        ))

    profile = render.get("profile") if isinstance(render, dict) else None
    if isinstance(cfg.get("render"), str):
        profile = cfg["render"]
    if profile and profile != "standard":
        rows.append(("profile", str(profile)))

    return rows


def compliance(info: dict) -> tuple[str, str] | None:
    spec = DELIVERY_SPECS.get((info["width"], info["height"]))
    if not spec:
        return None
    problems = []
    if info["frames"] != spec["frames"]:
        problems.append(f"{info['frames']} frames, expected {spec['frames']}")
    if abs(info["fps"] - spec["fps"]) > 0.01:
        problems.append(f"{info['fps']} fps, expected {spec['fps']}")
    if info["codec"] not in ("h264", "hevc"):
        problems.append(f"codec {info['codec']}")
    if problems:
        return "fail", f"{spec['name']}: " + "; ".join(problems)
    return "pass", f"{spec['name']} spec met: {info['width']}x{info['height']}, 300 frames, 30 fps, H.264"


# ----------------------------------------------------------------------- page

def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT)).replace("\\", "/")


CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
  --bg:#0d0b0a; --panel:#17130f; --line:#2e2621; --ink:#f2e9df;
  --muted:#a2917f; --accent:#e0913f; --ok:#5f9e5f; --bad:#c4563f;
  --radius:10px;
}
html{color-scheme:dark}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
  -webkit-font-smoothing:antialiased}
header{position:sticky;top:0;z-index:10;background:rgba(13,11,10,.94);
  backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:18px 24px}
h1{margin:0 0 2px;font-size:17px;font-weight:600;letter-spacing:.2px}
.sub{color:var(--muted);font-size:13px}
.controls{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px;align-items:center}
input[type=search]{flex:1 1 240px;min-width:200px;background:var(--panel);
  border:1px solid var(--line);color:var(--ink);border-radius:var(--radius);
  padding:9px 12px;font-size:14px}
input[type=search]:focus-visible,button:focus-visible,summary:focus-visible{
  outline:2px solid var(--accent);outline-offset:2px}
/* 59 tags filled 86% of a phone screen before any render was visible, so the
   filter wall is behind a toggle. It is now CLOSED by default at every width:
   at 74 tags it took five rows of a desktop screen too, so the page opened on
   its own chrome instead of on the work. */
.tagbar{display:none;gap:6px;flex-wrap:wrap;margin-top:10px}
.tagbar.open{display:flex}
/* The caret is what makes the button read as a disclosure control rather than
   as one more filter chip sitting among the others. */
.caret{display:inline-block;margin-left:7px;font-size:9px;line-height:1;
  transition:transform .16s;transform:rotate(-90deg);opacity:.75}
.chip[aria-pressed=true] .caret{transform:rotate(0deg)}
/* Active-filter count. Collapsing must never hide that a filter is on, so the
   button carries the count and turns accent when any tag is selected. */
#togglefilters.filtered{color:var(--bg);background:var(--accent);
  border-color:var(--accent)}
.chip{background:var(--panel);border:1px solid var(--line);color:var(--muted);
  border-radius:999px;padding:7px 14px;font:inherit;font-size:12.5px;cursor:pointer;
  transition:.14s;white-space:nowrap}
.chip:hover{color:var(--ink);border-color:var(--accent)}
.chip[aria-pressed=true]{background:var(--accent);border-color:var(--accent);
  color:#1a1206;font-weight:600}
.chip .n{opacity:.6;margin-left:5px}
button.tag{background:var(--panel);border:1px solid var(--line);color:var(--muted);
  border-radius:999px;padding:5px 11px;font-size:12px;cursor:pointer;
  font-family:inherit;transition:.14s}
button.tag:hover{color:var(--ink);border-color:var(--accent)}
button.tag[aria-pressed=true]{background:var(--accent);border-color:var(--accent);
  color:#1a1206;font-weight:600}
/* Touch: 44px is the iOS minimum. Everything here was 27px. */
@media (pointer:coarse), (max-width:640px){
  .chip,.flipbtn,input[type=search]{min-height:44px}
  .chip{padding:11px 16px;font-size:13.5px}
  .flipbtn{padding:11px 18px;font-size:13px;align-self:stretch;text-align:center}
  textarea.note{font-size:16px}   /* below 16px iOS zooms the page on focus */
}
main{padding:24px;display:grid;gap:20px;
  grid-template-columns:repeat(auto-fill,minmax(330px,1fr));max-width:1800px;margin:0 auto}
.card{perspective:1600px;background:none;border:0;border-radius:0;overflow:visible;
  min-width:0}
.card.hidden{display:none}
.flipper{position:relative;transform-style:preserve-3d;min-width:0;
  transition:transform .55s cubic-bezier(.25,.8,.3,1)}
.card.flipped .flipper{transform:rotateY(180deg)}
.face{backface-visibility:hidden;-webkit-backface-visibility:hidden;
  background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
  overflow:hidden;display:flex;flex-direction:column;min-width:0}
/* The back is absolutely positioned over the front so the card keeps the
   front's natural height; no fixed heights, so long prompt blocks still work. */
.face.back{position:absolute;inset:0;transform:rotateY(180deg);
  padding:13px 14px 14px;gap:9px;overflow:auto;
  /* backface-visibility hides the back but does NOT stop it capturing clicks.
     Without this the invisible back sits over the front and swallows every
     click, which silently kills both video playback and the flip button. */
  pointer-events:none}
.card.flipped .face.back{pointer-events:auto}
.card.flipped .face.front{pointer-events:none}
.backhead{font-weight:600;font-size:13px;word-break:break-word;color:var(--accent)}
.flipbtn{align-self:flex-start;margin-top:9px;background:#221b15;color:var(--muted);
  border:1px solid var(--line);border-radius:999px;padding:4px 12px;font:inherit;
  font-size:11.5px;cursor:pointer}
.flipbtn:hover{color:var(--ink);border-color:var(--accent)}
.flipbtn.has{color:var(--accent);border-color:#4a3a22}
.media{background:#000;display:flex;align-items:center;justify-content:center;
  max-height:420px;overflow:hidden}
.media video,.media img{width:100%;height:auto;max-height:420px;object-fit:contain;display:block}
.body{padding:14px 15px 15px;display:flex;flex-direction:column;gap:9px;flex:1}
.name{font-weight:600;font-size:14px;word-break:break-word}
.path{color:var(--muted);font-size:11.5px;font-family:ui-monospace,Menlo,Consolas,monospace;
  word-break:break-all}
.tags{display:flex;gap:5px;flex-wrap:wrap}
.tags span{background:#221b15;border:1px solid var(--line);color:var(--muted);
  border-radius:999px;padding:2px 9px;font-size:11px}
.tags span.style{color:var(--accent);border-color:#4a3a22}
dl.specs{margin:0;display:grid;grid-template-columns:auto 1fr;gap:2px 12px;font-size:12.5px}
dl.specs dt{color:var(--muted)}
dl.specs dd{margin:0;font-family:ui-monospace,Menlo,Consolas,monospace}
.badge{font-size:12px;border-radius:6px;padding:6px 9px;line-height:1.35}
.badge.pass{background:rgba(95,158,95,.13);border:1px solid var(--ok);color:#a8d6a8}
.badge.fail{background:rgba(196,86,63,.13);border:1px solid var(--bad);color:#e8a898}
details{border-top:1px solid var(--line);padding-top:9px;margin-top:auto}
summary{cursor:pointer;color:var(--muted);font-size:12.5px;user-select:none}
summary:hover{color:var(--ink)}
.prompt{margin-top:9px;border-left:2px solid var(--accent);padding-left:10px}
.prompt .lbl{color:var(--accent);font-size:11.5px;font-weight:600;margin-bottom:2px}
.prompt .txt{color:var(--muted);font-size:12.5px}
.neg{margin-top:9px;color:var(--muted);font-size:12px}
/* Still sets span the full grid width: a keyframe strip is only readable if the
   first and last frame are large enough to compare side by side. */
.card.stills{grid-column:1/-1}
.card.stills .body{flex:0}
.strip{display:flex;gap:10px;overflow-x:auto;padding:0 15px 15px;scrollbar-width:thin;
  min-width:0;max-width:100%;-webkit-overflow-scrolling:touch}
.strip figure{margin:0;flex:0 0 auto;max-width:340px}
.strip img{height:210px;width:auto;display:block;border-radius:4px;border:1px solid var(--line);
  background:#000}
.strip figcaption{color:var(--muted);font-size:11px;margin-top:4px;text-align:center;
  font-family:ui-monospace,Menlo,Consolas,monospace}
.face.back textarea.note{flex:1;min-height:120px;margin-top:0}
textarea.note{width:100%;box-sizing:border-box;margin-top:9px;min-height:52px;
  background:#17130f;color:var(--ink);border:1px solid var(--line);border-radius:6px;
  padding:7px 9px;font:inherit;font-size:12.5px;resize:vertical}
textarea.note:focus{outline:none;border-color:var(--accent)}
textarea.note.filled{border-color:var(--accent)}
/* The spec list is 14 rows and swallowed the whole card on a phone. Collapsed
   by default; the summary keeps size, duration and file size visible. */
details.specs-d{border-top:1px solid var(--line);padding-top:9px;margin-top:0}
details.specs-d>summary{color:var(--muted);font-size:12.5px;
  font-family:ui-monospace,Menlo,Consolas,monospace}
details.specs-d>summary:hover{color:var(--ink)}
details.specs-d[open]>summary{color:var(--accent);margin-bottom:7px}
details.specs-d dl.specs{margin-top:2px}
@media (pointer:coarse), (max-width:640px){
  details.specs-d>summary,details>summary{min-height:38px;display:flex;align-items:center}
}
.dlrow{display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin-top:9px}
.dlrow .flipbtn{margin-top:0}
a.dl{background:#221b15;border:1px solid var(--line);color:var(--accent);
  border-radius:999px;padding:4px 12px;font-size:11.5px;text-decoration:none;
  white-space:nowrap}
a.dl:hover{border-color:var(--accent);background:#2b2118}
a.dl.light{color:var(--muted)}
@media (pointer:coarse), (max-width:640px){
  a.dl{min-height:44px;display:flex;align-items:center;padding:0 16px;font-size:13px}
}
.empty{grid-column:1/-1;text-align:center;color:var(--muted);padding:60px 20px}
footer{color:var(--muted);font-size:12px;padding:8px 24px 40px;text-align:center}
@media (max-width:640px){
  main{padding:12px;gap:14px;grid-template-columns:1fr}
  header{padding:11px 12px;position:static}   /* was sticky, and it covered cards */
  h1{font-size:16px}
  .sub{font-size:12px}
  .tagbar{max-height:34vh;overflow-y:auto;-webkit-overflow-scrolling:touch}
  .face.back{padding:11px}
  .card.stills .strip img{height:150px}
  /* Must land AFTER the base textarea rule: equal specificity, source order
     decides. Below 16px iOS zooms the whole page when the field is focused. */
  textarea.note{font-size:16px}
}
"""

JS = """
const cards=[...document.querySelectorAll('.card')];
const search=document.getElementById('q');
const active=new Set();
let notesOnly=false;
function apply(){
  const q=search.value.trim().toLowerCase();
  let shown=0;
  for(const c of cards){
    const tags=(c.dataset.tags||'').split('|');
    const okTag=[...active].every(t=>tags.includes(t));
    const okQ=!q||(c.dataset.search||'').includes(q);
    const ta=c.querySelector('textarea.note');
    const okNotes=!notesOnly||(ta&&ta.value.trim());
    const vis=okTag&&okQ&&okNotes;
    c.classList.toggle('hidden',!vis);
    if(vis)shown++;
  }
  document.getElementById('empty').style.display=shown?'none':'block';
  document.getElementById('count').textContent=shown+' of '+cards.length;
}
search.addEventListener('input',apply);
for(const b of document.querySelectorAll('.chip[data-tag]')){
  b.addEventListener('click',()=>{
    const t=b.dataset.tag;
    if(active.has(t)){active.delete(t);b.setAttribute('aria-pressed','false');}
    else{active.add(t);b.setAttribute('aria-pressed','true');}
    apply();filterBadge();
  });
}
// Only load video on demand; dozens of autoplaying loops would thrash the page.
for(const c of cards){
  const m=c.querySelector('.media');
  if(!m||!m.dataset.src)continue;
  m.addEventListener('click',()=>{
    if(m.querySelector('video'))return;
    const v=document.createElement('video');
    v.src=m.dataset.src;v.controls=true;v.loop=true;v.muted=true;v.autoplay=true;
    v.playsInline=true;m.replaceChildren(v);
  });
}

// Feedback notes. localStorage keeps them across reloads; "Save feedback"
// exports gallery-feedback.json, which tools/gallery.py reads back on rebuild.
const LS='si-gallery-feedback';
const store=JSON.parse(localStorage.getItem(LS)||'{}');
const notes=[...document.querySelectorAll('textarea.note')];
for(const n of notes){
  const k=n.dataset.key;
  if(store[k]!==undefined&&!n.value)n.value=store[k];
  n.classList.toggle('filled',!!n.value.trim());
  n.addEventListener('input',()=>{
    if(n.value.trim())store[k]=n.value; else delete store[k];
    localStorage.setItem(LS,JSON.stringify(store));
    n.classList.toggle('filled',!!n.value.trim());
    count();
  });
}
function count(){
  document.getElementById('notecount').textContent=notes.filter(t=>t.value.trim()).length;
}
document.getElementById('export').addEventListener('click',()=>{
  const out={};
  for(const n of notes) if(n.value.trim()) out[n.dataset.key]=n.value.trim();
  const b=new Blob([JSON.stringify(out,null,2)],{type:'application/json'});
  const a=document.createElement('a');
  a.href=URL.createObjectURL(b); a.download='gallery-feedback.json'; a.click();
  alert('Saved gallery-feedback.json to your Downloads. Move it to the repo root, then tell the agent to read the feedback.');
});

// Flip: notes live on the back of the card the render is on.
for(const c of cards){
  for(const b of c.querySelectorAll('.flipbtn')){
    b.addEventListener('click',e=>{
      e.stopPropagation();
      c.classList.toggle('flipped');
      if(c.classList.contains('flipped')){
        const ta=c.querySelector('textarea.note'); if(ta) setTimeout(()=>ta.focus(),320);
      }
    });
  }
}
function marks(){
  for(const c of cards){
    const ta=c.querySelector('textarea.note');
    const b=c.querySelector('.face.front .flipbtn');
    if(!ta||!b)continue;
    const has=!!ta.value.trim();
    b.classList.toggle('has',has);
    b.textContent=has?'Notes *':'Notes';
  }
}
for(const n of notes) n.addEventListener('input',marks);

// Filters toggle. Collapsed by default at EVERY width now: 74 tags took five
// rows of a desktop screen, so the page opened on its own chrome. The choice is
// still remembered per browser, so anyone who prefers it open keeps it open.
//
// The storage key is VERSIONED. Changing a default is invisible to every
// browser that already stored the old preference, which is everyone who has
// opened this page before, so without the bump the change ships to nobody who
// would notice it. Bump it again if the default changes again.
const bar=document.querySelector('.tagbar');
const tf=document.getElementById('togglefilters');
const fcount=document.getElementById('filtercount');
const saved=localStorage.getItem('si-filters-open-v2');
function setFilters(open){
  bar.classList.toggle('open',open);
  tf.setAttribute('aria-pressed',open?'true':'false');
  tf.setAttribute('aria-expanded',open?'true':'false');
  localStorage.setItem('si-filters-open-v2',open?'1':'0');
}
// Collapsing must not hide state: with the wall shut, this button is the only
// thing left saying a filter is on. Show the active count, fall back to total.
// NB: JS is a plain string, not an f-string, so nothing here may use Python
// brace substitution. The total comes from the DOM for that reason.
const nTags=document.querySelectorAll('.chip[data-tag]').length;
function filterBadge(){
  const n=active.size;
  fcount.textContent=n?String(n):String(nTags);
  tf.classList.toggle('filtered',n>0);
  tf.title=n?(n+' filter'+(n===1?'':'s')+' active'):'Show tag filters';
}
setFilters(saved==='1');
filterBadge();
tf.addEventListener('click',()=>setFilters(!bar.classList.contains('open')));

// "With notes": jump straight to what has been reviewed.
const nb=document.getElementById('notesonly');
nb.addEventListener('click',()=>{
  notesOnly=!notesOnly;
  nb.setAttribute('aria-pressed',notesOnly?'true':'false');
  apply();
});

document.getElementById('clearall').addEventListener('click',()=>{
  active.clear(); notesOnly=false; search.value='';
  for(const b of document.querySelectorAll('.chip[data-tag]')) b.setAttribute('aria-pressed','false');
  nb.setAttribute('aria-pressed','false');
  apply();filterBadge();
});

// Tapping the poster on a phone should not require hitting a small button.
for(const c of cards){
  const back=c.querySelector('.face.back');
  if(back) back.addEventListener('dblclick',()=>c.classList.remove('flipped'));
}
marks();
count();
apply();
"""


def build(refresh: bool) -> int:
    if not OUTPUTS.exists():
        print(f"no outputs directory at {OUTPUTS}", file=sys.stderr)
        return 1

    configs = load_configs()
    feedback = load_feedback()
    videos = sorted(
        (p for p in OUTPUTS.rglob("*.mp4") if "_gallery" not in p.parts and "archive" not in p.parts),
        key=lambda p: generated_at(p)[0], reverse=True,
    )

    cards: list[str] = []
    all_tags: dict[str, int] = {}

    for video in videos:
        info = ffprobe(video)
        if not info:
            print(f"  skipped (unreadable): {rel(video)}")
            continue
        cfg, run = metadata_for(video, configs)
        tags = tags_for(video, info, cfg)
        for t in tags:
            all_tags[t] = all_tags.get(t, 0) + 1
        poster = poster_for(video, info, refresh)
        playable = preview_for(video, info) or video

        style = cfg.get("style") or {}
        subject = cfg.get("subject") or {}
        prompts = subject.get("prompts") or []

        spec_html = ""
        comp = compliance(info)
        if comp:
            kind, msg = comp
            spec_html = f'<div class="badge {kind}">{html.escape(msg)}</div>'

        rows = [
            ("size", f"{info['width']} x {info['height']}"),
            ("frames", f"{info['frames']} @ {info['fps']:g} fps"),
            ("duration", f"{info['duration']:.3f} s"),
            ("codec", f"{info['codec']} {info['pix_fmt']}"),
            ("file", human_size(info["size"])
             + (" (web proxy for playback)" if playable != video else "")),
        ]
        if style.get("lora_scale") is not None:
            rows.append(("lora", f"{style.get('name', '?')} @ {style['lora_scale']}"))
        rows.extend(variant_rows(cfg))
        if run.get("gpu"):
            rows.append(("gpu", str(run["gpu"])))
        if run.get("cost_usd") is not None:
            rows.append(("cost", f"${run['cost_usd']}"))
        gen_ts, exact = generated_at(video)
        stamp = datetime.fromtimestamp(gen_ts).strftime("%Y-%m-%d %H:%M")
        rows.append(("generated" if exact else "file date (no manifest)", stamp))

        specs = "".join(
            f"<dt>{html.escape(k)}</dt><dd>{html.escape(str(v))}</dd>" for k, v in rows
        )

        prompt_html = ""
        for p in prompts:
            if not isinstance(p, dict):
                continue
            prompt_html += (
                '<div class="prompt">'
                f'<div class="lbl">{html.escape(str(p.get("label", "")))}</div>'
                f'<div class="txt">{html.escape(str(p.get("prompt", "")).strip())}</div>'
                "</div>"
            )
        if style.get("prefix"):
            prompt_html = (
                f'<div class="neg"><b>prefix</b> {html.escape(str(style["prefix"]))}</div>'
                + prompt_html
            )
        if style.get("negative_prompt"):
            prompt_html += (
                f'<div class="neg"><b>negative</b> {html.escape(str(style["negative_prompt"]))}</div>'
            )
        if cfg.get("__config_path"):
            prompt_html += (
                f'<div class="neg"><b>config</b> {html.escape(cfg["__config_path"])}</div>'
            )
        if not prompt_html:
            prompt_html = '<div class="neg">No config or manifest found for this render.</div>'

        tag_html = "".join(
            f'<span class="{"style" if t in STYLE_TAGS.values() else ""}">{html.escape(t)}</span>'
            for t in tags
        )
        media = (
            f'<img src="{html.escape(rel(poster))}" alt="poster frame" loading="lazy">'
            if poster else '<div style="padding:50px;color:#a2917f">no poster</div>'
        )
        searchable = " ".join([
            video.stem, rel(video), " ".join(tags),
            " ".join(str(p.get("prompt", "")) for p in prompts if isinstance(p, dict)),
        ]).lower()

        cards.append(f"""
<article class="card" data-tags="{html.escape('|'.join(tags))}" data-search="{html.escape(searchable)}">
 <div class="flipper">
  <div class="face front">
  <div class="media" data-src="{html.escape(rel(playable))}" title="Click to play">{media}</div>
  <div class="body">
    <div class="name">{html.escape(video.stem)}</div>
    <div class="path">{html.escape(rel(video))}</div>
    <div class="tags">{tag_html}</div>
    {spec_html}
    <details class="specs-d"><summary>{info['width']}x{info['height']} &middot; {info['duration']:.1f} s &middot; {human_size(info["size"])}</summary>
      <dl class="specs">{specs}</dl>
    </details>
    <details><summary>Generation info</summary>{prompt_html}</details>
    <div class="dlrow">
      <a class="dl" href="{html.escape(rel(video))}" download="{html.escape(video.name)}"
         title="Full quality original">Download {human_size(info["size"])}</a>
      {f'<a class="dl light" href="{html.escape(rel(playable))}" download="{html.escape(playable.name)}" title="Small web version">Small {human_size(playable.stat().st_size)}</a>' if playable != video else ''}
      <button class="flipbtn" title="Notes">Notes{" *" if feedback.get(video.stem) else ""}</button>
    </div>
  </div>
  </div>
  <div class="face back">
    <div class="backhead">{html.escape(video.stem)}</div>
    <textarea class="note" data-key="{html.escape(video.stem)}"
      placeholder="Feedback on this render...">{html.escape(feedback.get(video.stem, ""))}</textarea>
    <button class="flipbtn back">Back</button>
  </div>
 </div>
</article>""")

    # Still sets. A directory of PNGs becomes ONE card with a scrollable strip,
    # not one card per image; a 5-rung ladder at 7 keyframes each would otherwise
    # bury the page under 35 cards. First and last frame are called out because
    # that pair is what shows whether quality survives the chain.
    for d, pngs in sorted(png_dirs(), key=lambda kv: -kv[1][0].stat().st_mtime):
        # Phase A writes to `<staging>/<subject>/keyframes/`, so the directory
        # holding the PNGs is called `keyframes` for every render in the repo.
        # Identity (card title, config lookup) belongs to its parent.
        ident = d.parent if d.name in {"keyframes", "frames", "images"} else d
        title = "/".join(ident.relative_to(OUTPUTS).parts) if ident != OUTPUTS else ident.name

        cfg, run = metadata_for(ident, configs)
        w, h = png_size(pngs[0])
        tags = ["stills"] + tags_for(d, {"width": w, "height": h}, cfg)
        for t in tags:
            all_tags[t] = all_tags.get(t, 0) + 1

        style = cfg.get("style") or {}
        rows = [("images", f"{len(pngs)} PNG" + (f" @ {w}x{h}" if w else ""))]
        if style.get("lora_scale") is not None:
            rows.append(("lora", f"{style.get('name', '?')} @ {style['lora_scale']}"))
        rows.extend(variant_rows(cfg))
        rows.append((
            "modified",
            datetime.fromtimestamp(pngs[0].stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        ))
        specs = "".join(
            f"<dt>{html.escape(k)}</dt><dd>{html.escape(str(v))}</dd>" for k, v in rows
        )

        strip = "".join(
            f'<figure><a href="{html.escape(rel(p))}" target="_blank">'
            f'<img src="{html.escape(rel(p))}" loading="lazy" alt="{html.escape(p.stem)}">'
            f'</a><figcaption>{html.escape(p.stem)}'
            f'{" (first)" if i == 0 else " (last)" if i == len(pngs) - 1 else ""}'
            "</figcaption></figure>"
            for i, p in enumerate(pngs)
        )
        cards.append(f"""
<article class="card stills" data-tags="{html.escape('|'.join(tags))}" data-search="{html.escape((title + ' ' + str(d) + ' ' + ' '.join(tags)).lower())}">
 <div class="flipper">
  <div class="face front">
  <div class="body">
    <div class="name">{html.escape(title)}</div>
    <div class="path">{html.escape(rel(d))}</div>
    <div class="tags">{"".join(f'<span>{html.escape(t)}</span>' for t in tags)}</div>
    <details class="specs-d"><summary>{len(pngs)} images{f" &middot; {w}x{h}" if w else ""}</summary>
      <dl class="specs">{specs}</dl>
    </details>
    <button class="flipbtn" title="Notes">Notes{" *" if feedback.get(title) else ""}</button>
  </div>
  <div class="strip">{strip}</div>
  </div>
  <div class="face back">
    <div class="backhead">{html.escape(title)}</div>
    <textarea class="note" data-key="{html.escape(title)}"
      placeholder="Feedback on this set...">{html.escape(feedback.get(title, ""))}</textarea>
    <button class="flipbtn back">Back</button>
  </div>
 </div>
</article>""")

    tagbar = "".join(
        f'<button class="chip" data-tag="{html.escape(t)}" aria-pressed="false">{html.escape(t)}<span class="n">{n}</span></button>'
        for t, n in sorted(all_tags.items(), key=lambda kv: (-kv[1], kv[0]))
    )
    n_tags = len(all_tags)
    built = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")

    PAGE.write_text(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>slow-interpolation outputs</title>
<style>{CSS}</style></head><body>
<header>
  <h1>slow-interpolation outputs</h1>
  <div class="sub">Tap a still to play. Tap <b>Notes</b> to flip a card over.
    <span id="count"></span></div>
  <div class="controls">
    <input type="search" id="q" placeholder="Search name or prompt...">
  </div>
  <div class="controls">
    <button class="chip" id="togglefilters" aria-pressed="false" aria-expanded="false"
            aria-controls="tagbar">Filters<span class="n" id="filtercount">{n_tags}</span><span class="caret">&#9660;</span></button>
    <button class="chip" id="notesonly" aria-pressed="false">With notes<span class="n" id="notecount"></span></button>
    <button class="chip" id="clearall">Clear</button>
    <button class="chip" id="export">Save feedback</button>
  </div>
  <div class="tagbar" id="tagbar">{tagbar}</div>
</header>
<main>{''.join(cards)}<div class="empty" id="empty" style="display:none">Nothing matches those filters.</div></main>
<footer>Built {built} by tools/gallery.py. Rebuild after new renders.</footer>
<script>{JS}</script></body></html>""", encoding="utf-8")

    print(f"{len(cards)} renders indexed -> {rel(PAGE)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--open", action="store_true", help="open the page after building")
    ap.add_argument("--refresh", action="store_true", help="re-extract cached posters")
    args = ap.parse_args()
    rc = build(args.refresh)
    if rc == 0 and args.open:
        webbrowser.open(PAGE.as_uri())
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
