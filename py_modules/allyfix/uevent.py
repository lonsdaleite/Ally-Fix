"""Kernel uevent listener over netlink (no udev/pyudev dependency).

Subscribers register a callback for a SUBSYSTEM value; the callback receives
the parsed event dict (ACTION, SUBSYSTEM, DEVPATH, plus env keys).
"""

from __future__ import annotations

import asyncio
import socket
from typing import Awaitable, Callable

import decky

NETLINK_KOBJECT_UEVENT = 15
_GROUP_KERNEL = 1

Callback = Callable[[dict[str, str]], Awaitable[None]]


class UeventMonitor:
    def __init__(self) -> None:
        self._sock: socket.socket | None = None
        self._subs: dict[str, list[Callback]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def subscribe(self, subsystem: str, cb: Callback) -> None:
        self._subs.setdefault(subsystem, []).append(cb)

    def unsubscribe(self, subsystem: str, cb: Callback) -> None:
        try:
            self._subs.get(subsystem, []).remove(cb)
        except ValueError:
            pass

    def start(self) -> None:
        if self._sock is not None:
            return
        self._loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, NETLINK_KOBJECT_UEVENT)
        sock.setblocking(False)
        sock.bind((0, _GROUP_KERNEL))
        self._sock = sock
        self._loop.add_reader(sock.fileno(), self._on_readable)
        decky.logger.info("[uevent] listening on netlink kobject_uevent")

    def stop(self) -> None:
        if self._sock is None:
            return
        if self._loop is not None:
            self._loop.remove_reader(self._sock.fileno())
        self._sock.close()
        self._sock = None

    def _on_readable(self) -> None:
        assert self._sock is not None
        try:
            while True:
                data = self._sock.recv(8192)
                if not data:
                    return
                event = self._parse(data)
                if event:
                    self._dispatch(event)
        except BlockingIOError:
            return
        except OSError as exc:
            decky.logger.warning("[uevent] recv failed: %s", exc)

    @staticmethod
    def _parse(data: bytes) -> dict[str, str] | None:
        # Format: "action@devpath\0KEY=VAL\0KEY=VAL\0..."
        if data.startswith(b"libudev"):
            return None  # udev-processed events use a binary header; we only bind kernel group
        parts = data.split(b"\0")
        if not parts or b"@" not in parts[0]:
            return None
        event: dict[str, str] = {}
        for part in parts[1:]:
            if b"=" in part:
                k, v = part.split(b"=", 1)
                event[k.decode(errors="replace")] = v.decode(errors="replace")
        return event

    def _dispatch(self, event: dict[str, str]) -> None:
        subs = self._subs.get(event.get("SUBSYSTEM", ""), [])
        for cb in subs:
            assert self._loop is not None
            self._loop.create_task(self._safe(cb, event))

    @staticmethod
    async def _safe(cb: Callback, event: dict[str, str]) -> None:
        try:
            await cb(event)
        except Exception:  # noqa: BLE001
            decky.logger.exception("[uevent] subscriber failed for %s", event.get("SUBSYSTEM"))
