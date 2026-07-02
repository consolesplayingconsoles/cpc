#!/usr/bin/env python3
"""TEST tool: stamp numbered markers on TITLE.PVM's SKY sub (#0 @0xd0, the full-screen background)
to learn the atlas->screen mapping and find a VISIBLE, EMPTY spot for the "Traduït per CPC" credit.

The menu atlas (#3) only renders its menu-item bands, so markers there were invisible. The sky is
drawn behind everything, so a marker shows up wherever the sky is actually visible on screen (the
empty areas). Build this, note which numbers you can see and where, and I map each back to its atlas
coords (the legend) to place the credit on a spot that lands — away from the © line.

    title_markers.py <orig TITLE.PVM> <out TITLE.PVM>       # menu untouched; markers on the sky
"""
import sys, os, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import pvr_codec as pv
import numpy as np
from PIL import Image, ImageDraw, ImageFont

SKY = 0xd0                                          # sub #0, 512x512, the sky background
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
XS = [45, 150, 255, 360, 455]
YS = [45, 130, 215, 300, 385]                       # avoid the very bottom (© line lives there)


def main():
    src, out = sys.argv[1], sys.argv[2]
    d = bytearray(open(src, "rb").read())
    im = Image.fromarray(pv.decode_argb4444(bytes(d), SKY + 16, 512, 512), "RGBA")
    dr = ImageDraw.Draw(im); f = ImageFont.truetype(FONT, 30)
    n = 1; legend = []
    for y in YS:
        for x in XS:
            s = str(n)
            for dx in (-2,-1,0,1,2):
                for dy in (-2,-1,0,1,2):
                    if dx or dy: dr.text((x+dx, y+dy), s, font=f, fill=(255,255,255,255))  # white halo
            dr.text((x, y), s, font=f, fill=(0, 0, 0, 255))                                # black digit
            legend.append((n, x, y)); n += 1
    enc = pv.encode_argb4444(np.array(im))
    d[SKY + 16: SKY + 16 + len(enc)] = enc
    open(out, "wb").write(d)
    print("wrote %s" % out)
    print("LEGEND (marker -> atlas x,y on the 512x512 sky):")
    for k, x, y in legend: print("  %2d -> (%d,%d)" % (k, x, y))


if __name__ == "__main__":
    main()
