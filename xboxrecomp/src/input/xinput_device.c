/**
 * Xbox Input Compatibility Layer
 *
 * Translates the Xbox controller API to a host gamepad backend.
 * Handles the structural differences between the Xbox gamepad
 * (analog buttons as bytes, separate trigger channels) and the host
 * (digital face buttons, trigger axes).
 *
 *   _WIN32 -> Windows XInput (SDL2 with XBOXRECOMP_SDL_INPUT: an SDL window build)
 *   POSIX  -> SDL2 GameController
 */

#include "xinput_xbox.h"
#include <stdlib.h>
#include <string.h>

/* ======================================================================== */
#if defined(_WIN32) && !defined(XBOXRECOMP_SDL_INPUT)
/* ====================  XInput backend  ================================== */
/* ======================================================================== */

#include <xinput.h>
#pragma comment(lib, "xinput.lib")

static BOOL  g_controller_connected[XBOX_MAX_CONTROLLERS] = { FALSE };
static DWORD g_last_packet[XBOX_MAX_CONTROLLERS] = { 0 };

/* ---- keyboard, when there is no pad --------------------------------------
 *
 * A title that waits on PRESS START is unreachable on a machine with no
 * controller plugged in, which is most machines someone brings this up on.
 * The whole point of a recompilation is to be able to look at the thing
 * running, and a build nobody can press a button in cannot be looked at.
 *
 * Off by default, because a keyboard silently acting as player 1 is
 * surprising when a real pad is what you meant to use. RECOMP_KEYBOARD=1
 * turns it on. It only ever answers for port 0, and is merged on top of a
 * pad connected there, so a real controller keeps working.
 *
 * The keys are the ones a Dreamcast or Saturn emulator would pick, which is
 * the closest thing to a convention here:
 *
 *   arrows        d-pad             Enter      START
 *   Z X A S       A B X Y           Backspace  BACK
 *   Q E           white black       1 3        triggers
 *   numpad 8/2/4/6 left thumb       I/K/J/L    right thumb
 *
 * Keys come from the framebuffer window, which only receives them while it
 * has the focus, so typing in another window does not drive the game.
 */
static BOOL keyboard_enabled(void)
{
    static int on = -1;
    if (on < 0) {
        const char *v = getenv("RECOMP_KEYBOARD");
        on = (v && *v && *v != '0') ? 1 : 0;
    }
    return on ? TRUE : FALSE;
}

/* The framebuffer window records what is held; see src/video/fb_present.c.
 *
 * GetAsyncKeyState was the first attempt and reads nothing here -- under
 * Wine it answers about a state a GDI-drawing guest never touches. Going
 * through the window is also the better gate: a window only receives keys
 * while it has the focus, so there is no separate focus check to get wrong
 * and no way for typing in another application to drive the game.
 *
 * Declared rather than included so src/input does not depend on the video
 * module's include path. */
extern int xbox_FramebufferKeyDown(int vk);

static BOOL key_down(int vk)
{
    return xbox_FramebufferKeyDown(vk) ? TRUE : FALSE;
}

/* A thumb axis from two keys, at the full deflection a digital key implies. */
static SHORT axis_from_keys(int negative, int positive)
{
    int v = 0;
    if (key_down(negative)) v -= 32767;
    if (key_down(positive)) v += 32767;
    return (SHORT)v;
}

static void keyboard_state(XBOX_INPUT_STATE *pState)
{
    static DWORD packet;
    WORD b = 0;

    memset(pState, 0, sizeof(*pState));

    if (key_down(VK_UP))     b |= XBOX_GAMEPAD_DPAD_UP;
    if (key_down(VK_DOWN))   b |= XBOX_GAMEPAD_DPAD_DOWN;
    if (key_down(VK_LEFT))   b |= XBOX_GAMEPAD_DPAD_LEFT;
    if (key_down(VK_RIGHT))  b |= XBOX_GAMEPAD_DPAD_RIGHT;
    if (key_down(VK_RETURN)) b |= XBOX_GAMEPAD_START;
    if (key_down(VK_BACK))   b |= XBOX_GAMEPAD_BACK;
    if (key_down(VK_SHIFT))  b |= XBOX_GAMEPAD_LEFT_THUMB;
    if (key_down(VK_CONTROL))b |= XBOX_GAMEPAD_RIGHT_THUMB;
    pState->Gamepad.wButtons = b;

    /* Analog on the console, so a key is 255 rather than a flag -- a title
     * that reads these as a pressure never sees a press if they are 1. */
    pState->Gamepad.bAnalogButtons[XBOX_BUTTON_A]        = key_down('Z') ? 255 : 0;
    pState->Gamepad.bAnalogButtons[XBOX_BUTTON_B]        = key_down('X') ? 255 : 0;
    pState->Gamepad.bAnalogButtons[XBOX_BUTTON_X]        = key_down('A') ? 255 : 0;
    pState->Gamepad.bAnalogButtons[XBOX_BUTTON_Y]        = key_down('S') ? 255 : 0;
    pState->Gamepad.bAnalogButtons[XBOX_BUTTON_WHITE]    = key_down('Q') ? 255 : 0;
    pState->Gamepad.bAnalogButtons[XBOX_BUTTON_BLACK]    = key_down('E') ? 255 : 0;
    pState->Gamepad.bAnalogButtons[XBOX_BUTTON_LTRIGGER] = key_down('1') ? 255 : 0;
    pState->Gamepad.bAnalogButtons[XBOX_BUTTON_RTRIGGER] = key_down('3') ? 255 : 0;

    /* W/A/S/D would collide with the face buttons above, so the left thumb
     * shares the arrow keys' row on the numeric pad instead. */
    pState->Gamepad.sThumbLX = axis_from_keys(VK_NUMPAD4, VK_NUMPAD6);
    pState->Gamepad.sThumbLY = axis_from_keys(VK_NUMPAD2, VK_NUMPAD8);
    pState->Gamepad.sThumbRX = axis_from_keys('J', 'L');
    pState->Gamepad.sThumbRY = axis_from_keys('K', 'I');

    /* The title's input layer looks for button edges, so the packet number
     * has to move whenever the state does or a press is never noticed. */
    pState->dwPacketNumber = ++packet;
}

void xbox_InputInit(void)
{
    for (DWORD i = 0; i < XBOX_MAX_CONTROLLERS; i++) {
        XINPUT_STATE state;
        DWORD result = XInputGetState(i, &state);
        g_controller_connected[i] = (result == ERROR_SUCCESS);
    }
}

DWORD xbox_InputGetState(DWORD dwPort, XBOX_INPUT_STATE *pState)
{
    XINPUT_STATE xi_state;
    DWORD result;

    if (dwPort >= XBOX_MAX_CONTROLLERS || !pState)
        return ERROR_DEVICE_NOT_CONNECTED;

    result = XInputGetState(dwPort, &xi_state);
    if (result != ERROR_SUCCESS) {
        g_controller_connected[dwPort] = FALSE;
        if (dwPort == 0 && keyboard_enabled()) {
            keyboard_state(pState);
            return ERROR_SUCCESS;
        }
        return result;
    }

    g_controller_connected[dwPort] = TRUE;
    g_last_packet[dwPort] = xi_state.dwPacketNumber;

    memset(pState, 0, sizeof(XBOX_INPUT_STATE));
    pState->dwPacketNumber = xi_state.dwPacketNumber;
    pState->Gamepad.wButtons = xi_state.Gamepad.wButtons & 0x00FF;

    pState->Gamepad.bAnalogButtons[XBOX_BUTTON_A] =
        (xi_state.Gamepad.wButtons & XINPUT_GAMEPAD_A) ? 255 : 0;
    pState->Gamepad.bAnalogButtons[XBOX_BUTTON_B] =
        (xi_state.Gamepad.wButtons & XINPUT_GAMEPAD_B) ? 255 : 0;
    pState->Gamepad.bAnalogButtons[XBOX_BUTTON_X] =
        (xi_state.Gamepad.wButtons & XINPUT_GAMEPAD_X) ? 255 : 0;
    pState->Gamepad.bAnalogButtons[XBOX_BUTTON_Y] =
        (xi_state.Gamepad.wButtons & XINPUT_GAMEPAD_Y) ? 255 : 0;
    pState->Gamepad.bAnalogButtons[XBOX_BUTTON_BLACK] =
        (xi_state.Gamepad.wButtons & XINPUT_GAMEPAD_LEFT_SHOULDER) ? 255 : 0;
    pState->Gamepad.bAnalogButtons[XBOX_BUTTON_WHITE] =
        (xi_state.Gamepad.wButtons & XINPUT_GAMEPAD_RIGHT_SHOULDER) ? 255 : 0;
    pState->Gamepad.bAnalogButtons[XBOX_BUTTON_LTRIGGER] = xi_state.Gamepad.bLeftTrigger;
    pState->Gamepad.bAnalogButtons[XBOX_BUTTON_RTRIGGER] = xi_state.Gamepad.bRightTrigger;

    pState->Gamepad.sThumbLX = xi_state.Gamepad.sThumbLX;
    pState->Gamepad.sThumbLY = xi_state.Gamepad.sThumbLY;
    pState->Gamepad.sThumbRX = xi_state.Gamepad.sThumbRX;
    pState->Gamepad.sThumbRY = xi_state.Gamepad.sThumbRY;

    /* Merge the keyboard on top rather than only standing in for a missing
     * pad.
     *
     * The first version put the keyboard behind XInput's failure, on the
     * assumption that with nothing plugged in the call would fail. It does
     * not: under Wine XInputGetState returns ERROR_SUCCESS and a gamepad
     * with every button at rest, so the fallback was unreachable and
     * pressing a key did nothing at all.
     *
     * Merging is also the better rule. A real pad keeps working -- its
     * buttons are already in pState and the keyboard only adds to them --
     * and there is no special case left to get wrong. */
    if (dwPort == 0 && keyboard_enabled()) {
        XBOX_INPUT_STATE kb;
        int i;
        keyboard_state(&kb);
        pState->Gamepad.wButtons |= kb.Gamepad.wButtons;
        for (i = 0; i < 8; i++)
            if (kb.Gamepad.bAnalogButtons[i] > pState->Gamepad.bAnalogButtons[i])
                pState->Gamepad.bAnalogButtons[i] = kb.Gamepad.bAnalogButtons[i];
        if (kb.Gamepad.sThumbLX) pState->Gamepad.sThumbLX = kb.Gamepad.sThumbLX;
        if (kb.Gamepad.sThumbLY) pState->Gamepad.sThumbLY = kb.Gamepad.sThumbLY;
        if (kb.Gamepad.sThumbRX) pState->Gamepad.sThumbRX = kb.Gamepad.sThumbRX;
        if (kb.Gamepad.sThumbRY) pState->Gamepad.sThumbRY = kb.Gamepad.sThumbRY;
        /* The input layer records edges, so an unchanged packet number is
         * read as the same state and the press never happens. */
        pState->dwPacketNumber = kb.dwPacketNumber;
    }

    return ERROR_SUCCESS;
}

DWORD xbox_InputSetState(DWORD dwPort, const XBOX_VIBRATION *pVibration)
{
    XINPUT_VIBRATION xi_vib;

    if (dwPort >= XBOX_MAX_CONTROLLERS || !pVibration)
        return ERROR_DEVICE_NOT_CONNECTED;

    xi_vib.wLeftMotorSpeed = pVibration->wLeftMotorSpeed;
    xi_vib.wRightMotorSpeed = pVibration->wRightMotorSpeed;
    return XInputSetState(dwPort, &xi_vib);
}

BOOL xbox_InputIsConnected(DWORD dwPort)
{
    if (dwPort >= XBOX_MAX_CONTROLLERS) return FALSE;
    return g_controller_connected[dwPort];
}

DWORD xbox_InputGetCapabilities(DWORD dwPort, DWORD dwFlags, XBOX_INPUT_CAPABILITIES *pCaps)
{
    XINPUT_CAPABILITIES xi_caps;
    DWORD result;

    if (dwPort >= XBOX_MAX_CONTROLLERS || !pCaps)
        return ERROR_DEVICE_NOT_CONNECTED;

    result = XInputGetCapabilities(dwPort, dwFlags, &xi_caps);
    if (result != ERROR_SUCCESS) return result;

    memset(pCaps, 0, sizeof(XBOX_INPUT_CAPABILITIES));
    pCaps->Type = xi_caps.Type;
    pCaps->SubType = xi_caps.SubType;
    pCaps->Flags = xi_caps.Flags;
    return ERROR_SUCCESS;
}

/* ======================================================================== */
#else /* !_WIN32 or XBOXRECOMP_SDL_INPUT */
/* ====================  SDL2 GameController backend  ===================== */
/* ======================================================================== */

#include <SDL.h>
#include <stdio.h>
#if !defined(__SWITCH__)
#include "sdl_keys.h"
#endif

static SDL_GameController *g_pads[XBOX_MAX_CONTROLLERS];
static BOOL  g_controller_connected[XBOX_MAX_CONTROLLERS];
static DWORD g_packet[XBOX_MAX_CONTROLLERS];

/* Open up to XBOX_MAX_CONTROLLERS attached game controllers. */
static void open_controllers(void)
{
    int slot = 0;
    for (int i = 0; i < SDL_NumJoysticks() && slot < XBOX_MAX_CONTROLLERS; i++) {
        if (!SDL_IsGameController(i))
            continue;
        if (!g_pads[slot]) {
            g_pads[slot] = SDL_GameControllerOpen(i);
            g_controller_connected[slot] = (g_pads[slot] != NULL);
        }
        slot++;
    }
}

void xbox_InputInit(void)
{
    if (!SDL_WasInit(SDL_INIT_GAMECONTROLLER))
        SDL_InitSubSystem(SDL_INIT_GAMECONTROLLER);
    open_controllers();
}

#if defined(__SWITCH__)
#include "xinput_nx.h"
#else
/* Hot-plug, once a second: a pad pulled out is closed, a new one (any SDL
 * game controller: XInput, DirectInput, Switch Pro, DualShock) takes the
 * first free slot. SDL_GameControllerUpdate() before this has refreshed
 * the device list. */
static void refresh_controllers(void)
{
    int i, j, slot;
    for (slot = 0; slot < XBOX_MAX_CONTROLLERS; slot++)
        if (g_pads[slot] && !SDL_GameControllerGetAttached(g_pads[slot])) {
            fprintf(stderr, "  [PAD] controller %d removed\n", slot + 1);
            SDL_GameControllerClose(g_pads[slot]);
            g_pads[slot] = NULL;
            g_controller_connected[slot] = FALSE;
        }
    for (i = 0; i < SDL_NumJoysticks(); i++) {
        SDL_JoystickID id;
        int open = 0;
        if (!SDL_IsGameController(i))
            continue;
        id = SDL_JoystickGetDeviceInstanceID(i);
        for (j = 0; j < XBOX_MAX_CONTROLLERS; j++)
            if (g_pads[j] && SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(g_pads[j])) == id)
                open = 1;
        if (open)
            continue;
        for (slot = 0; slot < XBOX_MAX_CONTROLLERS && g_pads[slot]; slot++) { }
        if (slot == XBOX_MAX_CONTROLLERS)
            break;
        if ((g_pads[slot] = SDL_GameControllerOpen(i))) {
            g_controller_connected[slot] = TRUE;
            fprintf(stderr, "  [PAD] controller %d: %s\n", slot + 1,
                    SDL_GameControllerName(g_pads[slot]));
        }
    }
}
#endif

/* ---- pad bindings (PC): each Xbox control from an SDL input -------------
 *
 * Controls in the order of sdl_keys.c: up down left right start back lthumb
 * rthumb a b x y black white lt rt. An input is an SDL game-controller
 * button (>= 0) or the positive / negative half of an axis (< 0:
 * -(axis * 2 + negative + 1)). */
static const char *const k_pad_ctl[16] = {
    "up", "down", "left", "right", "start", "back", "lthumb", "rthumb",
    "a", "b", "x", "y", "black", "white", "lt", "rt",
};
#define PAD_AXIS(a, neg) (-((a) * 2 + (neg) + 1))
static const int k_pad_default[16] = {
    SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_DOWN,
    SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT,
    SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_BACK,
    SDL_CONTROLLER_BUTTON_LEFTSTICK, SDL_CONTROLLER_BUTTON_RIGHTSTICK,
    SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_X,
    SDL_CONTROLLER_BUTTON_Y, SDL_CONTROLLER_BUTTON_LEFTSHOULDER, SDL_CONTROLLER_BUTTON_RIGHTSHOULDER,
    PAD_AXIS(SDL_CONTROLLER_AXIS_TRIGGERLEFT, 0), PAD_AXIS(SDL_CONTROLLER_AXIS_TRIGGERRIGHT, 0),
};
static int s_pad_bind[16] = {
    SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_DOWN,
    SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT,
    SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_BACK,
    SDL_CONTROLLER_BUTTON_LEFTSTICK, SDL_CONTROLLER_BUTTON_RIGHTSTICK,
    SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_X,
    SDL_CONTROLLER_BUTTON_Y, SDL_CONTROLLER_BUTTON_LEFTSHOULDER, SDL_CONTROLLER_BUTTON_RIGHTSHOULDER,
    PAD_AXIS(SDL_CONTROLLER_AXIS_TRIGGERLEFT, 0), PAD_AXIS(SDL_CONTROLLER_AXIS_TRIGGERRIGHT, 0),
};

/* 0..255: how far control k is pressed. */
static int pad_level(SDL_GameController *c, int k)
{
    int b = s_pad_bind[k], v;
    if (b >= 0)
        return SDL_GameControllerGetButton(c, (SDL_GameControllerButton)b) ? 255 : 0;
    b = -b - 1;
    v = SDL_GameControllerGetAxis(c, (SDL_GameControllerAxis)(b / 2));
    if (b & 1)
        v = -1 - v;                     /* the negative half */
    return v > 0 ? v >> 7 : 0;
}

/* "a", "leftshoulder", "lefttrigger", "+leftx", "-lefty" (SDL's names). */
static int pad_input_from_name(const char *s)
{
    int neg = 0;
    SDL_GameControllerButton b;
    SDL_GameControllerAxis a;
    if (*s == '+' || *s == '-')
        neg = *s++ == '-';
    b = SDL_GameControllerGetButtonFromString(s);
    if (b != SDL_CONTROLLER_BUTTON_INVALID && !neg)
        return b;
    a = SDL_GameControllerGetAxisFromString(s);
    if (a != SDL_CONTROLLER_AXIS_INVALID)
        return PAD_AXIS(a, neg);
    return 1000;                        /* unknown */
}

int xbox_pad_bind(const char *control, const char *input)
{
    int i, in = pad_input_from_name(input);
    if (in == 1000)
        return 0;
    for (i = 0; i < 16; i++)
        if (!strcmp(control, k_pad_ctl[i])) {
            s_pad_bind[i] = in;
            return 1;
        }
    return 0;
}

void xbox_pad_reset(void)
{
    memcpy(s_pad_bind, k_pad_default, sizeof s_pad_bind);
}

/* Pad 1's name (NULL: none), how many are attached, and the next one as pad 1. */
const char *xbox_pad_name(void)
{
    SDL_GameController *c = g_pads[0];
    return c && SDL_GameControllerGetAttached(c) ? SDL_GameControllerName(c) : NULL;
}

int xbox_pad_count(void)
{
    int i, n = 0;
    for (i = 0; i < XBOX_MAX_CONTROLLERS; i++)
        n += g_pads[i] && SDL_GameControllerGetAttached(g_pads[i]);
    return n;
}

void xbox_pad_cycle(void)
{
    SDL_GameController *first = g_pads[0];
    int i, last = 0;
    for (i = 1; i < XBOX_MAX_CONTROLLERS; i++)
        if (g_pads[i]) {
            g_pads[last] = g_pads[i];
            last = i;
        }
    g_pads[last] = first;
}

/* For a remap screen: an SDL input newly pressed on pad 1 since the last
 * call (a button, or an axis past 60%), by its SDL name; 1 if there is one. */
int xbox_pad_poll_new(char *out, int n)
{
    static int prev[SDL_CONTROLLER_BUTTON_MAX + 2 * SDL_CONTROLLER_AXIS_MAX];
    SDL_GameController *c = g_pads[0];
    int i, found = -1;
    if (!c || !SDL_GameControllerGetAttached(c))
        return 0;
    for (i = 0; i < SDL_CONTROLLER_BUTTON_MAX + 2 * SDL_CONTROLLER_AXIS_MAX; i++) {
        int now;
        if (i < SDL_CONTROLLER_BUTTON_MAX) {
            now = SDL_GameControllerGetButton(c, (SDL_GameControllerButton)i);
        } else {
            int a = (i - SDL_CONTROLLER_BUTTON_MAX) / 2, v = SDL_GameControllerGetAxis(c, (SDL_GameControllerAxis)a);
            now = (i - SDL_CONTROLLER_BUTTON_MAX) & 1 ? v < -20000 : v > 20000;
        }
        if (now && !prev[i] && found < 0)
            found = i;
        prev[i] = now;
    }
    if (found < 0)
        return 0;
    if (found < SDL_CONTROLLER_BUTTON_MAX) {
        snprintf(out, (size_t)n, "%s", SDL_GameControllerGetStringForButton((SDL_GameControllerButton)found));
    } else {
        int a = (found - SDL_CONTROLLER_BUTTON_MAX) / 2;
        snprintf(out, (size_t)n, "%s%s", (found - SDL_CONTROLLER_BUTTON_MAX) & 1 ? "-" : "",
                 SDL_GameControllerGetStringForAxis((SDL_GameControllerAxis)a));
    }
    return 1;
}

#if defined(__ANDROID__)
/* The on-screen controls (src/android.c), on top of pad 1 like the keyboard. */
void android_touch_apply(unsigned short *wButtons, unsigned char analog[8], short thumbs[4]);

static void touch_apply(XBOX_INPUT_STATE *s)
{
    short th[4] = { s->Gamepad.sThumbLX, s->Gamepad.sThumbLY,
                    s->Gamepad.sThumbRX, s->Gamepad.sThumbRY };
    unsigned short w = s->Gamepad.wButtons;

    android_touch_apply(&w, s->Gamepad.bAnalogButtons, th);
    s->Gamepad.wButtons = w;
    s->Gamepad.sThumbLX = th[0];
    s->Gamepad.sThumbLY = th[1];
    s->Gamepad.sThumbRX = th[2];
    s->Gamepad.sThumbRY = th[3];
}
#else
#define touch_apply(s) ((void)0)
#endif

#if !defined(__SWITCH__)
/* CLX_RUMBLE_TEST=1: five seconds after the first poll, pad 1 rumbles at
 * full strength for a second through the game's own path
 * (xbox_InputSetState), and the log says which way it went. It tells a
 * controller or phone that cannot rumble from a game that never asks. */
static int s_rumble_test_log;

static void rumble_test_tick(void)
{
    static int state = -1;      /* -1 unread, 0 off or done, 1 waiting, 2 on */
    static Uint32 t0;
    Uint32 now = SDL_GetTicks();
    XBOX_VIBRATION v;

    if (state < 0) {
        const char *e = getenv("CLX_RUMBLE_TEST");
        state = (e && *e && *e != '0') ? 1 : 0;
        t0 = now;
    }
    if (state == 1 && now - t0 >= 5000) {
        fprintf(stderr, "  [rumble test] pad 1 on: %s\n",
                g_pads[0] ? SDL_GameControllerName(g_pads[0]) : "no SDL controller");
        v.wLeftMotorSpeed = v.wRightMotorSpeed = 0xFFFF;
        s_rumble_test_log = 1;
        xbox_InputSetState(0, &v);
        state = 2;
        t0 = now;
    } else if (state == 2 && now - t0 >= 1000) {
        v.wLeftMotorSpeed = v.wRightMotorSpeed = 0;
        xbox_InputSetState(0, &v);
        s_rumble_test_log = 0;
        fprintf(stderr, "  [rumble test] pad 1 off\n");
        state = 0;
    }
}
#endif

DWORD xbox_InputGetState(DWORD dwPort, XBOX_INPUT_STATE *pState)
{
    if (dwPort >= XBOX_MAX_CONTROLLERS || !pState)
        return ERROR_DEVICE_NOT_CONNECTED;

#if defined(__SWITCH__)
    /* The console's own controllers, mapped by position (xinput_nx.c). */
    {
        uint16_t dig;
        uint8_t ana[8];
        int16_t th[4];
        int i;

        if (!xbox_nx_pad_read(dwPort, &dig, ana, th)) {
            g_controller_connected[dwPort] = FALSE;
            return ERROR_DEVICE_NOT_CONNECTED;
        }
        g_controller_connected[dwPort] = TRUE;
        memset(pState, 0, sizeof(XBOX_INPUT_STATE));
        pState->dwPacketNumber = ++g_packet[dwPort];
        pState->Gamepad.wButtons = dig;
        for (i = 0; i < 8; i++)
            pState->Gamepad.bAnalogButtons[i] = ana[i];
        pState->Gamepad.sThumbLX = th[0];
        pState->Gamepad.sThumbLY = th[1];
        pState->Gamepad.sThumbRX = th[2];
        pState->Gamepad.sThumbRY = th[3];
        return ERROR_SUCCESS;
    }
#endif

    SDL_GameControllerUpdate();
#if !defined(__SWITCH__)
    if (dwPort == 0) {
        static Uint32 last;
        Uint32 now = SDL_GetTicks();
        if (!last || now - last > 1000) {
            last = now;
            refresh_controllers();
        }
        rumble_test_tick();
    }
#endif
    SDL_GameController *c = g_pads[dwPort];
    memset(pState, 0, sizeof(XBOX_INPUT_STATE));
    if (!c || !SDL_GameControllerGetAttached(c)) {
#if !defined(__SWITCH__)
        /* On a PC the keyboard is pad 1 (sdl_keys.h), with or without a pad. */
        if (dwPort == 0) {
            int n = 0;
            const Uint8 *ks = SDL_GetKeyboardState(&n);
            if (ks)
                xbox_keys_apply(ks, n, pState);
            touch_apply(pState);
            g_controller_connected[0] = TRUE;
            pState->dwPacketNumber = ++g_packet[0];
            return ERROR_SUCCESS;
        }
#endif
        g_controller_connected[dwPort] = FALSE;
        return ERROR_DEVICE_NOT_CONNECTED;
    }

    g_controller_connected[dwPort] = TRUE;
    pState->dwPacketNumber = ++g_packet[dwPort];

    {
        /* Each control from its bound SDL input (pad_bind_*: the defaults
         * below unless the port rebinds them, xbox_pad_bind). */
        static const WORD dig[8] = {
            XBOX_GAMEPAD_DPAD_UP, XBOX_GAMEPAD_DPAD_DOWN, XBOX_GAMEPAD_DPAD_LEFT,
            XBOX_GAMEPAD_DPAD_RIGHT, XBOX_GAMEPAD_START, XBOX_GAMEPAD_BACK,
            XBOX_GAMEPAD_LEFT_THUMB, XBOX_GAMEPAD_RIGHT_THUMB,
        };
        WORD btn = 0;
        int k;
        for (k = 0; k < 8; k++)
            if (pad_level(c, k) > 127)
                btn |= dig[k];
        pState->Gamepad.wButtons = btn;
        for (k = 0; k < 8; k++)         /* A B X Y black white LT RT: analog 0..7 */
            pState->Gamepad.bAnalogButtons[k] = (BYTE)pad_level(c, 8 + k);
    }

    /* SDL Y axis points down; the Xbox Y axis points up -- invert.
     * Use (-1 - v) so v = -32768 does not overflow SHORT. */
    pState->Gamepad.sThumbLX = SDL_GameControllerGetAxis(c, SDL_CONTROLLER_AXIS_LEFTX);
    pState->Gamepad.sThumbLY =
        (SHORT)(-1 - SDL_GameControllerGetAxis(c, SDL_CONTROLLER_AXIS_LEFTY));
    pState->Gamepad.sThumbRX = SDL_GameControllerGetAxis(c, SDL_CONTROLLER_AXIS_RIGHTX);
    pState->Gamepad.sThumbRY =
        (SHORT)(-1 - SDL_GameControllerGetAxis(c, SDL_CONTROLLER_AXIS_RIGHTY));
#if !defined(__SWITCH__)
    if (dwPort == 0) {                  /* the keyboard, on top of pad 1 */
        int n = 0;
        const Uint8 *ks = SDL_GetKeyboardState(&n);
        if (ks)
            xbox_keys_apply(ks, n, pState);
        touch_apply(pState);
    }
#endif

    return ERROR_SUCCESS;
}

DWORD xbox_InputSetState(DWORD dwPort, const XBOX_VIBRATION *pVibration)
{
    if (dwPort >= XBOX_MAX_CONTROLLERS || !pVibration)
        return ERROR_DEVICE_NOT_CONNECTED;

#if defined(__SWITCH__)
    /* The console's own controllers (xinput_nx.c), not SDL's. */
    xbox_nx_pad_rumble(dwPort, pVibration->wLeftMotorSpeed,
                       pVibration->wRightMotorSpeed);
    return ERROR_SUCCESS;
#else
    SDL_GameController *c = g_pads[dwPort];

    /* SDL rumble needs a duration. The USB pad model passes changes only
     * (usb_gamepad_output), so a rumble lasts until the next call -- SDL's
     * longest; zero speeds stop it. This was 1 s, which cut every longer
     * rumble short. */
    if (c) {
        int r = SDL_GameControllerRumble(c, pVibration->wLeftMotorSpeed,
                                         pVibration->wRightMotorSpeed, 0xFFFF);
        if (s_rumble_test_log)
            fprintf(stderr, "  [rumble test] SDL rumble: %s\n",
                    r == 0 ? "accepted" : SDL_GetError());
        if (r == 0)
            return ERROR_SUCCESS;
    }
#if defined(__ANDROID__)
    /* SDL has no rumble for Android's own joysticks; Rumble.java does it,
     * and vibrates the phone for pad 1 on the touch controls. */
    {
        extern const char *android_rumble(int port, unsigned low, unsigned high);
        const char *how = android_rumble((int)dwPort, pVibration->wLeftMotorSpeed,
                                         pVibration->wRightMotorSpeed);
        if (s_rumble_test_log)
            fprintf(stderr, "  [rumble test] Rumble.java: %s\n", how);
        return ERROR_SUCCESS;
    }
#else
    return c ? ERROR_SUCCESS : ERROR_DEVICE_NOT_CONNECTED;
#endif
#endif
}

BOOL xbox_InputIsConnected(DWORD dwPort)
{
    if (dwPort >= XBOX_MAX_CONTROLLERS) return FALSE;
    return g_controller_connected[dwPort];
}

DWORD xbox_InputGetCapabilities(DWORD dwPort, DWORD dwFlags, XBOX_INPUT_CAPABILITIES *pCaps)
{
    (void)dwFlags;
    if (dwPort >= XBOX_MAX_CONTROLLERS || !pCaps)
        return ERROR_DEVICE_NOT_CONNECTED;
    if (!g_pads[dwPort])
        return ERROR_DEVICE_NOT_CONNECTED;

    memset(pCaps, 0, sizeof(XBOX_INPUT_CAPABILITIES));
    pCaps->Type    = 1;   /* XINPUT_DEVTYPE_GAMEPAD */
    pCaps->SubType = 1;   /* XINPUT_DEVSUBTYPE_GAMEPAD */
    pCaps->Flags   = 0;
    return ERROR_SUCCESS;
}

#endif /* _WIN32 && !XBOXRECOMP_SDL_INPUT */
