"""PyInstaller entry point."""

import multiprocessing
import os
import sys
from pathlib import Path


def _give_windowed_app_a_console():
    """A windowed Windows app starts with sys.stdout/sys.stderr = None, and libraries that print
    (download progress bars, warnings) then crash. Send their output to console.log instead."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    folder = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Svitlyachok"
    folder.mkdir(parents=True, exist_ok=True)
    stream = open(folder / "console.log", "w", encoding="utf-8", errors="replace", buffering=1)
    sys.stdout = sys.stdout or stream
    sys.stderr = sys.stderr or stream


if __name__ == "__main__":
    multiprocessing.freeze_support()
    _give_windowed_app_a_console()
    from svitlyachok.app import main

    sys.exit(main())
