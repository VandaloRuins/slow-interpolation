"""
Dropbox shared-folder fetcher for the media engine.

Streams each shared-folder link as a ZIP (dl=1) into a staging directory,
sequentially, with skip-if-done markers so re-runs resume cleanly.
Zero Claude tokens during transfer.

Usage:
    py -3.11 tools/media-engine/fetch_dropbox.py --manifest <json> --staging <dir> [--only NAME]

Manifest: JSON list of {"name": "...", "url": "https://www.dropbox.com/scl/fo/..."}.
Each entry lands at <staging>/<name>.zip with a <name>.done marker on success.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import urllib.request

CHUNK = 4 * 1024 * 1024  # 4 MB


def to_zip_url(url):
    if "dl=0" in url:
        return url.replace("dl=0", "dl=1")
    sep = "&" if "?" in url else "?"
    return url + sep + "dl=1"


def fetch(entry, staging):
    name = entry["name"]
    zip_path = staging / f"{name}.zip"
    done_path = staging / f"{name}.done"
    if done_path.exists():
        print(f"[skip] {name}: already downloaded ({zip_path.stat().st_size/1024/1024:.0f} MB)", flush=True)
        return True
    url = to_zip_url(entry["url"])
    tmp_path = staging / f"{name}.zip.part"
    offset = tmp_path.stat().st_size if tmp_path.exists() else 0
    headers = {"User-Agent": "Mozilla/5.0 (media-engine)"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
        print(f"[get ] {name} (resuming at {offset/1024/1024:.0f} MB) ...", flush=True)
    else:
        print(f"[get ] {name} ...", flush=True)
    req = urllib.request.Request(url, headers=headers)
    start = time.time()
    total = offset
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        ctype = resp.headers.get("Content-Type", "")
        if "text/html" in ctype:
            body = resp.read(2048).decode("utf-8", "replace")
            print(f"[FAIL] {name}: got HTML not a zip (link dead/limited?): {body[:160]}", flush=True)
            return False
        resumed = resp.status == 206
        if offset and not resumed:
            total = 0  # server ignored Range: start over
            print(f"       {name}: server ignored Range, restarting from 0", flush=True)
        with open(tmp_path, "ab" if (offset and resumed) else "wb") as out:
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                out.write(chunk)
                total += len(chunk)
                if total % (128 * 1024 * 1024) < CHUNK:
                    print(f"       {name}: {total/1024/1024:.0f} MB...", flush=True)
    except Exception as e:
        print(f"[FAIL] {name}: {type(e).__name__}: {e} (part kept for resume)", flush=True)
        return False
    tmp_path.rename(zip_path)
    done_path.write_text(f"{total} bytes in {time.time()-start:.0f}s\n")
    print(f"[ok  ] {name}: {total/1024/1024:.0f} MB in {time.time()-start:.0f}s", flush=True)
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", required=True)
    p.add_argument("--staging", required=True)
    p.add_argument("--only", default=None)
    args = p.parse_args()

    staging = Path(args.staging)
    staging.mkdir(parents=True, exist_ok=True)
    entries = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if args.only:
        entries = [e for e in entries if e["name"] == args.only]

    results = {}
    for entry in entries:
        results[entry["name"]] = fetch(entry, staging)

    print("--- fetch summary ---", flush=True)
    for name, ok in results.items():
        print(f"  {'OK  ' if ok else 'FAIL'} {name}", flush=True)
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()
