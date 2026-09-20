#!/usr/bin/env python3
"""Repaint the title logo in SYSTEM/TITLE.PVM: the game's name on the side of the bus.

    /usr/bin/python3 repaint_title.py <original TITLE.PVM> <output TITLE.PVM> [en|jp] [mod]

    en        the name in English: TOKYO BUS GUIDE (the translation release)
    jp        the Japanese logo untouched
    ... mod   renames the game to Tokyo BS Guide: in English the U of BUS is struck
              out in red, in Japanese a red BS is stamped over the バス
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from dc import pvr_codec as P

FONT = "/System/Library/Fonts/Supplemental/Arial Black.ttf"
GREEN, YELLOW, RED = (0, 136, 68, 255), (255, 204, 0, 255), (218, 16, 16, 255)
BOX = (663, 222, 926, 270)          # the flank of the bus, where the Japanese name was
TEXT = "TOKYO BUS GUIDE"
JP_BUS = (751, 835)                 # the バス of 東京バス案内, measured off the original


def stamp(img, dr, span, top, bottom):
    """The red BS that renames the game, over the word for bus."""
    x0, x1 = span
    size = bottom - top + 10
    while True:
        font = ImageFont.truetype(FONT, size)
        l, t, r, b = font.getbbox("BS")
        if r - l <= x1 - x0 + 10:
            break
        size -= 1
    dr.text(((x0 + x1 - (r - l)) // 2 - l, (top + bottom - (b - t)) // 2 - t), "BS",
            font=font, fill=RED, stroke_width=3, stroke_fill=(255, 255, 255, 255))


def main(src, dst, lang="en", mod=False):
    d = bytearray(open(src, "rb").read())
    off, w, h, pf = P.find_chunk(bytes(d), 0)
    img = Image.fromarray(P.decode_argb4444(bytes(d), off, w, h))
    dr = ImageDraw.Draw(img)

    if lang == "en":
        dr.rectangle(BOX, fill=GREEN)
        size = 48
        while True:
            font = ImageFont.truetype(FONT, size)
            l, t, r, b = font.getbbox(TEXT)
            if r - l <= BOX[2] - BOX[0] - 6 and b - t <= BOX[3] - BOX[1] - 6:
                break
            size -= 1
        x = (BOX[0] + BOX[2] - (r - l)) // 2 - l
        y = (BOX[1] + BOX[3] - (b - t)) // 2 - t
        dr.text((x, y), TEXT, font=font, fill=YELLOW)
        if mod:                                 # BUS -> BS, by striking the U out
            i = TEXT.index("U")
            x0 = x + font.getbbox(TEXT[:i])[2] - 3   # kerned, so measure the real prefix
            x1 = x + font.getbbox(TEXT[:i + 1])[2] + 3
            for a, c in (((x0, y + t - 4), (x1, y + b + 4)),
                         ((x0, y + b + 4), (x1, y + t - 4))):
                dr.line([a, c], fill=RED, width=6)
    elif mod:                                   # 東京バス案内 -> 東京BS案内
        stamp(img, dr, JP_BUS, 227, 266)

    d[off:off + w * h * 2] = P.encode_argb4444(np.array(img))
    open(dst, "wb").write(bytes(d))
    print("wrote %s (%s%s)" % (dst, lang, ", mod" if mod else ""))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "en", "mod" in sys.argv[4:])
