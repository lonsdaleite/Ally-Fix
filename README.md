# Ally Fix

A [Decky Loader](https://decky.xyz) plugin with one-click fixes for the **ROG Xbox Ally X** on SteamOS.
Every fix is a single toggle; **Fix all** at the top turns them all on. Everything runs inside the
plugin process — no systemd units, udev rules or keep-lists are installed. The only file written
outside the plugin directory is the InputPlumber override used by the Gyro Fix; the rumble packet
filter is a HID-BPF program that exists in the kernel only while the plugin runs.

| Fix | What it does |
|---|---|
| **CPU Boost Fix** | Disables CPU boost (`cpufreq/boost=0`) and keeps the 2 GHz frequency cap applied. On this device every charger plug/unplug makes the firmware drop the cap on all cores even with boost off; the plugin re-sends the cap on all 16 cpufreq policies and watches the cores for 30 s, kicking again if they go over the cap (the slip re-occurs ~10 s after unplugging). Settings: *Refresh cap on charger events* (on by default, reset to on whenever the fix is enabled), *Refresh cap now*. |
| **Vibration Fix** | Sets grip-motor vibration intensity to **50 %** per motor. Scale 0–100, firmware default 100/100. Sent straight to the controller (the same MCU command the kernel driver uses, as a feature report on the config interface) and confirmed through the controller's command echo; the kernel's `vibration_intensity` sysfs attribute gets a mirror copy (it still rejects values above 64, in which case the mirror is capped). The controller resets during sleep, so after every resume the settings are re-sent as a short series, and again when the controller re-enumerates (InputPlumber restart). Settings: link/unlink motors, per-motor sliders (reset to 50/50 whenever the fix is enabled), test rumble. Grip motors only. The card also hosts an **Enhanced Vibration** toggle — the "Xbox-recommended waveform" option from Armoury Crate, sent as a single MCU command. The controller keeps the flag across reboots and OS switches but loses it in sleep, so an enabled flag is re-sent after resume and on plugin start (a disabled one is never pushed, so a value set from Windows is left alone); the toggle is independent of the fix, untouched by *Fix all*, available on the Xbox Ally / Ally X only, and turned off when the plugin is uninstalled. While it is on, the plugin also caps game rumble at the controller's full scale: the SteamOS driver sends full-strength rumble as magnitude 127 where the controller expects 0–100, which under Enhanced Vibration makes the motors rattle instead of vibrating (Windows never sends more than 100). The cap is a small HID-BPF program attached to the driver's outgoing rumble packets, so it covers every game and Steam Input; if the kernel refuses to load it, the panel shows the reason under the toggle and rumble stays as it was. **Mirror to triggers** (Xbox Ally X only, the model with impulse triggers) uses the same packet filter to copy grip rumble onto the triggers at the same strength (left grip → LT, right grip → RT), which the SteamOS driver otherwise never drives. Nothing is stored in the controller for it. |
| **Fan Noise Fix** | Occasionally after resume both fans get stuck at maximum. The fix pins the fan curve (`pwm*_enable=1`), which brings the EC back. It does **not** invent a curve: for each thermal profile it pins the curve that profile already uses (the factory one, loaded via `pwm_enable=3`), remembers it per profile, and re-pins within 5 s after Steam switches profiles (the kernel resets `pwm_enable` on every switch). If another tool writes a curve while pinned, that curve is adopted. *Restore factory curve for this profile* discards an adopted curve. Failsafe: fans above 6000 rpm while the CPU is below 65 °C trigger a re-pin. |
| **Gyro Fix** | Steam Input reads the gyro axes wrong for the product id InputPlumber's `deck-uhid` target emulates for the Ally: it treats the controller as a handheld and tilts the IMU frame, and its two gyro code paths (the modern gyro-to-joystick/mouse modes and the legacy `Camera` action used by Valve's Source layouts — Portal 2, Half-Life 2) disagree on how. The fix writes `/etc/inputplumber/devices.d/50-rog_xbox_ally.yaml`, generated from the installed stock config, then restarts InputPlumber. Three modes in *Settings*: **Simple** (default) — mount-matrix `y` row negated; gyro right in regular games, Yaw and Roll stay swapped in Source games. **Complex** — `gyro_force_handheld_orientation 2` in Steam's `steam_dev.cfg` plus `y`/`z` rows swapped; gyro right everywhere. Steam reads that file only at start-up, so every change into or out of this mode first asks for confirmation and, once confirmed, applies the change and restarts Steam; declining leaves everything as it was. **Deck Emulation** — the composite device is renamed so InputPlumber emulates the generic Steam Controller id with the stock matrix; gyro right everywhere, but Steam sees a different controller and layouts saved for the ROG Ally no longer apply. *Fix all* keeps the selected mode and, when that mode needs a Steam restart, asks whether to restart or to skip the Gyro Fix. The override is stamped with the stock file's hash: after an InputPlumber update it shows *Needs update* and is regenerated automatically. Works only with the `deck-uhid` target (SteamOS selects it itself); a DualSense (`ds5`) target gets inverted yaw (Simple) or swapped axes (Complex) while the fix is on. |

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

Updates: the *Updates* section at the bottom of the panel checks GitHub Releases and installs a newer
version in place (Decky restarts afterwards). Re-running the install command works too.

## Uninstallation

Removing the plugin from Decky reverts every enabled fix and switches Enhanced Vibration off. If
that did not happen (the plugin was disabled or broken at the time), this removes the plugin,
reverts the fixes, switches Enhanced Vibration off, deletes the InputPlumber override and drops
the Gyro Fix line from `steam_dev.cfg` (the last three are the changes that survive a reboot):

```
curl -fsSL https://raw.githubusercontent.com/lonsdaleite/Ally-Fix/main/uninstall.sh | bash
```

Add `PURGE=1` before `bash` to also delete the plugin's settings and logs.

## How it works

- Background work is plain asyncio inside the plugin: a netlink uevent listener (charger and HID
  events), a suspend/resume detector (jump of `CLOCK_BOOTTIME − CLOCK_MONOTONIC`), and the fan
  watchdog. Steam client resume hooks are not used.
- Settings live in `~/homebrew/settings/Ally Fix/settings.json`; logs in `~/homebrew/logs/Ally Fix/`.
- Uninstalling the plugin through Decky reverts every enabled fix (boost on, vibration 100/100, fan
  curve back to auto, InputPlumber override and the `steam_dev.cfg` line removed, Enhanced Vibration off). This runs inside the plugin process, so it
  cannot happen if the plugin was disabled or not running at the time — use `uninstall.sh` then.

## Building

The frontend is built with the same container image the Decky Store uses:

```
podman run --rm --userns=keep-id -e RELEASE_TYPE=production \
  -v "$PWD:/plugin" -v "$PWD/out:/out" ghcr.io/steamdeckhomebrew/builder:latest
```

(`docker run --rm --user $(id -u):$(id -g) …` works as well.) For local development
`sudo bash scripts/dev-install.sh` copies the build into `~/homebrew/plugins` and restarts Decky.

The rumble packet filter (`bpf/ally_ff.bpf.c`) is shipped prebuilt as `bin/ally_ff.bpf.o`; it is
CO-RE, so one build works across kernels as long as they have BTF and `CONFIG_HID_BPF` (SteamOS
does). Rebuild it with `bpf/build.sh` (podman; uses the running kernel's BTF for `vmlinux.h`) and
commit the result. At runtime it is loaded through the system `libbpf.so.1`, nothing is compiled on
the device.

## License

MIT
