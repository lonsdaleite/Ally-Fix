#!/bin/bash
# Install the built plugin into the local Decky Loader (for development).
# Usage: sudo bash scripts/dev-install.sh   (run `pnpm run build` / the builder image first)
set -euo pipefail
SRC="$(cd "$(dirname "$0")/.." && pwd)"
NAME="$(python3 -c 'import json;print(json.load(open("'"$SRC"'/plugin.json"))["name"])')"
DEST="/home/deck/homebrew/plugins/$NAME"
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
[ -f "$SRC/dist/index.js" ] || { echo "dist/index.js missing — build first"; exit 1; }
systemctl stop plugin_loader
rm -rf "$DEST"
mkdir -p "$DEST"
cp -r "$SRC/dist" "$SRC/py_modules" "$SRC/main.py" "$SRC/plugin.json" "$SRC/package.json" "$SRC/LICENSE" "$SRC/README.md" "$DEST/"
find "$DEST" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
chown -R root:root "$DEST"
systemctl start plugin_loader
echo "installed to $DEST"
