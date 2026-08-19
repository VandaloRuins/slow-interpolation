# The Glance viewer (for agents)

You are about to build, deploy, or change something the Glance field renders. Read this
first.

**This is the only tracked file in this repo that answers three questions:** where the
viewer comes from, what belongs to it rather than to us, and what this repo may change
without forking it. Every other page links here. **If another page restates a fact from
this one, that page is wrong by construction, not merely out of date.**

That rule exists because of a measured failure. On 2026-08-19 the viewer's upstream moved,
and an audit found **17 tracked statements in this repo asserting the old one**. Every one
had been correct when written. The direction had been restated in 17 places instead of
stated in one, so it went stale in 17 places at once.

**Last verified: 2026-08-19.** When the topology changes again, this page is the file that
changes.

---

## The viewer is a released dependency, and this repo does not vendor it

`tools/glance_export.py` writes a data contract. `tools/glance_deploy.py` installs a viewer
payload over it at build time and ships the result.

**Nothing under the installed `glance/` directory is ours, and every byte of it is replaced
on the next install.** An edit typed into a built field is destroyed by the next deploy.
That is not a policy you can argue with; it is what `glance_deploy.py` does.

The upside is the thing that makes this arrangement worth keeping: **building a field here
executes the real payload end to end**, which makes it the only true integration test the
viewer has.

## Where it comes from

Resolve it with `--glance <dir>` or `$GLANCE_HOME`, pointing at the **inner `glance/`
directory** (the one containing `install.py`, `serve.py` and `payload/`). On PowerShell the
variable is `$env:GLANCE_HOME`.

**There is deliberately no default.** This repo is public, so no machine path and no
checkout name is baked into the tooling. See the comment at `tools/glance_deploy.py:51-53`,
which states the same rule at the point it is enforced.

- **The value for THIS machine** lives in `CLAUDE.local.md`, which is gitignored. If it is
  not there, ask the maintainer. Do not guess a sibling directory, and never write a
  resolved path into a tracked file.
- **To obtain a copy**, the viewer ships as an invite-only kit,
  `Ruins-Harness_Tools-for-Agents`, whose `glance/install.py` is what `glance_deploy.py`
  calls. The maintainer grants access.
- **Upstream of that kit is a private working repo you will not have.** Requests for viewer
  changes go to the maintainer, **described by behaviour**. Do not name a path and do not
  expect to edit it yourself.

## The decision: would another archive want this?

Before you change anything the viewer renders, answer that one question. It is a lookup,
not a judgement call.

**Yes, another archive would want it, so it is not yours to write here.** A layout bug,
cards overlapping, a missing button, a config key any adopter would set, a data-contract
field, anything under the installed `glance/` directory. Hand it to the maintainer by
describing the behaviour. A change made in a local checkout of the viewer is destroyed by
the next install, and a change that helps every adopter should not live only here.

**No, it is specific to this project, so it stays here.** How our outputs become a
catalogue (`tools/glance_export.py`), how a field is assembled and shipped
(`tools/glance_deploy.py`), the tier 0 curation face (`tools/glance_curate.js` and
`tools/glance_curate_hide.js`), the review queue (`tools/glance_queue.py`,
`tools/inbox_push.py`, `tools/decisions_pull.py`), which Vercel project a field pins to, and
every `.glance-*-vercel.json`. These go through the injected layer below, **never into the
installed payload**.

**Neither, so it is a decision.** Anything you cannot place in a minute. Ask before
building, exactly as the manual-scan rule says.

When genuinely torn, **build it here**. A local extension that should have gone upstream is
a duplicate somebody will find. An upstream change that should have stayed local is imposed
on every other adopter, and you cannot see them.

## The injected layer: what you may add without forking

`glance_deploy.py --curate` copies two files out of `tools/` into the built site and patches
two `<script>` tags into the installed `index.html`. **The payload itself is never edited.**
This is the sanctioned way to add behaviour that is ours alone, and it is the only one.

The mechanism is documented where it happens and is not repeated here, because a second
copy is a second thing to go stale. Read the header comments in
[`tools/glance_curate.js`](../../tools/glance_curate.js) and
[`tools/glance_curate_hide.js`](../../tools/glance_curate_hide.js), and the injection block
at `tools/glance_deploy.py:378-407`.

**One rule you must get right when adding a new extension**, because getting it wrong ships
something silently inert:

- **Anything that observes or patches a fetch is a CLASSIC script, injected before every
  module.** `glance.js` calls `boot()` at module evaluation, so it starts fetching the
  catalogue the moment it runs. Modules are deferred and classic scripts execute during
  parsing, so a fetch patch installed from a module is always too late.
- **Anything that adds UI once the field exists is a MODULE**, injected after `glance.js`.

The existing pair is the worked example of each: `curate-hide.js` is classic and pre-boot,
`curate-static.js` is a module.

### When the build asserts on index.html

`glance_deploy.py` asserts that two exact anchors exist in the installed `index.html` before
injecting anything:

```
<script src="glance/glance.config.js"></script>          # the hide shim goes after this
<script type="module" src="glance/glance.js"></script>   # the curation face goes after this
```

Those asserts are a **compatibility gate against the viewer**, not defensive validation.
They exist because a patch that prints success proves nothing: `str.replace` on a
non-matching needle changes nothing and returns happily.

If one fires, the viewer's `index.html` changed shape. That is a fact about the upstream,
and it is the earliest warning you will get that your checkout moved.

- **Never delete or soften the assert.** Doing so ships a field whose curation face is
  present in the bundle and dead in the browser, which reads to a curator as "remove does
  nothing" and to an agent as "the deploy worked".
- **Re-read the installed `index.html`**, find the new anchor, and fix the needle here. A
  changed script tag is a fix on our side; this repo owns its own injection.
- **If the anchor is gone entirely** rather than renamed, the viewer no longer supports
  pre-boot injection. That is a conversation with the maintainer, not a local patch.

## What the contract already gives you

Before building anything, check whether the viewer already does it. The published data
contract (`glance/docs/data-contract.md`, inside the kit) documents the tiers, the
join, the presentation switches, and an explicit extension seam. Several things that look
like missing features are dormant capabilities with no caller at tier 0, which is exactly
why `glance_curate.js` exists: the selection machinery was already there.

**The join is what breaks integrations**, and it is silent when wrong:
`field.assets[].sha` = `atlas.tiles[key]` = `catalogue.assets[].sha256[:16]` =
`thumbs/<sha>.jpg`. An asset in the field with no atlas tile is skipped without an error,
so a mismatch shows up as an empty or thinned field rather than as a failure.
