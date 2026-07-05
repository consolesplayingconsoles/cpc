#!/usr/bin/env python3
"""Repaint INFO/HIDORA_01.PVR (pocket-page transport-gadget labels, 256x256 ARGB4444
TWIDDLED) -> Catalan.

Same "four-dimensional pocket" info page as HIDORA_02, but this atlas is a SPRITE SHEET the
engine blits per sub-rect: eight empty cyan name-slot frames (left), red magnifier/search icons
(right), and TWO cyan text labels stacked at the bottom-left:

    タケコプター  -> Casquet volador
    どこでもドア  -> Porta màgica

Only the two labels are text. Each sits in its own ~127x22 box (x[3,130]); the game samples that
rect, so the Catalan must fit WITHIN it or the on-screen quad clips (same constraint as JYOU_00).
We erase each band to transparent (the labels sit on a transparent bg), then draw the name in the
same spring-cyan with a dark outline, fit-to-box and centred in the original x-extent. ARGB4444
round-trips byte-exactly, so untouched sprites (frames, magnifiers) are preserved. Same size ->
splices in place.

    repaint_hidora01.py <orig HIDORA_01.PVR> <out HIDORA_01.PVR>
"""
import sys, os, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))  # dc/ codecs
import pvr_codec as pv
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ARIAL = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
CYAN = (95, 238, 153)
OUTLINE = (12, 30, 20)

# (x0, y0, x1, y1, text) — boxes = the original JP label extents (measured)
LABELS = [
    (3, 191, 131, 215, "Casquet volador"),   # タケコプター
    (3, 216, 131, 239, "Porta màgica"),       # どこでもドア
]


def fit(text, maxw, maxh, hi=24, lo=8):
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
    # erase both label bands to transparent (nothing else lives in x<=135, y>=191)
    for x0, y0, x1, y1, _t in LABELS:
        arr[y0:y1 + 1, 0:136] = 0
    im = Image.fromarray(arr, "RGBA")
    for x0, y0, x1, y1, text in LABELS:
        size = fit(text, (x1 - x0) - 2, (y1 - y0) - 3)
        draw_outlined(im, (x0 + x1) / 2, (y0 + y1) / 2, text, size, CYAN, ow=1)
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
