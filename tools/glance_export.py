"""glance_export.py -- publish outputs/ as a Glance archive.

The existing gallery.html is one hand-built page listing a filtered slice. It works,
but it cannot answer "what have we actually rendered" -- that is a question about
shape, and 3,000 renders in a vertical list is not a shape you can see.

This emits the four artifacts of the Glance data contract (`glance-contract/1`), so
the whole of outputs/ can be looked at as one field: every render a tile, clustered
by run, reflowing under a query. Glance itself is a separate tool and knows nothing
about this repo; it reads the contract and nothing else.

    python tools/glance_export.py                    # everything, incl. keyframes
    python tools/glance_export.py --no-frames --dest outputs/_glance-renders
    python tools/glance_export.py --limit 400        # quick sample while iterating

Then:

    python <path-to>/glance/serve.py --data outputs/_glance

Thumbnails are cached once in outputs/_glance/thumbs and copied into any other
--dest, so building a second view costs a file copy rather than a re-encode.

Output is written to outputs/_glance/ and is a build artifact: regenerate it, never
edit it. Nothing here reads or writes any render; originals are untouched.

Requires Pillow, and ffmpeg on PATH only for videos that have no cached poster.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
POSTERS = OUTPUTS / "_gallery" / "posters"
DEST = OUTPUTS / "_glance"
THUMB_CACHE = OUTPUTS / "_glance" / "thumbs"   # shared across every --dest

IMG_EXT = {".png", ".jpg", ".jpeg", ".webp"}
VID_EXT = {".mp4", ".webm", ".mov", ".gif"}

SHEET_SIZE = 4096          # must equal SHEET in glance.js -- UVs are t.x / SHEET
THUMB = 512
# Ceiling on the atlas cell. It was 96, which is the right cell for a THOUSAND
# roughly-square photos and badly wrong for a small field of extreme aspects: a
# 3.18:1 LED-wall strip only got 29px of height out of a 96px cell, so a tile
# displayed at ~400px was a 4.4x upscale of a 93x29 source, i.e. visibly mushy,
# while a sharp 512px copy of the same frame sat unused in thumbs/ next to it.
#
# There is no reason to cap below the source thumbnail: past THUMB the cell would
# be padding, not detail. The min() against SHEET_SIZE // per_row below still
# decides for large fields, so this changes nothing about how a big archive packs
# (418 assets -> 195px, 1048 -> 124px) and simply stops starving the small ones
# (21 assets -> 512px, a 1:1 copy of the thumbnail).
MAX_CELL = THUMB

# Directory names that are scaffolding rather than work: the old gallery's own
# derived assets, deploy staging, harness logs, and this exporter's output. A
# leading underscore is the repo's existing convention for exactly that.
def is_internal(rel: Path) -> bool:
    return any(p.startswith("_") for p in rel.parts)


def slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s or "untitled"


def sha16_of(rel: Path) -> str:
    """Stable id from the repo-relative path.

    The contract allows any stable unique 16-hex id. Path-derived rather than
    content-derived on purpose: content hashing 313 videos at 60-80 MB each would
    read ~20 GB to produce ids nothing here needs to be content-addressed by.
    """
    return hashlib.sha256(rel.as_posix().encode("utf-8")).hexdigest()[:16]


def run_of(rel: Path) -> tuple[str, str]:
    """(cluster, group) for a file, from its directory path.

    A frame sequence lives in `<run>/keyframes/NNNN.png`; the run is the unit worth
    clustering, not the folder literally called "keyframes", which would collapse
    every sequence in the repo into one meaningless blob.
    """
    parts = [p for p in rel.parts[:-1] if p not in ("keyframes", "frames", "staging")]
    if not parts:
        return "root", "root"
    return slug(parts[-1]), slug(parts[0])


# No \b after the letter: these names are NY1087B_090226, and "_" is a word
# character, so there is no word boundary between the letter and the underscore.
# With \b the pattern matched nothing at all, and every file still landed in a
# plausible-looking cluster via the portrait fallback below -- which is exactly
# the kind of silent miss that reads as a working feature.
SCREEN_RE = re.compile(r"NY1087\s*([ABC])(?![A-Z0-9])", re.I)


def screen_of(rel: Path, dims: tuple[int, int] | None) -> str:
    """Which LED wall this file is FOR: screen-a, screen-bc, or unassigned.

    THERE ARE THREE WALLS AND ONLY TWO GEOMETRIES. conform.py's SCREENS collapses
    B and C into a single 1728x540 spec because they are physically identical, so
    dimensions can identify wall A and can NEVER separate B from C. That is why
    clustering this field by geometry tops out at two clusters no matter how the
    layout is tuned -- the third cluster does not exist in the pixels.

    The screen id survives in one place only: the delivery filename, NY1087A/B/C.

    The b/c in a RENDER name is NOT a screen and must not be read as one. In
    led13_b_realloc_soft vs led13_c_realloc_soft it is an experiment variant
    letter -- the same content at two settings, discussed as such throughout
    quality-first/progress.md. Reading it as a wall would file twelve candidate
    renders under walls nobody has chosen for them yet.

    A portrait file with no NY1087 tag is still wall A, because portrait is a
    geometry only wall A has. A landscape one is genuinely undecided: it is
    conformed to the B/C spec and could go to either, so it says so rather than
    guessing. That honesty is the point of the third cluster.
    """
    m = SCREEN_RE.search(rel.name)
    if m:
        return "screen-a" if m.group(1).upper() == "A" else "screen-bc"
    if dims and dims[0] < dims[1]:
        return "screen-a"
    return "unassigned"


# conform.py stamps "__<screen>_<w>x<h>" onto a delivery file, so the manifest for
# led13_c_realloc_soft__bc_1728x540.mp4 is led13_c_realloc_soft.manifest.json.
CONFORM_SUFFIX_RE = re.compile(r"__[a-z]+_\d+x\d+$", re.I)


def manifest_of(f: Path) -> Path | None:
    """The run manifest for a render, following a conform suffix back to its parent."""
    for stem in (f.stem, CONFORM_SUFFIX_RE.sub("", f.stem)):
        m = f.with_name(stem + ".manifest.json")
        if m.is_file():
            return m
    return None


def lora_of(f: Path) -> str | None:
    """The STYLE LoRA a render was made with, as a short label, or None if unknown.

    This is the sub-order key inside a cluster: outputs sharing a LoRA sit together
    instead of being scattered by sha, so a set you want to compare reads as a set.

    `style_lora_path` is the one that matters. `lightning_lora` is the 4-step speed
    adapter and is identical on every render here, so grouping by it would put
    everything in one bucket and look like the feature was not working.

    Returns None rather than guessing when there is no manifest, which is a real
    gap and not a rare one: a conformed DELIVERY file is copied and renamed out of
    its run, so nine of them carry no provenance at all, and the led16 renders were
    written without a manifest. Unknowns group together as their own honest block.
    """
    m = manifest_of(f)
    if not m:
        return None
    try:
        p = json.loads(m.read_text(encoding="utf-8")).get("style_lora_path")
    except Exception:
        return None
    if not p:
        return None
    return Path(p).stem          # models/loras/Thomas_Cole_epoch_10.safetensors -> Thomas_Cole_epoch_10


def generated_ts(f: Path) -> float:
    """When a render was GENERATED. Manifest first: file mtime is rewritten by
    every volume sync, so a date window on mtime would sweep in years-old work
    that happened to be re-downloaded this week."""
    man = f.with_suffix("").with_suffix(".manifest.json")
    if not man.is_file():
        man = f.with_name(f.stem + ".manifest.json")
    if man.is_file():
        try:
            import json as _json
            from datetime import datetime as _dt
            ts = _json.loads(man.read_text(encoding="utf-8")).get("started_at_utc")
            if ts:
                return _dt.fromisoformat(ts).timestamp()
        except Exception:
            pass
    return f.stat().st_mtime


PROBE_CACHE = OUTPUTS / "_gallery" / "probe-cache.json"
_probe: dict | None = None


def dimensions(f: Path) -> tuple[int, int] | None:
    """(width, height) of a video, from gallery.py's probe cache, else ffprobe.

    Filenames are the wrong key for "is this at wall spec". conform.py stamps the
    geometry into the name for a plain render, but a client-named delivery file
    carries no suffix at all, and on 2026-08-11 a name-based filter found 1 of the
    6 files that are actually 912x2736. Dimensions cannot lie.
    """
    global _probe
    if _probe is None:
        try:
            _probe = json.loads(PROBE_CACHE.read_text(encoding="utf-8"))
        except Exception:
            _probe = {}
    rel = f.relative_to(ROOT) if ROOT in f.parents else f
    hit = (_probe.get(str(f)) or _probe.get(str(rel))
           or _probe.get(str(rel).replace("/", chr(92)))
           or _probe.get(rel.as_posix()))
    if hit:
        i = hit.get("info") or {}
        if i.get("width"):
            return int(i["width"]), int(i["height"])
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height", "-of", "csv=p=0:s=x", str(f)],
            capture_output=True, text=True, timeout=30).stdout.strip()
        w, hgt = out.split("x")[:2]
        return int(w), int(hgt)
    except Exception:
        return None


def collect(include_frames: bool, limit: int | None,
            include: list[str] | None = None,
            since_days: float | None = None,
            exclude_keys: set[str] | None = None,
            match: list[str] | None = None,
            specs: set[tuple[int, int]] | None = None):
    import time as _time
    cutoff = (_time.time() - since_days * 86400) if since_days else None
    items = []
    for f in sorted(OUTPUTS.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(OUTPUTS)
        if is_internal(rel):
            continue
        # Curated scope: keep only assets under the named prefixes. This is how
        # a dedicated exhibition field is built without duplicating any file:
        # same originals, same thumb cache, a different catalogue.
        if include and not any(rel.as_posix().startswith(pre) for pre in include):
            continue
        ext = f.suffix.lower()
        if ext not in IMG_EXT and ext not in VID_EXT:
            continue
        is_frame = "keyframes" in rel.parts or "frames" in rel.parts
        if is_frame and not include_frames:
            continue
        if cutoff and generated_ts(f) < cutoff:
            continue
        if exclude_keys and rel.as_posix() in exclude_keys:
            continue
        # Delivery-spec scope. `--include` is a prefix, so it cannot select the
        # conform.py suffix that actually marks a file as wall-ready; this is a
        # glob over the whole relative path and can.
        if match and not any(fnmatch(rel.as_posix(), pat) for pat in match):
            continue
        # Delivery-spec scope, by ACTUAL GEOMETRY rather than by filename.
        if specs is not None:
            if ext not in VID_EXT:
                continue
            if dimensions(f) not in specs:
                continue
        items.append((f, rel, ext in VID_EXT, is_frame))
        if limit and len(items) >= limit:
            break
    return items


def poster_for(rel: Path) -> Path | None:
    """The cached poster the existing gallery already built for this video."""
    p = POSTERS / (rel.as_posix().replace("/", "__").rsplit(".", 1)[0] + ".jpg")
    return p if p.is_file() else None


def frame_grab(src: Path, dst: Path) -> bool:
    try:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", str(src),
             "-frames:v", "1", "-vf", f"scale={THUMB}:-1", str(dst)],
            check=True, capture_output=True, timeout=60)
        return dst.is_file()
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-frames", action="store_true",
                    help="skip keyframe sequences (finished renders only)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--collection", default="slow-interpolation")
    ap.add_argument("--rebuild-thumbs", action="store_true")
    ap.add_argument("--since-days", type=float, default=None,
                    help="only assets GENERATED in the last N days. Cloud renders "
                         "date from their manifest's started_at_utc; anything "
                         "else falls back to file mtime, which syncs rewrite, so "
                         "manifests win whenever present.")
    ap.add_argument("--exclude-file", type=Path, default=None,
                    help="removal list exported by the curated field's tier-0 "
                         "curate face; assets whose key matches are dropped")
    ap.add_argument("--include", action="append", default=None,
                    help="only assets whose outputs/-relative path starts with this; "
                         "repeatable. The curated-exhibition switch.")
    ap.add_argument("--match", action="append", default=None,
                    help="only assets whose outputs/-relative path matches this glob; "
                         "repeatable, OR-ed. The DELIVERY-SPEC switch: conform.py "
                         "stamps the wall geometry into the filename, so "
                         "--match '*__bc_1728x540.mp4' --match '*__a_912x2736.mp4' "
                         "keeps exactly the files that are wall-ready and drops every "
                         "raw render and test. Unlike a removal list this is standing: "
                         "tomorrow's conform lands in the field, tomorrow's raw does not.")
    ap.add_argument("--spec", action="append", default=None,
                    help="only videos whose ACTUAL dimensions are WxH; repeatable, "
                         "OR-ed. The wall-ready switch: --spec 1728x540 --spec "
                         "912x2736 keeps exactly the pieces cut for the LED walls "
                         "and drops every raw render and test. Prefer this over "
                         "--match: a client-named delivery file carries no geometry "
                         "in its name, so a name filter silently missed 5 of the 6 "
                         "vertical pieces. Standing, so tomorrow's conform qualifies "
                         "automatically.")
    ap.add_argument("--cluster-by", choices=("dir", "screen"), default="dir",
                    help="what a cluster MEANS. 'dir' (default) clusters by the "
                         "render's directory, which is the run that made it. "
                         "'screen' clusters by the LED wall the file is for "
                         "(screen-a / screen-bc / unassigned) -- the deliverable "
                         "view rather than the production view.")
    ap.add_argument("--dest", default=None,
                    help="output dir (default outputs/_glance); thumbs are still cached "
                         "in outputs/_glance/thumbs and copied in")
    args = ap.parse_args()

    global DEST
    if args.dest:
        DEST = (ROOT / args.dest).resolve() if not Path(args.dest).is_absolute() else Path(args.dest)

    if not OUTPUTS.is_dir():
        sys.exit(f"no outputs/ at {OUTPUTS}")

    excl: set[str] = set()
    if args.exclude_file:
        import json as _json
        doc = _json.loads(Path(args.exclude_file).read_text(encoding="utf-8"))
        excl = {e["key"] for e in doc.get("exclude", []) if e.get("key")}
        print(f"excluding {len(excl)} curated-out asset(s)")
    items = collect(not args.no_frames, args.limit, args.include,
                    since_days=args.since_days, exclude_keys=excl, match=args.match,
                    specs=({tuple(int(v) for v in sp.lower().split("x")) for sp in args.spec}
                           if args.spec else None))
    if not items:
        sys.exit("nothing to export")

    thumbs = DEST / "thumbs"
    (DEST / "data").mkdir(parents=True, exist_ok=True)
    (DEST / "atlas").mkdir(parents=True, exist_ok=True)
    thumbs.mkdir(parents=True, exist_ok=True)
    THUMB_CACHE.mkdir(parents=True, exist_ok=True)

    # One 4096 sheet, so the whole field stays a single draw call. Pick the largest
    # cell that still fits every tile: the viewer loads sheet-0 only.
    n = len(items)
    per_row = int(n ** 0.5) + 1
    cell = min(MAX_CELL, SHEET_SIZE // per_row)
    if cell < 16:
        sys.exit(f"{n} assets will not fit one {SHEET_SIZE}px sheet; use --no-frames or --limit")
    per_row = SHEET_SIZE // cell

    print(f"exporting {n} assets  (cell {cell}px, {per_row} per row)")
    sheet = Image.new("RGB", (SHEET_SIZE, SHEET_SIZE), (244, 241, 238))

    field, cat_assets, tiles = [], [], {}
    events: dict[str, dict] = {}
    skipped, made, reused = [], 0, 0
    t0 = time.time()

    for i, (f, rel, is_video, is_frame) in enumerate(items):
        sha = sha16_of(rel)
        tp = THUMB_CACHE / f"{sha}.jpg"

        if tp.is_file() and not args.rebuild_thumbs:
            reused += 1
        else:
            src = f
            if is_video:
                p = poster_for(rel)
                if p:
                    src = p
                elif not frame_grab(f, tp):
                    skipped.append(rel.as_posix())
                    continue
                else:
                    src = tp
            try:
                with Image.open(src) as im:
                    im = im.convert("RGB")
                    im.thumbnail((THUMB, THUMB), Image.LANCZOS)
                    im.save(tp, "JPEG", quality=82, optimize=True)
                made += 1
            except Exception as e:
                skipped.append(f"{rel.as_posix()} ({type(e).__name__})")
                continue

        try:
            with Image.open(tp) as im:
                w, h = im.size
                aspect = w / h if h else 1.0
                cw, ch = (cell - 3, int((cell - 3) / aspect)) if aspect >= 1 \
                    else (int((cell - 3) * aspect), cell - 3)
                cw, ch = max(1, min(cw, cell - 3)), max(1, min(ch, cell - 3))
                sheet.paste(im.resize((cw, ch), Image.LANCZOS),
                            ((len(tiles) % per_row) * cell + 1,
                             (len(tiles) // per_row) * cell + 1))
                colour = "#%02x%02x%02x" % im.resize((1, 1), Image.LANCZOS).getpixel((0, 0))
        except Exception as e:
            skipped.append(f"{rel.as_posix()} (tile: {type(e).__name__})")
            continue

        if thumbs != THUMB_CACHE:
            shutil.copy2(tp, thumbs / f"{sha}.jpg")

        idx = len(tiles)
        tiles[sha] = {"sheet": 0,
                      "x": (idx % per_row) * cell + 1, "y": (idx // per_row) * cell + 1,
                      "w": cw, "h": ch, "aspect": round(aspect, 4)}

        run, group = run_of(rel)
        ctx = group
        if args.cluster_by == "screen":
            # The cluster becomes the WALL. The production origin (the run
            # directory) stays on the record as `context`, so it is still shown
            # and still searchable -- it just stops deciding the layout. The
            # viewer needs no change for this: it already clusters on the field's
            # event key, so choosing what that key MEANS is the exporter's job,
            # which keeps the wall vocabulary out of a shared viewer.
            #
            # `group` MUST become the screen too, not the old run. clusterKey()
            # resolves `group || event`, so leaving the directory in `group`
            # silently overrides the whole thing: the clusters still came out
            # correct (21/5/4) because every member of a screen shares one first
            # directory, and every region was then LABELLED with that directory --
            # led / delivery / candidate. Right grouping, wrong name, and the
            # counts matching made it look like it had worked.
            ctx = group
            run = screen_of(rel, dimensions(f))
            group = run
        date = datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).date().isoformat()
        kind = "frame" if is_frame else ("render" if is_video else "still")
        caption = rel.stem.replace("_", " ").replace("-", " ")
        scene = [s for s in {kind, group, ctx, "video" if is_video else "image"} if s]

        events.setdefault(run, {"slug": run, "label": run.replace("-", " "),
                                "venue": group, "date": date, "kind": kind,
                                "group": group, "order": len(events) + 1,
                                "description": f"{ctx} / {run}"})
        lora = lora_of(f)
        dims = dimensions(f) if is_video else None
        field.append({
            "sha": sha, "key": rel.as_posix(), "date": date, "event": run,
            "context": ctx, "media_type": "video" if is_video else "photo",
            "asset_class": kind, "artists": [], "public": True,
            "caption_short": caption, "color": colour, "has_thumb": True,
            # Geometry ON THE RECORD. It previously existed ONLY inside the atlas
            # index, so the viewer could draw the right shape and could not tell you
            # what that shape WAS -- no spec chip, no "show me only the verticals",
            # and no way for a card to state the delivery size of a delivery file.
            "width": dims[0] if dims else None,
            "height": dims[1] if dims else None,
            # Sub-order inside the cluster: same LoRA sits together. The viewer
            # treats this as an opaque string (layout.js subgroupCmp), so the
            # LoRA vocabulary stays here rather than in a shared renderer.
            "subgroup": lora,
        })
        cat_assets.append({
            "key": rel.as_posix(), "bytes": f.stat().st_size,
            "sha256": sha + "0" * 48, "media_type": "video" if is_video else "photo",
            "ingested": datetime.fromtimestamp(f.stat().st_mtime, timezone.utc)
                                .isoformat().replace("+00:00", "Z"),
            "thumb": f"{sha}.jpg",
            "width": dims[0] if dims else None,
            "height": dims[1] if dims else None,
            # Direct path to the original, relative to the page. Lets the card play
            # video and show full-resolution stills with NO backend at all: serve.py
            # mounts these with --originals. Nothing signs anything.
            "media_url": "originals/" + rel.as_posix(),
            "tags": {
                "edition": args.collection, "event": run, "venue": group,
                "context": group, "date": date, "date_basis": "file mtime",
                "media_type": "video" if is_video else "photo", "asset_class": kind,
                "artists": [], "artworks": [], "persons": [],
                "scene": sorted(scene), "caption": caption,
            },
        })

        if (i + 1) % 250 == 0:
            print(f"  {i+1}/{n}  ({time.time()-t0:.0f}s)")

    sheet.save(DEST / "atlas" / "sheet-0.jpg", "JPEG", quality=88, optimize=True)
    generated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    (DEST / "atlas" / "atlas-index.json").write_text(json.dumps({
        "edition": args.collection, "sheet_size": SHEET_SIZE, "cell": cell,
        "sheets": 1, "count": len(tiles), "tiles": tiles}, ensure_ascii=False), encoding="utf-8")
    (DEST / "data" / "field.json").write_text(json.dumps({
        "edition": args.collection, "generated": generated, "count": len(field),
        "no_thumb": 0, "no_color": 0, "assets": field}, ensure_ascii=False), encoding="utf-8")
    (DEST / "data" / "catalogue.json").write_text(json.dumps({
        "edition": args.collection, "generated": generated,
        "assets": cat_assets, "events": list(events.values())}, ensure_ascii=False), encoding="utf-8")

    print(f"\n{len(tiles)} tiles in {len(events)} clusters  "
          f"({made} thumbs built, {reused} reused, {time.time()-t0:.0f}s)")
    if skipped:
        print(f"SKIPPED {len(skipped)} (no poster / unreadable):")
        for s in skipped[:8]:
            print(f"  {s}")
        if len(skipped) > 8:
            print(f"  ... +{len(skipped)-8} more")
    print(f"\nwrote {DEST}")
    print(f"view:  python <path-to>/glance/serve.py --data \"{DEST}\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())