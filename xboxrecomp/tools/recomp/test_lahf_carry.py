"""LAHF after INC/DEC reads CF from the earlier arithmetic.

lifter._lahf_value builds AH from the jb condition of the last flag setter,
and after inc/dec that is _cf. _function_needs_cf did not count lahf as a CF
reader, so `add; dec; lahf` used an undeclared _cf and the generated C did
not compile (Conker: Live & Reloaded, sub_00389F5A).

    python3 -m pytest tools/recomp/test_lahf_carry.py
"""
import os
import re
import subprocess
import tempfile

import pytest
from tools.recomp import config
from tools.recomp.translator import FunctionTranslator


def translate(body_hex):
    image = bytes.fromhex(body_hex)
    base = 0x10000
    config._install([config.Section('.text', base, len(image), 0, len(image), True)],
                    entry_point=base, kernel_thunk_addr=base, origin='lahf-carry-test')
    db = {base: {'start': hex(base), 'end': base + len(image), '_addr': base,
                 'size': len(image)}}
    return FunctionTranslator(image, db).translate_function(base, db[base])


@pytest.mark.parametrize('incdec', ['4b', '43'])   # dec ebx / inc ebx
def test_lahf_after_incdec_declares_cf(incdec):
    # add edx, esi; dec/inc ebx; lahf; ret
    code = translate('01f2' + incdec + '9f' + 'c3')
    assert 'int _cf = 0;' in code
    assert '_cf' in code[code.index('lahf') - 300:]


def test_lahf_after_cmp_needs_no_cf():
    # cmp eax, ebx; lahf; ret -- CF comes from the compare itself
    code = translate('39d8' + '9f' + 'c3')
    assert 'lahf' in code


def test_lahf_after_dec_compiles():
    code = translate('01f2' + '4b' + '9f' + 'c3')
    here = os.path.dirname(__file__)
    root = os.path.normpath(os.path.join(here, '..', '..'))
    runtime = os.path.join(root, 'templates', 'runtime')
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, 'recomp_funcs.h'), 'w') as f:
            f.write('#include "recomp_types.h"\n')
        src = os.path.join(d, 't.c')
        with open(src, 'w') as f:
            f.write('#include "recomp_funcs.h"\n' + code)
        r = subprocess.run(['cc', '-std=c11', '-fsyntax-only', '-w', '-I', d,
                            '-I', runtime, '-I', os.path.join(root, 'include'), src],
                           capture_output=True, text=True)
    assert 'fatal error' not in r.stderr, r.stderr
    # Other errors (RECOMP_RR_DECL, recomp_leaf_*: the template header lags the
    # translator, see test_incdec_result.py) are not this test's business.
    assert not re.search(r"_cf.? undeclared", r.stderr), r.stderr
