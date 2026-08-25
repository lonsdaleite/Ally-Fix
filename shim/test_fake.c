#include <stdint.h>
__attribute__((aligned(16), used))
const uint8_t fake_caps_const[16] = {0xff,0xbf,0x60,0x01, 0,0,0,0, 0,0,0,0, 0,0,0,0};
uint32_t fake_read(void) { return *(const uint32_t *)fake_caps_const; }
