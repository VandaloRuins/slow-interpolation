"""Publish a FILTERED slice of the gallery to Vercel as a real web page.

Why a slice and not the whole thing. `outputs/_gallery/previews` alone is
283 MB across 66 proxies, and the originals are 60 to 80 MB each. Vercel is not
a video CDN and a Hobby deployment is capped far below that, so "deploy the
gallery" in full is not a thing that can work. What actually gets reviewed is
the current batch, so this deploys the current batch: pass a filter, get a
standalone page carrying only the renders that match, with their posters and
their small web proxies rather than the originals.

Why bother, when `serve_gallery.py` plus a Cloudflare quick tunnel already
works. Because that path dies with the laptop, the URL changes every time, it
is public and unauthenticated for as long as it lives, and it has silently
served a stale page more than once. A Vercel deployment has a stable URL,
survives the machine going to sleep, and is the same page every time.

    python tools/deploy_gallery.py --filter led3 --filter led4
    python tools/deploy_gallery.py --filter nyc-billboard --prod

It prints the exact `vercel` command rather than running it by default, because
publishing is outward-facing: a deploy URL is public to anyone holding it, and
this repo's renders are unreleased work. Pass --deploy to actually ship.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "gallery.html"
DEFAULT_OUT = ROOT / "outputs" / "_deploy"

# Anything the page references, as repo-relative paths inside quoted attributes.
ASSET_RE = re.compile(r'(?:src|href|data-src)="(outputs/[^"]+)"')


def card_blocks(html_text: str) -> list[str]:
    """Split the page into whole <article class="card"> blocks.

    Filtering has to work on complete cards. Filtering line-wise would leave a
    card's markup half-present, which produces a page that renders but whose
    controls count wrong.
    """
    # Split on the class PREFIX, not on `class="card"`, because there are two
    # kinds: `class="card"` for videos and `class="card stills"` for keyframe
    # strips. Matching only the first left 123 strip cards riding along inside
    # the header block with their images uncopied, so the page reported 135
    # cards and most of them 404ed.
    marker = '<article class="card'
    parts = html_text.split(marker)
    return [parts[0]] + [marker + p for p in parts[1:]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--filter", action="append", default=[],
                    help="substring a card must contain; repeatable, OR-ed. "
                         "Omit to take every card, which will almost certainly "
                         "be too large to deploy.")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--deploy", action="store_true",
                    help="actually run vercel; otherwise just print the command")
    ap.add_argument("--prod", action="store_true", help="production rather than preview")
    ap.add_argument("--max-mb", type=float, default=90.0,
                    help="refuse to build a bundle larger than this")
    ap.add_argument("--max-asset-mb", type=float, default=8.0,
                    help="skip any single file larger than this (the 60 MB originals)")
    ap.add_argument("--stills", action="store_true",
                    help="include PNG keyframe strips; off by default because a strip "
                         "card references hundreds of them")
    args = ap.parse_args()

    if not PAGE.exists():
        print(f"no gallery at {PAGE}; run tools/gallery.py first", file=sys.stderr)
        return 1

    html_text = PAGE.read_text(encoding="utf-8")
    blocks = card_blocks(html_text)
    head, cards = blocks[0], blocks[1:]

    if not args.stills:
        cards = [c for c in cards if 'class="card stills"' not in c]
    if args.filter:
        kept = [c for c in cards if any(f in c for f in args.filter)]
    else:
        kept = cards
    if not kept:
        print(f"no cards matched {args.filter}", file=sys.stderr)
        return 1

    # Rebuild the page with only the kept cards.
    #
    # The tail (footer, </main>, and the entire <script> block) trails the LAST
    # card in the source, so it rides along inside that card's block after the
    # split. Taking it from `cards[-1]` is wrong the moment filtering removes
    # that card, and it silently produced a page with no script at all: every
    # control dead, and it still rendered, so it looked fine. Take the tail from
    # the ORIGINAL html and trim every kept block at its own </article>.
    end = "</article>"
    tail = html_text[html_text.rindex(end) + len(end):]

    def trim(c: str) -> str:
        return c[:c.rindex(end) + len(end)] if end in c else c

    page_out = head + "\n".join(trim(c) for c in kept) + tail

    out = args.out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # Asset selection, which is where the size actually lives. A first version
    # copied everything a card referenced and produced 4.2 GB from 12 cards,
    # because every card ALSO links its 60 to 80 MB original for download, and
    # the PNG-strip cards reference a keyframe directory of hundreds of stills.
    # So: skip anything over the per-asset cap, skip stills unless asked, and
    # then rewrite the page so nothing points at a file that was not copied.
    assets = sorted({m for c in kept for m in ASSET_RE.findall(c)})
    total = 0
    copied = 0
    missing: list[str] = []
    skipped: set[str] = set()
    cap = args.max_asset_mb * 1e6
    for a in assets:
        src = ROOT / a
        if not src.exists():
            missing.append(a)
            skipped.add(a)
            continue
        if a.lower().endswith(".png") and not args.stills and "posters" not in a:
            skipped.add(a)
            continue
        if src.stat().st_size > cap:
            skipped.add(a)
            continue
        dst = out / a
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        total += dst.stat().st_size
        copied += 1

    # Drop any anchor whose target was not copied, so the page never offers a
    # link that 404s. The small-proxy link survives, which is the one that
    # matters for review on a phone.
    for a in sorted(skipped):
        page_out = re.sub(
            r'<a class="dl[^"]*" href="' + re.escape(a) + r'".*?</a>',
            "", page_out, flags=re.S)
        page_out = re.sub(
            r'<figure><a href="' + re.escape(a) + r'".*?</figure>',
            "", page_out, flags=re.S)

    (out / "index.html").write_text(page_out, encoding="utf-8")
    (out / "vercel.json").write_text(
        '{\n  "cleanUrls": true,\n'
        '  "headers": [\n'
        '    { "source": "/outputs/(.*)", "headers": ['
        '{ "key": "Cache-Control", "value": "public, max-age=31536000, immutable" }] },\n'
        '    { "source": "/", "headers": ['
        '{ "key": "Cache-Control", "value": "no-store" }] }\n'
        '  ]\n}\n', encoding="utf-8")

    # Structural self-check. The bug this guards against shipped a page that
    # rendered perfectly and had no <script> at all.
    built = (out / "index.html").read_text(encoding="utf-8")
    broken = [t for t in ("<script>", "</script>", "</html>", "<footer>") if t not in built]
    if broken:
        print(f"  !! deployed page is missing {', '.join(broken)}: it will render but "
              f"every control will be dead. NOT deployable.", file=sys.stderr)
        return 1
    n_built = built.count('<article class="card')
    if n_built != len(kept):
        print(f"  !! page has {n_built} cards but {len(kept)} were selected",
              file=sys.stderr)
        return 1

    mb = total / 1e6
    print(f"cards      : {len(kept)} of {len(cards)}")
    print(f"assets     : {copied} copied, {len(missing)} missing")
    print(f"bundle     : {mb:.1f} MB at {out.relative_to(ROOT)}")
    for m in missing[:5]:
        print(f"  !! missing asset (card will 404): {m}", file=sys.stderr)

    if mb > args.max_mb:
        print(f"  !! {mb:.1f} MB exceeds --max-mb {args.max_mb}. Narrow the filter; "
              f"Vercel is not a video host.", file=sys.stderr)
        return 1

    cmd = ["vercel", "deploy", str(out), "--yes"] + (["--prod"] if args.prod else [])
    if not args.deploy:
        print("\nnot deployed. A deploy URL is PUBLIC to anyone holding it and these "
              "renders are unreleased. To ship it, run:")
        print("  " + " ".join(cmd))
        return 0

    print("\n" + " ".join(cmd))
    # On Windows `vercel` is a .cmd shim, which CreateProcess cannot exec
    # directly: subprocess raises WinError 2 "cannot find the file specified"
    # even though the CLI is installed and on PATH. Resolve it properly.
    exe = shutil.which(cmd[0])
    if exe is None:
        print("vercel CLI not found on PATH; npm i -g vercel", file=sys.stderr)
        return 1
    return subprocess.run([exe] + cmd[1:], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
