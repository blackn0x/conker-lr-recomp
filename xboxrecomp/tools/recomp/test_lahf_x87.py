"""Execute lifted x87 compare/LAHF branches against the host x86 CPU.

Conker's vector yaw checks a positive length with FUCOMIP; FSTP ST(0);
LAHF; TEST AH,44h; JP. Dropping LAHF makes it depend on the incoming EAX.
No game binary or generated game code is needed for these regressions.
"""
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess

import pytest

from tools.recomp import config
from tools.recomp.lifter import _lahf_value
from tools.recomp.translator import FunctionTranslator


@pytest.mark.parametrize("setter", ["fcomi", "fcomip", "fcompi", "fucomi", "fucomip", "fucompi"])
def test_x87_compare_has_lahf_value(setter):
    assert _lahf_value(setter, []) is not None


@pytest.mark.parametrize("opcode,mnemonic", [
    ("dbe9", "fucomi"), ("dfe9", "fucomip"),
    ("dbf1", "fcomi"), ("dff1", "fcomip"),
])
def test_lifted_lahf_matches_cpu(tmp_path, opcode, mnemonic):
    if platform.machine().lower() not in ("amd64", "x86_64"):
        pytest.skip("x86-64 reference CPU required")
    compiler = shlex.split(os.environ.get("CC", "cc"))
    if not shutil.which(compiler[0]):
        pytest.skip("C compiler required (set CC)")
    # compare st(0),st(1); fstp st(0); lahf; test ah,44h;
    # jp nonzero; mov ebx,0; jmp done; nonzero: mov ebx,1; done: ret
    image = bytes.fromhex(opcode + "ddd89ff6c4447a07bb00000000eb05bb01000000c3")
    base = 0x10000
    config._install([config.Section(".text", base, len(image), 0, len(image), True)],
                    entry_point=base, kernel_thunk_addr=base, origin="x87-lahf-test")
    db = {base: {"start": hex(base), "end": base + len(image),
                 "_addr": base, "size": len(image)}}
    code = FunctionTranslator(image, db).translate_function(base, db[base])
    assert "SET_HI8(eax," in code, code
    assert "lahf - load AH" not in code, code
    # This includes ordered <, =, > and unordered; stale AH must never affect
    # either the resulting flags byte or the parity branch.
    harness = r'''
#define RECOMP_GENERATED_CODE
#include "recomp_types.h"
#include <stdio.h>
RECOMP_TLS RecompRegs _rr[1];
volatile int g_gil_contended;
void recomp_preempt(void) {}
static unsigned hardware_flags(double left, double right) {
    unsigned out;
    __asm__ volatile("fninit; fldl %[right]; fldl %[left]; INSTRUCTION %%st(1), %%st; lahf; fninit"
                     : "=a"(out) : [left] "m"(left), [right] "m"(right)
                     : "cc", "st", "st(1)");
    return (out >> 8) & 255;
}
'''.replace("INSTRUCTION", mnemonic)
    harness += code
    harness += r'''
int main(void) {
    const double values[] = {-1.0, 0.0, 1.0, NAN};
    const unsigned stale[] = {0, 0x0100, 0x4000, 0x4500, 0xff00};
    for (unsigned i = 0; i < 4; ++i) {
        unsigned expected = hardware_flags(values[i], 0.0);
        for (unsigned j = 0; j < 5; ++j) {
            memset(_rr, 0, sizeof(*_rr));
            _rr->r_eax = 0x12340056 | stale[j];
            _rr->r_fp_stack[0] = values[i];
            _rr->r_fp_stack[1] = 0.0;
            sub_00010000();
            unsigned got = (_rr->r_eax >> 8) & 255;
            unsigned branch = (i == 0 || i == 2 || i == 3);
            if (got != expected || _rr->r_ebx != branch ||
                (_rr->r_eax & 0xffff00ff) != 0x12340056) {
                fprintf(stderr, "case %u stale %x: AH=%x expected=%x branch=%u expected=%u\n",
                        i, stale[j], got, expected, _rr->r_ebx, branch);
                return 1;
            }
        }
    }
    return 0;
}
'''
    root = Path(__file__).resolve().parents[2]
    source = tmp_path / "lahf.c"
    exe = tmp_path / ("lahf.exe" if os.name == "nt" else "lahf")
    source.write_text(harness, encoding="utf-8")
    result = subprocess.run(compiler + ["-std=c11", "-O2", "-I", str(root / "templates/runtime"),
                                      "-I", str(root / "include"), str(source), "-o", str(exe)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    result = subprocess.run([str(exe)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
