# Ally Fix

A [Decky Loader](https://decky.xyz) plugin with one-click fixes for the **ROG Xbox Ally X** on SteamOS.
Every fix is a single toggle; **Fix all** at the top turns them all on. Everything runs inside the
plugin process — no systemd units, udev rules or keep-lists are installed. The only file written
outside the plugin directory is the InputPlumber override used by the Gyro Fix.

| Fix | What it does |
|---|---|
| **CPU Boost Fix** | Disables CPU boost (`cpufreq/boost=0`) and keeps the 2 GHz frequency cap applied. On this device every charger plug/unplug makes the firmware drop the cap on all cores even with boost off; the plugin re-sends the cap on all 16 cpufreq policies and watches the cores for 30 s, kicking again if they go over the cap (the slip re-occurs ~10 s after unplugging). Settings: *Refresh cap on charger events* (on by default, reset to on whenever the fix is enabled), *Refresh cap now*. |
| **Vibration Fix** | Sets grip-motor vibration intensity to **50/50** (driver scale 0–64; 64 is the firmware default — the `100 100` shown after boot is a driver placeholder that was never sent to the controller). Re-applied when the controller re-enumerates (sleep/resume, InputPlumber restart). Settings: link/unlink motors, per-motor sliders (reset to 50/50 whenever the fix is enabled), test rumble. Trigger (impulse) vibration is a separate hardware path the kernel driver does not expose. |
| **Fan Noise Fix** | Occasionally after resume both fans get stuck at maximum. The fix pins the fan curve (`pwm*_enable=1`), which brings the EC back. It does **not** invent a curve: for each thermal profile it pins the curve that profile already uses (the factory one, loaded via `pwm_enable=3`), remembers it per profile, and re-pins within 5 s after Steam switches profiles (the kernel resets `pwm_enable` on every switch). If another tool writes a curve while pinned, that curve is adopted. *Restore factory curve for this profile* discards an adopted curve. Failsafe: fans above 6000 rpm while the CPU is below 65 °C trigger a re-pin. |
| **Gyro Fix** | Steam Input inverts gyro yaw for the product id InputPlumber's `deck-uhid` target emulates for the Ally. The fix writes `/etc/inputplumber/devices.d/50-rog_xbox_ally.yaml`, generated from the installed stock config with one line changed (the IMU mount-matrix `y` row negated), then restarts InputPlumber. The override is stamped with the stock file's hash: after an InputPlumber update it shows *Needs update* and is regenerated automatically. Works only with the `deck-uhid` target (SteamOS selects it itself); yaw through DualSense (`ds5`) targets becomes inverted while the fix is on. Turn it off if InputPlumber ships IMU normalization upstream. |

Verified on the ROG Xbox Ally X only (board `RC73XA`, SteamOS, kernel 6.16). The ROG Xbox Ally
(`RC73YA`) shares the drivers and the InputPlumber config and is expected to work, but has not been
tested. On other devices *Fix all* is disabled; individual fixes whose hardware interfaces are
missing show *Not supported* and cannot be enabled (the Gyro Fix is limited to the two boards above,
the CPU Boost Fix to ASUS devices).

## Requirements

- Decky Loader 3.2.0 or newer
- SteamOS with the `hid_asus_ally` and `asus-wmi` drivers (stock on the Ally X), InputPlumber for the Gyro Fix

## Installation

From the Decky Store, or with one command (downloads the latest GitHub release and asks for sudo):

```
curl -fsSL https://raw.githubusercontent.com/lonsdaleite/Ally-Fix/main/install.sh | bash
```

Or download the zip from the latest release and use
*Decky → Settings → Developer → Install Plugin from ZIP*.

## Uninstallation

Removing the plugin from Decky reverts every enabled fix. If that did not happen (the plugin was
disabled or broken at the time), this removes the plugin, reverts the fixes and deletes the
InputPlumber override — the only change that survives a reboot:

```
curl -fsSL https://raw.githubusercontent.com/lonsdaleite/Ally-Fix/main/uninstall.sh | bash
```

Add `PURGE=1` before `bash` to also delete the plugin's settings and logs.

## How it works

- Background work is plain asyncio inside the plugin: a netlink uevent listener (charger and HID
  events), a suspend/resume detector (jump of `CLOCK_BOOTTIME − CLOCK_MONOTONIC`), and the fan
  watchdog. Steam client resume hooks are not used.
- Settings live in `~/homebrew/settings/Ally Fix/settings.json`; logs in `~/homebrew/logs/Ally Fix/`.
- Uninstalling the plugin through Decky reverts every enabled fix (boost on, vibration 64/64, fan
  curve back to auto, InputPlumber override removed). This runs inside the plugin process, so it
  cannot happen if the plugin was disabled or not running at the time — use `uninstall.sh` then.

## Building

The frontend is built with the same container image the Decky Store uses:

```
podman run --rm --userns=keep-id -e RELEASE_TYPE=production \
  -v "$PWD:/plugin" -v "$PWD/out:/out" ghcr.io/steamdeckhomebrew/builder:latest
```

(`docker run --rm --user $(id -u):$(id -g) …` works as well.) For local development
`sudo bash scripts/dev-install.sh` copies the build into `~/homebrew/plugins` and restarts Decky.

## License

MIT
