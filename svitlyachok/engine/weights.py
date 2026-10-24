"""Model weights: downloaded once into the Hugging Face cache, reporting byte-level progress."""

from __future__ import annotations

import fnmatch
import threading
from pathlib import Path
from typing import Callable

from huggingface_hub import HfApi, constants, snapshot_download

ByteProgress = Callable[[int, int], None]  # (bytes done, bytes total)


def _blobs_dir(repo: str) -> Path:
    return Path(constants.HF_HUB_CACHE) / ("models--" + repo.replace("/", "--")) / "blobs"


def _dir_size(path: Path) -> int:
    try:
        return sum(f.stat().st_size for f in path.iterdir() if f.is_file())
    except FileNotFoundError:
        return 0


def ensure_weights(
    repo: str, revision: str, ignore_patterns: list[str] | None = None, on_progress: ByteProgress | None = None
) -> str:
    """Return the local snapshot folder, downloading whatever is missing first."""
    try:
        info = HfApi().model_info(repo, revision=revision, files_metadata=True)
    except Exception:  # offline: use the cache if the model was downloaded before
        try:
            return snapshot_download(repo, revision=revision, ignore_patterns=ignore_patterns, local_files_only=True)
        except Exception as e:
            raise RuntimeError("No internet connection, and the OCR model has not been downloaded yet.") from e

    wanted = [s for s in info.siblings if not any(fnmatch.fnmatch(s.rfilename, p) for p in ignore_patterns or [])]
    total = sum(s.size or 0 for s in wanted)
    blobs = _blobs_dir(repo)

    # snapshot_download has no byte-level callback, so run it in a thread and watch the cache grow.
    result: dict = {}

    def download():
        try:
            result["path"] = snapshot_download(repo, revision=revision, ignore_patterns=ignore_patterns)
        except Exception as e:
            result["error"] = e

    worker = threading.Thread(target=download, daemon=True)
    worker.start()
    while worker.is_alive():
        worker.join(0.5)
        if on_progress:
            on_progress(min(_dir_size(blobs), total), total)
    if "error" in result:
        raise result["error"]
    if on_progress:
        on_progress(total, total)
    return result["path"]
