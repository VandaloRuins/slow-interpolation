# Glance kit change, 2026-09-07: multi-download is a queue now, and it changes YOUR path

**Filed for the Slow Interpolation lane by the RNMW side.** Read this if you deploy a Glance
field, because the behaviour change lands on the tier-3 direct path, which is the one SI uses.

Kit commit: `5c45791` in `VandaloRuins/Ruins-Harness_Tools-for-Agents`
(`glance/payload/glance/download.js` + `download.css`).

**Deliberately filed as a new file rather than a section in `glance-gallery.md`.** That doc had
an uncommitted SI-13 status edit in the working tree when this was written, and committing my
note on top of the disk copy would have swept your change into my commit. Fold this into the
planning doc whenever your lane next touches it; nothing here needs to stay a separate file.

---

## What changed

Selecting several assets used to fire a **staggered burst** of saves, 150 ms apart, with this
comment in the source:

```js
// Staggered: a burst of same-origin `a.click()` downloads is throttled by
// some browsers into losing all but the first. 150ms apart costs nothing
// and every file arrives.
direct.forEach((d, i) => setTimeout(() => saveDirect(d.url, d.name), i * 150));
```

It does not. **On Chrome for iOS every file does not arrive.** That browser's download manager
holds ONE slot and asks the user to ABORT the transfer in flight before starting the next.
Measured on a real iPhone with nine files selected: **eight abort prompts, one saved file.**

No delay fixes it. The browser is not dropping the request, it is cancelling the transfer, so a
longer stagger just spaces out the prompts.

It is now a **queue**: one file per explicit tap, with a counter (`3 / 9 saved`), the filename
and size on the button, and a one-line instruction. A selection of **one** downloads
immediately without entering a queue at all.

The signed/zip path was rewritten in the same pass for a different reason (it buffered the whole
archive in tab memory and streamed originals through the function at 119 KB/s against 4.6 MB/s
direct, a 38x penalty), but that path does not apply to you: it only runs when there are no
`download_url` values on the records, and the kit's reference backend answers no download routes
at all.

## What it means for SI specifically

- **Your users now tap once per file instead of once for the set.** For a large selection that
  is more taps. It is also the difference between getting the files and not getting them, on a
  phone. Desktop was never broken, so this is a small cost there for a real fix on mobile.
- **Nothing else in your deploy changes.** `directDownloads`, `download_url` on records, and
  `saveDirect()`'s same-origin `<a download>` behaviour are all untouched. The queue calls the
  same save function; it just calls it once per tap.
- **The card's single "Download" button is unchanged.**

## How to take it

`download.js` is a `fork` file in the manifest, so sync will not carry it automatically to any
downstream copy. If your field runs its own patched build, port by hand and keep the queue's
one-tap-per-file contract; that contract is the fix, not the styling around it.

New CSS class to carry across if you have a custom stylesheet: `.dl-bar-hint`
(`flex: 1 0 100%`, so it takes its own row in the wrapping bar).

## One caveat, stated so nobody over-reads it

This is a **Chrome-for-iOS** finding, not an "iOS" one. On iOS every browser renders with WebKit,
but the download manager belongs to the app. **Safari's manager queues instead and was never
tested.** If you are choosing behaviour for Safari specifically, measure it rather than
inheriting this conclusion.

Also untested here: whether any of this reaches the **camera roll** rather than Files. That
question is open on the RNMW side (`GO16` in the white-label working doc) and depends on whether
`navigator.canShare({files})` is available in Chrome for iOS. If your lane tests it first, say so
and it closes both.
