"""
Slow Interpolation Media Engine -- ingest pipeline (Demo 1: local folder -> Cloudflare R2).

Importable module (serve.py runs it on a daemon thread) AND headless CLI
(the agent-facing path):

    py -3.11 tools/media-engine/ingest.py \
        --source knowledge/operations/drafts/lake-press-kit/assets \
        --edition nyc-billboard --prefix nyc-billboard/_preview/bla-lake \
        --asset-class press-kit --artists example-artist \
        [--context bla-lake] [--sample 2] --yes

Stages per file:
  discovered -> checksum -> dedupe -> uploading -> verified -> thumbnailed
             -> captioned -> embedded -> catalogued
Terminal alternates: duplicate, quarantined(reason), excluded.

Ledger invariant (enforced, shown in UI):
  discovered == catalogued + quarantined + duplicates + excluded + in_pipeline

Design doc: docs/architecture.md
"""

import argparse
import io
import json
import os
import re
import shutil
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
TOOLS_DIR = ENGINE_DIR.parent
REPO_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))

import media_store  # noqa: E402  (tools/media_store.py)

CACHE_DIR = ENGINE_DIR / "cache"
THUMBS_DIR = CACHE_DIR / "thumbs"
RUNS_DIR = ENGINE_DIR / "runs"
STATE_PATH = CACHE_DIR / "run-state.json"
REPORT_DIR = REPO_ROOT / "knowledge" / "operations" / "media-ingest"

CAPTION_MODEL = "gemini-flash-latest"  # alias tracks current flash (2.0-flash was retired mid-2026)
EMBED_MODEL = "gemini-embedding-2-preview"
EMBED_DIMS = 768
LANCE_DB_PATH = TOOLS_DIR / "data" / "media-vectors"
LANCE_TABLE = "kb_media"

# rough gemini-2.0-flash pricing, EUR (input/output per 1M tokens at ~0.92 EUR/USD)
PRICE_IN_PER_M = 0.10 * 0.92
PRICE_OUT_PER_M = 0.40 * 0.92

MEDIA_TYPE_BY_EXT = {
    ".jpg": "photo", ".jpeg": "photo", ".png": "photo", ".webp": "photo",
    ".mp4": "video", ".mov": "video", ".webm": "video",
    ".pdf": "document", ".docx": "document", ".doc": "document", ".txt": "document",
}

PIPELINE_STATES = ["discovered", "checksum", "uploading", "verified",
                   "thumbnailed", "captioned", "embedded", "catalogued"]

ARTWORK_CONF_THRESHOLD = 0.75

CAPTION_PROMPT = (
    "You are cataloguing media for Slow Interpolation. "
    "Analyse this image and answer with STRICT JSON only, no prose, no code fences:\n"
    '{"caption": "<one factual sentence describing what the image shows>", '
    '"scene": ["<2-5 short lowercase scene tags, e.g. install-shot, led-wall, portrait, render, exhibition-crowd>"], '
    '"artwork_guess": "<name of the artwork shown if identifiable, else empty string>", '
    '"artwork_confidence": <0.0-1.0>}\n'
    "Context: these assets relate to the artist(s) {artists} "
    "and known artwork(s) {artworks}. If the image clearly shows one of those "
    "artworks, name it; do not invent other artwork names."
)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_hms():
    return time.strftime("%H:%M:%S")


def ascii_safe(text):
    return str(text).encode("ascii", "replace").decode("ascii")


# ================================================================ RunState

class RunState:
    """In-memory run state, atomically persisted to cache/run-state.json."""

    def __init__(self, state_path=STATE_PATH):
        self.state_path = Path(state_path)
        self.lock = threading.Lock()
        self.data = {
            "run_id": datetime.now().strftime("%Y%m%d-%H%M%S"),
            "phase": "idle",
            "providers": {"caption": "unknown", "embed": "unknown",
                          "face": "skipped:no-gallery-enrolled"},
            "preflight": [],
            "batch": {},
            "counts": {},
            "cost": {"caption_calls": 0, "embed_calls": 0,
                     "tokens_in": 0, "tokens_out": 0,
                     "eur_actual": 0.0, "eur_full_run_estimate": None},
            "files": [],
            "log": [],
            "report_path": None,
            "error": None,
            "updated": now_iso(),
        }

    # ---- logging ----
    def log(self, line):
        line = f"{now_hms()} {ascii_safe(line)}"
        with self.lock:
            self.data["log"].append(line)
            if len(self.data["log"]) > 400:
                self.data["log"] = self.data["log"][-400:]
        print(line, flush=True)
        self.write()

    # ---- counts / ledger ----
    def refresh_counts(self):
        files = self.data["files"]
        catalogued = sum(1 for f in files if f["state"] == "catalogued")
        duplicates = sum(1 for f in files if f["state"] == "duplicate")
        quarantined = sum(1 for f in files if f["state"] == "quarantined")
        excluded = sum(1 for f in files if f["state"] == "excluded")
        discovered = len(files)
        in_pipeline = discovered - catalogued - duplicates - quarantined - excluded
        self.data["counts"] = {
            "discovered": discovered, "catalogued": catalogued,
            "duplicates": duplicates, "quarantined": quarantined,
            "excluded": excluded, "in_pipeline": in_pipeline,
            "balanced": in_pipeline >= 0,
        }

    # ---- persistence (atomic, OneDrive-retry) ----
    def write(self):
        with self.lock:
            self.refresh_counts()
            self.data["updated"] = now_iso()
            payload = json.dumps(self.data, indent=1, ensure_ascii=False)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".json.tmp")
        for attempt in range(3):
            try:
                tmp.write_text(payload, encoding="utf-8")
                os.replace(tmp, self.state_path)
                return
            except PermissionError:
                time.sleep(0.3 * (attempt + 1))
        # last resort: non-atomic write beats losing state
        try:
            self.state_path.write_text(payload, encoding="utf-8")
        except Exception:
            pass

    def set_phase(self, phase):
        self.data["phase"] = phase
        self.write()

    def file_by_id(self, file_id):
        for f in self.data["files"]:
            if f["id"] == file_id:
                return f
        return None


# ================================================================ scan / preflight

def scan_source(source_dir, state, batch):
    """Walk the source folder into intake file entries."""
    source_dir = Path(source_dir)
    if not source_dir.is_dir():
        raise SystemExit(f"source folder not found: {source_dir}")
    entries = []
    idx = 0
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        name = path.name
        # Skip hidden files + our internal sidecar/derived files. Do NOT skip all
        # "_"-prefixed names: camera exports use them (_DSF1234.jpg = Fujifilm).
        if name.startswith(".") or name.lower() in ("_sources.md",) or name.startswith(("_manifest", "_catalogue", "_contact-sheet", "_planner")):
            continue
        ext = path.suffix.lower()
        media_type = MEDIA_TYPE_BY_EXT.get(ext)
        if media_type is None:
            continue
        idx += 1
        rel = path.relative_to(source_dir).as_posix()
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", name)
        key = f"{batch['prefix']}/{media_type}/{safe_name}"
        entries.append({
            "id": f"f{idx:02d}",
            "name": name,
            "rel": rel,
            "path": str(path),
            "bytes": path.stat().st_size,
            "media_type": media_type,
            "state": "discovered",
            "states_done": ["discovered"],
            "key": key,
            "sha256": None,
            "date": None,
            "date_basis": None,
            "thumb": None,
            "caption": None,
            "scene": [],
            "artworks": [],
            "error": None,
            "retryable": False,
        })
    state.data["files"] = entries
    state.data["batch"] = batch
    state.log(f"[scan] {len(entries)} files discovered in {source_dir}")
    state.set_phase("intake")
    return entries


class Ctx:
    """Shared per-run context: clients, remote manifest sha-index, config."""

    def __init__(self, state):
        self.state = state
        self.env = media_store.load_env()
        self.r2 = None
        self.gemini = None
        self.openai_key = None
        self.caption_provider = "none"
        self.embed_provider = "none"
        self.known_sha = {}     # sha256 -> existing key (from remote manifest)
        self.known_keys = {}    # key -> sha256
        self.lance_db = None
        self.catalogue = None   # local working catalogue dict


def preflight(ctx):
    """Environment + connectivity checks. Each check is a console line."""
    st = ctx.state
    checks = []

    def check(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": ascii_safe(detail)})
        st.log(f"[preflight] {'OK  ' if ok else 'FAIL'} {name}: {detail}")
        return ok

    # interpreter deps
    try:
        import boto3  # noqa: F401
        check("boto3", True, "importable")
    except ImportError:
        check("boto3", False, "missing -- run: py -3.11 -m pip install boto3")
    try:
        import lancedb  # noqa: F401
        check("lancedb", True, "importable")
    except ImportError:
        check("lancedb", False, "missing -- embeddings will be skipped")
    try:
        from PIL import Image  # noqa: F401
        check("pillow", True, "importable")
    except ImportError:
        check("pillow", False, "missing -- thumbnails will be skipped")
    check("ffmpeg", shutil.which("ffmpeg") is not None,
          "present (unused this run: no videos in batch)" if shutil.which("ffmpeg")
          else "not on PATH (only needed for the future video lane)")

    # R2
    missing = media_store.missing_r2_keys(ctx.env)
    if missing:
        check("r2-credentials", False, "missing " + ", ".join(missing))
    else:
        check("r2-credentials", True, "all 4 vars present in env")
        ok, msg = media_store.check_connection(ctx.env, quiet=True)
        if check("r2-bucket", ok, msg):
            ctx.r2 = media_store.r2_client(ctx.env)

    # Gemini probe (council.py pattern), OpenAI fallback
    gem_key = ctx.env.get("GEMINI_API_KEY") or ctx.env.get("GOOGLE_API_KEY")
    if gem_key:
        try:
            from google import genai
            client = genai.Client(api_key=gem_key)
            client.models.generate_content(model=CAPTION_MODEL, contents="ping")
            ctx.gemini = client
            ctx.caption_provider = "gemini"
            ctx.embed_provider = "gemini"
            check("gemini", True, f"{CAPTION_MODEL} reachable")
        except Exception as e:
            check("gemini", False, f"probe failed ({ascii_safe(e)[:90]})")
    else:
        check("gemini", False, "no GEMINI_API_KEY")

    if ctx.caption_provider == "none":
        oa_key = ctx.env.get("OPENAI_API_KEY")
        if oa_key:
            ctx.openai_key = oa_key
            ctx.caption_provider = "openai"
            check("openai-fallback", True, "gpt-4o-mini vision will caption")
        else:
            check("openai-fallback", False, "no OPENAI_API_KEY -- captions skipped")

    st.data["providers"]["caption"] = ctx.caption_provider
    st.data["providers"]["embed"] = ctx.embed_provider
    st.data["preflight"] = checks
    st.write()

    # remote manifest -> dedupe index + local working catalogue
    if ctx.r2 is not None:
        edition = st.data["batch"]["edition"]
        try:
            manifest = media_store.read_manifest(edition, ctx.r2, ctx.env)
            for a in manifest.get("assets", []):
                if a.get("sha256"):
                    ctx.known_sha[a["sha256"]] = a["key"]
                ctx.known_keys[a["key"]] = a.get("sha256")
            ctx.catalogue = media_store.read_catalogue(edition, ctx.r2, ctx.env)
            st.log(f"[preflight] remote manifest: {len(ctx.known_sha)} known assets in {edition}")
        except Exception as e:
            st.log(f"[preflight] WARN could not read remote manifest: {ascii_safe(e)[:120]}")
            ctx.catalogue = {"edition": edition, "generated": "", "assets": []}

    return all(c["ok"] for c in checks if c["name"] in ("boto3", "r2-credentials", "r2-bucket"))


# ================================================================ stages

def _advance(entry, state_obj, new_state):
    entry["state"] = new_state
    if new_state in PIPELINE_STATES and new_state not in entry["states_done"]:
        entry["states_done"].append(new_state)
    state_obj.write()


def _quarantine(entry, state_obj, reason, retryable=True):
    entry["state"] = "quarantined"
    entry["error"] = ascii_safe(reason)
    entry["retryable"] = retryable
    state_obj.log(f"[quarantine] {entry['id']} {entry['name']}: {reason}")


def stage_checksum(entry, ctx):
    st = ctx.state
    _advance(entry, st, "checksum")
    entry["sha256"] = media_store.sha256_file(entry["path"])
    # EXIF date for photos, mtime fallback for everything
    date, basis = None, "mtime"
    if entry["media_type"] == "photo":
        try:
            from PIL import Image
            with Image.open(entry["path"]) as im:
                exif = im.getexif()
                raw = exif.get(36867) or exif.get(306)  # DateTimeOriginal, DateTime
                if not raw:
                    # Pillow >= 10 getexif() returns IFD0 only; DateTimeOriginal (36867)
                    # lives in the Exif sub-IFD (0x8769). Without this, every photo whose
                    # camera omits IFD0/DateTime silently falls back to mtime -- which for
                    # a freshly unzipped delivery is the DOWNLOAD date, not the shoot date.
                    try:
                        raw = exif.get_ifd(0x8769).get(36867)
                    except Exception:
                        raw = None
                if raw:
                    date = str(raw)[:10].replace(":", "-")
                    basis = "exif"
        except Exception:
            pass
    elif entry["media_type"] == "video":
        # Same failure as the photo branch above, different container: a video's real
        # shoot date is in the MP4/MOV metadata (`format.tags.creation_time`), and
        # without reading it every video falls to mtime -- the DOWNLOAD date for any
        # delivery that arrived as a zip. Measured on the Save the Cut REAL-TIME set:
        # 133 of 133 carry creation_time 2026-07-10 while mtime said 2026-07-23.
        try:
            import subprocess  # local import, matching stage_thumb below
            probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", entry["path"]],
                capture_output=True, text=True, timeout=60,
            )
            tags = (json.loads(probe.stdout).get("format", {}) or {}).get("tags", {}) or {}
            raw = tags.get("creation_time") or tags.get("com.apple.quicktime.creationdate")
            if raw:
                date = str(raw)[:10]
                basis = "container"
        except Exception:
            pass
    if not date:
        date = datetime.fromtimestamp(os.path.getmtime(entry["path"])).strftime("%Y-%m-%d")
    entry["date"], entry["date_basis"] = date, basis
    mb = entry["bytes"] / 1024 / 1024
    st.log(f"[checksum] {entry['id']} sha256 {entry['sha256'][:12]}... ({mb:.1f} MB, date {date} via {basis})")
    return True


def stage_dedupe(entry, ctx):
    st = ctx.state
    existing_key = ctx.known_sha.get(entry["sha256"])
    if existing_key:
        entry["state"] = "duplicate"
        entry["error"] = f"identical content already stored as {existing_key}"
        st.log(f"[dedupe] {entry['id']} duplicate of {existing_key} -- skipping")
        return False
    known_sha_for_key = ctx.known_keys.get(entry["key"])
    if known_sha_for_key and known_sha_for_key != entry["sha256"]:
        _quarantine(entry, st, f"key conflict: {entry['key']} exists with different content", retryable=False)
        return False
    return True


def stage_upload(entry, ctx):
    st = ctx.state
    _advance(entry, st, "uploading")
    st.log(f"[upload] {entry['id']} -> r2://{media_store.bucket_name(ctx.env)}/{entry['key']}")
    # Large files on a fragile line: retry the whole transfer up to 3 times
    # (fresh connections) before quarantining. Small files keep one attempt +
    # boto3's internal retries.
    attempts = 3 if entry["bytes"] > 100 * 1024 * 1024 else 1
    last_err = None
    for attempt in range(1, attempts + 1):
        try:
            media_store.upload(entry["path"], entry["key"], sha256=entry["sha256"],
                               verify=True, client=ctx.r2, env=ctx.env)
            last_err = None
            break
        except Exception as e:
            last_err = e
            if attempt < attempts:
                st.log(f"[upload] {entry['id']} attempt {attempt} failed ({ascii_safe(e)[:80]}) -- retrying in 30s")
                time.sleep(30)
                try:  # fresh client: a poisoned connection pool can wedge retries
                    ctx.r2 = media_store.r2_client(ctx.env)
                except Exception:
                    pass
    if last_err is not None:
        _quarantine(entry, st, f"upload/verify failed after {attempts} attempt(s): {ascii_safe(last_err)[:120]}")
        return False
    _advance(entry, st, "verified")
    st.log(f"[verify] {entry['id']} size + sha256 match remote")
    return True


def _video_poster(entry, ctx):
    """ffmpeg keyframe poster for video assets (graceful-skip on failure)."""
    st = ctx.state
    if shutil.which("ffmpeg") is None:
        st.log(f"[thumb] {entry['id']} skipped: ffmpeg not available")
        return
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    thumb_name = f"{entry['sha256'][:16]}.jpg"
    thumb_path = THUMBS_DIR / thumb_name
    import subprocess
    cmd = ["ffmpeg", "-y", "-ss", "3", "-i", entry["path"], "-frames:v", "1",
           "-vf", "scale=512:-2", "-q:v", "4", str(thumb_path)]
    try:
        subprocess.run(cmd, capture_output=True, timeout=120, check=True)
    except Exception:
        # frame at 3s may not exist for very short clips: retry at 0
        try:
            cmd[3] = "0"
            subprocess.run(cmd, capture_output=True, timeout=120, check=True)
        except Exception as e:
            st.log(f"[thumb] {entry['id']} WARN poster failed: {ascii_safe(e)[:90]} -- continuing")
            return
    entry["thumb"] = f"/thumbs/{thumb_name}"
    try:
        media_store.upload(thumb_path, f"thumbs/{entry['key']}", verify=False,
                           client=ctx.r2, env=ctx.env)
    except Exception as e:
        st.log(f"[thumb] {entry['id']} WARN r2 poster upload failed: {ascii_safe(e)[:90]}")
    st.log(f"[thumb] {entry['id']} video poster frame cached + pushed")


def stage_thumbnail(entry, ctx):
    st = ctx.state
    if entry["media_type"] == "video":
        _video_poster(entry, ctx)
        _advance(entry, st, "thumbnailed")
        return True
    if entry["media_type"] != "photo":
        st.log(f"[thumb] {entry['id']} skipped: {entry['media_type']}")
        _advance(entry, st, "thumbnailed")
        return True
    try:
        from PIL import Image
        THUMBS_DIR.mkdir(parents=True, exist_ok=True)
        thumb_name = f"{entry['sha256'][:16]}.jpg"  # flat-hashed (OneDrive path limits)
        thumb_path = THUMBS_DIR / thumb_name
        with Image.open(entry["path"]) as im:
            im = im.convert("RGB")
            im.thumbnail((512, 512))
            im.save(thumb_path, "JPEG", quality=82)
        entry["thumb"] = f"/thumbs/{thumb_name}"
        # derived copy to R2 so the library works from anywhere later
        try:
            media_store.upload(thumb_path, f"thumbs/{entry['key']}", verify=False,
                               client=ctx.r2, env=ctx.env)
        except Exception as e:
            st.log(f"[thumb] {entry['id']} WARN r2 thumb upload failed: {ascii_safe(e)[:90]}")
        st.log(f"[thumb] {entry['id']} 512px thumbnail cached + pushed")
    except Exception as e:
        st.log(f"[thumb] {entry['id']} WARN thumbnail failed: {ascii_safe(e)[:90]} -- continuing")
    _advance(entry, st, "thumbnailed")
    return True


def _parse_caption_json(text):
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    return json.loads(text)


def _caption_gemini(entry, ctx, prompt):
    from google.genai import types
    src = entry.get("_caption_path") or entry["path"]
    with open(src, "rb") as f:
        data = f.read()
    part = types.Part.from_bytes(data=data, mime_type=media_store.guess_content_type(src))
    resp = ctx.gemini.models.generate_content(model=CAPTION_MODEL, contents=[part, prompt])
    usage = getattr(resp, "usage_metadata", None)
    if usage:
        cost = ctx.state.data["cost"]
        cost["tokens_in"] += getattr(usage, "prompt_token_count", 0) or 0
        cost["tokens_out"] += getattr(usage, "candidates_token_count", 0) or 0
        cost["eur_actual"] = round(
            cost["tokens_in"] / 1e6 * PRICE_IN_PER_M
            + cost["tokens_out"] / 1e6 * PRICE_OUT_PER_M, 6)
    return resp.text


def _caption_openai(entry, ctx, prompt):
    import base64
    import urllib.request
    src = entry.get("_caption_path") or entry["path"]
    with open(src, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    mime = media_store.guess_content_type(src)
    body = json.dumps({
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]}],
        "max_tokens": 300,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {ctx.openai_key}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"]


def stage_caption(entry, ctx):
    st = ctx.state
    # Videos are captioned from their poster frame (generated in stage_thumbnail):
    # one cheap image call gives caption + scene tags so clips are choosable
    # from the catalogue without downloading gigabytes (usage feedback 2026-07-22).
    caption_path = entry["path"]
    if entry["media_type"] == "video":
        if entry.get("thumb"):
            poster = THUMBS_DIR / Path(entry["thumb"]).name
            if poster.is_file():
                caption_path = str(poster)
            else:
                st.log(f"[caption] {entry['id']} skipped: poster missing")
                _advance(entry, st, "captioned")
                return True
        else:
            st.log(f"[caption] {entry['id']} skipped: no poster frame")
            _advance(entry, st, "captioned")
            return True
    elif entry["media_type"] != "photo":
        st.log(f"[caption] {entry['id']} skipped: {entry['media_type']}")
        _advance(entry, st, "captioned")
        return True
    entry["_caption_path"] = caption_path
    if ctx.caption_provider == "none":
        entry["caption"] = ""
        st.log(f"[caption] {entry['id']} skipped: no provider")
        _advance(entry, st, "captioned")
        return True

    batch = st.data["batch"]
    known_artworks = batch.get("known_artworks", [])
    # .replace, not .format: the prompt body contains literal JSON braces
    prompt = (CAPTION_PROMPT
              .replace("{artists}", ", ".join(batch.get("artists", []) or ["unknown"]))
              .replace("{artworks}", ", ".join(known_artworks) or "none on record"))

    parsed = None
    for attempt in range(2):
        try:
            if ctx.caption_provider == "gemini":
                raw = _caption_gemini(entry, ctx, prompt)
            else:
                raw = _caption_openai(entry, ctx, prompt)
            st.data["cost"]["caption_calls"] += 1
            parsed = _parse_caption_json(raw)
            break
        except json.JSONDecodeError:
            if attempt == 0:
                prompt += "\nREMINDER: reply with the JSON object ONLY."
                continue
            entry["caption"] = ascii_safe(raw)[:280] if "raw" in dir() else ""
            st.log(f"[caption] {entry['id']} JSON parse failed twice -- kept raw text")
        except Exception as e:
            st.log(f"[caption] {entry['id']} WARN provider error: {ascii_safe(e)[:110]} -- continuing untagged")
            break

    if parsed:
        entry["caption"] = ascii_safe(parsed.get("caption", ""))[:400]
        entry["scene"] = [ascii_safe(s).lower() for s in (parsed.get("scene") or [])][:6]
        guess = (parsed.get("artwork_guess") or "").strip()
        conf = float(parsed.get("artwork_confidence") or 0)
        entry["_gemini_artwork"] = {"guess": guess, "confidence": conf}
        st.log(f"[caption] {entry['id']} \"{entry['caption'][:70]}\" scene={','.join(entry['scene'])}"
               + (f" artwork_guess={guess} ({conf:.2f})" if guess else ""))
    _advance(entry, st, "captioned")
    return True


def stage_embed(entry, ctx):
    st = ctx.state
    if entry["media_type"] != "photo" or ctx.embed_provider != "gemini":
        reason = entry["media_type"] if entry["media_type"] != "photo" else "provider unavailable"
        st.log(f"[embed] {entry['id']} skipped: {reason}")
        _advance(entry, st, "embedded")
        return True
    try:
        from google.genai import types
        import lancedb
        with open(entry["path"], "rb") as f:
            data = f.read()
        part = types.Part.from_bytes(data=data, mime_type=media_store.guess_content_type(entry["path"]))
        result = ctx.gemini.models.embed_content(
            model=EMBED_MODEL, contents=part,
            config={"output_dimensionality": EMBED_DIMS})
        vector = result.embeddings[0].values
        st.data["cost"]["embed_calls"] += 1
        if ctx.lance_db is None:
            ctx.lance_db = lancedb.connect(str(LANCE_DB_PATH))
        batch = st.data["batch"]
        record = {
            "file_path": entry["key"],  # R2 key = durable identity
            "filename": entry["name"],
            "media_type": "image",
            "entity_slug": (batch.get("artists") or [""])[0],
            "entity_type": "media-store",
            "size_mb": float(entry["bytes"] / 1024 / 1024),
            "text_content": f"{entry['name']} ({entry.get('caption') or 'no caption'})",
            "last_modified": float(time.time()),
            "vector": vector,
        }
        try:
            table = ctx.lance_db.open_table(LANCE_TABLE)
            table.delete(f"file_path = '{entry['key']}'")  # idempotent re-embed
            table.add([record])
        except Exception:
            ctx.lance_db.create_table(LANCE_TABLE, [record])
        st.log(f"[embed] {entry['id']} 768d vector -> {LANCE_TABLE}")
    except Exception as e:
        st.log(f"[embed] {entry['id']} WARN embed failed: {ascii_safe(e)[:110]} -- continuing")
    _advance(entry, st, "embedded")
    return True


def build_tags(entry, ctx):
    batch = ctx.state.data["batch"]
    artworks = []
    # deterministic: filename mentions a known artwork slug fragment
    for aw in batch.get("known_artworks", []):
        fragment = aw.split("/")[-1].replace("example-artist-", "")
        if fragment and fragment.lower() in entry["name"].lower():
            artworks.append({"slug": aw, "confidence": 0.98,
                             "status": "confirmed", "basis": "filename"})
    # gemini corroboration / new guess
    gem = entry.pop("_gemini_artwork", None)
    if gem and gem["guess"]:
        slug_guess = re.sub(r"[^a-z0-9]+", "-", gem["guess"].lower()).strip("-")
        matched = False
        for aw in artworks:
            if slug_guess and (slug_guess in aw["slug"] or aw["slug"].endswith(slug_guess)):
                aw["basis"] = "filename+gemini"
                matched = True
        if not matched and slug_guess:
            status = "confirmed" if gem["confidence"] >= ARTWORK_CONF_THRESHOLD else "pending"
            # unknown-to-KB artwork names always go to review, whatever the confidence
            known = any(slug_guess in aw for aw in batch.get("known_artworks", []))
            if not known:
                status = "pending"
            artworks.append({"slug": slug_guess,
                             "confidence": round(gem["confidence"], 2),
                             "status": status, "basis": "gemini"})
    entry["artworks"] = artworks
    return {
        "edition": batch["edition"],
        "event": batch.get("event"),
        "venue": batch.get("venue"),
        "context": batch.get("context"),
        "date": entry["date"], "date_basis": entry["date_basis"],
        "media_type": entry["media_type"],
        "asset_class": batch.get("asset_class", "unclassified"),
        "artists": batch.get("artists", []),
        "artworks": artworks,
        "persons": [],
        "face_pass": "skipped:no-gallery-enrolled",
        "scene": entry.get("scene", []),
        "caption": entry.get("caption") or "",
    }


def stage_catalogue(entry, ctx):
    st = ctx.state
    record = {
        "key": entry["key"],
        "bytes": entry["bytes"],
        "sha256": entry["sha256"],
        "media_type": entry["media_type"],
        "source": "local:" + (
            Path(entry["path"]).relative_to(REPO_ROOT).as_posix()
            if str(entry["path"]).startswith(str(REPO_ROOT))
            else Path(entry["path"]).as_posix()),
        "ingested": datetime.now().strftime("%Y-%m-%d"),
        "thumb": f"thumbs/{entry['key']}" if entry.get("thumb") else None,
        "tags": build_tags(entry, ctx),
    }
    media_store.upsert_asset_local(ctx.catalogue, record)
    ctx.known_sha[entry["sha256"]] = entry["key"]
    ctx.known_keys[entry["key"]] = entry["sha256"]
    _advance(entry, ctx.state, "catalogued")
    pending = sum(1 for a in record["tags"]["artworks"] if a["status"] == "pending")
    st.log(f"[catalogue] {entry['id']} recorded" + (f" ({pending} tag(s) -> review queue)" if pending else ""))
    return True


STAGES = [stage_checksum, stage_dedupe, stage_upload, stage_thumbnail,
          stage_caption, stage_embed, stage_catalogue]


def process_entry(entry, ctx):
    """Run one file through all stages. Stops at terminal states."""
    entry["error"] = None
    entry["retryable"] = False
    for stage in STAGES:
        if not stage(entry, ctx):
            return False
    return True


# ================================================================ run / finalize

def estimate_full_run(state, remaining_photos):
    cost = state.data["cost"]
    done = max(cost["caption_calls"], 1)
    per_photo = cost["eur_actual"] / done if cost["eur_actual"] else 0.0005
    est = round(cost["eur_actual"] + per_photo * remaining_photos, 4)
    cost["eur_full_run_estimate"] = est
    state.write()
    return est


def eligible_files(state):
    return [f for f in state.data["files"]
            if f["state"] not in ("catalogued", "duplicate", "excluded")
            and not (f["state"] == "quarantined" and not f["retryable"])]


def run_pipeline(state, ctx, sample=None):
    """Process eligible files (all, or first `sample`). Returns processed count."""
    todo = [f for f in eligible_files(state) if f["state"] in ("discovered", "checksum")]
    if sample:
        todo = todo[:sample]
    state.set_phase("dry-run" if sample else "running")
    processed = 0
    for entry in todo:
        process_entry(entry, ctx)
        processed += 1
    if sample:
        remaining = len([f for f in eligible_files(state) if f["media_type"] == "photo"])
        est = estimate_full_run(state, remaining)
        state.log(f"[dry-run] {processed} sample file(s) done; full-run estimate EUR {est}")
        state.set_phase("awaiting-approval")
    return processed


def append_sources_md(state, source_dir):
    """Append the durable R2 keys to the source folder's _SOURCES.md (append-only)."""
    sources_path = Path(source_dir) / "_SOURCES.md"
    if not sources_path.is_file():
        state.log("[finalize] no _SOURCES.md in source folder -- write-back skipped")
        return None
    existing = sources_path.read_text(encoding="utf-8")
    bucket = media_store.bucket_name()
    today = datetime.now().strftime("%Y-%m-%d")
    lines = []
    for f in state.data["files"]:
        if f["state"] != "catalogued":
            continue
        r2_uri = f"r2://{bucket}/{f['key']}"
        if r2_uri in existing:
            continue  # idempotent: never duplicate a line
        lines.append(f"- `{r2_uri}` | sha256 `{f['sha256']}` | {f['bytes']:,} bytes"
                     f" | ingested {today} | orig: local `{f['rel']}`")
    if not lines:
        state.log("[finalize] _SOURCES.md already carries all R2 keys -- nothing appended")
        return None
    block = (f"\n## R2 inventory (ingested {today})\n\n"
             "Durable object-store copies -- these keys never expire. "
             "Retrieve via `py -3.11 tools/media_store.py download --key <key> --out <path>`.\n\n"
             + "\n".join(lines) + "\n")
    with open(sources_path, "a", encoding="utf-8") as fh:
        fh.write(block)
    state.log(f"[finalize] appended {len(lines)} R2 key(s) to {sources_path.name}")
    return str(sources_path)


def write_run_report(state):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    rid = state.data["run_id"]
    path = REPORT_DIR / f"run-{rid}.md"
    d = state.data
    c = d["counts"]
    cost = d["cost"]
    batch = d["batch"]
    lines = [
        f"# Media ingest run {rid}",
        "",
        f"- date: {d['updated']}",
        f"- source: `{batch.get('source', '')}`",
        f"- edition / prefix: {batch.get('edition')} / `{batch.get('prefix')}`",
        f"- asset class: {batch.get('asset_class')} | artists: {', '.join(batch.get('artists', []))}",
        f"- providers: caption={d['providers']['caption']}, embed={d['providers']['embed']}, face={d['providers']['face']}",
        "",
        "## Ledger",
        "",
        f"| discovered | catalogued | duplicates | quarantined | excluded |",
        f"|---|---|---|---|---|",
        f"| {c.get('discovered', 0)} | {c.get('catalogued', 0)} | {c.get('duplicates', 0)} | {c.get('quarantined', 0)} | {c.get('excluded', 0)} |",
        "",
        "## Cost",
        "",
        f"- Gemini caption calls: {cost['caption_calls']}, embed calls: {cost['embed_calls']}",
        f"- tokens in/out: {cost['tokens_in']:,} / {cost['tokens_out']:,}",
        f"- actual cost: EUR {cost['eur_actual']}",
        "",
        "## Assets",
        "",
    ]
    for f in d["files"]:
        status = f["state"]
        note = f" ({f['error']})" if f.get("error") else ""
        lines.append(f"- `{f['key']}` -- {status}{note}")
    quarantined = [f for f in d["files"] if f["state"] == "quarantined"]
    if quarantined:
        lines += ["", "## Quarantine", ""]
        lines += [f"- {f['name']}: {f['error']}" for f in quarantined]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    state.data["report_path"] = str(path.relative_to(REPO_ROOT).as_posix())
    state.write()
    return path


def finalize(state, ctx, source_dir):
    """Push sidecars to the bucket, write run report + _SOURCES.md, archive run."""
    state.set_phase("finalizing")
    edition = state.data["batch"]["edition"]
    ctx.catalogue["generated"] = now_iso()
    media_store.write_catalogue(edition, ctx.catalogue, ctx.r2, ctx.env)
    manifest = {
        "edition": edition, "generated": now_iso(),
        "assets": [media_store.manifest_record_from(r) for r in ctx.catalogue["assets"]],
    }
    media_store.write_manifest(edition, manifest, ctx.r2, ctx.env)
    state.log(f"[finalize] _manifest.json + _catalogue.json pushed ({len(manifest['assets'])} assets)")
    append_sources_md(state, source_dir)
    report = write_run_report(state)
    state.log(f"[finalize] run report -> {report.relative_to(REPO_ROOT).as_posix()}")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    archive = RUNS_DIR / f"{state.data['run_id']}.json"
    archive.write_text(json.dumps(state.data, indent=1, ensure_ascii=False), encoding="utf-8")
    state.set_phase("done")
    c = state.data["counts"]
    state.log(f"[done] ledger: {c['discovered']} discovered = {c['catalogued']} catalogued"
              f" + {c['duplicates']} duplicates + {c['quarantined']} quarantined"
              f" + {c['excluded']} excluded ({'BALANCED' if c['in_pipeline'] == 0 else 'IN FLIGHT: ' + str(c['in_pipeline'])})")


# ================================================================ headless CLI

def default_batch(args):
    return {
        "edition": args.edition,
        "prefix": args.prefix.rstrip("/"),
        "asset_class": args.asset_class,
        "artists": [a.strip() for a in args.artists.split(",") if a.strip()],
        "event": args.event or None,
        "venue": None,
        "context": args.context or None,
        "source": args.source,
        "known_artworks": [a.strip() for a in (args.known_artworks or "").split(",") if a.strip()],
    }


def main():
    p = argparse.ArgumentParser(description="Slow Interpolation media ingest (headless)")
    p.add_argument("--source", required=True, help="local folder to ingest")
    p.add_argument("--edition", default="nyc-billboard")
    p.add_argument("--prefix", required=True, help="bucket key prefix, e.g. nyc-billboard/_preview/bla-lake")
    p.add_argument("--asset-class", dest="asset_class", default="press-kit")
    p.add_argument("--artists", default="", help="comma-separated artist slugs")
    p.add_argument("--event", default=None)
    p.add_argument("--context", default=None)
    p.add_argument("--known-artworks", dest="known_artworks", default="",
                   help="comma-separated artwork slugs for deterministic tagging")
    p.add_argument("--sample", type=int, default=None, help="process only the first N files")
    p.add_argument("--yes", action="store_true", help="run without interactive approval")
    args = p.parse_args()

    if not args.yes:
        sys.exit("Headless mode requires --yes (the web UI is the interactive path).")

    source = (REPO_ROOT / args.source) if not Path(args.source).is_absolute() else Path(args.source)
    state = RunState()
    batch = default_batch(args)
    batch["source"] = str(source.relative_to(REPO_ROOT).as_posix()) if str(source).startswith(str(REPO_ROOT)) else str(source)

    scan_source(source, state, batch)
    ctx = Ctx(state)
    if not preflight(ctx):
        state.set_phase("failed")
        state.data["error"] = "preflight failed (see log)"
        state.write()
        sys.exit("preflight failed -- see log above")

    run_pipeline(state, ctx, sample=args.sample)
    finalize(state, ctx, source)


if __name__ == "__main__":
    main()
