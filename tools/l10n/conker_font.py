#!/usr/bin/env python3
"""Conker: Live & Reloaded (Xbox) fonts: dvddata/aid/font/<Name>/default.bin.

  conker_font.py export FONT.bin OUTDIR            -> OUTDIR/atlas.png + OUTDIR/font.json
  conker_font.py import FONT.bin OUTDIR NEW.bin    -> NEW.bin from the edited atlas.png + font.json
  conker_font.py selftest FONT_DIR                 -> export + import of every font gives the same bytes

Format (found in the game code, default.xbe retail NTSC):
- CAFF file (see ../caff_text.py), 2 sections: .data (font tables) and .gpu
  (the atlas pixels, D3D format 0x13 = LIN_L8: one byte per pixel, linear).
- .data+0x20 -> descriptor (0x348 in every font; read by 0x003D49A0): -0x04 -> char
  hash table, +0x0C glyph count, +0x10 fallback char, +0x1C max hash probes.
  .data+0x24 -> font object (0x368): +0 -> metrics {line height, space width},
  +8 -> glyph records, 18 bytes each (text measure 0x003D5130 reads +0x0C):
    +0 s8 x offset, +1 s8 y offset (from the top of the line), +2 u8 w, +3 u8 h,
    +4 u16 u0, +6 u1, +8 v0, +0xA v1 (texel centres, 1/16384 of the atlas size),
    +0xC s16 advance, +0xE s16 kerning (-1 in all fonts), +0x10 s16 baseline - y.
  Hash table: 2048 slots of (u16 char, u16 glyph) + 12 bytes; empty = 0xFFFF.
  Lookup 0x003D4A50: slot = (c + k * step) mod 2048 for k = 1..max probes,
  step = ((c >> 5) + 1) mod 0x7FF + 1.
- The bubble text draws a..z as small capitals: the A..Z glyph at 0.81 (0x000E2352).

Limits: the glyph count and the atlas size stay as in the original file (their
growth moves relocated tables; not done). Re-use glyph slots for new letters:
change "chars" of a glyph and redraw its rectangle in atlas.png.
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from caff_text import caff_hash  # noqa: E402

SLOTS = 2048
DESC, FOBJ = 0x348, 0x368


def _data(d):
    return 0x180, struct.unpack_from('<I', d, 0x34)[0]


def parse(d):
    base, ds = _data(d)
    D = d[base:base + ds]
    assert d[:4] == b'CAFF' and D[:4] == b'font', 'not a Conker font'
    desc = struct.unpack_from('<I', D, 0x20)[0]
    fobj = struct.unpack_from('<I', D, 0x24)[0]
    htab = struct.unpack_from('<I', D, desc - 4)[0]
    n, fallback = struct.unpack_from('<II', D, desc + 0x0C)
    probes = struct.unpack_from('<I', D, desc + 0x1C)[0]
    mptr, _, gptr = struct.unpack_from('<III', D, fobj)
    line_h, space_w = struct.unpack_from('<ii', D, mptr)
    tw, th = struct.unpack_from('<HH', D, mptr + 8)
    glyphs = []
    for i in range(n):
        xo, yo, w, h, u0, u1, v0, v1, adv, kern, asc = struct.unpack_from('<bbBB4H3h', D, gptr + 18 * i)
        x, y = round(u0 * tw / 16384 - 0.5), round(v0 * th / 16384 - 0.5)
        glyphs.append(dict(index=i, chars=[], x=x, y=y, w=w, h=h, xoff=xo, yoff=yo, advance=adv,
                           kern=kern, ascent=asc, uv=[u0, u1, v0, v1], uv_rect=[x, y, w, h]))
    for s in range(SLOTS):
        c, g = struct.unpack_from('<HH', D, htab + 4 * s)
        if c != 0xFFFF and g < n:
            glyphs[g]['chars'].append(c)
    gpu = d[base + struct.unpack_from('<I', d, 0x50)[0]:]
    assert len(gpu) >= tw * th, 'atlas smaller than %dx%d' % (tw, th)
    return dict(line_height=line_h, space_width=space_w, fallback=fallback, probes=probes,
                atlas=[tw, th], glyphs=glyphs, offsets=dict(htab=htab, gptr=gptr, desc=desc),
                pixels=gpu[:tw * th], gpu_off=base + struct.unpack_from('<I', d, 0x50)[0])


def metrics(path):
    """Advance per char code for text layout: {code: advance}, line height, space width."""
    f = parse(open(path, 'rb').read())
    adv = {}
    for g in f['glyphs']:
        for c in g['chars']:
            adv[c] = g['advance']
    return dict(advance=adv, line_height=f['line_height'], space=f['space_width'])


def _uv(g, tw, th):
    # the original uv stay while x, y, w, h are the values they were exported with
    if g.get('uv_rect') == [g['x'], g['y'], g['w'], g['h']]:
        return g['uv']
    return (round((g['x'] + 0.5) * 16384 / tw), round((g['x'] + g['w'] - 0.5) * 16384 / tw),
            round((g['y'] + 0.5) * 16384 / th), round((g['y'] + g['h'] - 0.5) * 16384 / th))


def _slots(c):
    step = ((c >> 5) + 1) % 0x7FF + 1
    k = 1
    while True:
        yield k, (c + k * step) % SLOTS
        k += 1


def build(orig, meta, pixels):
    d = bytearray(orig)
    f = parse(orig)
    base = 0x180
    tw, th = f['atlas']
    if meta['atlas'] != f['atlas'] or len(pixels) != tw * th:
        raise ValueError('atlas size must stay %dx%d' % (tw, th))
    if len(meta['glyphs']) != len(f['glyphs']):
        raise ValueError('glyph count must stay %d (re-use slots)' % len(f['glyphs']))
    struct.pack_into('<ii', d, base + struct.unpack_from('<I', d, base + FOBJ)[0],
                     meta['line_height'], meta['space_width'])
    g0 = base + f['offsets']['gptr']
    for i, g in enumerate(meta['glyphs']):
        struct.pack_into('<bbBB4H3h', d, g0 + 18 * i, g['xoff'], g['yoff'], g['w'], g['h'],
                         *_uv(g, tw, th), g['advance'], g['kern'], g['ascent'])
    # hash table: keep slots of chars that did not change, insert the rest
    h0 = base + f['offsets']['htab']
    want = {}
    for i, g in enumerate(meta['glyphs']):
        for c in g['chars']:
            if c in want:
                raise ValueError('char U+%04X is in glyphs %d and %d' % (c, want[c], i))
            want[c] = i
    slot = {}
    for s in range(SLOTS):
        c, gi = struct.unpack_from('<HH', d, h0 + 4 * s)
        if c != 0xFFFF and want.get(c) == gi:
            slot[s] = (c, gi)
    have = {c for c, _ in slot.values()}
    probes = f['probes']
    for c, gi in sorted(want.items()):
        if c in have:
            continue
        for k, s in _slots(c):
            if s not in slot:
                slot[s] = (c, gi)
                probes = max(probes, k)
                break
    for s in range(SLOTS):
        struct.pack_into('<HH', d, h0 + 4 * s, *slot.get(s, (0xFFFF, 0xFFFF)))
    desc = base + f['offsets']['desc']
    struct.pack_into('<I', d, desc + 0x10, meta['fallback'])
    struct.pack_into('<I', d, desc + 0x1C, probes)
    d[f['gpu_off']:f['gpu_off'] + tw * th] = pixels
    struct.pack_into('<I', d, 0x14, caff_hash(d))
    return bytes(d)


def export(path, outdir):
    from PIL import Image
    f = parse(open(path, 'rb').read())
    os.makedirs(outdir, exist_ok=True)
    tw, th = f['atlas']
    Image.frombytes('L', (tw, th), f['pixels']).save(os.path.join(outdir, 'atlas.png'))
    meta = {k: f[k] for k in ('line_height', 'space_width', 'fallback', 'atlas')}
    meta['note'] = ('atlas.png is the alpha of the glyphs (white = ink). Pixel rectangle x, y, w, h; '
                    'the pen moves by advance; xoff/yoff place the rectangle from the pen and the line top. '
                    'Keep the glyph count and the atlas size.')
    for g in f['glyphs']:
        g['text'] = ''.join(chr(c) for c in g['chars'])
    meta['glyphs'] = f['glyphs']
    with open(os.path.join(outdir, 'font.json'), 'w', encoding='utf-8') as o:
        json.dump(meta, o, ensure_ascii=False, indent=1)
    return len(f['glyphs'])


def import_(path, outdir, out):
    from PIL import Image
    meta = json.load(open(os.path.join(outdir, 'font.json'), encoding='utf-8'))
    for g in meta['glyphs']:  # "text" wins over "chars" when a translator edited it
        if 'text' in g and ''.join(chr(c) for c in g['chars']) != g['text']:
            g['chars'] = [ord(ch) for ch in g['text']]
    img = Image.open(os.path.join(outdir, 'atlas.png')).convert('L')
    new = build(open(path, 'rb').read(), meta, img.tobytes())
    with open(out, 'wb') as o:
        o.write(new)


def selftest(font_dir):
    import tempfile
    ok = True
    for name in sorted(os.listdir(font_dir)):
        p = os.path.join(font_dir, name, 'default.bin')
        if not os.path.exists(p):
            continue
        with tempfile.TemporaryDirectory() as t:
            n = export(p, t)
            import_(p, t, os.path.join(t, 'new.bin'))
            same = open(p, 'rb').read() == open(os.path.join(t, 'new.bin'), 'rb').read()
            # an edit: give glyph 0 an extra char and check that lookup finds it
            meta = json.load(open(os.path.join(t, 'font.json'), encoding='utf-8'))
            meta['glyphs'][0]['chars'].append(0x0416)  # Cyrillic Zhe
            from PIL import Image
            px = Image.open(os.path.join(t, 'atlas.png')).tobytes()
            f2 = parse(build(open(p, 'rb').read(), meta, px))
            found = 0x0416 in f2['glyphs'][0]['chars']
        print('%-22s %3d glyphs  round trip %s  added char %s' % (name, n, 'OK' if same else 'DIFF',
                                                                   'OK' if found else 'LOST'))
        ok &= same and found
    return ok


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[:1] == ['export']:
        print('%d glyphs' % export(a[1], a[2]))
    elif a[:1] == ['import']:
        import_(a[1], a[2], a[3])
        print('written', a[3])
    elif a[:1] == ['selftest']:
        sys.exit(0 if selftest(a[1]) else 1)
    else:
        print(__doc__)
