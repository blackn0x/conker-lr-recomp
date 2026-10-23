"""A Z buffer sampled as a colour texture gets the byte order of that format.

Conker: Live & Reloaded's depth of field reads its Z24S8 buffer twice: as
LIN_R8G8B8A8 (0x41) for the blur mask and as LIN_A8B8G8R8 (0x3F) for the
composite, whose alpha (the top depth byte) says how much blur covers each
pixel. The GL and Vulkan back ends pack their depth images into colour for
those reads; they packed every read in the 0x41 order, so the composite got
the stencil byte as alpha and every cutscene came out blurred all over.

nv2a_depth_texel_order (src/kernel/nv2a_backend.h) now gives the order per
format. The test decodes the dword (z << 8) | s with the real sample_texture
and checks that each channel is the byte the helper names.

    python3 -m pytest tools/recomp/test_depth_texel_order.py
"""
import os
import re
import shutil
import subprocess
import tempfile

import pytest

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))
SRC = os.path.join(ROOT, 'src', 'kernel', 'nv2a_pb_exec.c')


def _func(src, name):
    m = re.search(r'^static (?:int|uint32_t) %s\([^;{]*\)\n\{.*?^\}\n' % name, src,
                  re.S | re.M)
    assert m, name
    return m.group(0)


def test_depth_texel_order_matches_decoder():
    cc = os.environ.get('CC') or shutil.which('cc') or shutil.which('gcc')
    if not cc:
        pytest.skip('no C compiler')
    src = open(SRC).read()
    tex = re.search(r'typedef struct \{\n    uint32_t offset;[^}]*\} Texture;',
                    src).group(0)
    prog = ('#include <stdint.h>\n#include <stdio.h>\n#include <string.h>\n'
            '#include "%s"\n' % os.path.join(ROOT, 'src', 'd3d', 'd3d8_swizzle.h')
            + '#include "%s"\n' % os.path.join(ROOT, 'src', 'kernel', 'nv2a_backend.h')
            + 'static uint8_t g_mem[4096];\n'
            'static void *xbox_GetMemoryOffset(void) { return g_mem; }\n'
            + tex + '\n'
            + ''.join(_func(src, n) for n in
                      ('wrap_coord', 'expand', 'linear_twin', 'sample_texture'))
            + r'''
int main(void) {
    static const uint32_t fmts[] = {0x41, 0x3F, 0x40, 0x12, 0x06};
    const uint32_t d = (0xABCDEFu << 8) | 0x5Au;      /* z = ABCDEF, stencil 5A */
    int bad = 0;
    unsigned i;
    memcpy(g_mem + 0x100, &d, 4);
    for (i = 0; i < sizeof fmts / sizeof fmts[0]; i++) {
        Texture t = {0x100, 1, 1, 4, fmts[i], 3, 3, 1};
        uint32_t argb = 0, o = nv2a_depth_texel_order(fmts[i]), want;
        uint32_t r = (d >> 8 * (o & 3)) & 0xFF, g = (d >> 8 * ((o >> 2) & 3)) & 0xFF;
        uint32_t b = (d >> 8 * ((o >> 4) & 3)) & 0xFF, a = (d >> 8 * ((o >> 6) & 3)) & 0xFF;
        want = a << 24 | r << 16 | g << 8 | b;
        if (!sample_texture(&t, 0, 0, &argb) || argb != want) {
            printf("fmt %02X: decoder %08X, helper order gives %08X\n", fmts[i], argb, want);
            bad = 1;
        }
    }
    return bad;
}
''')
    with tempfile.TemporaryDirectory() as d:
        c, exe = os.path.join(d, 't.c'), os.path.join(d, 't')
        open(c, 'w').write(prog)
        r = subprocess.run([cc, '-std=c11', c, '-o', exe],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-3000:]
        r = subprocess.run([exe], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
