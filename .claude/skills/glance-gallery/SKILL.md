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
published in this archive", which is true **of the Vercel bundle** and is not a bug to
chase there.

**It IS a bug on the local tunnel, and it was one.** Both limits exist because Vercel
has to hold the bundle; neither applies to a file read off this machine's own disk. On
2026-08-10 the served field showed that banner on 50 of 118 cards while every file sat
locally. `serve_glance.py` now patches `media_url` into the catalogue RESPONSE for
anything it can play, proxy first and original as fallback, so the tunnel plays
everything while the deployed bundle stays inside budget. Same trick as the curate shim:
modify the response, never the built JSON.

**Serve video with byte-range support or iOS will not play it.**
`SimpleHTTPRequestHandler` ignores `Range` and answers **200 with the whole file**.
Safari opens a video with a range probe and reads a 200 as "this server cannot seek", so
playback is unreliable and scrubbing impossible, including on proxies that shipped
correctly. Fixed in `serve_glance.py` for both routes: 206, `Content-Range`,
`Accept-Ranges`, and tail ranges (`bytes=-4096`), which is how a player finds the `moov`
atom. Verify with `curl -D - -o /dev/null -H "Range: bytes=0-1023"` and assert on **206**,
never on 200.

**A server restart does not cost the curator their work.** The curation epoch is a
hardcoded constant in `glance_curate_hide.js`, not a per-build value, so rebuilding and
restarting leaves every device's hidden list intact. Check that before touching a server
mid-pass; bumping the epoch is the one thing that would wipe it.

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

# ...and to curate WITH the automatic return path, serve the same build yourself:
python tools/serve_glance.py --port 8766        # prints a LAN URL for the phone
cloudflared tunnel --url http://127.0.0.1:8766  # only if Luca is not on the wifi
```

`--since-days` dates by MANIFEST (`started_at_utc`), never mtime: syncs rewrite mtime and
a mtime window sweeps in years-old work.

**Curation (tier 0). Removal is LOCAL, IMMEDIATE and REVERSIBLE.** `--curate` injects
`tools/glance_curate.js` plus the pre-boot shim `tools/glance_curate_hide.js`. The curate
chip enters the field's own select mode (it always existed but lies dormant below tier 1;
only the download layer ever enabled it), tiles toggle with taps, long-press takes a
cluster, and `remove N` takes them off the field and keeps them off.

It works through the viewer's OWN contract, not a hack: `glance.js` drops any catalogue
asset tagged `archived` before it reaches the field, and the data contract documents that
as `"archived": true = hidden from the field entirely`. Setting the flag is normally a
tier-2 server capability, so the shim sets it on the RESPONSE. The JSON on the CDN is never
modified, and with nothing hidden the shim leaves `window.fetch` untouched. The shim must be
injected as a CLASSIC script BEFORE the `glance.js` module, because `glance.js` calls
`boot()` at module evaluation; `glance_deploy.py` asserts on the anchor rather than shipping
a silently inert shim.

**Two stores, and the distinction is the design.** `marks` is the transient ringed
selection; `hidden` is the accumulated removal list that drives the shim AND is what gets
sent or exported. Hidden entries self-prune once a rebuild has removed the asset for real.

**`--exclude-file` is NOT cumulative, and that self-pruning is why it matters.** It
excludes exactly the keys in the file you hand it. The face posts its whole hidden list,
but it drops entries the last rebuild already removed, so `latest.json` covers only what
is still in the field. Feed it alone and everything removed in an earlier pass comes
straight back. Build the union of the applied history plus `latest.json`:

```bash
outputs/_glance-inbox/applied/applied-*.json  +  latest.json  ->  cumulative.json
```

**Keep `applied/` clean or the union lies.** It must hold ONLY lists that were actually
applied. On 2026-08-10 the stamped audit copies were filed there too, including the
61-card long-press accident that a `restore` had already undone, and the next union
silently re-applied it: an expected 74 tiles came out as 36. Never-applied posts go to
`audit/`. Always assert the tile count against `previous - len(latest)` before deploying.

**Four ways back, in increasing bluntness**, because a long-press selects a WHOLE CLUSTER
and on a phone that is one slightly-too-long tap from hiding sixty cards (it happened):
bulk-confirm needs a second tap at 10 or more; `undo` restores the pre-removal list for ten
minutes and survives the reload; `restore` clears everything hidden; `?curate=reset` clears
it from a link. And the **curation epoch** constant in the shim invalidates local curation
state on EVERY device at the next ordinary load, which is the only server-side lever over a
per-device store. Bump it when a device is stuck.

**The return path.** Hiding is per-DEVICE and invisible to the agent, so a removal only
becomes real for every viewer via a rebuild. Two routes:
- **Automatic (preferred).** Serve the build with `tools/serve_glance.py`; the face probes
  `curate/removals`, finds the same-origin sink and POSTs the whole list on every removal.
  It lands in `outputs/_glance-inbox/latest.json` plus a stamped audit copy. No CORS, no
  secret, no credential. Then `glance_export.py --exclude-file` and redeploy.
- **Manual fallback.** On the Vercel deploy the probe 404s, so the primary button becomes
  `export list` and the file is handed over. One build serves both, self-configuring.

A permanent version (a Vercel function committing the list into the repo, token in Vercel
env vars only, never in the browser) is priorities row DT14.

Real in-field Tier 2 curation lives ONLY in the private RNMW-agent repo and would be a
hand-port (`write.js` hardcodes RNMW's EVENT_PROFILES); the white-label manifest excludes it
by design.

**Immutable is for content-keyed names ONLY, so MAKE the name content-keyed.** The atlas is
fetched by fixed names (`atlas-index.json`, `sheet-0.jpg`) yet rewritten every build, which
made it the one thing a browser could get permanently wrong. It did: serving `atlas/`
immutable froze visitors on a 49-tile atlas after the field had grown, and immutable entries
are NEVER revalidated, so no ordinary reload recovers. It resurfaced 2026-08-10 on a phone
showing 49 of 117 assets in a collapsed layout, because `glance.js` silently skips any field
asset missing from the atlas (`const t = tiles[a.sha]; if (!t) continue;`) — so ONE stale
atlas drops most of the field AND wrecks the clustering, which reads as two separate bugs.

Fixed properly in `glance_deploy.py`: the atlas ships as **`atlas-<sha256[:10]>/`**, so the
NAME follows the CONTENT. A stale entry is orphaned rather than consulted, an
already-broken browser repairs itself on the next load with nothing asked of the user, and
`immutable` becomes CORRECT for the atlas rather than dangerous. No viewer change was
needed: `atlasBase` is a runtime config field and `glance.js` resolves both atlas fetches
through `atlasUrl()`.

**`glance/*` must stay short-lived (`max-age=60`), and this is load-bearing.** It holds
`glance.config.js`, which names the atlas directory; a cached config pointing at a retired
`atlas-<hash>/` would 404 the whole field, which is worse than the staleness it fixes.

Diagnostic that found both: fetch the same URL from inside the live page with default cache
and with `{cache:'no-store'}` and compare. And check the SERVED catalogue count, never the
build log.

## Costs and posture

The deploy is free (static, Hobby). It is **public to anyone with the link and these
renders are unreleased work** — say that out loud when you hand the URL over, and get
the maintainer's go-ahead before the first publish of anything new. `glance_deploy.py`
prints the command and does nothing without `--deploy`, deliberately, exactly like
`deploy_gallery.py`.