#!/bin/bash
# Build bin/liballycaps.so (32-bit) and bin/liballycaps64.so from shim/allycaps.c and run
# the offline test stand.
#
# The shim is an LD_PRELOAD library for Steam's `steam` process, built for both the
# 32-bit client (ubuntu12_32) and the 64-bit one (steamrt64); the 32-bit build needs
# gcc-multilib, which SteamOS does not ship, so both are built in a Debian container.
# The result does not depend on the Steam build (it looks for the capability mask by
# value); commit it.
#
# Test stand (shim/test_*.c): a fake steamclient with the mask in the shape of each
# client (test_fake.c: 16-byte .rodata constant, test_fake64.c: immediate in .text),
# pulled in as DT_NEEDED by a wrapper that a binary named `steam` dlopen()s — the same
# shape as the real client, where steamclient.so never shows up in dlopen() by name.
set -euo pipefail
cd "$(dirname "$0")/.."
IMG=ally-fix-shim
podman image exists "$IMG" || podman build -t "$IMG" -f shim/Containerfile shim
mkdir -p bin
podman run --rm --userns=keep-id -w /w -v "$PWD:/w" "$IMG" bash -ec '
  gcc -m32 -O2 -Wall -Wextra -fPIC -shared -s -pthread -o bin/liballycaps.so shim/allycaps.c
  gcc -m64 -O2 -Wall -Wextra -fPIC -shared -s -pthread -o bin/liballycaps64.so shim/allycaps.c
  # bits, shim, fake steamclient source
  run() {
    local bits=$1 shim=$2 fake=$3 t
    t=$(mktemp -d)
    gcc -m$bits -O2 -fPIC -shared -o "$t/steamclient.so" "$fake"
    gcc -m$bits -O2 -fPIC -shared -o "$t/libtest_wrap.so" shim/test_wrap.c -L"$t" -l:steamclient.so -Wl,-rpath,"$t"
    gcc -m$bits -O2 -o "$t/steam" shim/test_main.c -ldl
    cd "$t"
    out=$(ALLYCAPS_MASK=0x60afff ALLYCAPS_LOG="$t/log" LD_PRELOAD="$shim" ./steam)
    echo "[$bits] $out"; cat "$t/log"
    [ "$out" = "runtime read of constant: 0x60afff" ] || { echo "shim test FAILED ($bits-bit)"; exit 1; }
    mv steam not-steam
    out=$(ALLYCAPS_MASK=0x60afff ALLYCAPS_LOG="$t/log2" LD_PRELOAD="$shim" ./not-steam)
    [ "$out" = "runtime read of constant: 0x160bfff" ] && [ ! -e "$t/log2" ] || { echo "shim must be a no-op outside the steam process ($bits-bit)"; exit 1; }
    cd /w
  }
  run 32 /w/bin/liballycaps.so shim/test_fake.c
  run 64 /w/bin/liballycaps64.so shim/test_fake64.c
  echo "shim test OK"
'
ls -l bin/liballycaps.so bin/liballycaps64.so
