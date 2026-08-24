"""Which board this is and what its hardware has."""

from __future__ import annotations

from .sysfs import dmi_board

SUPPORTED_BOARDS = ("RC73XA", "RC73YA")  # ROG Xbox Ally X, ROG Xbox Ally
IMPULSE_TRIGGER_BOARDS = ("RC73XA",)  # only the Xbox Ally X has motors in the triggers


def device_supported() -> bool:
    return dmi_board() in SUPPORTED_BOARDS


def has_impulse_triggers() -> bool:
    return dmi_board() in IMPULSE_TRIGGER_BOARDS
