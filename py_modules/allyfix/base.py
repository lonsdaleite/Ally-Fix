"""Common interface for all fixes."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import decky

from . import settings as cfg

StateName = str  # "applied" | "not_applied" | "not_supported" | "error" | "stale" | "restart_pending"


@dataclass
class FixStatus:
    id: str
    enabled: bool
    state: StateName
    supported: bool
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "enabled": self.enabled,
            "state": self.state,
            "supported": self.supported,
            "message": self.message,
            "details": self.details,
        }


async def cancel_task(task: "asyncio.Task | None") -> None:
    """Cancel a background task and wait for it to finish."""
    if task is None or task.done():
        return
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):  # noqa: BLE001
        pass


class Fix:
    """Base class. Subclasses implement supported/is_applied/apply/revert.

    All methods may be called from the Decky event loop; blocking work must be
    short (sysfs reads/writes) or offloaded.
    """

    id: str = ""
    title: str = ""

    def __init__(self) -> None:
        self.last_error: str = ""
        self._emit: Callable[[FixStatus], Awaitable[None]] | None = None

    # --- configuration -------------------------------------------------
    @property
    def enabled(self) -> bool:
        return bool(cfg.get(self.id, "enabled", False))

    def set_enabled(self, value: bool) -> None:
        cfg.set(self.id, "enabled", bool(value))

    # --- hooks for subclasses -----------------------------------------
    def supported(self) -> tuple[bool, str]:
        return True, ""

    def is_applied(self) -> bool:
        raise NotImplementedError

    async def apply(self) -> None:
        raise NotImplementedError

    async def revert(self) -> None:
        raise NotImplementedError

    def details(self) -> dict[str, Any]:
        return {}

    async def start_background(self) -> None:
        """Called once at plugin start (after settings are loaded)."""

    async def stop_background(self) -> None:
        """Called at plugin unload."""

    def needs_resume(self) -> bool:
        """Whether on_resume should be called for this fix."""
        return self.enabled

    async def on_resume(self) -> None:
        """Called after the system wakes from suspend (if needs_resume())."""

    # --- helpers --------------------------------------------------------
    def status(self) -> FixStatus:
        ok, reason = self.supported()
        if not ok:
            return FixStatus(self.id, self.enabled, "not_supported", False, reason, self.details())
        if self.last_error:
            return FixStatus(self.id, self.enabled, "error", True, self.last_error, self.details())
        try:
            applied = self.is_applied()
        except Exception as exc:  # noqa: BLE001
            return FixStatus(self.id, self.enabled, "error", True, f"status check failed: {exc}", self.details())
        state = "applied" if applied else "not_applied"
        return FixStatus(self.id, self.enabled, state, True, "", self.details())

    async def set_and_apply(self, enabled: bool) -> FixStatus:
        ok, reason = self.supported()
        if not ok:
            self.last_error = ""
            return self.status()
        self.set_enabled(enabled)
        self.last_error = ""
        try:
            if enabled:
                await self.apply()
            else:
                await self.revert()
        except Exception as exc:  # noqa: BLE001
            decky.logger.exception("[%s] %s failed", self.id, "apply" if enabled else "revert")
            self.last_error = str(exc)
        return self.status()

    async def reapply_if_enabled(self) -> None:
        if not self.enabled or not self.supported()[0]:
            return
        try:
            await self.apply()
            self.last_error = ""
        except Exception as exc:  # noqa: BLE001
            decky.logger.exception("[%s] reapply failed", self.id)
            self.last_error = str(exc)

    async def notify(self) -> None:
        if self._emit is not None:
            try:
                await self._emit(self.status())
            except Exception:  # noqa: BLE001
                decky.logger.exception("[%s] notify failed", self.id)
