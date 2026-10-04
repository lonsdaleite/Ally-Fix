"""Stick Light Fix: keep the joystick RGB rings off.

The rings are a multicolor LED class device of hid_asus_ally. Whenever the
driver initialises the controller it forces the MCU's base brightness to a
visible level (`5A BA C5 C4 02`), and the rings light up in the MCU's stored
colour (blue) until colours are sent. That happens at boot, and after every
resume: the kernel sets mcu_powersave=1 at boot, so the MCU loses power in
sleep and is re-initialised a few seconds after wake. The driver's own restore
goes out at resume time, before the MCU is back, and is lost.

The fix writes a static blue at brightness 0 when the plugin starts and when
the LED device (re)appears. After resume it repeats the write as a dense series
for a while, so the rings go dark again within a fraction of a second of the
MCU coming back; a short flash cannot be avoided without keeping the MCU
powered (mcu_powersave=0), which is left to the user. The LED class
`brightness` is the kernel's cached value, not the controller's: it reads 0 even
while the rings are lit, so the series is sent unconditionally.
"""

from __future__ import annotations

import asyncio
import glob
import os
from typing import Any

import decky

from ..base import Fix, cancel_task
from ..sysfs import dmi_vendor, read_int, read_str, write_str

LED_PATH = "/sys/class/leds/ally:rgb:joystick_rings"
LED_GLOB = "/sys/class/leds/*joystick_rings*"
ZONES = 4
COLOR = 0x0000FF  # blue, packed 0xRRGGBB per zone
SERIES_TICK_S = 0.3
SERIES_DENSE_S = 10.0
SERIES_TAIL_S = (12.0, 15.0)  # the MCU can come back late, as the Vibration Fix sees


def _led_dir() -> str | None:
    if os.path.isdir(LED_PATH):
        return LED_PATH
    found = sorted(glob.glob(LED_GLOB))
    return found[0] if found else None


class StickLightsFix(Fix):
    id = "stick_lights"
    title = "Stick Light Fix"

    def __init__(self) -> None:
        super().__init__()
        self._uevent = None  # set by plugin
        self._task: asyncio.Task | None = None

    # --- Fix interface ---------------------------------------------------
    def supported(self) -> tuple[bool, str]:
        if "asus" not in dmi_vendor().lower():
            return False, "only for ASUS ROG Ally devices"
        if _led_dir() is None:
            return False, "stick light control not available"
        return True, ""

    def is_applied(self) -> bool:
        d = _led_dir()
        return d is not None and read_int(os.path.join(d, "brightness")) == 0

    async def apply(self) -> None:
        d = _led_dir()
        if d is None:
            raise OSError("stick light device not found")
        write_str(os.path.join(d, "multi_intensity"), " ".join([str(COLOR)] * ZONES))
        write_str(os.path.join(d, "brightness"), "0")
        decky.logger.info("[stick_lights] applied: blue, brightness 0")

    async def revert(self) -> None:
        d = _led_dir()
        if d is None:
            return
        mx = read_int(os.path.join(d, "max_brightness"), 255)
        write_str(os.path.join(d, "brightness"), str(mx))
        decky.logger.info("[stick_lights] reverted: brightness %d", mx)

    def details(self) -> dict[str, Any]:
        d = _led_dir()
        if d is None:
            return {}
        return {
            "brightness": read_int(os.path.join(d, "brightness")),
            "multi_intensity": read_str(os.path.join(d, "multi_intensity")),
        }

    async def on_resume(self) -> None:
        self._schedule("resume")

    async def start_background(self) -> None:
        if self._uevent is not None:
            self._uevent.subscribe("leds", self._on_led_event)

    async def stop_background(self) -> None:
        if self._uevent is not None:
            self._uevent.unsubscribe("leds", self._on_led_event)
        await cancel_task(self._task)
        self._task = None

    # --- re-apply ----------------------------------------------------------
    async def _on_led_event(self, event: dict[str, str]) -> None:
        if not self.enabled or event.get("ACTION") != "add":
            return
        if "joystick_rings" not in event.get("DEVPATH", ""):
            return
        self._schedule("led add")

    def _schedule(self, reason: str) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.get_running_loop().create_task(self._series(reason))

    def _write_off(self) -> bool:
        """One cheap tick: every brightness write makes the driver recompute the
        colours (stored blue x 0) and send black to the MCU."""
        d = _led_dir()
        if d is None:
            return False
        try:
            write_str(os.path.join(d, "brightness"), "0")
            return True
        except OSError:
            return False

    async def _series(self, reason: str) -> None:
        """The MCU comes back at an unpredictable moment after resume and lights
        the rings as soon as the driver re-initialises it; keep writing so they go
        dark again within one tick."""
        loop = asyncio.get_running_loop()
        await self.reapply_if_enabled()
        start = loop.time()
        writes = 0
        while loop.time() - start < SERIES_DENSE_S:
            await asyncio.sleep(SERIES_TICK_S)
            if not self.enabled:
                return
            writes += self._write_off()
        for at in SERIES_TAIL_S:
            await asyncio.sleep(max(0.0, start + at - loop.time()))
            if not self.enabled:
                return
            writes += self._write_off()
        await self.reapply_if_enabled()
        decky.logger.info("[stick_lights] %s series: %d writes", reason, writes + 2)
        await self.notify()
