"""InputPlumber bits shared by the fixes that override its configs (Gyro, Gamepad Layout)."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re

import decky

from .shell import run as _run
from .shell import run_sync as _run_sync

BINARY = "/usr/bin/inputplumber"
_VERSION_RE = re.compile(r"\binputplumber\s+v?(\d+(?:\.\d+)+)")

_lock: asyncio.Lock | None = None
_version_cache: tuple[float, str | None] = (-1.0, None)


def sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def version() -> str | None:
    """Installed InputPlumber version ("0.78.0"), cached per binary mtime: status() asks
    on every poll, the binary only changes with a SteamOS update."""
    global _version_cache
    try:
        mtime = os.stat(BINARY).st_mtime
    except OSError:
        return None
    if _version_cache[0] == mtime:
        return _version_cache[1]
    code, out = _run_sync((BINARY, "--version"), timeout=5)
    m = _VERSION_RE.search(out) if code == 0 else None
    _version_cache = (mtime, m.group(1) if m else None)
    return _version_cache[1]


async def restart(tag: str) -> None:
    """Restart the daemon so it re-reads its configs. Serialized: both fixes may change
    their file in the same pass (Fix all, plugin start)."""
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    async with _lock:
        code, out = await _run("systemctl", "restart", "inputplumber")
    if code != 0:
        raise RuntimeError(f"systemctl restart inputplumber failed ({code}): {out}")
    decky.logger.info("[%s] inputplumber restarted", tag)
