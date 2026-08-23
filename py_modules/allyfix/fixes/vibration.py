"""Vibration Fix: lower grip-motor vibration intensity and keep it applied.

The hid_asus_ally driver exposes `vibration_intensity` ("LEFT RIGHT"). The
store handler accepts 0..64 (checked against the 6.16 module); the driver's
initial readback is a placeholder 100/100 that was never sent to the MCU, so a
fresh boot reports 100/100 while the motors run at the firmware default
(full strength). The value is lost whenever the device re-enumerates
(suspend/resume), so we re-write it when the HID device (re)binds and after
resume. Trigger (impulse) vibration is a separate hardware path the kernel
does not expose.
"""

from __future__ import annotations

import asyncio
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
MAX_INTENSITY = 64
FACTORY = (MAX_INTENSITY, MAX_INTENSITY)
DEFAULT = (50, 50)
REBIND_RETRIES = 5
REBIND_RETRY_DELAY_S = 1.0

# evdev force feedback (for the test rumble)
_EVIOCGBIT_FF = 0x80204535
_EVIOCSFF = 0x40304580
_EVIOCRMFF = 0x40044581
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

    # --- options -------------------------------------------------------
    @property
    def intensity(self) -> tuple[int, int]:
        return _clamp(cfg.get(self.id, "left", DEFAULT[0])), _clamp(cfg.get(self.id, "right", DEFAULT[1]))

    @property
    def linked(self) -> bool:
        return bool(cfg.get(self.id, "linked", True))

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
        write_str(path, f"{left} {right}\n")

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
            "hw_left": hw[0] if hw else None,
            "hw_right": hw[1] if hw else None,
            "sysfs": _sysfs_path(),
        }

    async def on_resume(self) -> None:
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
        # Full FF magnitude on both motors: what the user feels is the sysfs scaling alone.
        duration = max(100, min(2000, int(duration_ms)))
        strong = weak = 0xFFFF
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
