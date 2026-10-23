#!/usr/bin/env python3
"""Conker: Live & Reloaded (Xbox) audio: XACT wave banks (dvddata/Audio/*.xwb).

  conker_audio.py index AUDIO_DIR OUT.json [--text TEXT_DIR/English]
  conker_audio.py export AUDIO_DIR OUT_DIR BANK [BANK ...]     -> OUT_DIR/BANK/NNNN[_cue].wav
  conker_audio.py import BANK.xwb WAV_DIR OUT.xwb             -> entries NNNN*.wav replaced
  conker_audio.py selftest AUDIO_DIR

Wave bank (WBND version 3, XACT of XDK 5849): header 0x28 bytes (magic,
version, 4 regions of (offset, length): bank data, entries, two empty, wave
data), bank data at 0x28 (flags, entry count, name[16], 0x18, 0x40,
alignment, 0, 0), entries of 24 bytes at 0x50 (flags 0/1/2/0x10000, format, play offset,
play length, loop offset, loop length), wave data from the first aligned offset
after the entries, each entry aligned, zero padding. Format dword: bits 0-1
tag (0 = PCM 16-bit, 1 = Xbox ADPCM, 36-byte mono blocks of 64 samples),
bits 2-4 channels, bits 5-30 sample rate, bit 31 16-bit flag.

Speech links: Audio/conker_sb.bin packs 58 sound banks (XSB "SDBK" v11).
cut_speech.xsb: 12 wave bank names at +0x08, cue records of 20 bytes at 0x38
(u16 flags, u16 sound index, u32 name offset, ...), sound offsets (u24 << 8 |
flags) at +0x0C; a 72-byte sound ends with (u16 wave, u16 wave bank). The text
banks' "; Mpeg = N: name.wav" comments name the cue (N = the N-th AD_MPEG_*
entry of the game's sound table at 0x0065E060 in default.xbe). Checked: voice
length against the cutscene's text length over 147 cutscenes, r = 0.89.
The other XSBs use other layouts: their waves are listed by index only.

Repack: a WAV must be 16-bit PCM; it is stored as PCM (also over ADPCM
entries), any sample rate; loop region = whole sound if the original looped.
The entry count stays. Not checked in the game yet.
"""
import json
import os
import struct
import sys
import wave

HERE = os.path.dirname(os.path.abspath(__file__))

STEP = [7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73,
        80, 88, 97, 107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494,
        544, 598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499,
        2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487,
        12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767]
IDX = [-1, -1, -1, -1, 2, 4, 6, 8]


def adpcm_decode(data):
    """Xbox ADPCM (IMA, 36-byte mono blocks: s16 predictor, u8 index, pad, 32 data bytes)."""
    out = []
    for b in range(len(data) // 36):
        blk = data[36 * b:36 * b + 36]
        pred, ix = struct.unpack_from('<hB', blk)
        ix = min(ix, 88)
        out.append(pred)
        for byte in blk[4:]:
            for nib in (byte & 15, byte >> 4):
                s = STEP[ix]
                dd = s >> 3
                if nib & 4:
                    dd += s
                if nib & 2:
                    dd += s >> 1
                if nib & 1:
                    dd += s >> 2
                pred = max(-32768, min(32767, pred - dd if nib & 8 else pred + dd))
                ix = max(0, min(88, ix + IDX[nib & 7]))
                out.append(pred)
    return struct.pack('<%dh' % len(out), *out)


class WaveBank:
    def __init__(self, path):
        self.path = path
        with open(path, 'rb') as f:
            h = f.read(0x50)
            if h[:4] != b'WBND' or struct.unpack_from('<I', h, 4)[0] != 3:
                raise ValueError('%s: not a WBND v3 wave bank' % path)
            self.flags, n = struct.unpack_from('<II', h, 0x28)
            self.name = h[0x30:0x40].split(b'\0')[0].decode('latin-1')
            self.align = struct.unpack_from('<I', h, 0x48)[0]
            self.regions = struct.unpack_from('<8I', h, 8)
            self.head = h + f.read(24 * n)
        self.entries = []
        for i in range(n):
            fl, fmt, po, pl, lo, ll = struct.unpack_from('<6I', self.head, 0x50 + 24 * i)
            tag, ch, rate = fmt & 3, (fmt >> 2) & 7, (fmt >> 5) & 0x3FFFFFF
            samples = pl // (2 * ch) if tag == 0 else pl // (36 * ch) * 64
            self.entries.append(dict(index=i, flags=fl, format=fmt, codec={0: 'pcm16', 1: 'xbox_adpcm'}.get(tag, 'tag%d' % tag),
                                     channels=ch, rate=rate, offset=po, length=pl, loop=[lo, ll],
                                     duration=round(samples / rate, 3) if rate else 0))

    def data_off(self):
        return self.regions[6]

    def read(self, i):
        e = self.entries[i]
        with open(self.path, 'rb') as f:
            f.seek(self.data_off() + e['offset'])
            return f.read(e['length'])

    def pcm(self, i):
        e = self.entries[i]
        raw = self.read(i)
        if e['codec'] == 'pcm16':
            return raw
        if e['codec'] == 'xbox_adpcm' and e['channels'] == 1:
            return adpcm_decode(raw)
        raise ValueError('entry %d: %s with %d channels not decoded' % (i, e['codec'], e['channels']))

    def rebuild(self, new):
        """Bank bytes with entries {index: (channels, rate, pcm bytes)} replaced."""
        n, a = len(self.entries), self.align
        head = bytearray(self.head)
        doff = (0x50 + 24 * n + a - 1) // a * a
        body = bytearray()
        for e in self.entries:
            i = e['index']
            if i in new:
                ch, rate, data = new[i]
                fmt = (1 << 31) | (rate << 5) | (ch << 2)
                lo, ll = (0, len(data)) if e['loop'][1] else (0, 0)
            else:
                fmt, data = e['format'], self.read(i)
                lo, ll = e['loop']
            struct.pack_into('<6I', head, 0x50 + 24 * i, e['flags'], fmt, len(body), len(data), lo, ll)
            body += data
            body += b'\0' * (-len(body) % a)
        struct.pack_into('<II', head, 8 + 24, doff, len(body))
        return bytes(head) + b'\0' * (doff - len(head)) + bytes(body)


# ---------------------------------------------------------------- speech cues

def sound_banks(audio_dir):
    """{xsb name: bytes} from conker_sb.bin."""
    d = open(os.path.join(audio_dir, 'conker_sb.bin'), 'rb').read()
    n = struct.unpack_from('<I', d, 8)[0]
    p, ents = 0x10, []
    for _ in range(n):
        nl = struct.unpack_from('<I', d, p)[0]
        name = d[p + 4:p + 4 + nl].split(b'\0')[0].decode('latin-1')
        off, sz = struct.unpack_from('<II', d, p + 4 + nl)
        p += 12 + nl
        ents.append((name, off, sz))
    return {name.split('\\')[-1]: d[p + off:p + off + sz] for name, off, sz in ents}


def speech_cues(audio_dir):
    """{cue name (lower case): {cue, xwb, wave}} for the cutscene speech (cut_speech.xsb)."""
    x = sound_banks(audio_dir)['cut_speech.xsb']
    assert x[:4] == b'SDBK' and struct.unpack_from('<H', x, 4)[0] == 11

    def cs(o):
        return x[o:o + 64].split(b'\0')[0].decode('latin-1')
    wb_off, snd_off = struct.unpack_from('<II', x, 8)
    ncue = struct.unpack_from('<H', x, 0x1A)[0]
    nwb = struct.unpack_from('<H', x, 0x22)[0]
    banks = [cs(wb_off + 16 * i) for i in range(nwb)]
    offs = [struct.unpack_from('<I', x, snd_off + 4 * i)[0] >> 8 for i in range(ncue)]
    ends = offs[1:] + [struct.unpack_from('<I', x, 0x14)[0]]
    out = {}
    for k in range(ncue):
        _, si, no = struct.unpack_from('<HHI', x, 0x38 + 20 * k)
        name = cs(no)
        rec = {'cue': k, 'xwb': None, 'wave': None}
        if si < len(offs) and ends[si] - offs[si] == 72:
            w, b = struct.unpack_from('<HH', x, ends[si] - 4)
            if b < nwb:
                rec.update(xwb=banks[b], wave=w)
        out[name.lower()] = rec
    return out


def text_links(text_lang_dir):
    """{cue name: [text keys]} from the text banks' Mpeg comments."""
    sys.path.insert(0, HERE)
    from conker_text import Bank
    links = {}
    for bank in sorted(os.listdir(text_lang_dir)):
        p = os.path.join(text_lang_dir, bank, 'default.bin')
        if not os.path.exists(p):
            continue
        b = Bank(open(p, 'rb').read())
        keys = [k for k in b.keys.values() if k]
        for cut, snds in b.sounds().items():
            for s in snds:
                name = s['file'].lower().rsplit('.', 1)[0]
                for k in keys:
                    if k.rsplit('_', 1)[0] == cut:
                        links.setdefault(name, []).append('%s/%s' % (bank, k))
    return links


def index(audio_dir, text_lang_dir=None):
    cues = speech_cues(audio_dir)
    links = text_links(text_lang_dir) if text_lang_dir else {}
    by_wave = {(c['xwb'], c['wave']): (n, c['cue']) for n, c in cues.items() if c['xwb']}
    out = {'format': 'conker-lr-audio/1', 'banks': {}}
    for f in sorted(os.listdir(audio_dir)):
        if not f.endswith('.xwb'):
            continue
        wb = WaveBank(os.path.join(audio_dir, f))
        es = []
        for e in wb.entries:
            r = {k: e[k] for k in ('index', 'codec', 'channels', 'rate', 'duration', 'loop')}
            r['loop'] = bool(e['loop'][1])
            hit = by_wave.get((f[:-4], e['index']))
            if hit:
                r['cue'], r['cue_index'] = hit
                if hit[0] in links:
                    r['text_keys'] = sorted(set(links[hit[0]]))
            es.append(r)
        out['banks'][f[:-4]] = {'name': wb.name, 'alignment': wb.align, 'entries': es}
    return out


def wav_name(e, cue=None):
    return '%04d%s.wav' % (e['index'], '_' + cue if cue else '')


def export(audio_dir, out_dir, banks):
    cues = speech_cues(audio_dir)
    by_wave = {(c['xwb'], c['wave']): n for n, c in cues.items() if c['xwb']}
    for b in banks:
        wb = WaveBank(os.path.join(audio_dir, b + '.xwb'))
        d = os.path.join(out_dir, b)
        os.makedirs(d, exist_ok=True)
        for e in wb.entries:
            with wave.open(os.path.join(d, wav_name(e, by_wave.get((b, e['index'])))), 'wb') as w:
                w.setnchannels(e['channels'])
                w.setsampwidth(2)
                w.setframerate(e['rate'])
                w.writeframes(wb.pcm(e['index']))
        print('%-22s %d waves -> %s' % (b, len(wb.entries), d))


def import_(xwb, wav_dir, out):
    wb = WaveBank(xwb)
    new = {}
    for f in sorted(os.listdir(wav_dir)):
        if f.lower().endswith('.wav') and f[:4].isdigit():
            i = int(f[:4])
            if i >= len(wb.entries):
                raise ValueError('%s: bank has %d entries' % (f, len(wb.entries)))
            with wave.open(os.path.join(wav_dir, f)) as w:
                if w.getsampwidth() != 2:
                    raise ValueError('%s: need 16-bit PCM' % f)
                new[i] = (w.getnchannels(), w.getframerate(), w.readframes(w.getnframes()))
            e = wb.entries[i]
            if new[i][0] != e['channels']:
                print('warning: %s has %d channels, the original %d' % (f, new[i][0], e['channels']))
    data = wb.rebuild(new)
    with open(out, 'wb') as o:
        o.write(data)
    return len(new)


def selftest(audio_dir):
    import tempfile
    ok = True
    small = sorted((os.path.getsize(os.path.join(audio_dir, f)), f) for f in os.listdir(audio_dir)
                   if f.endswith('.xwb'))
    for _, f in small[:6]:
        p = os.path.join(audio_dir, f)
        wb = WaveBank(p)
        same = wb.rebuild({}) == open(p, 'rb').read()
        print('%-22s rebuild %s' % (f, 'OK' if same else 'DIFF'))
        ok &= same
    # replace entry 0 of the smallest bank with its own audio as PCM, read it back
    wb = WaveBank(os.path.join(audio_dir, small[0][1]))
    e = wb.entries[0]
    pcm = wb.pcm(0)
    with tempfile.TemporaryDirectory() as t:
        out = os.path.join(t, 'x.xwb')
        with open(out, 'wb') as o:
            o.write(wb.rebuild({0: (e['channels'], e['rate'], pcm)}))
        back = WaveBank(out)
        ok &= back.pcm(0) == pcm and len(back.entries) == len(wb.entries)
        ok &= all(back.read(i) == wb.read(i) for i in range(1, len(wb.entries)))
    print('replace entry: %s' % ('OK' if ok else 'FAIL'))
    cues = speech_cues(audio_dir)
    g = cues.get('gargoyle1')
    print('cue gargoyle1 -> %s' % g)
    ok &= g is not None and g['xwb'] == 'cut_hungover'
    # ADPCM: decoded speech is not noise (spectral flatness well below white noise)
    ad = [f for _, f in small if WaveBank(os.path.join(audio_dir, f)).entries[0]['codec'] == 'xbox_adpcm']
    if ad:
        wb = WaveBank(os.path.join(audio_dir, ad[0]))
        x = struct.unpack('<%dh' % (len(wb.pcm(0)) // 2), wb.pcm(0))
        diff = sum(abs(a - b) for a, b in zip(x, x[1:])) / max(1, len(x))
        amp = sum(abs(a) for a in x) / max(1, len(x))
        print('ADPCM %s entry 0: mean |step| %.0f, mean |x| %.0f (speech: step << amplitude)' % (ad[0], diff, amp))
        ok &= diff < amp
    return ok


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[:1] == ['index']:
        doc = index(a[1], a[a.index('--text') + 1] if '--text' in a else None)
        with open(a[2], 'w', encoding='utf-8') as o:
            json.dump(doc, o, ensure_ascii=False, indent=1)
        n = sum(len(b['entries']) for b in doc['banks'].values())
        k = sum(1 for b in doc['banks'].values() for e in b['entries'] if 'cue' in e)
        print('%d banks, %d waves, %d linked to a speech cue' % (len(doc['banks']), n, k))
    elif a[:1] == ['export']:
        export(a[1], a[2], a[3:])
    elif a[:1] == ['import']:
        print('%d entries replaced -> %s' % (import_(a[1], a[2], a[3]), a[3]))
    elif a[:1] == ['selftest']:
        sys.exit(0 if selftest(a[1]) else 1)
    else:
        print(__doc__)
