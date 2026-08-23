"""CPU Boost Fix: keep CPU boost disabled and keep the frequency cap applied.

On the ROG Xbox Ally X (amd-pstate), every charger plug/unplug event makes the
firmware drop the scaling_max_freq cap on all cores even though boost is off
(cores run at 4+ GHz with a 2 GHz cap). Re-writing scaling_max_freq on every
policy re-sends the cap to the firmware. Each core is an independent cpufreq
policy, so every one of them must be kicked. The slip can also re-occur ~10 s
after the event, so after kicking we watch the cores for a while and kick
again if they go over the cap.
"""

from __future__ import annotations

import asyncio
import glob
import os
import re
from typing import Any

import decky

from .. import settings as cfg
from ..base import Fix, cancel_task
from ..sysfs import dmi_vendor, read_int, read_str, write_str

BOOST_PATH = "/sys/devices/system/cpu/cpufreq/boost"
POLICY_GLOB = "/sys/devices/system/cpu/cpu[0-9]*/cpufreq"

KICK_STEP_KHZ = 30_000
OVER_CAP_TOLERANCE_KHZ = 50_000
DEBOUNCE_S = 1.0
WATCH_WINDOW_S = 30.0
WATCH_POLL_S = 2.0


_CPU_RE = re.compile(r"/cpu(\d+)/cpufreq$")


def _policies() -> list[str]:
    found = [(int(m.group(1)), p) for p in glob.glob(POLICY_GLOB) if (m := _CPU_RE.search(p))]
    return [p for _, p in sorted(found)]


class CpuBoostFix(Fix):
    id = "cpu_boost"
    title = "CPU Boost Fix"

    def __init__(self) -> None:
        super().__init__()
        self._uevent = None  # set by plugin
        self._lock = asyncio.Lock()
        self._watch_task: asyncio.Task | None = None
        self._watch_until: float = 0.0
        self._last_kick: str = ""
        self._kicks: int = 0
        self._kick_requested: bool = False

    # --- options -------------------------------------------------------
    @property
    def refresh_on_charger(self) -> bool:
        return bool(cfg.get(self.id, "refresh_on_charger", True))

    def set_options(self, opts: dict[str, Any]) -> None:
        allowed = {k: bool(v) for k, v in opts.items() if k in ("refresh_on_charger",)}
        if allowed:
            cfg.update(self.id, allowed)

    # --- Fix interface ---------------------------------------------------
    def supported(self) -> tuple[bool, str]:
        if not os.path.exists(BOOST_PATH):
            return False, "cpufreq boost control not available"
        if "asus" not in dmi_vendor().lower():
            return False, "only for ASUS ROG Ally devices"
        return True, ""

    def is_applied(self) -> bool:
        return read_str(BOOST_PATH) == "0"

    async def apply(self) -> None:
        write_str(BOOST_PATH, "0")
        decky.logger.info("[cpu_boost] boost disabled")
        await self.kick_cap("apply")

    async def revert(self) -> None:
        self._stop_watch()
        write_str(BOOST_PATH, "1")
        # The cap we re-sent while boost was off is a user frequency-QoS request and survives
        # boost=1; lift it explicitly on every policy (verified on RC73XA: without this the
        # cores stay at 2 GHz until reboot).
        lifted = 0
        for p in _policies():
            hw_max = read_int(os.path.join(p, "cpuinfo_max_freq"))
            if hw_max is None:
                continue
            try:
                write_str(os.path.join(p, "scaling_max_freq"), str(hw_max))
                lifted += 1
            except OSError as exc:
                decky.logger.warning("[cpu_boost] lifting cap failed for %s: %s", p, exc)
        decky.logger.info("[cpu_boost] boost enabled (factory), cap lifted on %d policies", lifted)

    def details(self) -> dict[str, Any]:
        return {
            "boost": read_str(BOOST_PATH),
            "refresh_on_charger": self.refresh_on_charger,
            "over_cap_cores": self._over_cap_count(),
            "policies": len(_policies()),
            "kicks": self._kicks,
            "last_kick": self._last_kick,
            "watching": self._watch_task is not None and not self._watch_task.done(),
        }

    async def on_resume(self) -> None:
        await self.reapply_if_enabled()

    async def start_background(self) -> None:
        if self._uevent is not None:
            self._uevent.subscribe("power_supply", self._on_power_event)

    async def stop_background(self) -> None:
        if self._uevent is not None:
            self._uevent.unsubscribe("power_supply", self._on_power_event)
        await cancel_task(self._watch_task)
        self._watch_task = None

    # --- cap refresh -----------------------------------------------------
    def _over_cap_count(self) -> int:
        n = 0
        for p in _policies():
            cur = read_int(os.path.join(p, "scaling_cur_freq"))
            mx = read_int(os.path.join(p, "scaling_max_freq"))
            if cur is not None and mx is not None and cur > mx + OVER_CAP_TOLERANCE_KHZ:
                n += 1
        return n

    def _cap_slipped(self) -> bool:
        if read_str(BOOST_PATH) != "0":
            return True
        return self._over_cap_count() > 0

    async def kick_cap(self, reason: str) -> None:
        """Re-send scaling_max_freq on every policy (all cores)."""
        async with self._lock:
            if read_str(BOOST_PATH) != "0":
                write_str(BOOST_PATH, "0")
            saved: list[tuple[str, int]] = []
            try:
                for p in _policies():
                    path = os.path.join(p, "scaling_max_freq")
                    mx = read_int(path)
                    if mx is None:
                        continue
                    try:
                        write_str(path, str(mx - KICK_STEP_KHZ))
                        saved.append((path, mx))
                    except OSError as exc:
                        decky.logger.warning("[cpu_boost] kick write failed for %s: %s", path, exc)
                await asyncio.sleep(0.2)
            finally:
                # Always restore the original cap, even if the task is cancelled mid-kick.
                for path, mx in saved:
                    try:
                        write_str(path, str(mx))
                    except OSError as exc:
                        decky.logger.warning("[cpu_boost] restore write failed for %s: %s", path, exc)
            self._kicks += 1
            self._last_kick = reason
            decky.logger.info("[cpu_boost] cap kicked on %d policies (%s)", len(saved), reason)

    async def _on_power_event(self, event: dict[str, str]) -> None:
        if not self.enabled or not self.refresh_on_charger:
            return
        if event.get("ACTION") != "change" or event.get("POWER_SUPPLY_TYPE") != "Mains":
            return
        decky.logger.info("[cpu_boost] charger event: %s online=%s",
                          event.get("POWER_SUPPLY_NAME"), event.get("POWER_SUPPLY_ONLINE"))
        self.schedule_refresh("charger")

    def schedule_refresh(self, reason: str) -> None:
        loop = asyncio.get_running_loop()
        self._watch_until = loop.time() + WATCH_WINDOW_S
        if self._watch_task is None or self._watch_task.done():
            self._watch_task = loop.create_task(self._watch(reason))
        else:
            # a new event during an active window: every event deserves its own kick,
            # idle cores would not reveal the slip through scaling_cur_freq
            self._kick_requested = True

    def _stop_watch(self) -> None:
        if self._watch_task is not None and not self._watch_task.done():
            self._watch_task.cancel()
        self._watch_task = None

    async def _watch(self, reason: str) -> None:
        loop = asyncio.get_running_loop()
        await asyncio.sleep(DEBOUNCE_S)
        self._kick_requested = False
        await self.kick_cap(reason)
        await self.notify()
        kicked = 1
        while loop.time() < self._watch_until:
            await asyncio.sleep(WATCH_POLL_S)
            if not self.enabled:
                return
            if self._kick_requested:
                self._kick_requested = False
                await self.kick_cap(f"{reason}:event")
                kicked += 1
            elif self._cap_slipped():
                await self.kick_cap(f"{reason}:recheck")
                kicked += 1
                # a slip means the firmware is still settling: extend the window
                self._watch_until = loop.time() + WATCH_WINDOW_S
        decky.logger.info("[cpu_boost] watch finished (%s), %d kick(s)", reason, kicked)
        await self.notify()
