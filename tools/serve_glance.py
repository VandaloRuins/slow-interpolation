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
import re
import socket
import socketserver
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = ROOT / "outputs" / "_glance-ledwall-deploy"
INBOX = ROOT / "outputs" / "_glance-inbox"

SINK_PATH = "/curate/removals"
MAX_BODY = 256 * 1024          # a removal list is a few KB; this is generous
MAX_ENTRIES = 2000
SHA16 = re.compile(r"^[0-9a-f]{16}$")


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

        def log_message(self, fmt, *args):
            # Static noise is useless here; the POST logs itself explicitly.
            if "POST" in (args[0] if args else ""):
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

        def do_GET(self):  # noqa: N802
            # The curate face probes this to discover whether a sink exists. On
            # Vercel it 404s and the face falls back to manual export, so the
            # same build works in both places with no configuration.
            if self.path.split("?", 1)[0] == SINK_PATH:
                return self._json(200, {"sink": "ok", "writes_to": str(INBOX)})
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
