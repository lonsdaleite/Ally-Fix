#!/bin/bash
# Ally Fix uninstaller: removes the plugin and reverts every fix, including the InputPlumber
# override the Gyro Fix writes to /etc, its line in Steam's steam_dev.cfg, and the Steam-client
# shim plus service drop-in of the Gamepad Layout Fix (the things that survive a reboot).
#   curl -fsSL https://raw.githubusercontent.com/lonsdaleite/Ally-Fix/main/uninstall.sh | bash
# Optional: PURGE=1 also removes the plugin's settings and logs.
set -euo pipefail

PLUGIN_NAME="Ally Fix"
HOMEBREW="${HOMEBREW_DIR:-$HOME/homebrew}"
OVERRIDE="/etc/inputplumber/devices.d/50-rog_xbox_ally.yaml"
MARKER="managed-by: ally-fix"
STEAM_CFG="$HOME/.local/share/Steam/steam_dev.cfg"
LAYOUT_DROPIN="$HOME/.config/systemd/user/steam-launcher.service.d/zz-ally-fix-gamepad-layout.conf"
LAYOUT_LIB_DIR="$HOME/.local/lib/ally-fix"
SHIM_LOG="$HOME/.local/state/ally-fix-allycaps.log"

if [ "$(id -u)" = 0 ]; then
  echo "Run this script as the regular user (it will ask for sudo)." >&2
  exit 1
fi
command -v sudo >/dev/null || { echo "missing: sudo" >&2; exit 1; }

echo "Removing $PLUGIN_NAME and reverting fixes (sudo required)…"
# Gyro Fix (Complex mode) -> drop the Steam ConVar line, putting back a value the plugin had
# replaced (settings.json remembers it); Steam re-reads the file on its next start
if [ -f "$STEAM_CFG" ] && grep -qE '^[[:space:]]*gyro_force_handheld_orientation[[:space:]]+2[[:space:]]*$' "$STEAM_CFG"; then
  prev="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("gyro",{}).get("steam_cfg_prev",""))' "$HOMEBREW/settings/$PLUGIN_NAME/settings.json" 2>/dev/null || true)"
  if [ -n "$prev" ]; then
    sed -i -E "0,/^[[:space:]]*gyro_force_handheld_orientation[[:space:]]+2[[:space:]]*\$/s//$prev/" "$STEAM_CFG"
  fi
  sed -i -E '/^[[:space:]]*gyro_force_handheld_orientation[[:space:]]+2[[:space:]]*$/d' "$STEAM_CFG"
  [ -s "$STEAM_CFG" ] || rm -f "$STEAM_CFG"
  echo "  - steam_dev.cfg gyro line removed (takes effect after Steam restarts)"
fi
# Gamepad Layout Fix -> drop the LD_PRELOAD drop-in and the shim (both owned by the user)
if [ -f "$LAYOUT_DROPIN" ] || [ -d "$LAYOUT_LIB_DIR" ]; then
  rm -f "$LAYOUT_DROPIN"
  rm -rf "$LAYOUT_LIB_DIR"
  systemctl --user daemon-reload 2>/dev/null || true
  echo "  - Steam-client shim and service drop-in removed (takes effect after Steam restarts)"
fi
sudo env PURGE="${PURGE:-0}" HOMEBREW="$HOMEBREW" SHIM_LOG="$SHIM_LOG" OVERRIDE="$OVERRIDE" MARKER="$MARKER" PLUGIN_NAME="$PLUGIN_NAME" bash <<'ROOT'
set -u
plugin_dir="$HOMEBREW/plugins/$PLUGIN_NAME"
if [ -d "$plugin_dir" ]; then
  systemctl stop plugin_loader
  rm -rf "$plugin_dir"
  echo "  - plugin removed"
fi

# CPU Boost Fix -> boost back on
if [ -w /sys/devices/system/cpu/cpufreq/boost ]; then
  echo 1 > /sys/devices/system/cpu/cpufreq/boost && echo "  - CPU boost enabled"
  for d in /sys/devices/system/cpu/cpu[0-9]*/cpufreq; do
    cat "$d/cpuinfo_max_freq" > "$d/scaling_max_freq" 2>/dev/null || true
  done
  echo "  - frequency cap lifted"
fi
# Vibration Fix -> firmware default
for f in /sys/module/hid_asus_ally/drivers/hid:asus_rog_ally/*/vibration_intensity; do
  [ -w "$f" ] && echo "64 64" > "$f" 2>/dev/null && echo "  - vibration intensity 64/64"
done
# Enhanced Vibration -> off (the flag persists inside the controller's MCU;
# the command only exists on the ROG Xbox Ally / Ally X)
case "$(cat /sys/class/dmi/id/board_name 2>/dev/null)" in
  RC73XA|RC73YA)
    python3 - 2>/dev/null <<'PY' && echo "  - enhanced vibration off"
import fcntl, glob, os
attr = glob.glob("/sys/module/hid_asus_ally/drivers/hid:asus_rog_ally/*/vibration_intensity")[0]
node = sorted(glob.glob(os.path.join(os.path.dirname(attr), "hidraw", "hidraw*")))[0]
buf = bytearray(64)
buf[:5] = bytes([0x5A, 0xD1, 0x1F, 0x01, 0x00])
fd = os.open("/dev/" + os.path.basename(node), os.O_RDWR)
fcntl.ioctl(fd, 0xC0000000 | (64 << 16) | (ord("H") << 8) | 0x06, buf)
os.close(fd)
PY
    ;;
esac
# Fan Noise Fix -> factory auto mode
for d in /sys/class/hwmon/hwmon*; do
  if [ "$(cat "$d/name" 2>/dev/null)" = asus_custom_fan_curve ]; then
    echo 2 > "$d/pwm1_enable" 2>/dev/null; echo 2 > "$d/pwm2_enable" 2>/dev/null
    echo "  - fan curve back to factory auto"
  fi
done
# Gyro Fix -> remove the InputPlumber override
if [ -f "$OVERRIDE" ]; then
  if grep -q "$MARKER" "$OVERRIDE"; then
    rm -f "$OVERRIDE"
    systemctl restart inputplumber 2>/dev/null || true
    echo "  - InputPlumber override removed, inputplumber restarted"
  else
    echo "  ! $OVERRIDE exists but was not created by Ally Fix — left in place" >&2
  fi
fi

if [ "$PURGE" = 1 ]; then
  rm -rf "$HOMEBREW/settings/$PLUGIN_NAME" "$HOMEBREW/logs/$PLUGIN_NAME" "$SHIM_LOG"
  echo "  - settings and logs removed"
fi
systemctl start plugin_loader 2>/dev/null || true
ROOT
echo "Done."
