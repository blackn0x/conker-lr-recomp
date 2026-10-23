"""Two-channel and packed texture formats decode instead of turning magenta.

A8L8 (0x1A, linear 0x20), AL8 (0x01 / 0x1B), G8B8 (0x28 / 0x17) and R8B8
(0x29 / 0x16) had no case in sample_texture (src/kernel/nv2a_pb_exec.c), so
the GL and Vulkan back ends uploaded their 1x1 magenta "not decodable"
texture. Conker: Live & Reloaded's fur shells sample an A8L8 texture: the
player was a shaded pink egg. The first named channel is the high byte, as in
A8R8G8B8.

The test compiles the real linear_twin/wrap_coord/expand/sample_texture with
d3d8_swizzle.h and checks texels of each format, swizzled and linear.

    python3 -m pytest tools/recomp/test_tex_two_channel.py
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


def test_two_channel_formats_decode():
    cc = os.environ.get('CC') or shutil.which('cc') or shutil.which('gcc')
    if not cc:
        pytest.skip('no C compiler')
    src = open(SRC).read()
    tex = re.search(r'typedef struct \{\n    uint32_t offset;[^}]*\} Texture;',
                    src).group(0)
    prog = ('#include <stdint.h>\n#include <stdio.h>\n'
            '#include "%s"\n' % os.path.join(ROOT, 'src', 'd3d', 'd3d8_swizzle.h')
            + 'static uint8_t g_mem[4096];\n'
            'static void *xbox_GetMemoryOffset(void) { return g_mem; }\n'
            + tex + '\n'
            + ''.join(_func(src, n) for n in
                      ('wrap_coord', 'expand', 'linear_twin', 'sample_texture'))
            + r'''
static int bad;
static void check(uint32_t color, uint32_t pitch, uint32_t u, uint32_t v,
                  uint32_t want) {
    Texture t = {0x100, 2, 2, pitch, color, 3, 3, 1};
    uint32_t got = 0;
    if (!sample_texture(&t, u, v, &got) || got != want) {
        printf("fmt %02X (%u,%u): %08X want %08X\n", color, u, v, got, want);
        bad = 1;
    }
}
int main(void) {
    /* 2x2, 16-bit texels 0x1122 0x3344 / 0x5566 0x7788 (row-major; a 2x2
     * swizzle is (0,0) (1,0) (0,1) (1,1), the same order). */
    static const uint16_t w16[4] = {0x1122, 0x3344, 0x5566, 0x7788};
    memcpy(g_mem + 0x100, w16, sizeof w16);
    check(0x1A, 0, 0, 0, 0x11222222u);      /* A8L8: A=11, L=22 */
    check(0x1A, 0, 1, 1, 0x77888888u);
    check(0x20, 4, 1, 0, 0x33444444u);      /* LIN_A8L8 */
    check(0x28, 0, 0, 1, 0xFF005566u);      /* G8B8: G=55, B=66 */
    check(0x17, 4, 1, 1, 0xFF007788u);
    check(0x29, 0, 1, 0, 0xFF330044u);      /* R8B8: R=33, B=44 */
    check(0x16, 4, 0, 0, 0xFF110022u);
    /* AL8: high nibble alpha, low nibble luminance. */
    g_mem[0x100] = 0x3C; g_mem[0x101] = 0xF0;
    check(0x01, 0, 0, 0, 0x33CCCCCCu);
    check(0x1B, 2, 1, 0, 0xFF000000u);
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
