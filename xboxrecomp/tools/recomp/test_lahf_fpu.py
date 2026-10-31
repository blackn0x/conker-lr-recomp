"""LAHF after an x87 compare-to-EFLAGS loads AH from g_fp_cmp.

_lahf_value had no js for fcomip/fucomip, gave up, and lahf lifted to a
comment, so `fucomip; fstp st(0); lahf; test ah, 0x44; jp` tested a stale AH.
Conker: Live & Reloaded's yaw (0x002B0CB0) took its zero-length exit on every
direction and the slingshot pellet flew at yaw 0.

    python3 -m pytest tools/recomp/test_lahf_fpu.py
"""
import re

import pytest
from tools.recomp import config
from tools.recomp.lifter import _lahf_value
from tools.recomp.translator import FunctionTranslator


def translate(body_hex):
    image = bytes.fromhex(body_hex)
    base = 0x10000
    config._install([config.Section('.text', base, len(image), 0, len(image), True)],
                    entry_point=base, kernel_thunk_addr=base, origin='lahf-fpu-test')
    db = {base: {'start': hex(base), 'end': base + len(image), '_addr': base,
                 'size': len(image)}}
    return FunctionTranslator(image, db).translate_function(base, db[base])


def test_lahf_after_fucomip_sets_ah():
    # fucomip st, st(1); fstp st(0); lahf; test ah, 0x44; jp +1; nop; ret
    code = translate('dfe9' + 'ddd8' + '9f' + 'f6c444' + '7a01' + '90' + 'c3')
    assert 'SET_HI8(eax,' in code
    lahf = code[code.index('SET_HI8(eax,'):]
    assert 'g_fp_cmp' in lahf[:lahf.index(';')]


def ah(cmp):
    """The AH byte _lahf_value gives for one g_fp_cmp value."""
    expr = _lahf_value('fucomip', ()).replace('(uint8_t)', '').replace('||', ' or ')
    # ((cond) ? 0xNN : 0)  ->  (0xNN if (cond) else 0)
    expr = re.sub(r'\(\(([^?]*)\) \? (0x[0-9A-F]+) : 0\)', r'(\2 if (\1) else 0)', expr)
    return eval(expr.replace('g_fp_cmp', str(cmp)), {})


@pytest.mark.parametrize('cmp, flags', [
    (-1, 0x03),     # below: CF
    (0, 0x42),      # equal: ZF
    (1, 0x02),      # above: none
    (2, 0x47),      # unordered: ZF PF CF
])
def test_lahf_fpu_bits(cmp, flags):
    assert ah(cmp) == flags
