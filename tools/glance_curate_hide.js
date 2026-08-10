// glance_curate_hide.js -- PRE-BOOT hide shim for the tier-0 curated field.
//
// Why this file is classic (not a module) and injected BEFORE glance.js:
// `glance.js` calls boot() at module evaluation, so it starts fetching the
// catalogue the moment it runs. Modules are deferred; classic scripts execute
// during parsing. So a fetch patch installed from a module (curate-static.js)
// is always too late, while this one is always in time. index.html's own
// comment makes the same point about glance.config.js.
//
// What it does, and why this is a supported contract rather than a hack:
// `glance.js` drops any catalogue asset tagged `archived` before it reaches the
// field (`if (tg.asset_class === "press-kit" || tg.archived) continue;`), and
// its own comment calls that a view filter over an untouched original. The
// data-contract documents the field as `"archived": false  // true = hidden
// from the field entirely`. Setting that flag is a tier-2 (server) capability
// this static deploy does not have, so we set it on the response instead. The
// deployed JSON on the CDN is never modified.
//
// Consequence worth stating plainly: this is a per-DEVICE view. It is invisible
// to the agent and to anyone else opening the link. Making a removal real for
// every viewer still means exporting the list and rebuilding with
// `glance_export.py --exclude-file`.
//
// Deployed by glance_deploy.py --curate as glance/curate-hide.js.

(function () {
  "use strict";

  var cfg = window.GLANCE_CONFIG || {};
  var KEY = "glance-curate-hidden:" + (cfg.collection || "");

  var hidden = [];
  try {
    hidden = JSON.parse(localStorage.getItem(KEY) || "[]") || [];
  } catch (e) {
    // A corrupt or blocked store must never take the field down with it.
    console.warn("curate-hide: could not read hidden list", e);
    return;
  }
  if (!hidden.length) return;   // nothing hidden -> leave window.fetch untouched

  var drop = new Set();
  for (var i = 0; i < hidden.length; i++) {
    if (hidden[i] && hidden[i].sha16) drop.add(hidden[i].sha16);
  }
  if (!drop.size) return;

  var origFetch = window.fetch.bind(window);

  window.fetch = function (input, init) {
    var url = typeof input === "string" ? input : (input && input.url) || "";
    var p = origFetch(input, init);
    // Only the catalogue is rewritten. The atlas, the field file, thumbnails and
    // media all pass through the original fetch untouched.
    if (!/catalogue\.json(\?|$)/.test(url)) return p;

    return p.then(function (res) {
      if (!res.ok) return res;
      return res.clone().json().then(function (doc) {
        var assets = doc.assets || [];
        var present = new Set();
        var marked = 0;
        for (var j = 0; j < assets.length; j++) {
          var a = assets[j];
          var s16 = (a.sha256 || "").slice(0, 16);
          present.add(s16);
          if (drop.has(s16)) {
            a.tags = a.tags || {};
            a.tags.archived = true;
            marked++;
          }
        }
        // SELF-PRUNE. A hidden entry whose asset is no longer in the catalogue
        // has already been removed for real by a rebuild, so the local override
        // has done its job and should stop being carried. Without this the
        // hidden count only ever grows and eventually lies.
        var kept = hidden.filter(function (h) { return present.has(h.sha16); });
        if (kept.length !== hidden.length) {
          try { localStorage.setItem(KEY, JSON.stringify(kept)); } catch (e) {}
        }
        window.__curateHidden = kept;
        window.dispatchEvent(new CustomEvent("curate-hidden-ready", {
          detail: { hidden: kept, appliedToField: marked },
        }));
        return new Response(JSON.stringify(doc), {
          status: res.status,
          statusText: res.statusText,
          headers: { "Content-Type": "application/json" },
        });
      }).catch(function (e) {
        // Never let a rewrite failure cost the user the whole field.
        console.warn("curate-hide: passing the catalogue through unmodified", e);
        return res;
      });
    });
  };
})();
