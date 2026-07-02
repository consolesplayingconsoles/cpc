#!/usr/bin/env python3
"""TEST tool: stamp numbered markers across TITLE.PVM's menu atlas (sub #3) to learn the
atlas->screen mapping, so we can find a visible spot for the "Traduït per CPC" credit.

Keeps the real menu (COMENÇA/…) and drops a grid of bright numbers in the BLANK bands. Build
this, look at the screen, and tell me which numbers show up and where — I map each back to its
atlas coords (printed as the legend) and place the credit on a number that lands well.

    title_markers.py <orig TITLE.PVM> <out TITLE.PVM>
"""
import sys, os, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import pvr_codec as pv
import numpy as np
from PIL import Image, ImageDraw, ImageFont

SUBOFF = 0x180130
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
# grid points in the BLANK bands of the 256x256 atlas (avoid the menu rows 36-123 & 192-218)
XS = [8, 58, 108, 158, 208]
YS = [126, 150, 174, 228]                      # middle gap + bottom strip
COLS = [(255,80,80),(80,255,80),(90,160,255),(255,240,80)]   # a colour per row


def main():
    src, out = sys.argv[1], sys.argv[2]
    d = bytearray(open(src, "rb").read())
    arr = pv.decode_argb4444(bytes(d), SUBOFF + 16, 256, 256).copy()
    im = Image.fromarray(arr, "RGBA"); dr = ImageDraw.Draw(im)
    f = ImageFont.truetype(FONT, 15)
    n = 1; legend = []
    for yi, y in enumerate(YS):
        for x in XS:
            s = str(n)
            for dx in (-1,0,1):
                for dy in (-1,0,1):
                    if dx or dy: dr.text((x+dx, y+dy), s, font=f, fill=(0,0,0,255))
            dr.text((x, y), s, font=f, fill=COLS[yi] + (255,))
            legend.append((n, x, y)); n += 1
    enc = pv.encode_argb4444(np.array(im))
    d[SUBOFF + 16: SUBOFF + 16 + len(enc)] = enc
    open(out, "wb").write(d)
    print("wrote %s" % out)
    print("LEGEND (marker -> atlas x,y):")
    for k, x, y in legend: print("  %2d -> (%d,%d)" % (k, x, y))


if __name__ == "__main__":
    main()
