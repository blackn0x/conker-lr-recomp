#!/usr/bin/env python3
"""Conker: Live & Reloaded (Xbox) text banks <-> JSON for translators.

  conker_text.py export TEXT_DIR LANG OUT.json [bubble options]
  conker_text.py import TEXT_DIR IN.json OUT_DIR [--lang LANG]
  conker_text.py check IN.json [--font FONT.bin] [bubble options]
  conker_text.py selftest TEXT_DIR

TEXT_DIR is the disc's dvddata/aid/text (folders English, French, ...; one
<Bank>/default.bin each). export writes every string of one language; import
writes only the banks whose text changed, to OUT_DIR/<LANG>/<Bank>/default.bin
(LANG = the JSON's language unless --lang names another slot). check
recomputes "layout" after edits and prints the lines that do not fit.

Bubble options (the port's subtitle box options): --wrap N (20), --lines N (4),
--height N (160), or --bubble wide (= 40, 6, 240).

Bank format (the game reads it at 0x001F5BE2; header check 0x004072F0):
CAFF header 0x180 bytes (checksum +0x14, data size +0x34, section size +0x50
and +0x64), then .data:
  +0x00 "text", +0x14 a size that moves with the text, +0x20 -> LSBL,
  +0x24 -> key table, +0x28 key count; key table entries (u32 -> UTF-16 key
  name, u16 key hash, u16 string id); lookup 0x003F9CB0 (hash, then name, then
  a binary search of the id).
  LSBL: +0x04 0x1C, +0x08 4 blocks, +0x0C/+0x10/+0x14/+0x18 block offsets from
  LSBL (0 = none), +0x1C block 0 size, +0x20 string count, then (u16 id, u32
  offset in UTF-16 units) per string, a terminator (0xFFFF, pool length), the
  pool of NUL-terminated UTF-16 strings and one more 0x0000. Blocks 1-3 follow
  (each starts with its own size): 1 = ASCII key names (read by the game),
  2 = build comments "; Mpeg = N: file.wav" per cutscene, 3 = id list.
  The data ends 4-byte aligned with zeros; the tail (build path, relocations,
  all before LSBL) follows unchanged.
Growing a string moves blocks 1-3: every offset above is fixed here.
"""
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
from caff_text import caff_hash  # noqa: E402

# tag expander 0x001F3110: names at 0x006B9D98, one code word each at 0x006B9E28
TAGS = {'NORMAL': 0xFFA1, 'RED': 0xFFA2, 'GREEN': 0xFFA3, 'BLUE': 0xFFA4, 'YELLOW': 0xFFA5,
        'A': 0xFFA8, 'B': 0xFFA9, 'X': 0xFFBC, 'Y': 0xFFBD, 'JOYSTICK': 0xFFBE, 'Z': 0xFFAE,
        'L': 0xFFAF, 'R': 0xFFB0, 'ARROW_LEFT': 0xFFAA, 'ARROW_RIGHT': 0xFFAB, 'ARROW_UP': 0xFFAC,
        'ARROW_DOWN': 0xFFAD, 'SKULL': 0xFFB2, 'SWIRL': 0xFFB3, 'STAR': 0xFFB4, 'LIGHTNING': 0xFFB5,
        'JIGGLE': 0xFFA7, 'THROB': 0xFFA6, 'PARAGRAPH': 0xBD, 'THOUGHT': 0xBE, 'ELECTRONIC': 0xBF,
        'TXT_MORE': 0xFFBA, 'TXT_ST': 0xFFB6, 'TXT_RD': 0xFFB8, 'TXT_TH': 0xFFB9, 'TXT_ND': 0xFFB7,
        'TXT_CURSOR': 0xFFBB, 'TXT_JOYSTICK': 0xFFB1, 'TXT_IGNORE': 0x3E8, 'PMARKER': 0xFE}
# codes that draw nothing (colour, effect, bubble style, break marker)
ZERO_WIDTH = {0xFFA1, 0xFFA2, 0xFFA3, 0xFFA4, 0xFFA5, 0xFFA6, 0xFFA7, 0xBE, 0xBF, 0xFE, 0x3E8}
ICON_W = 24        # estimate (font pixels) for a button/icon code: their drawers are not decoded
# Measured on a Linux frame of a 4-line scrolling bubble (TrainingLevel string 29, 2026-10-22):
# ink widths of 4 lines match advances + 1.625 font px per glyph within 3 px, line pitch 25 px.
SPACING = 1.625
LINE_PX = 25.0
PARA, PMARK, SPACE, NL = 0xBD, 0xFE, 0x20, 0x0A
FONT_SCALE, BUBBLE_SCALE, SMALL_CAPS = 0.81, 0.9, 0.81   # font table 0x006BAEC8, 0x000E0B84, 0x000E2325
BUBBLE = {'wrap': 20, 'max_lines': 4, 'scroll_height': 160}
WIDE = {'wrap': 40, 'max_lines': 6, 'scroll_height': 240}


# ---------------------------------------------------------------- bank format

class Bank:
    def __init__(self, d):
        if d[:4] != b'CAFF' or d[0x180:0x184] != b'text':
            raise ValueError('not a CAFF text bank')
        self.d = d
        D = self.D = d[0x180:]
        self.L = L = struct.unpack_from('<I', D, 0x20)[0]
        if D[L:L + 4] != b'LSBL':
            raise ValueError('LSBL not found')
        self.h = list(struct.unpack_from('<9I', D, L))
        n = self.h[8]
        self.ents = [struct.unpack_from('<HI', D, L + 0x24 + 6 * k) for k in range(n + 1)]
        self.pool = L + 0x24 + 6 * (n + 1)
        self.texts = {}
        for sid, off in self.ents[:-1]:
            p = q = self.pool + 2 * off
            while D[q:q + 2] != b'\0\0':
                q += 2
            self.texts[sid] = D[p:q].decode('utf-16-le')
        self.order = [sid for sid, _ in self.ents[:-1]]
        self.keys = {}
        nk = struct.unpack_from('<I', D, 0x28)[0]
        for k in range(nk):
            p, _hash, sid = struct.unpack_from('<IHH', D, 0x2C + 8 * k)
            q = p
            while D[q:q + 2] != b'\0\0':
                q += 2
            self.keys[sid] = D[p:q].decode('utf-16-le')

    def sounds(self):
        """{cutscene name: [{cue, file}]} from the build comments in block 2."""
        out = {}
        txt = self.D[self.pool:].decode('latin-1')
        for m in re.finditer(r'; (\S+) ?\n((?:; Mpeg = \d+: [^\n]*\n)*)', txt):
            out[m.group(1)] = [{'cue': int(a), 'file': b.strip()}
                               for a, b in re.findall(r'Mpeg = (\d+): ([^\n]*)', m.group(2))]
        return out

    def rebuild(self, new):
        """Bank bytes with texts {id: text}; unchanged texts give the same bytes."""
        texts = dict(self.texts)
        texts.update(new)
        D, L, h = self.D, self.L, self.h
        old_end = self.pool + 2 * self.ents[-1][1]
        pool = bytearray()
        ents = []
        for sid in self.order:
            t = texts[sid]
            if '\0' in t or any(ord(c) > 0xFFFF for c in t):
                raise ValueError('id %d: NUL or a character above U+FFFF' % sid)
            ents.append((sid, len(pool) // 2))
            pool += t.encode('utf-16-le') + b'\0\0'
        delta = len(pool) - (old_end - self.pool)
        ents.append((0xFFFF, len(pool) // 2))
        # content end before the 4-byte padding
        ds = struct.unpack_from('<I', self.d, 0x34)[0]
        last = [x for x in h[4:7] if x]
        cend = L + last[-1] + struct.unpack_from('<I', D, L + last[-1])[0] if last else L + 0x1C + h[7]
        body = bytearray(D[:self.pool]) + pool + D[old_end:cend]
        body += b'\0' * (-len(body) % 4)
        nds = len(body)
        tail = D[ds:]
        for k, e in enumerate(ents):
            struct.pack_into('<HI', body, L + 0x24 + 6 * k, *e)
        for i in (4, 5, 6):
            if h[i]:
                struct.pack_into('<I', body, L + 4 * i, h[i] + delta)
        struct.pack_into('<I', body, L + 0x1C, h[7] + delta)
        struct.pack_into('<I', body, 0x14, struct.unpack_from('<I', D, 0x14)[0] + delta)
        out = bytearray(self.d[:0x180]) + body + tail
        dsec = nds - ds
        struct.pack_into('<I', out, 0x34, nds)
        for o in (0x50, 0x64):
            struct.pack_into('<I', out, o, struct.unpack_from('<I', out, o)[0] + dsec)
        struct.pack_into('<I', out, 0x14, caff_hash(out))
        return bytes(out)


# ---------------------------------------------------------------- layout

TAG_RE = re.compile(r'\{([^{}]*)\}')   # 0x001F3110 takes any {...}; an unknown name gives a wrong code


def units(text):
    """Text -> list of (code, shown text); a tag is one code word as in 0x001F3110."""
    out, unknown, i = [], [], 0
    for m in TAG_RE.finditer(text):
        out += [(ord(c), c) for c in text[i:m.start()]]
        name = m.group(1)
        if name in TAGS:
            out.append((TAGS[name], m.group(0)))
        else:
            unknown.append(m.group(0))
            out.append((0xFFFF, m.group(0)))
        i = m.end()
    out += [(ord(c), c) for c in text[i:]]
    return out, unknown


def wrap(para, W):
    """Word wrap of 0x000DFD90: count code words; past W, the last space or
    {PMARKER} becomes a newline. A word longer than W is not split."""
    out = list(para)
    col, brk = 0, -1
    for i, (c, _) in enumerate(out):
        col += 1
        if c in (SPACE, PMARK):
            brk = i
        if col > W and brk != -1:
            out[brk] = (NL, '\n')
            col = i - brk
            brk = -1
    lines, cur = [], []
    for u in out:
        if u[0] == NL:
            lines.append(cur)
            cur = []
        else:
            cur.append(u)
    lines.append(cur)
    return lines


def line_width(line, font):
    """Width in font pixels before scaling (measure 0x003D5130, small caps of 0x000E22E0)."""
    w = 0.0
    adv = font['advance']
    for c, _ in line:
        if c == SPACE:
            w += font['space'] + SPACING
        elif c in ZERO_WIDTH:
            pass
        elif 0x61 <= c <= 0x7A:
            w += (adv.get(c - 0x20, 0) + SPACING) * SMALL_CAPS
        elif c >= 0xFFA1:
            w += ICON_W
        else:
            w += adv.get(c, adv.get(0x25A1, 0)) + SPACING
    return w


def layout(text, font, bubble, display_time=None, japanese=False):
    us, unknown = units(text)
    paras, cur = [], []
    for u in us:
        if u[0] == PARA:
            paras.append(cur)
            cur = []
        else:
            cur.append(u)
    paras.append(cur)
    s = FONT_SCALE * BUBBLE_SCALE
    res, warn = [], ['unknown tag %s (the game shows a wrong code)' % t for t in unknown]
    fits = not unknown
    for p in paras:
        W = bubble['wrap']
        if display_time:   # 0x000DFDC2: long speech widens the lines
            k = 0.6 * display_time
            if k >= 5:
                W = int(len(p) / k)
                if not japanese:
                    W = max(W, bubble['wrap'])
        lines = wrap(p, W)
        shown = [''.join(t for _, t in ln) for ln in lines]
        tw = max(line_width(ln, font) for ln in lines) * s if font else None
        th = len(lines) * LINE_PX if font else None
        n, L = len(lines), bubble['max_lines']
        scrolls = n > L
        if font:
            if scrolls:
                bw, bh = max(tw + 60, 150), bubble['scroll_height']
            else:
                bw, bh = tw + 50, th + (60 if n == L else 40)
        else:
            bw = bh = None
        res.append({'lines': shown, 'units': len(p), 'text_w': _r(tw), 'text_h': _r(th),
                    'bubble_w': _r(bw), 'bubble_h': _r(bh), 'scrolls': scrolls})
        if scrolls:
            fits = False
            warn.append('paragraph %d: %d lines > %d, the text scrolls' % (len(res), n, L))
        for ln, sh in zip(lines, shown):
            if len(ln) > W and not any(c in (SPACE, PMARK) for c, _ in ln):
                fits = False
                warn.append('word longer than %d: %r' % (W, sh))
        if font and bw > 600:
            fits = False
            warn.append('paragraph %d: bubble %d px wide (screen 640)' % (len(res), bw))
    if len(us) > 511:
        warn.append('%d code words: over 511 can overflow a static buffer (0x0076F108)' % len(us))
        fits = False
    return {'wrap': bubble['wrap'], 'max_lines': bubble['max_lines'], 'paragraphs': res,
            'fits': fits, 'warnings': warn}


def _r(v):
    return None if v is None else round(v, 1)


def load_font(path):
    if not path or not os.path.exists(path):
        return None
    from conker_font import metrics
    return metrics(path)


def missing_chars(text, font):
    if not font:
        return []
    us, _ = units(text)
    return sorted({t for c, t in us if c < 0xFFA1 and c not in ZERO_WIDTH and c not in (SPACE, PARA, NL)
                   and not (0x61 <= c <= 0x7A) and c not in font['advance']})


# ---------------------------------------------------------------- JSON

KEY_RE = re.compile(r'^cutscene_(.+)_(\d+)_(\d+)$')


def export(text_dir, lang, bubble, font_path=None):
    if font_path is None:
        font_path = os.path.join(text_dir, '..', 'font',
                                 'ConkerFontJapanese' if lang == 'Japanese' else 'ConkerFont', 'default.bin')
    font = load_font(font_path)
    out = {'format': 'conker-lr-text/1', 'game': 'Conker: Live and Reloaded (Xbox, NTSC)',
           'language': lang, 'bubble': bubble,
           'font': os.path.basename(os.path.dirname(os.path.abspath(font_path))) if font else None,
           'font_path': os.path.abspath(font_path) if font else None,
           'note': 'Edit "text" only. Keep {TAGS}. Run "check" after edits; "import" writes the banks.',
           'strings': []}
    voice = _voices(os.path.join(text_dir, '..', '..', 'Audio'))
    for bank in sorted(os.listdir(os.path.join(text_dir, lang))):
        p = os.path.join(text_dir, lang, bank, 'default.bin')
        if not os.path.exists(p):
            continue
        b = Bank(open(p, 'rb').read())
        snd = b.sounds()
        for lst in snd.values():
            for s in lst:
                s.update(voice.get(s['file'].lower().rsplit('.', 1)[0], {}))
        for sid in b.order:
            key = b.keys.get(sid)
            e = {'bank': bank, 'id': sid, 'key': key, 'source': b.texts[sid], 'text': b.texts[sid]}
            m = KEY_RE.match(key or '')
            if m:
                e.update(kind='cutscene', scene=m.group(1), cutscene=int(m.group(2)), line=int(m.group(3)),
                         speaker=None, display_time=None,
                         sounds=snd.get('cutscene_%s_%s' % (m.group(1), m.group(2)), []))
            else:
                e['kind'] = 'ui'
            out['strings'].append(e)
    annotate(out, font)
    return out


def _voices(audio_dir):
    """{cue name: {xwb, wave, wav, seconds}} for cutscene speech (conker_audio.speech_cues)."""
    if not os.path.exists(os.path.join(audio_dir, 'conker_sb.bin')):
        return {}
    from conker_audio import WaveBank, speech_cues, wav_name
    out, banks = {}, {}
    for name, c in speech_cues(audio_dir).items():
        if not c['xwb']:
            continue
        if c['xwb'] not in banks:
            banks[c['xwb']] = WaveBank(os.path.join(audio_dir, c['xwb'] + '.xwb'))
        e = banks[c['xwb']].entries[c['wave']]
        out[name] = {'xwb': c['xwb'], 'wave': c['wave'], 'seconds': e['duration'],
                     'wav': '%s/%s' % (c['xwb'], wav_name(e, name))}
    return out


def annotate(doc, font):
    jp = doc.get('language') == 'Japanese'
    for e in doc['strings']:
        e.pop('layout', None)
        e.pop('missing_glyphs', None)
        miss = missing_chars(e['text'], font)
        if miss:
            e['missing_glyphs'] = miss
        if e.get('kind') == 'cutscene':
            e['layout'] = layout(e['text'], font, doc['bubble'], e.get('display_time'), jp)


def import_(text_dir, doc, out_dir, lang=None):
    lang = lang or doc['language']
    by_bank = {}
    for e in doc['strings']:
        by_bank.setdefault(e['bank'], []).append(e)
    written = []
    for bank, es in sorted(by_bank.items()):
        src = os.path.join(text_dir, lang, bank, 'default.bin')
        b = Bank(open(src, 'rb').read())
        new = {}
        for e in es:
            if e['id'] not in b.texts:
                raise ValueError('%s: id %d not in the bank' % (bank, e['id']))
            if e.get('key') != b.keys.get(e['id']):
                raise ValueError('%s id %d: key %r, bank has %r' % (bank, e['id'], e.get('key'),
                                                                   b.keys.get(e['id'])))
            if e['text'] != b.texts[e['id']]:
                new[e['id']] = e['text']
        if not new:
            continue
        dst = os.path.join(out_dir, lang, bank, 'default.bin')
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, 'wb') as o:
            o.write(b.rebuild(new))
        written.append((bank, len(new)))
    return written


def selftest(text_dir):
    """Round trip of every bank, plus one grown string re-read from the rebuilt bytes."""
    n = bad = 0
    for lang in sorted(os.listdir(text_dir)):
        for bank in sorted(os.listdir(os.path.join(text_dir, lang))):
            p = os.path.join(text_dir, lang, bank, 'default.bin')
            if not os.path.exists(p):
                continue
            d = open(p, 'rb').read()
            b = Bank(d)
            n += 1
            if b.rebuild({}) != d or struct.unpack_from('<I', d, 0x14)[0] != caff_hash(d):
                bad += 1
                print('DIFF', lang, bank)
                continue
            sid = b.order[0]
            grown = b.texts[sid] + ' Довгий рядок перекладу ' * 7
            d2 = b.rebuild({sid: grown})
            b2 = Bank(d2)
            ok = (b2.texts[sid] == grown and b2.keys == b.keys and
                  all(b2.texts[k] == b.texts[k] for k in b.order[1:]) and
                  b2.D[b2.L + b2.h[4]:b2.L + b2.h[4] + 4] == b.D[b.L + b.h[4]:b.L + b.h[4] + 4] and
                  b2.sounds() == b.sounds() and len(d2) % 4 == 0 and
                  struct.unpack_from('<I', d2, 0x14)[0] == caff_hash(d2) and
                  len(d2) == 0x180 + struct.unpack_from('<I', d2, 0x50)[0] and
                  Bank(b2.rebuild({sid: b.texts[sid]})).d == d)
            if not ok:
                bad += 1
                print('GROW FAIL', lang, bank)
    # wrap rule: 0x000DFD90 on the documented 120-char test line (2026-10-22)
    lines = wrap(units('Oh no! My head feels like a whole marching band has')[0], 20)
    assert [''.join(t for _, t in ln) for ln in lines] == \
        ['Oh no! My head feels', 'like a whole', 'marching band has'], lines
    print('%d banks, %d failed' % (n, bad))
    return bad == 0


def _bubble(args):
    b = dict(WIDE if '--bubble' in args and args[args.index('--bubble') + 1] == 'wide' else BUBBLE)
    for opt, k in (('--wrap', 'wrap'), ('--lines', 'max_lines'), ('--height', 'scroll_height')):
        if opt in args:
            b[k] = int(args[args.index(opt) + 1])
    return b


def main(a):
    if a[:1] == ['export']:
        doc = export(a[1], a[2], _bubble(a), a[a.index('--font') + 1] if '--font' in a else None)
        with open(a[3], 'w', encoding='utf-8') as o:
            json.dump(doc, o, ensure_ascii=False, indent=1)
        bad = sum(1 for e in doc['strings'] if not e.get('layout', {'fits': True})['fits'])
        print('%d strings, font %s, %d cutscene lines do not fit' % (len(doc['strings']), doc['font'], bad))
    elif a[:1] == ['import']:
        doc = json.load(open(a[2], encoding='utf-8'))
        w = import_(a[1], doc, a[3], a[a.index('--lang') + 1] if '--lang' in a else None)
        for bank, k in w:
            print('%-24s %d strings changed' % (bank, k))
        print('%d banks written' % len(w))
    elif a[:1] == ['check']:
        doc = json.load(open(a[1], encoding='utf-8'))
        if any(o in a for o in ('--bubble', '--wrap', '--lines', '--height')):
            doc['bubble'] = _bubble(a)
        fp = a[a.index('--font') + 1] if '--font' in a else doc.get('font_path')
        font = load_font(fp)
        if not font:
            print('font %r not found: layout without pixel sizes (use --font FONT.bin)' % fp)
        annotate(doc, font)
        with open(a[1], 'w', encoding='utf-8') as o:
            json.dump(doc, o, ensure_ascii=False, indent=1)
        # report edited strings only: many original lines scroll too
        bad = [e for e in doc['strings'] if e['text'] != e['source'] and
               (not e.get('layout', {'fits': True})['fits'] or e.get('missing_glyphs'))]
        for e in bad:
            print('%s/%s %s: %s%s' % (e['bank'], e['id'], e['key'], '; '.join(e.get('layout', {}).get('warnings', [])),
                                     ' missing glyphs ' + ''.join(e['missing_glyphs']) if e.get('missing_glyphs') else ''))
        print('%d strings, %d edited, %d edited with problems' % (
            len(doc['strings']), sum(e['text'] != e['source'] for e in doc['strings']), len(bad)))
    elif a[:1] == ['selftest']:
        sys.exit(0 if selftest(a[1]) else 1)
    else:
        print(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
