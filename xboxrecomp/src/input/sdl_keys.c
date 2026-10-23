/* Keyboard as pad 1 on a PC: see sdl_keys.h. */
#include "sdl_keys.h"

#include <SDL_keyboard.h>
#include <SDL_scancode.h>
#include <stdio.h>
#include <string.h>

enum {
    K_UP, K_DOWN, K_LEFT, K_RIGHT, K_START, K_BACK, K_LTHUMB, K_RTHUMB,
    K_A, K_B, K_X, K_Y, K_BLACK, K_WHITE, K_LT, K_RT,
    K_LSU, K_LSD, K_LSL, K_LSR, K_RSU, K_RSD, K_RSL, K_RSR, K_N
};

static const char *const k_names[K_N] = {
    "up", "down", "left", "right", "start", "back", "lthumb", "rthumb",
    "a", "b", "x", "y", "black", "white", "lt", "rt",
    "ls_up", "ls_down", "ls_left", "ls_right", "rs_up", "rs_down", "rs_left", "rs_right",
};

/* Up to two keys per control (0 = none). */
static const int k_default[K_N][2] = {
    { SDL_SCANCODE_1 }, { SDL_SCANCODE_2 }, { SDL_SCANCODE_3 }, { SDL_SCANCODE_4 },
    { SDL_SCANCODE_RETURN }, { SDL_SCANCODE_ESCAPE },
    { SDL_SCANCODE_C }, { SDL_SCANCODE_V },
    { SDL_SCANCODE_SPACE }, { SDL_SCANCODE_E }, { SDL_SCANCODE_Q }, { SDL_SCANCODE_R },
    { SDL_SCANCODE_X }, { SDL_SCANCODE_Z }, { SDL_SCANCODE_LSHIFT }, { SDL_SCANCODE_LCTRL },
    { SDL_SCANCODE_W }, { SDL_SCANCODE_S }, { SDL_SCANCODE_A }, { SDL_SCANCODE_D },
    { SDL_SCANCODE_UP, SDL_SCANCODE_I }, { SDL_SCANCODE_DOWN, SDL_SCANCODE_K },
    { SDL_SCANCODE_LEFT, SDL_SCANCODE_J }, { SDL_SCANCODE_RIGHT, SDL_SCANCODE_L },
};
static int s_keys[K_N][2];
static int s_keys_set;

void xbox_keys_reset(void)
{
    memcpy(s_keys, k_default, sizeof s_keys);
    s_keys_set = 1;
}

int xbox_keys_bind(const char *control, const char *key)
{
    int i, sc = (int)SDL_GetScancodeFromName(key);
    if (!s_keys_set)
        xbox_keys_reset();
    if (sc <= 0)
        return 0;
    for (i = 0; i < K_N; i++)
        if (!strcmp(control, k_names[i])) {
            s_keys[i][0] = sc;
            s_keys[i][1] = 0;
            return 1;
        }
    return 0;
}

static int held(const uint8_t *ks, int n, int c)
{
    int k;
    for (k = 0; k < 2; k++)
        if (s_keys[c][k] > 0 && s_keys[c][k] < n && ks[s_keys[c][k]])
            return 1;
    return 0;
}

/* A thumb axis from two controls: full deflection, added to the pad's. */
static SHORT axis(const uint8_t *ks, int n, int neg, int pos, SHORT pad)
{
    int v = pad;
    if (held(ks, n, neg)) v -= 32767;
    if (held(ks, n, pos)) v += 32767;
    return (SHORT)(v < -32767 ? -32767 : v > 32767 ? 32767 : v);
}

int xbox_keys_apply(const uint8_t *ks, int n, XBOX_INPUT_STATE *s)
{
    static const WORD dig[8] = {
        XBOX_GAMEPAD_DPAD_UP, XBOX_GAMEPAD_DPAD_DOWN, XBOX_GAMEPAD_DPAD_LEFT,
        XBOX_GAMEPAD_DPAD_RIGHT, XBOX_GAMEPAD_START, XBOX_GAMEPAD_BACK,
        XBOX_GAMEPAD_LEFT_THUMB, XBOX_GAMEPAD_RIGHT_THUMB,
    };
    int i, any = 0;
    if (!s_keys_set)
        xbox_keys_reset();
    for (i = 0; i < K_N; i++)
        any |= held(ks, n, i);
    if (!any)
        return 0;
    for (i = 0; i < 8; i++)
        if (held(ks, n, K_UP + i))
            s->Gamepad.wButtons |= dig[i];
    for (i = 0; i < 8; i++)             /* A B X Y black white LT RT: analog 0..7 */
        if (held(ks, n, K_A + i))
            s->Gamepad.bAnalogButtons[i] = 255;
    s->Gamepad.sThumbLX = axis(ks, n, K_LSL, K_LSR, s->Gamepad.sThumbLX);
    s->Gamepad.sThumbLY = axis(ks, n, K_LSD, K_LSU, s->Gamepad.sThumbLY);
    s->Gamepad.sThumbRX = axis(ks, n, K_RSL, K_RSR, s->Gamepad.sThumbRX);
    s->Gamepad.sThumbRY = axis(ks, n, K_RSD, K_RSU, s->Gamepad.sThumbRY);
    return 1;
}

int xbox_keys_poll_new(const uint8_t *ks, int n, char *out, int len)
{
    static uint8_t prev[512];
    int i, found = -1;
    if (n > 512)
        n = 512;
    for (i = 1; i < n; i++) {
        if (ks[i] && !prev[i] && found < 0)
            found = i;
        prev[i] = ks[i];
    }
    if (found < 0)
        return 0;
    snprintf(out, (size_t)len, "%s", SDL_GetScancodeName((SDL_Scancode)found));
    return out[0] != 0;
}
