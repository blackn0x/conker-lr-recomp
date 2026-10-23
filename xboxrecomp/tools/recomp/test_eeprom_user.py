"""ExQueryNonVolatileSetting(XC_MAX_OS / XC_MAX_ALL): the EEPROM layout.

Conker: Live & Reloaded reads the user-settings block (index 0xFF) rather
than XC_VIDEO alone. The kernel answered it with zeros, so the title saw no
16:9 flag. xbox_eeprom.h lays the values out as the EEPROM does: language at
0x30, video flags at 0x34, DVD region at 0x5C of the block, the block at 0x60
of the 256-byte EEPROM.

    python3 -m pytest tools/recomp/test_eeprom_user.py
"""
import os
import subprocess
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))
KERNEL = os.path.join(ROOT, 'src', 'kernel')

PROGRAM = r'''
#include <stdio.h>
#include "xbox_eeprom.h"
static unsigned get32(const uint8_t *p)
{ return p[0] | p[1] << 8 | p[2] << 16 | (unsigned)p[3] << 24; }
int main(void)
{
    uint8_t b[0x100];
    unsigned n = xbox_eeprom_query(0xFF, b, sizeof b, 1, 0x00010000u, 0, -300, 1);
    printf("os %u lang %u video %08X dvd %u tz %d rest %u\n", n, get32(b + 0x30),
           get32(b + 0x34), get32(b + 0x5C), (int)get32(b + 4), b[0x60]);
    n = xbox_eeprom_query(0xFFFF, b, sizeof b, 1, 0x00010000u, 0, -300, 1);
    printf("all %u video %08X std %08X\n", n, get32(b + 0x94), get32(b + 0x58));
    n = xbox_eeprom_query(0xFF, b, 0x38, 1, 0, 0, -300, 1);
    printf("short %u video %08X\n", n, get32(b + 0x34));
    return 0;
}
'''


def test_eeprom_user_layout():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, 't.c')
        exe = os.path.join(d, 't')
        with open(src, 'w') as f:
            f.write(PROGRAM)
        subprocess.run(['cc', '-std=c99', '-Wall', '-I', KERNEL, src, '-o', exe], check=True)
        out = subprocess.run([exe], capture_output=True, text=True, check=True).stdout
    assert 'os 96 lang 1 video 00010000 dvd 1 tz -300 rest 0' in out
    assert 'all 256 video 00010000 std 00400100' in out
    assert 'short 96 video 00000000' in out
