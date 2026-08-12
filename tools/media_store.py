"""
Slow Interpolation Media Store -- headless Cloudflare R2 client (Layer 1 of the media architecture, see docs/media-archive-architecture.md).

Object store for all archived media (photos / video / documents / original
works), keyed edition-{N}/{event-slug}/{artist-slug}/{media-type}/{filename}.
Maintains two JSON sidecars per edition inside the bucket:
    edition-{N}/_manifest.json   slim inventory (key/bytes/sha256/source/...)
    edition-{N}/_catalogue.json  manifest + per-asset tags block (Layer 2)

Dual use: importable API (the media-engine web tool and future content agents
call these functions) AND a standalone CLI. Zero Claude tokens during transfer.

Usage:
    py -3.11 tools/media_store.py check
    py -3.11 tools/media_store.py upload --file <path> --key <key> [--no-verify]
    py -3.11 tools/media_store.py download --key <key> --out <path>
    py -3.11 tools/media_store.py list [--prefix nyc-billboard/]
    py -3.11 tools/media_store.py delete --key <key> [--yes]
    py -3.11 tools/media_store.py manifest --edition nyc-billboard [--show]
    py -3.11 tools/media_store.py tag --edition nyc-billboard --key <key> \
        --tag-class artwork --slug example-artist-artwork --set-status confirmed
    py -3.11 tools/media_store.py query --edition nyc-billboard \
        [--artist slug] [--event slug] [--media-type photo] [--asset-class press-kit] \
        [--include-pending]

Credentials: R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_BUCKET
in tools/.env (fallback: repo-root .env; real env vars win over both).
"""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent

R2_ENV_KEYS = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")
CHUNK = 1024 * 1024  # 1 MB streaming chunks


class Conflict(Exception):
    """Optimistic-concurrency failure: the catalogue field changed under us
    between the client's read and this write. Callers must NOT clobber blind."""


_UNSET = object()          # sentinel: "no expected_prev supplied" (distinct from None/"")
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _utc_now():
    """UTC iso stamp for provenance (no external dep)."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_slug(slug):
    """kebab-case, lowercase (CLAUDE.md naming). Returns the normalized slug or
    raises ValueError."""
    s = str(slug).strip().lower()
    if not _SLUG_RE.match(s):
        raise ValueError(f"invalid slug (kebab-case lowercase required): {slug!r}")
    return s


DATE_BASIS_VALUES = frozenset({
    "exif",          # photo, EXIF DateTimeOriginal (incl. the 0x8769 sub-IFD)
    "container",     # video, MP4/MOV format.tags.creation_time
    "filename",      # parsed out of the filename
    "folder-label",  # the photographer's own day-folder label (beats EXIF, see learnings.md)
    "event",         # the event's registry date (contributed assets have no reader)
    "inferred",      # a judgement between conflicting signals -- flagged for correction
    "mtime",         # LAST RESORT: file mtime. For a zip delivery this is the DOWNLOAD date.
})

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_date(value):
    """ISO calendar date, and a REAL one (rejects 2026-02-31). Returns it or raises
    ValueError. Kept strict because a date is the one tag people sort and group by,
    so a malformed one is silently corrupting rather than loudly broken."""
    s = str(value).strip()
    if not _ISO_DATE_RE.match(s):
        raise ValueError(f"date must be YYYY-MM-DD: {value!r}")
    from datetime import date as _date
    y, m, d = (int(p) for p in s.split("-"))
    try:
        _date(y, m, d)
    except ValueError as exc:
        raise ValueError(f"not a real calendar date: {value!r} ({exc})") from exc
    return s


def _append_provenance(record, actor, field, frm, to, reason=None):
    """Record who/what/when/why of one catalogue mutation, in the asset record
    itself so provenance travels with the asset (survives, per-asset)."""
    entry = {"ts": _utc_now(), "actor": actor, "field": field, "from": frm, "to": to}
    if reason:
        entry["reason"] = reason
    record.setdefault("provenance", []).append(entry)
    return entry


def _venue_for_event(catalogue, event):
    """The venue an event happened at, from the catalogue event registry (or None)."""
    if not event:
        return None
    for e in catalogue.get("events", []):
        if isinstance(e, dict) and e.get("slug") == event:
            return e.get("venue")
    return None


# ---------------------------------------------------------------- env / client

def load_env():
    """Manual .env parse (no python-dotenv). tools/.env first, then repo root.
    Real environment variables always win."""
    merged = {}
    for env_path in (TOOLS_DIR / ".env", REPO_ROOT / ".env"):
        if not env_path.is_file():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                merged.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    for k in list(merged):
        if os.environ.get(k):
            merged[k] = os.environ[k]
    for k in os.environ:
        merged.setdefault(k, os.environ[k])
    return merged


def missing_r2_keys(env=None):
    env = env or load_env()
    return [k for k in R2_ENV_KEYS if not env.get(k)]


def r2_client(env=None):
    """boto3 S3 client against the R2 endpoint (memo-spec config)."""
    env = env or load_env()
    missing = missing_r2_keys(env)
    if missing:
        raise SystemExit(
            "R2 credentials missing: " + ", ".join(missing)
            + "\nAdd them to tools/.env (see docs/media-archive-provisioning.md)."
        )
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        raise SystemExit("boto3 not installed for this interpreter. Run: py -3.11 -m pip install boto3")
    return boto3.client(
        "s3",
        endpoint_url=f"https://{env['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=env["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=env["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4", retries={"max_attempts": 8, "mode": "adaptive"}),
        region_name="auto",
    )


def bucket_name(env=None):
    return (env or load_env()).get("R2_BUCKET", "slow-interpolation-media")


def explain_client_error(exc):
    """Map the common boto3 ClientError codes to plain-English fixes."""
    code = ""
    try:
        code = exc.response.get("Error", {}).get("Code", "")
    except Exception:
        pass
    hints = {
        "InvalidAccessKeyId": "R2_ACCESS_KEY_ID is wrong. Use the S3 Access Key ID shown when the API token was created (not the token value).",
        "SignatureDoesNotMatch": "R2_SECRET_ACCESS_KEY is wrong (or system clock skew). Re-copy the S3 Secret Access Key; check Windows clock sync.",
        "AccessDenied": "Token lacks permission on this bucket. Recreate it with Object Read & Write scoped to the bucket.",
        "NoSuchBucket": "Bucket not found. Check R2_BUCKET matches the bucket name exactly and R2_ACCOUNT_ID is your account id (from the R2 endpoint URL).",
        "404": "Bucket or key not found. Check R2_BUCKET / R2_ACCOUNT_ID.",
    }
    hint = hints.get(code, "")
    return f"{code or type(exc).__name__}: {exc}" + (f"\n  FIX: {hint}" if hint else "")


def check_connection(env=None, quiet=False):
    """head_bucket preflight. Returns (ok, message)."""
    env = env or load_env()
    missing = missing_r2_keys(env)
    if missing:
        msg = ("R2 credentials missing: " + ", ".join(missing)
               + " -- add them to tools/.env")
        if not quiet:
            print("R2 FAIL: " + msg)
        return False, msg
    try:
        client = r2_client(env)
        client.head_bucket(Bucket=bucket_name(env))
        msg = f"R2 OK: bucket '{bucket_name(env)}' reachable"
        if not quiet:
            print(msg)
        return True, msg
    except Exception as e:
        msg = explain_client_error(e)
        if not quiet:
            print("R2 FAIL: " + msg)
        return False, msg


# ---------------------------------------------------------------- core ops

def sha256_file(path):
    """Streaming sha256, 1 MB chunks (OneDrive-friendly: open, read, close)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def guess_content_type(path_or_key):
    ext = Path(str(path_or_key)).suffix.lower()
    return {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
        ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
        ".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm",
        ".pdf": "application/pdf", ".json": "application/json",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }.get(ext, "application/octet-stream")


def upload(path, key, sha256=None, verify=True, client=None, env=None, extra_metadata=None):
    """Upload one file. Stores sha256 as object metadata; optional round-trip verify.
    Returns dict {key, bytes, sha256, etag}."""
    env = env or load_env()
    client = client or r2_client(env)
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    digest = sha256 or sha256_file(path)
    size = path.stat().st_size
    metadata = {"sha256": digest}
    if extra_metadata:
        metadata.update({str(k): str(v) for k, v in extra_metadata.items()})
    # Managed transfer: automatic multipart above 256 MB (single put_object caps
    # at 5 GB and large video files exceed it), with parallel parts + retries.
    from boto3.s3.transfer import TransferConfig
    # Conservative settings: sequential parts + small chunks survive fragile
    # home-line connections far better than parallel 64MB parts (observed:
    # multi-minute transfers dying with SSL resets mid-multipart, 2026-07-21).
    transfer_cfg = TransferConfig(
        multipart_threshold=64 * 1024 * 1024,
        multipart_chunksize=32 * 1024 * 1024,
        max_concurrency=2,
    )
    client.upload_file(
        str(path), bucket_name(env), key,
        ExtraArgs={"ContentType": guess_content_type(path), "Metadata": metadata},
        Config=transfer_cfg,
    )
    result = {"key": key, "bytes": size, "sha256": digest}
    if verify:
        head = client.head_object(Bucket=bucket_name(env), Key=key)
        remote_size = head.get("ContentLength", -1)
        remote_sha = head.get("Metadata", {}).get("sha256", "")
        if remote_size != size or remote_sha != digest:
            raise RuntimeError(
                f"verify failed for {key}: local {size}B/{digest[:12]} vs remote {remote_size}B/{remote_sha[:12]}"
            )
        result["verified"] = True
    return result


def download(key, out_path, client=None, env=None):
    """Download one object to out_path. Returns dict {key, bytes, sha256}."""
    env = env or load_env()
    client = client or r2_client(env)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    client.download_file(bucket_name(env), key, str(out_path))
    return {"key": key, "bytes": out_path.stat().st_size, "sha256": sha256_file(out_path)}


def list_objects(prefix="", client=None, env=None):
    """List objects under a prefix. Returns [{key, bytes, modified}]."""
    env = env or load_env()
    client = client or r2_client(env)
    out = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket_name(env), Prefix=prefix):
        for obj in page.get("Contents", []):
            out.append({
                "key": obj["Key"],
                "bytes": obj["Size"],
                "modified": obj["LastModified"].strftime("%Y-%m-%d %H:%M:%S"),
            })
    return out


def delete(key, client=None, env=None):
    env = env or load_env()
    client = client or r2_client(env)
    client.delete_object(Bucket=bucket_name(env), Key=key)
    return {"deleted": key}


def presign(key, ttl=3600, client=None, env=None):
    """Short-TTL presigned GET URL for the private master bucket. Seekable
    (supports Range), so ffmpeg/browsers can stream or grab frames remotely."""
    env = env or load_env()
    client = client or r2_client(env)
    return client.generate_presigned_url(
        "get_object", Params={"Bucket": bucket_name(env), "Key": key},
        ExpiresIn=int(ttl))


def extract_frames(key, out_dir, times=None, every=None, ttl=3600, env=None):
    """Extract still frames from a video WITHOUT downloading it: ffmpeg seeks
    a presigned URL via HTTP range reads. times = list like ["0:03", "1:10"];
    every = seconds between frames (mutually exclusive). Returns saved paths."""
    import subprocess
    if not (times or every):
        raise ValueError("provide times=[...] or every=N")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    url = presign(key, ttl, env=env)
    stem = Path(key).stem
    saved = []
    if times:
        for t in times:
            safe_t = str(t).replace(":", "m")
            out = out_dir / f"{stem}_{safe_t}.jpg"
            subprocess.run(["ffmpeg", "-y", "-ss", str(t), "-i", url,
                            "-frames:v", "1", "-q:v", "3", str(out)],
                           capture_output=True, timeout=300, check=True)
            saved.append(str(out))
    else:
        out_pattern = out_dir / f"{stem}_%04d.jpg"
        subprocess.run(["ffmpeg", "-y", "-i", url,
                        "-vf", f"fps=1/{int(every)}", "-q:v", "3",
                        str(out_pattern)], capture_output=True,
                       timeout=1800, check=True)
        saved = [str(p) for p in sorted(out_dir.glob(f"{stem}_*.jpg"))]
    return saved


def download_batch(out_dir, prefix=None, keys=None, client=None, env=None):
    """Download many objects reusing ONE client/session. Provide prefix OR keys.
    Skips files that already exist locally with the right size."""
    env = env or load_env()
    client = client or r2_client(env)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if keys is None:
        if not prefix:
            raise ValueError("provide prefix or keys")
        keys = [o["key"] for o in list_objects(prefix, client, env)
                if not o["key"].endswith(".json")]
    results = []
    for key in keys:
        target = out_dir / Path(key).name
        try:
            head = client.head_object(Bucket=bucket_name(env), Key=key)
            size = head["ContentLength"]
            if target.exists() and target.stat().st_size == size:
                results.append({"key": key, "status": "exists", "path": str(target)})
                print(f"[skip] {key} (already local)", flush=True)
                continue
            client.download_file(bucket_name(env), key, str(target))
            results.append({"key": key, "status": "ok", "path": str(target)})
            print(f"[ok  ] {key} -> {target} ({size/1048576:.1f} MB)", flush=True)
        except Exception as e:
            results.append({"key": key, "status": "failed", "error": str(e)})
            print(f"[FAIL] {key}: {e}", flush=True)
    return results


# ---------------------------------------------------------------- publish (two-bucket)

PUBLIC_ENV_KEYS = ("R2_PUBLIC_BUCKET", "R2_PUBLIC_ACCESS_KEY_ID",
                   "R2_PUBLIC_SECRET_ACCESS_KEY", "R2_PUBLIC_DEV_URL")


def missing_public_keys(env=None):
    env = env or load_env()
    return [k for k in PUBLIC_ENV_KEYS if not env.get(k)]


def public_client(env=None):
    """boto3 client for the PUBLIC bucket (separate scoped token)."""
    env = env or load_env()
    missing = missing_public_keys(env)
    if missing:
        raise SystemExit("public-bucket credentials missing: " + ", ".join(missing)
                         + "\nProvision slow-interpolation-media-public + token first (see Layer 3 memo).")
    import boto3
    from botocore.config import Config
    return boto3.client(
        "s3",
        endpoint_url=f"https://{env['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=env["R2_PUBLIC_ACCESS_KEY_ID"],
        aws_secret_access_key=env["R2_PUBLIC_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4", retries={"max_attempts": 8, "mode": "adaptive"}),
        region_name="auto",
    )


def _catalogue_record(catalogue, key):
    for rec in catalogue.get("assets", []):
        if rec.get("key") == key:
            return rec
    return None


def _faststart_copy(src_path, out_path):
    """Lossless remux with the moov atom up front (web-optimized DERIVED copy;
    the archived original is never modified)."""
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-i", str(src_path), "-c", "copy",
                    "-movflags", "+faststart", str(out_path)],
                   capture_output=True, timeout=1800, check=True)


def publish(key, edition=None, env=None):
    """Copy one asset from the private master to the public bucket and record
    the permanent URL in the catalogue. Default-private posture: publishing is
    always per-asset and deliberate.

    Videos publish as a derived faststart copy under web/{key}; originals are
    untouched. Transfer streams through this machine (the master and public
    tokens are separately scoped, so server-side CopyObject is unavailable)."""
    import tempfile
    env = env or load_env()
    edition = edition or key.split("/", 1)[0]
    master = r2_client(env)
    pub = public_client(env)
    catalogue = read_catalogue(edition, master, env)
    record = _catalogue_record(catalogue, key)
    if record is None:
        raise KeyError(f"asset not in catalogue: {key}")
    media_type = (record.get("tags") or {}).get("media_type") or record.get("media_type")

    with tempfile.TemporaryDirectory() as td:
        local = Path(td) / Path(key).name
        master.download_file(bucket_name(env), key, str(local))
        dest_key = key
        upload_path = local
        if media_type == "video":
            web = Path(td) / ("web-" + Path(key).name)
            _faststart_copy(local, web)
            dest_key = f"web/{key}"
            upload_path = web
        with open(upload_path, "rb") as f:
            pub.put_object(Bucket=env["R2_PUBLIC_BUCKET"], Key=dest_key, Body=f,
                           ContentType=guess_content_type(upload_path),
                           Metadata={"sha256": sha256_file(upload_path)})

    public_url = env["R2_PUBLIC_DEV_URL"].rstrip("/") + "/" + dest_key
    tags = record.setdefault("tags", {})
    tags["public"] = True
    record["public_url"] = public_url
    tags["public_url"] = public_url
    write_catalogue(edition, catalogue, master, env)
    return {"key": key, "public_key": dest_key, "public_url": public_url}


def unpublish(key, edition=None, env=None):
    """Remove an asset from the public bucket and flip its catalogue tags."""
    env = env or load_env()
    edition = edition or key.split("/", 1)[0]
    master = r2_client(env)
    pub = public_client(env)
    catalogue = read_catalogue(edition, master, env)
    record = _catalogue_record(catalogue, key)
    if record is None:
        raise KeyError(f"asset not in catalogue: {key}")
    media_type = (record.get("tags") or {}).get("media_type") or record.get("media_type")
    dest_key = f"web/{key}" if media_type == "video" else key
    pub.delete_object(Bucket=env["R2_PUBLIC_BUCKET"], Key=dest_key)
    tags = record.setdefault("tags", {})
    tags["public"] = False
    tags.pop("public_url", None)
    record.pop("public_url", None)
    write_catalogue(edition, catalogue, master, env)
    return {"key": key, "unpublished": dest_key}


def published(edition, env=None):
    """List all public assets in an edition's catalogue."""
    catalogue = read_catalogue(edition)
    return [r for r in catalogue.get("assets", [])
            if (r.get("tags") or {}).get("public")]


# ---------------------------------------------------------------- manifest / catalogue

def _read_json_object(key, client, env):
    try:
        resp = client.get_object(Bucket=bucket_name(env), Key=key)
        return json.loads(resp["Body"].read().decode("utf-8"))
    except client.exceptions.NoSuchKey:
        return None
    except Exception as e:
        code = getattr(e, "response", {}).get("Error", {}).get("Code", "") if hasattr(e, "response") else ""
        if code in ("NoSuchKey", "404"):
            return None
        raise


def _write_json_object(key, payload, client, env):
    body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    client.put_object(Bucket=bucket_name(env), Key=key, Body=body,
                      ContentType="application/json")
    return {"key": key, "bytes": len(body)}


def manifest_key(edition):
    return f"{edition}/_manifest.json"


def catalogue_key(edition):
    return f"{edition}/_catalogue.json"


def read_manifest(edition, client=None, env=None):
    env = env or load_env()
    client = client or r2_client(env)
    return _read_json_object(manifest_key(edition), client, env) or {
        "edition": edition, "generated": "", "assets": []}


def write_manifest(edition, manifest, client=None, env=None):
    env = env or load_env()
    client = client or r2_client(env)
    return _write_json_object(manifest_key(edition), manifest, client, env)


def read_catalogue(edition, client=None, env=None):
    env = env or load_env()
    client = client or r2_client(env)
    return _read_json_object(catalogue_key(edition), client, env) or {
        "edition": edition, "generated": "", "assets": []}


def write_catalogue(edition, catalogue, client=None, env=None):
    env = env or load_env()
    client = client or r2_client(env)
    return _write_json_object(catalogue_key(edition), catalogue, client, env)


# --- compare-and-swap catalogue writes -------------------------------------------
# write_catalogue above is a BLIND PUT. The deployed Deno write face
# (packages/site/supabase/functions/glance/_catalogue.ts) has always used ETag/If-Match,
# so an offline Python pass and a live founder edit through Glance in the same window
# meant one of them was silently lost. These three functions are the Python twin.
# Use catalogue_rmw for ANY batch mutation; keep write_catalogue for ingest finalize,
# which owns the file for the length of its run.

class StaleCatalogue(RuntimeError):
    """The catalogue moved under us: someone else wrote between our read and our PUT."""


def read_catalogue_versioned(edition, client=None, env=None):
    """(catalogue, etag) for compare-and-swap writes.

    Refuses a weak (`W/"..."`) or multipart-shaped (`"hash-N"`) validator rather than
    degrading to blind-PUT semantics: If-Match needs a strong validator, and the Deno
    side hit exactly this -- its fetch advertised gzip, Cloudflare returned a weak tag,
    and every conditional PUT 412'd forever (_catalogue.ts:36-46). boto3 does not request
    compression so it gets the strong tag, but assert it rather than assume it."""
    env = env or load_env()
    client = client or r2_client(env)
    try:
        resp = client.get_object(Bucket=bucket_name(env), Key=catalogue_key(edition))
    except Exception as e:
        code = getattr(e, "response", {}).get("Error", {}).get("Code", "") if hasattr(e, "response") else ""
        if code in ("NoSuchKey", "404"):
            return {"edition": edition, "generated": "", "assets": []}, None
        raise
    etag = (resp.get("ETag") or "").strip()
    if etag.startswith("W/"):
        raise StaleCatalogue(f"weak ETag {etag!r}; If-Match cannot be trusted")
    if re.match(r'^"[0-9a-f]+-\d+"$', etag):
        raise StaleCatalogue(f"multipart-shaped ETag {etag!r}; If-Match cannot be trusted")
    return json.loads(resp["Body"].read().decode("utf-8")), etag


def write_catalogue_if_match(edition, catalogue, etag, client=None, env=None):
    """Conditional PUT. Returns the new ETag, or None if someone wrote first (412)."""
    env = env or load_env()
    client = client or r2_client(env)
    body = json.dumps(catalogue, indent=2, ensure_ascii=False).encode("utf-8")
    kwargs = {"Bucket": bucket_name(env), "Key": catalogue_key(edition),
              "Body": body, "ContentType": "application/json"}
    if etag:
        kwargs["IfMatch"] = etag
    try:
        resp = client.put_object(**kwargs)
    except Exception as e:
        code = getattr(e, "response", {}).get("Error", {}).get("Code", "") if hasattr(e, "response") else ""
        status = getattr(e, "response", {}).get("ResponseMetadata", {}).get("HTTPStatusCode") if hasattr(e, "response") else None
        if code in ("PreconditionFailed", "412") or status == 412:
            return None
        raise
    return (resp.get("ETag") or "").strip()


def catalogue_rmw(edition, mutate, attempts=10, client=None, env=None):
    """Read -> mutate -> If-Match PUT, REPLAYING mutate against the fresher catalogue
    on a 412. Python twin of _catalogue.ts rmw().

    `mutate(catalogue)` is called with the catalogue and may return a value, which is
    passed back to the caller on success.

    A Conflict raised BY mutate propagates IMMEDIATELY and is never retried -- that is
    a real answer about a specific asset (expected_prev tripped), and replaying it would
    clobber the very change the guard exists to protect."""
    import random
    import time as _time
    env = env or load_env()
    client = client or r2_client(env)
    last = None
    for i in range(attempts):
        catalogue, etag = read_catalogue_versioned(edition, client, env)
        result = mutate(catalogue)          # Conflict from here is intentional, let it fly
        new_etag = write_catalogue_if_match(edition, catalogue, etag, client, env)
        if new_etag is not None:
            return result, new_etag
        last = etag
        _time.sleep((min(100 * (2 ** i), 2000) + random.uniform(0, 250)) / 1000.0)
    raise StaleCatalogue(
        f"catalogue contended for {attempts} attempts (last etag {last!r}); nothing written")


def manifest_record_from(record):
    """Slim Layer-1 manifest view of a full catalogue record."""
    tags = record.get("tags", {})
    return {
        "key": record["key"],
        "event": tags.get("event"),
        "artist": (tags.get("artists") or [None])[0],
        "media_type": tags.get("media_type"),
        "bytes": record.get("bytes"),
        "sha256": record.get("sha256"),
        "source": record.get("source", ""),
        "ingested": record.get("ingested", ""),
    }


def upsert_asset_local(catalogue, record):
    """Append/replace a record (by key) in a catalogue dict. In-place; returns catalogue."""
    assets = catalogue.setdefault("assets", [])
    for i, existing in enumerate(assets):
        if existing.get("key") == record["key"]:
            assets[i] = record
            break
    else:
        assets.append(record)
    return catalogue


def add_asset(edition, record, client=None, env=None):
    """Append/replace one asset record in BOTH remote sidecars (read-modify-write).
    For bulk ingest prefer batching locally and one write_* at finalize."""
    env = env or load_env()
    client = client or r2_client(env)
    catalogue = read_catalogue(edition, client, env)
    upsert_asset_local(catalogue, record)
    write_catalogue(edition, catalogue, client, env)
    manifest = read_manifest(edition, client, env)
    upsert_asset_local(manifest, manifest_record_from(record))
    write_manifest(edition, manifest, client, env)
    return record["key"]


def set_tag_status(edition, key, tag_class, slug, status, client=None, env=None):
    """Review write-back: flip one tag's status (pending -> confirmed) or reject
    (status='rejected' removes the tag). tag_class: 'artworks' | 'persons' | 'scene'.
    Returns the updated record or raises KeyError."""
    if status not in ("pending", "confirmed", "rejected"):
        raise ValueError(f"bad status: {status}")
    env = env or load_env()
    client = client or r2_client(env)
    catalogue = read_catalogue(edition, client, env)
    target = None
    for record in catalogue.get("assets", []):
        if record.get("key") == key:
            target = record
            break
    if target is None:
        raise KeyError(f"asset not in catalogue: {key}")
    tags = target.setdefault("tags", {})
    entries = tags.get(tag_class) or []
    hit = False
    kept = []
    for entry in entries:
        if isinstance(entry, dict) and entry.get("slug") == slug:
            hit = True
            if status == "rejected":
                continue  # drop it
            entry["status"] = status
        kept.append(entry)
    if not hit:
        raise KeyError(f"tag {tag_class}/{slug} not on {key}")
    tags[tag_class] = kept
    write_catalogue(edition, catalogue, client, env)
    return target


# ---------------------------------------------------------------- event writes (Glance v2)

def set_event(edition, key, event, actor="glance-write", reason=None,
              expected_prev=_UNSET, catalogue=None, client=None, env=None):
    """Reassign (or clear) one asset's event tag. Gated catalogue write:
    fresh read -> optimistic check -> mutate -> provenance -> write.

    event: an event slug, or None/"" to clear the event.
    expected_prev: if supplied, the event value the caller last saw; a mismatch
      raises Conflict (a concurrent change happened -- never clobber blind).
    catalogue: if provided, mutate THIS in-memory catalogue in place and do NOT
      touch R2 (the caller owns persistence -- used by the write server's in-memory
      + background-flush path so saves respond instantly). If None, do the classic
      fresh read + write (CLI path).
    Raises KeyError (unknown key), ValueError (bad slug), Conflict (stale write).
    Returns the updated record (unchanged record on a no-op)."""
    new_event = _validate_slug(event) if event else None
    managed = catalogue is not None
    if not managed:
        env = env or load_env()
        client = client or r2_client(env)
        catalogue = read_catalogue(edition, client, env)
    target = None
    for record in catalogue.get("assets", []):
        if record.get("key") == key:
            target = record
            break
    if target is None:
        raise KeyError(f"asset not in catalogue: {key}")
    tags = target.setdefault("tags", {})
    prev = tags.get("event") or None
    if expected_prev is not _UNSET and prev != (expected_prev or None):
        raise Conflict(
            f"event changed under us on {key}: expected {expected_prev!r}, found {prev!r}")
    if prev == new_event:
        return target                       # no-op -> skip a pointless write
    tags["event"] = new_event
    _append_provenance(target, actor, "event", prev, new_event, reason)
    # VENUE IS NO LONGER MATERIALISED ONTO THE ASSET (founder rule 2026-08-06).
    # This used to copy the registry venue into tags.venue on every event assignment,
    # which produced the split this rule removes: an asset that arrived by INGEST had
    # tags.venue = null (ingest.py has never had a --venue flag) while one assigned
    # through the WRITE FACE carried a copy, so the same event answered two ways
    # depending only on how the asset got there -- 1,072 assets with a venue, 287
    # without. Worse, a copy goes stale silently: correcting a venue in the registry
    # left every previously-written asset asserting the old one.
    # Venue is derived at read time now (_venue_for_event / glance.js venueForEvent),
    # so the registry is the single place it lives, exactly as event-venue-registry.md
    # always claimed.
    if not managed:
        write_catalogue(edition, catalogue, client, env)
    return target


# Registry entry fields the UI + by-venue sort care about, beyond slug.
# Registry entry fields beyond slug. `group` links related events into ONE cluster;
# `order` sequences them within it (Co-Stories: talks first, then AV sets); `near`
# keeps SEPARATE clusters adjacent (Synthetic Histories next to Points of View).
_EVENT_META_FIELDS = ("label", "venue", "date", "description", "kind", "group", "order", "near")


def set_venue(edition, key, venue, actor="glance-write", reason=None,
              expected_prev=_UNSET, catalogue=None, client=None, env=None):
    """Set (or clear) one asset's venue tag. Gated catalogue write, mirrors
    set_event. venue is a display-name STRING (e.g. 'La Galleria delle Arti'),
    not a slug -- it matches the registry venue labels. None/"" clears it.
    catalogue: if provided, mutate it in place and skip R2 (managed mode).
    Raises KeyError (unknown key), Conflict (stale write). Returns the record."""
    new_venue = (str(venue).strip() or None) if venue is not None else None
    managed = catalogue is not None
    if not managed:
        env = env or load_env()
        client = client or r2_client(env)
        catalogue = read_catalogue(edition, client, env)
    target = None
    for record in catalogue.get("assets", []):
        if record.get("key") == key:
            target = record
            break
    if target is None:
        raise KeyError(f"asset not in catalogue: {key}")
    tags = target.setdefault("tags", {})
    prev = tags.get("venue") or None
    if expected_prev is not _UNSET and prev != (expected_prev or None):
        raise Conflict(
            f"venue changed under us on {key}: expected {expected_prev!r}, found {prev!r}")
    if prev == new_venue:
        return target
    tags["venue"] = new_venue
    _append_provenance(target, actor, "venue", prev, new_venue, reason)
    if not managed:
        write_catalogue(edition, catalogue, client, env)
    return target


def set_date(edition, key, date, basis, actor="glance-write", reason=None,
             expected_prev=_UNSET, catalogue=None, client=None, env=None):
    """Set (or clear) one asset's date + date_basis. Gated catalogue write, mirrors
    set_venue. date is 'YYYY-MM-DD' (None/"" clears BOTH fields); basis must be in
    DATE_BASIS_VALUES whenever a date is set.

    `basis` is POSITIONAL and has no default on purpose: a date with no stated
    provenance is precisely the defect this function exists to repair. Writing one
    would recreate it.

    Unlike set_venue this compares the two fields INDEPENDENTLY, because the common
    repair is 'the date happened to be right but the basis was mtime' -- a single
    early-return on date equality would silently swallow that and leave the asset
    claiming a provenance it does not have.

    expected_prev guards on tags.date only (same three-state _UNSET contract as
    set_event / set_venue).
    catalogue: if provided, mutate it in place and skip R2 (managed mode).
    Raises KeyError (unknown key), ValueError (bad date/basis), Conflict (stale write).
    Returns the record."""
    clearing = date is None or str(date).strip() == ""
    if clearing:
        new_date, new_basis = None, None
    else:
        new_date = _validate_date(date)
        if basis not in DATE_BASIS_VALUES:
            raise ValueError(
                f"date_basis must be one of {sorted(DATE_BASIS_VALUES)}: {basis!r}")
        new_basis = basis
    managed = catalogue is not None
    if not managed:
        env = env or load_env()
        client = client or r2_client(env)
        catalogue = read_catalogue(edition, client, env)
    target = None
    for record in catalogue.get("assets", []):
        if record.get("key") == key:
            target = record
            break
    if target is None:
        raise KeyError(f"asset not in catalogue: {key}")
    tags = target.setdefault("tags", {})
    prev_date = tags.get("date") or None
    prev_basis = tags.get("date_basis") or None
    if expected_prev is not _UNSET and prev_date != (expected_prev or None):
        raise Conflict(
            f"date changed under us on {key}: expected {expected_prev!r}, found {prev_date!r}")
    if prev_date == new_date and prev_basis == new_basis:
        return target
    if prev_date != new_date:
        tags["date"] = new_date
        _append_provenance(target, actor, "date", prev_date, new_date, reason)
    if prev_basis != new_basis:
        tags["date_basis"] = new_basis
        _append_provenance(target, actor, "date_basis", prev_basis, new_basis, reason)
    if not managed:
        write_catalogue(edition, catalogue, client, env)
    return target


def set_archived(edition, key, archived=True, actor="glance-write", reason=None,
                 catalogue=None, client=None, env=None):
    """Mark/unmark an asset as archived: it is HIDDEN from the Glance field but the
    original stays in R2, fully retrievable (never a delete). Sets tags.archived.
    Gated write. catalogue: if provided, mutate in place and skip R2 (managed)."""
    managed = catalogue is not None
    if not managed:
        env = env or load_env()
        client = client or r2_client(env)
        catalogue = read_catalogue(edition, client, env)
    target = None
    for record in catalogue.get("assets", []):
        if record.get("key") == key:
            target = record
            break
    if target is None:
        raise KeyError(f"asset not in catalogue: {key}")
    tags = target.setdefault("tags", {})
    prev = bool(tags.get("archived"))
    new = bool(archived)
    if prev == new:
        return target
    if new:
        tags["archived"] = True
    else:
        tags.pop("archived", None)
    _append_provenance(target, actor, "archived", prev, new, reason)
    if not managed:
        write_catalogue(edition, catalogue, client, env)
    return target


def create_event(edition, event, label=None, venue=None, date=None, description=None,
                 kind=None, group=None, order=None, near=None, actor="glance-write",
                 catalogue=None, client=None, env=None):
    """Register (or UPSERT) a named event in the catalogue event registry so an
    empty cluster can exist to drag into before any asset is assigned, and so the
    event->venue mapping has a home (asset tags never carry venue). Re-registering
    an existing slug updates its metadata in place, preserving `created`. `group`
    merges events into one cluster, `order` sequences within it, `near` keeps
    separate clusters adjacent. catalogue: if provided, mutate it in place and skip
    R2 (managed mode). Returns the entry."""
    slug = _validate_slug(event)
    meta = {"label": label or slug, "venue": venue, "date": date,
            "description": description, "kind": kind or "exhibition",
            "group": group, "order": order, "near": near}
    managed = catalogue is not None
    if not managed:
        env = env or load_env()
        client = client or r2_client(env)
        catalogue = read_catalogue(edition, client, env)
    events = catalogue.setdefault("events", [])
    for e in events:
        if isinstance(e, dict) and e.get("slug") == slug:
            changed = False
            for k, v in meta.items():
                if v is not None and e.get(k) != v:
                    e[k] = v
                    changed = True
            if changed:
                e["updated"] = _utc_now()
                if not managed:
                    write_catalogue(edition, catalogue, client, env)
            return e
    entry = {"slug": slug, **meta, "created": _utc_now(), "actor": actor}
    events.append(entry)
    if not managed:
        write_catalogue(edition, catalogue, client, env)
    return entry


def list_events(edition, catalogue=None, client=None, env=None):
    """Registry events unioned with every distinct non-null tags.event, so both
    existing events and freshly-created empty ones appear. Returns
    [{slug, label, venue, date, description, kind, count, registered}] sorted by
    slug. Venue lives only here (never on asset tags), so this is the event->venue
    source the dropdown grouping + the by-venue cluster rule read. catalogue: use
    this in-memory catalogue instead of reading R2 (managed mode)."""
    if catalogue is None:
        catalogue = read_catalogue(edition, client, env)
    reg = {}
    for e in catalogue.get("events", []):
        if isinstance(e, dict) and e.get("slug"):
            reg[e["slug"]] = {
                "slug": e["slug"], "label": e.get("label") or e["slug"],
                "venue": e.get("venue"), "date": e.get("date"),
                "description": e.get("description"), "kind": e.get("kind") or "exhibition",
                "count": 0, "registered": True}
    for record in catalogue.get("assets", []):
        ev = (record.get("tags") or {}).get("event")
        if not ev:
            continue
        if ev not in reg:
            reg[ev] = {"slug": ev, "label": ev, "venue": None, "date": None,
                       "description": None, "kind": "exhibition",
                       "count": 0, "registered": False}
        reg[ev]["count"] += 1
    return sorted(reg.values(), key=lambda r: r["slug"])


def query(edition, filters=None, confirmed_only=True, client=None, env=None):
    """Filter the catalogue locally (zero egress beyond the sidecar itself).
    filters: {event, artist, media_type, asset_class, person, artwork, date, context}.
    confirmed_only: person/artwork matches require status == confirmed."""
    filters = filters or {}
    catalogue = read_catalogue(edition, client, env)
    out = []
    for record in catalogue.get("assets", []):
        tags = record.get("tags", {})
        ok = True
        for fkey, want in filters.items():
            if want in (None, ""):
                continue
            if fkey == "event":
                ok = tags.get("event") == want
            elif fkey == "context":
                ok = tags.get("context") == want
            elif fkey == "artist":
                ok = want in (tags.get("artists") or [])
            elif fkey == "media_type":
                ok = tags.get("media_type") == want
            elif fkey == "asset_class":
                ok = tags.get("asset_class") == want
            elif fkey == "date":
                ok = tags.get("date") == want
            elif fkey in ("person", "artwork"):
                plural = "persons" if fkey == "person" else "artworks"
                entries = tags.get(plural) or []
                ok = any(
                    isinstance(e, dict) and e.get("slug") == want
                    and (not confirmed_only or e.get("status") == "confirmed")
                    for e in entries
                )
            if not ok:
                break
        if ok:
            out.append(record)
    return out


# ---------------------------------------------------------------- CLI

def main():
    p = argparse.ArgumentParser(description="Slow Interpolation media store (Cloudflare R2)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="verify credentials + bucket reachability")

    up = sub.add_parser("upload")
    up.add_argument("--file", required=True)
    up.add_argument("--key", required=True)
    up.add_argument("--no-verify", action="store_true")

    dl = sub.add_parser("download")
    dl.add_argument("--key", required=True)
    dl.add_argument("--out", required=True)

    ls = sub.add_parser("list")
    ls.add_argument("--prefix", default="")

    rm = sub.add_parser("delete")
    rm.add_argument("--key", required=True)
    rm.add_argument("--yes", action="store_true")

    mf = sub.add_parser("manifest")
    mf.add_argument("--edition", required=True)
    mf.add_argument("--show", action="store_true")

    tg = sub.add_parser("tag")
    tg.add_argument("--edition", required=True)
    tg.add_argument("--key", required=True)
    tg.add_argument("--tag-class", required=True, choices=["artworks", "persons", "scene"])
    tg.add_argument("--slug", required=True)
    tg.add_argument("--set-status", required=True, choices=["pending", "confirmed", "rejected"])

    se = sub.add_parser("set-event", help="reassign/clear an asset's event tag (gated write)")
    se.add_argument("--edition", required=True)
    se.add_argument("--key", required=True)
    se.add_argument("--event", default="", help="event slug, or empty to clear")
    se.add_argument("--reason")
    se.add_argument("--actor", default="cli")

    sv = sub.add_parser("set-venue", help="set/clear an asset's venue tag (gated write)")
    sv.add_argument("--edition", required=True)
    sv.add_argument("--key", required=True)
    sv.add_argument("--venue", default="", help="venue name, or empty to clear")
    sv.add_argument("--reason")
    sv.add_argument("--actor", default="cli")

    ce = sub.add_parser("create-event", help="register/upsert a named event (empty cluster)")
    ce.add_argument("--edition", required=True)
    ce.add_argument("--event", required=True)
    ce.add_argument("--label")
    ce.add_argument("--venue")
    ce.add_argument("--date")
    ce.add_argument("--description")
    ce.add_argument("--kind", default="exhibition",
                    choices=["exhibition", "non-exhibition", "preview"])
    ce.add_argument("--actor", default="cli")

    le = sub.add_parser("list-events", help="registry + distinct event tags with counts")
    le.add_argument("--edition", required=True)

    ps = sub.add_parser("presign")
    ps.add_argument("--key", required=True)
    ps.add_argument("--ttl", type=int, default=3600)

    fr = sub.add_parser("frames")
    fr.add_argument("--key", required=True)
    fr.add_argument("--times", help="comma-separated timestamps, e.g. 0:03,1:10")
    fr.add_argument("--every", type=int, help="seconds between frames")
    fr.add_argument("--out", required=True)

    db = sub.add_parser("download-batch")
    db.add_argument("--prefix")
    db.add_argument("--keys-file", help="file with one key per line")
    db.add_argument("--out", required=True)

    pb = sub.add_parser("publish")
    pb.add_argument("--key", required=True)
    pb.add_argument("--edition", default=None)

    upb = sub.add_parser("unpublish")
    upb.add_argument("--key", required=True)
    upb.add_argument("--edition", default=None)

    pbl = sub.add_parser("published")
    pbl.add_argument("--edition", required=True)

    q = sub.add_parser("query")
    q.add_argument("--edition", required=True)
    q.add_argument("--event")
    q.add_argument("--context")
    q.add_argument("--artist")
    q.add_argument("--person")
    q.add_argument("--artwork")
    q.add_argument("--media-type", dest="media_type")
    q.add_argument("--asset-class", dest="asset_class")
    q.add_argument("--date")
    q.add_argument("--include-pending", action="store_true")

    args = p.parse_args()

    try:
        if args.cmd == "check":
            ok, _ = check_connection()
            sys.exit(0 if ok else 1)

        elif args.cmd == "upload":
            res = upload(args.file, args.key, verify=not args.no_verify)
            print(json.dumps(res, indent=2))

        elif args.cmd == "download":
            res = download(args.key, args.out)
            print(json.dumps(res, indent=2))

        elif args.cmd == "list":
            objs = list_objects(args.prefix)
            total = sum(o["bytes"] for o in objs)
            for o in objs:
                print(f"{o['bytes']:>12,}  {o['modified']}  {o['key']}")
            print(f"-- {len(objs)} objects, {total/1024/1024:.1f} MB total")

        elif args.cmd == "delete":
            if not args.yes:
                confirm = input(f"Delete '{args.key}' from bucket? [y/N] ").strip().lower()
                if confirm != "y":
                    print("aborted")
                    return
            print(json.dumps(delete(args.key), indent=2))

        elif args.cmd == "manifest":
            m = read_manifest(args.edition)
            if args.show:
                print(json.dumps(m, indent=2, ensure_ascii=False))
            else:
                print(f"edition={m.get('edition')} generated={m.get('generated') or '(never)'} assets={len(m.get('assets', []))}")

        elif args.cmd == "tag":
            record = set_tag_status(args.edition, args.key, args.tag_class,
                                    args.slug, args.set_status)
            print(json.dumps(record, indent=2, ensure_ascii=False))

        elif args.cmd == "set-event":
            record = set_event(args.edition, args.key, args.event,
                               actor=args.actor, reason=args.reason)
            tags = record.get("tags", {})
            print(f"{args.key}  event -> {tags.get('event')!r}")
            print(json.dumps(record.get("provenance", [])[-1:], indent=2, ensure_ascii=False))

        elif args.cmd == "set-venue":
            record = set_venue(args.edition, args.key, args.venue,
                               actor=args.actor, reason=args.reason)
            tags = record.get("tags", {})
            print(f"{args.key}  venue -> {tags.get('venue')!r}")
            print(json.dumps(record.get("provenance", [])[-1:], indent=2, ensure_ascii=False))

        elif args.cmd == "create-event":
            entry = create_event(args.edition, args.event, label=args.label,
                                 venue=args.venue, date=args.date,
                                 description=args.description, kind=args.kind,
                                 actor=args.actor)
            print(json.dumps(entry, indent=2, ensure_ascii=False))

        elif args.cmd == "list-events":
            rows = list_events(args.edition)
            for r in rows:
                mark = "reg" if r["registered"] else "   "
                venue = r.get("venue") or "-"
                print(f"[{mark}] {r['count']:>4}  {r['slug']:<28}  {venue}")
            print(f"-- {len(rows)} events")

        elif args.cmd == "presign":
            print(presign(args.key, args.ttl))

        elif args.cmd == "frames":
            times = [t.strip() for t in args.times.split(",")] if args.times else None
            saved = extract_frames(args.key, args.out, times=times, every=args.every)
            for p in saved:
                print(p)
            print(f"-- {len(saved)} frame(s) extracted")

        elif args.cmd == "download-batch":
            keys = None
            if args.keys_file:
                keys = [k.strip() for k in Path(args.keys_file).read_text(encoding="utf-8-sig").splitlines() if k.strip()]
            results = download_batch(args.out, prefix=args.prefix, keys=keys)
            ok = sum(1 for r in results if r["status"] in ("ok", "exists"))
            print(f"-- {ok}/{len(results)} downloaded")

        elif args.cmd == "publish":
            print(json.dumps(publish(args.key, args.edition), indent=2))

        elif args.cmd == "unpublish":
            print(json.dumps(unpublish(args.key, args.edition), indent=2))

        elif args.cmd == "published":
            rows = published(args.edition)
            for r in rows:
                print(f"{r['key']}  ->  {r.get('public_url') or (r.get('tags') or {}).get('public_url')}")
            print(f"-- {len(rows)} public assets")

        elif args.cmd == "query":
            filters = {
                "event": args.event, "context": args.context, "artist": args.artist,
                "person": args.person, "artwork": args.artwork,
                "media_type": args.media_type, "asset_class": args.asset_class,
                "date": args.date,
            }
            results = query(args.edition, filters,
                            confirmed_only=not args.include_pending)
            for r in results:
                tags = r.get("tags", {})
                print(f"{r['key']}  [{tags.get('media_type')}/{tags.get('asset_class')}]  {tags.get('caption', '')[:80]}")
            print(f"-- {len(results)} assets matched")

    except SystemExit:
        raise
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        try:
            from botocore.exceptions import ClientError
            if isinstance(e, ClientError):
                sys.exit("ERROR " + explain_client_error(e))
        except ImportError:
            pass
        sys.exit(f"ERROR {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
