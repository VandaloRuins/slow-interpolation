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
// -- pass 2: marks persist, and `done` stopped destroying them ----------------
//
//  1. `done` was the only button that looked like a commit, and it was the one
//     that threw the work away: glance.js's exitSelectMode() runs
//     `selection.clear()`. Only `remove` and `export` act now.
//  2. Marks lived in the field's in-memory selection alone, so a reload or a
//     stray exit lost a whole curation pass. They now mirror to localStorage and
//     restore through selectShas(), which re-enters select mode and re-applies
//     the rings itself.
//
// -- pass 3: removal became real, locally ------------------------------------
//
// Two stores, and the distinction is the whole design:
//   marks   transient. What is ringed right now, pending a decision.
//   hidden  the accumulated REMOVAL LIST. Drives `curate-hide.js`, which tags
//           these assets `archived` in the catalogue response before glance.js
//           builds the field, using the viewer's own documented view filter.
//           This is also exactly what gets sent or exported.
// `remove` moves marks into hidden and reloads; the reload IS the removal.
// Instant vanish needs a ~15 line removeShas() upstream in the Tier 1 viewer.
//
// -- pass 4: MOBILE FIRST ----------------------------------------------------
//
// Luca, from a phone: "the ui you built is not mobile friendly." Correct. The
// first version was a desktop pill: five controls in one centred row, 12px
// monospace, ~28px tap targets, `bottom: 14px` sitting in the iPhone home
// indicator, and a separate floating banner and note that collided with each
// other. On a 390px screen it wrapped into a blob over the browser chrome.
//
// What changed, and the reasoning:
//   - FULL-WIDTH bottom bar under 641px, centred pill above it. The host CSS
//     already uses that breakpoint and env(safe-area-inset-*); the overlay was
//     the only thing in the page ignoring both.
//   - Every tap target is >= 44px, and the bar pads itself out of the home
//     indicator with env(safe-area-inset-bottom).
//   - AT MOST THREE TARGETS, and they are contextual rather than all present at
//     once: exit, one primary action, and one optional secondary row. `remove`,
//     `export` and `restore` are never all on screen together, because only one
//     of them is ever the sensible next move.
//   - The floating note and banner are GONE. Their job moved into the status
//     line, which is one element that always says what state you are in. Fewer
//     floating things beats more information.
//   - Styled from the host's tokens (--glass-strong, --hairline, --ink,
//     --font-ui, --shadow-panel) instead of hardcoded hexes, so it reads as part
//     of the viewer rather than bolted on.
//
// Deployed by glance_deploy.py --curate as glance/curate-static.js.

import { enableSelect, enterSelectMode, exitSelectMode, isSelectMode,
         onSelectionChange, getSelection, selectShas } from "./glance.js";

enableSelect();

const COLLECTION = (window.GLANCE_CONFIG || {}).collection || "";
const MARKS_KEY = `glance-curate-marks:${COLLECTION}`;
const HIDDEN_KEY = `glance-curate-hidden:${COLLECTION}`;
const EXPORTED_KEY = `glance-curate-exported:${COLLECTION}`;
const UNDO_KEY = `glance-curate-undo:${COLLECTION}`;

// A long-press selects the WHOLE CLUSTER the pressed tile belongs to, which on a
// phone is one slightly-too-long tap away from selecting sixty cards. That
// happened, and `remove` was then a single tap. So two guards:
//   CONFIRM   a removal of BULK_CONFIRM_AT or more needs a second tap
//   UNDO      any removal can be reversed for UNDO_WINDOW_MS, and the record
//             survives the reload that performs the removal
const BULK_CONFIRM_AT = 10;
const UNDO_WINDOW_MS = 10 * 60 * 1000;
let armed = false;   // primary is waiting for its confirming second tap

// A SINK is a same-origin endpoint that accepts the removal list, so a removal
// reaches the agent with no download and no file handling. `serve_glance.py`
// provides one; the Vercel deploy 404s the probe. Same build, both places.
const SINK = "curate/removals";
let sinkReady = false;

let marks = new Map();     // sha16 -> key, transient selection
let hidden = new Map();    // sha16 -> key, the accumulated removal list
let exportedCount = 0;     // how many hidden entries were last delivered
let suppressMirror = false;
let statusOverride = null;  // transient confirmation, replaces the status line

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

// The shim prunes hidden entries whose asset a rebuild already removed for real,
// then announces the pruned list. Pick it up so the counts cannot drift.
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
  .cur8-chip, .cur8-bar { font-family: var(--font-ui); color: var(--ink); }

  .cur8-chip{position:fixed;z-index:60;
    right:max(12px, env(safe-area-inset-right));
    bottom:calc(12px + env(safe-area-inset-bottom));
    display:flex;align-items:center;min-height:44px;padding:0 18px;
    font-size:13px;letter-spacing:.04em;
    background:var(--glass-strong);-webkit-backdrop-filter:blur(8px);
    backdrop-filter:blur(8px);border:1px solid var(--hairline);
    border-radius:999px;box-shadow:var(--shadow-panel);cursor:pointer}
  .cur8-chip:active{background:var(--bg-recede)}
  /* An author display rule beats the hidden attribute's UA style, so
     chip.hidden = true does nothing without this. */
  .cur8-chip[hidden]{display:none}

  .cur8-bar{position:fixed;z-index:60;left:0;right:0;bottom:0;display:none;
    flex-direction:column;gap:8px;
    padding:10px max(12px, env(safe-area-inset-right))
            calc(10px + env(safe-area-inset-bottom))
            max(12px, env(safe-area-inset-left));
    background:var(--glass-strong);-webkit-backdrop-filter:blur(12px);
    backdrop-filter:blur(12px);border-top:1px solid var(--hairline);
    box-shadow:var(--shadow-panel);font-size:13px;line-height:1.25}
  .cur8-bar.on{display:flex}
  .cur8-row{display:flex;gap:8px;align-items:center}
  .cur8-status{flex:1;min-width:0;opacity:.72;letter-spacing:.03em;
    overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .cur8-btn{display:flex;align-items:center;justify-content:center;
    min-height:44px;padding:0 16px;font:inherit;letter-spacing:.04em;
    color:var(--ink);background:var(--bg-lift);border:1px solid var(--hairline);
    border-radius:12px;cursor:pointer;white-space:nowrap}
  .cur8-btn:active{background:var(--bg-recede)}
  .cur8-btn[hidden]{display:none}
  .cur8-icon{width:44px;padding:0;font-size:17px;line-height:1}
  .cur8-danger{background:#8C3A26;border-color:#8C3A26;color:var(--bg);font-weight:700}
  .cur8-danger:active{background:#722F1E}
  .cur8-go{background:var(--ink);border-color:var(--ink);color:var(--bg);font-weight:700}
  .cur8-wide{width:100%}

  @media (min-width:641px){
    .cur8-bar{left:50%;right:auto;bottom:14px;transform:translateX(-50%);
      min-width:min(460px, calc(100vw - 28px));border:1px solid var(--hairline);
      border-radius:16px;padding:10px 12px}
  }
`;
document.head.appendChild(S);

const chip = document.createElement("button");
chip.className = "cur8-chip";
chip.type = "button";
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
  if (!isSelectMode()) enterSelectMode();
  render();
};
document.body.appendChild(chip);

const bar = document.createElement("div");
bar.className = "cur8-bar";
bar.innerHTML = `
  <div class="cur8-row">
    <button class="cur8-btn cur8-icon" data-a="exit" type="button" aria-label="Leave curate mode">&#215;</button>
    <span class="cur8-status"></span>
    <button class="cur8-btn" data-a="primary" type="button" hidden></button>
  </div>
  <button class="cur8-btn cur8-wide" data-a="second" type="button" hidden></button>`;
document.body.appendChild(bar);

const els = {
  status: bar.querySelector(".cur8-status"),
  primary: bar.querySelector('[data-a="primary"]'),
  second: bar.querySelector('[data-a="second"]'),
};

function flash(text) {
  statusOverride = text;
  render();
  clearTimeout(flash.t);
  flash.t = setTimeout(() => { statusOverride = null; render(); }, 6000);
}

function render() {
  const mode = isSelectMode();
  bar.classList.toggle("on", mode);
  // The chip is the way IN; the bar carries its own way out. Leaving both on
  // screen put a redundant control underneath the full-width bar, where it bled
  // through at the right edge on a phone. One control per job.
  chip.hidden = mode;
  chip.textContent = hidden.size ? `curate · ${hidden.size}` : "curate";

  const owed = hidden.size - exportedCount;

  // The status line is the only place state is reported. It replaced a floating
  // note and a floating banner, which used to overlap each other on a phone.
  if (statusOverride) {
    els.status.textContent = statusOverride;
  } else if (marks.size) {
    els.status.textContent = `${marks.size} selected`;
  } else if (hidden.size) {
    els.status.textContent = `${hidden.size} hidden`
      + (owed > 0 ? " · not sent yet" : sinkReady ? " · sent" : " · exported");
  } else {
    els.status.textContent = "tap cards to remove";
  }

  // ONE primary action, chosen by context: undo / remove / export / nothing.
  // Undo outranks everything, because if a removal was a mistake that is the
  // only thing you want the moment the page comes back.
  const undo = readUndo();
  let p = null;
  if (marks.size) {
    p = armed
      ? { label: `tap again to remove ${marks.size}`, act: "remove", cls: "cur8-danger" }
      : { label: `remove ${marks.size}`, act: "remove", cls: "cur8-danger" };
  } else if (undo) {
    p = { label: `undo · bring back ${undo.restores}`, act: "undo", cls: "cur8-go" };
  } else if (owed > 0) {
    p = { label: "export list", act: "export", cls: "cur8-go" };
  }
  els.primary.hidden = !p;
  if (p) {
    els.primary.textContent = p.label;
    els.primary.dataset.act = p.act;
    els.primary.className = `cur8-btn ${p.cls}`;
  }

  // ONE optional secondary, full width so it is never cramped beside the primary.
  let s = null;
  if (hidden.size) s = { label: `restore ${hidden.size} hidden`, act: "restore" };
  els.second.hidden = !s;
  if (s) {
    els.second.textContent = s.label;
    els.second.dataset.act = s.act;
  }
}

function payloadFor(map) {
  return {
    action: "exclude-from-curated-field",
    exported: new Date().toISOString(),
    collection: COLLECTION,
    exclude: [...map].map(([sha16, key]) => ({ sha16, key })),
  };
}

/** Send the removal list to the same-origin sink. Returns true if it landed.
 *  An EMPTY list is deliberately sendable: after an undo or a restore it is the
 *  whole message, meaning nothing should be excluded any more. */
async function sendToSink(map) {
  if (!sinkReady) return false;
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

/** The pre-removal hidden list, if a removal is still inside its undo window. */
function readUndo() {
  try {
    const raw = localStorage.getItem(UNDO_KEY);
    if (!raw) return null;
    const rec = JSON.parse(raw);
    if (!rec || !Array.isArray(rec.prev) || !rec.at) return null;
    if (Date.now() - rec.at > UNDO_WINDOW_MS) {
      localStorage.removeItem(UNDO_KEY);
      return null;
    }
    // `restores` is what undoing would put back, which is the number worth
    // showing on the button rather than the size of the saved list.
    return { prev: rec.prev, restores: Math.max(0, hidden.size - rec.prev.length) };
  } catch (e) {
    return null;
  }
}

function undoLastRemoval() {
  const rec = readUndo();
  if (!rec) return;
  hidden = new Map(rec.prev.filter(h => h && h.sha16).map(h => [h.sha16, h.key || null]));
  writeStore(HIDDEN_KEY, hidden);
  exportedCount = 0;   // the list changed, so a previous send no longer describes it
  try {
    localStorage.setItem(EXPORTED_KEY, "0");
    localStorage.removeItem(UNDO_KEY);
  } catch (e) {}
  // Tell the agent too, so its copy matches the device again. An empty list is a
  // legitimate message: it means nothing should be excluded.
  if (sinkReady) sendToSink(hidden).finally(() => location.reload());
  else location.reload();
}

async function removeSelected() {
  if (!marks.size) return;
  // Bulk removals need a second tap. A whole cluster can be selected by accident
  // with one long press, and this is the only thing standing between that and
  // sixty cards leaving the field.
  if (marks.size >= BULK_CONFIRM_AT && !armed) {
    armed = true;
    render();
    clearTimeout(removeSelected.t);
    removeSelected.t = setTimeout(() => { armed = false; render(); }, 5000);
    return;
  }
  armed = false;
  // Snapshot BEFORE the merge, so undo has somewhere to go back to. Written to
  // localStorage because performing the removal reloads the page.
  try {
    localStorage.setItem(UNDO_KEY, JSON.stringify({
      at: Date.now(),
      prev: [...hidden].map(([sha16, key]) => ({ sha16, key })),
    }));
  } catch (e) {}
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
      exportedCount = hidden.size;
      try { localStorage.setItem(EXPORTED_KEY, String(exportedCount)); } catch (e) {}
    }
  }
  location.reload();   // the shim tags them `archived`, so the reload removes them
}

function exportRemovals() {
  const all = new Map([...hidden, ...marks]);
  if (!all.size) return;
  const blob = new Blob([JSON.stringify(payloadFor(all), null, 2)],
                        { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "glance-removals.json";
  a.click();
  URL.revokeObjectURL(a.href);
  exportedCount = all.size;
  try { localStorage.setItem(EXPORTED_KEY, String(exportedCount)); } catch (e) {}
  flash(`${all.size} exported · send the file to the agent`);
}

bar.onclick = (e) => {
  const btn = e.target && e.target.closest && e.target.closest(".cur8-btn");
  if (!btn || btn.hidden) return;
  const act = btn.dataset.act || btn.dataset.a;
  if (act === "remove") removeSelected();
  if (act === "undo") undoLastRemoval();
  if (act === "export") exportRemovals();
  if (act === "restore") {
    hidden.clear();
    exportedCount = 0;
    writeStore(HIDDEN_KEY, hidden);
    try {
      localStorage.setItem(EXPORTED_KEY, "0");
      localStorage.removeItem(UNDO_KEY);
    } catch (err) {}
    if (sinkReady) sendToSink(hidden).finally(() => location.reload());
    else location.reload();
  }
  if (act === "exit") { armed = false; exitSelectMode(); render(); }
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

// Probe for the sink once. A 404 (Vercel) simply means manual export stays the
// route, which is a supported deployment, so it is not logged as an error.
fetch(SINK, { method: "GET", cache: "no-store" })
  .then((r) => r.ok ? r.json() : null)
  .then((info) => {
    if (!info || info.sink !== "ok") return;
    sinkReady = true;
    render();
  })
  .catch(() => {});

// Verification hook for automated checks; harmless to humans.
window.__curate = {
  enterSelectMode, exitSelectMode, isSelectMode, getSelection,
  marks: () => [...marks].map(([sha16, key]) => ({ sha16, key })),
  hidden: () => [...hidden].map(([sha16, key]) => ({ sha16, key })),
  removeSelected, exportRemovals, sinkReady: () => sinkReady,
};
