/* Headless tests of the real mouse/report implementation; no game needed.
 * Linux: cc tests/mouse_input.c $(pkg-config --cflags --libs sdl2) -lm -o mouse-test
 * Windows/MinGW: add SDL2's include/lib paths, -lSDL2 -luser32, then run the exe.
 * SDL supplies locks and threads; only window/input state is simulated.
 */
#define SDL_MAIN_HANDLED
#include <SDL.h>
#ifdef _WIN32
#include <SDL_syswm.h>
static SDL_bool test_wm(SDL_Window *w, SDL_SysWMinfo *i) { return SDL_FALSE; }
#define SDL_GetWindowWMInfo test_wm
#endif
#include <assert.h>
#include <stdio.h>
#include <string.h>

static Uint8 keys[SDL_NUM_SCANCODES];
static Uint32 flags = SDL_WINDOW_INPUT_FOCUS;
static int menu, relative, curve, curve_calls;
static SDL_atomic_t ticks;
static Uint32 test_ticks(void) { return (Uint32)SDL_AtomicGet(&ticks); }
static Uint32 test_flags(SDL_Window *w) { return flags; }
static const Uint8 *test_keys(int *n) { *n = SDL_NUM_SCANCODES; return keys; }
static int test_relative(SDL_bool on) { relative = on; return 0; }
static SDL_bool test_get_relative(void) { return relative ? SDL_TRUE : SDL_FALSE; }
static void test_grab(SDL_Window *w, SDL_bool on) {}
static int test_cursor(int on) { return relative ? SDL_DISABLE : SDL_ENABLE; }
static Uint32 test_motion(int *x, int *y) { return 0; }
static int test_fullscreen(SDL_Window *w, Uint32 f) { return 0; }
static SDL_bool test_hint(const char *name, const char *value) { return SDL_TRUE; }
#define SDL_GetTicks test_ticks
#define SDL_GetWindowFlags test_flags
#define SDL_GetKeyboardState test_keys
#define SDL_SetRelativeMouseMode test_relative
#define SDL_GetRelativeMouseMode test_get_relative
#define SDL_SetWindowGrab test_grab
#define SDL_ShowCursor test_cursor
#define SDL_GetRelativeMouseState test_motion
#define SDL_SetWindowFullscreen test_fullscreen
#define SDL_SetHint test_hint
#include "../src/clx_mouse.c"

int clx_menu_is_open(void) { return menu; }
void clx_camera_curve_mouse(int on) { curve = on; curve_calls++; }

static int axis(const uint8_t *r, int at) { return (int16_t)(r[at] | r[at+1] << 8); }
static void report(uint8_t *r) { memset(r, 0, 20); clx_mouse_report(r); }
static int guest_updates(void *unused)
{
    for (int i = 0; i < 20000; i++) {
        uint8_t r[20];
        clx_mouse_set_mode(i % 3);
        clx_mouse_camera_active();
        report(r);
    }
    return 0;
}
int main(void)
{
    uint8_t r[20];
    SDL_setenv("CLX_MOUSE_OPTIONS", "__missing_mouse_test_options__", 1);
    SDL_setenv("CLX_NATIVE_MOUSE", "1", 1);
    SDL_setenv("CLX_BORDERLESS", "0", 1);
    SDL_AtomicSet(&ticks, 1000);
    SDL_Window *window = (SDL_Window *)1; /* never passed to real SDL window APIs */
    clx_mouse_set_mode(1);
    assert(!clx_mouse_camera_active());
    int calls = curve_calls;
    clx_mouse_frame(window);
    assert(relative && curve_calls == calls); /* render cannot rewrite guest RAM */
    clx_mouse_set_mode(1);
    assert(curve && clx_mouse_camera_active());
    clx_mouse_motion(1, 1);
    clx_mouse_frame(window);
    report(r);
    int normal = axis(r, 16);
    assert(normal > 0 && axis(r, 18) < 0);
    memset(r, 0x7f, 16); memset(r + 16, 0, 4);
    clx_mouse_report(r);
    for (int i = 0; i < 16; i++) assert(r[i] == 0x7f); /* other controls unchanged */
    clx_mouse_frame(window);
    report(r); assert(!axis(r, 16) && !axis(r, 18)); /* no replay without motion */
    clx_mouse_set_mode(2);
    clx_mouse_motion(1, 0); clx_mouse_frame(window);
    report(r); assert(axis(r, 16) > normal); /* weapon gain retained */
    clx_mouse_set_mode(0);
    report(r); assert(!axis(r, 16) && !axis(r, 18) && !curve);
    clx_mouse_set_mode(1);
    clx_mouse_motion(1000, -1000); clx_mouse_frame(window);
    memset(r, 0, 20); r[16]=r[18]=0xff; r[17]=r[19]=0x7f;
    clx_mouse_report(r); assert(axis(r,16)==32767 && axis(r,18)==32767);
    menu = 1; clx_mouse_frame(window);
    report(r); assert(!relative && !axis(r,16) && !axis(r,18));
    clx_mouse_set_mode(1); assert(!curve);
    menu = 0; clx_mouse_camera_active(); clx_mouse_frame(window);
    assert(relative);
    flags = 0; clx_mouse_frame(window); assert(!relative);
    flags = SDL_WINDOW_INPUT_FOCUS;
    clx_mouse_camera_active(); clx_mouse_frame(window); assert(relative);
    SDL_AtomicSet(&ticks, 1300); clx_mouse_frame(window); assert(!relative);
    clx_mouse_camera_active(); clx_mouse_frame(window); assert(relative);
    SDL_Thread *thread = SDL_CreateThread(guest_updates, "mouse-test-guest", NULL);
    assert(thread);
    for (int i = 0; i < 20000; i++) { clx_mouse_motion(1,-1); clx_mouse_frame(window); }
    SDL_WaitThread(thread, NULL);
    clx_mouse_set_mode(0); report(r); assert(!axis(r,16) && !axis(r,18));
    puts("PASS mouse reports, capture, gain, saturation, timeout and concurrent updates");
    return 0;
}
