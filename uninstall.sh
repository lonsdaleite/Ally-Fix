#!/bin/bash
# Ally Fix uninstaller: removes the plugin and reverts every fix, including the InputPlumber
# override the Gyro Fix writes to /etc (the only thing that survives a reboot).
#   curl -fsSL https://raw.githubusercontent.com/lonsdaleite/Ally-Fix/main/uninstall.sh | bash
# Optional: PURGE=1 also removes the plugin's settings and logs.
set -euo pipefail

PLUGIN_NAME="Ally Fix"
HOMEBREW="${HOMEBREW_DIR:-$HOME/homebrew}"
OVERRIDE="/etc/inputplumber/devices.d/50-rog_xbox_ally.yaml"
MARKER="managed-by: ally-fix"

if [ "$(id -u)" = 0 ]; then
  echo "Run this script as the regular user (it will ask for sudo)." >&2
  exit 1
fi
command -v sudo >/dev/null || { echo "missing: sudo" >&2; exit 1; }

echo "Removing $PLUGIN_NAME and reverting fixes (sudo required)…"
sudo env PURGE="${PURGE:-0}" HOMEBREW="$HOMEBREW" OVERRIDE="$OVERRIDE" MARKER="$MARKER" PLUGIN_NAME="$PLUGIN_NAME" bash <<'ROOT'
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
  rm -rf "$HOMEBREW/settings/$PLUGIN_NAME" "$HOMEBREW/logs/$PLUGIN_NAME"
  echo "  - settings and logs removed"
fi
systemctl start plugin_loader 2>/dev/null || true
ROOT
echo "Done."
