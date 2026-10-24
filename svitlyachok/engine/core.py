"""Convert documents to Markdown: Office and text files directly, digital PDF pages from their
text layer, and scans/photos with Baidu's Unlimited-OCR (MLX on Apple Silicon, PyTorch elsewhere)."""

from __future__ import annotations

import ast
import base64
import importlib.util
import itertools
import logging
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pymupdf
from PIL import Image, ImageOps, ImageSequence

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass

from .formats import DIRECT_EXTS, direct_to_markdown
from .weights import ensure_weights

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".heic", ".heif"}
# Formats PyMuPDF can open and paginate natively.
DOC_EXTS = {".pdf", ".xps", ".oxps", ".epub", ".mobi", ".fb2", ".cbz", ".svg"}
# Older Office formats, converted to PDF through LibreOffice when it is installed.
LEGACY_OFFICE_EXTS = {".doc", ".ppt", ".xls", ".odt", ".odp", ".ods", ".rtf"}
SUPPORTED_EXTS = IMAGE_EXTS | DOC_EXTS | DIRECT_EXTS | LEGACY_OFFICE_EXTS

Progress = Callable[[str], None]
EngineEvent = Callable[[str, dict], None]  # (state, details): downloading / loading / ready
log = logging.getLogger("svitlyachok.engine")

# Each layout block starts with a tag giving its label and box(es) on a 0-999 grid:
#   <|det|>title [x1, y1, x2, y2]<|/det|>Text…   or   <|ref|>title<|/ref|><|det|>[[…]]<|/det|>Text…
BLOCK_TAG_RE = re.compile(
    r"<\|ref\|>(?P<ref>.*?)<\|/ref\|><\|det\|>(?P<ref_box>.*?)<\|/det\|>"
    r"|<\|det\|>\s*(?P<label>[A-Za-z_][\w-]*)\s*(?P<box>[\[\]\d\s,.]*)<\|/det\|>",
    re.S,
)
LEFTOVER_RE = re.compile(r"<\|det\|>.*?<\|/det\|>|<\|/?ref\|>|<\|/?det\|>|<｜end▁of▁sentence｜>|<PAGE>", re.S)
VISUAL_LABELS = {"image", "chart", "figure", "photo", "diagram"}
HEADING_PREFIX = {"title": "## ", "sub_title": "### ", "subtitle": "### "}
BULLET_RE = re.compile(r"^[ \t]*[•·▪◦●○■□‣⁃]\s*", re.M)


# ── Inputs → page images ────────────────────────────────────────────────────


def _find_soffice() -> str | None:
    return shutil.which("soffice") or next(
        (p for p in ["/Applications/LibreOffice.app/Contents/MacOS/soffice"] if Path(p).exists()), None
    )


def _office_to_pdf(path: Path, work_dir: Path) -> Path:
    soffice = _find_soffice()
    if not soffice:
        raise RuntimeError(f"{path.suffix} files need LibreOffice; save as PDF or .docx/.pptx/.xlsx instead")
    subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(work_dir), str(path)],
        check=True,
        capture_output=True,
        timeout=600,
    )
    pdf = work_dir / f"{path.stem}.pdf"
    if not pdf.exists():
        raise RuntimeError(f"{path.name}: LibreOffice did not produce a PDF.")
    return pdf


def as_document(path: Path, work_dir: Path) -> Path | None:
    """Return a file PyMuPDF can paginate (converting Office files to PDF), or None for images."""
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return None
    if ext in LEGACY_OFFICE_EXTS:
        return _office_to_pdf(path, work_dir)
    if ext in DOC_EXTS:
        return path
    raise ValueError(f"unsupported file type {ext or '(none)'}")


def image_frames(path: Path, work_dir: Path) -> dict[int, Path]:
    """Save each frame of an image file (several for multi-page TIFFs) as an RGB PNG."""
    frames = {}
    with Image.open(path) as img:
        for i, frame in enumerate(ImageSequence.Iterator(img)):
            frames[i] = work_dir / f"page_{i + 1:04d}.png"
            ImageOps.exif_transpose(frame).convert("RGB").save(frames[i])
    return frames


def render_pages(doc: pymupdf.Document, page_numbers: list[int], work_dir: Path, dpi: int) -> dict[int, Path]:
    matrix = pymupdf.Matrix(dpi / 72, dpi / 72)
    rendered = {}
    for i in page_numbers:
        rendered[i] = work_dir / f"page_{i + 1:04d}.png"
        doc[i].get_pixmap(matrix=matrix, alpha=False).save(rendered[i])
    return rendered


# ── Digital pages: read the embedded text layer, no OCR ─────────────────────

MIN_TEXT_CHARS = 20


def has_text_layer(page: pymupdf.Page) -> bool:
    """True when the page carries real, readable text (not a scan, nor a scan with an OCR layer)."""
    visible = sum(len(span["chars"]) for span in page.get_texttrace() if span["type"] != 3)  # 3 = invisible
    if visible < MIN_TEXT_CHARS:
        return False
    text = page.get_text()
    unreadable = sum(ch == "\ufffd" or "\ue000" <= ch <= "\uf8ff" for ch in text)  # fonts without Unicode map
    if unreadable > 0.05 * visible:
        return False
    page_area = abs(page.rect)
    return not any(abs(pymupdf.Rect(img["bbox"]) & page.rect) > 0.85 * page_area for img in page.get_image_info())


DATA_URI_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(data:image/(\w+);base64,([A-Za-z0-9+/=\s]+)\)")


def _tidy_text_layer_markdown(md: str, images_dir: Path, prefix: str) -> str:
    # Images arrive embedded as base64 (see markdown_from_text_layer); save them as files.
    counter = itertools.count(1)

    def save_image(m: re.Match) -> str:
        name = f"{prefix}_{next(counter)}.{m[2].lower().replace('jpeg', 'jpg')}"
        images_dir.mkdir(parents=True, exist_ok=True)
        (images_dir / name).write_bytes(base64.b64decode(m[3]))
        return f"![{m[1]}]({images_dir.name}/{name})"

    md = DATA_URI_IMAGE_RE.sub(save_image, md)
    md = re.sub(r"^(#+ )\*\*(.+?)\*\*[ \t]*$", r"\1\2", md, flags=re.M)  # "# **Title**" → "# Title"
    md = re.sub(r"\*\*([^*\n]+?)[ \t]+\*\*", r"**\1**", md)  # "**Region **" → "**Region**"
    md = re.sub(r"[ \t]+$", "", md, flags=re.M)
    md = re.sub(r"(?:<br>)+\|", "|", md)  # line breaks trailing a table cell
    md = re.sub(r"([^\n])\n(#{1,6} )", r"\1\n\n\2", md)  # blank line before headings
    md = re.sub(r"^  (- )", r"\1", md, flags=re.M)  # top-level list items come indented by two
    md = re.sub(r"^(- .*)\n\n(?=- )", r"\1\n", md, flags=re.M)  # keep list items together
    return re.sub(r"\n{3,}", "\n\n", md).strip()


def markdown_from_text_layer(
    doc: pymupdf.Document, images_dir: Path, stem: str, on_progress: Progress
) -> dict[int, str]:
    """Markdown for every page that has a usable text layer, keyed by page index."""
    pages = [i for i, page in enumerate(doc) if has_text_layer(page)]
    if not pages:
        return {}
    try:
        import pymupdf4llm

        # Images are embedded rather than written to image_path: pymupdf4llm replaces spaces in
        # that path with underscores, which breaks folders like "Application Support".
        chunks = pymupdf4llm.to_markdown(
            doc,
            pages=pages,
            page_chunks=True,
            embed_images=True,
            image_format="jpg",
            show_progress=False,
        )
    except Exception as e:  # fall back to OCR for the whole document
        log.warning("text-layer extraction failed: %s", e)
        on_progress("Text layer unreadable, using OCR")
        return {}
    if len(chunks) != len(pages):
        log.warning("text-layer extraction returned %d chunks for %d pages", len(chunks), len(pages))
        return {}
    return {
        i: _tidy_text_layer_markdown(chunk["text"], images_dir, f"{stem}_p{i + 1}")
        for i, chunk in zip(pages, chunks)
    }


# ── Raw model output → clean Markdown ───────────────────────────────────────


def _parse_boxes(text: str) -> list[list[float]]:
    try:
        boxes = ast.literal_eval(text.strip())
    except (ValueError, SyntaxError):
        return []
    if boxes and isinstance(boxes[0], (int, float)):
        boxes = [boxes]
    return [b for b in boxes if isinstance(b, (list, tuple)) and len(b) == 4]


def clean_page(raw: str, page_image: Path | None, images_dir: Path, prefix: str) -> str:
    """Turn one page of tagged model output into Markdown, cropping figures into `images_dir`."""
    counter = itertools.count(1)
    image = Image.open(page_image).convert("RGB") if page_image else None

    def crop(boxes: str) -> list[str]:
        if image is None:
            return []
        links = []
        w, h = image.size
        for x1, y1, x2, y2 in _parse_boxes(boxes):
            box = (int(x1 / 999 * w), int(y1 / 999 * h), int(x2 / 999 * w), int(y2 / 999 * h))
            if box[2] - box[0] < 8 or box[3] - box[1] < 8:
                continue
            name = f"{prefix}_{next(counter)}.jpg"
            images_dir.mkdir(parents=True, exist_ok=True)
            image.crop(box).save(images_dir / name, quality=90)
            links.append(f"![]({images_dir.name}/{name})")
        return links

    # Split into (label, boxes, content) blocks; text before the first tag has no label.
    tags = list(BLOCK_TAG_RE.finditer(raw))
    blocks = [("", "", raw[: tags[0].start()] if tags else raw)]
    for tag, nxt in zip(tags, tags[1:] + [None]):
        label = (tag["ref"] or tag["label"] or "").strip()
        boxes = tag["ref_box"] if tag["ref"] is not None else tag["box"]
        blocks.append((label, boxes, raw[tag.end() : nxt.start() if nxt else len(raw)]))

    parts = []
    for label, boxes, content in blocks:
        content = LEFTOVER_RE.sub("", content).strip()
        if label in VISUAL_LABELS:
            parts += crop(boxes)
        if not content:
            continue
        content = BULLET_RE.sub("- ", content)
        prefix_md = HEADING_PREFIX.get(label, "")
        if prefix_md and not content.startswith("#"):
            content = prefix_md + content
        parts.append(content)

    text = "\n\n".join(parts).replace("\\coloneqq", ":=").replace("\\eqqcolon", "=:")
    text = re.sub(r"^(- .*)\n\n(?=- )", r"\1\n", text, flags=re.M)  # keep list items together
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ── Model ───────────────────────────────────────────────────────────────────


def pick_backend(requested: str = "auto") -> str:
    """MLX on Apple Silicon when mlx-vlm is installed (several times faster there), else PyTorch."""
    if requested != "auto":
        return requested
    apple_silicon = sys.platform == "darwin" and platform.machine() == "arm64"
    return "mlx" if apple_silicon and importlib.util.find_spec("mlx_vlm") else "torch"


def split_pages(raw: str) -> list[str]:
    """Multi-page output starts each page with a <PAGE> marker."""
    parts = raw.split("<PAGE>")
    return parts[1:] if len(parts) > 1 and not parts[0].strip() else parts


@dataclass
class Conversion:
    md_path: Path
    pages: int
    text_pages: int  # read directly (text layer, Office, text files)
    ocr_pages: int


class UnlimitedOCR:
    """Converts documents to Markdown. The model loads on first use, so documents that need no
    OCR never pay for it. Model download and loading are reported through `on_engine`."""

    def __init__(self, backend: str = "auto", device: str | None = None, on_engine: EngineEvent | None = None):
        self.backend_name = pick_backend(backend)
        self.device = device
        self.backend = None
        self.on_engine = on_engine or (lambda state, details: None)
        self.load_seconds = 0.0  # time spent downloading and loading the model, for callers' timings

    def _load(self) -> None:
        if self.backend is not None:
            return
        start = time.perf_counter()
        try:
            if self.backend_name == "mlx":
                from . import backend_mlx as module
            else:
                from . import backend_torch as module

            def downloading(done: int, total: int):
                self.on_engine("downloading", {"done": done, "total": total})

            path = ensure_weights(module.MODEL_ID, module.MODEL_REVISION, module.IGNORE_PATTERNS, downloading)
            self.on_engine("loading", {})
            if self.backend_name == "mlx":
                self.backend = module.MLXBackend(path)
            else:
                self.backend = module.TorchBackend(path, device=self.device)
            self.on_engine("ready", {"backend": self.backend.name})
        finally:
            self.load_seconds += time.perf_counter() - start

    def _ocr_pages(
        self, page_images: dict[int, Path], images_dir: Path, stem: str, pages_per_pass: int, on_progress: Progress
    ) -> dict[int, str]:
        """OCR the given pages (index → PNG) and return Markdown keyed by page index."""
        self._load()
        order = sorted(page_images)
        results: dict[int, str] = {}
        for first in range(0, len(order), pages_per_pass):
            chunk = order[first : first + pages_per_pass]
            on_progress(f"OCR page {chunk[0] + 1}" if len(chunk) == 1 else f"OCR pages {chunk[0] + 1}-{chunk[-1] + 1}")
            if len(chunk) == 1:  # a lone page gets the higher-quality single-page mode
                outputs = [self.backend.parse_single(page_images[chunk[0]])]
            else:
                outputs = split_pages(self.backend.parse_multi([page_images[i] for i in chunk]))
            for i, raw in enumerate(outputs):
                page = chunk[min(i, len(chunk) - 1)]  # extra outputs are appended to the last page
                body = clean_page(raw, page_images[page] if i < len(chunk) else None, images_dir, f"{stem}_p{page + 1}")
                results[page] = f"{results[page]}\n\n{body}" if page in results else body
        return results

    def convert(
        self,
        path: str | Path,
        out_dir: str | Path,
        pages_per_pass: int = 8,
        dpi: int = 300,
        force_ocr: bool = False,
        on_progress: Progress = lambda message: None,
    ) -> Conversion:
        """Convert one file to `out_dir/<name>.md` (figures in `out_dir/images/`).

        `force_ocr` sends every page of a PDF through the model, even pages with a text layer
        (better for formulas, for example).
        """
        path, out_dir = Path(path), Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        images_dir = out_dir / "images"
        md_path = out_dir / f"{path.stem}.md"

        if path.suffix.lower() in DIRECT_EXTS:
            on_progress("Converting")
            markdown = direct_to_markdown(path, images_dir)
            result = Conversion(md_path, pages=1, text_pages=1, ocr_pages=0)
        else:
            markdown, result = self._convert_pages(path, md_path, images_dir, pages_per_pass, dpi, force_ocr, on_progress)

        md_path.write_text(markdown.strip() + "\n", encoding="utf-8")
        if images_dir.exists() and not any(images_dir.iterdir()):
            images_dir.rmdir()
        return result

    def _convert_pages(self, path, md_path, images_dir, pages_per_pass, dpi, force_ocr, on_progress):
        with tempfile.TemporaryDirectory(prefix="svitlyachok_") as tmp:
            work_dir = Path(tmp)
            doc_path = as_document(path, work_dir)
            on_progress("Reading pages")
            if doc_path is None:
                page_md: dict[int, str] = {}
                page_images = image_frames(path, work_dir)
                page_count = len(page_images)
            else:
                with pymupdf.open(doc_path) as doc:
                    page_count = doc.page_count
                    page_md = {} if force_ocr else markdown_from_text_layer(doc, images_dir, path.stem, on_progress)
                    to_ocr = [i for i in range(page_count) if i not in page_md]
                    page_images = render_pages(doc, to_ocr, work_dir, dpi)
            text_pages = len(page_md)
            if page_images:
                page_md |= self._ocr_pages(page_images, images_dir, path.stem, pages_per_pass, on_progress)

        if page_count == 1:
            markdown = page_md.get(0, "")
        else:
            markdown = "\n\n".join(f"<!-- page {i + 1} -->\n\n{page_md[i]}" for i in sorted(page_md))
        # The model labels the document title and section headings alike; promote the first one.
        if not re.search(r"^# ", markdown, flags=re.M):
            markdown = re.sub(r"^## ", "# ", markdown, count=1, flags=re.M)
        return markdown, Conversion(md_path, pages=page_count, text_pages=text_pages, ocr_pages=len(page_images))
