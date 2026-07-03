#!/usr/bin/env python3
"""Repaint CONT_0.PVR (pocket-screen control legend, 128x128 ARGB4444 TWIDDLED) -> Catalan.

Three blue button rows, each an icon on the left + a green hiragana label:
    [D-pad] いどう   (move)      -> Moure
    [A]     けってい  (confirm)   -> Tria
    [B]     もどる   (back)      -> Enrere
The icons are LEFT of x~57 and are preserved. Only the text area (x>=57) is touched: the green
label is erased by refilling the blue button background PER SCANLINE (so the vertical button
gradient survives), then the Catalan is drawn in the same green with a black outline. Same size,
so it splices in place.

    repaint_cont0.py <orig CONT_0.PVR> <out CONT_0.PVR>
"""
import sys, os, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))  # dc/ codecs
import pvr_codec as pv
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ARIAL = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
GREEN = (187, 255, 102)
OUTLINE = (0, 0, 0)
TEXT_X0, TEXT_X1 = 34, 125           # text area, right of the icons (which end ~x33)

# (row y0, y1, Catalan)
ROWS = [
    (0, 32,  "Moure"),    # D-pad + いどう
    (34, 66, "Tria"),     # A + けってい
    (68, 100, "Enrere"),  # B + もどる
]


def erase_text_keep_gradient(arr, x0, x1, y0, y1):
    """Refill the text area with the blue button bg PER SCANLINE (keeps the top->bottom gradient).
    Green glyph + dark outline pixels are excluded from the sample so only real bg is used."""
    R, G, B, A = (arr[..., i].astype(int) for i in range(4))
    for y in range(y0, y1):
        row = arr[y, x0:x1]
        r, g, b, a = R[y, x0:x1], G[y, x0:x1], B[y, x0:x1], A[y, x0:x1]
        is_green = (g > 140) & (g > r + 30) & (g > b + 30)
        is_dark = (r + g + b) < 120
        bg = row[(a > 60) & ~is_green & ~is_dark]
        if len(bg):
            fill = np.median(bg[:, :3], 0).astype(np.uint8)
            arr[y, x0:x1, :3] = fill
            arr[y, x0:x1, 3] = 255


def fit(text, maxw, maxh, hi=30, lo=8):
    for sz in range(hi, lo - 1, -1):
        f = ImageFont.truetype(ARIAL, sz)
        l, t, r, b = f.getbbox(text)
        if (r - l) <= maxw and (b - t) <= maxh:
            return sz
    return lo


def draw_outlined(im, cx, cy, text, size, fill, ow=1):
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


def build(d):
    p = d.find(b"PVRT")
    W, H = struct.unpack_from("<HH", d, p + 12)
    arr = pv.decode_argb4444(d, p + 16, W, H)
    for y0, y1, _t in ROWS:
        erase_text_keep_gradient(arr, TEXT_X0, TEXT_X1, y0, y1)
    im = Image.fromarray(arr, "RGBA")
    for y0, y1, text in ROWS:
        size = fit(text, (TEXT_X1 - TEXT_X0) - 4, (y1 - y0) - 6)
        draw_outlined(im, (TEXT_X0 + TEXT_X1) / 2, (y0 + y1) / 2, text, size, GREEN, ow=1)
    enc = pv.encode_argb4444(np.array(im))
    assert len(enc) == W * H * 2, (len(enc), W * H * 2)
    out = bytearray(d)
    out[p + 16: p + 16 + len(enc)] = enc
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
