// glance_curate.js -- TIER 0 curation face for a static Glance deployment.
//
// The white-label field ships full selection machinery (long-press to enter
// bulk-select, tap to toggle, cluster select, green rings) but it is DORMANT
// unless some module calls enableSelect(), and the only stock caller is the
// download layer, which index.html loads at tier >= 1. On a static tier-0
// archive nothing enables it, which reads as "there is no select function".
//
// This module is that missing tier-0 face.
//
// -- 2026-08-10, pass 2: marks persist, and `done` stopped destroying them ----
//
//  1. `done` was the only button that looked like a commit, and it was the one
//     that threw the work away: glance.js's exitSelectMode() runs
//     `selection.clear()`. It is now `exit`, and only `remove` and `export` act.
//  2. Marks lived in the field's in-memory selection alone, so a reload or a
//     stray exit lost a whole curation pass. They now mirror to localStorage and
//     restore through selectShas(), which re-enters select mode and re-applies
//     the rings itself.
//
// -- 2026-08-10, pass 3: REMOVAL IS NOW REAL, locally -------------------------
//
// Luca: "when I select one card to remove I would love to actually be able to
// live remove it, not just flag it to you." Flagging and waiting is not
// curation. So `remove` now takes the cards off the field and keeps them off.
//
// Two stores, and the distinction is the whole design:
//
//   marks   transient. What is ringed right now, pending a decision. Survives a
//           stray exit and a reload so a pass is never lost, nothing more.
//   hidden  the accumulated REMOVAL LIST. Drives `curate-hide.js`, which tags
//           these assets `archived` in the catalogue response before glance.js
//           builds the field, using the viewer's own documented view filter.
//           This is also exactly what gets exported.
//
// `remove` moves marks into hidden and reloads, which is how the field is
// rebuilt without the removed cards. A reload is the cost of doing this without
// touching the Tier 1 viewer: splicing a live tile out needs `base`,
// `tileBySha` and the renderer feed, none of which are exported. The instant
// version is a ~15 line `removeShas()` export upstream, sibling to the
// `selectShas` / `deselectShas` that already exist, and is queued separately.
//
// TWO THINGS THIS DELIBERATELY DOES NOT PRETEND:
//   - Hiding is per-DEVICE. It is invisible to the agent and to anyone else
//     opening the link. `restore all` brings everything back.
//   - Only a rebuild makes a removal true for every viewer. So once anything is
//     hidden and unexported, the face says so until you export it.
//
// Deployed by glance_deploy.py --curate as glance/curate-static.js.

import { enableSelect, enterSelectMode, exitSelectMode, isSelectMode,
         onSelectionChange, getSelection, selectShas } from "./glance.js";

enableSelect();

const COLLECTION = (window.GLANCE_CONFIG || {}).collection || "";
const MARKS_KEY = `glance-curate-marks:${COLLECTION}`;
const HIDDEN_KEY = `glance-curate-hidden:${COLLECTION}`;
const EXPORTED_KEY = `glance-curate-exported:${COLLECTION}`;

// A SINK is a same-origin endpoint that accepts the removal list, so a removal
// reaches the agent with no download and no file handling. `tools/serve_glance.py`
// provides one; the Vercel deploy does not, and 404s the probe. So the same build
// works in both places and configures itself: with a sink, removals are sent
// automatically; without one, the export banner is the fallback it always was.
const SINK = "curate/removals";
let sinkReady = false;

let marks = new Map();    // sha16 -> key, transient selection
let hidden = new Map();    // sha16 -> key, the accumulated removal list
let exportedCount = 0;     // how many hidden entries were in the last export
// Entering select mode emits count 0 BEFORE the rings go back on; mirroring that
// would wipe the very marks we are restoring.
let suppressMirror = false;

function readStore(key) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return new Map();
    return new Map((JSON.parse(raw) || []).filter(m => m && m.sha16)
                                          .map(m => [m.sha16, m.key || null]));
  } catch (e) {
    console.warn("curate: could not read", key, e);
    return new Map();
  }
}

function writeStore(key, map) {
  try {
    localStorage.setItem(key, JSON.stringify(
      [...map].map(([sha16, k]) => ({ sha16, key: k }))));
  } catch (e) {
    console.warn("curate: could not save", key, e);
  }
}

marks = readStore(MARKS_KEY);
hidden = readStore(HIDDEN_KEY);
try { exportedCount = Number(localStorage.getItem(EXPORTED_KEY) || 0); } catch (e) {}

// The shim prunes hidden entries whose asset a rebuild has already removed for
// real, then announces the pruned list. Pick it up so the counts cannot drift.
window.addEventListener("curate-hidden-ready", (e) => {
  const kept = (e.detail && e.detail.hidden) || [];
  hidden = new Map(kept.filter(h => h && h.sha16).map(h => [h.sha16, h.key || null]));
  if (exportedCount > hidden.size) {
    exportedCount = hidden.size;
    try { localStorage.setItem(EXPORTED_KEY, String(exportedCount)); } catch (err) {}
  }
  render();
});

const S = document.createElement("style");
S.textContent = `
  .cur8-chip{position:fixed;right:14px;bottom:14px;z-index:60;font:12px/1 monospace;
    letter-spacing:.08em;background:#1c1b1a;color:#f4f1ee;border:1px solid #1c1b1a;
    border-radius:999px;padding:10px 16px;cursor:pointer;opacity:.85}
  .cur8-chip:hover{opacity:1}
  .cur8-bar{position:fixed;left:50%;bottom:14px;transform:translateX(-50%);z-index:60;
    display:none;gap:8px;align-items:center;font:12px/1 monospace;letter-spacing:.06em;
    background:#1c1b1a;color:#f4f1ee;border-radius:999px;padding:10px 14px;
    max-width:calc(100vw - 28px);flex-wrap:wrap;justify-content:center}
  .cur8-bar.on{display:flex}
  .cur8-bar button{font:inherit;background:none;border:1px solid #6b6862;color:#f4f1ee;
    border-radius:999px;padding:6px 12px;cursor:pointer}
  .cur8-bar button:hover{border-color:#f4f1ee}
  .cur8-bar button[data-a="remove"]{border-color:#e0857a;color:#e0857a}
  .cur8-bar button[data-a="remove"]:hover{background:#e0857a;color:#1c1b1a}
  .cur8-bar button[data-a="export"]{border-color:#8fdc9a;color:#8fdc9a}
  .cur8-bar button[data-a="export"]:hover{background:#8fdc9a;color:#1c1b1a}
  .cur8-bar button:disabled{opacity:.35;cursor:default}
  .cur8-bar .n{color:#8fdc9a}
  .cur8-note,.cur8-banner{position:fixed;left:50%;transform:translateX(-50%);z-index:60;
    font:11px/1.45 monospace;letter-spacing:.04em;text-align:center;background:#1c1b1a;
    color:#c9c4bd;border-radius:10px;padding:8px 14px;max-width:min(92vw,540px)}
  .cur8-note{bottom:60px;display:none}
  .cur8-note.on{display:block}
  .cur8-banner{top:56px;display:none;cursor:pointer;color:#e8c98a;border:1px solid #4a4540}
  .cur8-banner.on{display:block}
`;
document.head.appendChild(S);

const chip = document.createElement("button");
chip.className = "cur8-chip";
chip.title = "Select cards to remove from this field (long-press also works)";
chip.onclick = () => {
  if (isSelectMode()) { exitSelectMode(); render(); return; }
  suppressMirror = true;
  selectShas([...marks.keys()]);   // enters select mode itself, restores rings
  suppressMirror = false;
  // A mark whose asset is no longer on the field never comes back as a ring.
  const live = new Set((getSelection().items || []).map(it => it.sha));
  if (marks.size && live.size < marks.size) {
    for (const sha of [...marks.keys()]) if (!live.has(sha)) marks.delete(sha);
    writeStore(MARKS_KEY, marks);
  }
  if (!isSelectMode()) enterSelectMode();   // no marks yet: still open the bar
  render();
};
document.body.appendChild(chip);

const bar = document.createElement("div");
bar.className = "cur8-bar";
bar.innerHTML = `<span><span class="n">0</span> selected</span>
  <button data-a="remove">remove</button>
  <button data-a="export">export removals</button>
  <button data-a="restore">restore all</button>
  <button data-a="exit">exit</button>`;
document.body.appendChild(bar);

const note = document.createElement("div");
note.className = "cur8-note";
document.body.appendChild(note);

// The export nudge. Hiding is local and invisible to everyone else, so an
// unexported removal list is a silent divergence between what Luca sees and
// what the shared link shows. This says so until it is exported.
const banner = document.createElement("div");
banner.className = "cur8-banner";
banner.onclick = () => exportRemovals();
document.body.appendChild(banner);

function showNote(text) {
  note.textContent = text;
  note.classList.add("on");
  clearTimeout(showNote.t);
  showNote.t = setTimeout(() => note.classList.remove("on"), 10000);
}

function render() {
  const mode = isSelectMode();
  bar.classList.toggle("on", mode);
  chip.textContent = mode ? "exit curate"
    : (hidden.size ? `curate (${hidden.size} hidden)` : "curate");
  bar.querySelector(".n").textContent = String(marks.size);
  const set = (a, on, label) => {
    const b = bar.querySelector(`button[data-a="${a}"]`);
    b.disabled = !on;
    if (label) b.textContent = label;
  };
  set("remove", marks.size > 0, marks.size ? `remove ${marks.size}` : "remove");
  set("export", hidden.size + marks.size > 0, "export removals");
  set("restore", hidden.size > 0, hidden.size ? `restore all (${hidden.size})` : "restore all");

  const unexported = hidden.size - exportedCount;
  banner.classList.toggle("on", unexported > 0);
  if (unexported > 0) {
    banner.textContent = `${hidden.size} hidden on this device`
      + `${exportedCount ? `, ${unexported} of them not exported yet` : ", not exported yet"}`
      + `. They are still on the shared link until the agent rebuilds. Tap to export.`;
  }
}

// Probe for the sink once. A 404 (Vercel) simply means manual export stays the
// route; nothing is logged as an error because that is a supported deployment.
fetch(SINK, { method: "GET", cache: "no-store" })
  .then((r) => r.ok ? r.json() : null)
  .then((info) => {
    if (!info || info.sink !== "ok") return;
    sinkReady = true;
    const b = bar.querySelector('button[data-a="export"]');
    if (b) b.title = "Also saved automatically; this downloads a copy";
    showNote("connected to the agent: removals are sent automatically, "
           + "no file to hand over.");
    render();
  })
  .catch(() => {});

function payloadFor(map) {
  return {
    action: "exclude-from-curated-field",
    exported: new Date().toISOString(),
    collection: COLLECTION,
    exclude: [...map].map(([sha16, key]) => ({ sha16, key })),
  };
}

/** Send the removal list to the same-origin sink. Returns true if it landed. */
async function sendToSink(map) {
  if (!sinkReady || !map.size) return false;
  try {
    const r = await fetch(SINK, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payloadFor(map)),
    });
    return r.ok;
  } catch (e) {
    console.warn("curate: sink POST failed", e);
    return false;
  }
}

async function removeSelected() {
  if (!marks.size) return;
  for (const [sha, key] of marks) hidden.set(sha, key);
  marks.clear();
  writeStore(HIDDEN_KEY, hidden);
  writeStore(MARKS_KEY, marks);
  // Send BEFORE reloading, and await it: a reload cancels in-flight requests.
  // The whole list goes each time rather than a delta, so one lost POST cannot
  // desync the agent's view from this device's.
  if (sinkReady) {
    const sent = await sendToSink(hidden);
    if (sent) {
      exportedCount = hidden.size;   // delivered, so the nudge is not owed
      try { localStorage.setItem(EXPORTED_KEY, String(exportedCount)); } catch (e) {}
    }
  }
  // The shim tags these `archived` before glance.js builds the field, so the
  // reload IS the removal. Nothing else takes them off a live canvas.
  location.reload();
}

function exportRemovals() {
  // Export the accumulated removal list plus anything currently ringed, so a
  // selection in progress is never silently left out of the file.
  const all = new Map([...hidden, ...marks]);
  if (!all.size) return;
  const payload = {
    action: "exclude-from-curated-field",
    exported: new Date().toISOString(),
    collection: COLLECTION,
    exclude: [...all].map(([sha16, key]) => ({ sha16, key })),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "glance-removals.json";
  a.click();
  URL.revokeObjectURL(a.href);
  exportedCount = all.size;
  try { localStorage.setItem(EXPORTED_KEY, String(exportedCount)); } catch (e) {}
  showNote(`${all.size} exported to glance-removals.json. Hand the file to the `
         + `agent, who rebuilds with --exclude-file and redeploys. Until then `
         + `they are hidden on THIS device only.`);
  render();
}

bar.onclick = (e) => {
  const act = e.target && e.target.dataset && e.target.dataset.a;
  if (!act || e.target.disabled) return;
  if (act === "remove") removeSelected();
  if (act === "export") exportRemovals();
  if (act === "restore") {
    hidden.clear();
    exportedCount = 0;
    writeStore(HIDDEN_KEY, hidden);
    try { localStorage.setItem(EXPORTED_KEY, "0"); } catch (err) {}
    location.reload();
  }
  if (act === "exit") { exitSelectMode(); render(); }
};

onSelectionChange((info) => {
  // The field's selection is the truth only while select mode is ON; its exit
  // path clears the selection, and mirroring that would delete the pass.
  if (info.mode && !suppressMirror) {
    marks = new Map((info.items || []).map(it => [it.sha, it.key || null]));
    writeStore(MARKS_KEY, marks);
  }
  render();
});

render();

// Verification hook for automated checks; harmless to humans.
window.__curate = {
  enterSelectMode, exitSelectMode, isSelectMode, getSelection,
  marks: () => [...marks].map(([sha16, key]) => ({ sha16, key })),
  hidden: () => [...hidden].map(([sha16, key]) => ({ sha16, key })),
  removeSelected, exportRemovals,
};
