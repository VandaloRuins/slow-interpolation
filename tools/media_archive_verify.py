"""
Media archive self-test. Run this FIRST, before any ingest.

    py -3.11 tools/media_archive_verify.py [--collection nyc-billboard] [--no-write]

Checks, in order (later checks are skipped if an earlier hard one fails):
  1. interpreter + required/optional python packages
  2. ffmpeg on PATH (needed for video posters, frames, faststart publishing)
  3. tools/.env -- which R2 vars are present (values are NEVER printed)
  4. bucket reachability (head_bucket)
  5. round-trip: upload a tiny file, verify sha256 + size, download, compare, delete
  6. catalogue read for the configured collection
  7. public bucket (only if R2_PUBLIC_* are configured)

Exit code 0 = safe to use. Non-zero = something is wrong; the message says what.
"""

import argparse
import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

OK, WARN, FAIL = "PASS", "WARN", "FAIL"
results = []


def record(status, label, detail=""):
    results.append((status, label, detail))
    mark = {OK: "  ok  ", WARN: " warn ", FAIL: " FAIL "}[status]
    print(f"[{mark}] {label}" + (f" -- {detail}" if detail else ""))
    return status == OK


REQUIRED = [("boto3", "object store"), ("botocore", "object store")]
OPTIONAL = [
    ("duckdb", "SQL search (media_query.py)"),
    ("pandas", "SQL search + KB export"),
    ("pyarrow", "parquet KB export"),
    ("PIL", "thumbnails at ingest"),
    ("google.genai", "VLM captions + scene tags at ingest"),
    ("lancedb", "similarity search at ingest (optional)"),
    ("yaml", "markdown frontmatter KB adapter (optional)"),
]


def check_packages():
    import importlib
    hard_ok = True
    for mod, why in REQUIRED:
        try:
            importlib.import_module(mod)
            record(OK, f"package {mod}", why)
        except Exception:
            hard_ok = False
            record(FAIL, f"package {mod}", f"MISSING -- {why}. pip install -e .[archive]")
    for mod, why in OPTIONAL:
        try:
            importlib.import_module(mod)
            record(OK, f"package {mod}", why)
        except Exception:
            record(WARN, f"package {mod}", f"missing -- {why} unavailable")
    return hard_ok


def main():
    p = argparse.ArgumentParser(description="Verify the media archive install")
    p.add_argument("--collection", default="nyc-billboard")
    p.add_argument("--no-write", action="store_true",
                   help="skip the upload/delete round-trip (read-only check)")
    args = p.parse_args()

    print(f"interpreter: {sys.executable}")
    print(f"python     : {sys.version.split()[0]}\n")
    if sys.version_info < (3, 9):
        record(FAIL, "python version", "3.9+ required")
        return 1
    record(OK, "python version", sys.version.split()[0])

    if not check_packages():
        print("\nInstall the required packages first, then re-run.")
        return 1

    record(OK if shutil.which("ffmpeg") else WARN, "ffmpeg",
           "on PATH" if shutil.which("ffmpeg") else "not on PATH -- video posters/frames/publish will fail")

    import media_store

    env = media_store.load_env()
    env_file = TOOLS_DIR / ".env"
    record(OK if env_file.is_file() else WARN, "tools/.env",
           "found" if env_file.is_file() else "not found (using process environment)")

    missing = media_store.missing_r2_keys(env)
    if missing:
        record(FAIL, "R2 credentials", "missing: " + ", ".join(missing))
        return 1
    record(OK, "R2 credentials", "all four vars present (values not shown)")

    ok, msg = media_store.check_connection(env, quiet=True)
    if not ok:
        record(FAIL, "bucket reachable", msg.replace("\n", " "))
        return 1
    record(OK, "bucket reachable", f"'{media_store.bucket_name(env)}'")

    if not args.no_write:
        key = f"_selftest/verify-{os.getpid()}.txt"
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "probe.txt"
            src.write_text("media-archive-kit self test\n", encoding="utf-8")
            digest = hashlib.sha256(src.read_bytes()).hexdigest()
            try:
                media_store.upload(src, key, verify=True, env=env)
                record(OK, "upload + verify", key)
                back = Path(td) / "probe-back.txt"
                got = media_store.download(key, back, env=env)
                if got["sha256"] != digest:
                    record(FAIL, "round-trip sha256", "downloaded bytes differ from uploaded")
                    return 1
                record(OK, "round-trip sha256", digest[:16] + "...")
            except Exception as e:
                record(FAIL, "round-trip", f"{type(e).__name__}: {e}")
                return 1
            finally:
                try:
                    media_store.delete(key, env=env)
                    record(OK, "cleanup", f"deleted {key}")
                except Exception as e:
                    record(WARN, "cleanup", f"could not delete {key}: {e}")

    try:
        catalogue = media_store.read_catalogue(args.collection, env=env)
        n = len(catalogue.get("assets", []))
        record(OK, f"catalogue {args.collection}",
               f"{n} assets" + (" (empty -- expected on a fresh bucket)" if n == 0 else ""))
    except Exception as e:
        record(WARN, f"catalogue {args.collection}", f"{type(e).__name__}: {e}")

    pub_missing = media_store.missing_public_keys(env)
    if pub_missing == list(media_store.PUBLIC_ENV_KEYS):
        record(WARN, "public bucket", "not configured -- publish/unpublish unavailable (fine until you need public links)")
    elif pub_missing:
        record(WARN, "public bucket", "partially configured, missing: " + ", ".join(pub_missing))
    else:
        try:
            media_store.public_client(env).head_bucket(Bucket=env["R2_PUBLIC_BUCKET"])
            record(OK, "public bucket", env["R2_PUBLIC_BUCKET"])
        except Exception as e:
            record(WARN, "public bucket", f"unreachable: {type(e).__name__}: {e}")

    fails = sum(1 for s, _, _ in results if s == FAIL)
    warns = sum(1 for s, _, _ in results if s == WARN)
    print(f"\n{len(results) - fails - warns} passed, {warns} warnings, {fails} failures")
    if fails:
        print("NOT READY -- fix the failures above.")
        return 1
    print("READY. Next: ingest a small folder with --sample 5 before a full wave.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
