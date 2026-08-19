# Render gallery (for agents)

You are an AI agent helping the maintainer look at renders. A finished render is
3,600 frames in a file you cannot open; the gallery is how it reaches a human
eye. Your job is to keep it truthful, stand it up, and read back what the
maintainer writes on it.

**This is not [gallery.md](gallery.md).** Two different tools share one word:

| Page | Tool | Serves | Reviewer |
|---|---|---|---|
| [gallery.md](gallery.md) | `tools/gallery_server.py` on `datasets/<name>/` | LoRA training candidates | a workshop student, keeping or cutting images |
| **this page** | `tools/gallery.py` on `outputs/` | finished MP4s and keyframe PNGs | the maintainer, judging renders |

Only this one deals with video, delivery specs and feedback notes. If the task
mentions a dataset or a student, you are on the wrong page.

## The whole-outputs view (Glance)

`gallery.html` answers "look at this batch". It cannot answer "what have we
actually rendered", because 3,000 renders in a vertical list is not a shape you can
see. `tools/glance_export.py` publishes `outputs/` as a **Glance** archive: one
WebGL field, every render a tile, clustered by run, reflowing under a query.

```bash
python tools/glance_export.py --no-frames --dest outputs/_glance-renders   # 418 finished renders
python tools/glance_export.py                                              # 2,951, keyframes included
```

Then serve it with the viewer (a separate tool, resolved via `$GLANCE_HOME`):

```bash
python <path-to>/glance/serve.py --data outputs/_glance-renders --originals outputs
```

`--originals` is what lets video play: each record carries a direct `media_url`, so
the card plays the MP4 straight off disk with no signing endpoint and no backend.

**Which view.** `--no-frames` is the gallery view and the one to default to: 418
finished renders, legible clusters. The full export is 2,951 tiles and is dominated
by 2,533 keyframes, which is honest but buries the renders. The full one is worth
opening when the question is about a run's drift rather than about a deliverable,
because a sequence reads as a colour arc across its cluster.

Glance knows nothing about this repo. It reads a published data contract
(`glance/docs/data-contract.md`), and `glance_export.py` is this repo's
implementation of it. Output under `outputs/_glance*` is a build artifact:
regenerate it, never edit it. Nothing in the exporter reads or writes a render.

## The three tools

| Tool | Does | Run it when |
|---|---|---|
| `tools/sync_outputs.py` | pulls artifacts off the Modal volume, then rebuilds | after any cloud render |
| `tools/gallery.py` | scans `outputs/`, writes `gallery.html` | after anything changes on disk |
| `tools/serve_gallery.py` | serves it to the LAN or a tunnel | only when the maintainer needs a phone |

```
python tools/sync_outputs.py --prefix coe_       # sync + rebuild
python tools/gallery.py --open                   # rebuild only
python tools/gallery.py --refresh                # rebuild + re-extract posters
```

For getting it onto a phone, follow the `publish-for-review` skill. It owns the
tunnel procedure and the security checks. This page owns what the thing is.

## The rule that has broken most often

**The page is a build artifact. Nothing rebuilds it for you.** A render can
finish, land on disk, and be invisible.

`sync_outputs.py --no-gallery` skips the rebuild. That flag was passed three
times in one session and each time the maintainer reported the new renders
missing. If you pass it, you own rebuilding afterwards. Prefer not passing it.

Before you tell the maintainer a render is on the page, confirm the count went
up. `gallery.py` prints `N renders indexed`; a stale N is the tell.

## What the maintainer sees (your briefing crib sheet)

One card per MP4, plus one strip card per keyframe PNG directory.

**Front of a video card:** poster still (tap to play inline), title, tags, a
delivery-spec badge when the file matches a known spec, then a collapsed
`details` summarising `WIDTHxHEIGHT . DURATION . SIZE`. Open it for the full
spec list: sampling budget, backbone, VAE kind, LoRA scale, RIFE scheme, segment
frame counts. A second `Generation info` fold holds the prompts.

**Download row:** `Download <size>` is the full-quality original. `Small <size>`
appears only when a web proxy exists. `Notes` flips the card.

**Back of a card:** a textarea. Whatever is typed there persists.

**Header:** search over name and prompt, a `Filters` chip revealing the tag bar,
`With notes` to show only annotated cards, `Clear`, and `Save feedback`.

**Stills cards** span the full row as a horizontal strip, ordered so `0000.png`
is first and the last keyframe is last. That ordering is the point: it is the
comparison the maintainer actually makes.

## The feedback contract

This is the only path by which the maintainer's judgement reaches you.

1. They type notes on card backs. Every keystroke goes to `localStorage` under
   `si-gallery-feedback`, so a reload or a dropped tunnel loses nothing.
2. They tap **Save feedback**. The browser downloads `gallery-feedback.json`.
3. They move it to the repo root. The page tells them to, and to tell you.
4. Next `gallery.py` run loads it and re-renders the notes into the cards, so
   notes survive a rebuild and a `*` marks annotated cards.

The keys are `video.stem` for renders and the directory title for stills. Read
the file directly when the maintainer says they left notes; do not ask them to
retype into chat.

**`gallery-feedback.json` is gitignored and must stay that way.** It is
commentary on unreleased work and has held client and venue names. This repo is
public.

## Caches, and when they lie

| Path | Holds | Stale when |
|---|---|---|
| `outputs/_gallery/posters/` | one extracted still per video | the video is replaced under the same name. Fix with `--refresh` |
| `outputs/_gallery/previews/` | web proxies | rarely; keyed off the source |

A file over `PREVIEW_OVER_MB` (25) gets a proxy: max 1280 wide, CRF 26,
`+faststart`, audio stripped. This is not cosmetic. A 363 MB delivery master
will not stream to a phone over a tunnel however good the connection, and
without `faststart` the browser must download the whole file before the first
frame because the moov atom sits at the end.

Both directories are excluded from the scan by the `_gallery` path check, so
proxies never appear as renders in their own right.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| new render missing | page not rebuilt | `python tools/gallery.py`; check the printed count |
| nothing on the page responds | a JS syntax error kills the whole `<script>` | open it in a real browser and read the console. A literal newline inside a quoted JS string has done this |
| card will not play or flip | invisible back face over the front | the unflipped back needs `pointer-events:none` |
| plays on desktop, not on phone | no Range support, or the file is too big | `serve_gallery.py` answers 206; confirm a proxy exists |
| phone shows an old page | HTML cached | `Cache-Control: no-store` is set for HTML only. If it recurs, check it survived an edit |
| poster is the wrong frame | cached from a previous file of the same name | `--refresh` |
| notes vanished | exported JSON never moved to the repo root | it is in their Downloads |

## What it does not do

No write-back from page to disk, no deletion, no re-render, no auth. It is a
read-only view plus a manual JSON round-trip. Anything destructive is yours to
run deliberately.

It also does not judge. A spec badge is arithmetic against a known delivery
spec, not an opinion that a render is good. Sharpness, motion and subject
verdicts come from [visual-diagnosis](../../.claude/skills/visual-diagnosis/SKILL.md)
and the deep skills it routes to, never from the gallery.
