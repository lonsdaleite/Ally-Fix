"""Gamepad Layout Fix: hide the inputs the ROG Xbox Ally does not have from Steam Input.

Steam builds the Ally's capability mask from a constant in `steamclient.so` and treats
the controller as one with trackpads, capacitive sticks and four rear buttons. The fix
has two layers:

* Native: `bin/liballycaps.so`, an LD_PRELOAD shim for the `steam` process that patches
  the capability constant in memory (TRACKPAD and CAPJOYSTICK bits cleared). It reaches
  the client through a drop-in of `steam-launcher.service`, so it is only in effect
  after the service (re)starts. This layer changes what the client *thinks* (config
  templates, gyro activator defaults), not just what it draws.
* UI: the frontend edits Steam's button metadata table and clears the GRIPS bit on the
  controller objects, which removes the lower rear pair (L5/R5) — the native mask
  cannot express "upper pair only". The result of that patch is reported back here.

Both layers fail towards stock: an unmatched constant or a missing table entry leaves
the client as it was.
"""

from __future__ import annotations

import glob
import os
import shlex
from typing import Any

import decky

from .. import steam
from ..base import Fix, FixStatus
from ..device import SUPPORTED_BOARDS
from ..sysfs import dmi_board

LIB_NAME = "liballycaps.so"
# LD_PRELOAD splits on spaces, and the plugin directory ("Ally Fix") has one.
LIB_DIR = os.path.join(steam.HOME, ".local", "lib", "ally-fix")
# The client is 32-bit, but LD_PRELOAD is inherited by every child of the service, most of
# them 64-bit (steamwebhelper, games); a single 32-bit path would make each of those print
# a "wrong ELF class" line. So the variable carries the `$LIB` token, which ld.so expands
# to `lib32` in 32-bit processes and `lib` in 64-bit ones, and a 64-bit build of the same
# shim (a no-op outside the `steam` process) sits at the other end.
LIBS = {
    os.path.join(LIB_DIR, "lib32", LIB_NAME): os.path.join(decky.DECKY_PLUGIN_DIR, "bin", LIB_NAME),
    os.path.join(LIB_DIR, "lib", LIB_NAME): os.path.join(decky.DECKY_PLUGIN_DIR, "bin", "liballycaps64.so"),
}
PRELOAD_ENTRY = os.path.join(LIB_DIR, "$LIB", LIB_NAME)
LEGACY_LIB = os.path.join(LIB_DIR, LIB_NAME)  # pre-release layout: one 32-bit file, no $LIB
DROPIN = os.path.join(steam.DROPIN_DIR, "zz-ally-fix-gamepad-layout.conf")  # sorts last: wins
LOG = os.path.join(steam.HOME, ".local", "state", "ally-fix-allycaps.log")
STEAMCLIENT = os.path.join(steam.HOME, ".local", "share", "Steam", "ubuntu12_32", "steamclient.so")
MASK = 0x60AFFF  # stock 0x160bfff without TRACKPAD (bit 12) and CAPJOYSTICK (bit 24)
MARKER = "# managed by Ally Fix (Gamepad Layout Fix)"

# Where systemd looks for drop-ins of a user unit, lowest priority first; a file name
# that exists in several of them is taken from the highest one.
DROPIN_DIRS = (
    f"/usr/lib/systemd/user/{steam.SERVICE}.d",
    f"/usr/local/lib/systemd/user/{steam.SERVICE}.d",
    f"/run/systemd/user/{steam.SERVICE}.d",
    f"/etc/systemd/user/{steam.SERVICE}.d",
    steam.DROPIN_DIR,
)


def _mkdir_user(path: str) -> None:
    """mkdir -p that leaves the directories it creates owned by the user, not root."""
    missing: list[str] = []
    p = path
    while p and not os.path.isdir(p):
        missing.append(p)
        p = os.path.dirname(p)
    for d in reversed(missing):
        os.mkdir(d, 0o755)
        steam.chown_user(d)


def _write_user(path: str, data: bytes, mode: int) -> None:
    _mkdir_user(os.path.dirname(path))
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.chmod(tmp, mode)
    steam.chown_user(tmp)
    os.replace(tmp, path)


def _read(path: str) -> bytes | None:
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def _preload_from(path: str, current: list[str]) -> list[str]:
    """Apply the Environment= lines of one unit/drop-in file to an LD_PRELOAD list."""
    text = _read(path)
    if text is None:
        return current
    for line in text.decode(errors="replace").splitlines():
        key, sep, value = line.partition("=")
        if not sep or key.strip() != "Environment":
            continue
        value = value.strip()
        if not value:  # `Environment=` resets everything
            current = []
            continue
        try:
            tokens = shlex.split(value)
        except ValueError:
            continue
        for tok in tokens:
            if tok.startswith("LD_PRELOAD="):
                current = [p for p in tok[len("LD_PRELOAD="):].replace(":", " ").split() if p]
    return current


class GamepadLayoutFix(Fix):
    id = "gamepad_layout"
    title = "Gamepad Layout Fix"

    def __init__(self) -> None:
        super().__init__()
        self.ui_result: dict[str, Any] | None = None  # last report from the frontend

    # --- support --------------------------------------------------------
    def supported(self) -> tuple[bool, str]:
        board = dmi_board()
        if board not in SUPPORTED_BOARDS:
            return False, f"needs a ROG Xbox Ally (board {board or 'unknown'})"
        if not os.path.isfile(steam.UNIT_FILE):
            return False, f"{steam.SERVICE} not found (SteamOS gaming mode only)"
        if not all(os.path.isfile(src) for src in LIBS.values()):
            return False, f"{LIB_NAME} missing from the plugin"
        if not os.path.isfile(STEAMCLIENT):
            return False, "32-bit steamclient.so not found"
        return True, ""

    # --- drop-in ----------------------------------------------------------
    def _other_preload(self) -> list[str]:
        """LD_PRELOAD as the other drop-ins of the service leave it. A drop-in replaces
        the variable rather than adding to it, so ours has to repeat theirs."""
        files: dict[str, str] = {}
        for d in DROPIN_DIRS:
            for path in glob.glob(os.path.join(d, "*.conf")):
                files[os.path.basename(path)] = path  # later dirs override same-named files
        preload = _preload_from(steam.UNIT_FILE, [])
        for name in sorted(files):
            path = files[name]
            if path == DROPIN:
                continue
            preload = _preload_from(path, preload)
        return [p for p in preload if p != PRELOAD_ENTRY and not p.startswith(LIB_DIR + "/")]

    def _dropin_text(self) -> str:
        preload = ":".join([*self._other_preload(), PRELOAD_ENTRY])
        return (
            f"{MARKER}\n"
            "[Service]\n"
            f"Environment=LD_PRELOAD={preload}\n"
            f"Environment=ALLYCAPS_MASK={MASK:#x}\n"
            f"Environment=ALLYCAPS_LOG={LOG}\n"
        )

    # --- state ------------------------------------------------------------
    def _lib_current(self) -> bool:
        for dst, src in LIBS.items():
            data = _read(src)
            if data is None or _read(dst) != data:
                return False
        return True

    def _dropin_current(self) -> bool:
        return _read(DROPIN) == self._dropin_text().encode()

    def is_applied(self) -> bool:
        return self._lib_current() and self._dropin_current()

    def _shim_state(self) -> tuple[bool, bool | None]:
        """(loaded into the running client, patched the constant) — patched is None
        while the log has nothing for this process yet."""
        pids = steam.client_pids()
        if not pids:
            return False, None
        pid = pids[0]
        if not steam.client_has_mapped(pid, "/" + LIB_NAME):
            return False, None
        patched: bool | None = None
        text = _read(LOG)
        if text is not None:
            tag = f"[{pid}]"
            for line in text.decode(errors="replace").splitlines():
                if tag not in line:
                    continue
                if "patched caps const" in line:
                    patched = True
                elif "NOT patching" in line or "failed" in line:
                    patched = False
        return True, patched

    def details(self) -> dict[str, Any]:
        loaded, patched = self._shim_state()
        return {
            "dropin": DROPIN,
            "lib": LIB_DIR,
            "mask": f"{MASK:#x}",
            "native_ready": self.is_applied(),
            "shim_active": loaded,
            "shim_patched": patched,
            "ui": self.ui_result,
            "restart_pending": self.enabled != loaded,
        }

    def status(self) -> FixStatus:
        st = super().status()
        if not st.supported or st.state == "error":
            return st
        loaded = bool(st.details.get("shim_active"))
        patched = st.details.get("shim_patched")
        ui = self.ui_result
        if self.enabled and st.state == "applied":
            if not loaded:
                st.state = "restart_pending"
                st.message = "Restart Steam to apply"
            elif patched is False:
                st.state = "error"
                st.message = "capability constant not found in steamclient.so (Steam update?)"
            elif ui is not None and not ui.get("ok"):
                st.state = "error"
                st.message = f"UI patch failed: {ui.get('error') or ui.get('stage') or 'unknown'}"
        elif not self.enabled and loaded:
            st.state = "restart_pending"
            st.message = "Restart Steam to finish turning the fix off"
        return st

    # --- apply / revert ---------------------------------------------------
    async def apply(self) -> None:
        changed = False
        if os.path.exists(LEGACY_LIB):
            os.remove(LEGACY_LIB)
        for dst, src in LIBS.items():
            data = _read(src)
            if data is None:
                raise RuntimeError(f"{src} unreadable")
            if _read(dst) != data:
                _write_user(dst, data, 0o755)
                changed = True
        _mkdir_user(os.path.dirname(LOG))  # the shim only appends; it never creates the directory
        if not self._dropin_current():
            _write_user(DROPIN, self._dropin_text().encode(), 0o644)
            changed = True
        if changed:
            decky.logger.info("[gamepad_layout] drop-in written: %s", DROPIN)
            await steam.daemon_reload()

    async def revert(self) -> None:
        self.ui_result = None  # the frontend reverts its half and reports again on the next apply
        changed = False
        if os.path.exists(DROPIN):
            os.remove(DROPIN)
            changed = True
        for dst in (*LIBS, LEGACY_LIB):
            if os.path.exists(dst):
                os.remove(dst)
        for d in (os.path.dirname(p) for p in LIBS):
            try:
                os.rmdir(d)
            except OSError:
                pass
        try:
            os.rmdir(LIB_DIR)
        except OSError:
            pass
        if changed:
            decky.logger.info("[gamepad_layout] drop-in removed")
            await steam.daemon_reload()

    def report_ui(self, result: dict[str, Any] | None) -> None:
        self.ui_result = result if isinstance(result, dict) else None
        if self.ui_result and not self.ui_result.get("ok"):
            decky.logger.warning("[gamepad_layout] UI patch: %s", self.ui_result)
        else:
            decky.logger.info("[gamepad_layout] UI patch: %s", self.ui_result)
