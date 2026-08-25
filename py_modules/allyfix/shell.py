"""Running host binaries (systemctl, busctl, runuser) from the plugin process."""

from __future__ import annotations

import asyncio
import shutil
import subprocess

from .sysfs import clean_env


def run_sync(argv: tuple[str, ...], timeout: float = 20.0) -> tuple[int, str]:
    env = clean_env()
    exe = shutil.which(argv[0], path=env["PATH"]) or argv[0]
    try:
        proc = subprocess.run([exe, *argv[1:]], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              env=env, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except OSError as exc:
        return 127, f"{argv[0]}: {exc}"
    return proc.returncode, proc.stdout.decode(errors="replace").strip()


async def run(*argv: str, timeout: float = 20.0) -> tuple[int, str]:
    # Plain subprocess in a worker thread: asyncio subprocess support depends on
    # the host loop/thread setup, which the Decky runtime does not guarantee.
    return await asyncio.get_running_loop().run_in_executor(None, run_sync, argv, timeout)
