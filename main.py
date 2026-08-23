"""Ally Fix — Decky Loader plugin backend.

One-click fixes for the ROG Xbox Ally X on SteamOS. All background logic runs
inside this process (asyncio); the only file written outside the plugin
directory is the InputPlumber override for the Gyro Fix.
"""

import asyncio
import json
import os
import sys

import decky

sys.path.insert(0, os.path.join(decky.DECKY_PLUGIN_DIR, "py_modules"))

from allyfix import registry  # noqa: E402
from allyfix import settings as cfg  # noqa: E402
from allyfix import updater  # noqa: E402
from allyfix.resume import ResumeDetector  # noqa: E402
from allyfix.uevent import UeventMonitor  # noqa: E402


def _version() -> str:
    try:
        with open(os.path.join(decky.DECKY_PLUGIN_DIR, "package.json"), "r", encoding="utf-8") as f:
            return str(json.load(f).get("version", "0"))
    except (OSError, ValueError):
        return "0"


class Plugin:
    async def _main(self):
        self.version = _version()
        self.fixes = registry.build()
        self.uevent = UeventMonitor()
        self.resume = ResumeDetector(self._on_resume)
        decky.logger.info("Ally Fix %s starting (uid=%d)", self.version, os.geteuid())

        cfg.load()
        for fix in self.fixes.values():
            fix._emit = self._emit_fix_status
            if hasattr(fix, "_uevent"):
                fix._uevent = self.uevent

        try:
            self.uevent.start()
        except OSError as exc:
            decky.logger.error("uevent monitor failed to start: %s", exc)
        self.resume.start()

        for fix in self.fixes.values():
            await fix.reapply_if_enabled()
            try:
                await fix.start_background()
            except Exception:  # noqa: BLE001
                decky.logger.exception("[%s] start_background failed", fix.id)
        await self._emit_status()

    async def _unload(self):
        decky.logger.info("Ally Fix unloading")
        await self.resume.stop()
        for fix in self.fixes.values():
            try:
                await fix.stop_background()
            except Exception:  # noqa: BLE001
                decky.logger.exception("[%s] stop_background failed", fix.id)
        self.uevent.stop()

    async def _uninstall(self):
        decky.logger.info("Ally Fix uninstalling: reverting enabled fixes")
        for fix in self.fixes.values():
            if fix.enabled and fix.supported()[0]:
                try:
                    await fix.revert()
                except Exception:  # noqa: BLE001
                    decky.logger.exception("[%s] revert on uninstall failed", fix.id)
        # Enhanced Vibration is not a fix, but the flag persists in the controller —
        # without the plugin there would be nothing left to turn it off with.
        vib = self.fixes["vibration"]
        if vib.enhanced and registry.device_supported() and vib.supported()[0]:
            try:
                await vib.set_enhanced(False)
            except Exception:  # noqa: BLE001
                decky.logger.exception("[vibration] enhanced off on uninstall failed")

    # --- events ----------------------------------------------------------
    async def _on_resume(self, slept: float):
        for fix in self.fixes.values():
            if fix.enabled and fix.supported()[0]:
                try:
                    await fix.on_resume()
                except Exception:  # noqa: BLE001
                    decky.logger.exception("[%s] on_resume failed", fix.id)
        await self._emit_status()

    async def _emit_fix_status(self, status):
        await decky.emit("fix_status", status.to_dict())

    async def _emit_status(self):
        await decky.emit("status", await registry.plugin_status(self.fixes, self.version))

    @staticmethod
    def _reset_defaults_on_enable(fix) -> None:
        """Turning a fix on (explicitly) brings its sub-options back to defaults."""
        if fix.id == "cpu_boost":
            fix.set_options({"refresh_on_charger": True})
        elif fix.id == "vibration":
            fix.set_options({"linked": True, "left": 50, "right": 50})

    # --- RPC ----------------------------------------------------------------
    async def get_status(self) -> dict:
        return await registry.plugin_status(self.fixes, self.version)

    async def set_fix_enabled(self, fix_id: str, enabled: bool) -> dict:
        fix = self.fixes.get(fix_id)
        if fix is None:
            return {"ok": False, "error": f"unknown fix {fix_id}", "status": None}
        if enabled:
            self._reset_defaults_on_enable(fix)
        await fix.set_and_apply(bool(enabled))
        st = await registry.status_of(fix)
        return {"ok": st.state != "error", "error": st.message, "status": st.to_dict()}

    async def fix_all(self) -> dict:
        if not registry.device_supported():
            decky.logger.warning("fix_all refused: unsupported device %s", registry.dmi_board())
            return await self.get_status()
        for fid in registry.FIX_ORDER:
            fix = self.fixes[fid]
            if fix.supported()[0]:
                self._reset_defaults_on_enable(fix)
                await fix.set_and_apply(True)
        return await self.get_status()

    async def set_cpu_boost_options(self, opts: dict) -> dict:
        fix = self.fixes["cpu_boost"]
        fix.set_options(opts or {})
        st = await registry.status_of(fix)
        return {"ok": True, "error": "", "status": st.to_dict()}

    async def cpu_cap_refresh_now(self) -> dict:
        fix = self.fixes["cpu_boost"]
        if not fix.enabled:
            return {"ok": False, "error": "CPU Boost Fix is not enabled"}
        fix.schedule_refresh("manual")
        return {"ok": True, "error": ""}

    async def set_vibration_options(self, opts: dict) -> dict:
        fix = self.fixes["vibration"]
        fix.set_options(opts or {})
        if fix.enabled:
            await fix.reapply_if_enabled()
        st = await registry.status_of(fix)
        return {"ok": not fix.last_error, "error": fix.last_error, "status": st.to_dict()}

    async def set_enhanced_vibration(self, enabled: bool) -> dict:
        fix = self.fixes["vibration"]
        if not registry.device_supported():
            st = await registry.status_of(fix)
            board = registry.dmi_board() or "unknown"
            return {"ok": False, "error": f"Enhanced Vibration needs a ROG Xbox Ally (board {board})", "status": st.to_dict()}
        try:
            await fix.set_enhanced(bool(enabled))
        except Exception as exc:  # noqa: BLE001
            decky.logger.warning("[vibration] enhanced toggle failed: %s", exc)
            st = await registry.status_of(fix)
            return {"ok": False, "error": str(exc), "status": st.to_dict()}
        st = await registry.status_of(fix)
        return {"ok": True, "error": "", "status": st.to_dict()}

    async def test_vibration(self, duration_ms: int = 500) -> dict:
        try:
            await self.fixes["vibration"].test(int(duration_ms))
            return {"ok": True, "error": ""}
        except Exception as exc:  # noqa: BLE001
            decky.logger.warning("[vibration] test failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    async def fan_restore_factory_curve(self) -> dict:
        fix = self.fixes["fan"]
        try:
            msg = await fix.restore_factory_curve()
            st = await registry.status_of(fix)
            return {"ok": True, "error": "", "message": msg, "status": st.to_dict()}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    async def check_update(self) -> dict:
        return await updater.check(self.version)

    async def install_update(self, zip_url: str) -> dict:
        if not zip_url.startswith("https://github.com/lonsdaleite/Ally-Fix/releases/download/"):
            return {"ok": False, "error": "refusing to install from an unexpected URL"}
        return await updater.install(zip_url)
