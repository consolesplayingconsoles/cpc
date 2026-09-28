#!/usr/bin/env python3
"""Repaint the controller help in SYSTEM/MENU.PVM: the OPTION screen's pad and wheel.

    /usr/bin/python3 repaint_menu.py <original MENU.PVM> <output MENU.PVM> [preview.png]

Every callout is a Japanese label on a leader line pointing into the artwork. The artwork
and the leaders are left exactly as they are; only the label boxes are cleared and reset in
English, each anchored on the edge its leader attaches to, so no label grows into the
picture it points at. Boxes were measured off the sheet by finding the label blue
(0,17,170) and dropping the long thin runs, which are the leaders.

Wording matches the rest of the translation: ウインカー is "indicator", not "blinker".
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from dc import pvr_codec as P

# Narrow, like the course cards: the pad and the wheel each carry a "Left indicator"
# and at a normal width the two run into each other across the middle of the plate.
FONT = "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf"
INK = (0, 17, 170, 255)

# (x0, y0, x1, y1, align, lines) -- align is the edge the leader attaches to:
#   "L" leader comes from the left, so the text starts at x0 and grows right
#   "R" leader leaves to the right, so the text ends at x1 and grows left
#   "C" leader drops straight down, so the text stays centred
LABELS = [
    (258, 690, 334, 717, "L", ["Left indicator", "ON/OFF"]),      # pad
    (371, 690, 447, 717, "R", ["Left indicator", "ON/OFF"]),      # wheel
    (609, 690, 685, 717, "L", ["Right indicator", "ON/OFF"]),     # wheel, nudged 4px
    (486, 700, 561, 711, "C", ["Steering"]),                      # wheel
    ( 46, 726,  95, 736, "R", ["Steering"]),                      # pad stick
    (257, 742, 333, 754, "L", ["Change view"]),                   # pad
    (610, 754, 682, 783, "L", ["Announcement", "Close doors"]),   # wheel, nudged 4px
    (371, 763, 446, 774, "R", ["Change view"]),                   # wheel
    (258, 772, 334, 799, "L", ["Right indicator", "ON/OFF"]),     # pad, nudged 4px
    ( 35, 788,  94, 816, "R", ["Up: forward", "Down: back"]),     # pad d-pad, and "back"
                                                                  # because "reverse" runs off
                                                                  # the left edge of the plate
    (410, 810, 445, 821, "R", ["Pause"]),                         # wheel
    (258, 826, 330, 855, "L", ["Announcement", "Close doors"]),   # pad, nudged 4px
    ( 59, 841,  94, 852, "R", ["Pause"]),                         # pad
    (397, 905, 446, 916, "R", ["Accelerator"]),                   # pedals
    (609, 905, 657, 916, "L", ["Brake"]),                         # pedals
    ( 45, 955,  94, 966, "R", ["Accelerator"]),                   # pad underside
    (256, 955, 305, 967, "L", ["Brake"]),                         # pad underside
]
PANEL = (0, 678, 967, 999)          # the light blue plate the callouts live on

# The A pages use the callouts above. B and C remap the buttons and draw a second set of
# labels from a packed strip higher on the sheet: eight two-line sprites, whose rects come
# from MENU_PARTS.DAT (#50-#57) rather than from measuring pixels. #57 is empty boxes, not
# text, so it is left alone. These boxes are only 80-88px wide against the callouts' 260,
# which is why the lane-change lines are abbreviated.
STRIP_CELLS = [                     # cleared whole, from MENU_PARTS.DAT #50-#56
    (584, 424, 672, 456), (672, 424, 752, 456), (752, 424, 832, 456), (832, 424, 912, 456),
    (584, 456, 672, 488), (672, 456, 752, 488), (752, 456, 832, 488),
]
# Each English line goes exactly where its Japanese line's ink was: same left edge, same
# top, and no wider than the Japanese occupied. The game's rects are not the cell rects
# (it samples past them, which is why placing by cell produced stray letters from the
# neighbour), so matching the original ink footprint is the only placement that is safe
# whatever rect it really uses. Note #53 is a single line sitting centred in its cell, and
# #56 is indented: both measured off the sheet, not assumed.
STRIP_LINES = [
    (586, 426, 77, "Left indicator"),  (587, 443, 57, "ON/OFF"),         # #50
    (674, 425, 63, "Announce"),    (674, 442, 73, "Close doors"),    # #52
    (753, 425, 77, "Right indicator"), (753, 442, 62, "Lane right"),  # #54
    (841, 426, 62, "Indicator"),       (847, 441, 50, "Lane"),    # #56
    (586, 458, 77, "Right indicator"), (587, 475, 57, "ON/OFF"),         # #51
    (674, 467, 76, "Change view"),                                       # #53
    (752, 457, 77, "Left indicator"),  (752, 473, 63, "Lane left"),  # #55
]


def main(src, dst, preview=None):
    d = bytearray(open(src, "rb").read())
    off, w, h, pf = P.find_chunk(bytes(d), 0)
    img = Image.fromarray(P.decode_argb4444(bytes(d), off, w, h))
    dr, px = ImageDraw.Draw(img), img.load()

    # The plate is not a flat colour: it is a pixel dither of four shades, so painting a
    # label out with one fill leaves a visibly smoother patch. Instead each label box is
    # covered with a piece of clean plate copied from nearby, at an even offset so the
    # dither stays in phase.
    PLATE_COLOURS = {(153, 204, 255, 255), (153, 187, 255, 255),
                     (170, 204, 255, 255), (170, 187, 255, 255)}

    def is_clean(x0, y0, x1, y1):
        if x0 < PANEL[0] or y0 < PANEL[1] or x1 > PANEL[2] or y1 > PANEL[3]:
            return False
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if px[x, y] not in PLATE_COLOURS:
                    return False
        return True

    def cover(x0, y0, x1, y1):
        """Patch the box with clean plate from the nearest in-phase source."""
        w, h = x1 - x0 + 1, y1 - y0 + 1
        for dist in range(2, 260, 2):
            for dy, dx in ((dist, 0), (-dist, 0), (0, dist), (0, -dist)):
                sx, sy = x0 + dx, y0 + dy
                if is_clean(sx, sy, sx + w - 1, sy + h - 1):
                    img.paste(img.crop((sx, sy, sx + w, sy + h)), (x0, y0))
                    return True
        return False

    font = ImageFont.truetype(FONT, 13)   # matches the strip, and fits the 80x32
                                          # slots the game overlays B/C labels into
    problems, drawn = [], []
    for x0, y0, x1, y1, align, lines in LABELS:
        pad = 2
        if not cover(x0 - pad, y0 - pad, x1 + pad, y1 + pad):
            problems.append("no clean plate to patch the box at (%d,%d)" % (x0, y0))
        step = (y1 - y0 + 1) // len(lines)
        for i, line in enumerate(lines):
            l, t, r, b = font.getbbox(line)
            wpx = r - l
            if align == "L":
                x = x0
            elif align == "R":
                x = x1 - wpx
            else:
                x = (x0 + x1 - wpx) // 2
            if x < PANEL[0] or x + wpx > PANEL[2]:
                problems.append("%r runs off the plate (x %d..%d)" % (line, x, x + wpx))
            ly = y0 + i * step
            for ox, ox1, oy, olabel in drawn:          # labels must not touch each other
                if abs(oy - ly) < 12 and x - 4 < ox1 and ox < x + wpx + 4:
                    problems.append("%r collides with %r at y=%d" % (line, olabel, ly))
            drawn.append((x, x + wpx, ly, line))
            # No antialiasing: the sheet is ARGB4444, and the grey edge pixels quantise
            # into stray dots that a CRT shows and an LCD hides. Render the glyphs to a
            # mask, threshold it, and paste flat ink through it, as the Japanese was.
            m = font.getmask(line, mode="L")
            g = Image.frombytes("L", m.size, bytes(m)).point(lambda v: 255 if v >= 128 else 0)
            # getmask's top row IS the glyph bbox top, so subtracting t lifts the text 3px
            # above the box and out of the 80x32 slot the game overlays B/C labels into.
            img.paste(INK[:3], (x - l, y0 + i * step), g.convert("1"))

    for x0, y0, x1, y1 in STRIP_CELLS:
        if not cover(x0, y0, x1 - 1, y1 - 1):
            for y in range(y0, y1):
                for x in range(x0, x1):
                    img.putpixel((x, y), (153, 204, 255, 255) if (x + y) % 2 == 0
                                         else (153, 187, 255, 255))
    # One size for the whole strip: the largest that keeps every line inside the width its
    # Japanese used. "Announcement" in 63px and "Change lane R" in 62px set the limit.
    size = 14
    while size > 6:
        f = ImageFont.truetype(FONT, size)
        if all(f.getbbox(s)[2] - f.getbbox(s)[0] <= wmax for _, _, wmax, s in STRIP_LINES):
            break
        size -= 1
    strip_font = ImageFont.truetype(FONT, size)
    print("   strip labels at %dpt" % size)
    for x, y, wmax, line in STRIP_LINES:
        l, tp, r, b = strip_font.getbbox(line)
        m = strip_font.getmask(line, mode="L")
        g = Image.frombytes("L", m.size, bytes(m)).point(lambda v: 255 if v >= 128 else 0)
        img.paste(INK[:3], (x - l, y), g.convert("1"))

    d[off:off + w * h * 2] = P.encode_argb4444(np.array(img))
    if len(d) != os.path.getsize(src):
        raise SystemExit("file size changed")
    open(dst, "wb").write(bytes(d))
    if preview:
        img.convert("RGB").crop(PANEL).save(preview)
    print("wrote %s; %s" % (dst, "; ".join(problems) if problems else "every label fits the plate"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
