#!/usr/bin/env python3
"""Repaint the mini-game HUD counter (MN1/2/3.PVM) -> Catalan.

The counter chunk (256x256 twiddled ARGB4444, the ドラやき/ゲット数 tally) is BYTE-IDENTICAL across
MN1/2/3 (md5 1b8edd90), just at different offsets. Repaint it ONCE and splice into all three:
    ドラやき (gold)  -> PASTISSETS
    ゲット数 (green) -> CRUSPITS
The dorayaki icon (top of the chunk) is kept. Each label's colour is sampled from the original so
the gold/green stays. Race-flash chunks (用意/スタート/終了) are per-file -> TODO, separate pass.

    repaint_mn.py <orig-dir> <out-dir>     # reads/writes MN1.PVM MN2.PVM MN3.PVM
"""
import sys, os, re, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))  # dc/ codecs
import pvr_codec as pv
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ARIAL = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
LINES = [((10, 84, 245, 139), "PASTISSETS"),   # ドラやき band (gold)
         ((5, 162, 250, 221), "GUANYATS")]      # ゲット数 band (green) -- shown as "pastissets guanyats"
                                                 # when you WIN them after a minigame, so "obtained", not a synonym
ICON_KEEP = 83                                  # rows above = dorayaki icon + gauge, untouched


def counter_offset(d):
    for m in re.finditer(b"PVRT", d):
        o = m.start(); W, H = struct.unpack_from("<HH", d, o + 12)
        if W == 256 and H == 256:
            return o
    return None


def sample_colour(arr, box):
    x0, y0, x1, y1 = box
    op = arr[y0:y1, x0:x1].reshape(-1, 4); op = op[op[:, 3] > 128]
    if len(op) == 0:
        return (255, 255, 255)
    score = op[:, :3].max(1).astype(int) + (op[:, :3].max(1).astype(int) - op[:, :3].min(1).astype(int))
    return tuple(int(c) for c in op[score.argmax(), :3])


def fit(text, box, pad=4):
    x0, y0, x1, y1 = box; bw, bh = (x1 - x0) - 2 * pad, (y1 - y0); sz = bh + 6
    while sz > 6:
        f = ImageFont.truetype(ARIAL, sz); l, t, r, b = f.getbbox(text)
        if (r - l) <= bw and (b - t) <= bh:
            break
        sz -= 1
    return sz


def draw(im, box, text, colour, sz, pad=4):
    x0, y0, x1, y1 = box; bw, bh = (x1 - x0) - 2 * pad, (y1 - y0)
    f = ImageFont.truetype(ARIAL, sz); l, t, r, b = f.getbbox(text); tw, th = r - l, b - t
    tmp = Image.new("RGBA", (tw + 8, th + 8), (0, 0, 0, 0)); td = ImageDraw.Draw(tmp); ox, oy = 4 - l, 4 - t
    for dx in (-2, -1, 0, 1, 2):                 # thick dark outline (HUD text is bold-outlined)
        for dy in (-2, -1, 0, 1, 2):
            if dx or dy:
                td.text((ox + dx, oy + dy), text, font=f, fill=(0, 0, 0, 255))
    td.text((ox, oy), text, font=f, fill=colour + (255,))
    im.alpha_composite(tmp, (x0 + (bw + 2 * pad - tw) // 2, y0 + (bh - th) // 2 - 4))


def build_counter(d, off):
    orig = pv.decode_argb4444(d, off + 16, 256, 256); arr = orig.copy()
    arr[ICON_KEEP:, :, 3] = 0                    # wipe the two text lines, keep the icon
    im = Image.fromarray(arr, "RGBA")
    for box, text in LINES:
        draw(im, box, text, sample_colour(orig, box), fit(text, box))
    return pv.encode_argb4444(np.array(im))


def main():
    src, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True)
    d1 = open(os.path.join(src, "MN1.PVM"), "rb").read()
    enc = build_counter(d1, counter_offset(d1))  # identical chunk -> repaint once
    for fn in ("MN1.PVM", "MN2.PVM", "MN3.PVM"):
        d = bytearray(open(os.path.join(src, fn), "rb").read()); o = counter_offset(d)
        d[o + 16: o + 16 + len(enc)] = enc
        open(os.path.join(out, fn), "wb").write(d)
        print("wrote %s (counter @0x%x)" % (fn, o))


if __name__ == "__main__":
    main()
