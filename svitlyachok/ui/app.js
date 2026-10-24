"use strict";

const $ = (id) => document.getElementById(id);
const els = {
  drop: $("drop"), pick: $("pick"), rows: $("rows"), empty: $("empty"), note: $("queue-note"),
  engine: $("engine"), engineText: $("engine-text"), files: $("hud-files"), pages: $("hud-pages"), time: $("hud-time"),
  download: $("download"), barFill: $("bar-fill"), bar: document.querySelector(".bar"), downloadText: $("download-text"),
  saveAll: $("save-all"), clear: $("clear"), forceOcr: $("force-ocr"), sound: $("sound"), version: $("version"),
  viewer: $("viewer"), viewerTitle: $("viewer-title"), viewerText: $("viewer-text"), viewerSave: $("viewer-save"),
  viewerClose: $("viewer-close"), toast: $("toast"), kbdMod: $("kbd-mod"),
};

let api = null;
let version = -1;
let state = { jobs: [], engine: { state: "idle", name: "" }, now: Date.now() / 1000 };
let clockSkew = 0;           // backend clock minus browser clock, for live timers
let viewing = null;          // job id open in the viewer
const rowsById = new Map();
const lastStates = new Map();

// ── Formatting ──

const pad = (n, width) => String(Math.max(0, Math.floor(n))).padStart(width, "0");
function clock(seconds) {
  const s = Math.max(0, seconds);
  const minutes = Math.floor(s / 60);
  return `${pad(minutes, 2)}:${(s - minutes * 60).toFixed(1).padStart(4, "0")}`;
}
const gb = (bytes) => (bytes / 1e9).toFixed(2);

// ── 8-bit sound ──

const sound = {
  on: true,
  ctx: null,
  play(notes) {
    if (!this.on) return;
    try {
      this.ctx = this.ctx || new (window.AudioContext || window.webkitAudioContext)();
      let t = this.ctx.currentTime;
      for (const [freq, dur] of notes) {
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        osc.type = "square";
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0.05, t);
        gain.gain.exponentialRampToValueAtTime(0.001, t + dur);
        osc.connect(gain).connect(this.ctx.destination);
        osc.start(t);
        osc.stop(t + dur);
        t += dur * 0.9;
      }
    } catch (e) { /* audio unavailable: stay silent */ }
  },
  coin() { this.play([[988, 0.07], [1319, 0.16]]); },
  clear() { this.play([[523, 0.08], [659, 0.08], [784, 0.08], [1047, 0.2]]); },
  fail() { this.play([[392, 0.12], [311, 0.12], [233, 0.3]]); },
  click() { this.play([[1760, 0.03]]); },
};
try { sound.on = localStorage.getItem("sv-sound") !== "off"; } catch (e) { /* storage blocked */ }

// ── Toast ──

let toastTimer = 0;
function toast(message, bad = false) {
  els.toast.textContent = message;
  els.toast.classList.toggle("bad", bad);
  els.toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => els.toast.classList.remove("show"), 3600);
}

// ── Rendering ──

function modeOf(job) {
  if (job.state !== "done") return null;
  if (job.ocr_pages && job.text_pages) return ["mix", "MIX"];
  return job.ocr_pages ? ["ocr", "OCR"] : ["text", "TEXT"];
}

const STATUS = { queued: "READY", working: "WORKING", done: "★ CLEAR", error: "GAME OVER" };

function buildRow(job) {
  const tr = document.createElement("tr");
  tr.className = "new";
  tr.innerHTML = `
    <td class="c-rank rank"></td>
    <td class="c-name"><div class="name"></div><div class="sub"></div></td>
    <td class="c-num pages"></td>
    <td class="mode-cell"></td>
    <td class="c-num time"></td>
    <td class="status"></td>
    <td class="c-act"><div class="actions"></div></td>`;
  tr.querySelector(".name").textContent = job.name;
  tr.querySelector(".name").title = job.path;
  return tr;
}

function renderActions(tr, job) {
  const box = tr.querySelector(".actions");
  const want = job.state === "done" ? "done" : "";
  if (box.dataset.for === want) return;
  box.dataset.for = want;
  box.replaceChildren();
  if (job.state !== "done") return;
  const view = Object.assign(document.createElement("button"), { className: "btn btn-sm", type: "button", textContent: "VIEW" });
  const save = Object.assign(document.createElement("button"), { className: "btn btn-sm", type: "button", textContent: "SAVE" });
  view.addEventListener("click", () => openViewer(job.id));
  save.addEventListener("click", () => saveOne(job.id));
  view.setAttribute("aria-label", `View markdown of ${job.name}`);
  save.setAttribute("aria-label", `Save markdown of ${job.name}`);
  box.append(view, save);
}

function jobTime(job) {
  if (job.state === "done" || job.state === "error") return clock(job.seconds);
  if (job.state === "working") {
    const engineBusy = ["downloading", "loading"].includes(state.engine.state);
    return engineBusy ? "--:--.-" : clock(Date.now() / 1000 + clockSkew - job.started);
  }
  return "—";
}

function render() {
  const jobs = state.jobs;
  const seen = new Set();
  jobs.forEach((job, index) => {
    seen.add(job.id);
    let tr = rowsById.get(job.id);
    if (!tr) {
      tr = buildRow(job);
      rowsById.set(job.id, tr);
    }
    if (els.rows.children[index] !== tr) els.rows.insertBefore(tr, els.rows.children[index] || null);
    tr.classList.toggle("err", job.state === "error");
    tr.querySelector(".rank").textContent = pad(index + 1, 2);
    const sub = job.state === "working" || job.state === "error" ? job.message.toUpperCase() : "";
    tr.querySelector(".sub").textContent = sub;
    tr.querySelector(".pages").textContent = job.state === "done" ? job.pages : "—";
    const mode = modeOf(job);
    const modeCell = tr.querySelector(".mode-cell");
    modeCell.replaceChildren();
    if (mode) {
      const badge = Object.assign(document.createElement("span"), { className: `mode ${mode[0]}`, textContent: mode[1] });
      badge.title = `${job.text_pages} page(s) read directly, ${job.ocr_pages} page(s) OCR`;
      modeCell.append(badge);
    } else {
      modeCell.textContent = "—";
    }
    tr.querySelector(".time").textContent = jobTime(job);
    const status = tr.querySelector(".status");
    status.className = `status ${job.state}`;
    status.textContent = STATUS[job.state] || job.state.toUpperCase();
    renderActions(tr, job);

    const before = lastStates.get(job.id);
    if (before && before !== job.state) {
      if (job.state === "done") sound.clear();
      if (job.state === "error") sound.fail();
    }
    lastStates.set(job.id, job.state);
  });
  for (const [id, tr] of rowsById) {
    if (!seen.has(id)) { tr.remove(); rowsById.delete(id); lastStates.delete(id); }
  }

  const done = jobs.filter((j) => j.state === "done");
  const waiting = jobs.filter((j) => j.state === "queued" || j.state === "working").length;
  els.empty.hidden = jobs.length > 0;
  els.note.textContent = waiting ? `${waiting} IN PLAY` : "";
  els.files.textContent = pad(done.length, 3);
  els.pages.textContent = pad(done.reduce((sum, j) => sum + j.pages, 0), 4);
  els.time.textContent = clock(jobs.reduce((sum, j) => sum + (j.state === "done" || j.state === "error" ? j.seconds : 0), 0));
  els.saveAll.disabled = done.length === 0;
  els.clear.disabled = !jobs.some((j) => j.state === "done" || j.state === "error");
  els.forceOcr.checked = !!state.force_ocr;
  renderEngine();
}

function renderEngine() {
  const e = state.engine;
  els.engine.className = `engine ${e.state}`;
  const labels = { idle: "STANDBY", downloading: "DOWNLOAD", loading: "LOADING", ready: "READY", error: "ERROR" };
  els.engineText.textContent = `${e.name || ""} ${labels[e.state] || e.state.toUpperCase()}`.trim();
  els.engine.title = e.state === "error" ? e.message || "" : e.state === "idle" ? "The OCR model loads when a page needs it" : e.backend || "";
  const downloading = e.state === "downloading" && e.total > 0;
  els.download.hidden = !downloading;
  if (downloading) {
    const pct = Math.min(100, (100 * e.done) / e.total);
    els.barFill.style.width = `${pct}%`;
    els.bar.setAttribute("aria-valuenow", pct.toFixed(0));
    els.downloadText.textContent = `${gb(e.done)} / ${gb(e.total)} GB · ${pct.toFixed(0)}% · ONE TIME ONLY`;
  }
}

// ── Actions ──

async function pick() {
  sound.click();
  const added = await api.pick_files();
  if (added) sound.coin();
}

async function saveOne(id) {
  sound.click();
  const result = await api.save(id);
  if (result && result.ok) toast(`SAVED ▶ ${result.path}`);
}

async function openViewer(id) {
  const job = state.jobs.find((j) => j.id === id);
  if (!job) return;
  viewing = id;
  els.viewerTitle.textContent = job.name.replace(/\.[^.]+$/, "") + ".MD";
  els.viewerText.textContent = await api.markdown(id);
  els.viewer.hidden = false;
  els.viewerText.scrollTop = 0;
  els.viewerClose.focus();
}

function closeViewer() {
  els.viewer.hidden = true;
  viewing = null;
}

els.pick.addEventListener("click", pick);
els.saveAll.addEventListener("click", async () => {
  sound.click();
  const result = await api.save_all();
  if (result && result.ok) toast(`SAVED ${result.count} FILE${result.count > 1 ? "S" : ""} ▶ ${result.path}`);
});
els.clear.addEventListener("click", async () => {
  sound.click();
  await api.clear_finished();
  version = -1;
});
els.forceOcr.addEventListener("change", () => { sound.click(); api.set_force_ocr(els.forceOcr.checked); });
els.sound.addEventListener("click", () => {
  sound.on = !sound.on;
  try { localStorage.setItem("sv-sound", sound.on ? "on" : "off"); } catch (e) { /* storage blocked */ }
  renderSound();
  sound.click();
});
function renderSound() {
  els.sound.textContent = sound.on ? "♪ ON" : "♪ OFF";
  els.sound.setAttribute("aria-pressed", String(sound.on));
}
els.viewerClose.addEventListener("click", closeViewer);
els.viewerSave.addEventListener("click", () => viewing && saveOne(viewing));
els.viewer.addEventListener("click", (e) => { if (e.target === els.viewer) closeViewer(); });

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !els.viewer.hidden) closeViewer();
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "o") { e.preventDefault(); pick(); }
});

// Drag highlight (the drop itself is handled natively, which provides full file paths).
let dragDepth = 0;
document.addEventListener("dragenter", (e) => { e.preventDefault(); dragDepth++; els.drop.classList.add("over"); });
document.addEventListener("dragleave", () => { if (--dragDepth <= 0) { dragDepth = 0; els.drop.classList.remove("over"); } });
document.addEventListener("dragover", (e) => e.preventDefault());
document.addEventListener("drop", (e) => {
  e.preventDefault();
  dragDepth = 0;
  els.drop.classList.remove("over");
  const before = state.jobs.length;
  setTimeout(() => { if (state.jobs.length > before) sound.coin(); }, 600);
});

// ── Ambient fireflies ──

function spawnFireflies(count) {
  const sky = document.querySelector(".sky");
  for (let i = 0; i < count; i++) {
    const f = document.createElement("i");
    f.style.left = `${Math.random() * 100}%`;
    f.style.top = `${30 + Math.random() * 70}%`;
    f.style.setProperty("--dx", `${Math.round(Math.random() * 120 - 60)}px`);
    f.style.setProperty("--dy", `${Math.round(-40 - Math.random() * 120)}px`);
    f.style.setProperty("--d", `${10 + Math.random() * 14}s`);
    f.style.setProperty("--delay", `${-Math.random() * 20}s`);
    sky.append(f);
  }
}

// ── Main loop ──

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function poll() {
  for (;;) {
    try {
      const snapshot = await api.state(version);
      if (snapshot) {
        state = snapshot;
        version = snapshot.version;
        clockSkew = snapshot.now - Date.now() / 1000;
        render();
      }
    } catch (e) { /* window closing or backend busy: try again */ }
    await sleep(250);
  }
}

function tickTimers() {
  for (const job of state.jobs) {
    if (job.state === "working") {
      const tr = rowsById.get(job.id);
      if (tr) tr.querySelector(".time").textContent = jobTime(job);
    }
  }
}

async function start(backend) {
  api = backend;
  const info = await api.info();
  els.version.textContent = `V${info.version}`;
  els.kbdMod.textContent = info.platform === "darwin" ? "CMD" : "CTRL";
  renderSound();
  spawnFireflies(18);
  setInterval(tickTimers, 100);
  poll();
}

if (new URLSearchParams(location.search).has("mock")) {
  const script = document.createElement("script");
  script.src = "mock.js";
  script.onload = () => start(window.mockApi);
  document.body.append(script);
} else if (window.pywebview && window.pywebview.api) {
  start(window.pywebview.api);
} else {
  window.addEventListener("pywebviewready", () => start(window.pywebview.api));
}
