"""The Steam client as a systemd user service of the Decky user.

In gaming mode Steam runs as `steam-launcher.service` in the user's systemd instance;
the plugin runs as root, so user-level systemctl calls go through `runuser` with the
user's runtime directory. `SteamClient.User.StartRestart` (what the UI can do on its own)
re-executes the client inside the same `steam.sh` with the environment it already has,
so anything that needs a fresh environment (LD_PRELOAD from a drop-in) needs the service
restarted instead.
"""

from __future__ import annotations

import os
import pwd
from typing import Any

import decky

from .shell import run

SERVICE = "steam-launcher.service"
UNIT_FILE = f"/usr/lib/systemd/user/{SERVICE}"
USER = decky.DECKY_USER
HOME = decky.DECKY_USER_HOME
DROPIN_DIR = os.path.join(HOME, ".config", "systemd", "user", f"{SERVICE}.d")


def uid() -> int:
    return pwd.getpwnam(USER).pw_uid


def gid() -> int:
    return pwd.getpwnam(USER).pw_gid


def chown_user(path: str) -> None:
    os.chown(path, uid(), gid())


async def user_systemctl(*args: str, timeout: float = 30.0) -> tuple[int, str]:
    u = uid()
    env = (f"XDG_RUNTIME_DIR=/run/user/{u}", f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{u}/bus")
    if os.geteuid() == u:
        return await run("env", *env, "systemctl", "--user", *args, timeout=timeout)
    return await run("runuser", "-u", USER, "--", "env", *env, "systemctl", "--user", *args, timeout=timeout)


async def daemon_reload() -> None:
    rc, out = await user_systemctl("daemon-reload")
    if rc != 0:
        raise RuntimeError(f"systemctl --user daemon-reload failed: {out or rc}")


async def service_state() -> str:
    """systemd ActiveState of the client service ("active", "activating", "inactive", …)."""
    rc, out = await user_systemctl("show", "-p", "ActiveState", "--value", SERVICE, timeout=10.0)
    return out.strip() if rc == 0 else ""


async def service_managed() -> bool:
    """Whether the client is (or is just becoming) the user service — a `restart` then does
    the right thing even while it is still starting up or shutting down."""
    return await service_state() in ("active", "activating", "reloading", "deactivating")


def client_pids() -> list[int]:
    """PIDs of the user's `steam` client processes, newest first."""
    u = uid()
    found: list[tuple[int, int]] = []
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        pid = int(name)
        try:
            if os.stat(f"/proc/{pid}").st_uid != u:
                continue
            with open(f"/proc/{pid}/comm") as f:
                if f.read().strip() != "steam":
                    continue
            with open(f"/proc/{pid}/stat") as f:
                starttime = int(f.read().rsplit(")", 1)[1].split()[19])
        except (OSError, ValueError, IndexError):
            continue
        found.append((starttime, pid))
    return [pid for _, pid in sorted(found, reverse=True)]


def client_has_mapped(pid: int, needle: str) -> bool:
    try:
        with open(f"/proc/{pid}/maps") as f:
            return any(needle in line for line in f)
    except OSError:
        return False


async def restart() -> dict[str, Any]:
    """Restart the client so it starts with a fresh environment. Only possible while it
    runs as the user service (gaming mode); the caller falls back to Steam's own restart."""
    if not await service_managed():
        return {"ok": False, "error": f"{SERVICE} is not running"}
    rc, out = await user_systemctl("restart", "--no-block", SERVICE)
    if rc != 0:
        return {"ok": False, "error": f"systemctl --user restart failed: {out or rc}"}
    decky.logger.info("[steam] %s restart requested", SERVICE)
    return {"ok": True, "error": ""}
