"""The flip shows the scanned-out buffer, not the last offscreen pass.

The executor used to present "the surface the last batch drew into". Conker:
Live & Reloaded's front end draws its 3D scene into the back buffer and then
an offscreen pass at the end of the frame, so every flip showed that pass: a
black title screen. It now remembers the buffers the title scanned out
(PCRTC_START) and shows the last of those that was drawn into. This checks the
set logic (nv2a_scanout_has/add in src/kernel/nv2a_pb_exec.c): physical vs
contiguous/tiled VA of one buffer match, the set keeps the newest entries.

    python3 -m pytest tools/recomp/test_present_scanout.py
"""
import os
import re
import shutil
import subprocess
import tempfile

import pytest

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))


def _source(name):
    src = open(os.path.join(ROOT, 'src', 'kernel', 'nv2a_pb_exec.c')).read()
    m = re.search(r'^(int|void) %s\(.*?\n\{.*?^\}\n' % name, src, re.S | re.M)
    assert m, name
    return m.group(0)


def test_scanout_set():
    cc = os.environ.get('CC') or shutil.which('cc') or shutil.which('gcc')
    if not cc:
        pytest.skip('no C compiler')
    prog = ('#include <stdint.h>\n#include <stdio.h>\n'
            + _source('nv2a_scanout_has') + _source('nv2a_scanout_add') + r'''
int main(void) {
    uint32_t s[4] = {0};
    int bad = 0;
    bad |= nv2a_scanout_has(s, 4, 0x80964000u);          /* empty: nothing */
    nv2a_scanout_add(s, 4, 0x00964000u);
    nv2a_scanout_add(s, 4, 0x00A90000u);
    nv2a_scanout_add(s, 4, 0x00964000u);                 /* no duplicate */
    bad |= !nv2a_scanout_has(s, 4, 0x80964000u) << 1;    /* contiguous VA */
    bad |= !nv2a_scanout_has(s, 4, 0xF0A90000u) << 2;    /* tiled VA */
    bad |= nv2a_scanout_has(s, 4, 0x80B00000u) << 3;     /* offscreen pass */
    bad |= (s[2] != 0) << 4;                             /* two entries only */
    nv2a_scanout_add(s, 4, 0x1000u); nv2a_scanout_add(s, 4, 0x2000u);
    nv2a_scanout_add(s, 4, 0x3000u);                     /* oldest drops out */
    bad |= nv2a_scanout_has(s, 4, 0x00964000u) << 5;
    bad |= !nv2a_scanout_has(s, 4, 0x00A90000u) << 6;
    nv2a_scanout_add(s, 4, 0);                           /* 0 is not a buffer */
    bad |= !nv2a_scanout_has(s, 4, 0x3000u) << 7;
    printf("%d\n", bad);
    return bad;
}
''')
    with tempfile.TemporaryDirectory() as d:
        c, exe = os.path.join(d, 't.c'), os.path.join(d, 't')
        open(c, 'w').write(prog)
        subprocess.run([cc, '-std=c11', c, '-o', exe], check=True,
                       capture_output=True, text=True)
        r = subprocess.run([exe], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
