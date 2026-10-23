"""`fincstp` / `fdecstp` rotate the x87 TOP.

They were lifted as comments. MSVC uses `fincstp` to park a value without
popping it: the old st(0) stays in its register and comes back as st(7), then
st(6) after the next pop. Conker: Live & Reloaded's rotation-matrix builder
(0x003E2E60) does

    fsincos x3; fst; fmul st(6); fincstp; fmul st(5), st(0); fstp; ...
    fmul st(6)        ; reads the parked value

With fincstp a no-op every later st(i) was one slot off, the camera's roll
matrix came out degenerate and the title and single-player scenes drew
nothing but the sky colour.

The test lifts those bytes, compiles them and checks the stores against the
x87 result worked out by hand.

    python3 -m pytest tools/recomp/test_fincstp.py
"""
import math
import os
import shutil
import subprocess
import tempfile

import pytest

from .disasm import Disassembler, Instruction
from .lifter import Lifter

# 0x003E2E6B..0x003E2EAE of Conker's default.xbe (esp already lowered by 0x18).
CONKER = bytes.fromhex(
    'd9442420' 'd9442428' 'd9fb' 'd9442430' 'd9fb' 'd944242c' 'd9fb'
    'd954240c' 'd8ce' 'd9f7' 'dccd' 'd95c2414' 'd9542408' 'd8ce' 'd918'
    'd9542404' 'd8cd' 'd95804' 'd95c2410' 'd91c24' 'd9e0' 'd95808' 'ddc1')

PRELUDE = r'''
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static unsigned char mem[0x100];
static double g_fp_stack[8];
static unsigned g_fp_top;
static uint32_t esp = 0x40, eax = 0xC0;
#define MEMF(a) (*(float *)(mem + (a)))
#define RECOMP_FP_PC(x) (x)
#define fp_push(v) do { double _fp_value = (v); \
    g_fp_top = (g_fp_top + 7u) & 7u; g_fp_stack[g_fp_top] = _fp_value; } while (0)
#define fp_pop() (g_fp_top = (g_fp_top + 1u) & 7u)
#define fp_top() g_fp_stack[g_fp_top]
#define fp_st(i) g_fp_stack[(g_fp_top + (i)) & 7u]
#define fp_st1() fp_st(1)
int main(void) {
    MEMF(esp + 0x20) = 2.0f;   /* scale */
    MEMF(esp + 0x28) = 0.3f;   /* a */
    MEMF(esp + 0x30) = -0.7f;  /* b */
    MEMF(esp + 0x2C) = 1.1f;   /* c */
'''


def _lifted():
    d = Disassembler()
    insns = [d._decode_instruction(i) for i in d._cs.disasm(CONKER, 0x003E2E6B)]
    assert insns[-1].mnemonic == 'ffree'
    lifter = Lifter()
    return [line for i in insns for line in lifter.lift_instruction(i)]


def test_fincstp_and_fdecstp_move_top():
    lifter = Lifter()
    for m, step in (('fincstp', '1u'), ('fdecstp', '7u')):
        out = lifter.lift_instruction(Instruction(0, 2, m, '', ''))
        assert out == ['g_fp_top = (g_fp_top + %s) & 7u; /* %s */' % (step, m)]


def test_conker_rotation_builder_matches_x87():
    cc = os.environ.get('CC') or shutil.which('cc') or shutil.which('gcc')
    if not cc:
        pytest.skip('no C compiler')
    body = '\n'.join('    ' + line for line in _lifted())
    src = PRELUDE + body + r'''
    printf("%.6f %.6f %.6f %.6f %.6f %.6f %.6f %.6f\n",
           MEMF(eax), MEMF(eax + 4), MEMF(eax + 8), MEMF(esp + 0xC),
           MEMF(esp + 0x14), MEMF(esp + 8), MEMF(esp + 4), MEMF(esp + 0x10));
    printf("%u\n", g_fp_top);
    return 0;
}
'''
    with tempfile.TemporaryDirectory() as tmp:
        c = os.path.join(tmp, 't.c')
        exe = os.path.join(tmp, 't')
        with open(c, 'w') as f:
            f.write(src)
        subprocess.run([cc, '-O1', '-o', exe, c, '-lm'], check=True)
        out = subprocess.run([exe], check=True, capture_output=True,
                             text=True).stdout.split('\n')
    got = [float(v) for v in out[0].split()]
    k, a, b, c_ = 2.0, 0.3, -0.7, 1.1
    a, b, c_ = (float.fromhex(float(v).hex()) for v in (a, b, c_))
    want = [math.cos(b) * math.cos(c_) * k,   # [eax]
            math.sin(b) * math.cos(c_) * k,   # [eax+4]
            -math.sin(c_) * k,                # [eax+8]
            math.cos(c_), math.sin(c_),       # [esp+0xC], [esp+0x14]
            math.cos(b), math.sin(b),         # [esp+8], [esp+4]
            math.cos(a)]                      # [esp+0x10]
    assert got == pytest.approx(want, abs=1e-5)
    # Pushed 7, popped 6 and parked one with fincstp: TOP is back where it was.
    assert int(out[1]) == 0
