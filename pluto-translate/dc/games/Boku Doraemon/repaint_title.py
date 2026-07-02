#!/usr/bin/env python3
"""Repaint TITLE.PVM's menu atlas (sub-texture #3, 256x256 twiddled ARGB4444) -> Catalan.

TITLE.PVM is a PVM container of 5 PVRT sub-textures; #3 (@0x180130) is the title MENU:
    PRESS START BUTTON   (already Latin -> leave)
    はじめから            -> COMENÇA
    つづきから            -> CONTINUA
    インターネット         -> INTERNET
    ドリームパスポートで登録をしてくださいね  -> Cal registrar-se amb / el Dream Passport
    オプション            -> OPCIONS

Like OPTION1, the engine maps each label to a FIXED screen quad, so each Catalan label is
fit WITHIN the original JP label's x-extent (measured bands below) or it clips. Each label's
colour is SAMPLED from the original pixels so the palette stays identical. Same size preserved
-> splice the sub-texture back into the PVM at its offset.

    repaint_title.py <orig TITLE.PVM> <out TITLE.PVM>
"""
import sys, os, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))  # dc/ format-generic codecs
import pvr_codec as pv
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ARIAL  = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
SUBOFF = 0x180130          # PVRT of sub-texture #3
W = H = 256

# (box=x0,y0,x1,y1  measured from the JP bands), text, fill-fraction of box width
LABELS = [
    ((1, 36, 128, 61),  "COMENÇA",  0.95),
    ((1, 67, 128, 92),  "CONTINUA", 0.95),
    ((1, 98, 180, 123), "INTERNET", 0.90),
    ((4, 192, 124, 218),"OPCIONS",  0.95),
]
# the 2-line Dream Passport note (its own colour sampled from its band)
DPNOTE = [((4, 131, 246, 158), "Cal registrar-se amb"),
          ((4, 159, 246, 187), "el Dream Passport")]
KEEP_TOP = 30              # rows above this (PRESS START BUTTON) are left untouched


def sample_colour(arr, box):
    x0, y0, x1, y1 = box
    reg = arr[y0:y1, x0:x1].reshape(-1, 4)
    op = reg[reg[:, 3] > 128]
    if len(op) == 0:
        return (255, 255, 255)
    # vivid text pixel, not the dark outline: max (max(rgb) + spread)
    score = op[:, :3].max(1).astype(int) + (op[:, :3].max(1).astype(int) - op[:, :3].min(1).astype(int))
    return tuple(int(c) for c in op[score.argmax(), :3])


def fit_size(text, box, fill=0.95, pad=2):
    """Largest font size at which `text` fits `box` (both dims)."""
    x0, y0, x1, y1 = box
    bw, bh = int(((x1 - x0) - 2 * pad) * fill), (y1 - y0)
    sz = bh + 6
    while sz > 6:
        f = ImageFont.truetype(ARIAL, sz)
        l, t, r, b = f.getbbox(text)
        if (r - l) <= bw and (b - t) <= bh:
            break
        sz -= 1
    return sz


def draw_at(im, box, text, colour, sz, pad=2):
    """Draw `text` at a GIVEN size, left-aligned + vertically centred in `box`."""
    x0, y0, x1, y1 = box
    bh = y1 - y0
    f = ImageFont.truetype(ARIAL, sz)
    l, t, r, b = f.getbbox(text); tw, th = r - l, b - t
    tmp = Image.new("RGBA", (tw + 6, th + 6), (0, 0, 0, 0)); td = ImageDraw.Draw(tmp)
    ox, oy = 3 - l, 3 - t
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx or dy:
                td.text((ox + dx, oy + dy), text, font=f, fill=(0, 0, 0, 255))
    td.text((ox, oy), text, font=f, fill=colour + (255,))
    im.alpha_composite(tmp, (max(0, x0), max(0, y0 + (bh - th) // 2 - 3)))


def main():
    src, out = sys.argv[1], sys.argv[2]
    d = bytearray(open(src, "rb").read())
    orig = pv.decode_argb4444(bytes(d), SUBOFF + 16, W, H)
    arr = orig.copy()
    arr[KEEP_TOP:, :, 3] = 0                    # wipe everything below PRESS START BUTTON
    im = Image.fromarray(arr, "RGBA")
    # ONE uniform size across the menu items (like the JP) — fit the tightest box, apply to all,
    # so INTERNET (its JP box is wider) doesn't balloon vs COMENÇA / OPCIONS.
    menu_sz = min(fit_size(text, box, fill) for box, text, fill in LABELS)
    for box, text, fill in LABELS:
        pos = box
        if text == "INTERNET":                      # its JP box is far wider than the others -> centre the
            f = ImageFont.truetype(ARIAL, menu_sz)  # (narrower) Catalan word so it doesn't sit left-shifted
            l, t, r, _ = f.getbbox(text); tw = r - l
            x0, y0, x1, y1 = box
            pos = (x0 + ((x1 - x0) - tw) // 2 - 8, y0, x1, y1)   # centred, then ~half a letter left (operator)
        draw_at(im, pos, text, sample_colour(orig, box), menu_sz)
    # DP registration note (band y131..187) is left BLANK — the shipped title never showed it.
    enc = pv.encode_argb4444(np.array(im))
    assert len(enc) == W * H * 2, (len(enc), W * H * 2)
    d[SUBOFF + 16: SUBOFF + 16 + len(enc)] = enc
    # translation credit on the SKY sub (#0 @0xd0), in the clear right-mid band (the 14-15 marker spot),
    # well away from the © line. The sky renders across the title screen, so this actually shows.
    SKY = 0xd0
    sky = Image.fromarray(pv.decode_argb4444(bytes(d), SKY + 16, 512, 512), "RGBA")
    sd = ImageDraw.Draw(sky); sf = ImageFont.truetype(ARIAL, 20)
    credit = "Traduït per CPC"
    l, t, r, b = sf.getbbox(credit); cx = 420 - (r - l) // 2; cy = 212   # up + right, off COMENÇA
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx or dy: sd.text((cx + dx, cy + dy), credit, font=sf, fill=(0, 0, 0, 255))
    sd.text((cx, cy), credit, font=sf, fill=(255, 90, 90))
    enc2 = pv.encode_argb4444(np.array(sky))
    d[SKY + 16: SKY + 16 + len(enc2)] = enc2
    open(out, "wb").write(d)
    print("wrote %s (%d B)" % (out, len(d)))


if __name__ == "__main__":
    main()
