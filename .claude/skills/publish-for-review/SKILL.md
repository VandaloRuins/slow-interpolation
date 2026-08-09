---
name: publish-for-review
description: Publish renders to the browser gallery and, when asked, to a phone over a Cloudflare tunnel. Use whenever the user says "check the gallery", "send me the link", "I want to see it on my phone", "update the gallery", or after any batch of renders lands. Encodes the six silent failures that made this waste an afternoon on 2026-08-08: none of them raised an error, and each one made the agent tell Luca to look at something that was not there or would not play.
---

# Publish for review

The whole point is that Luca sees the work. Every failure this guards against was
**silent**: the command exited zero, the file looked right, and the page was wrong.
So the rule underneath all of it is: **verify the way the user will experience it,
not the way you produced it.**

## The sequence

1. **Sync and rebuild together.** `python tools/sync_outputs.py --prefix <name>`
   It pulls from the Modal volume AND rebuilds the page.
2. **Confirm the render is IN the page**, not just on disk.
3. Only if the user wants it on a phone: **serve, tunnel, verify through the tunnel.**
4. Give the link with what to look at and why.

## Traps, all of which have actually happened here

**`--no-gallery` skips the rebuild.** It kept three renders (v6, v9, v10) out of the
gallery on 2026-08-08 and each time the agent said "it's live". If you pass it during
analysis, you MUST run `python tools/gallery.py` before telling anyone to look. The
tool now prints a loud warning; do not ignore it.

**A code change is not a page change.** Editing `tools/gallery.py` does nothing until
the page is rebuilt. "The markup is in the source" is not "the user can see it".

**Check the served page, not the file on disk.**
`curl -s "$URL/" | grep -c "<name>"` is the test. Disk and tunnel disagreed once
because of caching, and the agent blamed the wrong layer.

**Big files do not stream.** The pipeline encodes at ~40 Mbps, so 75 s is 363 MB.
`gallery.py` builds a proxy for anything over 25 MB. If a video will not play, check
the proxy exists before theorising.

**Never judge sharpness from a contact sheet.** A 3x downscaled montage retains ~34%
of the detail. Luca called a render blurry from one of these; the render was fine. Give
a 1:1 crop when sharpness is the question.

## Serving to a phone: the security-critical part

`tools/serve_gallery.py` serves ONLY `gallery.html` and `outputs/`. The repo also
contains `CLAUDE.local.md`, `models/` and `.git/`, so a naive
`python -m http.server` from the root is **not acceptable** behind a public tunnel.

Four things that were each wrong once and are now fixed in that tool. Re-verify them
rather than trusting they still hold:

- **Resolve paths before comparing.** A string prefix check let
  `outputs/../CLAUDE.local.md` return **200**. Only a resolved-target-inside-allowed-root
  test is safe.
- **Refuse an occupied port.** `allow_reuse_address` on Windows let the server bind a
  port another app held; the entire security test suite then passed against that app
  and proved nothing.
- **Implement real `206` ranges.** `SimpleHTTPRequestHandler` ignores `Range` and
  returns 200 with the full body. Advertising `Accept-Ranges` while doing that is worse
  than not advertising it: mobile browsers refuse to play.
- **Send `no-store` on the HTML.** Without it a phone serves a cached page through
  pull-to-refresh, and new renders look missing when they are being served correctly.

**Run the leak test against the public URL every time**, not just locally:

```
for p in CLAUDE.local.md .git/config gallery-feedback.json "outputs/../CLAUDE.local.md"; do
  curl -s -o /dev/null -w "$p %{http_code}\n" --path-as-is "$URL/$p"   # all must be 403
done
```

Tell Luca plainly that a quick tunnel is **public and unauthenticated**, and that it
carries unreleased work.

## If you change the gallery's JavaScript, open it in a browser

A literal newline inside a JS string killed the entire script block once, and the HTML
still contained every element, so grepping the file said "fine" while nothing on the
page worked. Playwright against `http://127.0.0.1:<port>` catches it; `file:` is blocked.
Check the console for errors, then click the thing you changed.

Related: when patching a file via a script, avoid escape sequences entirely rather than
trying to escape them correctly. That specific mistake happened twice in one day.
