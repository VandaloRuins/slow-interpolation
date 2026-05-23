"""Serve the dataset directory over http://localhost AND persist gallery
state (flags + manual crops) to disk so user work survives:

  - browser refreshes
  - browser cache / private-mode wipes
  - localStorage being scoped to a different origin (file:// vs
    http://localhost:8765)
  - regenerating gallery.html from build_gallery.py

The browser auto-syncs every save to the server via POST /api/state. The
server keeps:

  - gallery-state.json           current snapshot (source of truth)
  - gallery-state.log.jsonl      append-only event log (audit + recovery)
  - gallery-state.backups/       hourly rotating backup of the JSON

On boot, the gallery GETs /api/state. If the disk file has entries, it
overwrites localStorage. If the disk file is empty, the gallery uploads
the local localStorage to disk (one-shot migration aid).

Usage:
    py -3.11 datasets/soutine-figures/serve.py
    py -3.11 datasets/soutine-figures/serve.py 9000   # custom port
"""
from __future__ import annotations

import hashlib
import http.server
import json
import shutil
import socket
import socketserver
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
REJECTED_USER = ROOT / "rejected" / "user-removed"
STATE_FILE = ROOT / "gallery-state.json"
STATE_LOG = ROOT / "gallery-state.log.jsonl"
BACKUP_DIR = ROOT / "gallery-state.backups"


def port_for_dataset(name: str) -> int:
    """Deterministic per-dataset port in the 8765 to 8864 range.

    Mirror of build_gallery.py's helper so the gallery HTML's probe URL
    matches the server's bound port without any extra config file.
    Multiple datasets coexist on different ports automatically.
    """
    h = int(hashlib.md5(name.encode("utf-8")).hexdigest()[:8], 16)
    return 8765 + (h % 100)


# Accept a positional port argument; ignore --no-build (handled in main()).
_pos = [a for a in sys.argv[1:] if not a.startswith("-")]
PORT = int(_pos[0]) if _pos else port_for_dataset(ROOT.name)

STATE_LOCK = threading.Lock()


def empty_state() -> dict:
    return {
        "version": 1,
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "flags": {},   # filename -> "remove" | "review"
        "crops": {},   # filename -> {x, y, w, h, rotation?}
    }


def read_state() -> dict:
    if not STATE_FILE.exists():
        return empty_state()
    try:
        s = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        s.setdefault("flags", {})
        s.setdefault("crops", {})
        return s
    except Exception:
        # corrupt — back up and start fresh
        BACKUP_DIR.mkdir(exist_ok=True)
        shutil.copy2(STATE_FILE, BACKUP_DIR / f"corrupt-{int(time.time())}.json")
        return empty_state()


def write_state(state: dict, event: dict | None = None) -> None:
    state["updated_at"] = datetime.utcnow().isoformat() + "Z"
    # Atomic write: tmp + rename
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)
    # Append-only log (one line per change event)
    if event is not None:
        with STATE_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": state["updated_at"], **event},
                                ensure_ascii=False) + "\n")
    # Hourly rotating backup
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d-%H")
    bak = BACKUP_DIR / f"gallery-state-{stamp}.json"
    if not bak.exists():
        shutil.copy2(STATE_FILE, bak)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass

    def _send_json(self, code: int, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path.startswith("/api/state"):
            with STATE_LOCK:
                self._send_json(200, read_state())
            return
        return super().do_GET()

    def do_POST(self) -> None:
        if self.path == "/api/state":
            return self._handle_state_post()
        if self.path == "/api/state/patch":
            return self._handle_state_patch()
        if self.path == "/api/remove":
            return self._handle_remove()
        if self.path == "/api/restore":
            return self._handle_restore()
        self.send_error(404)

    def _read_json_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 256 * 1024:
            self._send_json(400, {"error": "bad length"})
            return None
        try:
            return json.loads(self.rfile.read(length))
        except Exception as e:
            self._send_json(400, {"error": f"bad json: {e}"})
            return None

    def _safe_filename(self, name: str) -> str | None:
        """Ensure name is a single-file basename in raw/ or rejected dir."""
        if not name or "/" in name or "\\" in name or ".." in name:
            return None
        return name

    def _handle_remove(self) -> None:
        body = self._read_json_body()
        if body is None:
            return
        name = self._safe_filename(body.get("filename", ""))
        if not name:
            return self._send_json(400, {"error": "bad filename"})
        src = RAW / name
        if not src.exists():
            return self._send_json(404, {"error": f"{name} not in raw/"})
        REJECTED_USER.mkdir(parents=True, exist_ok=True)
        dest = REJECTED_USER / name
        # If a previous removal already moved this filename, suffix with timestamp
        if dest.exists():
            dest = REJECTED_USER / f"{int(time.time())}-{name}"
        shutil.move(str(src), str(dest))
        with STATE_LOCK:
            state = read_state()
            # Also drop any flag/crop for this file: it's gone.
            state["flags"].pop(name, None)
            state["crops"].pop(name, None)
            write_state(state, event={"op": "remove", "filename": name,
                                       "moved_to": str(dest.relative_to(ROOT))})
        self._send_json(200, {"status": "ok", "moved_to": str(dest.relative_to(ROOT))})

    def _handle_restore(self) -> None:
        body = self._read_json_body()
        if body is None:
            return
        name = self._safe_filename(body.get("filename", ""))
        moved_to = body.get("moved_to", "")  # path returned by /api/remove
        if not name:
            return self._send_json(400, {"error": "bad filename"})
        # Prefer the exact path the client got from /api/remove; fall back to
        # the conventional location.
        src = (ROOT / moved_to) if moved_to else (REJECTED_USER / name)
        if not src.exists() or not str(src.resolve()).startswith(str(REJECTED_USER.resolve())):
            return self._send_json(404, {"error": "backup not found"})
        dest = RAW / name
        if dest.exists():
            return self._send_json(409, {"error": "raw/<filename> already exists"})
        shutil.move(str(src), str(dest))
        with STATE_LOCK:
            state = read_state()
            write_state(state, event={"op": "restore", "filename": name,
                                       "restored_from": moved_to or str(src.relative_to(ROOT))})
        self._send_json(200, {"status": "ok"})

    def _handle_state_post(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 5 * 1024 * 1024:
            return self._send_json(400, {"error": "bad length"})
        try:
            body = json.loads(self.rfile.read(length))
        except Exception as e:
            return self._send_json(400, {"error": f"bad json: {e}"})
        if not isinstance(body, dict):
            return self._send_json(400, {"error": "expected object"})
        new_state = empty_state()
        new_state["flags"] = body.get("flags", {}) or {}
        new_state["crops"] = body.get("crops", {}) or {}
        with STATE_LOCK:
            write_state(new_state, event={"op": "replace",
                                          "flag_count": len(new_state["flags"]),
                                          "crop_count": len(new_state["crops"])})
        self._send_json(200, {"status": "ok", "updated_at": new_state["updated_at"]})

    def _handle_state_patch(self) -> None:
        """Incremental update: {filename, kind: 'flag'|'crop', value: ... | null}"""
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 256 * 1024:
            return self._send_json(400, {"error": "bad length"})
        try:
            patch = json.loads(self.rfile.read(length))
        except Exception as e:
            return self._send_json(400, {"error": f"bad json: {e}"})
        fn = patch.get("filename")
        kind = patch.get("kind")
        val = patch.get("value")
        if not fn or kind not in ("flag", "crop"):
            return self._send_json(400, {"error": "missing fields"})
        with STATE_LOCK:
            state = read_state()
            bucket = state["flags"] if kind == "flag" else state["crops"]
            if val is None:
                bucket.pop(fn, None)
            else:
                bucket[fn] = val
            write_state(state, event={"op": "patch", "filename": fn,
                                       "kind": kind, "value": val})
        self._send_json(200, {"status": "ok"})


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def server_bind(self) -> None:
        # On Windows, allow re-binding the port even if a TIME_WAIT slot
        # from a previous run is still hanging around.
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return super().server_bind()


def build_gallery_if_possible() -> bool:
    """Run build_gallery.py to refresh gallery.html. Best-effort: if it
    fails (missing deps, missing metadata), keep going with whatever HTML
    is already on disk."""
    builder = ROOT / "build_gallery.py"
    if not builder.exists():
        return False
    import subprocess
    print("rebuilding gallery.html ...")
    try:
        r = subprocess.run([sys.executable, str(builder)],
                            capture_output=True, text=True, cwd=ROOT, timeout=120)
        if r.returncode == 0:
            for line in (r.stdout or "").splitlines():
                if line.strip():
                    print("  " + line)
            return True
        print("  [warn] build_gallery.py exited", r.returncode)
        if r.stderr:
            print("  " + r.stderr.strip().splitlines()[-1])
        return False
    except Exception as e:
        print(f"  [warn] build failed: {e}")
        return False


def main() -> int:
    if "--no-build" not in sys.argv:
        build_gallery_if_possible()
    if not (ROOT / "gallery.html").exists():
        print("[err] gallery.html not found and build failed.")
        return 1
    srv = ThreadingServer(("127.0.0.1", PORT), Handler)
    try:
        url = f"http://localhost:{PORT}/gallery.html"
        print(f"serving {ROOT} at {url}")
        st = read_state()
        print(f"state: {len(st['flags'])} flags, {len(st['crops'])} crops on disk")
        print("press Ctrl-C to stop")
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
