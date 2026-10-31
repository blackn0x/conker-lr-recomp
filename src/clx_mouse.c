/* Native relative mouse camera for the PC port.
 *
 * SDL's relative mouse mode gives raw pixel deltas with the cursor confined
 * and hidden. Each frame's motion becomes right-stick input in the USB pad
 * report, so the player and weapon cameras share the game's input path.
 *
 *   clx_mouse_motion()  render thread, SDL_MOUSEMOTION events
 *   clx_mouse_frame()   render thread, once per presented frame
 *   clx_mouse_camera_active()  guest thread, camera activity/capture status
 *
 * Controls: F8 releases/captures the mouse, Alt+Enter or F11 toggles
 * borderless fullscreen, Esc releases the mouse while the settings menu is
 * open (it is recaptured when the menu closes).
 *
 * Settings in clx_mouse_options.txt (next to the executable):
 *   sensitivity=0.15    degrees of horizontal camera rotation per mouse pixel
 *   sensitivity_y=      same vertically (default: sensitivity)
 *   invert_x=0          1 = reverse left/right
 *   invert_y=0          1 = moving the mouse down looks up
 */
#include "clx_mouse.h"

#include <stdio.h>
#include <stdlib.h>
#include <math.h>

#if defined(_WIN32)
#include <windows.h>
#include <SDL_syswm.h>

/* SDL only reads the keyboard and controllers while it believes the window
 * has the input focus. A launcher setting the OS foreground window is not
 * enough: the window's own thread must also take the keyboard focus, or SDL
 * keeps SDL_WINDOW_INPUT_FOCUS clear and every key is ignored. */
static void force_input_focus(SDL_Window *window)
{
    SDL_SysWMinfo info;
    HWND hwnd;
    SDL_VERSION(&info.version);
    if (!SDL_GetWindowWMInfo(window, &info))
        return;
    hwnd = info.info.win.window;
    if (!hwnd)
        return;
    SetForegroundWindow(hwnd);
    SetActiveWindow(hwnd);
    SetFocus(hwnd);
    /* Windows can refuse the focus change when another process owns the
     * foreground. SDL's own window procedure is what sets its keyboard
     * focus state, so deliver those messages directly as well. */
    SendMessage(hwnd, WM_ACTIVATE, WA_ACTIVE, 0);
    SendMessage(hwnd, WM_ACTIVATEAPP, TRUE, 0);
    SendMessage(hwnd, WM_SETFOCUS, 0, 0);
}
#else
static void force_input_focus(SDL_Window *window) { (void)window; }
#endif

extern int clx_menu_is_open(void);

static SDL_SpinLock lock;
static int dx_pending, dy_pending;
static int captured;                 /* relative mode is on */
static int pad_x, pad_y;             /* raw pad axes (-32767..32767) */
static uint32_t camera_tick;
static float sensitivity = 0.15f;
static float sensitivity_y;
static float aim_gain = 1.8f;         /* weapon/aim camera is slower */
static int mouse_mode;                /* 0 off, 1 player, 2 weapon aim */
static int invert_x, invert_y;
static int dbg;

static void options_load(void)
{
    const char *file = getenv("CLX_MOUSE_OPTIONS");
    FILE *f = fopen(file && *file ? file : "clx_mouse_options.txt", "r");
    char line[256];
    float v;

    if (!f)
        return;
    while (fgets(line, sizeof line, f)) {
        if (sscanf(line, "sensitivity=%f", &v) == 1 &&
            isfinite(v) && v >= 0.01f && v <= 5.0f)
            sensitivity = v;
        if (sscanf(line, "sensitivity_y=%f", &v) == 1 &&
            isfinite(v) && v >= 0.01f && v <= 5.0f)
            sensitivity_y = v;
        if (sscanf(line, "aim_gain=%f", &v) == 1 &&
            isfinite(v) && v >= 0.5f && v <= 4.0f)
            aim_gain = v;
        if (sscanf(line, "invert_x=%f", &v) == 1)
            invert_x = v != 0.0f;
        if (sscanf(line, "invert_y=%f", &v) == 1)
            invert_y = v != 0.0f;
    }
    fclose(f);
}

static void capture(SDL_Window *window, int on)
{
    if (on) {
        if (SDL_SetRelativeMouseMode(SDL_TRUE) != 0) {
            fprintf(stderr, "[mouse] relative mode failed: %s\n", SDL_GetError());
            on = 0;
        }
    } else {
        SDL_SetRelativeMouseMode(SDL_FALSE);
    }
    SDL_SetWindowGrab(window, on ? SDL_TRUE : SDL_FALSE);
    SDL_ShowCursor(on ? SDL_DISABLE : SDL_ENABLE);
    SDL_GetRelativeMouseState(NULL, NULL);   /* discard the transition warp */

    SDL_AtomicLock(&lock);
    captured = on;
    dx_pending = dy_pending = 0;
    pad_x = pad_y = 0;
    SDL_AtomicUnlock(&lock);

    fprintf(stderr, "[mouse] %s (relative=%d cursor=%d)\n",
            on ? "capture on" : "capture off",
            SDL_GetRelativeMouseMode(), SDL_ShowCursor(SDL_QUERY));
}

void clx_mouse_motion(int dx, int dy)
{
    if (!dx && !dy)
        return;
    SDL_AtomicLock(&lock);
    if (captured) {
        dx_pending += dx;
        dy_pending += dy;
    }
    SDL_AtomicUnlock(&lock);
    if (dbg && captured) {
        static int logged;
        if (logged++ < 40)
            fprintf(stderr, "[mouse-event] dx=%d dy=%d\n", dx, dy);
    }
}

void clx_mouse_frame(SDL_Window *window)
{
    static int initialized, enabled = 1, borderless, was_f8, was_full, fs;
    const Uint8 *keys;
    int nkeys = 0, f8, full, want, was_captured;
    int frame_dx, frame_dy, log_pad_x, log_pad_y;

    if (!initialized) {
        initialized = 1;
        const char *e = getenv("CLX_NATIVE_MOUSE");
        if (e)
            enabled = atoi(e) != 0;
        e = getenv("CLX_BORDERLESS");
        borderless = e && atoi(e) != 0;
        SDL_AtomicLock(&lock);
        dbg = getenv("CLX_MOUSE_DEBUG") != NULL;
        SDL_AtomicUnlock(&lock);
        options_load();
        SDL_SetHint(SDL_HINT_MOUSE_RELATIVE_MODE_WARP, "0");
        if (borderless) {
            if (SDL_SetWindowFullscreen(window, SDL_WINDOW_FULLSCREEN_DESKTOP) == 0)
                fs = 1;
            else
                fprintf(stderr, "[mouse] borderless failed: %s\n", SDL_GetError());
        }
        fprintf(stderr, "[mouse] relative camera %.3f deg/pixel%s%s; F8 capture, Alt+Enter fullscreen\n",
                sensitivity, invert_y ? ", inverted" : "",
                borderless ? ", borderless" : "");
        force_input_focus(window);
    }

    {
        /* Keep asking until SDL reports input focus once. After that, never
         * touch the focus again: the player may Alt+Tab away on purpose. */
        static int focus_done;
        if (!focus_done) {
            if (SDL_GetWindowFlags(window) & SDL_WINDOW_INPUT_FOCUS)
                focus_done = 1;
            else
                force_input_focus(window);
        }
    }

    keys = SDL_GetKeyboardState(&nkeys);
    f8 = keys && nkeys > SDL_SCANCODE_F8 && keys[SDL_SCANCODE_F8];
    if (f8 && !was_f8)
        enabled = !enabled;
    was_f8 = f8;

    {   /* Alt+Enter / F11: borderless fullscreen toggle */
        int alt = keys && nkeys > SDL_SCANCODE_LALT &&
                  (keys[SDL_SCANCODE_LALT] || keys[SDL_SCANCODE_RALT]);
        int enter = keys && nkeys > SDL_SCANCODE_RETURN &&
                    (keys[SDL_SCANCODE_RETURN] || keys[SDL_SCANCODE_KP_ENTER]);
        int f11 = keys && nkeys > SDL_SCANCODE_F11 && keys[SDL_SCANCODE_F11];
        full = (alt && enter) || f11;
        if (full && !was_full) {
            fs = !fs;
            if (SDL_SetWindowFullscreen(window, fs ? SDL_WINDOW_FULLSCREEN_DESKTOP : 0) == 0) {
                SDL_GetRelativeMouseState(NULL, NULL);
                fprintf(stderr, "[mouse] fullscreen %s\n", fs ? "on (borderless)" : "off");
            } else {
                fs = !fs;
                fprintf(stderr, "[mouse] fullscreen failed: %s\n", SDL_GetError());
            }
        }
        was_full = full;
    }

    {
        Uint32 now = SDL_GetTicks();
        int focused = (SDL_GetWindowFlags(window) & SDL_WINDOW_INPUT_FOCUS) != 0;
        int recent;
        SDL_AtomicLock(&lock);
        recent = camera_tick && (Uint32)(now - camera_tick) < 250;
        was_captured = captured;
        SDL_AtomicUnlock(&lock);
        want = enabled && !clx_menu_is_open() && focused && recent;
    }
    if (want != was_captured) {
        capture(window, want);
        return;
    }

    /* Events carry the real motion; clear SDL's own accumulator so it is
     * not counted twice. */
    SDL_GetRelativeMouseState(NULL, NULL);
    SDL_AtomicLock(&lock);
    frame_dx = dx_pending;
    frame_dy = dy_pending;
    dx_pending = dy_pending = 0;
    if (captured) {
        /* One frame's motion becomes one frame's right-stick deflection.
         * The camera's own stick path then moves the view, exactly as the
         * arrow keys do. With the linear curve above, a full stick is the
         * camera's full speed for one frame (120 deg/s yaw, 50.3 pitch at
         * 60 fps), so the deflection is the requested angle divided by that. */
        float sy = sensitivity_y > 0.0f ? sensitivity_y : sensitivity;
        float nx = (float)frame_dx * sensitivity / 2.0f;
        float ny = -(float)frame_dy * sy / (50.3f / 60.0f);
        int px, py;
        float gain = mouse_mode == 2 ? aim_gain : 1.0f;
        if (invert_x) nx = -nx;
        if (invert_y) ny = -ny;
        if (nx > 0.9f) nx = 0.9f; else if (nx < -0.9f) nx = -0.9f;
        if (ny > 1.0f) ny = 1.0f; else if (ny < -1.0f) ny = -1.0f;
        /* The game reads the camera input block as stick * 1.25 / 63;
         * nx/ny are the desired curve inputs, so undo the 1.25 here. The
         * aim camera is slower than the normal one, so give it extra gain. */
        px = (int)lrintf(nx * (32767.0f / 1.25f) * gain);
        py = (int)lrintf(ny * (32767.0f / 1.25f) * gain);
        if (px > 32767) px = 32767; else if (px < -32768) px = -32768;
        if (py > 32767) py = 32767; else if (py < -32768) py = -32768;
        pad_x = mouse_mode ? px : 0;
        pad_y = mouse_mode ? py : 0;
    } else {
        pad_x = pad_y = 0;
    }
    log_pad_x = pad_x;
    log_pad_y = pad_y;
    SDL_AtomicUnlock(&lock);

    if (dbg) {
        static int logged;
        if ((frame_dx || frame_dy) && logged++ < 120)
            fprintf(stderr, "[mouse-frame] dx=%d dy=%d pad=%d,%d\n",
                    frame_dx, frame_dy, log_pad_x, log_pad_y);
    }
}

void clx_mouse_set_mode(int mode)
{
    int on;
    extern void clx_camera_curve_mouse(int on);
    SDL_AtomicLock(&lock);
    mouse_mode = mode;
    on = captured && mode != 0;
    if (!mode)
        pad_x = pad_y = 0;
    SDL_AtomicUnlock(&lock);
    /* This entry point runs on the guest thread. Never rewrite the guest's
     * curve table on the render thread while the guest can be reading it. */
    clx_camera_curve_mouse(on);
}

static int mouse_pad(int *rx, int *ry, int *debug)
{
    SDL_AtomicLock(&lock);
    *rx = pad_x;
    *ry = pad_y;
    *debug = dbg;
    SDL_AtomicUnlock(&lock);
    return *rx != 0 || *ry != 0;
}

void clx_mouse_report(uint8_t *out)
{
    int mx = 0, my = 0, x, y, debug;
    if (!out || !mouse_pad(&mx, &my, &debug))
        return;
    x = (int)(int16_t)(out[16] | (out[17] << 8)) + mx;
    y = (int)(int16_t)(out[18] | (out[19] << 8)) + my;
    if (x > 32767) x = 32767; else if (x < -32768) x = -32768;
    if (y > 32767) y = 32767; else if (y < -32768) y = -32768;
    out[16] = (uint8_t)x; out[17] = (uint8_t)((uint16_t)x >> 8);
    out[18] = (uint8_t)y; out[19] = (uint8_t)((uint16_t)y >> 8);
    if (debug) {
        static int logged;
        if (logged++ < 40)
            fprintf(stderr, "[mouse-pad] mx=%d my=%d => %d,%d\n", mx, my, x, y);
    }
}

int clx_mouse_camera_active(void)
{
    Uint32 now = SDL_GetTicks();
    int on;

    SDL_AtomicLock(&lock);
    camera_tick = now;
    on = captured;
    SDL_AtomicUnlock(&lock);
    return on;
}
