"""Opt-in patch for a PRIVATE retail-NTSC generated directory.

No generated game code belongs in git. This does not change general LAHF
semantics: the runtime compatibility exception applies only when explicitly
requested by the Windows test launcher. Use a separate directory.
"""
from pathlib import Path
import re
import sys

TAG = "/* CLX_WINDOWS_INPUT_COMPAT_V1 */"

def patch(directory):
    directory = Path(directory)
    files = {p: p.read_text(encoding="utf-8") for p in directory.glob("recomp_*.c")}
    header = directory / "recomp_funcs.h"
    if not header.exists():
        raise ValueError("No recomp_funcs.h in generated directory")
    native = [(p, s) for p, s in files.items() if re.search(r"^void sub_0055BDF8(?:_gen)?\(void\)", s, re.M)]
    graphics = [(p, s) for p, s in files.items() if re.search(r"^void sub_003F57D0\(void\)", s, re.M)]
    if len(native) != 1 or len(graphics) != 1:
        raise ValueError("Expected the retail NTSC input and graphics functions exactly once")
    np, ns = native[0]
    gp, gs = graphics[0]
    if np == gp:
        raise ValueError("Unexpected generated chunk layout")
    ns = re.sub(r"^void sub_0055BDF8\(void\)", "void sub_0055BDF8_gen(void)", ns, flags=re.M)
    if TAG not in gs:
        match = re.search(r"^void sub_003F57D0\(void\)\n\{.*?^\}", gs, re.M | re.S)
        if not match:
            raise ValueError("Unexpected graphics function layout")
        body = match.group()
        count = 0
        lines = []
        for line in body.splitlines():
            if "SET_HI8(eax," in line and "g_fp_cmp" in line and "/* lahf */" in line:
                count += 1
                line = ("    { " + TAG + " static int enabled = -1; "
                        'if (enabled < 0) { const char *skip = getenv("CLX_GFX_LAHF_SKIP"); '
                        'enabled = !skip || strcmp(skip, "003F57D0") != 0; } '
                        "if (enabled) { " + line.strip() + " } }")
            lines.append(line)
        if count != 1:
            raise ValueError("Expected exactly one corrected x87 LAHF in 003F57D0; regenerate before patching")
        gs = gs[:match.start()] + "\n".join(lines) + gs[match.end():]
        gs = '#include <stdlib.h>\n#include <string.h>\n' + gs
    hs = header.read_text(encoding="utf-8")
    if "void sub_0055BDF8_gen(void);" not in hs:
        hs += "\nvoid sub_0055BDF8_gen(void);\n"
    # Validate everything before writing, so an unexpected translation fails cleanly.
    np.write_text(ns, encoding="utf-8")
    gp.write_text(gs, encoding="utf-8")
    header.write_text(hs, encoding="utf-8")
    (directory / "clx_input_compat.marker").write_text("v1\n", encoding="utf-8")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: windows_input_compat.py <private-generated-directory>")
    try:
        patch(sys.argv[1])
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc))
