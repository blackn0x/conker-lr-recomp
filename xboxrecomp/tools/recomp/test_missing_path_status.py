"""A missing file whose directory is missing too is OBJECT_PATH_NOT_FOUND.

NT answers OBJECT_NAME_NOT_FOUND (XAPI: ERROR_FILE_NOT_FOUND, 2) when the
directory exists and OBJECT_PATH_NOT_FOUND (ERROR_PATH_NOT_FOUND, 3) when it
does not. The POSIX backend answered NAME_NOT_FOUND for both, and Conker: Live
& Reloaded's "create a directory and its parents" routine creates the parents
only on 3, so it never made Z:\\texture\\frontend\\tips and stopped on its fatal
error screen. The test compiles xbox_missing_path_status out of
src/kernel/kernel_file.c against a real directory tree.

    python3 -m pytest tools/recomp/test_missing_path_status.py
"""
import os
import re
import shutil
import subprocess
import tempfile

import pytest

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))


def _function_source():
    src = open(os.path.join(ROOT, 'src', 'kernel', 'kernel_file.c')).read()
    m = re.search(r'^NTSTATUS xbox_missing_path_status\(const char \*host_path\)\n\{.*?^\}\n',
                  src, re.S | re.M)
    assert m, 'xbox_missing_path_status not found in kernel_file.c'
    return m.group(0)


def test_missing_path_status():
    cc = os.environ.get('CC') or shutil.which('cc') or shutil.which('gcc')
    if not cc or os.name == 'nt':
        pytest.skip('POSIX C compiler needed')
    program = ('#include <stdio.h>\n#include <string.h>\n#include <sys/stat.h>\n'
               'typedef long NTSTATUS;\n#define MAX_PATH 260\n'
               '#define STATUS_OBJECT_NAME_NOT_FOUND ((NTSTATUS)0xC0000034L)\n'
               '#define STATUS_OBJECT_PATH_NOT_FOUND ((NTSTATUS)0xC000003AL)\n'
               + _function_source() +
               'int main(int argc, char **argv) {\n'
               '    for (int i = 1; i < argc; i++)\n'
               '        printf("%s\\n", xbox_missing_path_status(argv[i])'
               ' == STATUS_OBJECT_PATH_NOT_FOUND ? "path" : "name");\n'
               '    return 0;\n}\n')
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, 'Cache', 'texture'))
        c, exe = os.path.join(d, 't.c'), os.path.join(d, 't')
        with open(c, 'w') as f:
            f.write(program)
        subprocess.run([cc, '-std=gnu11', c, '-o', exe], check=True,
                       capture_output=True, text=True)
        args = [os.path.join(d, 'Cache', 'texture'),                   # exists: its dir does
                os.path.join(d, 'Cache', 'texture', 'frontend'),       # dir exists
                os.path.join(d, 'Cache', 'texture', 'frontend', 'tips'),  # dir missing
                os.path.join(d, 'NoCache', 'x')]                        # dir missing
        out = subprocess.run([exe] + args, check=True, capture_output=True,
                             text=True).stdout.split()
    assert out == ['name', 'name', 'path', 'path']
