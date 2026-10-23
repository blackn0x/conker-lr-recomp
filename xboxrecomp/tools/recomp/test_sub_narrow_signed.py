"""Signed conditions after an 8/16-bit `sub` are evaluated at that width.

After `sub a, b` the lifter only has the result (_fa) and the source (_fb),
so jl/jge/jle/jg rebuild the original destination as _fa + _fb and compare
it with _fb. The sum was done in uint32_t: right at 32 bits, where it wraps,
and wrong at 8 and 16, where it does not. `sub ch, cl; jl` with ch=5, cl=15
compared 0x105 with 15 and never jumped; Conker: Live & Reloaded's LZ decoder
(0x0054AAD0, `mov ch, 0x10 ... sub ch, cl; jl refill`) then ran past its
output buffer and faulted at the end of the contiguous window.

The test compiles the emitted expressions and checks them against x86 for
every 8-bit pair and a spread of 16/32-bit pairs.

    python3 -m pytest tools/recomp/test_sub_narrow_signed.py
"""
import os
import shutil
import subprocess
import tempfile

import pytest

from .disasm import Operand
from .lifter import _make_condition

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))
JCCS = {'jl': '<', 'jge': '>=', 'jle': '<=', 'jg': '>'}
WIDTHS = {8: ('ch', 'cl', 'uint8_t', 'int8_t'), 16: ('ax', 'cx', 'uint16_t', 'int16_t'),
          32: ('eax', 'ecx', 'uint32_t', 'int32_t')}


def _cond(jcc, dst, src):
    return _make_condition(jcc, 'sub', [Operand(type='reg', reg=dst),
                                        Operand(type='reg', reg=src)])[0]


def test_reconstruction_is_cast_to_the_operand_width():
    assert '(uint8_t)' in _cond('jl', 'ch', 'cl')
    assert '(uint16_t)' in _cond('jl', 'ax', 'cx')


@pytest.mark.parametrize('bits', [8, 16, 32])
def test_signed_conditions_after_sub_match_x86(bits):
    cc = os.environ.get('CC') or shutil.which('cc') or shutil.which('gcc')
    if not cc:
        pytest.skip('no C compiler')
    dst, src, ut, st = WIDTHS[bits]
    funcs, calls = [], []
    for jcc, op in JCCS.items():
        funcs.append(
            'static int %s_(uint32_t a, uint32_t b) {\n'
            '    uint32_t _fa = (%s)(a - b), _fb = (%s)b;\n'
            '    int32_t _fas = (%s)_fa, _fbs = (%s)_fb;\n'
            '    (void)_fas; (void)_fbs;\n'
            '    return (%s) ? 1 : 0;\n}\n' % (jcc, ut, ut, st, st, _cond(jcc, dst, src)))
        calls.append('        if (%s_(a, b) != (((%s)a %s (%s)b) ? 1 : 0)) bad++;'
                     % (jcc, st, op, st))
    if bits == 8:
        loop = ('    for (uint32_t a = 0; a < 256; a++) for (uint32_t b = 0; b < 256; b++) {\n'
                '%s\n    }\n' % '\n'.join(calls))
    else:
        loop = ('    static const uint32_t v[] = {0, 1, 2, 5, 15, 0x7F, 0x80, 0xFF, 0x100,\n'
                '        0x7FFF, 0x8000, 0xFFFF, 0x10000, 0x7FFFFFFF, 0x80000000u, 0xFFFFFFFFu};\n'
                '    for (unsigned i = 0; i < 16; i++) for (unsigned j = 0; j < 16; j++) {\n'
                '        uint32_t a = v[i] & (uint32_t)(%s)~0u, b = v[j] & (uint32_t)(%s)~0u;\n'
                '%s\n    }\n' % (ut, ut, '\n'.join(calls)))
    src_text = ('#include <stdio.h>\n#include "recomp_types.h"\n%s'
                'int main(void) {\n    int bad = 0;\n%s'
                '    printf("%%d\\n", bad);\n    return bad != 0;\n}\n' % (''.join(funcs), loop))
    with tempfile.TemporaryDirectory() as d:
        c, exe = os.path.join(d, 't.c'), os.path.join(d, 't')
        with open(c, 'w') as f:
            f.write(src_text)
        build = subprocess.run([cc, '-O2', '-std=gnu11', '-w',
                                '-I', os.path.join(ROOT, 'templates', 'runtime'),
                                '-I', os.path.join(ROOT, 'include'), c, '-o', exe],
                               capture_output=True, text=True)
        assert build.returncode == 0, build.stderr[-2000:]
        run = subprocess.run([exe], capture_output=True, text=True)
    assert run.returncode == 0, 'mismatches: ' + run.stdout
