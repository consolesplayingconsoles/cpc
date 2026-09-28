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
def _balance(g, mark_col=16):
    """Sit the letter so the gap BEFORE it matches the gap between it and its mark.

    The first version pushed the letter as far left as it would go (ink ending at col 13), which
    left 4 px of left bearing and only 2 px before the mark: the operator read that as lopsided on
    hardware ("balance both sides to be similarly wide"). Sharing the slack evenly gives 3 px and
    3 px for a 10 px letter, and keeps the >= 2 px of clearance the 2bpp blit needs.
    """
    cols = [c for c in range(W) if any(g[r][c] for r in range(ROWS))]
    if not cols:
        return g
    lo, hi = min(cols), max(cols)
    lpad = max(0, (mark_col - (hi - lo + 1)) // 2)
    shift = lo - lpad
    if shift > 0:
        return [row[shift:] + [0] * shift for row in g]
    if shift < 0:
        return [[0] * (-shift) + row[:W + shift] for row in g]
    return g


# The apostrophe hung on the letter's own SHOULDER, the letter untouched.
# The operator's read, and it is the right one: there is empty space between the letter and the mark,
# so close the gap instead of moving (or squeezing) the letter. An apostrophe sits at cap height
# (rows 0-4) and a lowercase body at x-height (rows 6-17), so the two never share a row and the mark
# can hang anywhere along the top. It is anchored one column in from THAT letter's right edge, so it
# follows the letter's width (narrow `i` gets it at 13-15, round `e` at 17-19) instead of parking at
# the cell edge, where it read as belonging to the next letter. Nothing moves: the letter keeps its
# full width AND its normal 8 px spacing either side.
def _apos_px(lo, wide=True):
    if wide:
        return [(0, lo), (0, lo + 1), (0, lo + 2), (1, lo), (1, lo + 1), (1, lo + 2),
                (2, lo), (2, lo + 1), (2, lo + 2), (3, lo + 1), (4, lo)]
    return [(0, lo), (0, lo + 1), (1, lo), (1, lo + 1), (2, lo), (2, lo + 1), (3, lo + 1), (4, lo)]


_PX_APOS_C3 = _apos_px(17)          # the widest letters end up here; kept as names for the tests
_PX_APOS_C2 = _apos_px(18, False)


def _apos_corner(g):
    """Hang the apostrophe just PAST the letter's right edge, never above it.

    Anchored at the letter's right edge + 1, so it never sits on top of a stroke ("u' the apostrophe
    is right over the right part of u"), and the letter is nudged left by at most 2 px if that is
    what it takes to fit the 3 px wide mark. Cap height vs x-height means they never share a row, so
    nothing here can collide; this is purely about where the eye reads the mark.
    """
    body = [c for c in range(W) if any(g[r][c] for r in range(6, ROWS))]
    if not body:
        return None
    for wide in (True, False):              # a 3 px mark first, and only then the narrow one
        for shift in (0, 1, 2):             # nudging the letter at most 2 px to make room for it
            moved = [row[shift:] + [0] * shift for row in g] if shift else [row[:] for row in g]
            right = max(c for c in range(W) if any(moved[r][c] for r in range(6, ROWS)))
            px = _apos_px(right + 1, wide)
            if max(c for _, c in px) <= W - 1 and not any(moved[r][c] for r, c in px):
                for r, c in px:
                    moved[r][c] = 3
                return moved
    return None


def _apos_r(g, sq):             # BOLD apostrophe, RIGHT edge.
    """The letter is MOVED when it fits, and only squeezed when it cannot be.

    It used to squeeze every letter to 14 columns so a right-ascender (d, b) could not merge with
    the mark. The price was a thinned letter: `a` went from 12 px to 9 and read as a lighter, oddly
    isolated glyph between its neighbour and the mark ("Grandpa'?"), and `n` the same. Moving keeps
    every pixel, and the 2-column clearance still guards the ascenders, so only the letters too wide
    to move (m at 14 px, w at 20) take the squeeze now.
    """
    corner = _apos_corner(g)                        # best case: nothing moves at all
    if corner is not None:
        return corner
    cols = [c for c in range(W) if any(g[r][c] for r in range(ROWS))]
    if cols and max(cols) - min(cols) + 1 <= 12:     # else move it, every stroke intact
        return _mark_r(g, _PX_APOS)
    g = _squeeze(g, 14)         # too wide to move (m, w): squeeze, as before; 3px solid
    # M's base has a thin col-0 left serif set apart from its main stroke; the squeeze strands it as a
    # floating "|" ghost. If col 0 is inked but cols 1-2 are empty, that's the orphan serif -> drop it.
    if any(g[r][0] for r in range(ROWS)) and not any(g[r][1] or g[r][2] for r in range(ROWS)):
        for r in range(ROWS): g[r][0] = 0
    g = _balance(g)                            # even gaps either side of the letter, as with the marks
    for r, c in ((0,16),(0,17),(0,18),(1,16),(1,17),(1,18),   # (thin marks vanish in the game's blit).
                 (2,16),(2,17),(2,18),(3,17),(4,16)):
        if 0 <= c < W: g[r][c] = 3
    return g
# ── right-edge one-cell marks ──────────────────────────────────────────────
# A trailing mark in its own cell costs 2B. Hung off the preceding letter it costs nothing.
# Every mark below uses the SAME geometry: the letter is moved left to end by col 13 (see
# `_mark_r`), leaving cols 14-15 blank and 16-18 for the mark. Because the letter is moved and
# never scaled, even a full-height mark like `!` fits without touching a stroke.
# All pixels are level 3 (solid): the game's 2bpp blit eats thin or anti-aliased marks.
_PX_DOT   = [(r, c) for r in (16, 17, 18) for c in (16, 17, 18)]
# The comma stays inside cols 16-18 like the other marks. An earlier version let its tail reach
# col 15, which left only ONE blank column before the letter -- and a 1 px gap is what the game's
# 2bpp blit merges. Two columns of clearance on every mark, no exceptions.
_PX_COMMA = ([(r, c) for r in (14, 15, 16) for c in (16, 17, 18)]
             + [(17, 16), (17, 17), (17, 18), (18, 16), (18, 17)])        # body + descending tail
_PX_BANG  = ([(r, c) for r in range(3, 14) for c in (16, 17, 18)]
             + [(r, c) for r in (16, 17, 18) for c in (16, 17, 18)])      # stem, gap at 14-15, dot
# The apostrophe as a MOVED mark (kind 'rm'), for letters narrow enough not to need the squeeze:
# same shape `_apos_r` draws, but the letter keeps every pixel and `_balance` places it. `I` is 8 px
# wide, so squeezing it to 14 columns thinned its stem to 1 px -- the operator asked for a wider I
# and a smaller gap, and moving gives both.
_PX_APOS = ([(r, c) for r in (0, 1, 2) for c in (16, 17, 18)] + [(3, 17), (4, 16)])
_MARKS = {".": _PX_DOT, ",": _PX_COMMA, "!": _PX_BANG, "'": _PX_APOS}


# ── marks hung in the letter's own bottom-right corner ──────────────────────────
# Same idea as the apostrophe's shoulder, and for the same reason: a combo that MOVES the letter
# steals from the gap to the letter before it ("u, not quite yet", "n in soon"). A 2 px mark in
# columns 18-19 fits without touching the letter on 22 of the 26 letters for `.` and `,` (a g k m
# collide: their bowl or descender reaches the corner) and on 16 for the full-height `!`.
# Everything else falls back to the moved-and-balanced version below.
_PX_DOT_C   = [(r, c) for r in (16, 17, 18) for c in (18, 19)]
_PX_COMMA_C = [(r, c) for r in (15, 16, 17) for c in (18, 19)] + [(18, 18)]
_PX_BANG_C  = ([(r, c) for r in range(3, 14) for c in (18, 19)]
               + [(r, c) for r in (16, 17, 18) for c in (18, 19)])
_MARKS_CORNER = {".": _PX_DOT_C, ",": _PX_COMMA_C, "!": _PX_BANG_C}


_MARK_AIR = 3       # px between the letter and a hung mark. At 0 (the mark flush against the letter)
                    # the operator read every one of them as cramped: "e." "n." "n," "u," "u." "y!".


def _mark_corner(g, kind):
    """Hang the mark at columns 18-19 with `_MARK_AIR` px of daylight before it.

    The letter is nudged left only as far as that daylight needs -- 2-3 px, against the 4-5 px the
    old 16-18 placement cost -- so it keeps 5-6 px of left bearing instead of 3. Returns `None` when
    the letter's own ink is in the corner (a g k m w, and the taller `!` on b e o p v): those fall
    back to the moved-and-balanced version.
    """
    px = _MARKS_CORNER.get(kind)
    if px is None or any(g[r][c] for r, c in px):
        return None
    cols = [c for c in range(W) if any(g[r][c] for r in range(ROWS))]
    if not cols:
        return None
    shift = max(0, max(cols) - (min(c for _, c in px) - 1 - _MARK_AIR))
    if shift:
        if min(cols) - shift < 1:                       # would run off the left edge: leave it
            return None
        g = [row[shift:] + [0] * shift for row in g]
        if any(g[r][c] for r, c in px):                 # the shift moved ink INTO the corner
            return None
    out = [row[:] for row in g]
    for r, c in px:
        out[r][c] = 3
    return out


def _period_r(g, px=None):
    """BOLD mark, RIGHT edge -- MOVING the letter instead of scaling it. `px` picks the mark
    (default the period); see `_MARKS`.

    A terminal "." is the commonest thing at the end of a line in both languages, and as its own
    cell it costs 2B. Hung off the preceding letter it costs nothing, so punctuation stops competing
    with the box budget.

    `_apos_r` squeezes 20->14 because an ascender can reach the top-right corner where its mark
    goes. A BASELINE dot has no such problem, and lowercase glyphs are only 10-12 px wide inside a
    20 px cell (7-8 px of left bearing), so shifting the whole cell left clears the dot with every
    stroke intact. The operator's hardware-QA read of the squeezed version -- b badly damaged, c/n/u
    visibly so -- is exactly the 0.7x downscale merging 2 px strokes into 1, the same failure that
    needed the o/e fudge. Moving instead of scaling removes the cause, so there is no fudge here.

    `m` (14 px) and `w` (20 px) are too wide to move, so they would hit the squeeze branch below --
    and the operator rejected squeezed glyphs on hardware. They are excluded from every mark set
    instead (see `_MARK_SKIP`), so NO shipped combo is scaled: the branch is kept only as a guard.
    The letter always ends by col 13, leaving cols 14-15 blank and the mark in 16-18.
    """
    cols = [c for c in range(W) if any(g[r][c] for r in range(ROWS))]
    lo, hi = (min(cols), max(cols)) if cols else (0, W - 1)
    if hi - lo + 1 <= 14:                               # fits: place it with even gaps either side
        g = _balance(g)
    else:                                               # unreachable for the shipped sets (see _MARK_SKIP)
        g = _squeeze(g, 14)
        if any(g[r][0] for r in range(ROWS)) and not any(g[r][1] or g[r][2] for r in range(ROWS)):
            for r in range(ROWS): g[r][0] = 0           # same orphan-serif drop as _apos_r
    for r, c in (px or _PX_DOT):
        g[r][c] = 3
    return g


_mark_r = _period_r        # the general name; `_period_r` is kept for the tests that use it


def _bold_bang_right(g):
    """Redraw the `!` half of the ?!/!? cell 3 px wide, like every mark we author ourselves.

    The stock `!` is a 2 px stem. On its own that reads fine, but pressed against the fat `?` in one
    cell the operator read it as a hairline ("very narrow !"). Our letter+mark combos all use a 3 px
    solid mark for exactly this reason (the 2bpp blit eats thin strokes), so the interrobang matches
    them now instead of the stock glyph.
    """
    for r in range(ROWS):
        for c in range(14, W):
            g[r][c] = 0
    for r in range(2, 14):                      # stem, same rows as the stock bang
        for c in (15, 16, 17):
            g[r][c] = 3
    for r in (15, 16, 17):                      # the dot
        for c in (15, 16, 17):
            g[r][c] = 3
    return g


def _author_dot(data, prof=None):
    """Redraw the full stop in every `<letter>.` cell as a squat block (ENGLISH ONLY).

    The stock font's period is a round five-row blob and its comma is that same blob with a tail,
    so at CRT resolution `e.` and `g.` read as commas -- and `.'` at the end of a quote read as the
    American comma-inside-the-quote. The shapes themselves (`_PX_DOT`, `_PX_DOT_C`) are shared with
    Catalan, whose font is byte-identical by contract and must not drift, so this runs as an English
    author pass over the built glyphs instead of changing the marks for both languages.

    Only the MARK's own columns are touched: scan in from the right edge to the blank column that
    `_MARK_AIR` guarantees, so a descender (g p q y) keeps every pixel."""
    if prof is None:
        return data
    # The STANDALONE period first. Letters with no `<letter>.` combo (e, g, and every letter after
    # a space or a digit) fall back to this stock glyph, so leaving it round means `e.` and `g.`
    # still read as commas however many combos get fixed.
    g = _glyph(data, 0x81, 0x44)
    ink = [(r, c) for r in range(ROWS) for c in range(W) if g[r][c]]
    if ink:
        left = min(c for _, c in ink)
        for r, c in ink:
            g[r][c] = 0
        for r in (17, 18):
            for c in range(left, min(left + 3, W)):
                g[r][c] = 3
        off = jis_index(*sjis2jis(0x81, 0x44)) * STRIDE
        rec = bytearray(data[off:off + STRIDE])
        rec[BMP:BMP + ROWS * BPR] = encode(g)
        data[off:off + STRIDE] = rec
    for seq, code in sorted(prof.cslot.items()):
        if not seq.endswith(".") or len(seq) != 2:
            continue
        jhi, jlo = sjis2jis(code >> 8, code & 0xFF)
        off = jis_index(jhi, jlo) * STRIDE
        g = _glyph(data, code >> 8, code & 0xFF)
        right = max((c for c in range(W) if any(g[r][c] for r in range(12, ROWS))), default=-1)
        if right < 0:
            continue
        left = right
        while left > 0 and any(g[r][left - 1] for r in range(12, ROWS)):
            left -= 1
        if right - left + 1 > 4:          # that is the letter, not a hung mark: leave it alone
            continue
        for r in range(12, ROWS):
            for c in range(left, right + 1):
                g[r][c] = 0
        for r in (17, 18):
            for c in range(left, right + 1):
                g[r][c] = 3
        rec = bytearray(data[off:off + STRIDE])
        rec[BMP:BMP + ROWS * BPR] = encode(g)
        data[off:off + STRIDE] = rec
    return data


def _dot_left(g):
    """The LEFT mark of `.'`, redrawn as a compact solid full stop.

    Same trap as the bangs, the other way round: the stock font's period is a five-row round blob
    and its comma is that same blob with a tail, so composed into `.'` and `,'` the two cells are
    all but identical. On a CRT the operator read `wonderful.'` as `wonderful,'` and reported the
    comma as being inside the quote -- the text was right, the glyph was lying. A squat two-row
    block sits on the baseline and cannot be mistaken for the comma's descending taper."""
    cols = [c for c in range(W) if any(g[r][c] for r in range(12, ROWS))]
    if not cols:
        return g
    left = min(cols)
    for r in range(12, ROWS):
        for c in range(W):
            g[r][c] = 0
    for r in (17, 18):
        for c in range(left, min(left + 3, W)):
            g[r][c] = 3
    return g


def _bold_bang_left(g):
    """The LEFT half of `!!` / `!?`, drawn 3 px like its partner so the pair is symmetric.

    Operator on hardware: "not vertically equal !!" -- the two bangs came from different places (one
    authored by us at 3 px, one the stock 2 px hairline), so they differed in weight AND in height."""
    for r in range(ROWS):
        for c in range(0, 15):          # 14 too: the right half only clears from 14 up
            g[r][c] = 0
    for r in range(2, 14):
        for c in (5, 6, 7):
            g[r][c] = 3
    for r in (15, 16, 17):
        for c in (5, 6, 7):
            g[r][c] = 3
    return g


def _basejis(ch):
    up = ch.isupper(); o = ord(ch)
    return (0x23, (0x41 if up else 0x61) + o - (ord('A') if up else ord('a')))

_MIN_LEFT = 3   # no composed glyph may start left of this: at column 2 the `i` of `it` vanished on
                # hardware, at column 3 it renders (proven by `li`, which has always sat there).

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
def _compose(lg, rg, lw=None, rw=None, extra=0):
    """`extra` widens the gap BETWEEN the two letters by that many px, taken from the RIGHT
    bearing: the right-hand letter moves right, the left-hand one does not move at all.

    It was paid out of the LEFT bearing first, which put the `i` of `it` at columns 2-3 instead of
    3-4 -- and on hardware that `i` DISAPPEARED ("Nobita" rendered as "Nobta"), while `li` (whose
    `l` stayed at column 3) was fine. Whatever the renderer does with the left edge of a composed
    cell, column 3 is proven and column 2 is not, so nothing composed may start left of column 3.
    `_MIN_LEFT` below enforces that for every pair."""
    lw = lw or _crop(lg)[1]; rw = rw or _crop(rg)[1]
    scaled = lw + rw + 3 > W                   # two WIDE letters don't fit -> must shrink (ugly)
    if scaled:
        sc = (W - 3) / (lw + rw)
        lw = max(1, round(lw * sc)); rw = max(1, round(rw * sc))
    L = _resize(lg, lw); R = _resize(rg, rw)
    slack = W - lw - rw
    lpad = max(_MIN_LEFT, slack // 3)          # small left gap, the rest BETWEEN the letters so the
    mid = min(slack - lpad,                    # pair reads as two letters, not one blob; `extra`
              slack - 2 * (slack // 3) + extra)   # comes out of the RIGHT bearing, never the left
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

# contraction sequence -> (base letter, kind). kind: r=apos-right, rq=apos-right-squeezed (wide
# M/N). There is NO left-edge mark: a leading apostrophe is the PRECEDING letter's right-apostrophe
# (see below). Authored into the FREE Greek slots after accents.
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

# ── <letter>. combos: the terminal period, free ─────────────────────────────────
# Both scripts were budget-stripped of terminal periods (en 2,299 restored by hand, ca ~2,500 still
# missing) because a "." costs its own 2B cell. Hung off the preceding letter with the proven
# `_apos_r` geometry it costs NOTHING, and every period already placed gives 2B back.
#
# Slots come from kana. Census (2026-09-20, both projects): of the 169 kana slots, 30 appear in NO
# Japanese that still renders after the build -- i.e. only in `jp` we replace with our own text.
# Re-run the census before adding any more; a slot that some surviving menu still uses would render
# a Latin letter inside Japanese text.
_KANA_FREE = [0x8344, 0x834D, 0x835D, 0x8363, 0x8364, 0x836B, 0x8371, 0x8388, 0x8392, 0x8396,
              0x829F, 0x82A1, 0x82A3, 0x82A5, 0x82A7, 0x82B0, 0x82B4, 0x82BA, 0x82BC, 0x82C0,
              0x82C3, 0x82CA, 0x82D2, 0x82D5, 0x82D8, 0x82DB, 0x82E1, 0x82EC, 0x82EE, 0x82EF]
# A SECOND kana pool for the comma and `!` marks (49 more cells per language). The first census
# was too strict: it counted Japanese in the DP*/Dream Passport files, which are drawn by the DP
# font, NOT S18RM04.FON (see packers/lines.py), so kana appearing only there reserves nothing here.
# Counting only the GAME-font sources leaves 163 kana that never reach the screen after a build.
# Taking the maximum would be reckless -- nullsplit keeps a line JAPANESE if it does not fit, so a
# future edit that pushes a line out would render Latin letters inside it. These are the RAREST
# candidates instead (none exceeds ~190 occurrences in the whole script), which keeps that failure
# mode both unlikely and cosmetic. Re-run the census (see the memory note) before taking more.
_KANA_FREE2 = [
    0x8346, 0x8355, 0x82c0, 0x82d5, 0x835d, 0x82a1, 0x82d8, 0x8340, 0x82a7, 0x82db,
    0x82d2, 0x8342, 0x835b, 0x82a3, 0x8378, 0x8386, 0x8348, 0x837c, 0x8347, 0x8384,
    0x82c3, 0x8382, 0x835c, 0x8353, 0x835a, 0x836d, 0x8377, 0x837a, 0x8372, 0x8373,
    0x8354, 0x8387, 0x8369, 0x8345, 0x8351, 0x8385, 0x836a, 0x82b4, 0x8366, 0x82ca,
    0x82e4, 0x8365, 0x82ac, 0x8379, 0x82e3, 0x838f, 0x8375, 0x834f, 0x836e, 0x8359,
    0x8374, 0x8370, 0x8350, 0x8376, 0x8349, 0x8352, 0x834c, 0x82ba, 0x834b, 0x82a5,
]

# t/i/l are NOT here: `t.` `i.` `l.` already exist as _CLEAN composed pairs, tested on hardware.
# Re-authoring them would burn three slots to replace proven glyphs. `t!` `i!` `l!` exist too, so
# the `!` set skips them for the same reason; the comma has no prior pairs, so it covers a-z.
_PERIOD_SKIP = set("til")
# m (14 px) and w (20 px) are the only letters too wide to MOVE, so they would fall back to the
# 20->14 squeeze -- the technique the operator rejected on hardware QA ("b is suffering a lot,
# c/n/u a bit"). Excluded from every mark rather than shipped on trust: it costs 688 B in en and
# 200 B in ca out of ~69 KB / ~56 KB of headroom, so the whole set now uses ONLY moved letters,
# every pixel intact. `m.` `w,` etc. simply render as two cells, as they do today.
_MARK_SKIP = set("mw") | set("aegovbcdkpq")
# ...and every letter too WIDE to move without colliding with the letter BEFORE it. The font sets
# its letters hard against the right of the cell (1 px right bearing, 7 px left), so the gap between
# two letters is 8 px. Hanging a mark off a letter costs `shift` px of that gap, and for a 11-12 px
# letter the shift is 4-5 px -> a 3-4 px gap, half the normal spacing: the pair reads as one word-
# blob. Operator's hardware QA flagged e. e, e! a. a, a! o, g. d! -- exactly the letters whose left
# bearing after the shift is <=3 px (a e g o v = 2 px; b c d k p q = 3 px). It cannot be tuned away:
# 7 (bearing) + 12 (letter) + 2 (clearance) + 3 (mark) = 24 px in a 20 px cell. Measuring clearance
# in the mark's own rows only was tried: `e` gains 1 px, `a` none, because the bowl is widest exactly
# where the dot sits. So they render as two cells, at 2 B each (+5,474 B in en of ~66 KB free).
# The narrow letters (f h n s u x y z r j, left bearing 4-6 px) keep their combos.
_PERIOD_LETTERS = [c for c in "abcdefghijklmnopqrstuvwxyz" if c not in _PERIOD_SKIP | _MARK_SKIP]
# One kind for every letter: `_period_r` decides per glyph whether it can be moved or must be
# squeezed. No o/e special case -- that fudge existed to survive the squeeze this avoids.
_ALPHABET = "abcdefghijklmnopqrstuvwxyz"
# (sequence, base letter, mark) for every one-cell letter+mark combo. The comma covers the whole
# alphabet -- a comma that hugs some letters and not others reads as sloppy spacing, so partial
# coverage is worse than none. `.` and `!` skip t/i/l, which already have tested composed pairs.
# Which letters carry a one-cell mark, decided by measuring against the stock font (and by the
# operator's eye on hardware, which is what each note records):
#   * `.` and `,` -- out when the corner is occupied (a g k m w: bowl or descender in columns 18-19)
#     or when making room for the mark's 3 px of air would leave under 4 px of left bearing, i.e.
#     the 12 px letters (e o v). Those two failure modes are the same complaint: a cramped pair.
#   * `!` -- also out for every ASCENDER letter (b d f h k l t): the bang is a full-height stem, and
#     beside an ascender it reads as a second stem of the letter ("h! is terrible").
# i/l/t keep their proven composed `.`/`!` pairs from _CLEAN; the comma has no prior pair.
_CORNER_MARK_SKIP = set("aegkmovw")
_CORNER_BANG_SKIP = _CORNER_MARK_SKIP | set("bdfhklt") | set("p")   # p: its descender owns the corner
_PSPEC = ([(c + ".", c, ".") for c in _ALPHABET
           if c not in _PERIOD_SKIP and c not in _CORNER_MARK_SKIP]
          + [(c + ",", c, ",") for c in _ALPHABET if c not in _CORNER_MARK_SKIP]
          + [(c + "!", c, "!") for c in _ALPHABET
             if c not in _PERIOD_SKIP and c not in _CORNER_BANG_SKIP])
# 0x83D1 is NOT free: `_author_middot` draws the l·l geminate dot there. It sits at index 29, the
# first slot the periods would take, and nothing proven lives past it, so dropping it here moves
# only the new mark glyphs. (Same class of bug as the 0x83CA/'il' clash that killed l·l once.)
_FREE = [c for c in _FREE if c != 0x83D1] + _KANA_FREE + _KANA_FREE2


def _alloc(free, taken, specs):
    """Hand each spec the next free slot no one else holds. Index arithmetic (`free[base + i]`)
    silently collides the moment a set above grows; this cannot."""
    seen = set(taken)                 # the pools overlap (the 2nd census re-lists the 1st's kana),
    out, it = {}, iter(free)          # so dedupe here or two combos silently share one glyph
    for seq, _, _ in specs:
        for code in it:
            if code not in seen:
                seen.add(code); out[seq] = code; break
        else:
            raise RuntimeError("out of free glyph slots at %r (%d of %d allocated)"
                               % (seq, len(out), len(specs)))
    return out


# (_ACCENTS is built further down, so reserve the accent codes from ACCENT_SPEC itself.)
_ACCENT_CODES = {(shi << 8) | slo for _, _, _, _, shi, slo in ACCENT_SPEC.values()}
_PSLOT = _alloc(_FREE, set(_CSLOT.values()) | set(_OSLOT.values()) | set(_CLSLOT.values())
                | _ACCENT_CODES | {0x83C9, 0x83D1, 0x8394}, _PSPEC)
_CSPEC = _CSPEC + _PSPEC              # authored by the same engine loop as the apostrophe combos
_CSLOT.update(_PSLOT)                 # and probed by the same 2-char encoder branch

# ── bespoke-bitmap extras (glyphs drawn from scratch, not composed) -- per profile ──
def _author_hyphen(data):
    # standalone hyphen (no glyph in stock font) -> Greek slot 0x83C9, mid-row bar
    rec = bytearray(data[jis_index(0x23,0x61)*STRIDE:][:STRIDE])   # borrow 'a' header
    g = [[0]*W for _ in range(ROWS)]
    for c in range(6,14): g[9][c] = 3; g[10][c] = 3
    rec[BMP:BMP+ROWS*BPR] = encode(g)
    jhi, jlo = sjis2jis(0x83, 0xC9); rec[0], rec[1] = jlo, jhi
    hoff = jis_index(jhi,jlo)*STRIDE; data[hoff:hoff+STRIDE] = rec

def _author_middot(data):
    # middot glyph (for l·l geminate) -> Greek slot 0x83D1 (NOT 0x83CA: that slot is the 'il' digraph
    # in _CLSLOT, which was overwriting the dot -> l·l rendered as an 'il' ligature, no dot). Bold 4x4
    # block: a 2px dot gets eaten by the game's 2bpp blit.
    rec = bytearray(data[jis_index(0x23,0x61)*STRIDE:][:STRIDE])   # borrow 'a' header
    g = [[0]*W for _ in range(ROWS)]
    for r in (7, 8, 9, 10):
        for c in (8, 9, 10, 11): g[r][c] = 3
    rec[BMP:BMP+ROWS*BPR] = encode(g)
    jhi, jlo = sjis2jis(0x83, 0xD1); rec[0], rec[1] = jlo, jhi
    doff = jis_index(jhi,jlo)*STRIDE; data[doff:doff+STRIDE] = rec

def _author_ellipsis(data):
    # baseline ellipsis into a cannibalised archaic-kana slot ヴ (0x8394). NOT reusing the JP ellipsis
    # 0x8163 — that one is STILL used by the game for intertitle-style Japanese, so redrawing it broke
    # those. `fw` encodes "..." -> 0x8394 (2B, 1 cell) with 3 solid dots at the BASELINE (a Latin
    # ellipsis; the JP one centres its dots mid-height so they float too high).
    ell = jis_index(*sjis2jis(0x83, 0x94)) * STRIDE
    rec = bytearray(data[ell:ell + STRIDE])
    g = [[0]*W for _ in range(ROWS)]
    for cx in (7, 11, 15):       # first dot well clear of the left edge (was clipping ~1px); last stays at 15 (proven fine)
        for r in (15, 16, 17):
            for c in (cx, cx+1, cx+2): g[r][c] = 3
    rec[BMP:BMP+ROWS*BPR] = encode(g)
    data[ell:ell + STRIDE] = rec

def _author_unwrap(data):
    """Rebuild the Latin glyphs that are WIDER than the 20 px cell, and centre them in it.

    A G M O Q V W X Y (and lowercase w) overflow the cell, and the surplus is stored wrapped into
    columns 0-2 of the SAME row -- so each of those letters carries a stray clump at its left edge.
    In ordinary text the next letter is 8 px away and you never see it; put anything close (a quote,
    a mark) and it reads as dirt.

    Simply deleting the wrap leaves the letter lopsided: M's right stem ends flush against column 19
    while its left stem sits at column 5. So instead: unwrap (the tail belongs at columns 20-22),
    measure the REAL glyph, and set it back in the cell with the SAME bearing either side. Nothing is
    redrawn -- every stroke keeps its shape, the letter just stops hanging out of its box.
    """
    for code in ([0x8260 + i for i in range(26)] + [0x8281 + i for i in range(26)]
                 + [0x824F + i for i in range(10)]):
        jhi, jlo = sjis2jis(code >> 8, code & 0xFF)
        off = jis_index(jhi, jlo) * STRIDE
        rec = bytearray(data[off:off + STRIDE])
        g = decode(bytearray(rec))
        if not any(g[r][W - 1] and any(g[r][c] for c in (0, 1, 2)) for r in range(ROWS)):
            continue                                    # fits the cell already: leave it alone
        wide = [[0] * (W + 3) for _ in range(ROWS)]      # unwrap: cols 0-2 are really 20-22
        for r in range(ROWS):
            for c in range(3, W):
                wide[r][c] = g[r][c]
            for c in range(3):
                wide[r][W + c] = g[r][c]
        cols = [c for c in range(W + 3) if any(wide[r][c] for r in range(ROWS))]
        lo, hi = min(cols), max(cols)
        wd = hi - lo + 1
        out = [[0] * W for _ in range(ROWS)]
        if wd > W:                                      # still too wide (nothing here is today)
            src = [[wide[r][c] for c in range(lo, hi + 1)] for r in range(ROWS)]
            out = _resize(src, W)
        else:
            # RIGHT-aligned, not centred: this font sets every letter against the right of its cell
            # (left bearing 6-7, right bearing 0-1), so a centred M or W sits a couple of px left of
            # its neighbours and opens a hole after it -- "What" came out as W + a canyon + "hat".
            # Ending at the same column the stock glyph ended at keeps the rhythm, and the letter is
            # whole because the wrapped tail is back on its right side.
            lpad = max(0, W - wd)
            for r in range(ROWS):
                for c in range(wd):
                    out[r][lpad + c] = wide[r][lo + c]
        rec[BMP:BMP + ROWS * BPR] = encode(out)
        data[off:off + STRIDE] = rec


def _author_quotes(open_code):
    """Single quotes that hug the word they belong to, instead of floating mid-cell.

    The game has no LEFT quote glyph, so an opening quote is the stock apostrophe (0x8166), whose
    ink sits at columns 5-7. Against a following capital that leaves a canyon ("'Grandpa'?" on
    hardware), while the closing quote rides the previous letter and hugs it -- lopsided. So:
    0x8166 is redrawn hugging the LEFT (it is only ever a closing quote after `.` `,` `!` `?`),
    and `open_code` gets the same shape hugging the RIGHT for the opening one. `_encode` picks
    between them by what precedes the quote. English only: in Catalan the same glyph does elision
    duty (`l'altre`), where centred is right.
    """
    def author(data):
        src = jis_index(*sjis2jis(0x81, 0x66)) * STRIDE
        rec = bytearray(data[src:src + STRIDE])
        g = decode(bytearray(rec))
        cols = [c for c in range(W) if any(g[r][c] for r in range(ROWS))]
        lo, hi = min(cols), max(cols)

        def solid(gg):
            # the stock apostrophe is anti-aliased; at the cell edge its level-1/2 fringe reads as
            # two grey specks against the next letter. Our authored marks are all solid level 3.
            return [[3 if v >= 2 else 0 for v in row] for row in gg]

        def moved(to_lo):
            sh = lo - to_lo
            if sh > 0:
                return [row[sh:] + [0] * sh for row in g]
            if sh < 0:
                return [[0] * (-sh) + row[:W + sh] for row in g]
            return [row[:] for row in g]

        close = bytearray(rec); close[BMP:BMP + ROWS * BPR] = encode(solid(moved(1)))
        data[src:src + STRIDE] = close                      # 0x8166 = closing quote, hugs the left
        opn = bytearray(rec)
        # Flush right (columns 16-18), so it hugs the word it opens: normal letter spacing is 8 px
        # and this leaves 8. It only became safe once `_author_unwrap` pulled the over-wide capitals
        # back inside their cells -- before that it sat next to the wrapped clump on A G M O Q V W X Y.
        opn[BMP:BMP + ROWS * BPR] = encode(solid(moved(18 - (hi - lo))))
        jhi, jlo = sjis2jis(open_code >> 8, open_code & 0xFF)
        opn[0], opn[1] = jlo, jhi
        off = jis_index(jhi, jlo) * STRIDE
        data[off:off + STRIDE] = opn
    return author


# ── text encoder: language-neutral punctuation (shared by every profile) ─────────
_PUNCT = {" ":0x8140, ".":0x8144, ",":0x8143, "!":0x8149, "?":0x8148,
         ":":0x8146, ";":0x8147, "(":0x8169, ")":0x816a, "'":0x8166, "’":0x8166, "/":0x815e,
         "%":0x8193,   # ASCII % -> the full-width ％ the JP already uses (せいかいりつ１００％)
         "…":0x8163}   # full-width ellipsis the JP already uses: "..." (6B) -> "…" (2B)
_ACCENTS = {ch: (shi<<8)|slo for ch,(_,_,_,_,shi,slo) in ACCENT_SPEC.items()}
_ACCENTS["-"] = 0x83C9   # authored hyphen (enclitics: Ves-te'n, ajudar-lo)
_ACCENTS["·"] = 0x83D1  # authored middot (geminates: l·l → col·lecció). 0x83CA is taken by 'il' digraph.


def _author_it_apos(data):
    """`it'` in ONE cell (it's / it'll / it'd -- 321 of them in the English script).

    UNPROVEN ON HARDWARE (2026-09-16): the operator's rule is that a new narrow pair must be tested
    in-game before it is trusted, because the `_compose` fit maths passes pairs that later CROP.
    What makes this one a better bet than most: `i` is 4px and `t` is 9px, so the proven `it` pair
    only inks columns 2-17 and NOTHING is squeezed -- the apostrophe lands in the free right edge at
    the same coordinates the proven `<letter>'` combos use. Clearance is one blank row (the apostrophe
    ends row 4, the t crossbar starts row 6), so a blit that bleeds vertically is the thing to watch.
    """
    g = _compose(_glyph(data, 0x82, 0x89), _glyph(data, 0x82, 0x94))   # the proven `it` pair
    for r, c in ((0,16),(0,17),(0,18),(1,16),(1,17),(1,18),
                 (2,16),(2,17),(2,18),(3,17),(4,16)):                  # same mark as _apos_r
        g[r][c] = 3
    rec = bytearray(data[jis_index(0x23, 0x61)*STRIDE:][:STRIDE])      # borrow 'a' header
    rec[BMP:BMP+ROWS*BPR] = encode(g)
    code = _EN_TRI["it'"]; jhi, jlo = sjis2jis(code >> 8, code & 0xFF)
    rec[0], rec[1] = jlo, jhi
    off = jis_index(jhi, jlo)*STRIDE; data[off:off+STRIDE] = rec

# ── language profiles: a language is DATA (glyph sets + slots + extras), the ──────
# engines below are generic over it. Adding a language NEVER edits the engines or another
# language's data. `_CA` wraps the module-level Catalan globals so the existing globals + tests
# keep working; `lang="ca"` is byte-for-byte the original (locked by test_fon_codec golden MD5s).
class _Profile:
    def __init__(self, accent_spec, cspec, cslot, compose, oslot, clean, clslot,
                 accents, extras, ellipsis_code, quote_open_code=None):
        self.accent_spec = accent_spec            # {char: (baseHi, baseLo, drawFn, clearRows, slotHi, slotLo)}
        self.cspec, self.cslot = cspec, cslot     # contraction combos + their slots
        self.compose, self.oslot = compose, oslot # two-letter composition glyphs + slots
        self.clean, self.clslot = clean, clslot   # digraph/narrow pairs + slots
        self.accents = accents                    # encoder: char -> code (accents + authored hyphen/middot)
        self.extras = extras                      # bespoke-bitmap authors (hyphen/middot/ellipsis/...)
        self.ellipsis_code = ellipsis_code        # code fw emits for "..."
        self.quote_open_code = quote_open_code    # code fw emits for an OPENING ' (None: stock)

_CA = _Profile(ACCENT_SPEC, _CSPEC, _CSLOT, _COMPOSE, _OSLOT, _CLEAN, _CLSLOT,
               _ACCENTS, [_author_unwrap, _author_hyphen, _author_middot, _author_ellipsis], 0x8394)
# ── English profile (en): base Latin A-Z/a-z is already in the stock font, so the ONLY authored ─
# glyphs are the alphabet-wide `<letter>'` right-apostrophe combos (one cell each, same proven
# technique as Catalan) -- so contractions AND possessive 's render after ANY letter -- plus the
# shared hyphen + baseline ellipsis. No accents, no digraphs, so the whole Greek block is free.
# The full alphabet is authored now; prune the unused combos against the real English text later.
_EN_WIDE = set("mnw")                        # widest lowercase letters -> squeezed right-apostrophe
# Round letters whose LEFT stroke the 20->14 squeeze merges from 2 px to 1 px, so it reads as cut
# off in-game (operator, hardware QA 2026-09-17: o' and e'). Shifting the source 1 column right before
# the squeeze changes which columns merge and keeps the plain letter's stroke weights (o 2/2, e 2/1);
# the letter moves right 1 col, the apostrophe stays put, 2 cols of gap remain. English-only kind.
_EN_SHIFT1 = set("oe")
# m and w are NOT here: at 14 px and 20 px they cannot be moved, and the squeeze thins their stems
# to 1 px ("m' still has a narrow right bar"). Nor is e: at 12 px it moves, but its bowl then sits
# 2 px from the letter before it AND 2 px from the mark, which the operator read as crowded on
# hardware ("e' is a problem", "also o'") -- a, g and v passed the same test, so they keep theirs.
# They render as the letter plus a cell holding the hug-left quote glyph: full-width letter, normal
# spacing, 2 B each. e' is 244 lines in en, m'/w' 23.
# m (14 px) and w (20 px) are excluded: their body fills the cell, so the shoulder anchor lands over
# the letter's own right leg and the mark reads as cramped ("m is not an option"). 23 lines in en;
# they render as the letter plus a cell holding the hug-left quote glyph.
_EN_APOS_SKIP = set("mw")
_EN_CSPEC = ([("I'", "I", "r")] +            # I'm / I'll / I've / I'd (the one common capital combo)
             [(chr(c) + "'", chr(c),
               "rq" if chr(c) in _EN_WIDE else ("r1" if chr(c) in _EN_SHIFT1 else "r"))
              for c in range(ord('a'), ord('z') + 1) if chr(c) not in _EN_APOS_SKIP])
# free slots for en: the whole Greek block MINUS the authored-hyphen slot (0x83C9), + kana reserve.
_EN_FREE = [c for c in range(0x839F, 0x83D7)
            if 0x40 <= (c & 0xFF) <= 0xFC and (c & 0xFF) != 0x7F and c != 0x83C9] \
           + [0x838e, 0x8390, 0x8391, 0x8395, 0x8361]
_EN_CSLOT = {seq: _EN_FREE[i] for i, (seq, _, _) in enumerate(_EN_CSPEC)}
# multi-punctuation composed into one cell (English uses !! ?! !? heavily) -> 2B not 4B.
# `!!` only. `?!` and `!?` used to be composed into one cell too, but two marks in the width of one
# left the question mark a 1 px curve beside a 3 px bar, and on a CRT it did not read at all. They
# now emit their two stock cells (2 bytes more per occurrence), which every scene has room for once
# a handful of lines drop to a single mark. `!!` is two identical bars and stays legible squeezed.
_EN_COMPOSE = [("!!", 0x8149, 0x8149, None, None)]
_EN_OSLOT = {name: _EN_FREE[len(_EN_CSPEC) + i] for i, (name, *_) in enumerate(_EN_COMPOSE)}
for _n in _EN_OSLOT:
    _EN_CSLOT[_n] = _EN_OSLOT[_n]             # encoder emits the one-cell glyph for the pair
_EN_ACCENTS = {"-": 0x83C9}                   # authored hyphen; English has no accents/middot
# Catalan's narrow pairs, REUSED VERBATIM (`_CLEAN`): each packs two glyphs into one cell (2B not 4B).
# English earns MORE from them than Catalan does -- `t.` `i.` `l!` end a huge share of lines.
# ⚠️ EXACTLY this set, never an extra pair: these eleven are the survivors of the operator's on-hardware
# testing. Others pass the `_compose` sum<=17 "fit" maths and look right in a render, then get CROPPED
# in-game. Adding one is a hardware test, not a code change.
_EN_CLSLOT = {seq: _EN_FREE[len(_EN_CSPEC) + len(_EN_COMPOSE) + i]
              for i, (seq, _, _) in enumerate(_CLEAN)}
# `it'` is THREE characters in one cell, so it cannot be a _CLEAN pair or a _CSPEC letter+apostrophe.
# It rides in cslot (which `_encode` probes for 3-char sequences first) and is drawn by an extra.
_EN_TRI = {"it'": _EN_FREE[len(_EN_CSPEC) + len(_EN_COMPOSE) + len(_CLEAN)]}
_EN_CSLOT.update(_EN_TRI)
# `<letter>.` combos, same set and same technique as Catalan (see _PSPEC). English has 2,299 periods
# already placed that stop costing a cell, plus ~1,000 lines that can now take one for free.
# 0x83D1 is reserved in BOTH profiles. English authors no middot today, so the slot is technically
# free here -- but keeping the reservation language-wide means adding the middot to en later can
# never silently overwrite a period. It sits past every proven en slot, so only periods shift.
_EN_FREE = [c for c in _EN_FREE if c != 0x83D1] + _KANA_FREE + _KANA_FREE2
_EN_PSLOT = _alloc(_EN_FREE, set(_EN_CSLOT.values()) | set(_EN_OSLOT.values())
                   | set(_EN_CLSLOT.values()) | set(_EN_ACCENTS.values())
                   | {0x83C9, 0x83D1, 0x8394}, _PSPEC)
_EN_CSPEC = _EN_CSPEC + _PSPEC
_EN_CSLOT.update(_EN_PSLOT)

# Closing punctuation + quote in ONE cell: `.'` `,'` `!'` `?'`. Without them a quoted sentence ends
# in two near-empty cells ("hello.' " reads as `. '` with a canyon between), and they are 37 lines
# in en. Composed like ?!, so the period keeps the baseline and the quote the cap height.
_EN_QUOTE_PAIRS = [(".'", 0x8144, 0x8166, None, None), (",'", 0x8143, 0x8166, None, None),
                   ("!'", 0x8149, 0x8166, None, None), ("?'", 0x8148, 0x8166, None, None)]
# these and the opening quote take the LAST free slots, via the allocator, so nothing proven moves
_EN_LAST = _alloc(_EN_FREE, set(_EN_CSLOT.values()) | set(_EN_OSLOT.values())
                  | set(_EN_CLSLOT.values()) | set(_EN_ACCENTS.values())
                  | {0x83C9, 0x83D1, 0x8394},
                  [("'open", None, None)] + [(n, None, None) for n, *_ in _EN_QUOTE_PAIRS])
_EN_QUOTE_OPEN = _EN_LAST["'open"]
_EN_COMPOSE = _EN_COMPOSE + _EN_QUOTE_PAIRS
for _n, *_ in _EN_QUOTE_PAIRS:
    _EN_OSLOT[_n] = _EN_CSLOT[_n] = _EN_LAST[_n]

_EN = _Profile({}, _EN_CSPEC, _EN_CSLOT, _EN_COMPOSE, _EN_OSLOT, _CLEAN, _EN_CLSLOT,
               _EN_ACCENTS, [_author_unwrap, _author_hyphen, _author_ellipsis, _author_it_apos,
                             _author_quotes(_EN_QUOTE_OPEN)], 0x8394, _EN_QUOTE_OPEN)
_EN.late_extras = [_author_dot]     # squat full stops; Catalan keeps the stock round one

_PROFILES = {"ca": _CA, "en": _EN}
LANGS = tuple(sorted(_PROFILES))


# ── generic engines (parameterised by a _Profile) ───────────────────────────────
def _build(src_bytes, prof):
    """Author `prof`'s glyphs into the stock font. Generic -- the language lives entirely in `prof`."""
    data = bytearray(src_bytes)
    for ch, (bhi, blo, acc, clr, shi, slo) in prof.accent_spec.items():
        rec = bytearray(data[jis_index(bhi,blo)*STRIDE:][:STRIDE])
        g = decode(rec)
        if clr: _cleartop(g, clr)
        acc(g, ch.isupper())
        rec[BMP:BMP+ROWS*BPR] = encode(g)
        jhi, jlo = sjis2jis(shi, slo)
        rec[0], rec[1] = jlo, jhi
        off = jis_index(jhi, jlo)*STRIDE
        data[off:off+STRIDE] = rec
    for author in prof.extras:                        # hyphen / middot / ellipsis (bespoke bitmaps)
        author(data)
    # contraction combo-glyphs into the free Greek slots
    for seq, ch, kind in prof.cspec:
        bhi, blo = _basejis(ch)
        g = decode(bytearray(data[jis_index(bhi,blo)*STRIDE:][:STRIDE]))
        if   kind == 'r':  g = _apos_r(g, False)
        elif kind == 'rq': g = _apos_r(g, True)
        elif kind == 'rm': g = _mark_r(g, _PX_APOS)      # moved, not squeezed (see _PX_APOS)
        elif kind == 'r1':                               # nudged right 1 col ONLY if it must move:
            g = _apos_corner(g) or _apos_r([[0] + row[:W - 1] for row in g], False)
        elif kind in _MARKS: g = _mark_corner(g, kind) or _mark_r(g, _MARKS[kind])
        rec = bytearray(data[jis_index(bhi,blo)*STRIDE:][:STRIDE])   # borrow base header
        rec[BMP:BMP+ROWS*BPR] = encode(g)
        code = prof.cslot[seq]; jhi, jlo = sjis2jis(code >> 8, code & 0xFF)
        rec[0], rec[1] = jlo, jhi
        off = jis_index(jhi, jlo)*STRIDE; data[off:off+STRIDE] = rec
    # two-letter composition glyphs (menu Sí/No, ?!) into the next free slots
    for name, lsj, rsj, lw, rw in prof.compose:
        g = _compose(_glyph(data, lsj >> 8, lsj & 0xFF),
                     _glyph(data, rsj >> 8, rsj & 0xFF), lw, rw)
        # Which END the bang is on, not merely whether the name contains one: `!?` has its bang on
        # the LEFT, and bolding the right mark there overdrew the question mark with a second bang,
        # so `!?` rendered as `!!` and the question mark was simply absent from the game.
        if name.endswith("!"):                  # "?!" and "!!"
            g = _bold_bang_right(g)             # match the 3 px marks we author (see the helper)
        if name.startswith("!"):                # "!!" and "!?"
            g = _bold_bang_left(g)
        if name.startswith("."):                # ".'" -- see the helper
            g = _dot_left(g)
        rec = bytearray(data[jis_index(0x23, 0x61)*STRIDE:][:STRIDE])   # borrow 'a' header
        rec[BMP:BMP+ROWS*BPR] = encode(g)
        code = prof.oslot[name]; jhi, jlo = sjis2jis(code >> 8, code & 0xFF)
        rec[0], rec[1] = jlo, jhi
        off = jis_index(jhi, jlo)*STRIDE; data[off:off+STRIDE] = rec
    # clean glyph pairs (digraphs + narrow pairs), composed from their two letters
    for seq, lsj, rsj in prof.clean:
        g = _compose(_glyph(data, lsj >> 8, lsj & 0xFF), _glyph(data, rsj >> 8, rsj & 0xFF),
                     extra=1 if seq.isalpha() else 0)   # digraphs get the extra px, mark pairs don't
        rec = bytearray(data[jis_index(0x23, 0x61)*STRIDE:][:STRIDE])
        rec[BMP:BMP+ROWS*BPR] = encode(g)
        code = prof.clslot[seq]; jhi, jlo = sjis2jis(code >> 8, code & 0xFF)
        rec[0], rec[1] = jlo, jhi
        off = jis_index(jhi, jlo)*STRIDE; data[off:off+STRIDE] = rec
    # LATE authors, after every combo cell exists (prof.extras runs before they are built, so a
    # pass that edits combos has to come here instead). Only English registers any.
    for author in getattr(prof, "late_extras", ()):
        author(data, prof)
    return bytes(data)

def _encode(s, prof):
    """Text -> Shift-JIS bytes the patched font renders, using `prof`'s glyph set. Generic."""
    s = s.replace("’", "’")                                     # curly apostrophe -> straight
    o = bytearray(); i = 0; n = len(s)
    while i < n:
        if s[i:i+3] == "...":   # ellipsis -> baseline-dots glyph (2B, 1 cell)
            o += prof.ellipsis_code.to_bytes(2,"big"); i += 3; continue
        three = s[i:i+3]
        if three in prof.cslot:     # 3-char one-cell glyph (en `it'`); ca has none, so ca is untouched
            o += prof.cslot[three].to_bytes(2,"big"); i += 3; continue
        two = s[i:i+2]
        if two in prof.cslot and not (two[1] == "." and s[i+2:i+3] == ".") \
                and not (two[1] == "!" and s[i+2:i+3] in ("?", "!")):
            # contraction / `<letter>.` / ?! combo -> one glyph, 2B not 4B. NOT when another dot
            # follows: "a..." must stay `a` + the ellipsis glyph, never `a.` + "..". And `<letter>!`
            # must NOT fire in front of a `?`: "sister!?" would be `r!` + `?` while "Jaiko!?" (wide
            # letter, no combo) is `o` + the composed `!?` cell -- the same two marks drawn two
            # different ways on one screen. The interrobang cell wins, always.
            o += prof.cslot[two].to_bytes(2,"big"); i += 2; continue
        if two in prof.clslot and not (two[1] == "." and s[i+2:i+3] == ".") \
                and not (s[i+2:i+3] in ("'", "\u2019") and (two[1] + "'") in prof.cslot):
            # digraph/combo -- but NOT when it would swallow the letter an apostrophe must hang off
            # ("it's": the `it` pair would leave a STANDALONE apostrophe, the bug the right-edge
            # combos exist to prevent). Let the letter stand alone so `t'` fires on the next pass.
            o += prof.clslot[two].to_bytes(2,"big"); i += 2; continue   # (and let "t..." be t+…)
        ch = s[i]; c = ord(ch)
        if ch in prof.accents:  o += prof.accents[ch].to_bytes(2,"big")
        elif 0x41 <= c <= 0x5a: o += (0x8260+c-0x41).to_bytes(2,"big")
        elif 0x61 <= c <= 0x7a: o += (0x8281+c-0x61).to_bytes(2,"big")
        elif 0x30 <= c <= 0x39: o += (0x824f+c-0x30).to_bytes(2,"big")
        elif ch == "'" and prof.quote_open_code and (i == 0 or s[i-1] in " ("):
            o += prof.quote_open_code.to_bytes(2,"big")   # OPENING quote: hugs the word after it
        elif ch in _PUNCT:      o += _PUNCT[ch].to_bytes(2,"big")
        else: o += (0x8148).to_bytes(2,"big")   # ESCAPING: any glyph-less char -> full-width ？ (never crash the encoder)
        i += 1
    return bytes(o)


# ── public API: language-selected, default Catalan (backwards-compatible) ────────
def build_patched_font(src_bytes, lang="ca"):
    """Author the patched S18RM04.FON for `lang` (default Catalan). `lang` picks the glyph profile;
    lang='ca' is byte-for-byte the original output (locked by test_fon_codec golden-MD5 tests)."""
    if lang not in _PROFILES:
        raise ValueError("no font profile for lang %r (have: %s)" % (lang, ", ".join(LANGS)))
    return _build(src_bytes, _PROFILES[lang])

def fw(s, lang="ca"):
    """Encode text -> Shift-JIS bytes the patched font renders, using `lang`'s glyph set (default ca)."""
    if lang not in _PROFILES:
        raise ValueError("no encoder for lang %r (have: %s)" % (lang, ", ".join(LANGS)))
    return _encode(s, _PROFILES[lang])


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        print("usage: fon_codec.py <orig.FON> <patched.FON> [lang=ca]"); sys.exit(1)
    lang = sys.argv[3] if len(sys.argv) == 4 else "ca"
    out = build_patched_font(open(sys.argv[1], "rb").read(), lang)
    open(sys.argv[2], "wb").write(out)
    print("wrote %s (lang=%s, %d bytes)" % (sys.argv[2], lang, len(out)))
