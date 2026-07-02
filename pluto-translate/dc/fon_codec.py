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
def _apos_r(g, sq):             # BOLD apostrophe, RIGHT edge. ALWAYS squeeze the letter to 14 cols so
    g = _squeeze(g, 14)         # a right-ascender letter (d, b) can't merge with the mark; 3px solid
    # M's base has a thin col-0 left serif set apart from its main stroke; the squeeze strands it as a
    # floating "|" ghost. If col 0 is inked but cols 1-2 are empty, that's the orphan serif -> drop it.
    if any(g[r][0] for r in range(ROWS)) and not any(g[r][1] or g[r][2] for r in range(ROWS)):
        for r in range(ROWS): g[r][0] = 0
    for r, c in ((0,16),(0,17),(0,18),(1,16),(1,17),(1,18),   # (thin marks vanish in the game's blit).
                 (2,16),(2,17),(2,18),(3,17),(4,16)):
        if 0 <= c < W: g[r][c] = 3
    return g
def _dash_l(g):                 # hyphen on the LEFT + letter shifted RIGHT so they don't overlap
    cols = [c for c in range(W) if any(g[r][c] for r in range(ROWS))]  # (old version stamped the bar
    left = min(cols) if cols else 0                                    # ON the letter -> "blah-t" garbage)
    shift = max(0, 5 - left)    # move the letter just enough to start at col 5; wide letters keep width
    out = [[0]*W for _ in range(ROWS)]
    for r in range(ROWS):
        for c in range(W):
            if g[r][c] and c + shift < W: out[r][c + shift] = g[r][c]
    for r in (8, 9, 10):        # 3px-tall solid hyphen (survives the blit) in the cleared left gap
        for c in range(0, 4): out[r][c] = 3
    return out
def _basejis(ch):
    up = ch.isupper(); o = ord(ch)
    return (0x23, (0x41 if up else 0x61) + o - (ord('A') if up else ord('a')))

# composition glyphs: two letters/marks evenly set in one cell (menu Sí/No, and ?!)
def _crop(g):
    cols = [c for c in range(W) if any(g[r][c] for r in range(ROWS))]
    lo, hi = (min(cols), max(cols)) if cols else (0, 0)
    return [[g[r][c] for c in range(lo, hi + 1)] for r in range(ROWS)], hi - lo + 1
def _resize(g, tw):
    # MAX-POOL downscale, not subsample: a subsample (src[r][c*sw//tw]) drops whole columns, so a
    # thin vertical stroke vanishes or leaves a stray dot, and the game's 2bpp blit then eats what's
    # left. Max over each column's source span keeps every stroke present.
    src, sw = _crop(g)
    out = [[0] * tw for _ in range(ROWS)]
    for r in range(ROWS):
        for c in range(tw):
            lo = c * sw // tw; hi = max(lo + 1, (c + 1) * sw // tw)
            seg = src[r][lo:hi]
            if seg: out[r][c] = max(seg)
    return out
def _glyph(data, shi, slo):
    jhi, jlo = sjis2jis(shi, slo)
    return decode(bytearray(data[jis_index(jhi, jlo) * STRIDE:][:STRIDE]))
def _compose(lg, rg, lw=None, rw=None):
    lw = lw or _crop(lg)[1]; rw = rw or _crop(rg)[1]
    scaled = lw + rw + 3 > W                   # two WIDE letters don't fit -> must shrink (ugly)
    if scaled:
        sc = (W - 3) / (lw + rw)
        lw = max(1, round(lw * sc)); rw = max(1, round(rw * sc))
    L = _resize(lg, lw); R = _resize(rg, rw)
    slack = W - lw - rw
    lpad = slack // 3                          # small left gap, the rest BETWEEN the letters so the
    mid = slack - 2 * lpad                     # pair reads as two letters, not one blob
    out = [[0]*W for _ in range(ROWS)]
    for r in range(ROWS):
        for c in range(lw):
            if lpad + c < W: out[r][lpad + c] = L[r][c]
        for c in range(rw):
            if lpad + lw + mid + c < W: out[r][lpad + lw + mid + c] = R[r][c]
    if scaled:                                 # only shrunk strokes go thin -> solidify to level-3 so
        for r in range(ROWS):                  # the 2bpp blit keeps them. Natural-fit pairs (one narrow
            for c in range(W):                 # letter) stay at full width + anti-aliased -> crisp.
                if out[r][c]: out[r][c] = 3
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
 ("s'",'s','r'), ("S'",'S','r'), ("t'",'t','r'), ("T'",'T','rq'),
 ("m'",'m','rq'),("M'",'M','rq'),("n'",'n','rq'),("N'",'N','rq'),
 # Enclitics are NOT their own glyph. This game renders a RIGHT-edge apostrophe (M'/S' work on the DC)
 # but NOT a left one -- so an enclitic's apostrophe belongs to the PRECEDING vowel as a right-apostrophe:
 # "canvia't" = canvi + a' + t. fw matches the 2-char "a'" via _CSLOT with no extra logic. Commonest
 # vowels (a't/a'm, e'n) get the two valid Greek slots first; i'/o'/u' follow.
 ("a'",'a','r'), ("e'",'e','r'), ("i'",'i','r'), ("o'",'o','r'), ("u'",'u','r'),
 # dropped the -l/-m/-t/-s/-n dash combos: "-" renders as the standalone hyphen (0x83C9) in its own cell.
]
# free Greek codes (accents use 0x9F-0xA8 + 0xBF-0xC9); 0xA9-0xBE and 0xCA-0xD6 are spare
_FREE  = ([0x8300 | x for x in list(range(0xA9,0xBF)) + list(range(0xCA,0xD7))]
          # + cannibalised near-dead katakana slots (ヮ ヰ ヱ ヵ ヂ — archaic/unused in the remaining JP,
          # verified 0 occurrences in the state's jp; safe to repurpose since the game is ~all Catalan now)
          + [0x838e, 0x8390, 0x8391, 0x8395, 0x8361])
_CSLOT = {seq: _FREE[i] for i, (seq, _, _) in enumerate(_CSPEC)}

# two-letter composition glyphs: (name, left SJIS, right SJIS, left width, right width)
_COMPOSE = [
 ("?!", 0x8148, 0x8149, None, None),   # ? + !, one glyph for both orders
]
_OSLOT = {name: _FREE[len(_CSPEC) + i] for i, (name, *_) in enumerate(_COMPOSE)}
_CSLOT["?!"] = _CSLOT["!?"] = _OSLOT["?!"]   # interrobang both orders -> the one glyph

# top-6 "clean" glyph pairs (Catalan digraphs + narrow-letter pairs, read as one unit):
# (sequence, left letter SJIS, right letter SJIS). Composed evenly like Sí/No, applied
# everywhere at encode time. Fill the LAST free Greek slots (kana reserve unlocks more).
# each pair has a NARROW letter (i=4px, l=2px) so it fits one cell WITHOUT scaling -> both letters
# keep full width + anti-aliasing = crisp (the old qu/gu/ss shrank two WIDE letters -> illegible).
# Operator-chosen set (i/l pairs that read cleanly): it ti ix ri ir li il.
_CLEAN = [
 ("it", 0x8289, 0x8294), ("ti", 0x8294, 0x8289), ("ix", 0x8289, 0x8298),
 ("li", 0x828c, 0x8289), ("il", 0x8289, 0x828c),   # dropped ri/ir (rendered like "´i")
 # narrow letter + punctuation combos (i/l/t + ! or .), into the cannibalised kana slots
 ("t!", 0x8294, 0x8149), ("i!", 0x8289, 0x8149), ("l!", 0x828c, 0x8149),
 ("t.", 0x8294, 0x8144), ("i.", 0x8289, 0x8144), ("l.", 0x828c, 0x8144),
]
_CLSLOT = {seq: _FREE[len(_CSPEC) + len(_COMPOSE) + i]
           for i, (seq, _, _) in enumerate(_CLEAN)}

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
    # clean glyph pairs (digraphs + narrow pairs), composed from their two letters
    for seq, lsj, rsj in _CLEAN:
        g = _compose(_glyph(data, lsj >> 8, lsj & 0xFF), _glyph(data, rsj >> 8, rsj & 0xFF))
        rec = bytearray(data[jis_index(0x23, 0x61)*STRIDE:][:STRIDE])
        rec[BMP:BMP+ROWS*BPR] = encode(g)
        code = _CLSLOT[seq]; jhi, jlo = sjis2jis(code >> 8, code & 0xFF)
        rec[0], rec[1] = jlo, jhi
        off = jis_index(jhi, jlo)*STRIDE; data[off:off+STRIDE] = rec
    # baseline ellipsis into a cannibalised archaic-kana slot ヴ (0x8394). NOT reusing the JP ellipsis
    # 0x8163 — that one is STILL used by the game for intertitle-style Japanese, so redrawing it broke
    # those. `fw` encodes "..." -> 0x8394 (2B, 1 cell) with 3 solid dots at the BASELINE (a Latin
    # ellipsis; the JP one centres its dots mid-height so they float too high).
    ell = jis_index(*sjis2jis(0x83, 0x94)) * STRIDE
    rec = bytearray(data[ell:ell + STRIDE])
    g = [[0]*W for _ in range(ROWS)]
    for cx in (6, 11, 16):       # nudged right 1px more so the first dot clears the left edge fully
        for r in (15, 16, 17):
            for c in (cx, cx+1, cx+2): g[r][c] = 3
    rec[BMP:BMP+ROWS*BPR] = encode(g)
    data[ell:ell + STRIDE] = rec
    return bytes(data)

# ── text encoder: Catalan -> full-width / Greek-slot SJIS (codec-free) ──────────
_PUNCT = {" ":0x8140, ".":0x8144, ",":0x8143, "!":0x8149, "?":0x8148,
         ":":0x8146, ";":0x8147, "(":0x8169, ")":0x816a, "'":0x8166, "’":0x8166, "/":0x815e,
         "%":0x8193,   # ASCII % -> the full-width ％ the JP already uses (せいかいりつ１００％)
         "…":0x8163}   # full-width ellipsis the JP already uses: "..." (6B) -> "…" (2B)
_ACCENTS = {ch: (shi<<8)|slo for ch,(_,_,_,_,shi,slo) in ACCENT_SPEC.items()}
_ACCENTS["-"] = 0x83C9   # authored hyphen (enclitics: Ves-te'n, ajudar-lo)

def fw(s):
    """Catalan text -> Shift-JIS bytes the patched font renders (accents + contractions)."""
    s = s.replace("l·l","ll").replace("L·L","LL").replace("·","")   # no middot glyph yet
    s = s.replace("’", "'")                                     # curly apostrophe -> straight
    o = bytearray(); i = 0; n = len(s)
    while i < n:
        if s[i:i+3] == "...":   # ellipsis -> baseline-dots glyph in the ヴ slot (2B, 1 cell)
            o += (0x8394).to_bytes(2,"big"); i += 3; continue
        two = s[i:i+2]
        if two in _CSLOT:       # contraction or ?! combo -> one glyph, 2B not 4B
            o += _CSLOT[two].to_bytes(2,"big"); i += 2; continue
        if two in _CLSLOT and not (two[1] == "." and s[i+2:i+3] == "."):
            o += _CLSLOT[two].to_bytes(2,"big"); i += 2; continue   # digraph/combo (but let "t..." be t+…)
        ch = s[i]; c = ord(ch)
        if ch in _ACCENTS:      o += _ACCENTS[ch].to_bytes(2,"big")
        elif 0x41 <= c <= 0x5a: o += (0x8260+c-0x41).to_bytes(2,"big")
        elif 0x61 <= c <= 0x7a: o += (0x8281+c-0x61).to_bytes(2,"big")
        elif 0x30 <= c <= 0x39: o += (0x824f+c-0x30).to_bytes(2,"big")
        elif ch in _PUNCT:      o += _PUNCT[ch].to_bytes(2,"big")
        else: o += (0x8148).to_bytes(2,"big")   # ESCAPING: any glyph-less char -> full-width ？ (never crash the encoder / byte count)
        i += 1
    return bytes(o)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: fon_codec.py <orig.FON> <patched.FON>"); sys.exit(1)
    out = build_patched_font(open(sys.argv[1], "rb").read())
    open(sys.argv[2], "wb").write(out)
    extra = len(_CSPEC) + len(_COMPOSE) + len(_CLEAN)
    print("wrote %s (%d accents + %d glyphs: contractions, ?!)"
          % (sys.argv[2], len(ACCENT_SPEC), extra))
