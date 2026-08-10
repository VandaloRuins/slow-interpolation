"""glance_deploy.py -- publish the Glance field to a stable Vercel URL.

`glance_export.py` builds the archive; this assembles a deployable site from it and
ships it. The two are separate because export is cheap and local, while deploying is
outward-facing: the URL is public to anyone holding it and these renders are
unreleased work. So this PRINTS the vercel command by default and only runs it with
--deploy, exactly like tools/deploy_gallery.py.

    python tools/glance_deploy.py                       # build + print the command
    python tools/glance_deploy.py --deploy              # preview URL
    python tools/glance_deploy.py --deploy --prod       # the stable production URL

What can and cannot go up
-------------------------
The originals are 11.5 GB. They are never deployable and are never copied. What ships
is the field (thumbnails + atlas + metadata, ~15 MB) and, where one exists and fits,
the small web proxy `gallery.py` already built for a video.

A card whose video did not ship keeps its poster and its full record and says the
video is not published, rather than offering a play button that 404s. That is what
`media_url` in the Glance contract is for: it is written ONLY for media actually
present in the bundle, and stripped otherwise.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXPORT = ROOT / "outputs" / "_glance-renders"
DEFAULT_OUT = ROOT / "outputs" / "_glance-deploy"
PREVIEWS = ROOT / "outputs" / "_gallery" / "previews"

# Which Vercel project this repo publishes to. Kept at the repo root, NOT inside the
# build dir, because the build dir is wiped on every run -- a `.vercel/` link there
# would be destroyed each time and the next deploy would silently mint a NEW project
# with a new URL. That is exactly how the existing gallery ended up in a project
# literally named "_deploy". Project and org ids are identifiers, not credentials.
PROJECT_LINK = ROOT / ".glance-vercel.json"
# A second field needs a second pin, or deploying the curated exhibition would
# repoint the main archive's project and one of the two stable URLs would die.
CURATED_LINK = ROOT / ".glance-ledwall-vercel.json"

# The viewer is a separate tool. Point at it with --glance or $GLANCE_HOME; the
# default is the sibling checkout, which is where it lives on this machine.
DEFAULT_GLANCE = ROOT.parent / "Ruins-Harness_Tools-for-Agents" / "glance"


def proxy_for(key: str) -> Path | None:
    """The web proxy gallery.py built for this render, if it made one."""
    p = PREVIEWS / (key.replace("/", "__").rsplit(".", 1)[0] + ".mp4")
    return p if p.is_file() else None


def human(mb: float) -> str:
    return f"{mb:,.1f} MB"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", type=Path, default=DEFAULT_EXPORT,
                    help="a glance_export.py output dir")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--glance", type=Path,
                    default=Path(os.environ.get("GLANCE_HOME", DEFAULT_GLANCE)),
                    help="the glance tool checkout (holds install.py + payload/)")
    ap.add_argument("--title", default="Slow Interpolation")
    ap.add_argument("--collection", default="renders")
    ap.add_argument("--no-video", action="store_true",
                    help="ship the field only; every card keeps poster + record")
    ap.add_argument("--max-asset-mb", type=float, default=4.0,
                    help="skip any single proxy larger than this")
    ap.add_argument("--max-mb", type=float, default=95.0,
                    help="refuse to build a bundle larger than this")
    ap.add_argument("--project", default="slow-interpolation-glance",
                    help="Vercel project name, used only on the FIRST deploy; after "
                         "that the saved link decides, so the URL stays put")
    ap.add_argument("--pin", choices=["main", "ledwall"], default="main",
                    help="which Vercel project pin to use; ledwall is the curated field")
    ap.add_argument("--deploy", action="store_true", help="actually run vercel")
    ap.add_argument("--prod", action="store_true", help="production, not preview")
    args = ap.parse_args()

    cat_path = args.export / "data" / "catalogue.json"
    if not cat_path.is_file():
        print(f"no export at {args.export}\n  run: python tools/glance_export.py "
              f"--no-frames --dest {args.export.relative_to(ROOT)}", file=sys.stderr)
        return 1
    installer = args.glance / "install.py"
    if not installer.is_file():
        print(f"glance tool not found at {args.glance}\n"
              f"  pass --glance <dir> or set GLANCE_HOME", file=sys.stderr)
        return 1

    out = args.out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # 1) the viewer, configured for a static tier 0 deploy
    cfg = out.parent / "_glance-deploy.config.json"
    cfg.write_text(json.dumps({
        "title": args.title, "collection": args.collection, "tier": 0,
        "dataBase": "data", "atlasBase": "atlas", "thumbBase": "thumbs",
        "apiBase": "", "auth": None, "profileHello": False,
    }), encoding="utf-8")
    r = subprocess.run([sys.executable, str(installer), "--target", str(out),
                        "--config", str(cfg), "--force"], capture_output=True, text=True)
    cfg.unlink(missing_ok=True)
    if r.returncode != 0:
        print(f"viewer install failed:\n{r.stdout}\n{r.stderr}", file=sys.stderr)
        return 1

    # 2) the archive
    for sub in ("data", "atlas", "thumbs"):
        shutil.copytree(args.export / sub, out / sub, dirs_exist_ok=True)

    cat = json.loads((out / "data" / "catalogue.json").read_text(encoding="utf-8"))
    videos = [a for a in cat["assets"] if a.get("media_type") == "video"]

    # 3) video, smallest first so the budget buys the most playable cards
    shipped: dict[str, str] = {}
    total_mb = sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) / 1e6
    if not args.no_video:
        cands = []
        for a in videos:
            p = proxy_for(a["key"])
            if p:
                cands.append((p.stat().st_size / 1e6, a["key"], p))
        cands.sort()
        (out / "media").mkdir(exist_ok=True)
        for mb, key, p in cands:
            if mb > args.max_asset_mb:
                continue
            if total_mb + mb > args.max_mb:
                break
            dest_name = key.replace("/", "__")
            shutil.copy2(p, out / "media" / dest_name)
            shipped[key] = "media/" + dest_name
            total_mb += mb

    # 4) media_url points ONLY at what actually shipped. A stale one is worse than
    #    none: it renders a play button that 404s and reads as a broken archive.
    kept = 0
    for a in cat["assets"]:
        if a["key"] in shipped:
            a["media_url"] = shipped[a["key"]]
            kept += 1
        else:
            a.pop("media_url", None)
    (out / "data" / "catalogue.json").write_text(json.dumps(cat, ensure_ascii=False),
                                                 encoding="utf-8")

    # 5) hosting config. Content-keyed assets are immutable; the JSON is not.
    (out / "vercel.json").write_text(json.dumps({
        "cleanUrls": True,
        "headers": [
            {"source": "/(atlas|thumbs|media)/(.*)",
             "headers": [{"key": "Cache-Control",
                          "value": "public, max-age=31536000, immutable"}]},
            {"source": "/data/(.*)",
             "headers": [{"key": "Cache-Control", "value": "public, max-age=60"}]},
        ],
    }, indent=2), encoding="utf-8")

    total_mb = sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) / 1e6
    n_files = sum(1 for f in out.rglob("*") if f.is_file())

    print(f"built {out}")
    print(f"  {len(cat['assets'])} assets  ({len(videos)} video, "
          f"{len(cat['assets']) - len(videos)} still)")
    print(f"  {kept} video playable in the browser; "
          f"{len(videos) - kept} keep poster + record only")
    print(f"  {n_files:,} files, {human(total_mb)}")
    if total_mb > args.max_mb:
        print(f"\nREFUSING: {human(total_mb)} exceeds --max-mb {args.max_mb}", file=sys.stderr)
        return 1

    cmd = ["npx", "vercel", "deploy", str(out), "--yes"] + (["--prod"] if args.prod else [])
    print("\n" + " ".join(cmd))
    if not args.deploy:
        print("\n(not deployed. Re-run with --deploy.)")
        print("A Vercel URL is PUBLIC to anyone holding it, and these renders are "
              "unreleased work.")
        return 0

    # Pin the project, or every deploy mints a NEW one named after the build
    # directory and the URL you shared last week goes stale. That is how this repo
    # acquired a project called "_deploy", and then a second one called
    # "_glance-deploy" -- the build dir is wiped each run, so a `.vercel/` link
    # inside it cannot survive. The link lives at the repo root instead.
    env = dict(os.environ)
    pin_file = CURATED_LINK if args.pin == "ledwall" else PROJECT_LINK
    if pin_file.is_file():
        link = json.loads(pin_file.read_text(encoding="utf-8"))
        env["VERCEL_ORG_ID"] = link["orgId"]
        env["VERCEL_PROJECT_ID"] = link["projectId"]
        print(f"  -> project {link.get('projectName') or link['projectId']} (pinned)")
    else:
        print("  -> no pinned project yet; vercel will resolve one from the build dir")

    r = subprocess.run(cmd, capture_output=True, text=True, shell=(os.name == "nt"), env=env)
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    if r.returncode != 0:
        return r.returncode

    # Whatever project it actually landed in, record it so the NEXT deploy is
    # guaranteed to hit the same URL.
    made = out / ".vercel" / "project.json"
    if not pin_file.is_file() and made.is_file():
        pin_file.write_text(made.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  pinned {pin_file.name}: later deploys reuse this project + URL")

    url = [l.strip() for l in r.stdout.splitlines() if l.strip().startswith("https://")]
    if url:
        print(f"\ndeployment: {url[-1]}")
    # Report the pin that was actually USED. When the ledwall pin deployed the
    # curated field, this block read the MAIN pin and announced the main URL as
    # its stable address, which pointed the operator at the wrong gallery.
    if args.prod and pin_file.is_file():
        name = json.loads(pin_file.read_text(encoding="utf-8")).get("projectName", "")
        alias = name.lstrip("_").replace("_", "-")
        print(f"STABLE URL: https://{alias}.vercel.app")
        print("  Share the STABLE url, not the deployment one: deployment URLs are\n"
              "  protected (302 to a Vercel login) and change on every push.")
    print("Verify by opening it and checking a tile renders -- a 200 on the homepage\n"
          "proves only that a page was served.")
    return 0


if __name__ == "__main__":
    sys.exit(main())