#!/usr/bin/env bash
# Builds Світлячок.app and Svitlyachok-macOS.dmg (Apple Silicon, macOS 14+).
# Run in an environment with requirements-mac.txt, the macOS 14 MLX wheels (packaging/mlx_wheels.py)
# and pyinstaller installed.   Usage: packaging/build-mac.sh [output-dir]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/build}"

pyinstaller "$ROOT/packaging/svitlyachok.spec" --noconfirm --distpath "$OUT/dist" --workpath "$OUT/work"

STAGE="$OUT/dmg"
rm -rf "$STAGE" && mkdir -p "$STAGE"
ditto "$OUT/dist/Svitlyachok.app" "$STAGE/Світлячок.app"
ln -s /Applications "$STAGE/Applications"
codesign --verify --deep --strict "$STAGE/Світлячок.app"
hdiutil create -volname "Світлячок" -srcfolder "$STAGE" -ov -format ULMO "$OUT/Svitlyachok-macOS.dmg"
echo "Built $OUT/Svitlyachok-macOS.dmg"
