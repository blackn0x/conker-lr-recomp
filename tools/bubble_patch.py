#!/usr/bin/env python3
"""Point the speech-bubble literals of the lifted Conker code at the runtime getters.

The subtitle box takes three numbers from the code: the wrap width (20
characters), the line limit (4 lines) and the fixed height above the limit
(160.0 from guest 0x00649428). They are literals in the lifted functions, so
this script rewrites them to calls of clx_bubble_wrap(), clx_bubble_line_limit()
and clx_bubble_height() (src/recomp_manual.c). Unset variables give the original
values, so the game is unchanged by default.

    python3 tools/bubble_patch.py <gen dir>

Run after every regen (tools/regen.sh does it). Each function must hold exactly
the expected lines, or the script exits 1 and changes nothing: a regen that moved
the code must be checked by hand. Running it again on a patched gen is a no-op.

Sites (VAs of default.xbe, retail NTSC): wrap 0x000DFDF7 and 0x000DFE24; line
limit 0x000E0B9E, 0x000E0C03, 0x000E129A, 0x000E12FE; height load 0x000E0BDE and
0x000E12D9. The lifter emits the twin layouts twice (sub_000E0CD0 and the
overlapping sub_000E0E00), so each VA appears in two functions.
"""
import os
import re
import sys

SOURCE = "recomp_0012.c"
EXTERN = (
    "/* tools/bubble_patch.py: subtitle box getters (src/recomp_manual.c) */\n"
    "extern int32_t clx_bubble_wrap(void);\n"
    "extern int32_t clx_bubble_line_limit(void);\n"
    "extern float clx_bubble_height(void);\n"
)
WRAP_STORE = re.compile(r"^(\s*)MEM32\(esp \+ 0x14\) = 0x14;$")
WRAP_EAX = re.compile(r"^(\s*)eax = 0x14;$")
HEIGHT = re.compile(r"^(\s*)xmm0 = XMM_SCALAR\(MEMF\(0x649428\)\); /\* movss \*/$")
LINE_LOAD = "_fb = (uint32_t)(4) & 0xFFFFFFFFu;"
LINE_CMP = re.compile(r"/\* cmp (eax|MEM32\(esp \+ 0x18\)), 4 \(32-bit\) \*/")

# function -> (wrap stores, line-limit compares, height loads) expected in its body
EXPECT = {
    "sub_000DFD90": (2, 0, 0),
    "sub_000E0850": (0, 2, 1),
    "sub_000E0CD0": (0, 2, 1),
    "sub_000E0E00": (0, 2, 1),
}
NEW_WRAP = "clx_bubble_wrap()"
NEW_LINES = "clx_bubble_line_limit()"
NEW_HEIGHT = "clx_bubble_height()"


class PatchError(Exception):
    pass


def split_functions(lines):
    """Return (start, end, name) line ranges of each 'void sub_XXXX(void)' definition."""
    starts = []
    for i, line in enumerate(lines):
        m = re.match(r"^void (sub_[0-9A-F]{8})\(void\)$", line)
        if m:
            starts.append((i, m.group(1)))
    out = []
    for k, (i, name) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        out.append((i, end, name))
    return out


def patch_body(lines, start, end, name):
    """Rewrite one function body in place; return (changed, already) counts."""
    want_wrap, want_lines, want_height = EXPECT[name]
    body = range(start, end)
    wrap_hits, line_hits, height_hits = [], [], []
    for i in body:
        if WRAP_STORE.match(lines[i]) or WRAP_EAX.match(lines[i]):
            wrap_hits.append(i)
        if HEIGHT.match(lines[i]):
            height_hits.append(i)
        if LINE_LOAD in lines[i] and i + 1 < end and LINE_CMP.search(lines[i + 1]):
            line_hits.append(i)
    done_wrap = sum(NEW_WRAP in lines[i] for i in body)
    done_lines = sum(NEW_LINES in lines[i] for i in body)
    done_height = sum(NEW_HEIGHT in lines[i] for i in body)
    if done_wrap + done_lines + done_height:
        if (done_wrap, done_lines, done_height) != (want_wrap, want_lines, want_height):
            raise PatchError("%s: partly patched (%d/%d/%d)" % (name, done_wrap, done_lines, done_height))
        return 0, want_wrap + want_lines + want_height
    if (len(wrap_hits), len(line_hits), len(height_hits)) != (want_wrap, want_lines, want_height):
        raise PatchError("%s: found wrap %d, line %d, height %d; expected %d, %d, %d (regen changed the code?)"
                         % (name, len(wrap_hits), len(line_hits), len(height_hits),
                            want_wrap, want_lines, want_height))
    for i in wrap_hits:
        lines[i] = lines[i].replace("0x14;", NEW_WRAP + ";")
    for i in line_hits:
        lines[i] = lines[i].replace(LINE_LOAD, "_fb = (uint32_t)(clx_bubble_line_limit()) & 0xFFFFFFFFu;")
    for i in height_hits:
        lines[i] = lines[i].replace("XMM_SCALAR(MEMF(0x649428))", "XMM_SCALAR(" + NEW_HEIGHT + ")")
    return want_wrap + want_lines + want_height, 0


def patch_file(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        text = f.read()
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(newline)
    changed = already = 0
    for start, end, name in split_functions(lines):
        if name not in EXPECT:
            continue
        c, a = patch_body(lines, start, end, name)
        changed += c
        already += a
    missing = [n for n in EXPECT if n not in {s[2] for s in split_functions(lines)}]
    if missing:
        raise PatchError("functions not found in %s: %s" % (path, ", ".join(missing)))
    if changed:
        if not any(l.startswith("extern int32_t clx_bubble_wrap(void);") for l in lines):
            # after the first #include, so int32_t is already declared
            idx = next(i for i, l in enumerate(lines) if l.startswith("#include ")) + 1
            lines[idx:idx] = EXTERN.rstrip("\n").split("\n")
        tmp = path + ".bubble.tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(newline.join(lines))
        os.replace(tmp, path)
    return changed, already


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip().split("\n")[0], file=sys.stderr)
        print("usage: bubble_patch.py <gen dir>", file=sys.stderr)
        return 2
    path = os.path.join(argv[1], SOURCE)
    if not os.path.isfile(path):
        print("bubble_patch: no %s in %s" % (SOURCE, argv[1]), file=sys.stderr)
        return 1
    try:
        changed, already = patch_file(path)
    except PatchError as e:
        print("bubble_patch: %s" % e, file=sys.stderr)
        return 1
    if changed:
        print("bubble_patch: %d sites rewritten in %s" % (changed, path))
    else:
        print("bubble_patch: %d sites already rewritten in %s" % (already, path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
