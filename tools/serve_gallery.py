"""Serve ONLY the gallery and its renders, for phone viewing over a tunnel.

`python -m http.server` from the repo root would expose everything: unreleased
billboard work, `CLAUDE.local.md`, `models/` (2 GB of LoRAs), `.env`, `.git`.
Over a public Cloudflare quick tunnel that is not acceptable, so this serves a
strict allowlist and 403s the rest.

Allowed:  /  ->  gallery.html
          /outputs/**   (videos, posters, keyframes, analysis sheets)
Denied:   everything else, including any path that escapes the repo root.

    python tools/serve_gallery.py --port 8765

Pair with:  cloudflared tunnel --url http://127.0.0.1:8765

The tunnel URL is PUBLIC and UNAUTHENTICATED. Anyone with the link sees the
renders. Stop the tunnel when you are done.
"""

from __future__ import annotations

import argparse
import http.server
import socket
import re
import socketserver
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_DIRS = ("outputs",)
ALLOWED_FILES = ("gallery.html",)


class ScopedHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def _permitted(self, path: str) -> bool:
        """Resolve first, then compare. String prefixes are not enough.

        A prefix check let `/outputs/../CLAUDE.local.md` through: it starts with
        `outputs/`, and after resolution it still sits inside the repo, so an
        is-it-in-the-repo test passed it. The only safe test is whether the
        RESOLVED target is inside an explicitly allowed root.
        """
        rel = unquote(urlparse(path).path).lstrip("/")
        if rel in ("", "index.html"):
            rel = "gallery.html"
        try:
            target = (ROOT / rel).resolve()
        except (ValueError, OSError):
            return False
        if target in (ROOT / f for f in ALLOWED_FILES):
            return True
        for d in ALLOWED_DIRS:
            root = (ROOT / d).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                continue
            return True
        return False

    def do_GET(self):  # noqa: N802
        if self.path in ("/", ""):
            self.path = "/gallery.html"
        if not self._permitted(self.path):
            self.send_error(403, "Not served")
            return
        if self.headers.get("Range"):
            if self._serve_range():
                return
        super().do_GET()

    def _serve_range(self) -> bool:
        """Honour a Range request with a real 206.

        SimpleHTTPRequestHandler does NOT implement ranges; it ignores the header
        and returns 200 with the whole body. Advertising Accept-Ranges while
        doing that is worse than not advertising it: mobile browsers range-request
        video, get a 200 with a full multi-hundred-megabyte Content-Length, and
        refuse to play. That is exactly how a 363 MB clip failed on a phone.
        """
        rng = self.headers.get("Range", "")
        m = re.match(r"bytes=(\d*)-(\d*)$", rng.strip())
        if not m:
            return False
        path = Path(self.translate_path(self.path))
        if not path.is_file():
            return False
        size = path.stat().st_size
        start_s, end_s = m.group(1), m.group(2)
        if start_s == "" and end_s == "":
            return False
        if start_s == "":                       # suffix range: last N bytes
            length = min(int(end_s), size)
            start, end = size - length, size - 1
        else:
            start = int(start_s)
            end = int(end_s) if end_s else size - 1
        if start >= size:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return True
        end = min(end, size - 1)
        length = end - start + 1

        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(length))
        self.end_headers()
        with path.open("rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return True          # the player seeked away; normal
                remaining -= len(chunk)
        return True

    def do_HEAD(self):  # noqa: N802
        if not self._permitted(self.path):
            self.send_error(403, "Not served")
            return
        super().do_HEAD()

    def end_headers(self):
        # gallery.html is regenerated constantly. Without an explicit no-store a
        # mobile browser will keep serving a cached copy through pull-to-refresh,
        # so new renders appear to be missing when they are actually being served.
        # Videos and images are content-addressed by filename, so they may cache.
        if self.path.rstrip("/") in ("", "/index.html", "/gallery.html"):
            self.send_header("Cache-Control", "no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
        # Videos need range requests to scrub on mobile; SimpleHTTPRequestHandler
        # does not advertise it, and some mobile browsers refuse to play without.
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass  # quiet


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    # Do NOT set allow_reuse_address. On Windows it behaves like SO_REUSEADDR
    # and lets this bind a port another process already holds, after which
    # requests go to whichever socket wins. That silently happened once: the
    # allowlist tests all "passed" against a completely different app.
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if probe.connect_ex(("127.0.0.1", args.port)) == 0:
        probe.close()
        raise SystemExit(
            f"port {args.port} is already in use by another process. "
            f"Pick a free one with --port; refusing to share a port."
        )
    probe.close()
    with socketserver.ThreadingTCPServer(("127.0.0.1", args.port), ScopedHandler) as httpd:
        print(f"serving gallery.html + outputs/ on http://127.0.0.1:{args.port}")
        print("everything else returns 403")
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
