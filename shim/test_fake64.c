/* 64-bit client shape: the mask is the immediate of `mov eax, 0x0160bfff; jne +5;
 * mov eax, 0x100c7fff` in .text; fake_caps_const labels that immediate. */
__asm__(".text\n"
        ".globl fake_read\n.type fake_read,@function\nfake_read:\n"
        "  cmpl $0x66, %edi\n"
        "  .byte 0xb8\n"
        ".globl fake_caps_const\n.type fake_caps_const,@object\nfake_caps_const:\n"
        "  .long 0x0160bfff\n"
        "  .byte 0x75, 0x05, 0xb8\n"
        "  .long 0x100c7fff\n"
        "  ret\n");
