/* allycaps: in-memory patch of the Steam Deck-protocol controller capability mask
 * in steamclient.so. Anchored on values, not on file offsets:
 *  - 32-bit client (ubuntu12_32): the 16-byte .rodata constant {0x0160bfff, 0, 0, 0}
 *    (aligned 16) in a read-only segment;
 *  - 64-bit client (steamrt64): the mask is an immediate in code,
 *    `mov r32, 0x0160bfff; jne +5; mov r32, 0x100c7fff` (the second value is the
 *    Legion Go S mask), in an executable segment; the first immediate is patched.
 * The patch is done only when the two anchors together match exactly once.
 * Env: ALLYCAPS_MASK=0x... (new low-32 value, default 0x160afff = clear TRACKPAD bit 12)
 *      ALLYCAPS_LOG=/path (default $HOME/.local/state/allycaps.log)
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <link.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/mman.h>
#include <stdarg.h>
#include <time.h>
#include <pthread.h>

static const uint8_t PATTERN[16] = {0xff,0xbf,0x60,0x01, 0,0,0,0, 0,0,0,0, 0,0,0,0};
/* B8+r <0x0160bfff> 75 05 B8+r <0x100c7fff>; [0] and [7] are checked separately */
static const uint8_t CODE[12] = {0xb8,0xff,0xbf,0x60,0x01, 0x75,0x05, 0xb8,0xff,0x7f,0x0c,0x10};
static int g_active = 0, g_done = 0;
static pthread_mutex_t g_mu = PTHREAD_MUTEX_INITIALIZER; /* dlopen() is called from several threads */
static uint32_t g_newmask = 0x0160afff;
static char g_log[512];

static void logf_(const char *fmt, ...) {
    FILE *f = fopen(g_log, "a");
    if (!f) return;
    time_t t = time(NULL); struct tm tm; localtime_r(&t, &tm);
    char ts[32]; strftime(ts, sizeof ts, "%F %T", &tm);
    fprintf(f, "[%s] [%d] ", ts, getpid());
    va_list ap; va_start(ap, fmt); vfprintf(f, fmt, ap); va_end(ap);
    fputc('\n', f); fclose(f);
}

struct scan { uintptr_t hit; int count; int seen; int exec; };

static int code_match(const uint8_t *p) {
    return p[0] >= 0xb8 && p[0] <= 0xbf && p[7] == p[0] &&
           memcmp(p + 1, CODE + 1, 6) == 0 && memcmp(p + 8, CODE + 8, 4) == 0;
}

static int cb(struct dl_phdr_info *info, size_t size, void *data) {
    (void)size;
    struct scan *s = data;
    const char *name = info->dlpi_name ? info->dlpi_name : "";
    if (!strstr(name, "steamclient.so")) return 0;
    s->seen = 1;
    for (int i = 0; i < info->dlpi_phnum; i++) {
        const ElfW(Phdr) *ph = &info->dlpi_phdr[i];
        if (ph->p_type != PT_LOAD || !(ph->p_flags & PF_R) || (ph->p_flags & PF_W)) continue;
        uintptr_t start = info->dlpi_addr + ph->p_vaddr;
        uintptr_t end = start + ph->p_memsz;
        if (ph->p_flags & PF_X) {
            for (uintptr_t p = start; p + sizeof CODE <= end; p++) {
                if (code_match((const uint8_t *)p)) { s->count++; s->hit = p + 1; s->exec = 1; }
            }
        } else {
            for (uintptr_t p = (start + 15) & ~(uintptr_t)15; p + 16 <= end; p += 16) {
                if (memcmp((void *)p, PATTERN, 16) == 0) { s->count++; s->hit = p; s->exec = 0; }
            }
        }
    }
    return 0;
}

static void try_patch_locked(const char *why) {
    if (g_done) return;
    struct scan s = {0, 0, 0, 0};
    dl_iterate_phdr(cb, &s);
    if (!s.seen) return;
    g_done = 1;
    if (s.count != 1) { logf_("%s: pattern hits=%d, NOT patching", why, s.count); return; }
    uintptr_t page = s.hit & ~(uintptr_t)(sysconf(_SC_PAGESIZE) - 1);
    size_t len = (s.hit + 4) - page;  /* the immediate in code is unaligned and may straddle pages */
    int prot = PROT_READ | (s.exec ? PROT_EXEC : 0);
    if (mprotect((void *)page, len, prot | PROT_WRITE) != 0) { logf_("%s: mprotect RW failed", why); return; }
    uint32_t old;
    memcpy(&old, (void *)s.hit, 4);
    memcpy((void *)s.hit, &g_newmask, 4);
    mprotect((void *)page, len, prot);
    uint32_t now;
    memcpy(&now, (void *)s.hit, 4);
    logf_("%s: patched caps const (%s) at %p: 0x%x -> 0x%x", why, s.exec ? "code" : "rodata",
          (void *)s.hit, old, now);
}

static void try_patch(const char *why) {
    if (g_done) return;
    pthread_mutex_lock(&g_mu);
    try_patch_locked(why);
    pthread_mutex_unlock(&g_mu);
}

typedef void *(*dlopen_t)(const char *, int);
static int g_trace = 0;

void *dlopen(const char *file, int mode) {
    static dlopen_t real = NULL;
    if (!real) real = (dlopen_t)dlsym(RTLD_NEXT, "dlopen");
    void *h = real(file, mode);
    /* steamclient.so may arrive as a dependency of some other dlopen'ed object,
     * so rescan after every successful dlopen until the patch is done. */
    if (g_active && !g_done && h) {
        if (g_trace) logf_("dlopen(%s)", file ? file : "(null)");
        try_patch("dlopen");
    }
    return h;
}

__attribute__((constructor)) static void init(void) {
    char exe[512]; ssize_t n = readlink("/proc/self/exe", exe, sizeof exe - 1);
    if (n <= 0) return;
    exe[n] = 0;
    const char *base = strrchr(exe, '/'); base = base ? base + 1 : exe;
    if (strcmp(base, "steam") != 0) return;   /* not the client process (games inherit LD_PRELOAD) */
    const char *l = getenv("ALLYCAPS_LOG"), *h = getenv("HOME");
    if (l) snprintf(g_log, sizeof g_log, "%s", l);
    else snprintf(g_log, sizeof g_log, "%s/.local/state/allycaps.log", h ? h : "/tmp");
    g_trace = getenv("ALLYCAPS_TRACE") != NULL;
    const char *m = getenv("ALLYCAPS_MASK");
    if (m) g_newmask = (uint32_t)strtoul(m, NULL, 0);
    g_active = 1;
    logf_("loaded in %s, target mask 0x%x", exe, g_newmask);
    try_patch("init");
}
