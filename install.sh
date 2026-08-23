#!/bin/bash
# Ally Fix installer: downloads the latest GitHub release and installs it into Decky Loader.
#   curl -fsSL https://raw.githubusercontent.com/lonsdaleite/Ally-Fix/main/install.sh | bash
# Optional: VERSION=v1.0.0 to pin a release.
set -euo pipefail

REPO="lonsdaleite/Ally-Fix"
PLUGIN_NAME="Ally Fix"
HOMEBREW="${HOMEBREW_DIR:-$HOME/homebrew}"
DEST="$HOMEBREW/plugins/$PLUGIN_NAME"

if [ "$(id -u)" = 0 ]; then
  echo "Run this script as the regular user (it will ask for sudo)." >&2
  exit 1
fi
[ -d "$HOMEBREW/plugins" ] || { echo "Decky Loader not found at $HOMEBREW — install Decky first." >&2; exit 1; }
for bin in curl python3 unzip sudo; do
  command -v "$bin" >/dev/null || { echo "missing: $bin" >&2; exit 1; }
done

if [ -n "${VERSION:-}" ]; then
  api="https://api.github.com/repos/$REPO/releases/tags/$VERSION"
else
  api="https://api.github.com/repos/$REPO/releases/latest"
fi
echo "Looking up release ($api)…"
url="$(curl -fsSL "$api" | python3 -c '
import json, sys
rel = json.load(sys.stdin)
assets = [a["browser_download_url"] for a in rel.get("assets", []) if a["name"].endswith(".zip")]
print(assets[0] if assets else "")
')"
[ -n "$url" ] || { echo "No zip asset found in the release." >&2; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
echo "Downloading $url"
curl -fsSL "$url" -o "$tmp/plugin.zip"
unzip -q "$tmp/plugin.zip" -d "$tmp/unpacked"
src="$(find "$tmp/unpacked" -maxdepth 2 -name plugin.json -printf '%h\n' | head -1)"
[ -n "$src" ] || { echo "plugin.json not found in the archive." >&2; exit 1; }

echo "Installing to $DEST (sudo required)…"
sudo bash -c "
  systemctl stop plugin_loader
  rm -rf '$DEST'
  cp -r '$src' '$DEST'
  chown -R root:root '$DEST'
  systemctl start plugin_loader
"
echo "Done. Open the Quick Access Menu → Decky → Ally Fix."
