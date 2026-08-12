"""
Slow Interpolation Media Engine -- local web server (Engine Room + Library).

Serves engine.html/css/js + run state + thumbnails, and drives the ingest
pipeline (tools/media-engine/ingest.py) on a background thread.

Usage:
    py -3.11 tools/media-engine/serve.py [--port 8766] [--timeout 7200] \
        [--source <local-folder>] \
        [--edition nyc-billboard] [--prefix nyc-billboard/<group-slug>] \
        [--asset-class press-kit] [--artists <entity-slug>] [--context <label>] \
        [--known-artworks <work-slug>]

Open http://127.0.0.1:8766/ -- loopback only, no auth (planner-pattern).
"""

import argparse
import http.server
import json
import socketserver
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

ENGINE_DIR = Path(__file__).resolve().parent
TOOLS_DIR = ENGINE_DIR.parent
REPO_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(ENGINE_DIR))

import media_store  # noqa: E402
import ingest  # noqa: E402


class Runtime:
    """Single shared run context for the server process."""
    state = None          # ingest.RunState
    ctx = None            # ingest.Ctx
    batch = None          # dict
    source_dir = None     # Path
    run_lock = threading.Lock()
    worker = None         # threading.Thread

    @classmethod
    def fresh_state(cls):
        cls.state = ingest.RunState()
        cls.state.write()
        return cls.state


def _run_guarded(target, *args, **kwargs):
    """Start a pipeline thread if none is active. Returns (ok, message)."""
    if Runtime.worker is not None and Runtime.worker.is_alive():
        return False, "a run is already in progress"

    def wrapper():
        try:
            target(*args, **kwargs)
        except SystemExit as e:
            Runtime.state.data["error"] = str(e)
            Runtime.state.set_phase("failed")
        except Exception as e:
            Runtime.state.data["error"] = ingest.ascii_safe(f"{type(e).__name__}: {e}")
            Runtime.state.log(f"[error] pipeline crashed: {Runtime.state.data['error']}")
            Runtime.state.set_phase("failed")

    Runtime.worker = threading.Thread(target=wrapper, daemon=True)
    Runtime.worker.start()
    return True, "started"


def do_dry_run(sample, excluded_ids):
    st = Runtime.state
    for fid in excluded_ids or []:
        entry = st.file_by_id(fid)
        if entry and entry["state"] == "discovered":
            entry["state"] = "excluded"
            st.log(f"[intake] {fid} excluded by user")
    st.write()
    Runtime.ctx = ingest.Ctx(st)
    if not ingest.preflight(Runtime.ctx):
        st.data["error"] = "preflight failed (see console)"
        st.set_phase("failed")
        return
    ingest.run_pipeline(st, Runtime.ctx, sample=sample)


def do_approve():
    st = Runtime.state
    if Runtime.ctx is None:
        st.log("[error] approve before dry-run -- run the dry-run first")
        return
    ingest.run_pipeline(st, Runtime.ctx, sample=None)
    ingest.finalize(st, Runtime.ctx, Runtime.source_dir)


def do_retry(file_id):
    st = Runtime.state
    entry = st.file_by_id(file_id)
    if entry is None or Runtime.ctx is None:
        return
    if entry["state"] != "quarantined" or not entry["retryable"]:
        st.log(f"[retry] {file_id} is not retryable")
        return
    entry["state"] = "discovered"
    entry["states_done"] = ["discovered"]
    st.log(f"[retry] re-queueing {file_id} {entry['name']}")
    ingest.process_entry(entry, Runtime.ctx)
    if st.data["phase"] == "done":
        ingest.finalize(st, Runtime.ctx, Runtime.source_dir)  # refresh sidecars


def review_tag(key, tag_class, slug, action):
    """Confirm/reject a pending tag in the working catalogue, push to R2."""
    st = Runtime.state
    catalogue = Runtime.ctx.catalogue if Runtime.ctx else None
    if catalogue is None:
        raise RuntimeError("no active catalogue -- run an ingest first")
    target = None
    for record in catalogue.get("assets", []):
        if record.get("key") == key:
            target = record
            break
    if target is None:
        raise KeyError(f"asset not in catalogue: {key}")
    entries = target.get("tags", {}).get(tag_class) or []
    hit = False
    kept = []
    for e in entries:
        if isinstance(e, dict) and e.get("slug") == slug:
            hit = True
            if action == "reject":
                continue
            e["status"] = "confirmed"
        kept.append(e)
    if not hit:
        raise KeyError(f"tag {tag_class}/{slug} not on {key}")
    target["tags"][tag_class] = kept
    if Runtime.ctx.r2 is not None:
        media_store.write_catalogue(catalogue["edition"], catalogue,
                                    Runtime.ctx.r2, Runtime.ctx.env)
    st.log(f"[review] {tag_class}/{slug} on {key.split('/')[-1]} -> {action}ed")
    return target


class EngineHandler(http.server.SimpleHTTPRequestHandler):
    server_state = {"last_activity": time.time()}

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[engine] {fmt % args}\n")

    def _touch(self):
        type(self).server_state["last_activity"] = time.time()

    # ------------------------------------------------------------- GET
    def do_GET(self):
        self._touch()
        path = urlparse(self.path).path

        if path in ("/", "/engine.html"):
            return self._serve_file(ENGINE_DIR / "engine.html", "text/html; charset=utf-8")
        if path == "/engine.css":
            return self._serve_file(ENGINE_DIR / "engine.css", "text/css; charset=utf-8")
        if path == "/engine.js":
            return self._serve_file(ENGINE_DIR / "engine.js", "application/javascript; charset=utf-8")

        if path == "/api/state":
            state_file = ingest.STATE_PATH
            if not state_file.is_file():
                return self._json_response({"phase": "idle", "files": [], "log": [],
                                            "counts": {}, "cost": {}})
            mtime = state_file.stat().st_mtime
            ims = self.headers.get("If-Modified-Since")
            if ims:
                try:
                    if float(ims) >= round(mtime, 3):
                        self.send_response(304)
                        self.end_headers()
                        return
                except ValueError:
                    pass
            data = state_file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-State-Mtime", str(round(mtime, 3)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return

        if path == "/api/catalogue":
            catalogue = Runtime.ctx.catalogue if (Runtime.ctx and Runtime.ctx.catalogue) else None
            if catalogue is None:
                try:
                    env = media_store.load_env()
                    if not media_store.missing_r2_keys(env):
                        catalogue = media_store.read_catalogue(Runtime.batch["edition"])
                except Exception:
                    catalogue = None
            return self._json_response(catalogue or {"edition": Runtime.batch["edition"], "assets": []})

        if path == "/api/media-url":
            from urllib.parse import parse_qs
            qs = parse_qs(urlparse(self.path).query)
            key = (qs.get("key") or [""])[0]
            if not key:
                return self._json_response({"ok": False, "error": "key required"}, 400)
            try:
                env = media_store.load_env()
                client = media_store.r2_client(env)
                url = client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": media_store.bucket_name(env), "Key": key},
                    ExpiresIn=3600,
                )
                return self._json_response({"ok": True, "url": url})
            except Exception as e:
                return self._json_response({"ok": False, "error": str(e)}, 500)

        if path == "/api/report":
            st = Runtime.state
            if st is None:
                return self._json_response({"available": False})
            return self._json_response({
                "available": st.data.get("report_path") is not None,
                "report_path": st.data.get("report_path"),
                "counts": st.data.get("counts", {}),
                "cost": st.data.get("cost", {}),
                "run_id": st.data.get("run_id"),
            })

        if path.startswith("/thumbs/"):
            name = path[len("/thumbs/"):]
            target = (ingest.THUMBS_DIR / name).resolve()
            if not str(target).startswith(str(ingest.THUMBS_DIR.resolve())):
                self.send_error(403, "Forbidden")
                return
            if target.is_file():
                return self._serve_file(target, "image/jpeg")
            self.send_error(404, "Not found")
            return

        self.send_error(404, "Not found")

    # ------------------------------------------------------------- POST
    def do_POST(self):
        self._touch()
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length > 0 else b""
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception as e:
            self.send_error(400, f"Bad JSON: {e}")
            return

        try:
            if path == "/api/scan":
                if Runtime.worker is not None and Runtime.worker.is_alive():
                    return self._json_response({"ok": False, "error": "a run is in progress"}, 409)
                st = Runtime.fresh_state()
                ingest.scan_source(Runtime.source_dir, st, dict(Runtime.batch))
                return self._json_response({"ok": True, "discovered": len(st.data["files"])})

            if path == "/api/dry-run":
                if Runtime.state is None or not Runtime.state.data["files"]:
                    return self._json_response({"ok": False, "error": "scan first"}, 400)
                sample = int(payload.get("sample", 3))
                ok, msg = _run_guarded(do_dry_run, sample, payload.get("excluded", []))
                return self._json_response({"ok": ok, "message": msg}, 200 if ok else 409)

            if path == "/api/approve":
                if Runtime.state is None or Runtime.state.data["phase"] != "awaiting-approval":
                    return self._json_response({"ok": False, "error": "nothing awaiting approval"}, 400)
                ok, msg = _run_guarded(do_approve)
                return self._json_response({"ok": ok, "message": msg}, 200 if ok else 409)

            if path == "/api/retry":
                fid = payload.get("file_id", "")
                ok, msg = _run_guarded(do_retry, fid)
                return self._json_response({"ok": ok, "message": msg}, 200 if ok else 409)

            if path == "/api/exclude":
                st = Runtime.state
                entry = st.file_by_id(payload.get("file_id", "")) if st else None
                if entry is None:
                    return self._json_response({"ok": False, "error": "unknown file"}, 404)
                if entry["state"] != "discovered":
                    return self._json_response({"ok": False, "error": "can only exclude at intake"}, 400)
                entry["state"] = "excluded"
                st.log(f"[intake] {entry['id']} {entry['name']} excluded by user")
                return self._json_response({"ok": True})

            if path == "/api/publish":
                key = payload.get("key", "")
                action = payload.get("action", "publish")
                if not key:
                    return self._json_response({"ok": False, "error": "key required"}, 400)
                fn = media_store.publish if action == "publish" else media_store.unpublish
                result = fn(key)
                # keep the in-memory working catalogue coherent with the remote write
                if Runtime.ctx and Runtime.ctx.catalogue:
                    for rec in Runtime.ctx.catalogue.get("assets", []):
                        if rec.get("key") == key:
                            tags = rec.setdefault("tags", {})
                            if action == "publish":
                                tags["public"] = True
                                tags["public_url"] = result["public_url"]
                                rec["public_url"] = result["public_url"]
                            else:
                                tags["public"] = False
                                tags.pop("public_url", None)
                                rec.pop("public_url", None)
                return self._json_response({"ok": True, "result": result})

            if path == "/api/review":
                record = review_tag(payload["key"], payload.get("tag_class", "artworks"),
                                    payload["slug"], payload.get("action", "confirm"))
                return self._json_response({"ok": True, "record": record})

        except (KeyError, RuntimeError) as e:
            return self._json_response({"ok": False, "error": ingest.ascii_safe(e)}, 400)

        self.send_error(404, "Unknown POST endpoint")

    # ------------------------------------------------------------- helpers
    def _serve_file(self, path: Path, mime: str):
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            self.send_error(404, "Not found")
            return
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json_response(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ReusableTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8766)
    p.add_argument("--timeout", type=int, default=7200, help="idle timeout seconds")
    p.add_argument("--source", default="outputs")
    p.add_argument("--edition", default="nyc-billboard")
    p.add_argument("--prefix", default="nyc-billboard/_inbox")
    p.add_argument("--asset-class", dest="asset_class", default="press-kit")
    p.add_argument("--artists", default="")
    p.add_argument("--event", default=None)
    p.add_argument("--context", default="")
    p.add_argument("--known-artworks", dest="known_artworks", default="")
    args = p.parse_args()

    source = Path(args.source)
    if not source.is_absolute():
        source = REPO_ROOT / source
    if not source.is_dir():
        # Library-only launch: create the staging folder rather than refusing to start.
        source.mkdir(parents=True, exist_ok=True)
        print(f"[engine] staging folder created (empty): {source}")

    Runtime.source_dir = source
    Runtime.batch = {
        "edition": args.edition,
        "prefix": args.prefix.rstrip("/"),
        "asset_class": args.asset_class,
        "artists": [a.strip() for a in args.artists.split(",") if a.strip()],
        "event": args.event or None,
        "venue": None,
        "context": args.context or None,
        "source": str(source.relative_to(REPO_ROOT).as_posix()) if str(source).startswith(str(REPO_ROOT)) else str(source),
        "known_artworks": [a.strip() for a in args.known_artworks.split(",") if a.strip()],
    }

    server = ReusableTCPServer(("127.0.0.1", args.port), EngineHandler)
    sys.stderr.write(f"[engine] serving at http://127.0.0.1:{args.port}/  (source={source})\n")
    sys.stderr.flush()

    def watcher():
        while True:
            time.sleep(5)
            idle = time.time() - EngineHandler.server_state["last_activity"]
            busy = Runtime.worker is not None and Runtime.worker.is_alive()
            if idle > args.timeout and not busy:
                sys.stderr.write(f"[engine] idle {int(idle)}s > {args.timeout}s -- shutting down.\n")
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
