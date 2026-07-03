#!/usr/bin/env python3
"""Repaint the main-game field HUD label `ドラやき` -> `Pastissets` in PARAM.PVM (chunk 0).

The 256x256 ARGB4444 atlas is the field HUD: month numbers + `月` (KEPT -- it's a date suffix, no room
for a Catalan word), `TIME` (already English) + time digits, dorayaki icons, and the green `ドラやき`
count label. Only that label is translated: erase it (alpha, transparent atlas bg) and redraw
`Pastissets` in the same green, fitted to its ~76px slot at a reduced font (operator's call -- full word
over an abbreviation). Everything else is left byte-for-byte, so only the label's pixels change.

    repaint_param.py <in-PARAM.PVM> <out-PARAM.PVM>
"""
import sys, os, re, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))  # dc/ codecs
import pvr_codec as pv
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ARIAL = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
GREEN = (127, 238, 170)                 # sampled from the original ドラやき
LABEL = "Pastissets"
SLOT = (102, 178)                       # ドラやき x-extent (the on-screen label footprint)
ERASE = (98, 180, 184, 221)             # x0,y0,x1,y1 -- covers ドラやき (x102-179, y183-217) + margin
CENTER_Y = 200


def fit(text, maxw):
    for sz in range(30, 7, -1):
        f = ImageFont.truetype(ARIAL, sz)
        if (f.getbbox(text)[2] - f.getbbox(text)[0]) <= maxw:
            return sz
    return 8


def build(d):
    off = [m.start() for m in re.finditer(b"PVRT", d)][0]
    W, H = struct.unpack_from("<HH", d, off + 12)
    arr = pv.decode_argb4444(d, off + 16, W, H)
    ex0, ey0, ex1, ey1 = ERASE
    arr[ey0:ey1, ex0:ex1, 3] = 0                      # erase ドラやき (transparent atlas bg)
    im = Image.fromarray(arr, "RGBA")
    sz = fit(LABEL, SLOT[1] - SLOT[0] - 2)
    f = ImageFont.truetype(ARIAL, sz)
    l, t, r, b = f.getbbox(LABEL)
    th = b - t
    tmp = Image.new("RGBA", (r - l + 8, th + 8), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    ox, oy = 4 - l, 4 - t
    for dx in (-1, 0, 1):                             # thin dark outline (crisp at small size)
        for dy in (-1, 0, 1):
            if dx or dy:
                td.text((ox + dx, oy + dy), LABEL, font=f, fill=(15, 55, 25, 255))
    td.text((ox, oy), LABEL, font=f, fill=GREEN + (255,))
    im.alpha_composite(tmp, (SLOT[0], CENTER_Y - (th + 8) // 2))
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
