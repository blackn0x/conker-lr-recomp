/* Per-frame cost breakdown (RECOMP_FRAME_STATS=1): see frame_stats.h. */
#include "frame_stats.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#if defined(__SWITCH__)
#include <switch.h>
#else
#include <pthread.h>
#endif

static const char *const k_tname[FS_T_N] = { "game", "exec", "rec", "pres" };

static struct {
    int set;
#if defined(__SWITCH__)
    Handle h;
#else
    clockid_t c;
#endif
    uint64_t last;
} s_t[FS_T_N];

static uint64_t s_sum[FS_N], s_max[FS_N];
static int s_on = -1;

int fs_on(void)
{
    if (s_on < 0) {
        const char *e = getenv("RECOMP_FRAME_STATS");
        s_on = e && *e == '1';
    }
    return s_on;
}

static uint64_t mono_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

static int thread_cpu_ns(int i, uint64_t *ns)
{
    if (!s_t[i].set)
        return 0;
#if defined(__SWITCH__)
    {
        u64 t;
        if (R_FAILED(svcGetInfo(&t, InfoType_ThreadTickCount, s_t[i].h, (u64)-1))
            && R_FAILED(svcGetInfo(&t, InfoType_ThreadTickCountDeprecated, s_t[i].h, (u64)-1)))
            return 0;
        *ns = t * 625 / 12;                 /* 19.2 MHz ticks */
    }
#else
    {
        struct timespec ts;
        if (clock_gettime(s_t[i].c, &ts))
            return 0;
        *ns = (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
    }
#endif
    return 1;
}

void fs_thread(int which)
{
    if (!fs_on() || which < 0 || which >= FS_T_N)
        return;
#if defined(__SWITCH__)
    s_t[which].h = threadGetCurHandle();
#else
    if (pthread_getcpuclockid(pthread_self(), &s_t[which].c))
        return;
#endif
    s_t[which].set = 1;
    thread_cpu_ns(which, &s_t[which].last);
}

void fs_add(int stat, uint64_t ns)
{
    if (stat < 0 || stat >= FS_N)
        return;
    /* ponytail: plain adds from up to two threads; a lost update skews one
     * second's average a little, not worth atomics on the hot path. */
    s_sum[stat] += ns;
    if (ns > s_max[stat])
        s_max[stat] = ns;
}

void fs_frame(unsigned draws, unsigned programs, unsigned textures)
{
    static uint64_t window, last, fmax, fsum;
    static unsigned n, ndraws, nprogs, ntex;
    uint64_t now;
    char line[512];
    int len, i;

    if (!fs_on())
        return;
    now = mono_ns();
    if (!window) {
        window = last = now;
        memset(s_sum, 0, sizeof s_sum);
        memset(s_max, 0, sizeof s_max);
        return;
    }
    if (now - last > fmax)
        fmax = now - last;
    fsum += now - last;
    last = now;
    n++;
    ndraws += draws;
    nprogs += programs;
    ntex += textures;
    if (now - window < 1000000000ull)
        return;

    len = snprintf(line, sizeof line, "[ft] %.0f fps, frame %.1f avg / %.1f max ms | cpu per frame:",
                   n * 1e9 / (double)(now - window), fsum / 1e6 / n, fmax / 1e6);
    for (i = 0; i < FS_T_N; i++) {
        uint64_t t;
        if (!thread_cpu_ns(i, &t))
            continue;
        len += snprintf(line + len, sizeof line - len, " %s %.1f", k_tname[i],
                        (t - s_t[i].last) / 1e6 / n);
        s_t[i].last = t;
    }
    len += snprintf(line + len, sizeof line - len,
                    " | game fence wait %.1f / %.1f | gpu %.1f / %.1f"
                    " | rec slot wait %.1f, acquire %.1f | %u draws, %u programs, %u textures",
                    s_sum[FS_GAME_WAIT] / 1e6 / n, s_max[FS_GAME_WAIT] / 1e6,
                    s_sum[FS_GPU] / 1e6 / n, s_max[FS_GPU] / 1e6,
                    s_sum[FS_SLOT_WAIT] / 1e6 / n, s_sum[FS_ACQUIRE] / 1e6 / n,
                    ndraws / n, nprogs, ntex);
    fprintf(stderr, "%s\n", line);
    memset(s_sum, 0, sizeof s_sum);
    memset(s_max, 0, sizeof s_max);
    window = now;
    fmax = fsum = 0;
    n = ndraws = nprogs = ntex = 0;
}
