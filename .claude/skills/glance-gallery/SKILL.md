---
name: glance-gallery
description: Publish and update the Glance field gallery at https://glance-deploy.vercel.app -- the whole-outputs view of every render, clustered and searchable. Use whenever the user says "update the glance link", "push the new renders to the gallery link", "update the vercel gallery", "send the field link", or after a batch of renders lands and they want the shared URL current. Not gallery.html; that is publish-for-review.
---

# Glance gallery (the shared Vercel field)

**Stable URL: https://glance-deploy.vercel.app** — public, no login. Share this one.

Two galleries exist and they answer different questions. Do not confuse them:

| | tool | question it answers |
|---|---|---|
| [publish-for-review](../publish-for-review/SKILL.md) | `gallery.py` + tunnel | "look at THIS batch" |
| **this one** | `glance_export.py` + `glance_deploy.py` | "what have we actually rendered" |

Glance is a separate tool (`Ruins-Harness_Tools-for-Agents/glance/`) that knows nothing
about this repo. It reads a published data contract; `tools/glance_export.py` is our
implementation of it. Point at another checkout with `--glance` or `$GLANCE_HOME`.

## Updating the link after new renders

```bash
python tools/sync_outputs.py --prefix <name>                              # if from Modal
python tools/glance_export.py --no-frames --dest outputs/_glance-renders  # rebuild the archive
python tools/glance_deploy.py --deploy --prod                             # publish
```

Then **open the URL and click a tile.** Not a curl. See "verify" below.

`glance_export.py` is incremental: thumbnails are cached in `outputs/_glance/thumbs`
and reused, so a rebuild after a new batch costs seconds, not the 194 s of a cold run.

## Which view

- `--no-frames` (**the default you want**): finished renders only. 418 assets, 43
  clusters, ~15 MB before video. This is the gallery.
- full (no flag): 2,951 assets including 2,533 keyframes. Honest, and it buries the
  renders. Worth building when the question is a run's *drift* rather than a
  deliverable, because a sequence reads as a colour arc across its own cluster.

## Traps, each of which actually happened

**The stable URL and the deployment URL are different things.** `vercel deploy` prints
`glance-deploy-<hash>-....vercel.app`, which **302s to a Vercel login** — anyone you
send it to sees a sign-in page. The shareable one is the production alias,
`https://glance-deploy.vercel.app`. Only `--prod` updates it.

**`.glance-vercel.json` at the repo root pins the Vercel project. Never delete it, and
keep it committed.** Without it, every deploy creates a NEW project named after the
build directory, with a new URL, and last week's link goes stale. That is exactly how
this repo acquired a project called `_deploy` and then another called `_glance-deploy`.
The build dir is wiped on every run, so a `.vercel/` link inside it cannot survive.

**Originals are 11.5 GB and are never deployed.** Only the small proxies `gallery.py`
already built get shipped, under a 4 MB per-file cap and a 95 MB bundle budget. Today
that is 59 of 209 videos. The rest keep poster and full record and say "video not
published in this archive" — which is true, and is not a bug to chase.

**`media_url` must name only what actually shipped.** `glance_export.py` writes it
pointing at local originals; `glance_deploy.py` REWRITES it to the bundled proxy and
strips it where nothing shipped. A stale `media_url` renders a play button that 404s,
which reads as a broken archive. Never hand-edit the deployed catalogue.

**An empty field with a clean console means the join is wrong**, not that the viewer
broke. `field.json[].sha`, `atlas-index.tiles{}`, `catalogue[].sha256[:16]` and
`thumbs/<sha>.jpg` must agree on one 16-char id. An asset with no atlas tile is
silently skipped by design.

**A patch script that prints success proves nothing.** `str.replace` on a
non-matching pattern changes nothing and returns happily. Assert the pattern was
found, then re-read the file. This bit during the build of these very tools: the
project-pinning code reported "added" and was not there, which is why the first
deploy created `_glance-deploy` in the first place.

## Verify

A 200 on the homepage proves only that a page was served. Assert on something unique
to this build:

```bash
curl -s https://glance-deploy.vercel.app/data/catalogue.json | python -c "import json,sys; d=json.load(sys.stdin); print(len(d['assets']),'assets', sum(1 for a in d['assets'] if a.get('media_url')),'playable')"
```

Then open it, confirm tiles render, type a query and watch the field reflow, and click
a video card. Zero console errors is part of the check, not a bonus.


## The curated LED-wall field (second deployment, 2026-08-10)

**Stable URL: https://glance-ledwall-deploy.vercel.app** -- public, no login. A SECOND
pinned Vercel project (`.glance-ledwall-vercel.json`; never delete either pin). Scope:
the exhibition work, exported with `--since-days` / `--include`.

```
python tools/glance_export.py --no-frames --since-days 8 --dest outputs/_glance-ledwall
python tools/glance_deploy.py --export outputs/_glance-ledwall --out outputs/_glance-ledwall-deploy     --pin ledwall --curate --title "Slow Interpolation -- LED Wall" --collection ledwall --deploy --prod
```

`--since-days` dates by MANIFEST (`started_at_utc`), never mtime: syncs rewrite mtime and
a mtime window sweeps in years-old work.

**Curation round trip (tier 0).** `--curate` injects `tools/glance_curate.js`: a curate
chip enters the field's own select mode (it always existed but lies dormant below tier 1;
only the download layer ever enabled it), tiles toggle with taps, long-press takes a
cluster, "export removals" downloads `glance-removals.json` carrying KEYS. Rebuild with
`glance_export.py --exclude-file glance-removals.json` and redeploy. Real in-field Tier 2
curation lives ONLY in the private RNMW-agent repo and would be a hand-port
(`write.js` hardcodes RNMW's EVENT_PROFILES); the white-label manifest excludes it by design.

**Immutable is for content-keyed names ONLY.** `atlas-index.json` and `sheet-0.jpg` keep
their names across rebuilds; marking `atlas/` immutable froze every prior visitor on the
old field forever (immutable entries are never revalidated; no ordinary reload recovers).
Fixed in `glance_deploy.py`: immutable = `thumbs/<sha>` only. Anyone who visited before
2026-08-10 needs ONE hard refresh. Diagnostic that found it: fetch the same URL from
inside the live page with default cache and with `{cache:'no-store'}` and compare.

## Costs and posture

The deploy is free (static, Hobby). It is **public to anyone with the link and these
renders are unreleased work** — say that out loud when you hand the URL over, and get
the maintainer's go-ahead before the first publish of anything new. `glance_deploy.py`
prints the command and does nothing without `--deploy`, deliberately, exactly like
`deploy_gallery.py`.