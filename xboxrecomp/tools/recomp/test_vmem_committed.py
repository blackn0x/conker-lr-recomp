"""Kernel exports accept a buffer in a title's committed extended-VMA pages.

Conker: Live & Reloaded reserves and commits its own memory at 0x74000000
(above RAM and the mirror range) and reads its font file into it. The
buffer check in kernel_bridge.c (bridge_va_mapped) knew only RAM and the
contiguous window, so NtReadFile answered STATUS_ACCESS_VIOLATION and the
title stopped on its fatal-error screen. guest_vmem_committed tells the
check which extended-VMA pages are live.

    python3 -m pytest tools/recomp/test_vmem_committed.py
"""
import os
import subprocess
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))
KERNEL = os.path.join(ROOT, 'src', 'kernel')

PROGRAM = r'''
#include <stdio.h>
#include <stdint.h>
#include <stddef.h>
#include "guest_vmem.h"
size_t g_xbox_total_ram = 64u << 20;
ptrdiff_t g_xbox_mem_offset = 0;
int g_xbox_extvma_reserved = 1;
void *VirtualAlloc(void *a, size_t n, unsigned long t, unsigned long p)
{ (void)n; (void)t; (void)p; return a ? a : (void *)1; }
unsigned long GetLastError(void) { return 0; }
int main(void)
{
    uint32_t base = 0x74000000u, size = 0x30000u, st = 1;
    printf("before %d\n", guest_vmem_committed(0x7400C860u, 4096));
    guest_vmem_allocate(&base, &size, 0x2000u, 4, &st);          /* reserve */
    printf("reserved %d\n", guest_vmem_committed(0x7400C860u, 4096));
    base = 0x7400C000u; size = 0x22000u;                          /* commit */
    guest_vmem_allocate(&base, &size, 0x1000u, 4, &st);
    printf("status %u\n", st);
    printf("inside %d\n", guest_vmem_committed(0x7402C8CCu, 4096));
    printf("edge %d\n", guest_vmem_committed(0x7402DFFFu, 1));
    printf("past %d\n", guest_vmem_committed(0x7402DFFFu, 2));
    printf("ram %d\n", guest_vmem_committed(0x00100000u, 16));
    printf("zero %d\n", guest_vmem_committed(0x7400C000u, 0));
    return 0;
}
'''


def run_program():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, 't.c')
        exe = os.path.join(d, 't')
        with open(src, 'w') as f:
            f.write(PROGRAM)
        subprocess.run(['cc', '-std=gnu11', '-w', '-I', KERNEL,
                        '-I', os.path.join(ROOT, 'src'), '-I', os.path.join(ROOT, 'include'),
                        src, os.path.join(KERNEL, 'guest_vmem.c'), '-o', exe],
                       check=True, capture_output=True, text=True)
        out = subprocess.run([exe], check=True, capture_output=True, text=True).stdout
    return {k: int(v) for k, v in (line.split() for line in out.splitlines())}


def test_vmem_committed():
    r = run_program()
    assert r['before'] == 0
    assert r['reserved'] == 0          # reserved is not yet usable memory
    assert r['status'] == 0
    assert r['inside'] == 1            # 0x7402C8CC..0x7402D8CB is committed
    assert r['edge'] == 1              # last committed byte
    assert r['past'] == 0              # one byte into the uncommitted page
    assert r['ram'] == 0               # RAM is not this tracker's to answer
    assert r['zero'] == 0
