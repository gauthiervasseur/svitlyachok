"""Download the macOS 14 builds of mlx and mlx-metal, so the app runs on macOS 14 and newer.

pip picks the build for the machine it runs on (e.g. macOS 26), which older Macs cannot load.
Usage: python packaging/mlx_wheels.py <dest-dir>   → prints the wheel paths to install.
"""

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

PACKAGES = {"mlx": "0.32.4", "mlx-metal": "0.32.4"}  # keep in sync with requirements-mac.txt
TAG = "macosx_14_0_arm64"
PYTHON_TAGS = ("cp312-cp312", "py3-none")


def main(dest: Path):
    dest.mkdir(parents=True, exist_ok=True)
    for name, version in PACKAGES.items():
        with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json") as response:
            files = json.load(response)["urls"]
        wheel = next(
            f for f in files if f["filename"].endswith(f"{TAG}.whl") and any(t in f["filename"] for t in PYTHON_TAGS)
        )
        target = dest / wheel["filename"]
        with urllib.request.urlopen(wheel["url"]) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != wheel["digests"]["sha256"]:
            raise SystemExit(f"checksum mismatch for {wheel['filename']}")
        target.write_bytes(data)
        print(target)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
