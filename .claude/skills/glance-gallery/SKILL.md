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

Glance is a separate tool that knows nothing about this repo. It reads a published
data contract; `tools/glance_export.py` is our implementation of it. Resolve it with
`--glance` or `$GLANCE_HOME`; there is deliberately no default.

**Where it comes from, and whether a change belongs upstream or here, is stated in
exactly one place: [docs/manual/glance-viewer.md](../../../docs/manual/glance-viewer.md).**
Read it before changing anything the field renders. Do not restate its facts here.

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

**The export scans SUBFOLDERS, so working files publish as if they were pieces**
(2026-08-15). `action_shore`'s source clip and its rejected perspective variant were
sitting in `outputs/arendt/action_shore/` and both appeared in the served catalogue as
finished work, at full size. Any compositing piece leaves a source clip behind and any
A/B leaves a loser, so this recurs. **Keep working files under `outputs/_work/<piece>/`,
never in a subfolder of the collection directory.** Caught only by reading the served
catalogue BY NAME; an asset count would have looked fine, because the count was correct.

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


## THE WORKING GALLERY (2026-08-14). Read this before touching any export flag.

**Stable URL: https://glance-arendt-deploy.vercel.app** -- its OWN Vercel pin
(`.glance-arendt-vercel.json`), separate from `ledwall`, because the two fields
were sharing one project and overwriting each other. Tier 3, login-gated editing,
public to look at.

**ONE list decides what is visible, and it lives on the server.** Until today four
things did, and they disagreed: `approved.json`, `cumulative.json`, the export
filters, and `glance_hidden`. Measured on the live deploy before the fix: 18 of 24
undecided renders were already public, 30 approved items were NOT on the field,
and 22 live items had never been approved. That is not a strict gate or a lax one,
it is an unrelated one -- and it is what the founder meant by "the gate is still
not really working".

Now:

- **The build ships everything** that matches the include/match filters.
- **`glance_hidden` (Supabase) alone decides what is not shown**, at runtime, for
  every viewer, reversibly, per item, with NO rebuild. `cumulative.json`'s 147
  entries were migrated into it and `--exclude-file` is no longer used.
- **`approved.json` is the gate for NEW work only.** It was baselined to the whole
  field on 2026-08-14, so it is a no-op for everything that already existed and
  bites only on the next render.

```bash
# THE canonical build. Changing a flag here changes founder-visible state.
py -3.11 tools/glance_export.py --no-frames \
    --include arendt --include nyc-billboard/delivery-final \
    --match "*.mp4" --match "*.mov" --cluster-by notion \
    --approved-file outputs/_glance-inbox/approved.json \
    --dest outputs/_glance-arendt
# NO --exclude-file: removals are server-side now. Adding it back double-gates
# and makes a removal permanent-and-invisible instead of reversible.

# ...then deploy (tier-3 flags below), and ALWAYS close with:
py -3.11 tools/glance_sort_curations.py --apply
```

**The last line is not optional, and it is the step most likely to be forgotten.**
The two standing curations are not snapshots of a moment, they are a STANDING RULE
about where work belongs:

| | |
|---|---|
| wall spec (1728x540 / 912x2736) | **NYC bill board** |
| everything else still visible | **Objkt** |

A share's key set is otherwise FROZEN by design, so new renders would never join a
curation and a removed one would keep travelling in a link after leaving the field.
`glance_sort_curations.py` re-derives both from the deployed field and writes them
back, keeping the same tokens, links and open counts. It is idempotent, it prints
the diff before writing, it excludes anything in `glance_hidden`, and it **refuses
to write if an asset would land in both curations** -- wall-spec work belongs to
the billboard set and must not also fall into the catch-all.

It sorts by **actual width/height from the catalogue, never by filename**: a
client-named delivery file carries no spec suffix, and a filename match once found
1 of the 6 files that really were 912x2736 and shipped a silently horizontal-only
set. The three `SUBJECTS THROUGH TIME` deliverables land in the billboard set for
exactly this reason.

Deploy with the tier-3 flags (`--pin arendt`, `--api-base`, `--auth-url`,
`--auth-anon-key`); a build without them silently drops to tier 0, which removes
login, review, download and curation in one go, with no error anywhere.

**`--match "*.mp4" --match "*.mov"` is load-bearing.** Without it the field is
5,007 tiles of anchors, masks and keyframes and the renders are unfindable. An
"output" here is a finished video.

**Four bugs on the review path, all fixed 2026-08-14, all invisible to greps and
curl.** Each one presented as "nothing happens": `review-bar.js` used `hasAuth`
and `CONFIG` without importing them (module dies at load, pill never renders);
`glance.js` passed the dead `__GLANCE_EDITOR_TOKEN__` global to the queue builder
(401 -> silent fallback to the whole archive, so the pill looked like a page
reload); the backend's CORS allow-list omitted `apikey`, so the browser refused
the preflight while curl saw a healthy 200; and review posters were presigned R2
URLs, which an `<img crossOrigin>` cannot load (no CORS header, no way to send a
token), so the queue rendered blank tiles. **Check payload JavaScript by LOADING
THE PAGE and reading the console.** `node --check` parses these as CommonJS and
misses duplicate top-level declarations; a grep of the deployed file proves the
new code shipped, not that it runs.

## The Arendt field: notion clusters + the admission queue (2026-08-13, founder-directed)

**The ledwall export/deploy dirs now carry the ARENDT field**, and its build has TWO
founder-directed properties. Any rebuild that omits these flags REVERTS founder-visible
state (it happened twice on 2026-08-13, mid-session):

```bash
py -3.11 tools/glance_export.py --no-frames --include arendt --cluster-by notion \
    --approved-file outputs/_glance-inbox/approved.json \
    --exclude-file outputs/_glance-inbox/cumulative.json \
    --dest outputs/_glance-ledwall
py -3.11 tools/glance_deploy.py --export outputs/_glance-ledwall \
    --out outputs/_glance-ledwall-deploy \
    --pin ledwall --curate --tile-fit contain --max-asset-mb 12 --collection ledwall
py -3.11 tools/serve_glance.py --port 8766        # queue routes ON by default (--queue arendt)
```

- **`--cluster-by notion`**: labor / work / action, in Arendt's order, derived from the
  filename tokens; a file naming none lands in `unsorted`. The field array is sorted
  cluster-contiguous so the card swipe deck walks the argument in order.
- **`--approved-file`**: the ADMISSION GATE. A render that is not in `approved.json`
  never enters the field -- the same shape as the RNMW inbox, where an undecided
  contribution is not in the archive at all. **All new generations queue for the
  founder's review**; nothing walks straight onto the field, including yours.
- **The queue is reviewed at `?review=1`** on the local server: `review.js` builds the
  queue AS a field (batched by notion + day, "render pipeline" as contributor) and
  `review-bar.js` -- the decide surface ported into the white-label from RNMW's editor
  layer -- offers Keep / Reject. Keep grows `approved.json`, Reject grows
  `rejected.json`, originals are never touched; a re-export then moves the decision
  onto the field. serve_glance upgrades the SERVED config to tier 3 for this
  (response-patch; the built file and the Vercel deploy stay tier 0).
- **One server, one port.** serve_glance instances stack on 8766 (Windows SO_REUSEADDR
  lets multiple listeners share the port and requests route arbitrarily -- measured:
  three listeners, a stale one answering). Before starting one, kill the listeners:
  `netstat -ano | grep :8766` then `taskkill //PID <n> //F`.
- **Check `python tools/agent-ops-harness/shared/ship.py claims` before rebuilding these dirs** --
  parallel chats share this tree and two of them fought over this exact build twice.
- **The Arendt gallery builds from `outputs/_glance-arendt`, not `_glance-ledwall`.**
  A sibling chat rebuilds the ledwall dirs on its own schedule and overwrote this
  build twice mid-deploy (once shipping 23 assets where 42 were intended). The
  dedicated dir ends that race; `--pin` is now a free-form NAME, so a new field
  gets its own Vercel project rather than borrowing one.

### The review inbox (2026-08-14)

Pending renders now live in R2, not only on this laptop, which is what lets
review work anywhere:

```bash
py -3.11 tools/inbox_push.py --dry-run     # what is pending, nothing uploaded
py -3.11 tools/inbox_push.py               # original + poster + _batch.json
py -3.11 tools/decisions_pull.py           # bring remote decisions back, then re-export
```

- `tools/glance_queue.py` is the ONE definition of "pending" -- imported by both
  `serve_glance.py` and `inbox_push.py`, so the queue you approve is the queue
  that was pushed. Change the walk there, never in one of the two callers.
- `sync_outputs.py` pushes automatically after a Modal pull; `--no-inbox` skips it.
- **Uploading is not approving.** The inbox touches neither the catalogue nor the
  approve/reject lists; an inbox object is invisible to the field until decided.
- A file in `cumulative.json` (a curation removal) is NOT re-queued -- re-offering
  something the founder removed would resurrect it. Twice during verification the
  "smallest pending file" turned out to be exactly this, which is the rule working.

### The review backend (live 2026-08-14)

Supabase project **`vvnpshvfpbbhhcrzqfol`** ("Slow Interpolation", eu-central-1).
Function at `https://vvnpshvfpbbhhcrzqfol.supabase.co/functions/v1/glance`, source
of truth `$GLANCE_HOME/backend/`. Credentials live in
`tools/.env` (`SI_SUPABASE_*`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`) --
**never paste a key into a shell or a chat; read it from that file**, which is how
every command below is written.

Deploying the gallery WITH review (tier 3) rather than plain tier 0: pass the
three backend flags. A build without them stays tier 0, which is correct for any
field that should not carry a login.

```bash
py -3.11 tools/glance_deploy.py --export outputs/_glance-arendt \
  --out outputs/_glance-arendt-deploy --pin ledwall --curate --tile-fit contain \
  --max-asset-mb 45 --max-mb 700 --no-bundle-proxies --collection ledwall \
  --title "Slow Interpolation" --glance "$GLANCE_HOME" \
  --api-base "https://<ref>.supabase.co/functions/v1/glance" \
  --auth-url "https://<ref>.supabase.co" --auth-anon-key "<anon>" --deploy --prod
```

- **Redeploying the function** after editing the white-label source:
  `cp "$GLANCE_HOME/backend/index.ts" supabase/functions/glance/index.ts`
  then `npx supabase functions deploy glance --project-ref <ref> --no-verify-jwt`.
  `--no-verify-jwt` is required: the function does its OWN editor check and must be
  able to answer 401 itself rather than have the platform reject the request first.
- **Editors are a table, not a config.** Add one with an INSERT into
  `glance_editors` (email is enough, before they ever sign in).
- **The archive catalogue is never touched by review.** Approving records a
  decision; `nyc-billboard/_catalogue.json` is asserted unchanged after every
  inbox run, and that assertion is worth keeping.
- **Approvals reach the field via `decisions_pull.py` + a re-export**, not
  automatically -- the same "in the archive, not yet published" model RNMW uses.
- **The sign-in email must send a CODE, not a link, and Supabase's default does
  the opposite.** `glance/login.js` renders a 6-digit input and calls `verifyOtp`
  with what you type, but the stock `magic_link` template mails
  `{{ .ConfirmationURL }}` -- so the first sign-in produced an email the panel in
  front of you could not use (founder, 2026-08-14). Fixed by
  `supabase/templates/magic_link.html` (`{{ .Token }}`) pushed with
  `npx supabase config push --project-ref <ref>`. `supabase/config.toml` is kept
  deliberately MINIMAL: `config push` writes everything the file declares, so a
  fuller config copied from a template would push defaults over settings nobody
  meant to change. Verified end to end by sending one to a mailbox the email
  bridge can read and asserting the body carried a 6-digit code and no
  `ConfirmationURL`. Note it arrived flagged **[SPAM]** there (Supabase's
  `noreply@mail.app.supabase.io` is not in the bridge's trusted list) -- if an
  editor says no email arrived, check junk before re-sending.

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

**The wall-ready field: filter by GEOMETRY, never by filename.**

```bash
python tools/glance_export.py --no-frames --since-days 8 --collection ledwall \
    --spec 1728x540 --spec 912x2736 --exclude-file outputs/_glance-inbox/cumulative.json \
    --dest outputs/_glance-ledwall
python tools/glance_deploy.py --export outputs/_glance-ledwall --out outputs/_glance-ledwall-deploy \
    --pin ledwall --curate --tile-fit contain --max-asset-mb 12 --collection ledwall --deploy --prod
```

`--spec` keeps only videos whose ACTUAL dimensions match, so the field holds the pieces
cut for the walls and nothing else. It is standing: tomorrow's conform qualifies by
itself, tomorrow's raw render never appears, and no removal list has to be maintained.

**A filename filter was tried first and was wrong.** `conform.py` stamps the geometry into
the name of a plain render, but a client-named delivery file carries no suffix at all, so
`--match '*__a_912x2736.mp4'` found **1 of the 6** files that are actually 912x2736 and
silently produced a horizontal-only field. `--match` still exists for path patterns;
for "is this at wall spec", dimensions cannot lie. They come from `gallery.py`'s
probe-cache, with an ffprobe fallback.

**`--tile-fit contain` for a field of extreme aspects.** The viewer sizes a tile
`w = aspect, h = 1` against a 1.15 to 1.3 unit pitch, so landscape assets overlap; across
a thousand mixed-aspect tiles that IS the dense-mosaic look and must stay in the archive.
At 3.2 (16:5) a tile spans two neighbours and at 0.33 (1:3) it is a sliver. `contain` fits
each tile inside its cell preserving aspect, the same rule review mode already uses. It is
a viewer config field defaulting to `overlap`, so no other project's field changes.

**`contain` also switches the camera padding, and that is what actually made the
verticals legible.** `layoutBounds` pads a fixed 1.5 world units, which is a thin margin
against a thousand tiles and most of the frame against twenty: the 21-piece field
rendered in about a third of the viewport and a 1:3 vertical came out ~35 px wide on a
phone. The viewer already had the fix, `pad by half a cell instead`, but gated to review
mode. It now applies to any `contain` field. Tiles roughly doubled and the field fills
the width. Note the two orientations then measure 0.27 (vertical) against 0.25
(horizontal) world units squared, i.e. verticals are slightly LARGER in area; if they
still read as weaker it is the 1:3 crop being narrow, not a sizing bug.

**Delivery files have no proxy, and that once shipped a link of dead posters.**
`gallery.py` only builds previews for the raw renders it indexes, so a spec-only field was
**0 of 12 playable** on Vercel while the tunnel showed 12. `glance_deploy.py` now falls
back to the original when no proxy exists; at 5 to 6 MB these are the deliverable at the
size it should be seen, so raise `--max-asset-mb` rather than re-compressing them.

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

Real in-field Tier 2 curation lives ONLY upstream of the viewer and would be a
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