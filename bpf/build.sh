#!/bin/bash
# Build bin/ally_ff.bpf.o from bpf/ally_ff.bpf.c.
#
# Needs podman and a host kernel with BTF (/sys/kernel/btf/vmlinux) that has the
# HID-BPF struct_ops hooks — SteamOS 6.16-valve does. The object is CO-RE, so it
# does not have to be rebuilt for other kernels; commit the result.
set -euo pipefail
cd "$(dirname "$0")/.."
IMG=ally-fix-bpf
podman image exists "$IMG" || podman build -t "$IMG" -f bpf/Containerfile bpf
mkdir -p bin
podman run --rm --userns=keep-id -w /w \
  -v "$PWD:/w" -v /sys/kernel/btf/vmlinux:/vmlinux:ro "$IMG" bash -ec '
    bpftool btf dump file /vmlinux format c > /tmp/vmlinux.h
    grep -q "struct hid_bpf_ops {" /tmp/vmlinux.h || { echo "host kernel has no hid_bpf_ops in BTF"; exit 1; }
    clang -O2 -g -target bpf -D__TARGET_ARCH_x86 -I/tmp -Wall -Werror \
      -c bpf/ally_ff.bpf.c -o bin/ally_ff.bpf.o
    llvm-strip -g bin/ally_ff.bpf.o
  '
ls -l bin/ally_ff.bpf.o
