#!/usr/bin/env python3
"""Repaint INFO/HIDORA_02.PVR (pocket-screen body-part label atlas, 256x256 ARGB1555
TWIDDLED) -> Catalan.

This is the "four-dimensional pocket" info page: Doraemon's body opened up into eight
labelled parts, laid out as a 2-col x 4-row grid of white rounded boxes (blue border,
magenta text). The eight JP labels (row-major) are the secret gadgets built into his body:

    赤外線アイ  強力ハナ        Ulls infrarojos   Supernas
    レーダーひげ ネコ集め鈴  ->  Bigotis radar     Campaneta gatera
    ペタリハンド 四次元ポケット   Mans ventosa      Butxaca magica
    しっぽ      あし            Cua interruptor   Peus flotants

Method (see textures.md): decode the twiddled ARGB1555 to RGBA, and PER BOX erase only the
magenta glyphs -> white (leaving the blue border + rounded corners byte-untouched), then draw
the Catalan name centred in the box in the SAME magenta, fit-to-width and wrapped to two lines
for the long two-word names (the box is short+wide, one line would be a squint). Re-encode only
the pixels that actually changed back into the original 16-bit buffer, so everything outside the
glyphs (border, corners, gaps) stays byte-identical -- ARGB1555 does NOT round-trip exactly, so
we must not re-quantise untouched pixels. Same size -> splices in place.

    repaint_hidora.py <orig HIDORA_02.PVR> <out HIDORA_02.PVR>
"""
import sys, os, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))  # dc/ codecs
import pvr_codec as pv
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ARIAL = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
MAGENTA = (238, 82, 164)
WHITE = (246, 246, 246)

# Column interiors (x0,x1) and row bands (y0,y1), inset off the blue border/rounded corners.
COLS = [(8, 120), (136, 248)]
BANDS = [(8, 58), (72, 122), (136, 186), (200, 250)]

# row-major, wrapped to lines. Single-word names stay one line (drawn bigger).
LABELS = [
    ["Ulls", "infrarojos"],   ["Supernas"],
    ["Bigotis", "radar"],     ["Campaneta", "gatera"],
    ["Mans", "ventosa"],      ["Butxaca", "màgica"],
    ["Cua", "interruptor"],   ["Peus", "flotants"],
]


def decode(d):
    j = d.find(b"PVRT")
    w, h = struct.unpack_from("<HH", d, j + 12)
    raw = np.frombuffer(d, dtype="<u2", count=w * h, offset=j + 16).copy()
    sx = pv.twiddle_table(w); sy = pv.twiddle_table(h)
    tw = (sx[None, :] << 1) | sy[:, None]            # twiddled src index per (x,y)
    v = raw[tw.ravel()].reshape(h, w).astype(np.uint16)
    a = (v >> 15) & 1; r = ((v >> 10) & 0x1F) * 255 // 31
    g = ((v >> 5) & 0x1F) * 255 // 31; b = (v & 0x1F) * 255 // 31
    rgba = np.dstack([r, g, b, a * 255]).astype(np.uint8)
    return j, w, h, raw, tw, rgba


def fit_lines(lines, maxw, maxh, hi=30, lo=9):
    """Largest font size at which every line fits maxw and the stack fits maxh."""
    for sz in range(hi, lo - 1, -1):
        f = ImageFont.truetype(ARIAL, sz)
        widths = [f.getbbox(t)[2] - f.getbbox(t)[0] for t in lines]
        lh = (f.getbbox("Àgjy")[3] - f.getbbox("Àgjy")[1]) + 2
        if max(widths) <= maxw and lh * len(lines) <= maxh:
            return sz
    return lo


# px kept clear of the box edge on each side so the on-screen quad doesn't clip the glyphs
MARGIN_X = 12
MARGIN_Y = 6


def draw_label(im, box, lines):
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    sz = fit_lines(lines, (x1 - x0) - 2 * MARGIN_X, (y1 - y0) - 2 * MARGIN_Y,
                   hi=26 if len(lines) == 1 else 22)
    f = ImageFont.truetype(ARIAL, sz)
    lh = (f.getbbox("Àgjy")[3] - f.getbbox("Àgjy")[1]) + 2
    total = lh * len(lines)
    d = ImageDraw.Draw(im)
    for i, t in enumerate(lines):
        l, tp, r, b = f.getbbox(t)
        tw = r - l
        ty = cy - total / 2 + i * lh - tp
        tx = cx - tw / 2 - l
        d.text((tx, ty), t, font=f, fill=MAGENTA + (255,))


def build(d):
    j, w, h, raw, tw, rgba = decode(d)
    orig_rgba = rgba.copy()
    Ri = rgba[..., 0].astype(int); Gi = rgba[..., 1].astype(int)
    # erase the magenta glyphs (and their pink AA) -> white, restricted to each box interior
    for row in range(4):
        by0, by1 = BANDS[row]
        for col in range(2):
            bx0, bx1 = COLS[col]
            sub = np.s_[by0:by1 + 1, bx0:bx1 + 1]
            mag = (Ri[sub] - Gi[sub] > 10)
            cell = rgba[sub]
            cell[mag] = WHITE + (255,)
            rgba[sub] = cell
    # draw the Catalan names
    im = Image.fromarray(rgba, "RGBA")
    for idx, lines in enumerate(LABELS):
        row, col = divmod(idx, 2)
        bx0, bx1 = COLS[col]; by0, by1 = BANDS[row]
        draw_label(im, (bx0, by0, bx1, by1), lines)
    rgba = np.array(im)
    # re-encode ONLY changed pixels into the original 16-bit buffer (keep the rest byte-exact)
    changed = np.any(rgba != orig_rgba, axis=2)
    R = rgba[..., 0].astype(np.uint16); G = rgba[..., 1].astype(np.uint16)
    B = rgba[..., 2].astype(np.uint16); A = rgba[..., 3]
    r5 = (R * 31 + 127) // 255; g5 = (G * 31 + 127) // 255; b5 = (B * 31 + 127) // 255
    a1 = (A > 127).astype(np.uint16)
    packed = (a1 << 15) | (r5 << 10) | (g5 << 5) | b5
    ys, xs = np.where(changed)
    out_raw = raw.copy()
    out_raw[tw[ys, xs]] = packed[ys, xs].astype(np.uint16)
    out = bytearray(d)
    out[j + 16: j + 16 + w * h * 2] = out_raw.astype("<u2").tobytes()
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
