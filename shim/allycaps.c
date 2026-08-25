/* allycaps: in-memory patch of the Steam Deck-protocol controller capability mask
 * in steamclient.so (32-bit). Anchored on the 16-byte .rodata constant
 * {0x0160bfff, 0, 0, 0} (aligned 16), not on file offsets.
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

struct scan { uintptr_t hit; int count; int seen; };

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
        for (uintptr_t p = (start + 15) & ~(uintptr_t)15; p + 16 <= end; p += 16) {
            if (memcmp((void *)p, PATTERN, 16) == 0) { s->count++; s->hit = p; }
        }
    }
    return 0;
}

static void try_patch_locked(const char *why) {
    if (g_done) return;
    struct scan s = {0, 0, 0};
    dl_iterate_phdr(cb, &s);
    if (!s.seen) return;
    g_done = 1;
    if (s.count != 1) { logf_("%s: pattern hits=%d, NOT patching", why, s.count); return; }
    uintptr_t page = s.hit & ~(uintptr_t)(sysconf(_SC_PAGESIZE) - 1);
    size_t len = (s.hit + 16) - page;
    if (mprotect((void *)page, len, PROT_READ | PROT_WRITE) != 0) { logf_("%s: mprotect RW failed", why); return; }
    uint32_t old = *(uint32_t *)s.hit;
    *(uint32_t *)s.hit = g_newmask;
    mprotect((void *)page, len, PROT_READ);
    logf_("%s: patched caps const at %p: 0x%x -> 0x%x", why, (void *)s.hit, old, *(uint32_t *)s.hit);
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
