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

import { enableSelect, enterSelectMode, exitSelectMode, isSelectMode,
         onSelectionChange, getSelection } from "./glance.js";

enableSelect();

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
  .cur8-bar .n{color:#8fdc9a}
`;
document.head.appendChild(S);

const chip = document.createElement("button");
chip.className = "cur8-chip";
chip.textContent = "curate";
chip.title = "Select tiles to REMOVE from this curated field (long-press also works)";
chip.onclick = () => (isSelectMode() ? exitSelectMode() : enterSelectMode());
document.body.appendChild(chip);

const bar = document.createElement("div");
bar.className = "cur8-bar";
bar.innerHTML = `<span><span class="n">0</span> to remove</span>
  <button data-a="export">export removals</button>
  <button data-a="done">done</button>`;
document.body.appendChild(bar);

function exportRemovals() {
  const info = getSelection();
  if (!info.count) return;
  const payload = {
    action: "exclude-from-curated-field",
    exported: new Date().toISOString(),
    collection: (window.GLANCE_CONFIG || {}).collection || "",
    exclude: info.items.map((it) => ({ sha16: it.sha, key: it.key || null })),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)],
                        { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "glance-removals.json";
  a.click();
  URL.revokeObjectURL(a.href);
}

bar.onclick = (e) => {
  const act = e.target && e.target.dataset && e.target.dataset.a;
  if (act === "export") exportRemovals();
  if (act === "done") exitSelectMode();
};

onSelectionChange((info) => {
  bar.classList.toggle("on", info.mode);
  chip.textContent = info.mode ? "browsing off" : "curate";
  bar.querySelector(".n").textContent = String(info.count);
});

// Verification hook for automated checks; harmless to humans.
window.__curate = { enterSelectMode, exitSelectMode, isSelectMode, getSelection };
