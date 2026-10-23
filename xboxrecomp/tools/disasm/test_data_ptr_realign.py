"""A data pointer to code the sweep stepped over still becomes an entry.

linear_sweep loses phase in data inside .text: `05 cc cc cc` (the tail of a
byte jump table, then padding) decodes as `add eax, imm32` and swallows the
first byte of the function after it. _pass_data_ptr_targets required the
target to be an instruction boundary the sweep recorded, so a function reached
only through a vtable in .rdata was never lifted (Conker: Live & Reloaded
0x0002D710, in 33 vtables: an unresolved indirect call, then a crash). It is
now taken when it follows a ret or int3 padding and decodes as a returning
body; an address in the middle of real code still is not.

    python3 -m pytest tools/disasm/test_data_ptr_realign.py
"""
import struct

from tools.disasm.test_decode_at import _Section, _Image, BASE
from tools.disasm.engine import DisasmEngine
from tools.disasm.functions import FunctionDetector

DATA_VA = 0x00100000


def _detector(code, target_off):
    text = _Section(BASE, code)
    text.data = code
    table = struct.pack('<I', BASE + target_off)
    rdata = _Section(DATA_VA, table, executable=False)
    rdata.data = table
    rdata.name = '.rdata'
    img = _Image(text, rdata)
    img.sections = [text, rdata]
    img.read_bytes_at_va = lambda addr, size: code[addr - BASE:addr - BASE + size]
    engine = DisasmEngine(img)
    engine.linear_sweep(text)
    det = FunctionDetector(engine, img, None, None)
    return det, text, BASE + target_off


# f0: mov eax, 1; ret  |  `05` + cc cc cc (table tail + padding)  |  f1 at +0x10
CODE = (bytes.fromhex('b801000000c3')          # 0x00..0x05
        + bytes.fromhex('080808070808')        # 0x06..0x0b byte table
        + bytes.fromhex('05cccccc')            # 0x0c..0x0f: add eax, imm32 eats 0x10
        + bytes.fromhex('83ec14b802000000') + bytes.fromhex('83c414c3'))  # 0x10


def test_sweep_steps_over_the_entry():
    det, _, target = _detector(CODE, 0x10)
    assert target not in det.engine.instructions
    assert det.engine.instruction_covering(target) is not None


def test_pointer_after_padding_becomes_an_entry():
    det, text, target = _detector(CODE, 0x10)
    det._pass_data_ptr_targets([text])
    assert target in det._alias_entries or target in det.functions


def test_pointer_into_the_middle_of_code_does_not():
    # f1 + 3 (`mov eax, 2`) follows `sub esp, 0x14`, not a ret or padding.
    det, text, target = _detector(CODE, 0x13)
    det.engine.instructions.pop(target, None)
    det._pass_data_ptr_targets([text])
    assert target not in det._alias_entries


def test_pointer_after_a_jump_table_becomes_an_entry():
    # f0: mov eax, 1; ret; then a 2-entry jump table into f0; f1 right after.
    table = struct.pack('<II', BASE + 0, BASE + 5)
    code = (bytes.fromhex('b801000000c3') + b'\x00\x00' + table
            + bytes.fromhex('83ec14b802000000') + bytes.fromhex('83c414c3'))
    det, text, target = _detector(code, 0x10)
    det.engine.instructions.pop(target, None)
    det._pass_data_ptr_targets([text])
    assert target in det._alias_entries or target in det.functions


# f0: mov eax, [esp+4]; jmp f0  |  f1 right after: 100 x `mov eax, 1`, ret.
LONG = bytes.fromhex('b801000000') * 100 + bytes.fromhex('c3')


def test_long_body_after_a_jmp_becomes_an_entry():
    # Conker 0x0014FE60 / 0x000CF610: a vtable method right after a jmp,
    # more than 64 instructions before its first ret or jump.
    code = bytes.fromhex('8b442404') + bytes.fromhex('e9f7ffffff') + LONG
    det, text, target = _detector(code, 9)
    assert target in det.engine.instructions
    det._pass_data_ptr_targets([text])
    assert target in det._alias_entries or target in det.functions


def test_long_body_after_plain_code_is_still_refused():
    # Same body after a `mov`: something may fall into it, so the 64
    # instruction guard still applies.
    code = bytes.fromhex('8b442404') + bytes.fromhex('b801000000') + LONG
    det, text, target = _detector(code, 9)
    assert target in det.engine.instructions
    det._pass_data_ptr_targets([text])
    assert target not in det._alias_entries
