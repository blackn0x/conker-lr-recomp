"""The guest stack region moves above an image that reaches past 0x00780000.

The stack region (main stack, worker stack slices), the heap after it and the
runtime data block below it used fixed addresses that assumed the image ends
below 0x00780000. Conker: Live & Reloaded's .data/.bss ends at 0x00881A64, so
the timer thread's and the OHCI ISR's stacks and the TLS / kernel data block
landed inside the title's globals. xbox_StackBaseFor (xbox_memory_layout.h)
places the stack above such an image, leaving room for the runtime data block.

    python3 -m pytest tools/recomp/test_stack_base.py
"""
import os
import subprocess
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))

PROGRAM = r'''
#include <stdio.h>
#include <stdint.h>
#include "xbox_memory_layout.h"
int main(void)
{
    static const uint32_t ends[] = { 0, 0x002CC200u, 0x0076B93Cu, 0x0077C000u,
                                     0x00881A64u, 0x009B68C0u };
    unsigned i;
    for (i = 0; i < sizeof ends / sizeof ends[0]; i++)
        printf("%08X %08X\n", ends[i], xbox_StackBaseFor(ends[i]));
    printf("RT %08X\n", (unsigned)XBOX_RTDATA_SIZE);
    return 0;
}
'''


def run_program():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, 't.c')
        exe = os.path.join(d, 't')
        with open(src, 'w') as f:
            f.write(PROGRAM)
        subprocess.run(['cc', '-std=c11', '-w', '-I', os.path.join(ROOT, 'src', 'kernel'),
                        '-I', os.path.join(ROOT, 'src'), '-I', os.path.join(ROOT, 'include'),
                        src, '-o', exe],
                       check=True, capture_output=True, text=True)
        out = subprocess.run([exe], check=True, capture_output=True, text=True).stdout
    rows = dict(line.split() for line in out.splitlines())
    return {int(k, 16): int(v, 16) for k, v in rows.items() if k != 'RT'}, int(rows['RT'], 16)


def test_stack_base():
    base, rtdata = run_program()
    # No image yet, Burnout 3, FlatOut 2-sized: the default.
    assert base[0] == 0x00780000
    assert base[0x002CC200] == 0x00780000
    assert base[0x0076B93C] == 0x00780000          # 0x76C000 + 16 KB fits exactly
    # Too close for the runtime data block, Conker, Half-Life 2: above the image.
    for end in (0x0077C000, 0x00881A64, 0x009B68C0):
        b = base[end]
        assert b % 0x10000 == 0
        assert b >= ((end + 0xFFF) & ~0xFFF) + rtdata, hex(b)
        assert b - end < 0x10000 + rtdata, hex(b)
    assert base[0x00881A64] == 0x00890000
