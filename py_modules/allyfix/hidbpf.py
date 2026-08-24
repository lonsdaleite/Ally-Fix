"""Load and attach the force-feedback packet filter (bin/ally_ff.bpf.o).

The object is a HID-BPF struct_ops program (see bpf/ally_ff.bpf.c) that rewrites
the driver's outgoing 0x0D rumble packets for one hid device. It is driven
through the system libbpf (SteamOS ships libbpf.so.1) over ctypes, so nothing
has to be compiled on the device; the kernel needs CONFIG_HID_BPF and BTF.

Two things are patched into the object before it is loaded: the target hid id
(the numeric suffix of the sysfs name, `0003:0B05:1B4C.0006` -> 6) into the
struct_ops map, and the behaviour flags into `.rodata`. A struct_ops link is
tied to this process — when it exits, the kernel drops the program on its own.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import POINTER, byref, c_char_p, c_int, c_size_t, c_uint, c_void_p

import decky

OBJECT_PATH = os.path.join(decky.DECKY_PLUGIN_DIR, "bin", "ally_ff.bpf.o")

# Must match bpf/ally_ff.bpf.c.
FLAG_CLAMP = 1  # magnitudes capped at 100
FLAG_MIRROR = 2  # grips copied onto the impulse triggers

_BPF_MAP_TYPE_STRUCT_OPS = 26
_libbpf: ctypes.CDLL | None = None


class HidBpfError(OSError):
    pass


def _lib() -> ctypes.CDLL:
    global _libbpf
    if _libbpf is not None:
        return _libbpf
    try:
        lib = ctypes.CDLL("libbpf.so.1", use_errno=True)
    except OSError as exc:
        raise HidBpfError(f"libbpf.so.1 not available: {exc}") from exc
    protos = {
        "bpf_object__open_file": ([c_char_p, c_void_p], c_void_p),
        "bpf_object__load": ([c_void_p], c_int),
        "bpf_object__close": ([c_void_p], None),
        "bpf_object__next_map": ([c_void_p, c_void_p], c_void_p),
        "bpf_map__name": ([c_void_p], c_char_p),
        "bpf_map__type": ([c_void_p], c_uint),
        "bpf_map__initial_value": ([c_void_p, POINTER(c_size_t)], c_void_p),
        "bpf_map__attach_struct_ops": ([c_void_p], c_void_p),
        "bpf_link__destroy": ([c_void_p], c_int),
        "libbpf_version_string": ([], c_char_p),
    }
    for name, (argtypes, restype) in protos.items():
        try:
            fn = getattr(lib, name)
        except AttributeError as exc:
            raise HidBpfError(f"libbpf.so.1 lacks {name}") from exc
        fn.argtypes = argtypes
        fn.restype = restype
    _libbpf = lib
    return lib


def available() -> tuple[bool, str]:
    if not os.path.exists(OBJECT_PATH):
        return False, "bin/ally_ff.bpf.o missing from the plugin"
    if not os.path.exists("/sys/kernel/btf/vmlinux"):
        return False, "kernel has no BTF (CONFIG_DEBUG_INFO_BTF)"
    try:
        _lib()
    except HidBpfError as exc:
        return False, str(exc)
    return True, ""


def flags_name(flags: int) -> str:
    parts = []
    if flags & FLAG_CLAMP:
        parts.append("clamp")
    if flags & FLAG_MIRROR:
        parts.append("mirror")
    return "+".join(parts) or "none"


class FfFilter:
    """One loaded and attached instance; `close()` detaches it."""

    def __init__(self, obj: int, link: int, hid_id: int, flags: int) -> None:
        self._obj = obj
        self._link = link
        self.hid_id = hid_id
        self.flags = flags

    def close(self) -> None:
        lib = _lib()
        if self._link:
            lib.bpf_link__destroy(self._link)
            self._link = 0
        if self._obj:
            lib.bpf_object__close(self._obj)
            self._obj = 0


def attach(hid_id: int, flags: int) -> FfFilter:
    ok, reason = available()
    if not ok:
        raise HidBpfError(reason)
    lib = _lib()
    obj = lib.bpf_object__open_file(OBJECT_PATH.encode(), None)
    if not obj:
        raise HidBpfError(f"open {OBJECT_PATH}: {os.strerror(ctypes.get_errno())}")
    try:
        ops_map = None
        rodata_done = False
        m = lib.bpf_object__next_map(obj, None)
        while m:
            size = c_size_t(0)
            if lib.bpf_map__type(m) == _BPF_MAP_TYPE_STRUCT_OPS:
                data = lib.bpf_map__initial_value(m, byref(size))
                if not data or size.value < ctypes.sizeof(c_int):
                    raise HidBpfError("struct_ops map has no initial value")
                c_int.from_address(data).value = hid_id  # hid_id is the first member of hid_bpf_ops
                ops_map = m
            elif (lib.bpf_map__name(m) or b"").endswith(b".rodata"):
                data = lib.bpf_map__initial_value(m, byref(size))
                if not data or size.value != ctypes.sizeof(ctypes.c_uint32):
                    raise HidBpfError(f".rodata is {size.value} bytes, expected one u32 (ally_ff_flags)")
                ctypes.c_uint32.from_address(data).value = flags
                rodata_done = True
            m = lib.bpf_object__next_map(obj, m)
        if ops_map is None or not rodata_done:
            raise HidBpfError("unexpected object layout (no struct_ops or .rodata map)")
        rc = lib.bpf_object__load(obj)
        if rc:
            raise HidBpfError(f"load rejected by the kernel: {os.strerror(-rc)}")
        link = lib.bpf_map__attach_struct_ops(ops_map)
        if not link:
            raise HidBpfError(f"attach to hid {hid_id}: {os.strerror(ctypes.get_errno())}")
    except Exception:
        lib.bpf_object__close(obj)
        raise
    return FfFilter(obj, link, hid_id, flags)
