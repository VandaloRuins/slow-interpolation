/* Media Engine -- front-end. Vanilla JS, 1s state polling (planner pattern). */

"use strict";

const RAIL_STATES = ["discovered", "checksum", "uploading", "verified",
                     "thumbnailed", "captioned", "embedded", "catalogued"];
const TERMINAL = ["duplicate", "quarantined", "excluded"];

let lastMtime = null;
let state = null;
let catalogue = null;
let facetFilters = {};        // {media_type, asset_class, artist, context, date}
let reviewMode = false;
let selectedKey = null;

const $ = (id) => document.getElementById(id);

/* ---------------- toast ---------------- */
let toastTimer = null;
function toast(msg, kind) {
  const el = $("toast");
  el.textContent = msg;
  el.className = "show" + (kind ? " " + kind : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.className = ""), 2600);
}

/* ---------------- api ---------------- */
async function post(path, body) {
  const resp = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok || data.ok === false) {
    throw new Error(data.error || data.message || `HTTP ${resp.status}`);
  }
  return data;
}

async function pollState() {
  try {
    const headers = {};
    if (lastMtime !== null) headers["If-Modified-Since"] = String(lastMtime);
    const resp = await fetch("/api/state", { headers });
    if (resp.status === 304) return;
    const mt = resp.headers.get("X-State-Mtime");
    if (mt) lastMtime = parseFloat(mt);
    state = await resp.json();
    renderEngine();
  } catch (e) {
    /* server briefly busy; next tick retries */
  }
}

/* ================================================================ ENGINE ROOM */

function renderEngine() {
  if (!state) return;
  const phase = state.phase || "idle";

  // phase badge
  const badge = $("phase-badge");
  badge.textContent = phase;
  badge.className = "phase-badge " + phase;

  // batch meta
  const b = state.batch || {};
  $("bm-source").textContent = b.source || "--";
  $("bm-prefix").textContent = b.prefix ? b.prefix + "/" : "--";
  $("bm-edition").textContent = b.edition || "--";
  $("bm-class").textContent = b.asset_class || "--";
  $("bm-artists").textContent = (b.artists || []).join(", ") || "--";
  const prov = state.providers || {};
  $("bm-providers").textContent =
    `caption=${prov.caption || "?"} | embed=${prov.embed || "?"} | face=${prov.face || "?"}`;

  // buttons by phase
  $("btn-scan").disabled = ["dry-run", "running", "finalizing"].includes(phase);
  $("btn-dryrun").disabled = phase !== "intake";
  $("btn-approve").disabled = phase !== "awaiting-approval";

  // ledger
  const c = state.counts || {};
  $("lg-discovered").textContent = c.discovered ?? 0;
  $("lg-catalogued").textContent = c.catalogued ?? 0;
  $("lg-duplicates").textContent = c.duplicates ?? 0;
  $("lg-quarantined").textContent = c.quarantined ?? 0;
  $("lg-excluded").textContent = c.excluded ?? 0;
  $("lg-inflight").textContent = c.in_pipeline ?? 0;
  const balanced = (c.in_pipeline ?? 0) === 0;
  const lb = $("lg-balance");
  lb.textContent = balanced ? "BALANCED" : "IN FLIGHT";
  lb.className = "ledger-balance" + (balanced ? "" : " off");

  // cost ticker
  const cost = state.cost || {};
  $("ct-calls").textContent =
    `${(cost.caption_calls || 0) + (cost.embed_calls || 0)} calls`;
  $("ct-cost").textContent = `EUR ${(cost.eur_actual || 0).toFixed(4)}`;
  $("ct-est").textContent = cost.eur_full_run_estimate != null
    ? `full run est. EUR ${cost.eur_full_run_estimate.toFixed(4)}` : "";

  renderGate(phase);
  renderRail(phase);
  renderLanes();
  renderConsole();
}

function renderGate(phase) {
  const gate = $("approval-gate");
  if (phase !== "awaiting-approval") { gate.classList.add("hidden"); return; }
  gate.classList.remove("hidden");
  const done = (state.files || []).filter((f) => f.state === "catalogued");
  $("gate-body").innerHTML = done.map((f) => {
    const scene = (f.scene || []).join(", ");
    return `<div class="g-sample"><span class="mono">${f.name}</span>` +
           ` &mdash; <i>${escapeHtml(f.caption || "no caption")}</i>` +
           (scene ? ` <span class="dim">[${scene}]</span>` : "") + `</div>`;
  }).join("") || "<div class='dim'>no samples catalogued</div>";
  const cost = state.cost || {};
  $("gate-estimate").textContent = cost.eur_full_run_estimate != null
    ? `estimated total for the full batch: EUR ${cost.eur_full_run_estimate.toFixed(4)}`
    : "";
}

function renderRail(phase) {
  const rail = $("rail");
  rail.innerHTML = "";
  const tpl = document.querySelector("#t-rail-col");
  const cardTpl = document.querySelector("#t-file-card");
  const files = state.files || [];
  const activeStates = new Set(
    files.filter((f) => !TERMINAL.includes(f.state) &&
                        f.state !== "discovered" && f.state !== "catalogued")
         .map((f) => f.state));

  for (const colState of RAIL_STATES) {
    const col = tpl.content.cloneNode(true);
    const colEl = col.querySelector(".rail-col");
    col.querySelector(".rail-col-head").textContent = colState;
    if (activeStates.has(colState)) colEl.classList.add("active-col");
    const body = col.querySelector(".rail-col-body");

    for (const f of files) {
      if (f.state !== colState) continue;
      const card = cardTpl.content.cloneNode(true);
      const cardEl = card.querySelector(".file-card");
      card.querySelector(".fc-name").textContent = f.name;
      card.querySelector(".fc-meta").textContent =
        `${(f.bytes / 1048576).toFixed(1)} MB | ${f.media_type}` +
        (f.sha256 ? ` | ${f.sha256.slice(0, 8)}` : "");
      card.querySelector(".fc-sub").textContent =
        colState === "catalogued" ? (f.caption || "") : "";
      if (!TERMINAL.includes(f.state) && f.state !== "discovered" && f.state !== "catalogued") {
        cardEl.classList.add("active");
      }
      if (f.state === "catalogued") cardEl.classList.add("done");
      if (phase === "intake" && f.state === "discovered") {
        cardEl.classList.add("intake");
        card.querySelector(".fc-exclude").onclick = async () => {
          try { await post("/api/exclude", { file_id: f.id }); pollNow(); }
          catch (e) { toast(e.message, "err"); }
        };
      }
      body.appendChild(card);
    }
    rail.appendChild(col);
  }
}

function renderLanes() {
  const qBody = $("quarantine-body");
  const dBody = $("duplicates-body");
  const files = state.files || [];
  const tpl = document.querySelector("#t-quarantine-row");

  const quarantined = files.filter((f) => f.state === "quarantined");
  qBody.innerHTML = quarantined.length ? "" : "<div class='lane-empty'>nothing quarantined</div>";
  for (const f of quarantined) {
    const row = tpl.content.cloneNode(true);
    row.querySelector(".q-name").textContent = f.name;
    row.querySelector(".q-reason").textContent = f.error || "";
    const btn = row.querySelector(".q-retry");
    if (!f.retryable) btn.remove();
    else btn.onclick = async () => {
      try { await post("/api/retry", { file_id: f.id }); toast("retrying " + f.name); }
      catch (e) { toast(e.message, "err"); }
    };
    qBody.appendChild(row);
  }

  const dupes = files.filter((f) => f.state === "duplicate");
  dBody.innerHTML = dupes.length ? "" : "<div class='lane-empty'>no duplicates</div>";
  for (const f of dupes) {
    const div = document.createElement("div");
    div.className = "q-row";
    div.innerHTML = `<span class="q-name mono">${f.name}</span>` +
                    `<span class="q-reason dim">${escapeHtml(f.error || "")}</span>`;
    dBody.appendChild(div);
  }
}

let lastLogLen = 0;
function renderConsole() {
  const log = state.log || [];
  const el = $("console");
  if (log.length !== lastLogLen) {
    el.textContent = log.join("\n");
    el.scrollTop = el.scrollHeight;
    lastLogLen = log.length;
  }
  $("console-updated").textContent = state.updated || "";
}

function pollNow() { lastMtime = null; pollState(); }

/* ================================================================ LIBRARY */

async function loadCatalogue() {
  try {
    const resp = await fetch("/api/catalogue");
    catalogue = await resp.json();
    renderLibrary();
  } catch (e) {
    toast("catalogue load failed: " + e.message, "err");
  }
}

function assets() { return (catalogue && catalogue.assets) || []; }

function pendingTags() {
  const out = [];
  for (const rec of assets()) {
    for (const cls of ["artworks", "persons"]) {
      for (const t of (rec.tags && rec.tags[cls]) || []) {
        if (t && t.status === "pending") out.push({ record: rec, tag_class: cls, tag: t });
      }
    }
  }
  return out;
}

function filteredAssets() {
  return assets().filter((rec) => {
    const t = rec.tags || {};
    if (facetFilters.media_type && t.media_type !== facetFilters.media_type) return false;
    if (facetFilters.asset_class && t.asset_class !== facetFilters.asset_class) return false;
    if (facetFilters.artist && !(t.artists || []).includes(facetFilters.artist)) return false;
    if (facetFilters.context && t.context !== facetFilters.context && t.event !== facetFilters.context) return false;
    if (facetFilters.date && t.date !== facetFilters.date) return false;
    return true;
  });
}

function renderFacetBlock(containerId, facetKey, values) {
  const block = $(containerId);
  block.querySelectorAll(".facet-chip").forEach((el) => el.remove());
  const counts = {};
  for (const rec of assets()) {
    const t = rec.tags || {};
    let vals;
    if (facetKey === "artist") vals = t.artists || [];
    else if (facetKey === "context") vals = [t.context || t.event].filter(Boolean);
    else vals = [t[facetKey]].filter(Boolean);
    for (const v of vals) counts[v] = (counts[v] || 0) + 1;
  }
  for (const val of Object.keys(counts).sort()) {
    const btn = document.createElement("button");
    btn.className = "facet-chip" + (facetFilters[facetKey] === val ? " on" : "");
    btn.innerHTML = `${escapeHtml(val)} <span class="count">${counts[val]}</span>`;
    btn.onclick = () => {
      facetFilters[facetKey] = facetFilters[facetKey] === val ? null : val;
      reviewMode = false;
      renderLibrary();
    };
    block.appendChild(btn);
  }
}

function renderDayChips() {
  const wrap = $("day-chips");
  wrap.innerHTML = "";
  const days = [...new Set(assets().map((r) => (r.tags || {}).date).filter(Boolean))].sort();
  for (const d of days) {
    const btn = document.createElement("button");
    btn.className = "facet-chip" + (facetFilters.date === d ? " on" : "");
    btn.textContent = d.slice(5); // MM-DD
    btn.title = d;
    btn.onclick = () => {
      facetFilters.date = facetFilters.date === d ? null : d;
      reviewMode = false;
      renderLibrary();
    };
    wrap.appendChild(btn);
  }
}

function renderGrid() {
  const grid = $("grid");
  const list = $("review-list");
  grid.classList.toggle("hidden", reviewMode);
  list.classList.toggle("hidden", !reviewMode);

  if (reviewMode) { renderReviewList(); return; }

  grid.innerHTML = "";
  const tpl = document.querySelector("#t-grid-tile");
  const rows = filteredAssets();
  $("grid-count").textContent = `${rows.length} asset${rows.length === 1 ? "" : "s"}`;
  for (const rec of rows) {
    const tile = tpl.content.cloneNode(true);
    const tileEl = tile.querySelector(".tile");
    const img = tile.querySelector(".tile-img");
    const localThumb = thumbUrl(rec);
    if (localThumb) img.style.backgroundImage = `url('${localThumb}')`;
    else img.textContent = (rec.tags || {}).media_type === "document" ? "\u{1F4C4}" : "\u{1F39E}";
    tile.querySelector(".tile-name").textContent = rec.key.split("/").pop();
    const badges = tile.querySelector(".tile-badges");
    const t = rec.tags || {};
    for (const chipVal of [t.media_type, t.asset_class]) {
      if (!chipVal) continue;
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = chipVal;
      badges.appendChild(chip);
    }
    const nPending = ((t.artworks || []).concat(t.persons || []))
      .filter((x) => x && x.status === "pending").length;
    if (nPending) {
      const chip = document.createElement("span");
      chip.className = "chip pending";
      chip.textContent = `${nPending} pending`;
      badges.appendChild(chip);
    }
    if (rec.key === selectedKey) tileEl.classList.add("selected");
    tileEl.onclick = () => { selectedKey = rec.key; renderLibrary(); };
    grid.appendChild(tile);
  }
}

function thumbUrl(rec) {
  // local thumbs are flat-hashed by sha256 prefix
  if (rec.sha256) return `/thumbs/${rec.sha256.slice(0, 16)}.jpg`;
  return null;
}

function renderReviewList() {
  const list = $("review-list");
  list.innerHTML = "";
  const tpl = document.querySelector("#t-review-row");
  const items = pendingTags();
  $("grid-count").textContent = `${items.length} pending tag${items.length === 1 ? "" : "s"}`;
  if (!items.length) {
    list.innerHTML = "<div class='lane-empty'>review queue is empty -- every tag is confirmed</div>";
    return;
  }
  for (const item of items) {
    const row = tpl.content.cloneNode(true);
    const thumb = row.querySelector(".rr-thumb");
    const url = thumbUrl(item.record);
    if (url) thumb.style.backgroundImage = `url('${url}')`;
    row.querySelector(".rr-asset").textContent = item.record.key;
    const kind = item.tag_class === "persons" ? "person" : "artwork";
    row.querySelector(".rr-question").innerHTML =
      `Is this ${kind} <b>${escapeHtml(item.tag.slug)}</b>?`;
    row.querySelector(".rr-conf").textContent =
      `confidence ${(item.tag.confidence ?? 0).toFixed(2)} | basis: ${item.tag.basis || "?"}`;
    row.querySelector(".rr-confirm").onclick = () => reviewAction(item, "confirm");
    row.querySelector(".rr-reject").onclick = () => reviewAction(item, "reject");
    list.appendChild(row);
  }
}

async function reviewAction(item, action) {
  try {
    await post("/api/review", {
      key: item.record.key, tag_class: item.tag_class,
      slug: item.tag.slug, action,
    });
    toast(`${item.tag.slug} ${action}ed`, action === "confirm" ? "ok" : undefined);
    await loadCatalogue();
  } catch (e) {
    toast(e.message, "err");
  }
}

function renderDetail() {
  const panel = $("detail");
  const layout = document.querySelector(".library-layout");
  const rec = assets().find((r) => r.key === selectedKey);
  if (!rec) {
    panel.classList.add("hidden");
    layout.classList.remove("has-detail");
    return;
  }
  panel.classList.remove("hidden");
  layout.classList.add("has-detail");
  const t = rec.tags || {};
  const thumb = thumbUrl(rec);
  const detailThumb = $("detail-thumb");
  const oldVideo = document.getElementById("detail-video");
  if (oldVideo) oldVideo.remove();
  if (t.media_type === "video") {
    detailThumb.style.backgroundImage = thumb ? `url('${thumb}')` : "none";
    const vid = document.createElement("video");
    vid.id = "detail-video";
    vid.controls = true;
    vid.preload = "metadata";
    vid.style.cssText = "width:100%;border-radius:8px;margin-bottom:10px;background:#000";
    if (thumb) vid.poster = thumb;
    detailThumb.style.display = "none";
    detailThumb.parentNode.insertBefore(vid, detailThumb);
    fetch(`/api/media-url?key=${encodeURIComponent(rec.key)}`)
      .then((r) => r.json())
      .then((d) => { if (d.ok) vid.src = d.url; else toast(d.error, "err"); })
      .catch((e) => toast("media url failed: " + e.message, "err"));
  } else {
    detailThumb.style.display = "";
    detailThumb.style.backgroundImage = thumb ? `url('${thumb}')` : "none";
  }
  $("detail-name").textContent = rec.key;
  $("detail-caption").textContent = t.caption || "";
  $("detail-rows").innerHTML = [
    ["sha256", rec.sha256 || ""],
    ["bytes", (rec.bytes || 0).toLocaleString()],
    ["ingested", rec.ingested || ""],
    ["date", `${t.date || "?"} (${t.date_basis || "?"})`],
    ["source", rec.source || ""],
    ["face pass", t.face_pass || ""],
  ].map(([k, v]) =>
    `<div class="d-row"><span class="d-key">${k}</span><span class="d-val">${escapeHtml(String(v))}</span></div>`
  ).join("");

  const tags = $("detail-tags");
  tags.innerHTML = "";
  const chips = [];
  for (const v of [t.edition, t.context, t.event, t.venue, t.media_type, t.asset_class]) {
    if (v) chips.push({ text: v });
  }
  for (const a of t.artists || []) chips.push({ text: "artist: " + a });
  for (const aw of t.artworks || []) {
    chips.push({ text: `artwork: ${aw.slug} (${(aw.confidence ?? 0).toFixed(2)})`, status: aw.status });
  }
  for (const s of t.scene || []) chips.push({ text: s });
  for (const c of chips) {
    const el = document.createElement("span");
    el.className = "chip" + (c.status ? " " + c.status : "");
    el.textContent = c.text;
    tags.appendChild(el);
  }

  $("btn-copy-link").onclick = async () => {
    const uri = `r2://slow-interpolation-media/${rec.key}`;
    try { await navigator.clipboard.writeText(uri); toast("copied " + uri, "ok"); }
    catch { toast(uri); }
  };

  // publish / unpublish (two-bucket copy-on-publish, default-private)
  let pubBtn = document.getElementById("btn-publish");
  if (!pubBtn) {
    pubBtn = document.createElement("button");
    pubBtn.id = "btn-publish";
    pubBtn.className = "btn";
    pubBtn.style.marginTop = "8px";
    $("btn-copy-link").after(pubBtn);
  }
  const isPublic = !!(t.public);
  pubBtn.textContent = isPublic ? "unpublish (remove public link)" : "publish (create public link)";
  pubBtn.className = isPublic ? "btn err" : "btn ok";
  pubBtn.onclick = async () => {
    pubBtn.disabled = true;
    try {
      const d = await post("/api/publish", { key: rec.key, action: isPublic ? "unpublish" : "publish" });
      if (!isPublic && d.result && d.result.public_url) {
        try { await navigator.clipboard.writeText(d.result.public_url); } catch {}
        toast("PUBLIC: " + d.result.public_url + " (copied)", "ok");
      } else {
        toast("unpublished " + rec.key.split("/").pop(), "ok");
      }
      await loadCatalogue();
    } catch (e) { toast(e.message, "err"); }
    pubBtn.disabled = false;
  };
  let pubUrlEl = document.getElementById("detail-public-url");
  if (!pubUrlEl) {
    pubUrlEl = document.createElement("div");
    pubUrlEl.id = "detail-public-url";
    pubUrlEl.className = "mono";
    pubUrlEl.style.cssText = "font-size:11px;word-break:break-all;margin-top:6px;color:var(--ok)";
    pubBtn.after(pubUrlEl);
  }
  pubUrlEl.textContent = isPublic ? (t.public_url || rec.public_url || "") : "";
}

function renderLibrary() {
  renderFacetBlock("facet-media-type", "media_type");
  renderFacetBlock("facet-asset-class", "asset_class");
  renderFacetBlock("facet-artist", "artist");
  renderFacetBlock("facet-context", "context");
  renderDayChips();
  const pend = pendingTags().length;
  $("review-count").textContent = pend;
  $("chip-review").classList.toggle("on", reviewMode);
  renderGrid();
  renderDetail();
}

/* ================================================================ wiring */

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (ch) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

function switchView(name) {
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.view === name));
  $("view-engine").classList.toggle("active", name === "engine");
  $("view-library").classList.toggle("active", name === "library");
  if (name === "library") loadCatalogue();
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.onclick = () => switchView(tab.dataset.view);
});

$("btn-scan").onclick = async () => {
  try {
    const r = await post("/api/scan");
    toast(`scanned: ${r.discovered} files discovered`);
    pollNow();
  } catch (e) { toast(e.message, "err"); }
};

$("btn-dryrun").onclick = async () => {
  try { await post("/api/dry-run", { sample: 3 }); toast("dry run started"); pollNow(); }
  catch (e) { toast(e.message, "err"); }
};

const approve = async () => {
  try { await post("/api/approve"); toast("full run started", "ok"); pollNow(); }
  catch (e) { toast(e.message, "err"); }
};
$("btn-approve").onclick = approve;
$("btn-gate-approve").onclick = approve;

$("btn-clear-facets").onclick = () => { facetFilters = {}; reviewMode = false; renderLibrary(); };
$("chip-review").onclick = () => { reviewMode = !reviewMode; renderLibrary(); };
$("btn-reload-cat").onclick = loadCatalogue;
$("detail-close").onclick = () => { selectedKey = null; renderLibrary(); };

setInterval(pollState, 1000);
pollState();
