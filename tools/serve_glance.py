"""Serve the built Glance field to a phone AND accept curation back from it.

Why this exists. The deployed field on Vercel is a static site with no backend,
so a removal made in the browser lives in that device's localStorage and nowhere
else: invisible to the agent, invisible to anyone else opening the link. The only
way to act on it was to download `glance-removals.json` and hand the file over,
which is three manual steps in the middle of a curation pass.

Served from here instead, the page and the sink are SAME-ORIGIN, so the curate
face can POST its removal list straight back with no CORS, no shared secret and
no credential anywhere. Tap remove on the phone, the list lands in this repo, the
agent rebuilds. `tools/serve_gallery.py` already established this pattern for
viewing renders over a Cloudflare quick tunnel; this is the same idea with one
narrow write.

    python tools/serve_glance.py                        # LAN + localhost
    python tools/serve_glance.py --root outputs/_glance-ledwall-deploy
    python tools/serve_glance.py --token hunter2        # require ?t= on the POST

On the same wifi, open the printed LAN URL on the phone and nothing is exposed
to the internet at all. Away from home, pair with a tunnel:

    cloudflared tunnel --url http://127.0.0.1:8766

EXPOSURE, stated plainly. The static side serves only `--root`, which is a build
directory whose entire contents are already published to a public URL, so it
leaks nothing new. The write side accepts ONE fixed filename, caps the body,
and validates the shape before it touches disk, so the worst a stranger with the
tunnel URL can do is leave a junk removals file for the agent to read and ignore.
Pass --token if even that bothers you. Stop the tunnel when you are done.
"""

from __future__ import annotations

import argparse
import http.server
import json
import mimetypes
import re
import socket
import socketserver
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = ROOT / "outputs" / "_glance-ledwall-deploy"
INBOX = ROOT / "outputs" / "_glance-inbox"
ORIGINALS = ROOT / "outputs"
PREVIEWS = ROOT / "outputs" / "_gallery" / "previews"

SINK_PATH = "/curate/removals"
LOCAL_MEDIA = "/local-media/"
MAX_BODY = 256 * 1024          # a removal list is a few KB; this is generous
MAX_ENTRIES = 2000
SHA16 = re.compile(r"^[0-9a-f]{16}$")
RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def local_media_for(key: str) -> Path | None:
    """The best local file for a catalogue key: small proxy first, else original.

    `glance_deploy.py` withholds media for two reasons that are both about
    VERCEL: a 4 MB per-file cap and a 95 MB bundle budget. Neither applies to a
    file being read off this machine's own disk, so served from here the field
    can play everything it has. On 2026-08-10 that was 50 of 118 cards showing
    "video not published in this archive" on a local tunnel, which is true of
    the Vercel bundle and misleading here.
    """
    proxy = PREVIEWS / (key.replace("/", "__").rsplit(".", 1)[0] + ".mp4")
    if proxy.is_file():
        return proxy
    original = ORIGINALS / key
    try:
        original.relative_to(ORIGINALS)
    except ValueError:
        return None
    return original if original.is_file() else None


def validate(doc: object) -> tuple[list[dict], str | None]:
    """Return (entries, error). Anything unexpected is refused, not coerced."""
    if not isinstance(doc, dict):
        return [], "body is not a JSON object"
    if doc.get("action") != "exclude-from-curated-field":
        return [], f"unexpected action {doc.get('action')!r}"
    raw = doc.get("exclude")
    if not isinstance(raw, list):
        return [], "`exclude` is not a list"
    if len(raw) > MAX_ENTRIES:
        return [], f"{len(raw)} entries exceeds the {MAX_ENTRIES} cap"
    out = []
    for e in raw:
        if not isinstance(e, dict):
            return [], "an `exclude` entry is not an object"
        sha = str(e.get("sha16", "")).lower()
        key = e.get("key")
        if not SHA16.match(sha):
            return [], f"bad sha16 {sha!r}"
        if key is not None and not isinstance(key, str):
            return [], "a `key` is not a string"
        if isinstance(key, str) and ("\\" in key or key.startswith("/") or ".." in key):
            # Keys are only ever read back as catalogue identifiers, never opened
            # as paths, but refusing traversal shapes here costs nothing.
            return [], f"suspicious key {key!r}"
        out.append({"sha16": sha, "key": key})
    return out, None


def make_handler(root: Path, token: str | None):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(root), **kw)

        def end_headers(self):
            # NEVER let this server's own copy of the viewer be cached.
            #
            # SimpleHTTPRequestHandler answers conditional requests with 304, so a
            # browser keeps serving the module it already has. That is fine for a
            # static host and actively harmful here, because this server exists to
            # look at a build you are CHANGING: edit layout.js, reload, and the page
            # runs yesterday's file while looking exactly like it ran today's.
            #
            # It cost three false readings on 2026-08-11 -- a stylesheet that "did
            # not apply" was in the file and not in the sheet, and a layout change
            # measured as having no effect (17.7% vs 17.6% viewport fill) when the
            # page had simply never loaded it. A silent stale module does not look
            # like a caching problem, it looks like your change did nothing, which
            # is the most expensive way to be wrong.
            #
            # Data and media stay cacheable: they are big, they do not change while
            # you iterate, and re-fetching 80 MB of video on every reload would make
            # the tunnel unusable.
            p = self.path.split("?", 1)[0]
            if p.endswith((".js", ".css", ".html", ".json")) or p == "/":
                self.send_header("Cache-Control", "no-store, must-revalidate")
            super().end_headers()

        def send_head(self):
            # Suppress the 304 path as well. end_headers() sets the response header,
            # but a conditional request is answered from If-Modified-Since before a
            # body is ever considered, so the header alone still lets the browser
            # keep the copy it has. Dropping the validator forces a full 200.
            p = self.path.split("?", 1)[0]
            if p.endswith((".js", ".css", ".html", ".json")) or p == "/":
                for h in ("If-Modified-Since", "If-None-Match"):
                    if h in self.headers:
                        del self.headers[h]
            return super().send_head()

        def log_message(self, fmt, *args):
            # Static noise is useless here; the POST logs itself explicitly.
            #
            # str() is load-bearing: log_error() calls this with an HTTPStatus
            # enum as args[0], not a string, so a bare `"POST" in args[0]` raises
            # TypeError. That fires inside send_error(), i.e. while a 404 is being
            # written, so a missing favicon produced a traceback and a truncated
            # response instead of a clean 404. Found in the live log 2026-08-10.
            first = str(args[0]) if args else ""
            if "POST" in first or "curate" in first:
                super().log_message(fmt, *args)

        def _json(self, code: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _authed(self) -> bool:
            if not token:
                return True
            return f"t={token}" in (self.path.split("?", 1)[1] if "?" in self.path else "")

        def _serve_file(self, path: Path) -> None:
            """Send a file, honouring Range. iOS will not play video without it.

            `SimpleHTTPRequestHandler` ignores `Range` and answers 200 with the
            whole body. Safari on iPhone opens a video with a range probe and
            treats a 200 as "this server cannot seek", so playback is unreliable
            and scrubbing is impossible. Measured 2026-08-10: the live server
            returned 200 to `Range: bytes=0-1023`, which is the exact shape the
            project's own verification rule warns about.
            """
            try:
                size = path.stat().st_size
            except OSError:
                return self.send_error(404, "no such media")
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            start, end = 0, size - 1
            partial = False
            m = RANGE_RE.match(self.headers.get("Range", "") or "")
            if m and size:
                lo, hi = m.group(1), m.group(2)
                if lo:
                    start = int(lo)
                    if hi:
                        end = min(int(hi), size - 1)
                elif hi:                       # bytes=-N is the LAST n bytes
                    start = max(0, size - int(hi))
                if start > end or start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                partial = True

            self.send_response(206 if partial else 200)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if partial:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if self.command == "HEAD":
                return
            remaining = end - start + 1
            with path.open("rb") as fh:
                fh.seek(start)
                while remaining > 0:
                    chunk = fh.read(min(256 * 1024, remaining))
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        return          # the phone seeked away; not an error
                    remaining -= len(chunk)

        def _patched_catalogue(self, path: Path) -> None:
            """Fill in `media_url` for anything this machine can actually play."""
            doc = json.loads(path.read_text(encoding="utf-8"))
            added = 0
            for a in doc.get("assets", []):
                if a.get("media_url"):
                    continue
                key = a.get("key") or ""
                if local_media_for(key):
                    a["media_url"] = LOCAL_MEDIA.lstrip("/") + urllib.parse.quote(key)
                    added += 1
            body = json.dumps(doc).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            if added:
                print(f"  catalogue: +{added} local media_url (not in the Vercel bundle)")

        def do_HEAD(self):  # noqa: N802
            # Players probe with HEAD before ranging. Only our own routes need
            # the override; everything else keeps the stock behaviour.
            raw = self.path.split("?", 1)[0]
            if raw.startswith(LOCAL_MEDIA) or raw.endswith(".mp4"):
                return self.do_GET()
            return super().do_HEAD()

        def do_GET(self):  # noqa: N802
            raw = self.path.split("?", 1)[0]
            # The curate face probes this to discover whether a sink exists. On
            # Vercel it 404s and the face falls back to manual export, so the
            # same build works in both places with no configuration.
            if raw == SINK_PATH:
                return self._json(200, {"sink": "ok", "writes_to": str(INBOX)})
            if raw.startswith(LOCAL_MEDIA):
                key = urllib.parse.unquote(raw[len(LOCAL_MEDIA):])
                if "\\" in key or ".." in key or key.startswith("/"):
                    return self.send_error(403, "bad key")
                target = local_media_for(key)
                if not target:
                    return self.send_error(404, "no local media for that key")
                return self._serve_file(target)
            if raw == "/data/catalogue.json":
                cat = root / "data" / "catalogue.json"
                if cat.is_file():
                    return self._patched_catalogue(cat)
            # Range for the bundled proxies too, so seeking works on those.
            #
            # UNQUOTE FIRST. `self.path` is percent-encoded, so a delivery file named
            # "VANDALO RUINS_... .mp4" arrives as "VANDALO%20RUINS_... .mp4" and
            # `root / raw` names a file that does not exist. is_file() was therefore
            # False, this branch was skipped, and the request fell through to
            # SimpleHTTPRequestHandler -- which ignores Range and answers 200 with
            # the whole file. Safari treats a 200 to a range probe as "this server
            # cannot seek", so playback is unreliable and scrubbing impossible.
            #
            # It hit exactly the 9 client deliverables and nothing else, because they
            # are the only files here with spaces in their names: the range support
            # was real, it just never ran for the files that matter most. Measured
            # 2026-08-11: 9 of 26 answered 200 instead of 206.
            if raw.endswith(".mp4"):
                rel = urllib.parse.unquote(raw).lstrip("/")
                if "\\" not in rel and ".." not in rel:
                    f = root / rel
                    if f.is_file():
                        return self._serve_file(f)
            return super().do_GET()

        def do_POST(self):  # noqa: N802
            if self.path.split("?", 1)[0] != SINK_PATH:
                return self._json(404, {"error": "no such endpoint"})
            if not self._authed():
                return self._json(403, {"error": "bad or missing token"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._json(400, {"error": "bad Content-Length"})
            if n <= 0 or n > MAX_BODY:
                return self._json(413, {"error": f"body must be 1..{MAX_BODY} bytes"})
            try:
                doc = json.loads(self.rfile.read(n).decode("utf-8"))
            except Exception as e:
                return self._json(400, {"error": f"not JSON: {e}"})

            entries, err = validate(doc)
            if err:
                print(f"  REFUSED a removal POST: {err}")
                return self._json(422, {"error": err})

            INBOX.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            payload = {
                "action": "exclude-from-curated-field",
                "received": stamp,
                "collection": doc.get("collection") or "",
                "exclude": entries,
            }
            text = json.dumps(payload, indent=2)
            (INBOX / f"removals-{stamp}.json").write_text(text, encoding="utf-8")
            # `latest.json` is the one the agent feeds to glance_export.py; the
            # stamped copies are the audit trail.
            (INBOX / "latest.json").write_text(text, encoding="utf-8")
            print(f"  RECEIVED {len(entries)} removal(s) -> {INBOX / 'latest.json'}")
            for e in entries[:12]:
                print(f"     {e['key'] or e['sha16']}")
            return self._json(200, {"ok": True, "received": len(entries)})

    return Handler


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))       # no packets sent; just picks the route
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT,
                    help="a glance_deploy.py --out build directory")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--token", default=None,
                    help="if set, the POST requires ?t=<token>")
    args = ap.parse_args()

    if not (args.root / "index.html").is_file():
        raise SystemExit(f"no index.html in {args.root}\n"
                         f"  build one: python tools/glance_deploy.py --out {args.root}")

    with Server(("0.0.0.0", args.port), make_handler(args.root, args.token)) as httpd:
        print(f"serving {args.root.name} on:")
        print(f"  http://127.0.0.1:{args.port}        (this machine)")
        print(f"  http://{lan_ip()}:{args.port}       (phone, same wifi)")
        print(f"curation sink: POST {SINK_PATH} -> {INBOX}")
        if args.token:
            print(f"  token required: ?t={args.token}")
        print("away from wifi:  cloudflared tunnel --url "
              f"http://127.0.0.1:{args.port}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
