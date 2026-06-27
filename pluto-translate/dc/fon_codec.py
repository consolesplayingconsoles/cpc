#!/usr/bin/env python3
"""Dreamcast S18RM04.FON font codec + Catalan accent authoring + text encoder.

The reusable core for translating into a Latin-accented language on a Dreamcast
font that ships SJIS-only (no half-width, no accents). Pure stdlib (Python 3.6,
no shift_jis codec needed) so it runs on the Batocera box.

FONT FORMAT (cracked 2026-06-27 via yzb's CrystalTile2 params):
  106-byte records; [0:2] = JIS code BYTE-SWAPPED ([low][high]); [2:10] = per-glyph
  header; [10:106] = 2bpp bitmap, WIDTH 20 (5 bytes/row, MSB-first, palette 0..3),
  19 rows. Glyph index = JIS row-major (glyph0 = JIS 2121); record = idx*106.

ACCENTS: SJIS can't encode à/é/ç and the font has no glyphs for them. We overwrite
the GREEK glyph slots (SJIS 0x839F-0x83D6) -- a Japanese game never renders Greek
(verified: 0 of a game's 1817 codes fall in that range) -- with base-letter + accent
glyphs, and `fw()` encodes each accented char as its Greek SJIS code.

    fon_codec.py <orig.FON> <patched.FON>     # write a patched font with accents
"""
import sys

STRIDE, BMP, W, BPR, ROWS = 106, 10, 20, 5, 19

def jis_index(jhi, jlo): return (jhi - 0x21) * 94 + (jlo - 0x21)
def sjis2jis(s1, s2):
    s1 -= 0x81 if s1 < 0xA0 else 0xC1
    if s2 < 0x9F: jlo = s2 - (0x1F if s2 < 0x7F else 0x20); jhi = s1*2 + 0x21
    else:         jlo = s2 - 0x7E;                          jhi = s1*2 + 0x22
    return jhi, jlo

# ── glyph codec ───────────────────────────────────────────────────────────────
def decode(rec):
    bmp, grid = rec[BMP:BMP+ROWS*BPR], []
    for r in range(ROWS):
        row = []
        for b in bmp[r*BPR:(r+1)*BPR]:
            for s in (6,4,2,0): row.append((b>>s)&3)
        grid.append(row[:W])
    return grid
def encode(grid):
    out = bytearray()
    for row in grid:
        px = list(row) + [0]*(W-len(row))
        for c in range(0, W, 4):
            out.append((px[c]<<6)|(px[c+1]<<4)|(px[c+2]<<2)|px[c+3])
    return bytes(out)
def show(grid):
    pal = " .:#"
    return "\n".join("".join(pal[v] for v in row) for row in grid)

# ── accent marks (up = uppercase cap fills rows ~3-18 -> mark at 0-2) ───────────
def _grave(g, up):
    for k, c in enumerate((8,9,10)):
        if (0 if up else 1)+k < ROWS: g[(0 if up else 1)+k][c] = 3
    return g
def _acute(g, up):
    for k, c in enumerate((11,10,9)):
        if (0 if up else 1)+k < ROWS: g[(0 if up else 1)+k][c] = 3
    return g
def _dieresis(g, up):
    b = 0 if up else 1
    for c in (8,12): g[b][c] = 3; g[b+1][c] = 3
    return g
def _cedilla(g, up):
    for (r,c) in ((17,11),(18,11),(18,10)): g[r][c] = 3
    return g
def _cleartop(g, n):
    for r in range(n):
        for c in range(W): g[r][c] = 0
    return g

# accented char -> (base JIS hi, lo, accent fn, clear-i-dot rows, target SJIS hi, lo)
ACCENT_SPEC = {
 "à":(0x23,0x61,_grave,0,0x83,0xBF), "è":(0x23,0x65,_grave,0,0x83,0xC0),
 "é":(0x23,0x65,_acute,0,0x83,0xC1), "í":(0x23,0x69,_acute,5,0x83,0xC2),
 "ï":(0x23,0x69,_dieresis,5,0x83,0xC3), "ò":(0x23,0x6F,_grave,0,0x83,0xC4),
 "ó":(0x23,0x6F,_acute,0,0x83,0xC5), "ú":(0x23,0x75,_acute,0,0x83,0xC6),
 "ü":(0x23,0x75,_dieresis,0,0x83,0xC7), "ç":(0x23,0x63,_cedilla,0,0x83,0xC8),
 "À":(0x23,0x41,_grave,0,0x83,0x9F), "È":(0x23,0x45,_grave,0,0x83,0xA0),
 "É":(0x23,0x45,_acute,0,0x83,0xA1), "Í":(0x23,0x49,_acute,0,0x83,0xA2),
 "Ï":(0x23,0x49,_dieresis,0,0x83,0xA3), "Ò":(0x23,0x4F,_grave,0,0x83,0xA4),
 "Ó":(0x23,0x4F,_acute,0,0x83,0xA5), "Ú":(0x23,0x55,_acute,0,0x83,0xA6),
 "Ü":(0x23,0x55,_dieresis,0,0x83,0xA7), "Ç":(0x23,0x43,_cedilla,0,0x83,0xA8),
}

def build_patched_font(src_bytes):
    """Return font bytes with the 20 Catalan accent glyphs authored into Greek slots."""
    data = bytearray(src_bytes)
    for ch, (bhi, blo, acc, clr, shi, slo) in ACCENT_SPEC.items():
        rec = bytearray(data[jis_index(bhi,blo)*STRIDE:][:STRIDE])
        g = decode(rec)
        if clr: _cleartop(g, clr)
        acc(g, ch.isupper())
        rec[BMP:BMP+ROWS*BPR] = encode(g)
        jhi, jlo = sjis2jis(shi, slo)
        rec[0], rec[1] = jlo, jhi
        off = jis_index(jhi, jlo)*STRIDE
        data[off:off+STRIDE] = rec
    # standalone hyphen (no glyph in stock font) -> Greek slot 0x83C9, mid-row bar
    rec = bytearray(data[jis_index(0x23,0x61)*STRIDE:][:STRIDE])   # borrow 'a' header
    g = [[0]*W for _ in range(ROWS)]
    for c in range(6,14): g[9][c] = 3; g[10][c] = 3
    rec[BMP:BMP+ROWS*BPR] = encode(g)
    jhi, jlo = sjis2jis(0x83, 0xC9); rec[0], rec[1] = jlo, jhi
    hoff = jis_index(jhi,jlo)*STRIDE; data[hoff:hoff+STRIDE] = rec
    return bytes(data)

# ── text encoder: Catalan -> full-width / Greek-slot SJIS (codec-free) ──────────
_PUNCT = {" ":0x8140, ".":0x8144, ",":0x8143, "!":0x8149, "?":0x8148,
         ":":0x8146, ";":0x8147, "(":0x8169, ")":0x816a, "'":0x8166, "’":0x8166}
_ACCENTS = {ch: (shi<<8)|slo for ch,(_,_,_,_,shi,slo) in ACCENT_SPEC.items()}
_ACCENTS["-"] = 0x83C9   # authored hyphen (enclitics: Ves-te'n, ajudar-lo)

def fw(s):
    """Catalan text -> Shift-JIS bytes the patched font renders (accents included)."""
    s = s.replace("l·l","ll").replace("L·L","LL").replace("·","")   # no middot glyph yet
    o = bytearray()
    for ch in s:
        c = ord(ch)
        if ch in _ACCENTS:      o += _ACCENTS[ch].to_bytes(2,"big")
        elif 0x41 <= c <= 0x5a: o += (0x8260+c-0x41).to_bytes(2,"big")
        elif 0x61 <= c <= 0x7a: o += (0x8281+c-0x61).to_bytes(2,"big")
        elif 0x30 <= c <= 0x39: o += (0x824f+c-0x30).to_bytes(2,"big")
        elif ch in _PUNCT:      o += _PUNCT[ch].to_bytes(2,"big")
        else: raise ValueError("no full-width glyph for %r" % ch)
    return bytes(o)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: fon_codec.py <orig.FON> <patched.FON>"); sys.exit(1)
    out = build_patched_font(open(sys.argv[1], "rb").read())
    open(sys.argv[2], "wb").write(out)
    print("wrote %s (%d accent glyphs in Greek slots)" % (sys.argv[2], len(ACCENT_SPEC)))
