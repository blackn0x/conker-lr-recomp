"""Keyboard as pad 1 on a PC: the default layout and a rebinding.

src/input/sdl_keys.c maps keys held (an SDL keyboard state, indexed by
scancode) onto an XBOX_INPUT_STATE: WASD the left stick, arrows/IJKL the
right stick, Space A, E B, Esc BACK, and so on (sdl_keys.h). The test
compiles it against SDL2's headers with SDL_GetScancodeFromName stubbed, so
no window or SDL library is needed.

    python3 -m pytest tools/recomp/test_sdl_keys.py
"""
import os
import shutil
import subprocess
import tempfile

import pytest

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))
INPUT = os.path.join(ROOT, 'src', 'input')

PROG = r'''
#include <stdio.h>
#include <string.h>
#include <SDL_keyboard.h>
#include "sdl_keys.h"

SDL_Scancode SDL_GetScancodeFromName(const char *name)
{
    return !strcmp(name, "Return") ? SDL_SCANCODE_RETURN : SDL_SCANCODE_UNKNOWN;
}

const char *SDL_GetScancodeName(SDL_Scancode sc)
{
    return sc == SDL_SCANCODE_F ? "F" : "?";
}

static int bad;
#define CHECK(c) do { if (!(c)) { printf("failed: %s\n", #c); bad = 1; } } while (0)

int main(void)
{
    static uint8_t ks[SDL_NUM_SCANCODES];
    XBOX_INPUT_STATE s;

    memset(&s, 0, sizeof s);
    CHECK(xbox_keys_apply(ks, SDL_NUM_SCANCODES, &s) == 0);   /* nothing held */

    ks[SDL_SCANCODE_W] = ks[SDL_SCANCODE_D] = ks[SDL_SCANCODE_SPACE] = 1;
    ks[SDL_SCANCODE_LEFT] = ks[SDL_SCANCODE_ESCAPE] = ks[SDL_SCANCODE_LSHIFT] = 1;
    memset(&s, 0, sizeof s);
    CHECK(xbox_keys_apply(ks, SDL_NUM_SCANCODES, &s) == 1);
    CHECK(s.Gamepad.sThumbLY == 32767 && s.Gamepad.sThumbLX == 32767);
    CHECK(s.Gamepad.sThumbRX == -32767 && s.Gamepad.sThumbRY == 0);
    CHECK(s.Gamepad.bAnalogButtons[XBOX_BUTTON_A] == 255);
    CHECK(s.Gamepad.bAnalogButtons[XBOX_BUTTON_LTRIGGER] == 255);
    CHECK(s.Gamepad.bAnalogButtons[XBOX_BUTTON_B] == 0);
    CHECK(s.Gamepad.wButtons == XBOX_GAMEPAD_BACK);

    /* A pad's own deflection plus a key: clamped, not wrapped. */
    memset(&s, 0, sizeof s);
    s.Gamepad.sThumbLY = 20000;
    xbox_keys_apply(ks, SDL_NUM_SCANCODES, &s);
    CHECK(s.Gamepad.sThumbLY == 32767);

    /* key_a=Return: A moves to Enter, Space no longer presses it. */
    CHECK(xbox_keys_bind("a", "Return") == 1);
    CHECK(xbox_keys_bind("nonsense", "Return") == 0);
    CHECK(xbox_keys_bind("b", "NoSuchKey") == 0);
    memset(&s, 0, sizeof s);
    xbox_keys_apply(ks, SDL_NUM_SCANCODES, &s);
    CHECK(s.Gamepad.bAnalogButtons[XBOX_BUTTON_A] == 0);
    ks[SDL_SCANCODE_RETURN] = 1;
    memset(&s, 0, sizeof s);
    xbox_keys_apply(ks, SDL_NUM_SCANCODES, &s);
    CHECK(s.Gamepad.bAnalogButtons[XBOX_BUTTON_A] == 255);

    /* Reset: Space is A again. */
    xbox_keys_reset();
    ks[SDL_SCANCODE_RETURN] = 0;
    memset(&s, 0, sizeof s);
    xbox_keys_apply(ks, SDL_NUM_SCANCODES, &s);
    CHECK(s.Gamepad.bAnalogButtons[XBOX_BUTTON_A] == 255);

    /* Remap poll: keys held at the first call are not new; F pressed after is. */
    {
        char name[16];
        xbox_keys_poll_new(ks, SDL_NUM_SCANCODES, name, sizeof name);
        CHECK(xbox_keys_poll_new(ks, SDL_NUM_SCANCODES, name, sizeof name) == 0);
        ks[SDL_SCANCODE_F] = 1;
        CHECK(xbox_keys_poll_new(ks, SDL_NUM_SCANCODES, name, sizeof name) == 1 && !strcmp(name, "F"));
        CHECK(xbox_keys_poll_new(ks, SDL_NUM_SCANCODES, name, sizeof name) == 0);
    }
    return bad;
}
'''


def _sdl_include():
    for d in ('/usr/include/SDL2', '/usr/local/include/SDL2'):
        if os.path.exists(os.path.join(d, 'SDL_keyboard.h')):
            return d
    return None


def test_keyboard_layout_and_binding():
    cc = os.environ.get('CC') or shutil.which('cc') or shutil.which('gcc')
    sdl = _sdl_include()
    if not cc or not sdl:
        pytest.skip('no C compiler or SDL2 headers')
    with tempfile.TemporaryDirectory() as d:
        c, exe = os.path.join(d, 't.c'), os.path.join(d, 't')
        open(c, 'w').write(PROG)
        r = subprocess.run([cc, '-std=c11', '-I', sdl, '-I', INPUT, '-I', os.path.join(ROOT, 'src'),
                            c, os.path.join(INPUT, 'sdl_keys.c'), '-o', exe],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-3000:]
        r = subprocess.run([exe], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
