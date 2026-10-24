"""Desktop window: an HTML/CSS arcade UI (ui/) in a native webview, driving the OCR engine.

One worker thread owns the engine (MLX must load and run on the same thread) and processes the
queue in order. The UI polls `Api.state()` for a versioned snapshot instead of receiving pushed
JavaScript calls, so a native dialog holding the main thread can never deadlock the worker.
"""

from __future__ import annotations

import logging
import os
import queue
import re
import shutil
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

import webview
from webview.dom import DOMEventHandler

from . import __version__
from .engine.core import SUPPORTED_EXTS, UnlimitedOCR

TITLE = "Світлячок"
UI_DIR = Path(__file__).parent / "ui"
log = logging.getLogger("svitlyachok")


def data_dir() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    path = base / "Svitlyachok"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _first_path(selection) -> str | None:
    """File dialogs return a str or a sequence depending on platform and dialog type."""
    if not selection:
        return None
    return selection if isinstance(selection, str) else selection[0]


@dataclass
class Job:
    id: str
    path: str
    name: str
    state: str = "queued"  # queued → working → done | error
    message: str = ""
    started: float = 0.0  # epoch seconds, so the UI can run a live timer
    seconds: float = 0.0
    pages: int = 0
    text_pages: int = 0
    ocr_pages: int = 0
    md_path: str = ""


class Svitlyachok:
    def __init__(self):
        self.window: webview.Window | None = None
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()
        self.version = 0
        self.queue: queue.Queue[str] = queue.Queue()
        self.force_ocr = False
        self.results = data_dir() / "results"
        shutil.rmtree(self.results, ignore_errors=True)  # results only live for one session
        self.engine = UnlimitedOCR(on_engine=self._on_engine)
        self.engine_state = {"state": "idle", "name": "MLX" if self.engine.backend_name == "mlx" else "CPU"}
        threading.Thread(target=self._work, name="ocr-worker", daemon=True).start()

    # ── state shared with the UI ──

    def _changed(self):
        self.version += 1

    def _update(self, job: Job, **fields):
        with self.lock:
            for key, value in fields.items():
                setattr(job, key, value)
            self._changed()

    def _on_engine(self, state: str, details: dict):
        with self.lock:
            self.engine_state = {**self.engine_state, "state": state, **details}
            self._changed()

    def snapshot(self, since: int) -> dict | None:
        with self.lock:
            if since == self.version:
                return None
            return {
                "version": self.version,
                "engine": self.engine_state,
                "force_ocr": self.force_ocr,
                "jobs": [asdict(job) for job in self.jobs.values()],
                "now": time.time(),
            }

    # ── queue ──

    def add_paths(self, paths: list[str]) -> int:
        files: list[Path] = []
        for p in map(Path, paths):
            if p.is_dir():  # a dropped folder brings in every supported file inside it
                files += sorted(
                    f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS and not f.name.startswith(".")
                )
            elif p.is_file() and not p.name.startswith("."):
                files.append(p)
        with self.lock:
            for f in files:
                job = Job(id=uuid.uuid4().hex[:12], path=str(f), name=f.name)
                self.jobs[job.id] = job
                self.queue.put(job.id)
            if files:
                self._changed()
        return len(files)

    def _work(self):
        while True:
            job = self.jobs.get(self.queue.get())
            if job is None or job.state != "queued":  # cleared while waiting
                continue
            self._update(job, state="working", started=time.time(), message="Starting")
            load_before = self.engine.load_seconds
            start = time.perf_counter()

            def elapsed() -> float:  # model download/loading is shown separately, not billed to the file
                return time.perf_counter() - start - (self.engine.load_seconds - load_before)

            try:
                result = self.engine.convert(
                    job.path,
                    self.results / job.id,
                    force_ocr=self.force_ocr,
                    on_progress=lambda message: self._update(job, message=message),
                )
                self._update(
                    job, state="done", message="", seconds=elapsed(), md_path=str(result.md_path),
                    pages=result.pages, text_pages=result.text_pages, ocr_pages=result.ocr_pages,
                )
            except Exception as e:
                log.exception("conversion failed: %s", job.path)
                if self.engine_state["state"] in ("downloading", "loading"):
                    self._on_engine("error", {"message": str(e)})
                self._update(job, state="error", message=_friendly_error(e), seconds=elapsed())

    def clear_finished(self):
        with self.lock:
            for job_id in [j.id for j in self.jobs.values() if j.state in ("done", "error")]:
                del self.jobs[job_id]
                shutil.rmtree(self.results / job_id, ignore_errors=True)
            self._changed()

    # ── saving ──

    def save_markdown(self, job: Job, destination: Path):
        """Write the .md and copy the figures it links to into images/ beside it."""
        source = Path(job.md_path)
        markdown = source.read_text(encoding="utf-8")
        destination.write_text(markdown, encoding="utf-8")
        for link in set(re.findall(r"\]\((images/[^)\s]+)\)", markdown)):
            image = source.parent / link
            if image.exists():
                (destination.parent / "images").mkdir(exist_ok=True)
                shutil.copy2(image, destination.parent / link)


def _friendly_error(e: Exception) -> str:
    text = str(e).strip() or type(e).__name__
    return text if len(text) < 140 else text[:137] + "…"


class Api:
    """Methods callable from JavaScript as window.pywebview.api.<name>()."""

    def __init__(self, app: Svitlyachok):
        self._app = app  # underscore: not exposed to JavaScript

    def info(self) -> dict:
        return {"version": __version__, "platform": sys.platform, "engine": self._app.engine_state["name"]}

    def state(self, since: int = -1) -> dict | None:
        return self._app.snapshot(since)

    def pick_files(self) -> int:
        paths = self._app.window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True)
        return self._app.add_paths(list(paths or []))

    def add_paths(self, paths: list[str]) -> int:
        return self._app.add_paths(paths)

    def set_force_ocr(self, on: bool) -> bool:
        with self._app.lock:
            self._app.force_ocr = bool(on)
            self._app._changed()
        return self._app.force_ocr

    def markdown(self, job_id: str) -> str:
        job = self._app.jobs.get(job_id)
        return Path(job.md_path).read_text(encoding="utf-8") if job and job.state == "done" else ""

    def save(self, job_id: str) -> dict:
        job = self._app.jobs.get(job_id)
        if not job or job.state != "done":
            return {"ok": False}
        target = _first_path(
            self._app.window.create_file_dialog(
                webview.FileDialog.SAVE, save_filename=Path(job.name).stem + ".md", file_types=("Markdown (*.md)",)
            )
        )
        if not target:
            return {"ok": False, "cancelled": True}
        target = Path(target) if Path(target).suffix.lower() == ".md" else Path(target).with_suffix(".md")
        self._app.save_markdown(job, target)
        return {"ok": True, "path": str(target)}

    def save_all(self) -> dict:
        done = [j for j in self._app.jobs.values() if j.state == "done"]
        if not done:
            return {"ok": False}
        folder = _first_path(self._app.window.create_file_dialog(webview.FileDialog.FOLDER))
        if not folder:
            return {"ok": False, "cancelled": True}
        used: set[str] = set()
        for job in done:
            stem, n = Path(job.name).stem, 1
            name = f"{stem}.md"
            while name.lower() in used or (Path(folder) / name).exists():  # never overwrite
                n += 1
                name = f"{stem} ({n}).md"
            used.add(name.lower())
            self._app.save_markdown(job, Path(folder) / name)
        return {"ok": True, "count": len(done), "path": folder}

    def clear_finished(self) -> None:
        self._app.clear_finished()


def _enable_drop(app: Svitlyachok):
    def on_drop(event):
        files = event.get("dataTransfer", {}).get("files", [])
        app.add_paths([f["pywebviewFullPath"] for f in files if f.get("pywebviewFullPath")])

    document = app.window.dom.document
    document.events.dragover += DOMEventHandler(lambda event: None, prevent_default=True)
    document.events.drop += DOMEventHandler(on_drop, prevent_default=True)


def main() -> int:
    logging.basicConfig(
        filename=data_dir() / "svitlyachok.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    if "--selftest" in sys.argv:
        from .selftest import run

        return run(ocr="--ocr" in sys.argv)

    app = Svitlyachok()
    app.window = webview.create_window(
        TITLE,
        url=str(UI_DIR / "index.html"),
        js_api=Api(app),
        width=1120,
        height=800,
        min_size=(900, 640),
        background_color="#07060f",
    )
    app.window.events.loaded += lambda: _enable_drop(app)
    webview.start(debug=os.environ.get("SVITLYACHOK_DEBUG") == "1")
    return 0
