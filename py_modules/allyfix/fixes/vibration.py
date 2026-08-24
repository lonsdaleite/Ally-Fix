"""Vibration Fix: lower grip-motor vibration intensity and keep it applied.

The MCU takes intensity as a percentage 0..100 per motor (firmware default
100/100), via feature report `5A D1 06` on the config interface — the same
command the hid_asus_ally driver uses. We send it there directly. The driver's
sysfs attribute caps values at 64 (a decimal/hex slip: its own init value is
0x64 = 100) and its store handler synchronously forwards its copy to the MCU,
so the sysfs mirror is written first (full value; capped to 64 only if the
kernel still rejects it) and the real value goes out last and wins. The MCU echoes the last accepted
command back through a GET of the same feature report, which confirms
delivery; concurrent rumble traffic (0x0D) shares that echo, so an
unconfirmed send is retried.

The controller is reset by suspend (a `usb 1-4: reset` on resume — seen after
naps of a few seconds as well as after hours; warm reboots keep it), which
resets both the intensity and the Enhanced Vibration flag, and it can come
back at an unpredictable moment after resume — so on resume the settings are
re-sent as a spaced series of idempotent writes, not a single shot. That reset
raises no hid uevents (same device, no re-enumeration), so detecting the
resume itself is what triggers the series.

The driver's outgoing rumble packets (feature report 0x0D on the gamepad
interface) are optionally rewritten by a HID-BPF program (`hidbpf.py`,
bin/ally_ff.bpf.o): magnitudes clamped to the MCU's 0..100 while Enhanced
Vibration is on (the driver scales evdev FF to 0..127, and 101..127 buzz under
enhanced), and/or the grip magnitudes mirrored onto the impulse triggers. The
program is attached per hid device, so it is re-attached whenever the
controller re-enumerates.
"""

from __future__ import annotations

import asyncio
import fcntl
import glob
import os
import struct
import time
from typing import Any

import decky

from .. import hidbpf
from .. import settings as cfg
from ..base import Fix, cancel_task
from ..device import has_impulse_triggers
from ..sysfs import read_str, write_str

DRIVER_GLOB = "/sys/module/hid_asus_ally/drivers/hid:asus_rog_ally/*/vibration_intensity"
HIDRAW_GLOB = "/sys/class/hidraw/*/device/vibration_intensity"
MAX_INTENSITY = 100
SYSFS_MAX = 64  # kernel store handler limit
FACTORY = (MAX_INTENSITY, MAX_INTENSITY)
DEFAULT = (50, 50)
REBIND_DELAYS_S = (1.0, 2.0, 3.0, 4.0, 5.0)  # cumulative ~1/3/6/10/15s after the trigger

# evdev force feedback (for the test rumble)
_EVIOCGBIT_FF = 0x80204535
_EVIOCSFF = 0x40304580
_EVIOCRMFF = 0x40044581
# MCU config command, same as hid-asus-ally.h: report 0x5A, xpad config class 0xD1,
# xpad_cmd_set_vibe_intensity, xpad_cmd_len_vibe_intensity, then LEFT RIGHT.
_FEATURE_REPORT_ID = 0x5A
_XPAD_CONFIG = 0xD1
_XPAD_CMD_SET_VIBE_INTENSITY = 0x06
_XPAD_CMD_LEN_VIBE_INTENSITY = 0x02
# "Use Xbox-recommended vibration waveform" (Armoury Crate's Enhanced Vibration),
# boolean. Kept by the MCU across warm reboots and OS switches, lost with the suspend reset.
_XPAD_CMD_SET_ENHANCED = 0x1F
_FEATURE_REPORT_SIZE = 64
_HIDIOCSFEATURE = 0xC0000000 | (_FEATURE_REPORT_SIZE << 16) | (ord("H") << 8) | 0x06
_HIDIOCGFEATURE = 0xC0000000 | (_FEATURE_REPORT_SIZE << 16) | (ord("H") << 8) | 0x07
_ECHO_TRIES = 3
_EV_FF = 0x15
_FF_RUMBLE = 0x50
_ASUS_VENDOR = ":0B05:"


def _clamp(v: Any, lo: int = 0, hi: int = MAX_INTENSITY) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return lo


def _sysfs_path() -> str | None:
    for pattern in (DRIVER_GLOB, HIDRAW_GLOB):
        found = sorted(glob.glob(pattern))
        if found:
            return found[0]
    return None


def _hidraw_node() -> str | None:
    """/dev/hidrawN of the config interface that owns the sysfs attribute."""
    attr = _sysfs_path()
    if attr is None:
        return None
    for node in sorted(glob.glob(os.path.join(os.path.dirname(attr), "hidraw", "hidraw*"))):
        return "/dev/" + os.path.basename(node)
    return None


def _find_ff_device() -> str | None:
    """Pick an evdev node with FF_RUMBLE, preferring the ASUS/Ally gamepad."""
    candidates: list[tuple[int, str]] = []
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        except OSError:
            continue
        try:
            buf = bytearray(32)
            fcntl.ioctl(fd, _EVIOCGBIT_FF, buf)
            if not (buf[_FF_RUMBLE // 8] >> (_FF_RUMBLE % 8)) & 1:
                continue
        except OSError:
            continue
        finally:
            os.close(fd)
        name = read_str(f"/sys/class/input/{os.path.basename(path)}/device/name", "") or ""
        score = 2 if ("ASUS" in name.upper() or "ALLY" in name.upper()) else 1
        candidates.append((score, path))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _gamepad_hid_id() -> int | None:
    """Numeric hid id of the interface that owns the FF evdev node
    (`0003:0B05:1B4C.0006` -> 6); changes when the controller re-enumerates."""
    ev = _find_ff_device()
    if ev is None:
        return None
    hid_dir = os.path.realpath(f"/sys/class/input/{os.path.basename(ev)}/device/device")
    name = os.path.basename(hid_dir)  # bus:vendor:product.id
    if _ASUS_VENDOR not in name.upper():
        return None  # a virtual pad (uhid) would take the attach and filter nothing
    try:
        return int(name.rsplit(".", 1)[1], 16)
    except (IndexError, ValueError):
        return None


class VibrationFix(Fix):
    id = "vibration"
    title = "Vibration Fix"

    def __init__(self) -> None:
        super().__init__()
        self._uevent = None  # set by plugin
        self._rebind_task: asyncio.Task | None = None
        self._hw: tuple[int, int] | None = None  # last value sent to the MCU (sysfs holds only the capped mirror)
        self._ff_filter: hidbpf.FfFilter | None = None
        self._ff_error = ""
        self._ff_stale = False  # the hid device was re-created; re-attach even if the id repeats

    # --- options -------------------------------------------------------
    @property
    def intensity(self) -> tuple[int, int]:
        return _clamp(cfg.get(self.id, "left", DEFAULT[0])), _clamp(cfg.get(self.id, "right", DEFAULT[1]))

    @property
    def linked(self) -> bool:
        return bool(cfg.get(self.id, "linked", True))

    @property
    def enhanced(self) -> bool:
        return bool(cfg.get(self.id, "enhanced", False))

    @property
    def mirror_triggers(self) -> bool:
        return bool(cfg.get(self.id, "mirror_triggers", False)) and has_impulse_triggers()

    async def set_enhanced(self, on: bool) -> None:
        """Independent of the intensity fix and of `enabled`. The MCU keeps the
        flag only until the suspend reset (it survives warm reboots, not sleep),
        so an enabled flag is re-sent on start/resume/rebind. A disabled flag is
        never pushed automatically — only here and on uninstall — so a value set
        from Windows is left alone. While on, the FF filter clamps magnitudes."""
        confirmed = self._send_feature(_XPAD_CMD_SET_ENHANCED, bytes([1 if on else 0]))
        cfg.update(self.id, {"enhanced": bool(on)})
        decky.logger.info("[vibration] enhanced vibration %s%s",
                          "on" if on else "off", "" if confirmed else " (echo unconfirmed)")
        self._sync_ff_filter()

    async def set_mirror_triggers(self, on: bool) -> None:
        """Mirror grip rumble onto the impulse triggers (Xbox Ally X only). Pure
        host-side rewrite, nothing is stored in the controller."""
        cfg.update(self.id, {"mirror_triggers": bool(on)})
        self._sync_ff_filter()
        if on and self._ff_error:
            error = self._ff_error
            cfg.update(self.id, {"mirror_triggers": False})
            self._sync_ff_filter()
            raise OSError(error)
        decky.logger.info("[vibration] trigger mirroring %s", "on" if on else "off")

    # --- FF packet filter (HID-BPF) ---------------------------------------
    def _ff_flags(self) -> int:
        flags = 0
        if self.enhanced:
            flags |= hidbpf.FLAG_CLAMP
        if self.mirror_triggers:
            flags |= hidbpf.FLAG_MIRROR
        return flags

    def _sync_ff_filter(self, force: bool = False) -> None:
        """Bring the attached program in line with the settings: detach when
        nothing is wanted, (re)attach when the flags or the hid device changed."""
        flags = self._ff_flags()
        hid_id = _gamepad_hid_id() if flags else None
        cur = self._ff_filter
        force = force or self._ff_stale  # a re-created hid device may reuse its id
        if cur is not None and not force and cur.flags == flags and cur.hid_id == hid_id:
            return
        if cur is not None:
            cur.close()
            self._ff_filter = None
            decky.logger.info("[vibration] ff filter detached from hid %d", cur.hid_id)
        if not flags:
            self._ff_stale = False
            self._set_ff_error("")
            return
        if hid_id is None:
            self._set_ff_error("gamepad hid device not found")
            return
        try:
            self._ff_filter = hidbpf.attach(hid_id, flags)
        except Exception as exc:  # noqa: BLE001
            self._set_ff_error(f"ff filter not loaded: {exc}")
            return
        self._ff_stale = False
        self._set_ff_error("")
        decky.logger.info("[vibration] ff filter attached to hid %d (%s)", hid_id, hidbpf.flags_name(flags))

    def _set_ff_error(self, error: str) -> None:
        if error and error != self._ff_error:
            decky.logger.warning("[vibration] %s", error)
        self._ff_error = error

    def _close_ff_filter(self) -> None:
        if self._ff_filter is not None:
            self._ff_filter.close()
            self._ff_filter = None

    def _resend_enhanced(self) -> None:
        if not self.enhanced:
            return
        if not self._send_feature(_XPAD_CMD_SET_ENHANCED, b"\x01"):
            decky.logger.warning("[vibration] enhanced re-send, echo unconfirmed")

    def set_options(self, opts: dict[str, Any]) -> None:
        values: dict[str, Any] = {}
        if "linked" in opts:
            values["linked"] = bool(opts["linked"])
        if "left" in opts:
            values["left"] = _clamp(opts["left"])
        if "right" in opts:
            values["right"] = _clamp(opts["right"])
        linked = values.get("linked", self.linked)
        if linked:
            if "left" in values:
                values["right"] = values["left"]
            elif "right" in values:
                values["left"] = values["right"]
        if values:
            cfg.update(self.id, values)

    # --- Fix interface ---------------------------------------------------
    def supported(self) -> tuple[bool, str]:
        if _sysfs_path() is None:
            return False, "hid_asus_ally driver not found"
        return True, ""

    def _read_hw(self) -> tuple[int, int] | None:
        if self._hw is not None:
            return self._hw
        # Fresh boot / re-enumeration: the driver's placeholder 100/100 matches the MCU default.
        path = _sysfs_path()
        if path is None:
            return None
        raw = read_str(path)
        if not raw:
            return None
        try:
            left, right = (int(x) for x in raw.split()[:2])
            return left, right
        except ValueError:
            return None

    def _write_hw(self, left: int, right: int) -> None:
        # sysfs first: the driver's store synchronously forwards its (capped) copy
        # to the MCU, so our direct write below must come last to win.
        path = _sysfs_path()
        if path is None:
            raise OSError("vibration_intensity sysfs attribute not found")
        try:
            write_str(path, f"{left} {right}\n")
        except OSError as exc:
            capped = (min(left, SYSFS_MAX), min(right, SYSFS_MAX))
            if capped == (left, right):
                decky.logger.warning("[vibration] sysfs mirror write failed: %s", exc)
            else:
                # kernel store still has the `> 64` slip — mirror what it allows
                try:
                    write_str(path, "%d %d\n" % capped)
                except OSError as exc2:
                    decky.logger.warning("[vibration] sysfs mirror write failed: %s", exc2)
        confirmed = self._send_feature(_XPAD_CMD_SET_VIBE_INTENSITY, bytes([left, right]))
        self._hw = (left, right)
        if not confirmed:
            decky.logger.warning("[vibration] intensity %d/%d sent, echo unconfirmed", left, right)

    @staticmethod
    def _send_feature(cmd: int, data: bytes) -> bool:
        """Send `5A D1 <cmd> <len> <data…>` as a feature report on the config
        interface and confirm delivery: the MCU echoes the last accepted command
        back through a GET of the same report. Rumble traffic (0x0D) shares the
        echo and can clobber it between our SET and GET, hence a few tries.
        Returns whether the echo confirmed the command; the send itself raises
        OSError on failure."""
        node = _hidraw_node()
        if node is None:
            raise OSError("hidraw node for the config interface not found")
        packet = bytes([_FEATURE_REPORT_ID, _XPAD_CONFIG, cmd, len(data)]) + data
        fd = os.open(node, os.O_RDWR)
        try:
            for _ in range(_ECHO_TRIES):
                buf = bytearray(_FEATURE_REPORT_SIZE)
                buf[: len(packet)] = packet
                fcntl.ioctl(fd, _HIDIOCSFEATURE, buf)
                echo = bytearray(_FEATURE_REPORT_SIZE)
                echo[0] = _FEATURE_REPORT_ID
                try:
                    fcntl.ioctl(fd, _HIDIOCGFEATURE, echo)
                except OSError:
                    return False  # echo unreadable; the SET itself went through
                if bytes(echo[: len(packet)]) == packet:
                    return True
        finally:
            os.close(fd)
        return False

    def is_applied(self) -> bool:
        return self._read_hw() == self.intensity

    async def apply(self) -> None:
        left, right = self.intensity
        self._write_hw(left, right)
        decky.logger.info("[vibration] intensity set to %d/%d", left, right)

    async def revert(self) -> None:
        self._write_hw(*FACTORY)
        decky.logger.info("[vibration] intensity restored to factory %d/%d", *FACTORY)

    def details(self) -> dict[str, Any]:
        hw = self._read_hw()
        left, right = self.intensity
        return {
            "left": left,
            "right": right,
            "linked": self.linked,
            "enhanced": self.enhanced,
            "mirror_triggers": self.mirror_triggers,
            "hw_left": hw[0] if hw else None,
            "hw_right": hw[1] if hw else None,
            "sysfs": _sysfs_path(),
            "ff_filter": hidbpf.flags_name(self._ff_filter.flags) if self._ff_filter else "off",
            "ff_error": self._ff_error,
        }

    def _wants_controller(self) -> bool:
        return self.enabled or self.enhanced or self.mirror_triggers

    def needs_resume(self) -> bool:
        return self._wants_controller()

    async def reapply_if_enabled(self) -> None:
        await super().reapply_if_enabled()
        if self.enhanced and self.supported()[0]:
            try:
                self._resend_enhanced()
            except OSError as exc:
                decky.logger.warning("[vibration] enhanced re-send failed: %s", exc)

    async def on_resume(self) -> None:
        self._hw = None
        self._schedule_rebind("resume")

    async def start_background(self) -> None:
        if self._uevent is not None:
            self._uevent.subscribe("hid", self._on_hid_event)
        self._sync_ff_filter()

    async def stop_background(self) -> None:
        if self._uevent is not None:
            self._uevent.unsubscribe("hid", self._on_hid_event)
        await cancel_task(self._rebind_task)
        self._rebind_task = None
        self._close_ff_filter()

    async def _on_hid_event(self, event: dict[str, str]) -> None:
        if not self._wants_controller():
            return
        if event.get("ACTION") not in ("add", "bind"):
            return
        if "asus" not in event.get("DRIVER", "").lower() and "0B05" not in event.get("HID_ID", "").upper():
            return
        self._hw = None
        self._ff_stale = True
        self._schedule_rebind(f"hid {event.get('ACTION')}")

    def _schedule_rebind(self, reason: str) -> None:
        if self._rebind_task is not None and not self._rebind_task.done():
            return
        self._rebind_task = asyncio.get_running_loop().create_task(self._rebind(reason))

    async def _rebind(self, reason: str) -> None:
        """The controller can reset at an unpredictable moment after resume (its
        power comes back late), so a single write is not enough: send the whole
        spaced series unconditionally — the writes are idempotent, and the last
        one lands well after the controller has settled."""
        sent = failed = 0
        for delay in REBIND_DELAYS_S:
            await asyncio.sleep(delay)
            if not self._wants_controller():
                return
            self._sync_ff_filter()
            if not (self.enabled or self.enhanced):
                continue
            try:
                if self.enabled:
                    self._write_hw(*self.intensity)
                self._resend_enhanced()
                sent += 1
            except OSError as exc:
                failed += 1
                decky.logger.warning("[vibration] re-apply after %s failed: %s", reason, exc)
        if sent:
            self.last_error = ""
            parts = []
            if self.enabled:
                parts.append("intensity %d/%d" % self.intensity)
            if self.enhanced:
                parts.append("enhanced on")
            decky.logger.info("[vibration] re-applied after %s: %s (%d/%d sends ok)",
                              reason, ", ".join(parts), sent, sent + failed)
        elif self.enabled or self.enhanced:
            self.last_error = f"could not re-apply vibration settings after {reason}"
        await self.notify()

    # --- test rumble -----------------------------------------------------
    async def test(self, duration_ms: int = 500) -> None:
        """Fire a short FF_RUMBLE so the user can feel the current intensity."""
        # 0xC800 goes out on the wire as magnitude 100 (/512) — the MCU's full scale,
        # so what the user feels is the intensity scaling alone. 0xFFFF would be sent
        # as 127, out of range, and buzzes audibly with Enhanced Vibration on.
        duration = max(100, min(2000, int(duration_ms)))
        strong = weak = 100 * 512
        ff_path = _find_ff_device()
        if ff_path is None:
            raise OSError("no rumble-capable input device found")
        fd = os.open(ff_path, os.O_RDWR)
        try:
            # struct ff_effect (48 bytes) for FF_RUMBLE: type, id(-1 → kernel assigns),
            # direction, trigger{button, interval}, replay{length, delay}, pad,
            # rumble{strong, weak}, union padding.
            effect = bytearray(struct.pack("<HhHHHHHxxHH28x", _FF_RUMBLE, -1, 0, 0, 0, duration, 0, strong, weak))
            fcntl.ioctl(fd, _EVIOCSFF, effect)
            effect_id = struct.unpack_from("<h", effect, 2)[0]

            def ev(value: int) -> bytes:
                t = time.time()
                return struct.pack("<qqHHi", int(t), int((t % 1) * 1e6), _EV_FF, effect_id, value)

            os.write(fd, ev(1))
            await asyncio.sleep(duration / 1000.0)
            os.write(fd, ev(0))
            # EVIOCRMFF takes the id by value, not a pointer
            fcntl.ioctl(fd, _EVIOCRMFF, effect_id)
        finally:
            os.close(fd)
        decky.logger.info("[vibration] test rumble %dms via %s (hw %s)", duration, ff_path, self._read_hw())
