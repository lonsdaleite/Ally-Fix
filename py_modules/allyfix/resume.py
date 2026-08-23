"""Suspend/resume detection without Steam client hooks.

CLOCK_MONOTONIC stops during suspend, CLOCK_BOOTTIME does not. A jump in their
difference means the machine was suspended in between.
"""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable

import decky

_POLL_S = 1.0
_THRESHOLD_S = 2.0


class ResumeDetector:
    def __init__(self, on_resume: Callable[[float], Awaitable[None]]) -> None:
        self._on_resume = on_resume
        self._task: asyncio.Task | None = None

    @staticmethod
    def _delta() -> float:
        return time.clock_gettime(time.CLOCK_BOOTTIME) - time.clock_gettime(time.CLOCK_MONOTONIC)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.get_running_loop().create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None

    async def _run(self) -> None:
        last = self._delta()
        while True:
            await asyncio.sleep(_POLL_S)
            now = self._delta()
            slept = now - last
            last = now
            if slept >= _THRESHOLD_S:
                decky.logger.info("[resume] detected: suspended for ~%.0fs", slept)
                try:
                    await self._on_resume(slept)
                except Exception:  # noqa: BLE001
                    decky.logger.exception("[resume] handler failed")
