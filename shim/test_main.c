#include <dlfcn.h>
#include <stdio.h>
#include <stdint.h>
int main(void) {
    void *h = dlopen("./libtest_wrap.so", RTLD_NOW);
    if (!h) { printf("dlopen failed: %s\n", dlerror()); return 1; }
    volatile const uint32_t *p = (volatile const uint32_t *)dlsym(h, "fake_caps_const");
    printf("runtime read of constant: 0x%x\n", p ? *p : 0);
    return 0;
}
