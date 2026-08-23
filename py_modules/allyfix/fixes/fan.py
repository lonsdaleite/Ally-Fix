"""Fan Noise Fix: pin the fan curve so the EC cannot get stuck at full speed.

Symptom on the ROG Xbox Ally X: occasionally after resume both fans spin at
maximum (>8000 rpm) and never settle. Writing the custom fan curve with
pwm*_enable=1 brings the EC back. The kernel (asus-wmi) resets pwm*_enable to
2 (auto) on every thermal-profile change and never restores curves on resume,
so a watchdog keeps the curve pinned.

Policy: the fix does NOT invent a curve. For each thermal profile it pins the
curve that is there — the factory curve of that profile (loaded through
pwm_enable=3, "reset to factory for current mode") or whatever another tool
wrote while the curve was enabled. Curves are remembered per profile.

Facts verified on RC73XA (kernel 6.16): pwm scale is 0..255; profile switch
does not touch the points, only pwm_enable; pwm_enable=3 loads the factory
curve of the *current* throttle_thermal_policy and leaves enable=2;
platform_profile reads "custom" after any curve operation, so the current
profile is read from throttle_thermal_policy.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import decky

from .. import settings as cfg
from ..base import Fix, cancel_task
from ..sysfs import find_hwmon, read_int, read_str, write_str

TTP_PATH = "/sys/devices/platform/asus-nb-wmi/throttle_thermal_policy"
PROFILE_NAMES = {0: "balanced", 1: "performance", 2: "low-power"}
POINTS = 8
FANS = ("pwm1", "pwm2")
RPM_FAILSAFE = 6000
FAILSAFE_MAX_TEMP_C = 65.0  # above this, >6000 rpm is legitimate load, not a stuck EC
WATCHDOG_PERIOD_S = 5.0
RESUME_SETTLE_S = 3.0

Curve = dict[str, list[int]]  # {"temps": [...], "pwm1": [...], "pwm2": [...]}


class FanFix(Fix):
    id = "fan"
    title = "Fan Noise Fix"

    def __init__(self) -> None:
        super().__init__()
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._last_event: str = ""

    # --- hwmon access ----------------------------------------------------
    @staticmethod
    def _curve_dir() -> str | None:
        return find_hwmon("asus_custom_fan_curve")

    @staticmethod
    def _fan_dir() -> str | None:
        return find_hwmon("asus")

    @staticmethod
    def _temp() -> float | None:
        d = find_hwmon("k10temp")
        v = read_int(os.path.join(d, "temp1_input")) if d else None
        return v / 1000.0 if v is not None else None

    def _rpm(self) -> tuple[int | None, int | None]:
        d = self._fan_dir()
        if not d:
            return None, None
        return read_int(os.path.join(d, "fan1_input")), read_int(os.path.join(d, "fan2_input"))

    @staticmethod
    def profile() -> str:
        ttp = read_int(TTP_PATH)
        return PROFILE_NAMES.get(ttp, f"ttp{ttp}") if ttp is not None else "unknown"

    def _enable(self) -> tuple[int | None, int | None]:
        d = self._curve_dir()
        if not d:
            return None, None
        return read_int(os.path.join(d, "pwm1_enable")), read_int(os.path.join(d, "pwm2_enable"))

    def _write_enable(self, value: int) -> None:
        d = self._curve_dir()
        if not d:
            raise OSError("asus_custom_fan_curve hwmon not found")
        for fan in FANS:
            write_str(os.path.join(d, f"{fan}_enable"), str(value))

    def _read_curve(self) -> Curve:
        d = self._curve_dir()
        if not d:
            raise OSError("asus_custom_fan_curve hwmon not found")
        temps = [read_int(os.path.join(d, f"pwm1_auto_point{i}_temp"), -1) for i in range(1, POINTS + 1)]
        curve: Curve = {"temps": temps}
        for fan in FANS:
            curve[fan] = [read_int(os.path.join(d, f"{fan}_auto_point{i}_pwm"), -1) for i in range(1, POINTS + 1)]
        return curve

    def _write_curve(self, curve: Curve) -> None:
        d = self._curve_dir()
        if not d:
            raise OSError("asus_custom_fan_curve hwmon not found")
        for fan in FANS:
            for i in range(POINTS):
                write_str(os.path.join(d, f"{fan}_auto_point{i + 1}_temp"), str(curve["temps"][i]))
                write_str(os.path.join(d, f"{fan}_auto_point{i + 1}_pwm"), str(curve[fan][i]))

    # --- snapshots ------------------------------------------------------
    def _snapshots(self) -> dict[str, Curve]:
        curves = cfg.get(self.id, "curves", {})
        return dict(curves) if isinstance(curves, dict) else {}

    def _save_snapshot(self, profile: str, curve: Curve) -> None:
        curves = self._snapshots()
        curves[profile] = curve
        cfg.set(self.id, "curves", curves)

    @staticmethod
    def _valid(curve: Curve | None) -> bool:
        if not curve:
            return False
        return all(len(curve.get(k, [])) == POINTS and min(curve[k]) >= 0 for k in ("temps", *FANS))

    # --- core operation --------------------------------------------------
    def _pin(self, reason: str, force_write: bool = False) -> str:
        """Ensure the current profile's curve is loaded and enabled. Returns what was done."""
        profile = self.profile()
        en1, en2 = self._enable()
        curve = self._read_curve()
        snap = self._snapshots().get(profile)

        if en1 == 1 and en2 == 1 and not force_write:
            if not self._valid(curve):
                return ""  # transient read failure: do not adopt garbage
            if self._valid(snap) and curve != snap:
                # someone else wrote a curve while pinned: adopt it
                self._save_snapshot(profile, curve)
                return f"adopted external curve for {profile}"
            if not self._valid(snap):
                self._save_snapshot(profile, curve)
                return f"captured curve for {profile}"
            return ""

        if not self._valid(snap):
            # no snapshot for this profile: load the factory curve of the current mode
            self._write_enable(3)
            curve = self._read_curve()
            self._save_snapshot(profile, curve)
            action = f"captured factory curve for {profile}"
        else:
            curve = snap
            action = f"restored curve for {profile}"
        self._write_curve(curve)
        self._write_enable(1)
        return f"{action} ({reason})"

    def _failsafe_tripped(self) -> bool:
        rpm1, rpm2 = self._rpm()
        temp = self._temp()
        if temp is not None and temp >= FAILSAFE_MAX_TEMP_C:
            return False
        return any(r is not None and r > RPM_FAILSAFE for r in (rpm1, rpm2))

    def _state_line(self) -> str:
        en1, en2 = self._enable()
        rpm1, rpm2 = self._rpm()
        temp = self._temp()
        return f"profile={self.profile()} enable={en1}/{en2} rpm={rpm1}/{rpm2} temp={temp}"

    # --- Fix interface ---------------------------------------------------
    def supported(self) -> tuple[bool, str]:
        if self._curve_dir() is None:
            return False, "asus_custom_fan_curve hwmon not found"
        if read_int(TTP_PATH) is None:
            return False, "throttle_thermal_policy not available"
        return True, ""

    def is_applied(self) -> bool:
        en1, en2 = self._enable()
        return en1 == 1 and en2 == 1

    async def apply(self) -> None:
        self._start_watchdog()  # even if this first pin fails, the watchdog keeps retrying
        async with self._lock:
            done = self._pin("apply")
            decky.logger.info("[fan] %s; %s", done or "already pinned", self._state_line())
            self._last_event = done or "pinned"

    async def revert(self) -> None:
        self._stop_watchdog()
        async with self._lock:
            self._write_enable(2)
            decky.logger.info("[fan] curve unpinned (factory auto); %s", self._state_line())
            self._last_event = "unpinned"

    def details(self) -> dict[str, Any]:
        en1, en2 = self._enable()
        rpm1, rpm2 = self._rpm()
        profile = self.profile()
        return {
            "profile": profile,
            "pwm_enable": [en1, en2],
            "rpm": [rpm1, rpm2],
            "temp": self._temp(),
            "snapshot_profiles": sorted(self._snapshots().keys()),
            "last_event": self._last_event,
        }

    async def restore_factory_curve(self) -> str:
        """Forget the pinned curve of the current profile and pin the factory one again."""
        async with self._lock:
            profile = self.profile()
            curves = self._snapshots()
            curves.pop(profile, None)
            cfg.set(self.id, "curves", curves)
            if not self.enabled:
                return f"snapshot for {profile} cleared"
            done = self._pin("factory-restore", force_write=True)
            decky.logger.info("[fan] %s; %s", done, self._state_line())
            self._last_event = done
            return done

    async def on_resume(self) -> None:
        pre = self._state_line()
        await asyncio.sleep(RESUME_SETTLE_S)
        if not self.enabled:
            return
        async with self._lock:
            done = self._pin("resume", force_write=True)
        decky.logger.info("[fan] resume: pre-state %s | %s", pre, done)
        await asyncio.sleep(RESUME_SETTLE_S)
        post = self._state_line()
        decky.logger.info("[fan] resume: post-state %s", post)
        if self.enabled and self._failsafe_tripped():
            async with self._lock:
                done = self._pin("resume-failsafe", force_write=True)
            decky.logger.warning("[fan] resume: fans still in failsafe, re-pinned: %s", done)
        self._last_event = f"resume: {done}"
        await self.notify()

    async def start_background(self) -> None:
        if self.enabled and self.supported()[0]:
            self._start_watchdog()

    async def stop_background(self) -> None:
        await cancel_task(self._task)
        self._task = None

    # --- watchdog ---------------------------------------------------------
    def _start_watchdog(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(self._watchdog())

    def _stop_watchdog(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None

    async def _watchdog(self) -> None:
        while True:
            await asyncio.sleep(WATCHDOG_PERIOD_S)
            if not self.enabled:
                return
            try:
                async with self._lock:
                    if self._failsafe_tripped():
                        pre = self._state_line()
                        done = self._pin("failsafe", force_write=True)
                        decky.logger.warning("[fan] failsafe tripped: %s -> %s", pre, done)
                    else:
                        done = self._pin("watchdog")
                        if done:
                            decky.logger.info("[fan] %s; %s", done, self._state_line())
                if done:
                    self._last_event = done
                if done or self.last_error:
                    self.last_error = ""
                    await self.notify()
            except Exception as exc:  # noqa: BLE001
                decky.logger.exception("[fan] watchdog failed")
                self.last_error = str(exc)
                await self.notify()
