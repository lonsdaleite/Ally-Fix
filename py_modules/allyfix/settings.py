"""Settings persistence via Decky's SettingsManager.

Layout (settings.json):
{
  "version": 1,
  "cpu_boost": {"enabled": false, "refresh_on_charger": true},
  "vibration": {"enabled": false, "left": 50, "right": 50, "linked": true,
                "enhanced": false, "mirror_triggers": false},
  "fan":       {"enabled": false, "curves": {"performance": {...}}},
  "gyro":      {"enabled": false, "mode": "simple"},  # plus bookkeeping for steam_dev.cfg
  "gamepad_layout": {"enabled": false}
}
"""

from __future__ import annotations

from typing import Any

import decky
from settings import SettingsManager

DEFAULTS: dict[str, dict[str, Any]] = {
    "cpu_boost": {"enabled": False, "refresh_on_charger": True},
    "vibration": {"enabled": False, "left": 50, "right": 50, "linked": True, "enhanced": False, "mirror_triggers": False},
    "fan": {"enabled": False, "curves": {}},
    "gyro": {"enabled": False, "mode": "simple"},
    "gamepad_layout": {"enabled": False},
}

_manager: SettingsManager | None = None


def load() -> None:
    global _manager
    _manager = SettingsManager(name="settings", settings_directory=decky.DECKY_PLUGIN_SETTINGS_DIR)
    _manager.read()
    if _manager.getSetting("version") is None:
        _manager.setSetting("version", 1)
        _manager.commit()


def section(fix_id: str) -> dict[str, Any]:
    assert _manager is not None, "settings not loaded"
    data = dict(DEFAULTS.get(fix_id, {}))
    stored = _manager.getSetting(fix_id, None)
    if isinstance(stored, dict):
        data.update(stored)
    return data


def get(fix_id: str, key: str, default: Any = None) -> Any:
    return section(fix_id).get(key, default)


def set(fix_id: str, key: str, value: Any) -> None:  # noqa: A001
    assert _manager is not None, "settings not loaded"
    data = section(fix_id)
    data[key] = value
    _manager.setSetting(fix_id, data)
    _manager.commit()


def update(fix_id: str, values: dict[str, Any]) -> None:
    assert _manager is not None, "settings not loaded"
    data = section(fix_id)
    data.update(values)
    _manager.setSetting(fix_id, data)
    _manager.commit()
