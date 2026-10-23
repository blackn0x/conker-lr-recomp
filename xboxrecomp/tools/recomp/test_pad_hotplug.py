"""PC pads come and go while the game runs (SDL2 hot-plug).

xbox_InputGetState (src/input/xinput_device.c, SDL path) looks for new and
removed game controllers once a second: a pad plugged in takes the first
free slot, one pulled out is closed. The test attaches an SDL virtual game
controller (SDL >= 2.24), presses A on it, then detaches it. The keyboard
always answers for pad 1 on a PC, so port 0 stays connected throughout.

    python3 -m pytest tools/recomp/test_pad_hotplug.py
"""
import os
import shutil
import subprocess
import tempfile

import pytest

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))
SRC = os.path.join(ROOT, 'src')

PROG = r'''
#include <SDL.h>
#include <stdio.h>
#include "input/xinput_xbox.h"

static int bad;
#define CHECK(c) do { if (!(c)) { printf("failed: %s\n", #c); bad = 1; } } while (0)

static void poll_after(int ms, XBOX_INPUT_STATE *s)
{
    SDL_Delay(ms);
    SDL_PumpEvents();
    xbox_InputGetState(0, s);
}

int main(void)
{
    XBOX_INPUT_STATE s;
    SDL_VirtualJoystickDesc d;
    int idx;
    SDL_Joystick *j;

    if (SDL_Init(SDL_INIT_GAMECONTROLLER | SDL_INIT_VIDEO) != 0) {
        printf("SDL_Init: %s\n", SDL_GetError());
        return 2;
    }
    xbox_InputInit();
    poll_after(0, &s);
    CHECK(s.Gamepad.bAnalogButtons[XBOX_BUTTON_A] == 0);

    SDL_zero(d);
    d.version = SDL_VIRTUAL_JOYSTICK_DESC_VERSION;
    d.type = SDL_JOYSTICK_TYPE_GAMECONTROLLER;
    d.naxes = SDL_CONTROLLER_AXIS_MAX;
    d.nbuttons = SDL_CONTROLLER_BUTTON_MAX;
    d.name = "virtual pad";
    idx = SDL_JoystickAttachVirtualEx(&d);
    CHECK(idx >= 0);
    j = SDL_JoystickOpen(idx);
    SDL_JoystickSetVirtualButton(j, SDL_CONTROLLER_BUTTON_A, 1);
    poll_after(1100, &s);                  /* the next once-a-second look */
    poll_after(10, &s);
    CHECK(s.Gamepad.bAnalogButtons[XBOX_BUTTON_A] == 255);

    SDL_JoystickClose(j);
    SDL_JoystickDetachVirtual(idx);
    poll_after(1100, &s);
    poll_after(10, &s);
    CHECK(s.Gamepad.bAnalogButtons[XBOX_BUTTON_A] == 0);
    CHECK(xbox_InputIsConnected(0));       /* the keyboard */
    SDL_Quit();
    return bad;
}
'''


def test_pad_hotplug():
    cc = os.environ.get('CC') or shutil.which('cc') or shutil.which('gcc')
    cfg = shutil.which('sdl2-config')
    if not cc or not cfg:
        pytest.skip('no C compiler or SDL2')
    ver = subprocess.run([cfg, '--version'], capture_output=True, text=True).stdout.strip()
    if tuple(int(x) for x in ver.split('.')[:2]) < (2, 24):
        pytest.skip('SDL %s has no virtual game controllers' % ver)
    flags = subprocess.run([cfg, '--cflags', '--libs'], capture_output=True, text=True).stdout.split()
    with tempfile.TemporaryDirectory() as d:
        c, exe = os.path.join(d, 't.c'), os.path.join(d, 't')
        open(c, 'w').write(PROG)
        r = subprocess.run([cc, '-std=gnu11', '-I', SRC, '-I', os.path.join(SRC, 'input'), c,
                            os.path.join(SRC, 'input', 'xinput_device.c'),
                            os.path.join(SRC, 'input', 'sdl_keys.c'), '-o', exe] + flags,
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-3000:]
        env = dict(os.environ, SDL_VIDEODRIVER='offscreen')
        r = subprocess.run([exe], capture_output=True, text=True, env=env, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr
    assert '[PAD] controller 1: virtual pad' in r.stderr
    assert '[PAD] controller 1 removed' in r.stderr
