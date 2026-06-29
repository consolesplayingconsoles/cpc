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
def _grave(g, up):              # OPEN accent: 3px-thick \, leans LEFT (left-of-centre)
    r0 = 0 if up else 1
    for i in range(3):
        r = r0 + i
        for c in (6+i, 7+i, 8+i):
            if r < ROWS: g[r][c] = 3
    return g
def _acute(g, up):              # CLOSED accent: 3px-thick /, leans RIGHT (right-of-centre)
    r0 = 0 if up else 1
    for i in range(3):
        r = r0 + i
        for c in (13-i, 14-i, 15-i):
            if r < ROWS: g[r][c] = 3
    return g
def _dieresis(g, up):           # two bold 2x2 dots
    r0 = 0 if up else 1
    for rr, cc in ((r0,7),(r0,8),(r0+1,7),(r0+1,8),(r0,11),(r0,12),(r0+1,11),(r0+1,12)):
        if rr < ROWS: g[rr][cc] = 3
    return g
def _cedilla(g, up):            # bolder tail under c/C
    for r, c in ((16,10),(16,11),(17,11),(17,12),(18,10),(18,11)): g[r][c] = 3
    return g
def _cleartop(g, n):
    for r in range(n):
        for c in range(W): g[r][c] = 0
    return g

# ── contraction combo-glyphs (letter + edge-hugging apostrophe/dash, one cell) ───
# Catalan is dense with l'/d'/m' (proclitic), -lo/-me (enclitic) and 'n/'s (enclitic
# apos). Each is 2 cells (4B); a combo glyph makes it 1 (2B). The full-width cell has
# so much air the mark hugs an edge without crowding -- wide M/N get squeezed to fit.
def _squeeze(g, tw):
    out = [[0]*W for _ in range(ROWS)]
    for r in range(ROWS):
        for i in range(tw):
            lo = i*W//tw; hi = max(lo+1, (i+1)*W//tw)
            seg = g[r][lo:hi]
            if seg: out[r][i] = max(seg)
    return out
def _apos_r(g, sq):             # apostrophe (comma) hugging the RIGHT edge
    if sq: g = _squeeze(g, 15); c0 = 16
    else:  c0 = 17
    for r, c in ((0,c0+1),(0,c0+2),(1,c0+1),(1,c0+2),(2,c0+2),(3,c0+1)):
        if c < W: g[r][c] = 3
    return g
def _apos_l(g):                 # apostrophe hugging the LEFT edge
    for r, c in ((0,0),(0,1),(1,0),(1,1),(2,1),(3,0)): g[r][c] = 3
    return g
def _dash_l(g):                 # dash bar hugging the LEFT edge, mid-row
    for c in range(0,5): g[9][c] = 3; g[10][c] = 3
    return g
def _basejis(ch):
    up = ch.isupper(); o = ord(ch)
    return (0x23, (0x41 if up else 0x61) + o - (ord('A') if up else ord('a')))

# composition glyphs: two letters/marks evenly set in one cell (menu Sí/No, and ?!)
def _crop(g):
    cols = [c for c in range(W) if any(g[r][c] for r in range(ROWS))]
    lo, hi = (min(cols), max(cols)) if cols else (0, 0)
    return [[g[r][c] for c in range(lo, hi + 1)] for r in range(ROWS)], hi - lo + 1
def _resize(g, tw):
    src, sw = _crop(g)
    return [[src[r][c * sw // tw] for c in range(tw)] for r in range(ROWS)]
def _glyph(data, shi, slo):
    jhi, jlo = sjis2jis(shi, slo)
    return decode(bytearray(data[jis_index(jhi, jlo) * STRIDE:][:STRIDE]))
def _compose(lg, rg, lw=None, rw=None):
    lw = lw or _crop(lg)[1]; rw = rw or _crop(rg)[1]
    L = _resize(lg, lw); R = _resize(rg, rw); gap = max(1, (W - lw - rw) // 3)
    out = [[0]*W for _ in range(ROWS)]
    for r in range(ROWS):
        for c in range(lw):
            if gap + c < W: out[r][gap + c] = L[r][c]
        for c in range(rw):
            if gap + lw + gap + c < W: out[r][gap + lw + gap + c] = R[r][c]
    return out

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

# contraction sequence -> (base letter, kind). kind: r=apos-right, rq=apos-right-squeezed
# (wide M/N), al=apos-left, dl=dash-left. Authored into the FREE Greek slots after accents.
_CSPEC = [
 ("l'",'l','r'), ("L'",'L','r'), ("d'",'d','r'), ("D'",'D','r'),
 ("s'",'s','r'), ("S'",'S','r'), ("t'",'t','r'), ("T'",'T','r'),
 ("m'",'m','rq'),("M'",'M','rq'),("n'",'n','rq'),("N'",'N','rq'),
 ("-l",'l','dl'),("-m",'m','dl'),("-t",'t','dl'),("-s",'s','dl'),
 ("-n",'n','dl'),("-h",'h','dl'),("-v",'v','dl'),
 ("'l",'l','al'),("'n",'n','al'),("'s",'s','al'),("'t",'t','al'),("'m",'m','al'),
]
# free Greek codes (accents use 0x9F-0xA8 + 0xBF-0xC9); 0xA9-0xBE and 0xCA-0xD6 are spare
_FREE  = [0x8300 | x for x in list(range(0xA9,0xBF)) + list(range(0xCA,0xD7))]
_CSLOT = {seq: _FREE[i] for i, (seq, _, _) in enumerate(_CSPEC)}

# two-letter composition glyphs: (name, left SJIS, right SJIS, left width, right width)
_COMPOSE = [
 ("no", 0x828e, 0x828f, 8, 9),     # n + o, evenly set
 ("sí", 0x8293, 0x83C2, None, None),   # s + authored í, natural widths
 ("?!", 0x8148, 0x8149, None, None),   # ? + !, one glyph for both orders
]
_OSLOT = {name: _FREE[len(_CSPEC) + i] for i, (name, *_) in enumerate(_COMPOSE)}
_CSLOT["?!"] = _CSLOT["!?"] = _OSLOT["?!"]   # interrobang both orders -> the one glyph
# menu-only Sí/No: only ever in the A:sí / B:no button pattern, so prose sí/no stays normal
_MENU = {"A:sí": (0x8260, 0x8146, _OSLOT["sí"]),
         "B:no": (0x8261, 0x8146, _OSLOT["no"])}

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
    # contraction combo-glyphs into the free Greek slots
    for seq, ch, kind in _CSPEC:
        bhi, blo = _basejis(ch)
        g = decode(bytearray(data[jis_index(bhi,blo)*STRIDE:][:STRIDE]))
        if   kind == 'r':  g = _apos_r(g, False)
        elif kind == 'rq': g = _apos_r(g, True)
        elif kind == 'al': g = _apos_l(g)
        elif kind == 'dl': g = _dash_l(g)
        rec = bytearray(data[jis_index(bhi,blo)*STRIDE:][:STRIDE])   # borrow base header
        rec[BMP:BMP+ROWS*BPR] = encode(g)
        code = _CSLOT[seq]; jhi, jlo = sjis2jis(code >> 8, code & 0xFF)
        rec[0], rec[1] = jlo, jhi
        off = jis_index(jhi, jlo)*STRIDE; data[off:off+STRIDE] = rec
    # two-letter composition glyphs (menu Sí/No, ?!) into the next free slots
    for name, lsj, rsj, lw, rw in _COMPOSE:
        g = _compose(_glyph(data, lsj >> 8, lsj & 0xFF),
                     _glyph(data, rsj >> 8, rsj & 0xFF), lw, rw)
        rec = bytearray(data[jis_index(0x23, 0x61)*STRIDE:][:STRIDE])   # borrow 'a' header
        rec[BMP:BMP+ROWS*BPR] = encode(g)
        code = _OSLOT[name]; jhi, jlo = sjis2jis(code >> 8, code & 0xFF)
        rec[0], rec[1] = jlo, jhi
        off = jis_index(jhi, jlo)*STRIDE; data[off:off+STRIDE] = rec
    return bytes(data)

# ── text encoder: Catalan -> full-width / Greek-slot SJIS (codec-free) ──────────
_PUNCT = {" ":0x8140, ".":0x8144, ",":0x8143, "!":0x8149, "?":0x8148,
         ":":0x8146, ";":0x8147, "(":0x8169, ")":0x816a, "'":0x8166, "’":0x8166,
         "…":0x8163}   # full-width ellipsis the JP already uses: "..." (6B) -> "…" (2B)
_ACCENTS = {ch: (shi<<8)|slo for ch,(_,_,_,_,shi,slo) in ACCENT_SPEC.items()}
_ACCENTS["-"] = 0x83C9   # authored hyphen (enclitics: Ves-te'n, ajudar-lo)

def fw(s):
    """Catalan text -> Shift-JIS bytes the patched font renders (accents + contractions)."""
    s = s.replace("l·l","ll").replace("L·L","LL").replace("·","")   # no middot glyph yet
    s = s.replace("’", "'")                                     # curly apostrophe -> straight
    o = bytearray(); i = 0; n = len(s)
    while i < n:
        four = s[i:i+4]
        if four in _MENU:       # menu A:sí / B:no -> A/B, colon, then the sí/no glyph
            for code in _MENU[four]: o += code.to_bytes(2,"big")
            i += 4; continue
        two = s[i:i+2]
        if two in _CSLOT:       # contraction or ?! combo -> one glyph, 2B not 4B
            o += _CSLOT[two].to_bytes(2,"big"); i += 2; continue
        ch = s[i]; c = ord(ch)
        if ch in _ACCENTS:      o += _ACCENTS[ch].to_bytes(2,"big")
        elif 0x41 <= c <= 0x5a: o += (0x8260+c-0x41).to_bytes(2,"big")
        elif 0x61 <= c <= 0x7a: o += (0x8281+c-0x61).to_bytes(2,"big")
        elif 0x30 <= c <= 0x39: o += (0x824f+c-0x30).to_bytes(2,"big")
        elif ch in _PUNCT:      o += _PUNCT[ch].to_bytes(2,"big")
        else: raise ValueError("no full-width glyph for %r" % ch)
        i += 1
    return bytes(o)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: fon_codec.py <orig.FON> <patched.FON>"); sys.exit(1)
    out = build_patched_font(open(sys.argv[1], "rb").read())
    open(sys.argv[2], "wb").write(out)
    print("wrote %s (%d accent glyphs in Greek slots)" % (sys.argv[2], len(ACCENT_SPEC)))
