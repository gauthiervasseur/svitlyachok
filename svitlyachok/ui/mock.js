"use strict";
// Design preview only: open index.html?mock (or ?mock=download, ?mock=empty) in a browser.
window.mockApi = (() => {
  const scenario = new URLSearchParams(location.search).get("mock") || "table";
  const now = () => Date.now() / 1000;
  let version = 0;
  let force = false;
  let engine = { state: scenario === "download" ? "downloading" : "ready", name: "MLX", done: 0, total: 6.22e9 };
  const job = (name, extra) => ({
    id: Math.random().toString(16).slice(2), path: `/Users/team/Documents/${name}`, name, state: "queued", message: "",
    started: 0, seconds: 0, pages: 0, text_pages: 0, ocr_pages: 0, md_path: "", ...extra,
  });
  let jobs = scenario === "empty" ? [] : [
    job("Quarterly Sales Report Q3.pdf", { state: "done", seconds: 0.31, pages: 12, text_pages: 12 }),
    job("скан_договору_2024.pdf", { state: "done", seconds: 41.6, pages: 6, ocr_pages: 6 }),
    job("whiteboard-photo.heic", { state: "done", seconds: 5.2, pages: 1, ocr_pages: 1 }),
    job("Board deck - final FINAL v7.pptx", { state: "done", seconds: 0.08, pages: 1, text_pages: 1 }),
    job("mixed-contract-annexes.pdf", { state: "working", started: now() - 7.4, message: "OCR pages 9-16" }),
    job("budget_2027.xlsx"),
    job("legacy-memo.doc", { state: "error", seconds: 0.01, message: ".doc files need LibreOffice; save as PDF or .docx/.pptx/.xlsx instead" }),
  ];
  const tick = setInterval(() => {
    if (engine.state === "downloading") {
      engine = { ...engine, done: Math.min(engine.total, engine.done + 0.09e9) };
      if (engine.done >= engine.total) engine = { ...engine, state: "loading" };
      version++;
    }
  }, 200);
  const done = (j) => ({ ...j, state: "done", seconds: 3 + Math.random() * 9, pages: 2, ocr_pages: 2 });
  return {
    info: async () => ({ version: "1.0.0", platform: "darwin", engine: "MLX" }),
    state: async (since) => (since === version ? null : { version, engine, force_ocr: force, jobs, now: now() }),
    pick_files: async () => {
      const added = [job("new-scan-001.png"), job("meeting-notes.docx")];
      jobs = [...jobs, ...added];
      version++;
      setTimeout(() => { jobs = jobs.map((j) => (added.some((a) => a.id === j.id) ? done(j) : j)); version++; }, 2500);
      return added.length;
    },
    add_paths: async () => 0,
    set_force_ocr: async (on) => { force = on; version++; return on; },
    markdown: async () => "# Quarterly Sales Report\n\nThis report summarises revenue across four regions for Q3 2026.\n\n## 1. Revenue by region\n\n| Region | Q2 | Q3 |\n| --- | --- | --- |\n| North | 1,200 | 1,480 |\n",
    save: async () => ({ ok: true, path: "/Users/team/Desktop/Quarterly Sales Report Q3.md" }),
    save_all: async () => ({ ok: true, count: jobs.filter((j) => j.state === "done").length, path: "/Users/team/Desktop/markdown" }),
    clear_finished: async () => { jobs = jobs.filter((j) => j.state === "queued" || j.state === "working"); version++; },
  };
})();
