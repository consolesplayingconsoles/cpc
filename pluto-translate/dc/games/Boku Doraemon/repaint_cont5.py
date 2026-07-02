#!/usr/bin/env python3
"""Repaint CONT_5.PVR (options-screen button-hint bar, 256x64 ARGB4444 NON-twiddled) -> Catalan.

Original JP (two left-aligned pink lines):
    スタートボタン：せってい   (Start button: confirm/apply)
    Bボタン：キャンセル       (B button: cancel)
-> Start: Confirma / B: Cancel·la  (both lines drawn at ONE uniform size)

This atlas is datafmt 0x09 (rectangle, NON-twiddled) -> linear ARGB4444, unlike OPTION1.PVR
(twiddled). Same size preserved so it splices in place.

    repaint_cont5.py <orig CONT_5.PVR> <out CONT_5.PVR>
"""
import sys, os, struct
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ARIAL = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
PINK  = (245, 110, 165)                       # matches the JP hint colour
LINES = ["Start: Confirma", "B: Cancel·la"]


def lin_decode(d, off, w, h):
    a = np.zeros((h, w, 4), np.uint8)
    for y in range(h):
        for x in range(w):
            v = struct.unpack_from("<H", d, off + (y * w + x) * 2)[0]
            a[y, x] = [((v >> 8) & 0xf) * 17, ((v >> 4) & 0xf) * 17, (v & 0xf) * 17, ((v >> 12) & 0xf) * 17]
    return a


def lin_encode(arr):
    h, w = arr.shape[:2]
    out = bytearray(w * h * 2)
    for y in range(h):
        for x in range(w):
            r, g, b, al = (int(c) for c in arr[y, x])   # int(): numpy uint8<<12 would overflow
            v = ((al // 17) << 12) | ((r // 17) << 8) | ((g // 17) << 4) | (b // 17)
            struct.pack_into("<H", out, (y * w + x) * 2, v)
    return bytes(out)


def fit_size(text, box, fontpath, pad=3):
    x0, y0, x1, y1 = box
    bw, bh = (x1 - x0) - 2 * pad, (y1 - y0)
    sz = bh + 4
    while sz > 6:
        f = ImageFont.truetype(fontpath, sz)
        l, t, r, b = f.getbbox(text)
        if (r - l) <= bw and (b - t) <= bh:
            break
        sz -= 1
    return sz


def draw_line(im, text, box, fontpath, colour, sz, pad=3):
    x0, y0, x1, y1 = box
    bh = y1 - y0
    f = ImageFont.truetype(fontpath, sz)
    l, t, r, b = f.getbbox(text); tw, th = r - l, b - t
    tmp = Image.new("RGBA", (tw + 6, th + 6), (0, 0, 0, 0)); td = ImageDraw.Draw(tmp)
    ox, oy = 3 - l, 3 - t
    for dx in (-1, 0, 1):                       # dark outline like the original
        for dy in (-1, 0, 1):
            if dx or dy:
                td.text((ox + dx, oy + dy), text, font=f, fill=(0, 0, 0, 255))
    td.text((ox, oy), text, font=f, fill=colour + (255,))
    im.alpha_composite(tmp, (x0, y0 + (bh - th) // 2 - 3))


def main():
    src, out = sys.argv[1], sys.argv[2]
    d = bytearray(open(src, "rb").read())
    p = d.find(b"PVRT"); W, H = struct.unpack_from("<HH", d, p + 12); off = p + 16
    arr = lin_decode(bytes(d), off, W, H)
    arr[:, :, 3] = 0                            # wipe the JP
    im = Image.fromarray(arr, "RGBA")
    boxes = [(4, 2, W - 2, 32), (4, 33, W - 2, 63)]             # top / bottom line
    sz = min(fit_size(t, b, ARIAL) for t, b in zip(LINES, boxes))  # ONE size for both lines
    for text, box in zip(LINES, boxes):
        draw_line(im, text, box, ARIAL, PINK, sz)
    enc = lin_encode(np.array(im))
    assert len(enc) == W * H * 2, (len(enc), W * H * 2)
    d[off:off + len(enc)] = enc
    open(out, "wb").write(d)
    print("wrote %s (%d B)" % (out, len(d)))


if __name__ == "__main__":
    main()
