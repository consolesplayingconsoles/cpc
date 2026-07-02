#!/usr/bin/env python3
"""Repaint OPTION1.PVR (options screen atlas, 256x256 ARGB4444 twiddled) -> Catalan.

The engine maps each label's texture region to a FIXED screen quad, so every label must be drawn
WITHIN the original JP label's x-extent or the quad clips it (that was the earlier overflow bug on
STEREO·MONO / RÀPID·LENT). Boxes below are the detected JP extents; text is fit-to-box (Arial Narrow
Bold for the tight toggles). Number scales (12345 / 1234) are left untouched.

    repaint_option1.py <orig OPTION1.PVR> <out OPTION1.PVR>
"""
import sys, os, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))  # dc/ format-generic codecs
import pvr_codec as pv
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ARIAL  = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
NARROW = "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf"
Y = (245, 235, 90); G = (120, 235, 70); P = (245, 110, 165)   # label / title / toggle colours

# (x0,y0,x1,y1), text, colour, font — boxes = original JP label extents (see /tmp/option1_boxes.png)
# (box, text, colour, font, fill) — fill = fraction of the box width to fill. The engine maps each
# label to a NARROWER screen quad than the atlas box, so toggles overflowed on hardware; fill<1
# leaves margin so they fit the real quad (operator-tuned from the DC screenshot).
LABELS = [
    ((32, 10, 224, 52),  "OPCIONS",     G, ARIAL,  0.95),
    ((3, 65, 122, 87),   "SO",          Y, ARIAL,  0.90),
    ((130, 65, 253, 87), "VEL.",        Y, ARIAL,  0.90),
    ((2, 87, 122, 109),  "PAG.",        Y, ARIAL,  0.85),
    ((130, 87, 254, 109),"VEUS",        Y, ARIAL,  0.90),
    ((2, 113, 126, 132), "MÚSICA",      Y, ARIAL,  0.95),   # smaller box -> smaller font so the Ú accent fits inside its cell (no overflow, no bottom cut)
    ((128, 110, 254, 135),"EFECTES",    Y, ARIAL,  0.95),
    # STEREO / MONO are TWO options at two fixed positions (like OFF/ON) -- drawn separately so the
    # game's selection frame lands on STEREO without clipping MONO, and both bigger than the old merge.
    ((129, 137, 191, 159),"STEREO",     P, NARROW, 0.94),
    ((198, 137, 254, 159),"MONO",       P, NARROW, 0.94),
    ((2, 160, 126, 186), "OFF ON",      P, ARIAL,  0.82),
    ((146, 160, 240, 186),"S L",        P, ARIAL,  0.60),
    ((146, 184, 254, 205),"RÀP LEN",    P, NARROW, 0.85),   # nudged up 3px off the bottom clip
]


def draw_fit(im, box, text, colour, fontpath, fill=0.95, pad=3):
    x0, y0, x1, y1 = box
    bw, bh = int(((x1 - x0) - 2 * pad) * fill), (y1 - y0)
    sz = bh + 6
    while sz > 6:
        f = ImageFont.truetype(fontpath, sz)
        l, t, r, b = f.getbbox(text)
        if (r - l) <= bw and (b - t) <= bh: break
        sz -= 1
    f = ImageFont.truetype(fontpath, sz)
    l, t, r, b = f.getbbox(text); tw, th = r - l, b - t
    tmp = Image.new("RGBA", (tw + 6, th + 6), (0, 0, 0, 0)); td = ImageDraw.Draw(tmp)
    ox, oy = 3 - l, 3 - t
    for dx in (-1, 0, 1):                       # dark outline (mimics the original glow edge)
        for dy in (-1, 0, 1):
            if dx or dy: td.text((ox + dx, oy + dy), text, font=f, fill=(0, 0, 0, 255))
    td.text((ox, oy), text, font=f, fill=colour + (255,))
    cx = x0 + (bw + 2 * pad - tw) // 2 - 3
    cy = y0 + (bh - th) // 2 - 3
    im.alpha_composite(tmp, (max(0, cx), max(0, cy)))


def main():
    src, out = sys.argv[1], sys.argv[2]
    d = bytearray(open(src, "rb").read())
    p = d.find(b"PVRT"); W, H = struct.unpack_from("<HH", d, p + 12); off = p + 16
    rgba = pv.decode_argb4444(bytes(d), off, W, H)
    arr = rgba.copy()
    arr[:, :, 3] = 0                             # WIPE the whole atlas (kills all JP + stray fragments)
    kx0, ky0, kx1, ky1 = 0, 187, 122, 234       # ...then restore ONLY the rainbow number scales (12345/1234)
    arr[ky0:ky1, kx0:kx1, 3] = rgba[ky0:ky1, kx0:kx1, 3]
    im = Image.fromarray(arr, "RGBA")
    for box, text, col, font, fill in LABELS:
        draw_fit(im, box, text, col, font, fill)
    enc = pv.encode_argb4444(np.array(im))
    assert len(enc) == H * W * 2, (len(enc), H * W * 2)
    d[off:off + len(enc)] = enc
    open(out, "wb").write(d)
    print("wrote %s (%d B)" % (out, len(d)))


if __name__ == "__main__":
    main()
