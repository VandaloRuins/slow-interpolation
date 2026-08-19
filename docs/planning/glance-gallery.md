# Slow Interpolation Glance gallery — archive, galleries, curation, and the generative direction

**Status 2026-08-12:** the archive is live. The gallery and curation layers need a backend
that does not exist yet. This file is the plan; it is not a record of shipped work.

**2026-08-12, later session: the backend is designed.** [glance-backend-design.md](glance-backend-design.md)
decides the fork (generation = sibling service, not tier 4), fixes the `si-run/1` run
record schema (deliberately also the future job schema), rescopes SI-2 (the port that
matters is a reference BACKEND into the white-label; the white-label ships none today),
and inverts one sequencing item (run record first, before any backend). Read it before
building anything below.

Glance is a released dependency this repo does not vendor. Where it comes from, and
whether a change belongs upstream or here, is stated in exactly one place:
[../manual/glance-viewer.md](../manual/glance-viewer.md). **Building a field here executes
the real viewer payload**, which is also the only end-to-end test that tool has.

**2026-08-19: the viewer's upstream moved.** Rows closed before that date name the topology
that was correct when they were written and are left as dated history. Nothing in the Open
work table below is authoritative about where a change belongs today.

---

## Where things actually are

**Archive: DONE and verified.** Cloudflare R2 bucket `slow-interpolation-media`, public
access off, credential bucket-scoped (a leak cannot reach `rnmw-media` or `edmund-media`).
Installed from the portable `media-archive` kit, second instance after Dark Tales.

    py -3.11 tools/media_archive_verify.py     # 18 passed, 0 failures, READY
    py -3.11 tools/archive_wave.py --source outputs/<x> --prefix <x> [--stage-mixed]

Wave 1 (`nyc-billboard`) catalogued **915 assets**, verified complete: every source sha256
present, zero missing, zero assets left with a meaningless event tag.

**Captions are deliberately OFF.** Founder direction: SI wants to see outputs clustered by
LoRA, not Gemini scene tags. Ingest runs with no provider and says so per asset.

**Gallery + curation: BLOCKED on a backend.** Proven in the shipped code, not assumed:

    index.html:89    if (tier < 1 || !hasAuth) return;      // tier 0 loads no auth module
    index.html:107   if (tier >= 3) mod("glance/curations.js");
    curations.js     self-gates AGAIN on /api/tree answering

The fields deployed from here are **tier 0**. So there is no user icon, and the
"galleries you curate" shelf is never fetched — twice over. This is not a defect in the
viewer or a gap in the white-label (which ships `curations.js` with the same gating as
RNMW). It is the absence of a backend for tier 3 to talk to.

---

## The three layers, in RNMW's vocabulary

RNMW already implements all of this; the words matter because the code uses them:

| layer | what it is | RNMW's mechanism |
|---|---|---|
| **archive** | everything, unfiltered | R2 bucket + in-bucket catalogue |
| **gallery** | a project's whole body of work | a Glance field over a catalogue slice |
| **curation** | the reviewed best-of | **a share** (`/api/shares`, `share-update`, `share-revoke`) |
| **approve** | pending -> visible | **promote out of the inbox** (editor-gated) |

So "make a curation" is "mint a share", and "approve" is "promote". Both exist. The
white-label already ships the shelf (`curations.js`) and the review viewer (`review.js`);
it **excludes** `upload.js`, `contrib.js`, `editor.js`, `write.js` — the intake, the editor
gate and the write surface. Those are the pieces that must be ported through the
white-label before SI can use them.

**One simplification specific to SI:** the contributor here is a MACHINE (this repo,
finishing a render), not an invited human. The submit half needs no upload UI at all — it
writes to the inbox prefix with a token it already holds. Only review/approve needs a real
UI and a real identity.

---

## The generative direction (founder, 2026-08-12)

The long-term shape: **a gallery per project; choose among custom models and pipelines;
give prompts; outputs arrive for approval; approved work lands in the gallery and can be
curated.** A personal alternative to Midjourney, built on custom Modal pipelines.

This changes what the backend must be. Review-and-approve is CRUD over an existing
archive. Generation additionally needs:

- **job dispatch** to Modal that does not block a browser
- **job state** across minutes (queued / running / failed / done)
- **a callback path** landing outputs in the inbox
- **a model/pipeline registry per gallery** (which Modal app, which LoRA, which params)
- **cost accounting**, which must be authoritative and therefore server-side

None of that has a tier-0 or local-only version.

### Recommended sequencing, and the reason

Build the **archive + review/approve** backend now: it is well understood, it ports from
RNMW, and it is needed whether or not generation ever lands. **Design its schema so job
dispatch attaches later without a rewrite.** Do NOT build the dispatcher until the Modal
pipeline stabilises — it is explicitly not settled (the current blocker is artefact-free
output), and building a UI against a moving contract encodes it twice.

### Design the run record NOW even though the dispatcher waits

Every asset must be able to name the run that made it, from day one.

This is not speculative. **GO4 closed 2026-08-12 as unrecoverable**: provenance died when a
file was copied and renamed, and the LoRA behind 13 assets could not be recovered by any
means — no manifest for `led16_*`, none in `delivery/` or `candidate*/`, and exact sha256
matching of all 11 orphaned deliverables against every `led/` render returned **zero**.
`conform.py` now carries provenance forward, but nothing recovers the past.

At 900 assets that is an annoyance. At generation volume with cost attached per job, it is
fatal. Today's failure is a preview of the schema mistake.

### The architectural fork -- RESOLVED 2026-08-12: sibling service

Glance's tiers 0-3 are all about *viewing and curating an archive*. Generation is not a
higher tier of that; it is a different axis. **Decided: a sibling service that writes into
Glance's inbox** -- sibling in contract, roommate in infrastructure (same Supabase
project, second Edge Function, same JWT and editors table). Full argument with the code
evidence: [glance-backend-design.md](glance-backend-design.md) section 2. The short form:
the contract's own extension seam says new content arrives as archive shapes, the
machine-contributor already makes the inbox the callback path, and tier 4 would couple a
viewer anyone can deploy to a Modal account.

---

## Open work

| # | Item | Note |
|---|---|---|
| SI-1 | **Backend for tier 3** — SI's own Supabase + its own glance Edge Function against `slow-interpolation-media` | Decided 2026-08-12: SI gets its OWN, not RNMW's. Unlocks the user icon, the shelf, and approve. Concretized in [glance-backend-design.md](glance-backend-design.md) section 1: one auth + editors gate + one batch table + one Edge Function; no captioner, no events registry |
| SI-2 | **RESCOPED 2026-08-12: port a reference BACKEND through the white-label** | The white-label ships NO backend (viewer + contract only), so SI deploying RNMW's `index.ts` directly would violate the porting rule. Real port: RNMW Edge Function -> trimmed reference backend in the white-label -> SI deploys it. The old targets `upload/contrib` are not needed (machine contributor); `editor/write` deferred. Design doc section 1 |
| ~~SI-3~~ | **CLOSED 2026-08-13: the Arendt field clusters by notion, in Arendt's order.** `glance_export.py --cluster-by notion` derives labor / work / action from the filename tokens (position-independent: `arendt_work_chair_fast` files under work), `unsorted` for a file naming none, explicit order labor(1)/work(2)/action(3) because encounter order is alphabetical and would misstate the argument; the field array is sorted cluster-contiguous so the swipe deck walks the argument in order. **PLUS the admission queue, in the white-label's own vocabulary** (founder correction 2026-08-13: no invented UI): a render not in `approved.json` never enters the field -- the RNMW-inbox shape -- and the queue is reviewed at `?review=1`, where `review.js` builds it AS a field and the newly ported `review-bar.js` (Ruins `0c458b4`, hand-ported from RNMW's editor layer, RNMW untouched) offers Keep/Reject against serve_glance's local `/api/contributions` + `/api/contribution-decide` + `/api/contribution-presign`. Keep grows `approved.json`, Reject grows `rejected.json`, originals never move; the served config is response-patched to tier 3 (built file and Vercel stay tier 0). Queue is VIDEOS only (the first verification pick was an anchor PNG -- working files are not generations) | Verified end to end: field 11 tiles labor 7 / work 1 / action 3 contiguous; queue 4 real new renders (`grow_*`); bar drove Keep 1 -> allowlist grew server-side, then reverted (the decision is the founder's); tunnel serves both surfaces. **Five of the 16 ratified keys went stale mid-session** (the render chat renames files as it iterates) -- re-admit the renamed versions via the queue. Note: `grow_*` names carry no notion token, so they will land `unsorted` unless renamed or a mapping is added |
| SI-4 | **Two galleries**: "full archive" (video only, 323 clips) and "OBJKT lab" (Arendt only) | Needs SI-1 for the shelf; two separate fields are possible without it |
| SI-5 | **Ingest the rest of the tree** | Wave 1 was `nyc-billboard` only. Whole tree is 3,497 files / 19.1 GB |
| SI-6 | **132 keys do not mirror their source tree** | Deliberately not fixed: no move verb, and the alternatives are a 4.7 GB re-upload or hand-rewriting the catalogue. `source` records true origin |
| SI-7 | **`NY1087B` and `NY1087C` are byte-identical** | Asked 2026-08-12; founder answer: **"not sure, will check the client folder"**. Stays open on the founder's side; nothing here can resolve it. Note both B and C are also excluded from the ledwall field (01:25 hand session), consistent with a curator seeing two identical tiles |
| ~~SI-8~~ | **CLOSED 2026-08-12: the union was right after all.** Audited post-by-post: `rejected/` correctly quarantines the 60-card long-press MISTAKE (37 of its keys re-entered ONLY via later deliberate hand passes); `applied/` holds only real sessions (the documented 74->36 pollution mode is absent); the 23:19 post is an identical re-post of 16:53 (deduped). Of 109 entries ~57 target wall-spec assets: founder hand passes cut ~29, `agent-excluded.json` cuts 23 (led18 style series, led20/21 sweeps, flowmasks). **Founder ratified the 7-tile field as the intended show.** Standing rule unchanged: assert tile count against `previous - len(latest)` before any deploy | done. `agent-excluded.json` provenance now documented in `outputs/_glance-inbox/README.md` |
| SI-9 | **Emit `si-run/1` from BOTH render paths + carry `run_id` through ingest and conform** | The new first item, ahead of any backend: extend `cloud/manifest.py`, add local-CLI emission, teach `archive_wave.py`/ingest the sidecar, re-stamp outputs in `conform.py`. Plus `pipelines.json` (registry v0). Schema fixed in [glance-backend-design.md](glance-backend-design.md) section 3 |
| ~~SI-10~~ | **CLOSED 2026-08-13: the deploy patch is gone and the config drives it.** The white-label viewer now reads `videoLoop` (optional, default **false** — a talk or documentation recording must not restart itself), so `glance_deploy.py` sets `"videoLoop": True` in the config it writes and the `card.js` force-patch is **deleted** rather than left alongside. Deleting it is the point: a hardcode that outlives its config field silently outranks it, and whoever later set `videoLoop: false` would watch the field keep looping with nothing in the tree explaining why | done. **Controlled A/B on the same build** (built from the edited white-label checkout, served no-store, `anchored/t2_anchor_050.mp4`, 10.933 s, seek to `duration - 0.25`, 2.5 s wait — the two builds differ in exactly one line of `glance.config.js`): `videoLoop: true` -> `loop=true, ended:false, paused:false, currentTime 2.233` (wrapped and still playing); `videoLoop: false` -> `loop=false, ended:true, paused:true, currentTime 10.933`. Range curl on `/media/anchored__t2_anchor_050.mp4` -> **206** (`bytes 0-1023/595863`). Console clean apart from the known favicon 404 |

| ~~SI-12~~ | **CLOSED 2026-08-13 (reworked same day, founder correction: no new download UX).** `download_url` -- `media_url`'s download sibling, tier 0, additive -- is rendered by **`download.js`'s OWN surface**, not an invented row (which was built first and then deleted, Ruins `e1df328`): the card's `dl-btn` "Download original", the Select fab, and the "Download N" selection bar, pixel-identical to tier 1, running direct when `directDownloads: true` is declared. `auth.js` became a lazy hasAuth-gated import so the module loads on auth-less deploys; signed-in tier 1 still prefers the presign path (it feeds the download log). serve_glance patches `download_url` into the catalogue RESPONSE (originals only, never a proxy) and serves `/originals/<key>` with Range + attachment | Verified by driving: card `dl-btn` works signed-out; "2 photos / Download 2 / Cancel" bar downloaded TWO REAL FILES to disk via the iframe saver and exited select mode; flag off -> no fab, no button, even with URLs present. The FUTURE public deploy (SI-1) flips to tier 1 presign -- same UI, backend-signed |
| SI-14 | **Review/approval works off this laptop: the R2 inbox + the decision loop** | **BUILT 2026-08-14, one step from live.** The gap was never the UI (that was done and driven): pending renders existed only on local disk, so no hosted page could show them. Now: `tools/glance_queue.py` holds the ONE walk that defines "pending" (imported by both the server and the uploader, so they cannot disagree); `tools/inbox_push.py` pushes original + poster + a `_batch.json` sidecar to `inbox/<notion>/<day>/` via `media_store.upload`, idempotent by sha256; `tools/sync_outputs.py` calls it after every Modal pull (`--no-inbox` opts out); `tools/decisions_pull.py` brings remote decisions back and maps inbox keys to local keys through the sidecar's `origin`. The white-label gained a **reference backend** (`glance/backend/`, Ruins `cc27cbd`): contributions + contribution-presign + contribution-decide, the editor allowlist copied from RNMW's migration, and a decisions table. **Two deviations from RNMW, deliberate:** batches derive from the object store rather than a table (so the render machine needs no database credential), and approving records a decision without copying bytes (SI's field builds from local disk, so copying would mutate a catalogue nothing reads) | Verified against the real bucket: file + poster + sidecar landed, sha256 and origin in the object metadata, **`nyc-billboard/_catalogue.json` byte-identical before and after** (etag `a061fa2d…`), re-run skipped the upload. Full loop rehearsed with a stubbed PostgREST: push -> remote approval -> `decisions_pull` mapped `inbox/labor/2026-08-13/labor_breath.mp4` back to `arendt/labor_breath.mp4` -> merged -> re-export put it on the field. **The Edge Function itself is UNRUN** (no Deno locally); it is verified when deployed. **Blocked on the founder: a Supabase project + secrets** |
| ~~SI-1~~ / ~~SI-2~~ | **CLOSED 2026-08-14: SI has its own backend, live and verified.** Supabase project **`vvnpshvfpbbhhcrzqfol`** ("Slow Interpolation", eu-central-1, micro, in the founder's PRO org). Schema from the white-label's `glance/backend/schema.sql` applied over the session pooler (`glance_editors` + `am_i_glance_editor()` + `glance_decisions`); founder seeded as the SOLE editor; R2 secrets set via `supabase secrets set`; the Edge Function deployed from `glance/backend/index.ts`. The gallery build now takes `--api-base/--auth-url/--auth-anon-key` and flips itself to **tier 3**, which wakes the review surface | **Every route driven against real data** with a TEMPORARY editor that was deleted afterwards (project left with one editor, zero decision rows): anon -> **401**, signed-in non-editor -> **403**, editor -> **200** with the real queue (sha256 populated, thumbnails signed); presign returned a URL that answered **206**; presign OUTSIDE `inbox/` -> **400**; decide(approve) -> item left the queue; re-deciding the same key as reject -> **first decision stood** (idempotent); presign on a decided key -> **404**. Live site signed out: no pill, no review bar, login panel is email-code only (no Google), downloads still save real files. **6 renders are in the queue now** |
| SI-13 | **Public domain (`si.vandalo.art`) + magic-link admin** | Founder request 2026-08-13; checked the same day: NO parallel chat has started it (no Supabase project, no claims, nothing in the trackers). This is SI-1 + SI-2 executed plus deployment: reference backend port -> white-label -> SI's own Supabase (email magic-link auth = Supabase email OTP, founder as sole editor), fields to tier 1/3, `si.vandalo.art` DNS -> Vercel. Everything shipped today (review-bar, download, shelf, curate) works unchanged against it -- the local serve implements the same contract routes the Edge Function will. Spawn brief in the session log |
| ~~SI-11~~ | **CLOSED 2026-08-13: card swipe navigation + gesture dismissal, shipped in the white-label viewer as config.** Founder chose option A (deck = the field's own cluster-contiguous order, query-faded tiles skipped exactly as taps skip them) with the camera-follow glue (the card is a lens: `camT` glides to each card's tile underneath, so closing lands where you travelled) and the long-swipe dismissal with the X removed. Two additive config keys, both default-conservative: `cardNav` (false) and `cardCloseButton` (true); SI's deploy sets `true`/`false`. Whole-card gestures arbitrate by dominant axis after a 14px slop: interactive elements keep their taps, the video's bottom 48px stays with the scrub bar, a scrolled body keeps native scrolling; a **short fast flick can no longer dismiss** (surface drags carry a 33%-of-sheet travel floor; the grip keeps its tuned flick) | done. Verified by driving the served build: X `display:none`; arrows walk the deck both ways and STOP at the ends (card stays open, no wrap); touch swipe left/right navigates; short fast flick (1.0 px/ms, 14%) snaps back open; long slow drag (~90%) and long fast swipe (1.9 px/ms, 45%) both dismiss; camera follow proven by screenshot pixel-diff (60.5% of the field half changed across three navs; the first canvas readback returned 0 because WebGL drawImage is blank without preserveDrawingBuffer — a readback artifact, not a finding). **Falsified on the same build with config off**: X visible, arrow inert, swipe inert, X closes, videoLoop unaffected. Console clean bar the known favicon 404 |

## Two kit defects found while building this

- **`ingest.py` accepts an event value that `set-event` rejects.** `led10_a_fall` passes
  ingest and fails set-event's kebab-case validation. The two write paths disagree.
- **`set-event` updates `_catalogue.json` but not `_manifest.json`.** So
  `media_store.py manifest --show` reports stale tags after any write. This cost a false
  "silent no-op" diagnosis: the repair had worked and the wrong file was being read.

## The trap that cost the most, so it is not repeated

`ingest.py` builds keys from `path.name` alone and walks with `rglob`. Point it at a parent
and the whole subtree flattens into one prefix. On this tree, 23 filenames appear in more
than one directory and `0000.png` exists in **71** separate `keyframes/` dirs.

`tools/archive_wave.py` ingests one run per leaf and **refuses any directory holding files
AND subdirectories** (exit 3, naming each offender). Use `--stage-mixed` for those. The
first driver already did per-directory ingest and still flattened 132 objects, because it
enumerated "directories containing files" and two of them were not leaves.