"""RECOMP_FILE_ALIAS swaps one Xbox path for another (kernel_path.c, POSIX).

Conker: Live & Reloaded's boot movie dvddata\\fmv\\frontend\\BootIntro.xmv
(the Microsoft Game Studios logo and a multiplayer montage) can't simply be
deleted: a missing movie leaves the title on its fatal screen. The Switch
build swaps it for the disc's blank black.xmv instead (CLX_SKIP_INTRO).

    python3 -m pytest tools/recomp/test_file_alias.py
"""
import os
import subprocess
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))
KERNEL = os.path.join(ROOT, 'src', 'kernel')

PROGRAM = r'''
#include <stdio.h>
#include <stdlib.h>
#include "kernel.h"
const char *xbox_LookupSymbolicLink(const char *link) { (void)link; return NULL; }
void xbox_log(int level, const char *subsystem, const char *fmt, ...)
{ (void)level; (void)subsystem; (void)fmt; }
static void show(const char *tag, const char *p)
{
    char out[512];
    if (xbox_translate_path(p, out, sizeof out)) printf("%s %s\n", tag, out);
    else printf("%s FAIL\n", tag);
}
int main(int argc, char **argv)
{
    xbox_path_init(argv[1], argv[2]);
    show("none", "\\Device\\CdRom0\\dvddata\\fmv\\frontend\\BootIntro.xmv");
    setenv("RECOMP_FILE_ALIAS",
           "nothing\\here.bin=x.bin;dvddata\\fmv\\frontend\\BootIntro.xmv=dvddata\\fmv\\black.xmv", 1);
    show("hit", "\\Device\\CdRom0\\dvddata\\fmv\\frontend\\BootIntro.xmv");
    show("case", "\\Device\\CdRom0\\DVDDATA\\FMV\\FRONTEND\\bootintro.XMV");
    show("other", "\\Device\\CdRom0\\dvddata\\fmv\\frontend\\Attract.xmv");
    setenv("RECOMP_FILE_ALIAS", "a.xmv=a.xmv", 1);           /* no loop */
    show("self", "\\Device\\CdRom0\\a.xmv");
    return 0;
}
'''


def run_program(tmp):
    src = os.path.join(tmp, 't.c')
    exe = os.path.join(tmp, 't')
    with open(src, 'w') as f:
        f.write(PROGRAM)
    subprocess.run(['cc', '-std=gnu11', '-w', '-I', KERNEL, '-I', os.path.join(ROOT, 'src'),
                    '-I', os.path.join(ROOT, 'include'), src,
                    os.path.join(KERNEL, 'kernel_path.c'), '-o', exe],
                   check=True, capture_output=True, text=True)
    game, save = os.path.join(tmp, 'game'), os.path.join(tmp, 'save')
    os.makedirs(game)
    out = subprocess.run([exe, game, save], check=True, capture_output=True,
                         text=True).stdout
    return game, dict(line.split(' ', 1) for line in out.splitlines())


def test_file_alias():
    with tempfile.TemporaryDirectory() as tmp:
        game, r = run_program(tmp)
        assert r['none'] == game + '/dvddata/fmv/frontend/BootIntro.xmv'
        assert r['hit'] == game + '/dvddata/fmv/black.xmv'
        assert r['case'].lower() == (game + '/dvddata/fmv/black.xmv').lower()
        assert r['other'] == game + '/dvddata/fmv/frontend/Attract.xmv'
        assert r['self'] == game + '/a.xmv'
