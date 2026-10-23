"""caff_text.py: Conker L&R CAFF text bank (default.bin) -- grow LSBL strings and
fix every size the game checks. Facts from the game code (2026-10-22):
header 0x180 bytes, checksum at +0x14 = ELF/PJW hash (signed bytes) over the
header with +0x14 zeroed (0x004072F0); +0x34 data size; one section entry at
+0x40 (0x28 bytes): +0x10 and +0x24 = section size (data + tail); the tail
(build path + big-endian relocation offsets) follows the data.
LSBL: 'LSBL', +0x10 block size, +0x20 count, then count entries (u16 id, u32
offset in UTF-16 units) and a terminator (0xFFFF, pool length in units), then
the pool of NUL-terminated UTF-16 strings.

  caff_text.py check FILE                      -> verify header checksum
  caff_text.py list FILE                       -> index and start of every string
  caff_text.py set IN OUT IDX TEXT             -> string IDX becomes TEXT (any length), all fixed
  caff_text.py grow IN OUT MODE IDX:N [IDX:N]  -> string IDX grows by N chars
     MODE naive = only the bytes (like a plain in-place rewrite, file grows)
     MODE fixed = also index offsets, terminator, LSBL size, header sizes, checksum
"""
import struct, sys


def caff_hash(hdr):
    h = bytearray(hdr[:0x180])
    h[0x14:0x18] = b'\0\0\0\0'
    v = 0
    for b in h:
        c = b - 256 if b >= 128 else b
        v = ((v << 4) + c) & 0xFFFFFFFF
        g = v & 0xF0000000
        if g:
            v ^= (g >> 24) | g
    return v


def parse(d):
    D = d[0x180:]
    L = D.find(b'LSBL')
    cnt = struct.unpack_from('<I', D, L + 0x20)[0]
    ents = [struct.unpack_from('<HI', D, L + 0x24 + 6 * k) for k in range(cnt + 1)]
    pool = L + 0x24 + 6 * (cnt + 1)
    return L, cnt, ents, pool


def grow(d, mode, grows):
    d = bytearray(d)
    L, cnt, ents, pool = parse(d[:])
    base = 0x180
    # apply from the last string backwards so offsets stay valid while editing
    total = 0
    for idx, n in sorted(grows, reverse=True):
        sid, off = ents[idx]
        p = base + pool + 2 * off
        q = p
        while d[q:q + 2] != b'\0\0':
            q += 2
        add = ('X' * n).encode('utf-16-le')
        d[q:q] = add                      # n chars appended to string idx
        total += 2 * n
        if mode == 'fixed':
            for k in range(cnt + 1):
                i2, o2 = ents[k]
                if o2 > off:
                    ents[k] = (i2, o2 + n)
    if mode == 'fixed':
        for k in range(cnt + 1):
            struct.pack_into('<HI', d, base + L + 0x24 + 6 * k, *ents[k])
        lsz = struct.unpack_from('<I', d, base + L + 0x10)[0]
        struct.pack_into('<I', d, base + L + 0x10, lsz + total)
        for o in (0x34, 0x40 + 0x10, 0x40 + 0x24):
            v = struct.unpack_from('<I', d, o)[0]
            struct.pack_into('<I', d, o, v + total)
        struct.pack_into('<I', d, 0x14, caff_hash(d))
    return bytes(d)


def set_text(d, idx, text):
    """String idx becomes `text` (any length); every size and the checksum fixed."""
    d = bytearray(d)
    L, cnt, ents, pool = parse(d[:])
    base = 0x180
    sid, off = ents[idx]
    p = base + pool + 2 * off
    q = p
    while d[q:q + 2] != b'\0\0':
        q += 2
    old = (q - p) // 2
    new = text.encode('utf-16-le')
    delta = len(new) // 2 - old
    d[p:q] = new
    for k in range(cnt + 1):
        i2, o2 = ents[k]
        if o2 > off:
            ents[k] = (i2, o2 + delta)
        struct.pack_into('<HI', d, base + L + 0x24 + 6 * k, *ents[k])
    lsz = struct.unpack_from('<I', d, base + L + 0x10)[0]
    struct.pack_into('<I', d, base + L + 0x10, lsz + 2 * delta)
    for o in (0x34, 0x40 + 0x10, 0x40 + 0x24):
        v = struct.unpack_from('<I', d, o)[0]
        struct.pack_into('<I', d, o, v + 2 * delta)
    struct.pack_into('<I', d, 0x14, caff_hash(d))
    return bytes(d)


def strings(d):
    L, cnt, ents, pool = parse(d)
    out = []
    for k in range(cnt):
        p = 0x180 + pool + 2 * ents[k][1]
        q = p
        while d[q:q + 2] != b'\0\0':
            q += 2
        out.append(d[p:q].decode('utf-16-le'))
    return out


if __name__ == '__main__':
    if sys.argv[1] == 'list':
        for k, s in enumerate(strings(open(sys.argv[2], 'rb').read())):
            print(k, repr(s[:90]))
    elif sys.argv[1] == 'set':
        _, _, src, dst, idx, text = sys.argv
        open(dst, 'wb').write(set_text(open(src, 'rb').read(), int(idx), text))
        print('string %s set (%d chars)' % (idx, len(text)))
    elif sys.argv[1] == 'check':
        d = open(sys.argv[2], 'rb').read()
        print('stored %08X computed %08X' % (struct.unpack_from('<I', d, 0x14)[0], caff_hash(d)))
        L, cnt, ents, pool = parse(d)
        print('LSBL at .data+%#x, %d strings, pool at .data+%#x, terminator %s' % (L, cnt, pool, ents[-1]))
    else:
        _, _, src, dst, mode, *specs = sys.argv
        g = [(int(a), int(b)) for a, b in (s.split(':') for s in specs)]
        out = grow(open(src, 'rb').read(), mode, g)
        open(dst, 'wb').write(out)
        print('%s: %d -> %d bytes' % (mode, len(open(src, 'rb').read()), len(out)))
