#!/usr/bin/env python3
"""Repaint the Start-Of-Day / week-transition banner glyph atlas -> Catalan.

The `4月第4週` banner is COMPOSED at runtime from a 4x4, 64px-cell glyph atlas that is chunk #170
inside STORYGRA.PAC (256x256 ARGB4444): digits 0-11, `12`, and the kanji `月`(month) `第`(ordinal)
`週`(week). Editing text strings never touches it because these are baked bitmaps.

We repaint only the three kanji cells (digits untouched), matching their cream->green vertical
gradient + black outline:
  * `月` + `第` cells  -> "MES" drawn HORIZONTALLY across BOTH cells (one wide word; the ordinal `第`
    has no Catalan word, so it's absorbed -- the game blits the two cells adjacent and MES reassembles)
  * `週` cell          -> "SETM" STACKED vertically (a 4-letter word won't fit one 64px cell wide)
Result on screen: `4 MES 4 SETM`.

Output is JUST the patched chunk's raw pixel bytes (256*256*2 = 131072 B), spliced into the disc by
splice_pac_chunk.py -- so we never store or move the ~464 MB PAC.

    repaint_sod.py <orig STORYGRA.PAC> <out chunk .bin>
"""
import sys, os, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))  # dc/ codecs
import pvr_codec as pv
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ARIAL = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
TOP, BOT = (238, 255, 153), (51, 187, 85)   # glyph gradient: cream (top) -> green (bottom)
CHUNK_INDEX = 170
CELL = 64
# bottom row cells (row 3): [0]=12  [1]=月  [2]=第  [3]=週
MES_BOX  = (CELL * 1, CELL * 3, CELL * 3, CELL * 4)   # spans 月+第 (x64-192, y192-256)
SETM_BOX = (CELL * 3, CELL * 3, CELL * 4, CELL * 4)   # 週 cell (x192-256, y192-256)


def find_nth_pvrt(data, n):
    i = 0
    for _ in range(n):
        i = data.find(b"PVRT", i) + 4
    return data.find(b"PVRT", i)


def _grad_text(text, maxw, maxh):
    for sz in range(maxh, 8, -1):
        f = ImageFont.truetype(ARIAL, sz)
        l, t, r, b = f.getbbox(text)
        if (r - l) <= maxw and (b - t) <= maxh:
            break
    l, t, r, b = f.getbbox(text)
    tw, th, pad = r - l, b - t, 6
    tmp = Image.new("RGBA", (tw + 2 * pad, th + 2 * pad), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    ox, oy = pad - l, pad - t
    for dx in range(-3, 4):
        for dy in range(-3, 4):
            if dx * dx + dy * dy <= 9:
                td.text((ox + dx, oy + dy), text, font=f, fill=(0, 0, 0, 255))
    mask = Image.new("L", tmp.size, 0)
    ImageDraw.Draw(mask).text((ox, oy), text, font=f, fill=255)
    ma = np.array(mask)
    Hh, Ww = ma.shape
    fr = np.clip((np.arange(Hh) - oy) / max(1, th), 0, 1)
    g = np.zeros((Hh, Ww, 4), np.uint8)
    for c in range(3):
        g[:, :, c] = (TOP[c] + (BOT[c] - TOP[c]) * fr).astype(np.uint8)[:, None]
    g[:, :, 3] = ma
    tmp.alpha_composite(Image.fromarray(g, "RGBA"))
    return tmp


def build_chunk(pac):
    j = find_nth_pvrt(pac, CHUNK_INDEX)
    w, h = struct.unpack_from("<HH", pac, j + 12)
    arr = pv.decode_argb4444(pac, j + 16, w, h)
    # erase the three kanji cells (transparent atlas bg)
    for (x0, y0, x1, y1) in [(64, 192, 128, 256), (128, 192, 192, 256), (192, 192, 256, 256)]:
        arr[y0:y1, x0:x1, 3] = 0
    im = Image.fromarray(arr, "RGBA")
    # MES horizontal across 月+第 (margin so a letter doesn't hug the cell seam/edge)
    mx0, my0, mx1, my1 = MES_BOX
    mes = _grad_text("MES", (mx1 - mx0) - 24, (my1 - my0) - 16)
    im.alpha_composite(mes, (mx0 + (mx1 - mx0 - mes.width) // 2, my0 + (my1 - my0 - mes.height) // 2))
    # SETM stacked in 週 cell
    sx0, sy0, sx1, sy1 = SETM_BOX
    cellh = (sy1 - sy0) / 4
    for k, ch in enumerate("SETM"):
        gt = _grad_text(ch, (sx1 - sx0) - 20, int(cellh + 2))
        im.alpha_composite(gt, (sx0 + (sx1 - sx0 - gt.width) // 2, int(sy0 + cellh * k + (cellh - gt.height) // 2)))
    enc = pv.encode_argb4444(np.array(im))
    assert len(enc) == w * h * 2, (len(enc), w * h * 2)
    return enc


def main():
    src, out = sys.argv[1], sys.argv[2]
    pac = open(src, "rb").read()
    enc = build_chunk(pac)
    open(out, "wb").write(enc)
    print("wrote %s (%d B = chunk #%d pixel data)" % (out, len(enc), CHUNK_INDEX))


if __name__ == "__main__":
    main()
