#!/bin/bash
# Build bin/liballycaps.so (32-bit) and bin/liballycaps64.so from shim/allycaps.c and run
# the offline test stand.
#
# The shim is a 32-bit LD_PRELOAD library for Steam's `steam` process (the client is
# still 32-bit); it needs gcc-multilib, which SteamOS does not ship, so it is built in
# a Debian container. The result does not depend on the Steam build (it looks for the
# capability constant by value); commit it.
#
# Test stand (shim/test_*.c): a fake steamclient with the same 16-byte constant, pulled
# in as DT_NEEDED by a wrapper that a binary named `steam` dlopen()s — the same shape
# as the real client, where steamclient.so never shows up in dlopen() by name.
set -euo pipefail
cd "$(dirname "$0")/.."
IMG=ally-fix-shim
podman image exists "$IMG" || podman build -t "$IMG" -f shim/Containerfile shim
mkdir -p bin
podman run --rm --userns=keep-id -w /w -v "$PWD:/w" "$IMG" bash -ec '
  gcc -m32 -O2 -Wall -Wextra -fPIC -shared -s -pthread -o bin/liballycaps.so shim/allycaps.c
  # 64-bit twin for the $LIB scheme (see fixes/gamepad_layout.py): same source, never
  # active — no 64-bit process is called `steam`.
  gcc -m64 -O2 -Wall -Wextra -fPIC -shared -s -pthread -o bin/liballycaps64.so shim/allycaps.c
  t=$(mktemp -d)
  gcc -m32 -O2 -fPIC -shared -o "$t/steamclient.so" shim/test_fake.c
  gcc -m32 -O2 -fPIC -shared -o "$t/libtest_wrap.so" shim/test_wrap.c -L"$t" -l:steamclient.so -Wl,-rpath,"$t"
  gcc -m32 -O2 -o "$t/steam" shim/test_main.c -ldl
  cd "$t"
  out=$(ALLYCAPS_MASK=0x60afff ALLYCAPS_LOG="$t/log" LD_PRELOAD=/w/bin/liballycaps.so ./steam)
  echo "$out"; cat "$t/log"
  [ "$out" = "runtime read of constant: 0x60afff" ] || { echo "shim test FAILED"; exit 1; }
  mv steam not-steam
  out=$(ALLYCAPS_MASK=0x60afff ALLYCAPS_LOG="$t/log2" LD_PRELOAD=/w/bin/liballycaps.so ./not-steam)
  [ "$out" = "runtime read of constant: 0x160bfff" ] && [ ! -e "$t/log2" ] || { echo "shim must be a no-op outside the steam process"; exit 1; }
  echo "shim test OK"
'
ls -l bin/liballycaps.so bin/liballycaps64.so
