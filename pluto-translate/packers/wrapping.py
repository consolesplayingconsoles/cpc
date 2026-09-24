"""Line wrapping shared by the packers that fill a fixed-width box.

Split out because the same greedy wrap lived in `nullsplit` (dialogue) and `itemtbl` (gadget
descriptions), and the hyphen rule below had to land in both: the operator's hardware QA caught
`great-great-grandfather` running off the right edge of the dialogue box, and the item table has
`fourth-dimensional` in the same shape.
"""


def hyphen_pieces(w, width):
    """A word too long for the box, split after its hyphens so it CAN break.

    `great-great-grandfather` is 23 cells in a 15-cell box with no space to break at, so it ran
    off the edge on hardware -- the off-screen text the reviews reported. ONLY over-long words are
    split: every word that already fits keeps its line exactly as today, so no existing wrap (or
    byte budget) moves. The hyphen stays on the LEFT piece, where a reader expects it.
    """
    if len(w) <= width or "-" not in w:
        return [w]
    parts = w.split("-")
    if not all(parts):                      # a lone "-" or a leading/trailing dash: leave it alone
        return [w]
    return [p + "-" for p in parts[:-1]] + [parts[-1]]


def wrap(text, width):
    """Greedy wrap to `width` cells, breaking over-long hyphenated words (see `hyphen_pieces`)."""
    out, cur = [], ""
    for w in text.split(" "):
        for i, piece in enumerate(hyphen_pieces(w, width)):
            joint = "" if (i and cur.endswith("-")) else " "   # hyphen pieces join with no space
            if not cur:
                cur = piece
            elif len(cur) + len(joint) + len(piece) <= width:
                cur += joint + piece
            else:
                out.append(cur); cur = piece
    if cur:
        out.append(cur)
    return out
