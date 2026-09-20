#!/usr/bin/env python3
"""Repaint the Japanese labels baked into SYSTEM/COMMON.PVM (the BONUS results table).

Run with /usr/bin/python3 (the Python that has PIL + numpy):

    /usr/bin/python3 repaint_common.py <original COMMON.PVM> <output COMMON.PVM>

The atlas is one 512x512 twiddled ARGB4444 texture cut into 32x32 tiles; a label is
drawn as a run of whole tiles, so each label may use every pixel of the tiles its
Japanese spans and not one pixel more. Boxes below are those tile runs, measured from
the original: draw outside one and the text lands on another screen.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from dc import pvr_codec as P

FONT = "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf"
RED, WHITE = (255, 0, 0, 255), (255, 255, 255, 255)

# (box to clear, left edge to draw from, right limit, glyph band top/bottom, text)
# One table, so every label is drawn at one size: the largest that fits them all.
LABELS = [
    ((448, 128, 512, 160), 450, 511, 131, 148, "FINISH"),     # 完走
    ((384, 160, 448, 192), 386, 447, 162, 180, "FIRST"),      # 初走
    ((448, 160, 512, 192), 450, 511, 162, 180, "RIDERS"),     # 乗客
    ((0, 256, 96, 288),      2,  95, 259, 276, "BADGE"),      # バッジ獲得
    ((0, 288, 176, 320),     3, 172, 290, 307, "DRIVER POINTS"), # ドライバーズポイント
]


def fits(text, size, box_w, box_h):
    l, t, r, b = ImageFont.truetype(FONT, size).getbbox(text)
    return r - l + 4 <= box_w and b - t + 4 <= box_h + 2


def common_size():
    """The largest point size that fits every label in its own box."""
    for size in range(28, 5, -1):
        if all(fits(text, size, right - left, bottom - top + 1)
               for _, left, right, top, bottom, text in LABELS):
            return size
    raise SystemExit("no size fits every label")


def main(src, dst):
    d = open(src, "rb").read()
    off, w, h, pf = P.find_chunk(d, 0)
    if (w, h, pf) != (512, 512, 2):
        raise SystemExit("unexpected chunk: %dx%d fmt %d" % (w, h, pf))
    img = Image.fromarray(P.decode_argb4444(d, off, w, h), "RGBA")

    size = common_size()
    font = ImageFont.truetype(FONT, size)
    print("one size for the table: %dpt" % size)
    for (x0, y0, x1, y1), left, right, top, bottom, text in LABELS:
        img.paste((0, 0, 0, 0), (x0, y0, x1, y1))           # clear the whole tile run
        bl, bt, br, bb = font.getbbox(text)
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        dr = ImageDraw.Draw(layer)
        x = left + 1 - bl
        y = top - bt + (bottom - top + 1 - (bb - bt)) // 2
        dr.text((x, y), text, font=font, fill=RED, stroke_width=2, stroke_fill=WHITE)
        img.alpha_composite(layer)

    out = bytearray(d)
    out[off:off + w * h * 2] = P.encode_argb4444(np.array(img))
    open(dst, "wb").write(bytes(out))
    print("wrote %s (%d bytes)" % (dst, len(out)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
