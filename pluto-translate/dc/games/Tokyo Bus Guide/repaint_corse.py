#!/usr/bin/env python3
"""Repaint the nine course cards baked into SYSTEM/CORSE.PVM (the "this course?" screen).

    /usr/bin/python3 repaint_corse.py <original CORSE.PVM> <output CORSE.PVM>

Each card is one sprite quad, but a card taller than the space left in the atlas is
stored as two or three strips (the rects come from CORSE_PARTS.DAT). The script
stitches a card's strips into one 224-wide image, repaints it, and writes the strips
back, so a line never has to know which strip it lands in.

Every line keeps the row band the Japanese used: title, four stat rows and the
description rows are fixed, and only their contents change.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from dc import pvr_codec as P

BOLD = "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf"
BOOK = "/System/Library/Fonts/Supplemental/Arial Narrow.ttf"
BG, TITLE_BLUE, INK = (170, 204, 255, 255), (0, 17, 170, 255), (0, 0, 0, 255)

TITLE = (86, 10, 222, 56)                       # x0, y0, x1, y1 (clear), text centred in it
STATS = [87, 109, 130, 152]                     # top row of each stat band
BAND = 14                                       # band height, all rows
DESC = [181, 203, 224, 246, 267, 289, 311]      # description rows (7th only on tall cards)
LEFT = 14
STAR = (56, 128, 72, 144)                       # a gold star to stamp, from card 0

# Strips per card, in reading order: (x0, y0, x1, y1) in the atlas.
LAYOUT = {
    0: [[(0, 0, 224, 320)], [(224, 0, 448, 320)],
        [(0, 320, 224, 480), (224, 320, 448, 448), (224, 448, 448, 480)]],
    2: [[(0, 0, 224, 320)], [(224, 0, 448, 352)],
        [(0, 320, 224, 480), (224, 352, 448, 480), (224, 480, 448, 512)]],
    3: [[(0, 0, 224, 320)], [(224, 0, 448, 320)],
        [(0, 320, 224, 480), (224, 320, 448, 448), (224, 448, 448, 480)]],
}

WANGAN = "Flat apart from the rise over the Rainbow Bridge, on well-kept, easy roads."
SHINJUKU = ("Flat, but full of lanes and constant lane changes. The stops at Aoyama 1-chome "
            "sit in the middle of turn after turn: a real test.")
OME = ("A climb into the hills: the nearer the end, the sharper the curves and the steeper "
       "the slope. Traffic is very light.")

# chunk -> cards, in the order LAYOUT lists them.
# (title, distance, stops, riders, traffic, difficulty, [paragraphs])
CARDS = {
    0: [("WANGAN DAY", "11.7km", "14", 1, 2, 1,
         [WANGAN, "Light traffic, few riders: one for beginners. Most of them live in the flats nearby."]),
        ("WANGAN EVENING", "11.7km", "14", 3, 2, 2,
         [WANGAN, "Riders are people working in Odaiba, office workers, and couples out on dates."]),
        ("WANGAN NIGHT", "11.7km", "14", 2, 1, 3,
         [WANGAN, "Office workers heading home, couples back from a night out."])],
    2: [("SHINJUKU NIGHT", "7.3km", "22", 3, 4, 4,
         [SHINJUKU, "Riders are office workers on their way home."]),
        ("SHINJUKU EVENING", "7.3km", "22", 5, 5, 4,
         [SHINJUKU, "Traffic and crowds are heaviest now: take the greatest care. Riders are mostly students and shoppers."]),
        ("SHINJUKU DAY", "7.3km", "22", 4, 3, 3,
         [SHINJUKU, "Most riders are out shopping."])],
    3: [("OME DAY", "11.7km", "22", 1, 2, 1, [OME, "Riders are mostly people who live nearby."]),
        ("OME EVENING", "11.7km", "22", 2, 2, 2, [OME, "Plenty of schoolchildren and shoppers."]),
        ("OME NIGHT", "11.7km", "22", 1, 1, 2, [OME, "Mostly commuters heading home."])],
}


def stitch(img, strips):
    h = sum(y1 - y0 for _, y0, _, y1 in strips)
    card = Image.new("RGBA", (224, h))
    y = 0
    for (x0, y0, x1, y1) in strips:
        card.paste(img.crop((x0, y0, x1, y1)), (0, y))
        y += y1 - y0
    return card


def unstitch(img, card, strips):
    y = 0
    for (x0, y0, x1, y1) in strips:
        img.paste(card.crop((0, y, 224, y + y1 - y0)), (x0, y0))
        y += y1 - y0


def wrap(draw, text, font, width):
    lines, line = [], ""
    for word in text.split():
        trial = (line + " " + word).strip()
        if draw.textlength(trial, font=font) <= width:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def paint(card, star, size, usable, title, dist, stops, riders, traffic, diff, paras):
    dr = ImageDraw.Draw(card)
    bold = ImageFont.truetype(BOLD, 16)
    book = ImageFont.truetype(BOOK, size)
    head = ImageFont.truetype(BOLD, 26)

    dr.rectangle(TITLE, fill=BG)
    l, t, r, b = head.getbbox(title)
    while r - l > TITLE[2] - TITLE[0] - 4:
        head = ImageFont.truetype(BOLD, head.size - 1)
        l, t, r, b = head.getbbox(title)
    dr.text(((TITLE[0] + TITLE[2] - (r - l)) // 2 - l, 14 - t), title, font=head, fill=TITLE_BLUE)

    def row(i, parts):
        """parts: strings and star counts, laid out left to right from x=LEFT."""
        y = STATS[i]
        dr.rectangle((0, y - 4, 224, y + BAND + 3), fill=BG)
        x = LEFT
        for part in parts:
            if isinstance(part, int):
                for _ in range(part):
                    card.paste(star, (int(x), y - 2))
                    x += star.width
            else:
                dr.text((x, y - 1), part, font=bold, fill=INK)
                x += dr.textlength(part, font=bold) + 5
        return x

    # Five stars of riders and five of traffic never share a row in English, so
    # distance and stops share the first row instead and traffic gets its own.
    x = row(0, ["DISTANCE", dist])
    dr.text((max(x + 10, 120), STATS[0] - 1), "STOPS  " + stops, font=bold, fill=INK)
    row(1, ["RIDERS", riders])
    row(2, ["TRAFFIC", traffic])
    row(3, ["DIFFICULTY", diff])

    rows = [y for y in DESC if y + BAND < usable]
    dr.rectangle((0, rows[0] - 4, 224, rows[-1] + BAND + 2), fill=BG)
    lines = []
    for para in paras:
        lines += wrap(dr, para, book, 224 - 2 * LEFT)
    if len(lines) > len(rows):
        raise SystemExit("%s: %d lines of description, only %d rows" % (title, len(lines), len(rows)))
    for y, line in zip(rows, lines):
        dr.text((LEFT, y - 1), line, font=book, fill=INK)


def usable_height(img, strips):
    """How much of a stitched card may be written to.

    A card's last strip can be empty in the original (card 3 of each sheet ends early),
    and the game still draws it somewhere, so anything painted there shows up under a
    different card. Stop at the end of the last strip that has ink."""
    height = 0
    for (x0, y0, x1, y1) in strips:
        band = np.array(img.crop((x0, y0, x1, y1)).convert("L"))
        if band.min() < 110:                     # the strip carries text
            height += y1 - y0
        else:
            break
    return height


def desc_size(usable):
    """One description size for all nine cards: the largest that fits every one.

    usable: {(chunk, card index): height that may be written to}."""
    dr = ImageDraw.Draw(Image.new("RGBA", (224, 320)))
    for size in range(16, 10, -1):
        font = ImageFont.truetype(BOOK, size)
        ok = True
        for chunk, cards in CARDS.items():
            for i, spec in enumerate(cards):
                rows = len([y for y in DESC if y + BAND < usable[(chunk, i)]])
                lines = sum(len(wrap(dr, para, font, 224 - 2 * LEFT)) for para in spec[6])
                ok = ok and lines <= rows
        if ok:
            return size
    raise SystemExit("no description size fits every card")


# The route line on the black card before a run. Its glyphs live down the right edge of
# the atlas, two per 64-wide row, and the game draws the rows left to right, so the pieces
# below ARE the line in order: render the English across them and slice it back.
ROUTES = {
    0: ([(448, 0, 504, 40), (448, 40, 504, 80), (448, 80, 504, 120), (448, 120, 504, 160),
         (448, 160, 504, 200), (448, 200, 504, 240), (448, 240, 488, 280)],
        "Kokusai-Tenjijo ~ Hamamatsucho",
        [(448, 280, 504, 312), (488, 240, 504, 272)], "Niji 01"),
    2: ([(448, 0, 504, 40), (448, 40, 504, 80), (448, 80, 504, 120), (448, 120, 504, 160),
         (448, 160, 480, 200)],
        "Nakanohashi ~ Shinjuku",
        [(448, 200, 504, 232), (448, 232, 464, 264)], "Ta 70"),
    3: ([(448, 0, 504, 40), (448, 40, 504, 80), (448, 80, 504, 120), (448, 120, 504, 160),
         (448, 160, 488, 200)],
        "Higashi-Ome ~ Kaminariki",
        [(448, 200, 504, 232), (448, 232, 472, 264)], "Ume 76"),
}


PROMPT = (252, 374, 506, 406)   # "このコースでいいですか?" in chunk 1: black glyphs, white edge
SEAM = 1                        # columns lost on screen where two pieces meet


def prompt(img, text="Take this course?"):
    """The line under the card. Black with a white edge, centred where the Japanese was."""
    dr = ImageDraw.Draw(img)
    dr.rectangle(PROMPT, fill=(0, 0, 0, 0))
    font = ImageFont.truetype(BOLD, 30)
    l, t, r, b = font.getbbox(text)
    while r - l > PROMPT[2] - PROMPT[0] - 6 or b - t > PROMPT[3] - PROMPT[1] - 4:
        font = ImageFont.truetype(BOLD, font.size - 1)
        l, t, r, b = font.getbbox(text)
    dr.text(((PROMPT[0] + PROMPT[2] - (r - l)) // 2 - l,
             (PROMPT[1] + PROMPT[3] - (b - t)) // 2 - t),
            text, font=font, fill=INK, stroke_width=2, stroke_fill=(255, 255, 255, 255))


def place(text, font, dr, widths):
    """Character positions across the pieces, or None if the text will not fit.

    A join between two pieces loses a column or two on screen, so no letter may straddle
    one: each piece takes whole letters only, and its leftover space is spread evenly
    between them, which keeps the line evenly set rather than gappy."""
    chars, out, base = list(text), [], 0.0
    for w in widths:
        room, taken, used = w - 2 * SEAM, [], 0.0
        while chars:
            adv = dr.textlength(chars[0], font=font)
            if used + adv > room:
                break
            taken.append((chars.pop(0), adv))
            used += adv
        if not taken:
            return None
        gap = (room - used) / max(len(taken) - 1, 1) if chars else 0.0
        x = base + SEAM
        for ch, adv in taken:
            out.append((x, ch))
            x += adv + gap
        base += w
    return None if chars else out


def line(img, pieces, text):
    """Draw text across pieces that the game lays out side by side, white on nothing.

    A row of the atlas is 56 wide (two 28-pixel glyph cells); the 8 columns of padding
    after it are not drawn, which is why the pieces stop at 504 and not at the edge."""
    widths = [x1 - x0 for x0, _, x1, _ in pieces]
    width, height = sum(widths), max(y1 - y0 for _, y0, _, y1 in pieces)
    strip = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    dr = ImageDraw.Draw(strip)

    for size in range(height, 8, -1):               # the biggest size that still fits
        font = ImageFont.truetype(BOLD, size)
        spots = place(text, font, dr, widths)
        if spots:
            break
    else:
        raise SystemExit("%r does not fit the route line" % text)

    l, t, r, b = font.getbbox(text)
    top = (height - (b - t)) // 2 - t
    for x, ch in spots:
        dr.text((x, top), ch, font=font, fill=(255, 255, 255, 255),
                stroke_width=1, stroke_fill=(0, 0, 0, 255))

    x = 0
    for (x0, y0, x1, y1) in pieces:
        img.paste((0, 0, 0, 0), (x0, y0, x1, y1))
        img.paste(strip.crop((x, 0, x + x1 - x0, y1 - y0)), (x0, y0))
        x += x1 - x0


def main(src, dst):
    d = bytearray(open(src, "rb").read())
    usable, sheets = {}, {}
    for chunk in CARDS:
        off, w, h, pf = P.find_chunk(bytes(d), chunk)
        sheets[chunk] = Image.fromarray(P.decode_argb4444(bytes(d), off, w, h))
        for i, strips in enumerate(LAYOUT[chunk]):
            usable[(chunk, i)] = usable_height(sheets[chunk], strips)
    size = desc_size(usable)
    print("one description size for all cards: %dpt" % size)
    star = None
    for chunk, cards in CARDS.items():
        off, w, h, pf = P.find_chunk(bytes(d), chunk)
        img = sheets[chunk]
        if star is None:
            star = img.crop(STAR)
        pieces, name, num_pieces, number = ROUTES[chunk]
        line(img, pieces, name)
        line(img, num_pieces, number)
        for i, (strips, spec) in enumerate(zip(LAYOUT[chunk], cards)):
            card = stitch(img, strips)
            paint(card, star, size, usable[(chunk, i)], *spec)
            unstitch(img, card, strips)
        d[off:off + w * h * 2] = P.encode_argb4444(np.array(img))
    off, w, h, pf = P.find_chunk(bytes(d), 1)
    img = Image.fromarray(P.decode_argb4444(bytes(d), off, w, h))
    prompt(img)
    d[off:off + w * h * 2] = P.encode_argb4444(np.array(img))

    open(dst, "wb").write(bytes(d))
    print("wrote %s (%d bytes)" % (dst, len(d)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
