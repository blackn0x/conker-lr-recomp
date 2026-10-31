"""Private A/B diagnostic generated-code patch; do not publish generated C."""
from pathlib import Path
import re
import sys
root = Path(sys.argv[1]).resolve()
baseline = root
sites = []
for source in baseline.glob('recomp_*.c'):
    text = source.read_text(encoding='utf-8')
    fn = ''
    lines = []
    for line in text.splitlines():
        if line.startswith('void '):
            fn = line.split('(')[0].split()[-1]
        if 'SET_HI8(eax,' in line and 'g_fp_cmp' in line:
            address = fn.removeprefix('sub_')
            sites.append(address)
            # Keep the confirmed slingshot yaw correction in every variant.
            if address != '002B0CB0' and 'CLX_GFX_LAHF_SKIP' not in line:
                line = ('    { static int enabled = -1; if (enabled < 0) {'
                        ' const char *skip = getenv("CLX_GFX_LAHF_SKIP");'
                        f' enabled = !(skip && (strstr(skip, "all") || strstr(skip, "{address}")));'
                        f' fprintf(stderr, "[gfx-lahf] {address} enabled=%d\\n", enabled); }}'
                        ' if (enabled) { ' + line.strip() + ' } }')
        lines.append(line)
    output = '\n'.join(lines) + '\n'
    if output != text:
        output = output.replace('#include <math.h>', '#include <math.h>\n#include <stdlib.h>\n#include <stdio.h>')
    (root / source.name).write_text(output, encoding='utf-8')
print('Instrumented', len(sites), 'sites in', len(set(sites)), 'functions; slingshot stays enabled')

# Keep the opt-in native input bridge reproducible after re-instrumenting.
p = root / "recomp_0084.c"
s = p.read_text(encoding="utf-8")
s = s.replace("void sub_0055BDF8(void)\n{", "void sub_0055BDF8_gen(void)\n{")
p.write_text(s, encoding="utf-8")
p = root / "recomp_funcs.h"
s = p.read_text(encoding="utf-8")
if "void sub_0055BDF8_gen(void);" not in s:
    p.write_text(s + "\nvoid sub_0055BDF8_gen(void);\n", encoding="utf-8")

# Bounded callback diagnostic present in the exact tested executable.
p = root / "recomp_0054.c"
s = p.read_text(encoding="utf-8")
if "[gfx-callback]" not in s:
    start=s.index("void sub_003F57D0(void)")
    end=s.index("\nvoid sub_",start+10)
    needle="    g_fp_cmp = RECOMP_FCMP(fp_top(), fp_st1()); fp_pop(); /* fucompi */"
    diagnostic='    { static unsigned trace; if (trace++ < 100) fprintf(stderr, "[gfx-callback] cand=%08X args=%08X,%08X ret=%.9g top=%d ah=%02X\\n", MEM32(ebp-8), MEM32(ebp+8), MEM32(ebp+12), fp_st1(), g_fp_top, HI8(eax)); }\n'
    part=s[start:end]
    if part.count(needle)!=1: raise SystemExit("Unexpected callback translation")
    p.write_text(s[:start]+part.replace(needle,diagnostic+needle)+s[end:],encoding="utf-8")
