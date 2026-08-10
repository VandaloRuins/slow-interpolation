// glance_curate.js -- TIER 0 curation face for a static Glance deployment.
//
// The white-label field ships full selection machinery (long-press to enter
// bulk-select, tap to toggle, cluster select, green rings) but it is DORMANT
// unless some module calls enableSelect(), and the only stock caller is the
// download layer, which index.html loads at tier >= 1. On a static tier-0
// archive nothing enables it, which reads as "there is no select function".
//
// This module is that missing tier-0 face. It cannot write anywhere (there is
// no backend), so curation is a round trip: select what should GO, export a
// removal list, hand the file to the agent, who rebuilds the field with
// `glance_export.py --exclude-file` and redeploys. The list carries keys, not
// numbers, so it stays valid across rebuilds.
//
// Deployed by glance_deploy.py --curate as glance/curate-static.js; it is not
// part of the white-label payload and never touches that repo.
//
// -- 2026-08-10: marks now PERSIST, and the buttons stopped lying ------------
//
// Reported from the field: "I select and click done but the gallery does not
// update to remove them." Two faults, one of them destructive.
//
//  1. `done` was the only button that looked like a commit, and it is the one
//     that throws the work away: glance.js's exitSelectMode() runs
//     `selection.clear()` (verified in the payload source), so every mark is
//     discarded on the way out. It is now labelled `exit`, and export is
//     visibly the only commit.
//  2. Marks lived in the field's in-memory selection only, so a reload or a
//     stray exit lost a whole curation pass. They are now mirrored to
//     localStorage per collection and restored via selectShas(), which
//     re-enters select mode and re-applies the rings itself.
//
// Removal is still a round trip and this module still cannot delete anything.
// What it can do is stop losing your decisions between marking and export.
// Note that the viewer ALREADY honours a persistent removal: glance.js drops
// any asset tagged `archived` before it reaches the field. Setting that flag is
// a tier-2 (server) capability, which is why the static path rebuilds instead.

import { enableSelect, enterSelectMode, exitSelectMode, isSelectMode,
         onSelectionChange, getSelection, selectShas } from "./glance.js";

enableSelect();

const COLLECTION = (window.GLANCE_CONFIG || {}).collection || "";
const STORE_KEY = `glance-curate-marks:${COLLECTION}`;

// sha16 -> key. The durable record of this curation pass, independent of the
// field's own selection, which is cleared on every exit.
let marks = new Map();
// While restoring we must ignore the field's selection events: entering select
// mode emits count 0 BEFORE the rings go back on, and mirroring that would wipe
// the very marks we are restoring.
let suppressMirror = false;

function loadMarks() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (!raw) return;
    for (const m of JSON.parse(raw)) if (m && m.sha16) marks.set(m.sha16, m.key || null);
  } catch (e) {
    // A corrupt or blocked store must never take the field down with it.
    console.warn("curate: could not read saved marks", e);
  }
}

function saveMarks() {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(
      [...marks].map(([sha16, key]) => ({ sha16, key }))));
  } catch (e) {
    console.warn("curate: could not save marks", e);
  }
}

loadMarks();

const S = document.createElement("style");
S.textContent = `
  .cur8-chip{position:fixed;right:14px;bottom:14px;z-index:60;font:12px/1 monospace;
    letter-spacing:.08em;background:#1c1b1a;color:#f4f1ee;border:1px solid #1c1b1a;
    border-radius:999px;padding:10px 16px;cursor:pointer;opacity:.85}
  .cur8-chip:hover{opacity:1}
  .cur8-bar{position:fixed;left:50%;bottom:14px;transform:translateX(-50%);z-index:60;
    display:none;gap:10px;align-items:center;font:12px/1 monospace;letter-spacing:.06em;
    background:#1c1b1a;color:#f4f1ee;border-radius:999px;padding:10px 16px}
  .cur8-bar.on{display:flex}
  .cur8-bar button{font:inherit;background:none;border:1px solid #6b6862;color:#f4f1ee;
    border-radius:999px;padding:6px 12px;cursor:pointer}
  .cur8-bar button:hover{border-color:#f4f1ee}
  .cur8-bar button[data-a="export"]{border-color:#8fdc9a;color:#8fdc9a}
  .cur8-bar button[data-a="export"]:hover{background:#8fdc9a;color:#1c1b1a}
  .cur8-bar .n{color:#8fdc9a}
  .cur8-note{position:fixed;left:50%;bottom:56px;transform:translateX(-50%);z-index:60;
    display:none;font:11px/1.4 monospace;letter-spacing:.04em;text-align:center;
    background:#1c1b1a;color:#c9c4bd;border-radius:10px;padding:8px 14px;max-width:min(92vw,520px)}
  .cur8-note.on{display:block}
`;
document.head.appendChild(S);

const chip = document.createElement("button");
chip.className = "cur8-chip";
chip.title = "Mark tiles to REMOVE from this curated field (long-press also works)";
chip.onclick = () => {
  if (isSelectMode()) { exitSelectMode(); return; }
  suppressMirror = true;
  selectShas([...marks.keys()]);   // enters select mode itself, restores the rings
  suppressMirror = false;
  // Marks whose asset is no longer on the field (already removed by a rebuild)
  // never come back as rings; drop them so the count cannot drift upward
  // forever. This is the mark's natural end of life.
  const live = new Set((getSelection().items || []).map((it) => it.sha));
  if (marks.size && live.size < marks.size) {
    for (const sha of [...marks.keys()]) if (!live.has(sha)) marks.delete(sha);
    saveMarks();
  }
  if (!isSelectMode()) enterSelectMode();   // no marks yet: still open the bar
  render();
};
document.body.appendChild(chip);

const bar = document.createElement("div");
bar.className = "cur8-bar";
bar.innerHTML = `<span><span class="n">0</span> marked to remove</span>
  <button data-a="export">export removals</button>
  <button data-a="clear">clear marks</button>
  <button data-a="exit">exit</button>`;
document.body.appendChild(bar);

const note = document.createElement("div");
note.className = "cur8-note";
document.body.appendChild(note);

function showNote(text) {
  note.textContent = text;
  note.classList.add("on");
  clearTimeout(showNote.t);
  showNote.t = setTimeout(() => note.classList.remove("on"), 9000);
}

function render() {
  const mode = isSelectMode();
  bar.classList.toggle("on", mode);
  chip.textContent = mode ? "exit curate" : (marks.size ? `curate (${marks.size})` : "curate");
  bar.querySelector(".n").textContent = String(marks.size);
  const ex = bar.querySelector('button[data-a="export"]');
  ex.disabled = marks.size === 0;
  ex.style.opacity = marks.size === 0 ? 0.4 : 1;
}

function exportRemovals() {
  if (!marks.size) return;
  const payload = {
    action: "exclude-from-curated-field",
    exported: new Date().toISOString(),
    collection: COLLECTION,
    exclude: [...marks].map(([sha16, key]) => ({ sha16, key })),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)],
                        { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "glance-removals.json";
  a.click();
  URL.revokeObjectURL(a.href);
  // Say exactly what did and did not just happen. The old face said nothing,
  // which is why exiting felt like it should have applied something.
  showNote(`${marks.size} exported to glance-removals.json. They are STILL on `
         + `this field: hand the file to the agent, who rebuilds with `
         + `--exclude-file and redeploys. Your marks are saved until then.`);
}

bar.onclick = (e) => {
  const act = e.target && e.target.dataset && e.target.dataset.a;
  if (act === "export") exportRemovals();
  if (act === "clear") {
    marks.clear();
    saveMarks();
    exitSelectMode();
    showNote("marks cleared. Nothing was removed from the field.");
    render();
  }
  if (act === "exit") exitSelectMode();
};

onSelectionChange((info) => {
  // The field's selection is the truth only while select mode is ON. Its exit
  // path clears the selection, and mirroring that would delete the pass.
  if (info.mode && !suppressMirror) {
    marks = new Map((info.items || []).map((it) => [it.sha, it.key || null]));
    saveMarks();
  }
  render();
});

render();

// Verification hook for automated checks; harmless to humans.
window.__curate = { enterSelectMode, exitSelectMode, isSelectMode, getSelection,
                    marks: () => [...marks].map(([sha16, key]) => ({ sha16, key })) };
