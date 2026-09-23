#!/usr/bin/env python3
"""Repaint the OPENING sequence's six text lines -> Catalan / English.

The intro fades up one line at a time over white:

    あのとき…  きみがいて…  今のぼくがある…    (then)  わすれない…  たくさんの思い出を…  最高のともだち…

Each line is its own 512x512 chunk inside STORYGRA.PAC, exactly like the SOD week banner, so the
same `splice_pac_chunk.py` path ships them: this writes `STORYGRA_c<index>.bin`, one per line.
FILE ORDER IS NOT DISPLAY ORDER -- see `LINES` below.

Two things differ from the other repaints:
  * the chunks are **RGB565** (pixfmt 1), not ARGB4444, so `pvr_codec.decode_rgb565` /
    `encode_rgb565`. 565 has NO alpha: the white behind the glyphs is real picture, so the erase
    paints white rather than clearing to transparent.
  * each line is one reveal of its own, so a 1:1 replacement keeps the intro's timing exactly as
    it is -- nothing here can drift out of sync with the music.

Style sampled from the original: pink fill (255,162,255), orange outline (247,150,74), glyphs
53 px tall, centred on the texture. Arial Rounded Bold is the closest match to the game's rounded
kana; one size serves the whole sequence, set by its longest line.

    repaint_opening.py <extract-dir> <out-dir> [lang=ca]
"""
import sys, os, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))  # dc/ codecs
import numpy as np
import pvr_codec as pv
from PIL import Image, ImageDraw, ImageFont

ROUNDED = "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf"
FILL, OUTLINE, BG = (255, 162, 255), (247, 150, 74), (255, 255, 255)
MAX_W = 470              # keep clear of the 512 edges; the JP longest line is 432 px
TRACK = 3                # extra px between letters: Arial Rounded sets very tight, and pink-on-white
                         # with a heavy outline closes the gaps further -- it reads as a blur without this
BAND = (190, 300)        # rows to erase: covers every line's ink (209-269) plus its soft halo

# (chunk index, display position). The reveal order is 144, 141, 142, 143, 140, 145.
LINES = [(144, 0), (141, 1), (142, 2), (143, 3), (140, 4), (145, 5)]

TEXT = {
    # No ellipses: the trailing … is a Japanese habit, it is not idiomatic in either language, and
    # each one costs width that the whole sequence pays for in font size (+5 pt en, +4 pt ca).
    "ca": ["Aleshores", "eres amb mi", "i per això sóc qui sóc",
           "mai oblidaré", "tots aquells records", "del meu millor amic"],
    # Line 3 chains off line 2 rather than restating the subject, as きみがいて -> 今のぼくがある does.
    # It is also the line that sets the size for the whole sequence: "and made me who I am" costs
    # 37 pt, "and that made me who I am" would cost 29.
    "en": ["Back then", "you were there", "and made me who I am",
           "I'll never forget", "all those memories", "of my best friend"],
}


def ink_rows(arr):
    """Rows holding glyph ink, used to keep the replacement on the original's baseline."""
    ink = np.abs(arr[:, :, :3].astype(int) - 255).sum(axis=2) > 40
    rows = np.where(ink.any(axis=1))[0]
    return int(rows[0]), int(rows[-1])


def stroke_for(size):
    """Outline thickness proportional to the glyphs: 3 px at the original 53 px height. A fixed
    3 px at a small size swallows the counters of a/e/o and the line turns into a smear."""
    return max(1, int(round(size / 18.0)))


def measure(font, text, track, stroke):
    """Width of `text` drawn letter by letter with `track` px between letters."""
    w = 0
    for ch in text:
        w += font.getlength(ch) + track
    return int(round(w - track)) + 2 * stroke


def draw_tracked(d, x, y, text, font, track, fill, stroke, outline):
    """PIL has no letter-spacing, so place each glyph itself."""
    for ch in text:
        d.text((x, y), ch, font=font, fill=fill, stroke_width=stroke, stroke_fill=outline)
        x += font.getlength(ch) + track


def fit_all(texts, target_h, max_w):
    """ONE size for the whole sequence: the largest at which EVERY line still fits.

    Fitting each line on its own makes the short ones huge and the long ones small, which the
    original never does -- its kana are the same height on all six reveals. The price is that the
    longest line sets the size for the rest."""
    size = target_h * 2
    while size > 8:
        f = ImageFont.truetype(ROUNDED, size); st = stroke_for(size)
        fits = True
        for t in texts:
            bb = f.getbbox(t, stroke_width=st)
            if measure(f, t, TRACK, st) > max_w or (bb[3] - bb[1]) > target_h + 8:
                fits = False; break
        if fits:
            return f
        size -= 1
    return ImageFont.truetype(ROUNDED, 8)


def main(extract, out, lang):
    pac = os.path.join(extract, "STORYGRA.PAC")
    data = open(pac, "rb").read()
    offs, i, n = {}, data.find(b"PVRT"), 0
    while i >= 0:
        offs[n] = i; n += 1; i = data.find(b"PVRT", i + 4)
    os.makedirs(out, exist_ok=True)
    font = fit_all(TEXT[lang], 53, MAX_W)          # 53 px = the original glyph height
    print("  one size for all six lines: %d pt" % font.size)
    for ci, pos in LINES:
        off = offs[ci]
        w, h = struct.unpack_from("<HH", data, off + 12)
        arr = pv.decode_rgb565(data, off + 16, w, h)
        top, bot = ink_rows(arr)
        arr[BAND[0]:BAND[1], :, :3] = BG                     # erase the line, keep the rest
        im = Image.fromarray(arr, "RGBA").convert("RGB")
        d = ImageDraw.Draw(im)
        text = TEXT[lang][pos]
        st = stroke_for(font.size)
        tw = measure(font, text, TRACK, st)
        bb = font.getbbox(text, stroke_width=st)
        x = (w - tw) // 2
        y = (top + bot) // 2 - (bb[3] - bb[1]) // 2 - bb[1]   # centre on the original's baseline band
        draw_tracked(d, x, y, text, font, TRACK, FILL, st, OUTLINE)
        rgba = np.dstack([np.array(im), np.full((h, w), 255, np.uint8)])
        blob = pv.encode_rgb565(rgba)
        assert len(blob) == w * h * 2, "chunk %d: wrong payload size" % ci
        p = os.path.join(out, "STORYGRA_c%d.bin" % ci)
        open(p, "wb").write(blob)
        print("  chunk #%-4d (line %d) %-28r -> %s" % (ci, pos + 1, text, os.path.basename(p)))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__.strip().splitlines()[-1]); sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "ca")
