#!/usr/bin/env python3
"""Repaint the album header in ALBUM.PVM: the plate at the top of the corkboard.

    /usr/bin/python3 repaint_album.py <original ALBUM.PVM> <output ALBUM.PVM>

Only the header is text. Everything else pinned to the board is a photograph of a
handwritten letter, which is artwork, not a string, so it is left alone.

お客様からの声 is feedback from customers, and お客様 is "passengers" everywhere else in
this translation, so the plate reads FROM OUR PASSENGERS. The plate keeps its bevel: only
its flat interior is cleared, and the English is set to the same ink height as the
Japanese so the board looks untouched apart from the words.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
import struct
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from dc import pvr_codec as P

BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
PLATE = (136, 28, 356, 52)          # the flat inside of the header plate, bevel excluded
PLATE_GREY = (238, 238, 238, 255)
INK = (0, 0, 0, 255)
TEXT = "FROM OUR PASSENGERS"


def main(src, dst):
    d = bytearray(open(src, "rb").read())
    off, w, h, pf = P.find_chunk(bytes(d), 0)
    img = Image.fromarray(P.decode_argb4444(bytes(d), off, w, h))
    dr = ImageDraw.Draw(img)
    dr.rectangle(PLATE, fill=PLATE_GREY)

    size = PLATE[3] - PLATE[1]
    while True:
        font = ImageFont.truetype(BOLD, size)
        l, t, r, b = font.getbbox(TEXT)
        if r - l <= PLATE[2] - PLATE[0] - 8 and b - t <= PLATE[3] - PLATE[1] - 2:
            break
        size -= 1
    dr.text(((PLATE[0] + PLATE[2] - (r - l)) // 2 - l,
             (PLATE[1] + PLATE[3] - (b - t)) // 2 - t), TEXT, font=font, fill=INK)

    d[off:off + w * h * 2] = P.encode_argb4444(np.array(img))
    if len(d) != os.path.getsize(src):
        raise SystemExit("file size changed")
    open(dst, "wb").write(bytes(d))
    print("wrote %s at %dpt" % (dst, size))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
