"""
serve_atlas.py -- Media Archive Viz, the READ face (v1).

A standalone, read-only HTTP server for the media archive. It boots on
`--edition` alone (NO ingest args, NO `--source`) and imports only `media_store`
(+ `media_query` lazily, for cluster retrieval). It has NO publish / review / tag
/ write endpoints of any kind -- the read face literally cannot mutate the
catalogue. Writes (edit-to-fix, publish, drag-tag) live in the separate
ingest/write engine (serve.py) and are a later v2 phase.

Doctrine: the viz is a front-end to the SAME gated backend tools, never a second
writer. This server only READS the catalogue, the derived field, the local
thumbnail cache, and mints short-lived presigned GET URLs for playback.

Endpoints (all read-only except the append-only usage log added in T8):
    GET  /                      -> atlas.html (or a placeholder until T4)
    GET  /atlas.(js|css|mjs)    -> static front-end assets
    GET  /api/field             -> cache/field-{edition}.json (far-LOD data)
    GET  /api/catalogue         -> full catalogue (read-only)
    GET  /api/presign?key=      -> short-lived presigned GET URL (video/original)
    GET  /thumbs/{sha}.jpg      -> local thumbnail cache
    (T6) GET /api/query         -> cluster retrieval via DuckDB
    (T8) POST /api/log          -> append-only usage log
    GET  /api/download?key=     -> login-gated single download (stream original)
    POST /api/download-zip      -> login-gated multi download (zip of selected keys)

Downloads verify a valid Slow Interpolation Supabase session server-side and append to an
append-only download ledger; they READ objects + mint no catalogue write, so the
read-only-catalogue doctrine still holds.

Usage:
    py -3.11 tools/media-engine/serve_atlas.py [--edition nyc-billboard] [--port 8767]
                                               [--host 127.0.0.1]
Open http://127.0.0.1:8767/
"""

import argparse
import http.server
import io
import json
import os
import socketserver
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ENGINE_DIR = Path(__file__).resolve().parent
TOOLS_DIR = ENGINE_DIR.parent
REPO_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(ENGINE_DIR))

import media_store  # noqa: E402  (read-only usage only)
import usage_log     # noqa: E402  (append-only usage log; never touches the catalogue)

# Reject an oversized POST body outright -- the log endpoint only ever receives a
# small event object, so anything large is malformed or abusive.
MAX_LOG_BODY = 8192

CACHE_DIR = ENGINE_DIR / "cache"
THUMBS_DIR = CACHE_DIR / "thumbs"
ATLAS_DIR = CACHE_DIR / "atlas"
GLANCE_DIR = ENGINE_DIR / "glance"
DOWNLOAD_LOG = CACHE_DIR / "download-log.jsonl"

# ---- login-gated download (identity check only; NO catalogue mutation) ----
# PUBLIC Supabase values (same pair the site + glance/auth-config.js use). The anon
# key is a public browser value; the service-role key never appears here. Tokens are
# verified against Supabase's /auth/v1/user so only a valid Slow Interpolation session can download.
SUPABASE_URL = os.environ.get("PUBLIC_SUPABASE_URL", "https://")
SUPABASE_ANON = os.environ.get(
    "PUBLIC_SUPABASE_ANON_KEY",
    "",
)
ZIP_MAX_FILES = 60             # multi-select download cap (files)
ZIP_MAX_BYTES = 600 * 1024 * 1024   # and total-size cap (~600 MB) -- in-memory zip

# short-lived cache of a verified access token -> user (avoids re-hitting Supabase on
# every file of a multi-download). Tokens are opaque here; we only trust /auth/v1/user.
_TOKEN_CACHE = {}
_TOKEN_TTL = 120  # seconds

_R2_CLIENT = None
_R2_ENV = None
_R2_LOCK = threading.Lock()


def _r2():
    """Lazily build ONE R2 client/env (reused across download requests)."""
    global _R2_CLIENT, _R2_ENV
    with _R2_LOCK:
        if _R2_CLIENT is None:
            _R2_ENV = media_store.load_env()
            _R2_CLIENT = media_store.r2_client(_R2_ENV)
        return _R2_CLIENT, _R2_ENV


def _verify_token(token):
    """Return {id, email} for a valid Supabase session token, else None. Verified
    server-side against Supabase (never trusts the client's word)."""
    if not token:
        return None
    now = time.time()
    hit = _TOKEN_CACHE.get(token)
    if hit and hit[0] > now:
        return hit[1]
    req = urllib.request.Request(
        SUPABASE_URL.rstrip("/") + "/auth/v1/user",
        headers={"Authorization": "Bearer " + token, "apikey": SUPABASE_ANON},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            if r.status == 200:
                u = json.loads(r.read().decode("utf-8"))
                user = {"id": u.get("id"), "email": u.get("email")}
                _TOKEN_CACHE[token] = (now + _TOKEN_TTL, user)
                return user
    except (urllib.error.URLError, ValueError, TimeoutError):
        return None
    return None


def _download_log(event):
    """Append-only download ledger (who downloaded what). Fixed path, best-effort,
    never raises. Separate from the circulation usage log."""
    try:
        rec = dict(event or {})
        rec.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        with open(DOWNLOAD_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _safe_name(key):
    return os.path.basename(key or "").replace('"', "") or "download"

STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}

PLACEHOLDER = b"""<!doctype html><meta charset=utf-8>
<title>Media Archive Viz</title>
<body style="font:14px system-ui;background:#0c0c0e;color:#d8d5cf;padding:40px">
<h1>Media Archive Viz &mdash; read face</h1>
<p>Server is up. Front-end (atlas.html) lands in T4.</p>
<p>Endpoints: <code>/api/field</code> &middot; <code>/api/catalogue</code> &middot;
<code>/api/presign?key=</code> &middot; <code>/thumbs/{sha}.jpg</code></p>
</body>"""


class State:
    edition = "nyc-billboard"
    _catalogue = None
    _cat_lock = threading.Lock()

    @classmethod
    def field_path(cls):
        return CACHE_DIR / f"field-{cls.edition}.json"

    _keys = None

    @classmethod
    def catalogue(cls):
        """Read-once, in-memory. (Read-only: never written back.)"""
        with cls._cat_lock:
            if cls._catalogue is None:
                cls._catalogue = media_store.read_catalogue(cls.edition)
            return cls._catalogue

    @classmethod
    def valid_key(cls, key):
        """True if `key` is a real asset key in this edition's catalogue. Guards the
        download endpoints so an arbitrary R2 key can never be fetched/presigned."""
        with cls._cat_lock:
            if cls._keys is None:
                cat = cls._catalogue or media_store.read_catalogue(cls.edition)
                cls._catalogue = cat
                cls._keys = {a.get("key") for a in cat.get("assets", []) if a.get("key")}
            return key in cls._keys


class AtlasHandler(http.server.BaseHTTPRequestHandler):
    server_state = {"last_activity": time.time()}

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[atlas] {fmt % args}\n")

    def _touch(self):
        type(self).server_state["last_activity"] = time.time()

    # --------------------------------------------------------------- GET
    def do_GET(self):
        self._touch()
        path = urlparse(self.path).path

        if path in ("/", "/index.html", "/glance.html"):
            f = GLANCE_DIR / "index.html"
            if f.is_file():
                return self._serve_file(f)
            return self._raw(PLACEHOLDER, "text/html; charset=utf-8")

        # Glance front-end (present from T4 on): glance/*.{html,css,js,mjs,svg}
        if path.startswith("/glance/"):
            f = (GLANCE_DIR / path[len("/glance/"):]).resolve()
            if str(f).startswith(str(GLANCE_DIR.resolve())) and f.is_file():
                return self._serve_file(f)
            return self.send_error(404, "Not found")

        # Atlas sheets + index (derived artifacts under cache/atlas/)
        if path.startswith("/atlas/"):
            name = path[len("/atlas/"):]
            f = (ATLAS_DIR / name).resolve()
            if not str(f).startswith(str(ATLAS_DIR.resolve())):
                return self.send_error(403, "Forbidden")
            if f.is_file():
                mime = "image/jpeg" if f.suffix == ".jpg" else None
                return self._serve_file(f, mime=mime, cache=True)
            return self.send_error(404, "Not found")

        if path == "/api/field":
            fp = State.field_path()
            if not fp.is_file():
                return self._json({"error": f"field data not built; run build_field.py "
                                            f"(missing {fp.name})"}, 503)
            return self._serve_file(fp, cache=False)

        if path == "/api/catalogue":
            return self._json(State.catalogue(), cache=False)

        if path == "/api/presign":
            qs = parse_qs(urlparse(self.path).query)
            key = (qs.get("key") or [""])[0]
            if not key:
                return self._json({"ok": False, "error": "key required"}, 400)
            try:
                ttl = int((qs.get("ttl") or ["3600"])[0])
                url = media_store.presign(key, ttl=ttl)
                return self._json({"ok": True, "url": url})
            except Exception as e:
                return self._json({"ok": False, "error": str(e)}, 500)

        # ---- login-gated single download (stream the original, attachment) ----
        # Requires a valid Slow Interpolation Supabase session (Authorization: Bearer <token>).
        # Streams the object from R2 through this server (same-origin, so the browser
        # saves it cleanly) with an attachment disposition, and appends to the ledger.
        if path == "/api/download":
            user = _verify_token(self._bearer())
            if not user:
                return self._json({"ok": False, "error": "login required"}, 401)
            qs = parse_qs(urlparse(self.path).query)
            key = (qs.get("key") or [""])[0]
            if not key or not State.valid_key(key):
                return self._json({"ok": False, "error": "unknown key"}, 404)
            return self._stream_object(key, user)

        if path.startswith("/thumbs/"):
            name = path[len("/thumbs/"):]
            target = (THUMBS_DIR / name).resolve()
            if not str(target).startswith(str(THUMBS_DIR.resolve())):
                return self.send_error(403, "Forbidden")
            if target.is_file():
                return self._serve_file(target, mime="image/jpeg", cache=True)
            return self.send_error(404, "Not found")

        return self.send_error(404, "Not found")

    # --------------------------------------------------------------- POST
    # The ONLY write path on this server: an append-only usage log. It never
    # touches the catalogue, R2, or the filesystem beyond one fixed jsonl file
    # (path is set in usage_log.py, never from the request). Every other POST 404s.
    def do_POST(self):
        self._touch()
        path = urlparse(self.path).path

        # ---- login-gated multi download (zip of selected keys) ----
        if path == "/api/download-zip":
            user = _verify_token(self._bearer())
            if not user:
                return self._json({"ok": False, "error": "login required"}, 401)
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length <= 0 or length > 256 * 1024:
                    return self._json({"ok": False, "error": "bad body size"}, 400)
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                keys = body.get("keys") if isinstance(body, dict) else None
            except (ValueError, UnicodeDecodeError):
                return self._json({"ok": False, "error": "bad json"}, 400)
            if not isinstance(keys, list) or not keys:
                return self._json({"ok": False, "error": "no keys"}, 400)
            keys = [k for k in keys if isinstance(k, str) and State.valid_key(k)]
            if not keys:
                return self._json({"ok": False, "error": "no valid keys"}, 404)
            if len(keys) > ZIP_MAX_FILES:
                return self._json({"ok": False, "error": f"too many files (max {ZIP_MAX_FILES})"}, 413)
            return self._stream_zip(keys, user)

        if path != "/api/log":
            return self.send_error(404, "Not found")

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json({"ok": False, "error": "bad length"}, 400)
        if length <= 0 or length > MAX_LOG_BODY:
            return self._json({"ok": False, "error": "bad body size"}, 400)

        try:
            body = self.rfile.read(length)
            event = json.loads(body.decode("utf-8"))
            if not isinstance(event, dict):
                raise ValueError("event must be an object")
        except (ValueError, UnicodeDecodeError):
            return self._json({"ok": False, "error": "bad json"}, 400)

        # server-stamped fields; client may set `source` (defaults to "ui")
        event.setdefault("source", "ui")
        try:
            event["client_ip"] = self.client_address[0]
        except Exception:
            pass
        usage_log.append(event)
        return self._json({"ok": True})

    # ------------------------------------------------------ download helpers
    def _bearer(self):
        h = self.headers.get("Authorization") or ""
        return h[7:].strip() if h.lower().startswith("bearer ") else ""

    def _stream_object(self, key, user):
        """Stream ONE R2 object to the client as an attachment, then log it."""
        client, env = _r2()
        bucket = media_store.bucket_name(env)
        try:
            head = client.head_object(Bucket=bucket, Key=key)
        except Exception:
            return self._json({"ok": False, "error": "not found"}, 404)
        size = int(head.get("ContentLength") or 0)
        ctype = head.get("ContentType") or "application/octet-stream"
        fname = _safe_name(key)
        try:
            obj = client.get_object(Bucket=bucket, Key=key)
            body = obj["Body"]
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            if size:
                self.send_header("Content-Length", str(size))
            self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            for chunk in iter(lambda: body.read(65536), b""):
                self.wfile.write(chunk)
        except Exception as e:
            self.log_message("download stream error: %s", e)
            return
        _download_log({"type": "download", "mode": "single", "count": 1,
                       "keys": [key], "user_id": user.get("id"), "email": user.get("email"),
                       "client_ip": self._ip()})

    def _stream_zip(self, keys, user):
        """Build an in-memory zip of the selected keys and stream it as an attachment.
        ZIP_STORED (no recompression -- photos/videos are already compressed)."""
        client, env = _r2()
        bucket = media_store.bucket_name(env)
        buf = io.BytesIO()
        total = 0
        used = {}
        try:
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
                for key in keys:
                    try:
                        data = client.get_object(Bucket=bucket, Key=key)["Body"].read()
                    except Exception:
                        continue
                    total += len(data)
                    if total > ZIP_MAX_BYTES:
                        return self._json({"ok": False, "error": "selection too large"}, 413)
                    name = _safe_name(key)
                    if name in used:                       # dedupe basename collisions
                        used[name] += 1
                        stem, dot, ext = name.rpartition(".")
                        name = (f"{stem}-{used[name]}.{ext}" if dot else f"{name}-{used[name]}")
                    else:
                        used[name] = 0
                    z.writestr(name, data)
        except Exception as e:
            self.log_message("zip build error: %s", e)
            return self._json({"ok": False, "error": "zip failed"}, 500)
        blob = buf.getvalue()
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Length", str(len(blob)))
        self.send_header("Content-Disposition", 'attachment; filename="glance-photos.zip"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(blob)
        _download_log({"type": "download", "mode": "zip", "count": len(keys),
                       "keys": keys, "user_id": user.get("id"), "email": user.get("email"),
                       "client_ip": self._ip()})

    def _ip(self):
        try:
            return self.client_address[0]
        except Exception:
            return None

    # --------------------------------------------------------------- helpers
    def _serve_file(self, path: Path, mime=None, cache=False):
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            return self.send_error(404, "Not found")
        if mime is None:
            mime = STATIC_TYPES.get(path.suffix.lower(), "application/octet-stream")
        self._raw(data, mime, cache=cache)

    def _raw(self, data: bytes, mime: str, cache=False):
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control",
                         "public, max-age=86400" if cache else "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, status=200, cache=False):
        # obj may already be a dict; serialize compactly
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store" if not cache else "public, max-age=60")
        self.end_headers()
        self.wfile.write(body)


class ReusableTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--edition", default="nyc-billboard")
    p.add_argument("--port", type=int, default=8767)
    p.add_argument("--host", default="127.0.0.1",
                   help="127.0.0.1 (loopback) or 0.0.0.0 (LAN, for iPhone in T9)")
    p.add_argument("--timeout", type=int, default=14400, help="idle shutdown seconds")
    args = p.parse_args()

    State.edition = args.edition
    if not State.field_path().is_file():
        sys.stderr.write(f"[atlas] WARNING: {State.field_path().name} not found -- "
                         f"run build_field.py --edition {args.edition} first.\n")

    server = ReusableTCPServer((args.host, args.port), AtlasHandler)
    sys.stderr.write(f"[atlas] read-only viz at http://{args.host}:{args.port}/  "
                     f"(edition={args.edition})\n")
    sys.stderr.flush()

    def watcher():
        while True:
            time.sleep(10)
            idle = time.time() - AtlasHandler.server_state["last_activity"]
            if idle > args.timeout:
                sys.stderr.write(f"[atlas] idle {int(idle)}s > {args.timeout}s -- shutting down.\n")
                server.shutdown()
                return

    threading.Thread(target=watcher, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
