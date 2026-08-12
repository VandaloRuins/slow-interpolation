# Slow Interpolation Glance gallery — archive, galleries, curation, and the generative direction

**Status 2026-08-12:** the archive is live. The gallery and curation layers need a backend
that does not exist yet. This file is the plan; it is not a record of shipped work.

Glance itself is a separate white-label tool (`Ruins-Harness_Tools-for-Agents/glance/`).
This repo does not vendor it; `glance_deploy.py` resolves it at build time via `$GLANCE_HOME`
/ `--glance`. **Building a field here executes the white-label payload**, which is also the
only end-to-end test that tool has. Changes flow RNMW -> white-label -> here, never
RNMW -> here directly.

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

### The architectural fork, unresolved

Glance's tiers 0-3 are all about *viewing and curating an archive*. Generation is not a
higher tier of that; it is a different axis. Either it becomes tier 4, or it is a **sibling
service that writes into Glance's inbox**. Leaning sibling: it keeps the white-label a
viewer anyone can deploy, rather than something that requires a Modal account.

---

## Open work

| # | Item | Note |
|---|---|---|
| SI-1 | **Backend for tier 3** — SI's own Supabase + its own glance Edge Function against `slow-interpolation-media` | Decided 2026-08-12: SI gets its OWN, not RNMW's. Unlocks the user icon, the shelf, and approve |
| SI-2 | **Port the missing tier-3 surfaces** through the white-label first | `upload/contrib/editor/write` are `exclude` in the manifest. RNMW -> white-label -> SI, never direct |
| SI-3 | **Arendt clustering**: labour / work / action | Derives cleanly from `labor_*` / `work_*` / `action_*` under `outputs/arendt/`. **4 videos exist today**; `work_chair` fails twice per commit `cfedbad` |
| SI-4 | **Two galleries**: "full archive" (video only, 323 clips) and "OBJKT lab" (Arendt only) | Needs SI-1 for the shelf; two separate fields are possible without it |
| SI-5 | **Ingest the rest of the tree** | Wave 1 was `nyc-billboard` only. Whole tree is 3,497 files / 19.1 GB |
| SI-6 | **132 keys do not mirror their source tree** | Deliberately not fixed: no move verb, and the alternatives are a 4.7 GB re-upload or hand-rewriting the catalogue. `source` records true origin |
| SI-7 | **`NY1087B` and `NY1087C` are byte-identical** | Founder eye needed: deliberate (shared 1728x540 spec) or a delivery error in a client folder |
| SI-8 | **Curation exclude list has over-accumulated** | `cumulative.json` holds 109 exclusions against a 68-asset field, cutting it to 7. The skill doc's own rule is to assert tile count before deploying |

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