"""Thin helpers around sysfs/DMI reads and writes."""

from __future__ import annotations

import glob
import os

import decky

DMI_BOARD = "/sys/class/dmi/id/board_name"
DMI_PRODUCT = "/sys/class/dmi/id/product_name"
DMI_VENDOR = "/sys/class/dmi/id/sys_vendor"


def read_str(path: str, default: str | None = None) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return default


def read_int(path: str, default: int | None = None) -> int | None:
    value = read_str(path)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def write_str(path: str, value: str) -> None:
    """Write to a sysfs attribute. Raises OSError on failure."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(value)


def try_write(path: str, value: str, log_prefix: str = "") -> bool:
    try:
        write_str(path, value)
        return True
    except OSError as exc:
        decky.logger.warning("%s write %r -> %s failed: %s", log_prefix, value, path, exc)
        return False


def find_hwmon(name: str) -> str | None:
    for d in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
        if read_str(os.path.join(d, "name")) == name:
            return d
    return None


def dmi_board() -> str:
    return read_str(DMI_BOARD, "") or ""


def dmi_vendor() -> str:
    return read_str(DMI_VENDOR, "") or ""


def dmi_product() -> str:
    return read_str(DMI_PRODUCT, "") or ""


def clean_env() -> dict[str, str]:
    """Environment for host binaries (systemctl, busctl).

    Decky's PyInstaller runtime sets LD_LIBRARY_PATH to its bundled OpenSSL,
    which breaks host binaries linked against the system libcrypto.
    """
    env = {k: v for k, v in os.environ.items() if k not in ("LD_LIBRARY_PATH", "PYTHONPATH", "PYTHONHOME")}
    env.setdefault("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
    return env
