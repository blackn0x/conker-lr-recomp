# Conker L&R (Xbox) text banks: growth limit and on-screen text (2026-10-22)

From the Conker static-recompilation session (repo conker-lr-xbox, branch
switch-local-build; tool `tools/caff_text.py`). VAs are guest addresses in
`default.xbe` (retail NTSC, sha1 2232a1b3...).

## Q1. Why growing LSBL strings freezes, and the real limit

**Cause (tested):** the game sizes each text bank's buffer from the CAFF header,
not from the file length. A string grown in place makes the file longer than
the header says, so the load writes past the buffer into the next heap block.
Small growth lands in allocation slack and seems to work; larger growth
corrupts the heap and freezes or crashes later.

Linux run of the lifted game, MPFortress strings 0 and 1 grown by 520
characters each:
- bytes only, header untouched: crash at boot right after MPFortress loads
  (in 0x001F1360, the file-request list at [0x00775F48] overwritten with text);
- same growth plus the header fields below updated: boots normally.

**Loader:** 0x004065B0 (header callback) -> 0x004072F0 (header check) ->
0x00406020 (sections) -> per-section reads -> 0x004062E0 (after load).
Errors go to 0x004069D0.

**Header check 0x004072F0** (returns 0 OK, 1 bad magic, 2 bad version, 3 bad sum):
- bytes 0..3 "CAFF" (string at 0x005D8954), bytes 4..16 "28.01.05.0031" (0x006460E8);
- checksum at +0x14: ELF/PJW hash over the first 0x180 bytes with +0x14 set to 0,
  bytes taken as **signed** chars:
  `h = (h << 4) + (int8)b; g = h & 0xF0000000; if g: h ^= (g >> 24) | g`.

**Fields to update when text grows by D bytes (D = 2 x added UTF-16 chars):**
| Field | Offset | MPFortress value |
|---|---|---|
| data size | header +0x34 | 0x22B0 |
| section size | header +0x50 (entry +0x10) | 0x2414 |
| section size again | header +0x64 (entry +0x24) | 0x2414 |
| LSBL block size | LSBL +0x10 | 0xEF4 |
| LSBL index | entries after the grown string | +added chars |
| LSBL terminator | (0xFFFF, pool length in chars) | +added chars |
| checksum | header +0x14 | recompute last |

Layout: header 0x180 bytes; `.data` = data (header+0x34 bytes) + tail (build
path string + big-endian relocation offsets; count at header+0x2C). All 63
relocations in MPFortress point to the start of `.data` (the pointer to LSBL at
+0x20 and the UTF-16 key names), before LSBL, so growing dialogue text does not
move relocation targets. LSBL: "LSBL", +0x10 block size, +0x20 count N, then N
entries of (u16 id, u32 offset in UTF-16 units into the pool), a terminator
(0xFFFF, pool length in units), then the pool of NUL-terminated UTF-16 strings.

`tools/caff_text.py grow IN OUT fixed IDX:N ...` does all of this (and `check
FILE` verifies a checksum). Checked: the checksum matches the original
MPFortress (0x05D42770) and TrainingLevel (0x04CCB430) files.

**Max safe length:** no fixed table cap was found (the bank buffer comes from
the header). Per displayed string, the on-screen text node keeps the text
inline at node+0x28..+0x1028 (0x1000 bytes), so keep one displayed string under
2047 UTF-16 characters. Not tested: in-game display of the grown MPFortress
strings (they are multiplayer option values).

## Q2. Speech/subtitle bubble (2026-10-22, found)

**Short answer:** the bubble wraps at **20 characters per line** (UTF-16 units,
a tag code counts as 1), breaking at a space or `{PMARKER}`. It is never more
than **4 lines tall**; longer text is not cut: the bubble stays 4 lines high
and the text **scrolls up** while the line is shown. Each `{PARAGRAPH}` starts
a new bubble.

**Chain (VAs in default.xbe):**
1. 0x000569A0 (cutscene player) asks 0x00055810 for the line: it builds the key
   `cutscene_<scene>_...`, looks it up in the bank (0x003F9CB0) and runs the tag
   expander 0x001F3110 in place.
2. 0x001F3110 replaces each `{TAG}` (names: UTF-16 table at 0x006B9D98, 35
   entries) with one code word (table 0x006B9E28): `{PARAGRAPH}` 0x00BD,
   `{PMARKER}` 0x00FE, `{THOUGHT}` 0x00BE, `{ELECTRONIC}` 0x00BF, colours and
   button icons 0xFFA1..0xFFBE (one glyph each; drawers registered by 0x001F3600).
3. 0x000569A0 copies the expanded line (wcscpy, no length check) to
   bubble+0x2060; the bubble object comes from 0x00054700.
4. Layout 0x000E0850 (a twin at 0x000E0CD0 with the same constants): for the
   current paragraph (0x000E2230 skips to it by 0x00BD), 0x000DFD90 copies it to
   bubble+8 (buffer up to bubble+0x2008 = 4096 chars) and word-wraps it;
   0x000E2280 counts the lines (newlines 0x0A + 1); 0x000E22E0 measures them; then the
   bubble size is set.
5. Drawing 0x000E2940.

**Word wrap 0x000DFD90 (character count, not pixels):**
- t = display time in seconds ([bubble+0x2044] / 60).
- If 0.6 x t < 5 (0x00648D1C = 5.0, factor 0x00649228 = 0.6): W = 20 (0x14).
- Else W = 0x000DFEC0 = paragraph length / (0.6 x t), i.e. about 0.6 x t lines
  (5 or more lines, so these always scroll).
- W is raised to at least 20, except for language 2 (0x0042C91F reads
  XC_LANGUAGE; 2 = Japanese).
- Breaks: the last space (0x20) or `{PMARKER}` (0x00FE) before the line passes
  W characters becomes a newline (0x0A). A word longer than W is not split.
- Display time: [bubble+0x2044] from the line's speech timing (0x00055980), or
  length x 5 frames (0.0833 x 60) when the time is over 3600 frames; x 2.5 for
  language 2.

**Bubble size (0x000E0B5E..0x000E0C97, floats on the 640x480 screen):**
| Lines | Width | Height |
|---|---|---|
| 1-3 | text width + 50 | text height + 40 |
| 4 | text width + 50 | text height + 60 |
| more than 4 | max(text width + 60, 150) | **160 (fixed)** |
Then +60/+60 for one bubble style, +20 width with flag bit 1, and a script can
set width/height directly (bubble+0x9C / +0xA0, -1 = automatic). Text scale:
0.9 (0x006B3F00; or a script value x 0.009) x ConkerFont 0.81 = 0.729.

**There is no shrink step for bubbles:** the 0.05 shrink is 0x002AC1F0, a
different UI box (more than 3 lines -> scale -0.05 per pass until it fits).

**Safe lengths for a translation (ConkerFont, all languages but Japanese):**
- per line: 20 characters (the game wraps there itself; words over 20 stay on
  one long line and widen the bubble);
- per bubble at once: 4 lines = about 80 characters; more scrolls, so keep a
  `{PARAGRAPH}` short enough to read in its speech time;
- hard limits: bubble text buffer 4096 characters (bubble+8); a cutscene line
  goes through a static 0x200-character buffer (0x0076F108) on one path
  (flag 0x00847134), so keep one line (all its paragraphs) under 511
  characters to be safe.

**How to change it:** the 20 is the immediate `mov dword [esp+0x14], 0x14` at
0x000DFDF3 and the `mov eax, 0x14` at 0x000DFE23 (two places); the 4-line rule
is the `cmp eax, 4` at 0x000E0B9C / `cmp [esp+0x18], 4` at 0x000E0BFF (and the
twin at 0x000E1298 / 0x000E12FA), with the fixed height 160.0 at 0x00649428.
In the recompiled port this would be a wrapper in src/recomp_manual.c; on the
Xbox it is a byte patch of default.xbe. Wider lines need a wider bubble: the
bubble widths follow the text, so a larger W alone works, but a bubble near
the screen edge can then leave the screen.

**Verified at runtime (Linux build, 2026-10-22):** the path 0x00055810 ->
0x001F3110 (gdb watchpoint on the line's text); the 20-character wrap and the
4-line bubble that scrolls: TrainingLevel string 29 changed with
`tools/caff_text.py set` to a 120-character first paragraph, the intro showed
"OH NO! MY HEAD FEELS / LIKE A WHOLE / MARCHING BAND HAS / ..." in a bubble of
about 290 x 155 pixels, scrolling.
**Read from code only:** the width formula for long speech (W = length /
0.6t), the size constants 50/40/60/150/160, the language-2 exception, the
display-time rules and the buffer sizes.

### Earlier, other text code (for reference)
- Font table at 0x006BAEC8, 0x18-byte records: ConkerFont (scale 0.81 x 0.81),
  FrontendTitle (1.0), ConkerFontJapanese (0.81), FrontendTitleJapanese (1.0).
  Current font pointer [0x006BAF28], set at 0x001F5463.
- Text helpers: measure 0x003D3EC0, extent 0x003D4F60, draw 0x003D3E60.
- On-screen text pass 0x001F2BC0 (menus/HUD): list from [0x00849794], text inline
  at node+0x28 (0x1000 bytes); flag 0x02 clips to x 48..592.
- Two-line caption 0x002255B0: breaks at the space nearest the middle when
  wider than [0x005A005C].
