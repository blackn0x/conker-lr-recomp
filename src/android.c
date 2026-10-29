/**
 * Android host: folders, settings and the bug log.
 *
 *   /sdcard/ConkerLR/game/          the extracted disc (default.xbe and the tree)
 *   /sdcard/ConkerLR/save/          saves
 *   /sdcard/ConkerLR/cache/         shader and pipeline caches
 *   /sdcard/ConkerLR/clx_options.txt, clx_env.txt   settings (copied from the
 *                                   APK the first time)
 *   /sdcard/Download/ConkerLR-logs/<date_time>/     one folder per start:
 *       clx_log.txt      everything the game prints, the device, and a crash
 *                        report (signal, registers, guest and host stacks)
 *       xbox_kernel.log  the kernel's own log
 *
 * The on-screen controls (TouchPadView.java) report here; the input layer
 * merges them into pad 1 (android_touch_apply, from xinput_device.c).
 * Rumble goes the other way (android_rumble -> Rumble.java).
 *
 * The launcher (ClxLauncher.java) asks for "All files access" first; without
 * it the log goes to the app's own folder (Android/data/<package>/files/logs).
 * Every line also goes to logcat (tag "clx") when the log file cannot be made.
 */
#if defined(__ANDROID__)

#include <android/log.h>
#include <jni.h>
#include <pthread.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/system_properties.h>
#include <time.h>
#include <unistd.h>

#include <SDL.h>

#define CLX_DATA_DIR "/storage/emulated/0/ConkerLR"
#define CLX_LOG_ROOT "/storage/emulated/0/Download/ConkerLR-logs"
#define CLX_LOG_KEEP 20                 /* sessions kept in the log folder */

static char s_log_dir[512];

const char *android_log_dir(void)
{
    return s_log_dir;
}

static int make_dir(const char *p)
{
    return mkdir(p, 0775) == 0 || errno == EEXIST;
}

static int name_cmp(const void *a, const void *b)
{
    return strcmp(*(char *const *)a, *(char *const *)b);
}

/* Old sessions go, oldest first (the names sort by date). */
static void prune_logs(const char *root)
{
    char *names[256];
    int n = 0, i;
    DIR *d = opendir(root);
    struct dirent *e;

    if (!d)
        return;
    while ((e = readdir(d)) && n < 256)
        if (e->d_name[0] >= '0' && e->d_name[0] <= '9')
            names[n++] = strdup(e->d_name);
    closedir(d);
    qsort(names, n, sizeof *names, name_cmp);
    for (i = 0; i < n; i++) {
        if (i < n - CLX_LOG_KEEP) {
            char dir[512], f[768];
            DIR *s;
            snprintf(dir, sizeof dir, "%s/%s", root, names[i]);
            if ((s = opendir(dir))) {
                while ((e = readdir(s)))
                    if (e->d_name[0] != '.') {
                        snprintf(f, sizeof f, "%s/%s", dir, e->d_name);
                        unlink(f);
                    }
                closedir(s);
            }
            rmdir(dir);
        }
        free(names[i]);
    }
}

/* <root>/<date_time>/clx_log.txt, as stdout and stderr. A write goes
 * straight to the file (no buffer, no thread), so a crash report is on disk
 * before the process dies. */
static int open_log(const char *root)
{
    char stamp[32], path[600];
    time_t t = time(NULL);
    struct tm tm;
    int fd;

    if (!make_dir(root))
        return 0;
    localtime_r(&t, &tm);
    strftime(stamp, sizeof stamp, "%Y-%m-%d_%H-%M-%S", &tm);
    snprintf(s_log_dir, sizeof s_log_dir, "%s/%s", root, stamp);
    if (!make_dir(s_log_dir))
        return 0;
    snprintf(path, sizeof path, "%s/clx_log.txt", s_log_dir);
    fd = open(path, O_WRONLY | O_CREAT | O_TRUNC | O_APPEND, 0664);
    if (fd < 0)
        return 0;
    dup2(fd, STDOUT_FILENO);
    dup2(fd, STDERR_FILENO);
    close(fd);
    prune_logs(root);
    return 1;
}

static void prop(const char *key, const char *label)
{
    char v[PROP_VALUE_MAX] = "";
    __system_property_get(key, v);
    if (v[0])
        printf("  %-10s %s\n", label, v);
}

/* A file the APK carries in assets/, copied out once so it can be edited. */
static void copy_default(const char *asset, const char *dest)
{
    struct stat st;
    SDL_RWops *in;
    FILE *out;
    char buf[4096];
    size_t n;

    if (stat(dest, &st) == 0 || !(in = SDL_RWFromFile(asset, "rb")))
        return;
    if ((out = fopen(dest, "wb"))) {
        while ((n = SDL_RWread(in, buf, 1, sizeof buf)) > 0)
            fwrite(buf, 1, n, out);
        fclose(out);
        printf("[android] wrote the default %s\n", dest);
    }
    SDL_RWclose(in);
}

/* clx_env.txt: KEY=VALUE per line, '#' comments, as on the Switch. A
 * setting there wins over the port's defaults below. */
static void load_env(const char *path)
{
    char line[512];
    FILE *f = fopen(path, "r");

    if (!f) {
        printf("[android] no %s: default settings\n", path);
        return;
    }
    while (fgets(line, sizeof line, f)) {
        char *eq, *end;
        line[strcspn(line, "\r\n")] = 0;
        if (!line[0] || line[0] == '#' || !(eq = strchr(line, '=')))
            continue;
        *eq = 0;
        for (end = eq; end > line && (end[-1] == ' ' || end[-1] == '\t'); )
            *--end = 0;
        setenv(line, eq + 1, 1);
        printf("[android] env %s=%s\n", line, eq + 1);
    }
    fclose(f);
}

/* How the previous run ended, as Android recorded it (ExitInfo.java writes
 * it before the game starts): a run the system killed has no report of its
 * own, so the next log carries it. */
static void last_exit(const char *path)
{
    char line[512];
    FILE *f = fopen(path, "r");

    if (!f)
        return;
    while (fgets(line, sizeof line, f))
        printf("[last run] %s", line);
    fclose(f);
    remove(path);
}

/* A title that was presenting and then stops for 6 s is frozen (the longest
 * loads still present their loading screen, and take ~4.5 s on an SM8550):
 * take the watchdog's snapshot of the main guest thread then, and once more
 * at 15 s to show whether it moves. A freeze gets swiped away and Android
 * records only "user requested", so without this the log ends with nothing.
 * As the Switch's in switch_nx.c perf_report. */
uint32_t nv2a_gl_frame_count(void);
void xbox_WatchdogDump(const char *why);
void xbox_perf_sample(void);

static void *freeze_watch(void *arg)
{
    uint32_t last = 0, f;
    int presented = 0, still = 0;

    (void)arg;
    for (unsigned secs = 1;; secs++) {
        sleep(1);
        f = nv2a_gl_frame_count();
        if (secs % 30 == 0) {
            /* A heap that climbs over a session is a leak; the NaN count is
             * the Windmill collision point (recomp_manual.c, 0x00355B40). */
            extern volatile unsigned g_clx_nan_fixes;
            uint32_t xbox_HeapLiveBytes(uint32_t *big_blocks);
            uint32_t big, live = xbox_HeapLiveBytes(&big);
            fprintf(stderr, "[mem] %u s, frame %u: heap %u.%u MB live, %u blocks of 1 MB+,"
                            " %u NaN points fixed\n", secs, f, live >> 20,
                    (live >> 16 & 15) * 10 / 16, big, g_clx_nan_fixes);
        }
        if (f != last) {
            presented = 1;
            still = 0;
        } else if (presented && (++still == 6 || still == 15)) {
            fprintf(stderr, "[freeze] no frame presented for %d s (last frame %u)\n", still, f);
            xbox_perf_sample();
            xbox_WatchdogDump(still == 6 ? "no frame presented for 6 s"
                                         : "still no frame after 15 s");
        }
        last = f;
    }
    return NULL;
}

void android_boot(void)
{
    const char *own = SDL_AndroidGetExternalStoragePath();
    char p[600];
    long page = sysconf(_SC_PAGESIZE);

    if (!open_log(CLX_LOG_ROOT)) {
        /* No "All files access": the app's own folder still works. */
        snprintf(p, sizeof p, "%s/logs", own ? own : "/data/local/tmp");
        if (!open_log(p)) {
            s_log_dir[0] = 0;
            __android_log_print(ANDROID_LOG_ERROR, "clx", "no log folder (%s): logging to logcat only",
                                strerror(errno));
        }
    }
    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);
    __android_log_print(ANDROID_LOG_INFO, "clx", "log: %s/clx_log.txt", s_log_dir);

    printf("=== Conker: Live & Reloaded, Android (arm64) ===\n");
    printf("  log        %s\n", s_log_dir);
    prop("ro.product.manufacturer", "maker");
    prop("ro.product.model", "model");
    prop("ro.build.version.release", "android");
    prop("ro.build.version.sdk", "api");
    prop("ro.soc.model", "soc");
    prop("ro.board.platform", "platform");
    prop("ro.hardware.vulkan", "vulkan");
    prop("ro.build.fingerprint", "build");
    printf("  page size  %ld\n", page);
    printf("  cpus       %ld\n", sysconf(_SC_NPROCESSORS_ONLN));
    printf("  memory     %ld MB\n", (long)(sysconf(_SC_PHYS_PAGES) * (page / 1024) / 1024));

    make_dir(CLX_DATA_DIR);
    last_exit(CLX_DATA_DIR "/last_exit.txt");
    make_dir(CLX_DATA_DIR "/save");
    make_dir(CLX_DATA_DIR "/cache");
    copy_default("clx_options.txt", CLX_DATA_DIR "/clx_options.txt");
    copy_default("clx_env.txt", CLX_DATA_DIR "/clx_env.txt");
    load_env(CLX_DATA_DIR "/clx_env.txt");

    setenv("NFSU2_GAME_DIR", CLX_DATA_DIR "/game", 0);
    setenv("CLX_OPTIONS", CLX_DATA_DIR "/clx_options.txt", 0);
    setenv("RECOMP_CACHE_DIR", CLX_DATA_DIR "/cache/", 0);
    /* Periodic lines are slow on shared storage; RECOMP_QUIET=0 in
     * clx_env.txt brings them back. Warnings and errors stay. */
    setenv("RECOMP_QUIET", "1", 0);
    /* The kernel's xbox_kernel.log and anything else the runtime writes to
     * the current folder go beside clx_log.txt. */
    if (s_log_dir[0] && chdir(s_log_dir) != 0)
        printf("[android] chdir %s: %s\n", s_log_dir, strerror(errno));
    {
        pthread_t t;
        if (pthread_create(&t, NULL, freeze_watch, NULL) == 0)
            pthread_detach(t);
    }
}

/* ---- on-screen controls ----------------------------------------------
 *
 * TouchPadView sends the whole state on each change (the UI thread); the
 * game reads it once per pad poll. Buttons are the 16 controls in the order
 * of xinput_device.c's k_pad_ctl; sticks are -1..1 with y down. */
static pthread_mutex_t s_touch_lock = PTHREAD_MUTEX_INITIALIZER;
static int s_touch_buttons;
static float s_touch_axes[4];

JNIEXPORT void JNICALL
Java_org_clx_recomp_TouchPadView_nativeState(JNIEnv *env, jclass cls, jint buttons,
                                             jfloat lx, jfloat ly, jfloat rx, jfloat ry)
{
    (void)env; (void)cls;
    pthread_mutex_lock(&s_touch_lock);
    s_touch_buttons = buttons;
    s_touch_axes[0] = lx;
    s_touch_axes[1] = ly;
    s_touch_axes[2] = rx;
    s_touch_axes[3] = ry;
    pthread_mutex_unlock(&s_touch_lock);
}

/* Up/down/left/right/start/back/lthumb/rthumb are the Xbox wButtons bits
 * 0..7; A B X Y black white LT RT are analog buttons 0..7. A deflected stick
 * replaces the pad's own (y flipped: the Xbox's points up). */
static short touch_axis(float v)
{
    v = v < -1.0f ? -1.0f : v > 1.0f ? 1.0f : v;
    return (short)(v * 32767.0f);
}

void android_touch_apply(unsigned short *wButtons, unsigned char analog[8], short thumbs[4])
{
    int b, i;
    float a[4];

    pthread_mutex_lock(&s_touch_lock);
    b = s_touch_buttons;
    memcpy(a, s_touch_axes, sizeof a);
    pthread_mutex_unlock(&s_touch_lock);
    *wButtons |= (unsigned short)(b & 0xFF);
    for (i = 0; i < 8; i++)
        if (b & (0x100 << i))
            analog[i] = 255;
    if (a[0] != 0.0f || a[1] != 0.0f) {
        thumbs[0] = touch_axis(a[0]);
        thumbs[1] = touch_axis(-a[1]);
    }
    if (a[2] != 0.0f || a[3] != 0.0f) {
        thumbs[2] = touch_axis(a[2]);
        thumbs[3] = touch_axis(-a[3]);
    }
}

/* ---- rumble ----------------------------------------------------------
 *
 * Rumble.set(port, low, high, phone), called from the game's threads. A
 * thread SDL attaches to the VM sees only the system classes, so the class
 * is looked up once on the UI thread (ClxActivity -> Rumble.nativeInit).
 * CLX_PHONE_RUMBLE=0 in clx_env.txt: no phone vibration with the touch
 * controls (a controller's rumble stays). */
static jclass s_rumble_cls;
static jmethodID s_rumble_set;

JNIEXPORT void JNICALL
Java_org_clx_recomp_Rumble_nativeInit(JNIEnv *env, jclass cls)
{
    if (s_rumble_cls)
        return;
    s_rumble_set = (*env)->GetStaticMethodID(env, cls, "set", "(IIIZ)V");
    s_rumble_cls = (jclass)(*env)->NewGlobalRef(env, cls);
}

void android_rumble(int port, unsigned low, unsigned high)
{
    static int phone = -1;
    JNIEnv *env;

    if (!s_rumble_cls || !s_rumble_set || !(env = (JNIEnv *)SDL_AndroidGetJNIEnv()))
        return;
    if (phone < 0) {
        const char *e = getenv("CLX_PHONE_RUMBLE");
        phone = !(e && *e == '0');
    }
    (*env)->CallStaticVoidMethod(env, s_rumble_cls, s_rumble_set, (jint)port,
                                 (jint)low, (jint)high, (jboolean)phone);
    if ((*env)->ExceptionCheck(env)) {
        static int told;
        (*env)->ExceptionDescribe(env);
        (*env)->ExceptionClear(env);
        if (!told++)
            fprintf(stderr, "[android] rumble failed (exception above)\n");
    }
}

#endif /* __ANDROID__ */
