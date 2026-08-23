"""Vibration Fix: lower grip-motor vibration intensity and keep it applied.

The MCU takes intensity as a percentage 0..100 per motor (firmware default
100/100). We write the hid_asus_ally sysfs attribute `vibration_intensity`;
its store handler currently rejects anything above 64 with EINVAL (a
decimal/hex slip: the driver's own init value is 0x64 = 100). On that error we
fall back to writing 64 into sysfs (so the kernel's copy stays as close as it
can get) and then send the real value ourselves with the same MCU command the
driver uses, as a feature report on the config interface's hidraw node. sysfs
cannot report a value above 64, so after a fallback we remember what we sent
and forget it whenever the device re-enumerates (suspend/resume, driver
rebind), at which point the MCU is back at its default and we re-apply.
"""

from __future__ import annotations

import asyncio
import errno
import fcntl
import glob
import os
import struct
import time
from typing import Any

import decky

from .. import settings as cfg
from ..base import Fix, cancel_task
from ..sysfs import read_str, write_str

DRIVER_GLOB = "/sys/module/hid_asus_ally/drivers/hid:asus_rog_ally/*/vibration_intensity"
HIDRAW_GLOB = "/sys/class/hidraw/*/device/vibration_intensity"
MAX_INTENSITY = 100
SYSFS_MAX = 64  # kernel store handler limit
FACTORY = (MAX_INTENSITY, MAX_INTENSITY)
DEFAULT = (50, 50)
REBIND_RETRIES = 5
REBIND_RETRY_DELAY_S = 1.0

# evdev force feedback (for the test rumble)
_EVIOCGBIT_FF = 0x80204535
_EVIOCSFF = 0x40304580
_EVIOCRMFF = 0x40044581
# MCU config command, same as hid-asus-ally.h: report 0x5A, xpad config class 0xD1,
# xpad_cmd_set_vibe_intensity, xpad_cmd_len_vibe_intensity, then LEFT RIGHT.
_FEATURE_REPORT_ID = 0x5A
_XPAD_CONFIG = 0xD1
_XPAD_CMD_SET_VIBE_INTENSITY = 0x06
_XPAD_CMD_LEN_VIBE_INTENSITY = 0x02
# "Use Xbox-recommended vibration waveform" (Armoury Crate's Enhanced Vibration),
# boolean. The MCU stores the flag itself and it survives reboots and OS switches.
_XPAD_CMD_SET_ENHANCED = 0x1F
_FEATURE_REPORT_SIZE = 64
_HIDIOCSFEATURE = 0xC0000000 | (_FEATURE_REPORT_SIZE << 16) | (ord("H") << 8) | 0x06
_EV_FF = 0x15
_FF_RUMBLE = 0x50


def _clamp(v: Any, lo: int = 0, hi: int = MAX_INTENSITY) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return lo


def _sysfs_path() -> str | None:
    for pattern in (DRIVER_GLOB, HIDRAW_GLOB):
        found = sorted(glob.glob(pattern))
        if found:
            return found[0]
    return None


def _hidraw_node() -> str | None:
    """/dev/hidrawN of the config interface that owns the sysfs attribute."""
    attr = _sysfs_path()
    if attr is None:
        return None
    for node in sorted(glob.glob(os.path.join(os.path.dirname(attr), "hidraw", "hidraw*"))):
        return "/dev/" + os.path.basename(node)
    return None


def _find_ff_device() -> str | None:
    """Pick an evdev node with FF_RUMBLE, preferring the ASUS/Ally gamepad."""
    candidates: list[tuple[int, str]] = []
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        except OSError:
            continue
        try:
            buf = bytearray(32)
            fcntl.ioctl(fd, _EVIOCGBIT_FF, buf)
            if not (buf[_FF_RUMBLE // 8] >> (_FF_RUMBLE % 8)) & 1:
                continue
        except OSError:
            continue
        finally:
            os.close(fd)
        name = read_str(f"/sys/class/input/{os.path.basename(path)}/device/name", "") or ""
        score = 2 if ("ASUS" in name.upper() or "ALLY" in name.upper()) else 1
        candidates.append((score, path))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


class VibrationFix(Fix):
    id = "vibration"
    title = "Vibration Fix"

    def __init__(self) -> None:
        super().__init__()
        self._uevent = None  # set by plugin
        self._rebind_task: asyncio.Task | None = None
        self._hw: tuple[int, int] | None = None  # value sent via hidraw fallback (sysfs can't show it)

    # --- options -------------------------------------------------------
    @property
    def intensity(self) -> tuple[int, int]:
        return _clamp(cfg.get(self.id, "left", DEFAULT[0])), _clamp(cfg.get(self.id, "right", DEFAULT[1]))

    @property
    def linked(self) -> bool:
        return bool(cfg.get(self.id, "linked", True))

    @property
    def enhanced(self) -> bool:
        return bool(cfg.get(self.id, "enhanced", False))

    async def set_enhanced(self, on: bool) -> None:
        """Independent of the intensity fix and of `enabled`; the MCU keeps the
        flag across reboots, so it is sent once on toggle and never re-applied."""
        self._send_feature(_XPAD_CMD_SET_ENHANCED, bytes([1 if on else 0]))
        cfg.update(self.id, {"enhanced": bool(on)})
        decky.logger.info("[vibration] enhanced vibration %s", "on" if on else "off")

    def set_options(self, opts: dict[str, Any]) -> None:
        values: dict[str, Any] = {}
        if "linked" in opts:
            values["linked"] = bool(opts["linked"])
        if "left" in opts:
            values["left"] = _clamp(opts["left"])
        if "right" in opts:
            values["right"] = _clamp(opts["right"])
        linked = values.get("linked", self.linked)
        if linked:
            if "left" in values:
                values["right"] = values["left"]
            elif "right" in values:
                values["left"] = values["right"]
        if values:
            cfg.update(self.id, values)

    # --- Fix interface ---------------------------------------------------
    def supported(self) -> tuple[bool, str]:
        if _sysfs_path() is None:
            return False, "hid_asus_ally driver not found"
        return True, ""

    def _read_hw(self) -> tuple[int, int] | None:
        if self._hw is not None:
            return self._hw
        # Fresh boot / re-enumeration: the driver's placeholder 100/100 matches the MCU default.
        path = _sysfs_path()
        if path is None:
            return None
        raw = read_str(path)
        if not raw:
            return None
        try:
            left, right = (int(x) for x in raw.split()[:2])
            return left, right
        except ValueError:
            return None

    def _write_hw(self, left: int, right: int) -> None:
        path = _sysfs_path()
        if path is None:
            raise OSError("vibration_intensity sysfs attribute not found")
        try:
            write_str(path, f"{left} {right}\n")
        except OSError as exc:
            if exc.errno != errno.EINVAL or (left <= SYSFS_MAX and right <= SYSFS_MAX):
                raise
        else:
            self._hw = None  # sysfs is authoritative again
            return
        # Kernel refused (>64): keep its copy as close as it allows, then send the real value ourselves.
        write_str(path, f"{min(left, SYSFS_MAX)} {min(right, SYSFS_MAX)}\n")
        self._write_mcu(left, right)
        self._hw = (left, right)

    @staticmethod
    def _write_mcu(left: int, right: int) -> None:
        VibrationFix._send_feature(_XPAD_CMD_SET_VIBE_INTENSITY, bytes([left, right]))

    @staticmethod
    def _send_feature(cmd: int, data: bytes) -> None:
        """Send `5A D1 <cmd> <len> <data…>` as a feature report on the config interface."""
        node = _hidraw_node()
        if node is None:
            raise OSError("hidraw node for the config interface not found")
        buf = bytearray(_FEATURE_REPORT_SIZE)
        buf[: 4 + len(data)] = bytes([_FEATURE_REPORT_ID, _XPAD_CONFIG, cmd, len(data)]) + data
        fd = os.open(node, os.O_RDWR)
        try:
            fcntl.ioctl(fd, _HIDIOCSFEATURE, buf)
        finally:
            os.close(fd)

    def is_applied(self) -> bool:
        return self._read_hw() == self.intensity

    async def apply(self) -> None:
        left, right = self.intensity
        self._write_hw(left, right)
        decky.logger.info("[vibration] intensity set to %d/%d", left, right)

    async def revert(self) -> None:
        self._write_hw(*FACTORY)
        decky.logger.info("[vibration] intensity restored to factory %d/%d", *FACTORY)

    def details(self) -> dict[str, Any]:
        hw = self._read_hw()
        left, right = self.intensity
        return {
            "left": left,
            "right": right,
            "linked": self.linked,
            "enhanced": self.enhanced,
            "hw_left": hw[0] if hw else None,
            "hw_right": hw[1] if hw else None,
            "sysfs": _sysfs_path(),
        }

    async def on_resume(self) -> None:
        self._hw = None
        self._schedule_rebind("resume")

    async def start_background(self) -> None:
        if self._uevent is not None:
            self._uevent.subscribe("hid", self._on_hid_event)

    async def stop_background(self) -> None:
        if self._uevent is not None:
            self._uevent.unsubscribe("hid", self._on_hid_event)
        await cancel_task(self._rebind_task)
        self._rebind_task = None

    async def _on_hid_event(self, event: dict[str, str]) -> None:
        if not self.enabled:
            return
        if event.get("ACTION") not in ("add", "bind"):
            return
        if "asus" not in event.get("DRIVER", "").lower() and "0B05" not in event.get("HID_ID", "").upper():
            return
        self._hw = None
        self._schedule_rebind(f"hid {event.get('ACTION')}")

    def _schedule_rebind(self, reason: str) -> None:
        if self._rebind_task is not None and not self._rebind_task.done():
            return
        self._rebind_task = asyncio.get_running_loop().create_task(self._rebind(reason))

    async def _rebind(self, reason: str) -> None:
        for attempt in range(1, REBIND_RETRIES + 1):
            await asyncio.sleep(REBIND_RETRY_DELAY_S)
            if not self.enabled:
                return
            try:
                await self.apply()
                self.last_error = ""
                decky.logger.info("[vibration] re-applied after %s (attempt %d)", reason, attempt)
                await self.notify()
                return
            except OSError as exc:
                decky.logger.warning("[vibration] re-apply attempt %d failed: %s", attempt, exc)
        self.last_error = "could not re-apply vibration intensity after device re-enumeration"
        await self.notify()

    # --- test rumble -----------------------------------------------------
    async def test(self, duration_ms: int = 500) -> None:
        """Fire a short FF_RUMBLE so the user can feel the current intensity."""
        # 0xC800 goes out on the wire as magnitude 100 (/512) — the MCU's full scale,
        # so what the user feels is the intensity scaling alone. 0xFFFF would be sent
        # as 127, out of range, and buzzes audibly with Enhanced Vibration on.
        duration = max(100, min(2000, int(duration_ms)))
        strong = weak = 100 * 512
        ff_path = _find_ff_device()
        if ff_path is None:
            raise OSError("no rumble-capable input device found")
        fd = os.open(ff_path, os.O_RDWR)
        try:
            # struct ff_effect (48 bytes) for FF_RUMBLE: type, id(-1 → kernel assigns),
            # direction, trigger{button, interval}, replay{length, delay}, pad,
            # rumble{strong, weak}, union padding.
            effect = bytearray(struct.pack("<HhHHHHHxxHH28x", _FF_RUMBLE, -1, 0, 0, 0, duration, 0, strong, weak))
            fcntl.ioctl(fd, _EVIOCSFF, effect)
            effect_id = struct.unpack_from("<h", effect, 2)[0]

            def ev(value: int) -> bytes:
                t = time.time()
                return struct.pack("<qqHHi", int(t), int((t % 1) * 1e6), _EV_FF, effect_id, value)

            os.write(fd, ev(1))
            await asyncio.sleep(duration / 1000.0)
            os.write(fd, ev(0))
            # EVIOCRMFF takes the id by value, not a pointer
            fcntl.ioctl(fd, _EVIOCRMFF, effect_id)
        finally:
            os.close(fd)
        decky.logger.info("[vibration] test rumble %dms via %s (sysfs %s)", duration, ff_path, self._read_hw())
