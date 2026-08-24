// SPDX-License-Identifier: GPL-2.0-or-later
/* Ally Fix — force-feedback packet filter for the ROG Xbox Ally X.
 *
 * hid_asus_ally sends every evdev FF_RUMBLE to the controller's gamepad interface
 * as feature report 0x0D in the Xbox GIP rumble layout:
 *
 *   0D | enable | LT | RT | strong (left grip) | weak (right grip) | sustain | release | loop
 *
 * with magnitudes scaled to 0..127 while the MCU expects 0..100 (101..127 buzz
 * audibly with Enhanced Vibration on) and the trigger bytes always 0. This program
 * sits on the hid_hw_request hook and rewrites the packet on its way out:
 *
 *   ALLY_FF_CLAMP   clamp all four magnitudes to 100
 *   ALLY_FF_MIRROR  copy the grip magnitudes onto the impulse triggers (LT <- strong,
 *                   RT <- weak, always clamped to 100) so ordinary rumble shakes the
 *                   triggers as well
 *
 * The flags and the target hid device are patched in by the loader
 * (py_modules/allyfix/hidbpf.py) before the object is loaded. Built by bpf/build.sh
 * into bin/ally_ff.bpf.o. GPL because it calls the hid_bpf_get_data kfunc.
 */
#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>

#define FF_REPORT_ID 0x0D
#define FF_PACKET_LEN 6 /* report id .. weak */
#define MAX_MAGNITUDE 100
#define ENABLE_TRIGGERS 0x03 /* bit0 = LT, bit1 = RT, bit2/bit3 = grips (verified on device) */

#define ALLY_FF_CLAMP 1u
#define ALLY_FF_MIRROR 2u

/* .rodata; written by the loader before bpf_object__load(). */
const volatile __u32 ally_ff_flags = 0;

extern __u8 *hid_bpf_get_data(struct hid_bpf_ctx *ctx, unsigned int offset,
			      const size_t rdwr_buf_size) __ksym;

static __always_inline __u8 clamp_mag(__u8 v)
{
	return v > MAX_MAGNITUDE ? MAX_MAGNITUDE : v;
}

SEC("struct_ops/hid_hw_request")
int BPF_PROG(ally_ff_request, struct hid_bpf_ctx *hctx, unsigned char reportnum,
	     enum hid_report_type rtype, enum hid_class_request reqtype, __u64 source)
{
	__u8 *d;

	if (reportnum != FF_REPORT_ID || rtype != HID_FEATURE_REPORT ||
	    reqtype != HID_REQ_SET_REPORT)
		return 0;
	d = hid_bpf_get_data(hctx, 0, FF_PACKET_LEN);
	if (!d)
		return 0;

	if (ally_ff_flags & ALLY_FF_CLAMP) {
		d[2] = clamp_mag(d[2]);
		d[3] = clamp_mag(d[3]);
		d[4] = clamp_mag(d[4]);
		d[5] = clamp_mag(d[5]);
	}
	if (ally_ff_flags & ALLY_FF_MIRROR) {
		d[2] = clamp_mag(d[4]);
		d[3] = clamp_mag(d[5]);
		d[1] |= ENABLE_TRIGGERS;
	}
	return 0;
}

SEC(".struct_ops.link")
struct hid_bpf_ops ally_ff = {
	.hid_id = 0, /* patched by the loader */
	.hid_hw_request = (void *)ally_ff_request,
};

char _license[] SEC("license") = "GPL";
