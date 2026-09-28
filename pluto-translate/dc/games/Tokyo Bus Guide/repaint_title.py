#!/usr/bin/env python3
"""Repaint the title logo in SYSTEM/TITLE.PVM: the game's name on the side of the bus.

    /usr/bin/python3 repaint_title.py <original TITLE.PVM> <output TITLE.PVM> [en|jp] [mod]

    en        the name in English: TOKYO BUS GUIDE, with the translation credit
              on the green band underneath it
    jp        the Japanese logo untouched
    ... mod   renames the game to Tokyo BS Guide: in English the U of BUS is struck
              out in red, in Japanese a red BS is stamped over the バス
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from dc import pvr_codec as P

FONT = "/System/Library/Fonts/Supplemental/Arial Black.ttf"
NARROW = "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf"
GREEN, YELLOW, RED = (0, 136, 68, 255), (255, 204, 0, 255), (218, 16, 16, 255)
BOX = (663, 222, 926, 270)          # the flank of the bus, where the Japanese name was
TEXT = "TOKYO BUS GUIDE"
# A clear band of green runs under the name, between it and the wheel arches, measured
# off the sheet: it is the one place on the bus that can carry a line without covering art.
# The translation says what it is. The mod is not a translation, so it only signs itself,
# in both languages. The English name leaves a clear green band under it; the Japanese logo
# runs lower and does not, so the Japanese mod signs the panel between the wheel arches.
# What each build actually is. The sandbox mod is built on top of the translation
# (LAYERS="translation tokyo-bs-guide tokyo-bs-guide-en"), so it credits both; the
# Japanese mod target excludes the translation, so it only credits the mod.
CREDIT, MOD_EN_CREDIT, MOD_JP_CREDIT = ("TRANSLATION PATCH BY CPC",
                                        "MOD AND TRANSLATION PATCH BY CPC", "MOD BY CPC")
CREDIT_BAND = (665, 254, 924, 271)          # under the English name
MOD_JP_BAND = (714, 268, 873, 289)          # between the wheels, measured clean green

# The memory-card messages, baked into the sheet as blue-on-transparent artwork. They are
# NOT one sprite per line: TITLE_PARTS.DAT draws them as whole dialogs, #77 (528x64) and
# #78 (424x64) holding three lines each, so they read as two messages, not six strings.
# The same sentences exist as real text in the executable (01b19c.src and friends) and are
# already English there; this is only the painted copy.
# Held back from this version: painted, verified, and switched off rather than deleted so
# it can go straight back in. Flip to True to paint them again.
PAINT_MESSAGES = False
MSG_INK = (0, 17, 170, 255)
MSG_PITCH = 22
MESSAGES = [
    # (left x, first baseline y, max width, [lines])
    (1, 681, 520, ["There is not enough space on the memory card to create a file.",
                   "You can still start the game, but you will not be able to save.",
                   "Saving needs 3 free blocks on the memory card."]),
    (1, 745, 420, ["Saving needs a memory card.",
                   "The card needs 3 free blocks.",
                   "You can start the game, but you will not be able to save."]),
    (641, 673, 374, ["Save your progress so far?",
                     "This overwrites the file you chose."]),
]
MSG_BOXES = [(0, 676, 528, 808), (640, 668, 1020, 715)]     # cleared before repainting
JP_BUS = (751, 835)                 # the バス of 東京バス案内, measured off the original


def stamp(img, dr, span, top, bottom):
    """The red BS that renames the game, over the word for bus."""
    x0, x1 = span
    size = bottom - top + 10
    while True:
        font = ImageFont.truetype(FONT, size)
        l, t, r, b = font.getbbox("BS")
        if r - l <= x1 - x0 + 10:
            break
        size -= 1
    dr.text(((x0 + x1 - (r - l)) // 2 - l, (top + bottom - (b - t)) // 2 - t), "BS",
            font=font, fill=RED, stroke_width=3, stroke_fill=(255, 255, 255, 255))


def main(src, dst, lang="en", mod=False):
    d = bytearray(open(src, "rb").read())
    off, w, h, pf = P.find_chunk(bytes(d), 0)
    img = Image.fromarray(P.decode_argb4444(bytes(d), off, w, h))
    dr = ImageDraw.Draw(img)

    if lang == "en":
        dr.rectangle(BOX, fill=GREEN)
        size = 48
        while True:
            font = ImageFont.truetype(FONT, size)
            l, t, r, b = font.getbbox(TEXT)
            if r - l <= BOX[2] - BOX[0] - 6 and b - t <= BOX[3] - BOX[1] - 6:
                break
            size -= 1
        x = (BOX[0] + BOX[2] - (r - l)) // 2 - l
        y = (BOX[1] + BOX[3] - (b - t)) // 2 - t
        dr.text((x, y), TEXT, font=font, fill=YELLOW)
        if mod:                                 # BUS -> BS, by striking the U out
            i = TEXT.index("U")
            x0 = x + font.getbbox(TEXT[:i])[2] - 3   # kerned, so measure the real prefix
            x1 = x + font.getbbox(TEXT[:i + 1])[2] + 3
            for a, c in (((x0, y + t - 4), (x1, y + b + 4)),
                         ((x0, y + b + 4), (x1, y + t - 4))):
                dr.line([a, c], fill=RED, width=6)
    elif mod:                                   # 東京バス案内 -> 東京BS案内
        stamp(img, dr, JP_BUS, 227, 266)

    text, band = ((MOD_JP_CREDIT, MOD_JP_BAND) if lang == "jp" else (MOD_EN_CREDIT, CREDIT_BAND)) \
                 if mod else (CREDIT, CREDIT_BAND)
    if lang == "en" or mod:                     # untouched Japanese signs nothing
        size = 16
        while True:
            cf = ImageFont.truetype(FONT, size)
            cl, ct, cr, cb = cf.getbbox(text)
            if cr - cl <= band[2] - band[0] and cb - ct <= band[3] - band[1]:
                break
            size -= 1
        dr.text(((band[0] + band[2] - (cr - cl)) // 2 - cl,
                 (band[1] + band[3] - (cb - ct)) // 2 - ct), text, font=cf, fill=YELLOW)


    problems = []
    if lang == "en" and PAINT_MESSAGES:
        for x0, y0, x1, y1 in MSG_BOXES:                  # the backdrop here is transparent
            dr.rectangle([x0, y0, x1, y1], fill=(0, 0, 0, 0))
        mf = ImageFont.truetype(NARROW, 18)
        for x, y, room, lines in MESSAGES:
            for i, line in enumerate(lines):
                l, t_, r, b = mf.getbbox(line)
                if r - l > room:
                    problems.append("%r is %dpx, only %d" % (line, r - l, room))
                dr.text((x - l, y + i * MSG_PITCH - t_), line, font=mf, fill=MSG_INK)

    d[off:off + w * h * 2] = P.encode_argb4444(np.array(img))
    open(dst, "wb").write(bytes(d))
    print("wrote %s (%s%s); %s" % (dst, lang, ", mod" if mod else "",
                                   "; ".join(problems) if problems else "messages fit"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "en", "mod" in sys.argv[4:])
