"""Self-update from GitHub Releases (the plugin is distributed outside the Decky Store)."""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import shutil
import ssl
import subprocess
import tempfile
import urllib.request
import zipfile
from typing import Any

import decky

from .sysfs import clean_env

REPO = "lonsdaleite/Ally-Fix"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
TIMEOUT_S = 15


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


CA_BUNDLES = ("/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt", "/etc/ssl/cert.pem")


def _ssl_context() -> ssl.SSLContext:
    # Decky's bundled Python may not find the host CA store; point it there explicitly.
    for path in CA_BUNDLES:
        if os.path.exists(path):
            return ssl.create_default_context(cafile=path)
    return ssl.create_default_context()


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Ally-Fix-updater", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S, context=_ssl_context()) as resp:
            return resp.read()
    except Exception as exc:  # noqa: BLE001
        decky.logger.warning("[updater] urllib fetch failed (%s), falling back to curl", exc)
    curl = shutil.which("curl", path=clean_env()["PATH"])
    if not curl:
        raise RuntimeError(f"fetch failed and curl not available")
    proc = subprocess.run([curl, "-fsSL", "-A", "Ally-Fix-updater", url], capture_output=True,
                          env=clean_env(), timeout=TIMEOUT_S * 4, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"curl failed ({proc.returncode}): {proc.stderr.decode(errors='replace').strip()[:200]}")
    return proc.stdout


def _latest_sync() -> dict[str, Any]:
    rel = json.loads(_fetch(API_LATEST))
    assets = [a for a in rel.get("assets", []) if a.get("name", "").endswith(".zip")]
    return {
        "tag": rel.get("tag_name", ""),
        "url": rel.get("html_url", ""),
        "zip": assets[0]["browser_download_url"] if assets else "",
        "notes": (rel.get("body") or "")[:2000],
    }


async def check(current: str) -> dict[str, Any]:
    try:
        latest = await asyncio.get_running_loop().run_in_executor(None, _latest_sync)
    except Exception as exc:  # noqa: BLE001
        decky.logger.warning("[updater] check failed: %s", exc)
        return {"ok": False, "error": f"update check failed: {exc}", "current": current}
    newer = _version_tuple(latest["tag"]) > _version_tuple(current)
    return {"ok": True, "error": "", "current": current, "latest": latest["tag"],
            "url": latest["url"], "zip": latest["zip"], "update_available": newer and bool(latest["zip"])}


def _install_sync(zip_url: str, plugin_dir: str) -> None:
    data = _fetch(zip_url)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        roots = {n.split("/", 1)[0] for n in names if "/" in n}
        if len(roots) != 1:
            raise RuntimeError("unexpected zip layout")
        root = roots.pop()
        if not any(n == f"{root}/plugin.json" for n in names):
            raise RuntimeError("plugin.json not found in the archive")
        staging = tempfile.mkdtemp(prefix="ally-fix-update-", dir=os.path.dirname(plugin_dir))
        try:
            zf.extractall(staging)
            new_dir = os.path.join(staging, root)
            backup = plugin_dir + ".old"
            shutil.rmtree(backup, ignore_errors=True)
            os.rename(plugin_dir, backup)
            try:
                os.rename(new_dir, plugin_dir)
            except OSError:
                os.rename(backup, plugin_dir)
                raise
            shutil.rmtree(backup, ignore_errors=True)
        finally:
            shutil.rmtree(staging, ignore_errors=True)


async def install(zip_url: str) -> dict[str, Any]:
    plugin_dir = decky.DECKY_PLUGIN_DIR
    try:
        await asyncio.get_running_loop().run_in_executor(None, _install_sync, zip_url, plugin_dir)
    except Exception as exc:  # noqa: BLE001
        decky.logger.exception("[updater] install failed")
        return {"ok": False, "error": f"update failed: {exc}"}
    decky.logger.info("[updater] new version unpacked into %s; restarting plugin_loader", plugin_dir)
    # Restart Decky from outside our own process tree so the restart survives our exit.
    subprocess.Popen(["systemd-run", "--quiet", "--on-active=2", "systemctl", "restart", "plugin_loader"],
                     env=clean_env(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"ok": True, "error": ""}
