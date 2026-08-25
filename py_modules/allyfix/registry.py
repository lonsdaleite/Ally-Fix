"""Fix registry and plugin-level status."""

from __future__ import annotations

from typing import Any

import decky

from .base import Fix, FixStatus
from .device import SUPPORTED_BOARDS, device_supported, has_impulse_triggers  # noqa: F401
from .fixes.cpu_boost import CpuBoostFix
from .fixes.fan import FanFix
from .fixes.gyro import GyroFix
from .fixes.vibration import VibrationFix
from .sysfs import dmi_board, dmi_product

FIX_ORDER = ("cpu_boost", "vibration", "fan", "gyro")


def build() -> dict[str, Fix]:
    fixes: dict[str, Fix] = {}
    for cls in (CpuBoostFix, VibrationFix, FanFix, GyroFix):
        fix = cls()
        fixes[fix.id] = fix
    return fixes


async def status_of(fix: Fix) -> FixStatus:
    st = fix.status()
    details_async = getattr(fix, "details_async", None)
    if details_async is not None:
        try:
            st.details = await details_async()
        except Exception:  # noqa: BLE001
            decky.logger.exception("[%s] details_async failed", fix.id)
    return st


async def plugin_status(fixes: dict[str, Fix], version: str) -> dict[str, Any]:
    board = dmi_board()
    statuses = {fid: (await status_of(fixes[fid])).to_dict() for fid in FIX_ORDER if fid in fixes}
    cpu = fixes["cpu_boost"]
    vib = fixes["vibration"]
    gyro = fixes["gyro"]
    return {
        "version": version,
        "board": board,
        "product": dmi_product(),
        "device_supported": device_supported(),
        "impulse_triggers": has_impulse_triggers(),
        "fixes": statuses,
        "options": {
            "cpu_boost": {"refresh_on_charger": cpu.refresh_on_charger},  # type: ignore[attr-defined]
            "vibration": {
                "left": vib.intensity[0],  # type: ignore[attr-defined]
                "right": vib.intensity[1],  # type: ignore[attr-defined]
                "linked": vib.linked,  # type: ignore[attr-defined]
                "enhanced": vib.enhanced,  # type: ignore[attr-defined]
                "mirror_triggers": vib.mirror_triggers,  # type: ignore[attr-defined]
            },
            "gyro": {"mode": gyro.mode},  # type: ignore[attr-defined]
        },
    }
