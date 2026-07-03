#!/usr/bin/env python3
"""Repaint the INFO / records screen text atlas `INFO/JYOU_00.PVR` -> Catalan.

The 256x256 ARGB4444 atlas is a SPRITE SHEET: the game blits each label from its own
sub-rect onto the records screen (title, stat labels, unit suffixes, buttons). We repaint
each label WITHIN its original bbox (the rect the game samples), so whatever UV the engine
uses, the Catalan lands where the Japanese was -- erase the glyphs (alpha, transparent bg)
and redraw fitted to that box in the label's own colour + a dark outline. Digits 0-9 and the
`%` glyph are kept byte-for-byte.

Units (year/month/week/count suffixes) sit in ~20px-wide, 24px-tall slots flush against the
numbers; there's no horizontal room for a Catalan word, so they're STACKED vertically
(any/dia/mes/setm) -- the tall-narrow slot fits ~3-4 short letters top-to-bottom.

    repaint_jyou.py <in-JYOU_00.PVR> <out-JYOU_00.PVR>
"""
import sys, os, struct, re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))  # dc/ codecs
import pvr_codec as pv
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ARIAL = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
OUTLINE = (12, 12, 12)

# Horizontal labels: (x0, y0, x1, y1) = the ORIGINAL glyphs' box (erased whole, so no old pixels
# survive), fill colour, Catalan text. The word is centred in the box and fitted with a margin so it
# never touches an edge. Boxes come from measuring each JP word's true extent (the two columns don't
# split at a fixed x -- おかたづけ runs much wider than the other left labels).
LABELS = [
    ((5, 48, 91, 72),    (68, 204, 119), "Escena"),      # シナリオ
    ((99, 48, 188, 72),  (170, 90, 140), "Encerts"),     # せいこう (success count)
    ((7, 72, 90, 96),    (17, 238, 119), "Pastissets"),  # ドラやき
    ((100, 72, 164, 96), (185, 110, 160), "i mig"),      # と半分
    ((5, 96, 91, 120),   (34, 238, 119), "Encàrrecs"),   # お手伝い
    ((100, 96, 187, 120),(170, 110, 160), "Rècord"),     # さいこう (highest)
    ((5, 120, 90, 144),  (17, 221, 221), "Massatges"),   # 肩たたき
    ((101, 120, 186, 144),(17, 229, 229), "Escardar"),   # 草むしり
    ((4, 144, 116, 168), (17, 238, 238), "Endreçar"),    # おかたづけ (runs to x116)
    ((124, 144, 211, 168),(150, 110, 165), "Errades"),   # しっぱい (starts at x124)
    ((3, 216, 68, 240),  (200, 70, 45),  "Enrere"),      # もどる
    ((75, 216, 140, 240),(200, 65, 30),  "Secret"),      # ヒミツ (true box = same width as もどる)
]

# The big green title. Rendered larger with a thicker outline, centred in its band.
TITLE = ((8, 170, 233, 215), (90, 200, 45), "Info")     # じょうほう

# Unit suffixes: (x0, y0, x1, y1), text, orientation ('h' horizontal | 'v' stacked). The slot is inset
# vertically so it doesn't crowd the digit row above. `年目` ("Nth year") is ONE concept, not two units,
# so it collapses to a single "any" spanning both original glyph slots (x1-45) and is drawn horizontally.
# The lone month/week glyphs (月→mes, 週→setm) keep their narrow single slot, so they stay stacked.
UNIT_PINK = (210, 90, 125)
UNIT_INSET = 3
UNITS = [
    ((1, 24, 45, 48),    "any",  'h'),   # 年目 -> one word, both slots
    ((51, 24, 69, 48),   "mes",  'v'),   # 月
    ((73, 24, 95, 48),   "setm", 'v'),   # 週
    ((98, 24, 119, 48),  "#",    'h'),   # 回
    ((121, 24, 143, 48), "U",    'h'),   # 個 (uppercase: no descender, sits centred cleanly)
    ((145, 24, 167, 48), "P",    'h'),   # 点
    # % (x170-191) kept as-is
]


def fit(text, maxw, maxh, hi=34, lo=7):
    for sz in range(hi, lo - 1, -1):
        f = ImageFont.truetype(ARIAL, sz)
        l, t, r, b = f.getbbox(text)
        if (r - l) <= maxw and (b - t) <= maxh:
            return sz
    return lo


def draw_outlined(im, cx, cy, text, size, fill, ow=1):
    """Draw `text` centred at (cx, cy) with a dark outline of half-width `ow`."""
    f = ImageFont.truetype(ARIAL, size)
    l, t, r, b = f.getbbox(text)
    tw, th = r - l, b - t
    pad = ow + 2
    tmp = Image.new("RGBA", (tw + 2 * pad, th + 2 * pad), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    ox, oy = pad - l, pad - t
    for dx in range(-ow, ow + 1):
        for dy in range(-ow, ow + 1):
            if dx or dy:
                td.text((ox + dx, oy + dy), text, font=f, fill=OUTLINE + (255,))
    td.text((ox, oy), text, font=f, fill=tuple(fill) + (255,))
    im.alpha_composite(tmp, (int(cx - tmp.width / 2), int(cy - tmp.height / 2)))


def draw_stack(im, box, letters, fill):
    """Stack single letters top-to-bottom, each fitted to the slot width, filling the height."""
    x0, y0, x1, y1 = box
    sw, sh = x1 - x0, y1 - y0
    n = len(letters)
    cellh = sh / n
    # one size for all letters: fit the widest letter to slot width and a letter to the cell height
    size = min(fit("W", sw - 1, cellh + 2, hi=20), fit(max(letters, key=len), sw - 1, cellh + 2, hi=20))
    for i, ch in enumerate(letters):
        cy = y0 + cellh * (i + 0.5)
        draw_outlined(im, (x0 + x1) / 2, cy, ch, size, fill, ow=1)


def build(d):
    off = [m.start() for m in re.finditer(b"PVRT", d)][0]
    W, H = struct.unpack_from("<HH", d, off + 12)
    arr = pv.decode_argb4444(d, off + 16, W, H)

    # erase every region we repaint (transparent atlas bg). Label rows + the title band are erased
    # FULL-WIDTH (we redraw both words in each), so no sliver of the old glyphs can survive at a box
    # edge. The units row is erased per-slot to spare the kept `%` glyph. Digits row is untouched.
    LABEL_BANDS = sorted({(y0, y1) for (_x0, y0, _x1, y1), _c, _t in LABELS})
    for (y0, y1) in LABEL_BANDS:
        arr[y0:y1, :, 3] = 0
    tx0, ty0, tx1, ty1 = TITLE[0]
    arr[ty0:ty1, :, 3] = 0
    for (x0, y0, x1, y1), _t, _o in UNITS:
        arr[y0:y1, x0:x1, 3] = 0
    arr[24:48, 27:45, 3] = 0   # also erase the old 目 slot (folded into "any", no glyph now)

    im = Image.fromarray(arr, "RGBA")

    MARGIN = 5   # keep the word off the box edges
    for (x0, y0, x1, y1), fill, text in LABELS:
        size = fit(text, (x1 - x0) - 2 * MARGIN, (y1 - y0) - 4)
        draw_outlined(im, (x0 + x1) / 2, (y0 + y1) / 2, text, size, fill, ow=1)

    # title: bigger, thicker outline
    (x0, y0, x1, y1), tfill, ttext = TITLE
    tsize = fit(ttext, (x1 - x0) - 4, (y1 - y0) - 4, hi=52)
    draw_outlined(im, (x0 + x1) / 2, (y0 + y1) / 2, ttext, tsize, tfill, ow=2)

    for (x0, y0, x1, y1), text, orient in UNITS:
        box = (x0, y0 + UNIT_INSET, x1, y1 - UNIT_INSET)   # inset so it clears the digit row
        if orient == 'h':
            size = fit(text, (x1 - x0) - 2, (box[3] - box[1]), hi=22)
            draw_outlined(im, (x0 + x1) / 2, (box[1] + box[3]) / 2, text, size, UNIT_PINK, ow=1)
        else:
            draw_stack(im, box, list(text), UNIT_PINK)

    enc = pv.encode_argb4444(np.array(im))
    assert len(enc) == W * H * 2, (len(enc), W * H * 2)
    out = bytearray(d)
    out[off + 16: off + 16 + len(enc)] = enc
    return bytes(out)


def main():
    src, out = sys.argv[1], sys.argv[2]
    d = open(src, "rb").read()
    patched = build(d)
    assert len(patched) == len(d), (len(patched), len(d))
    open(out, "wb").write(patched)
    print("wrote %s (%d B, same size)" % (out, len(patched)))


if __name__ == "__main__":
    main()
