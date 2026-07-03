#!/usr/bin/env python3
"""Repaint the mini-game DIALOGUE -> Catalan: Mama's praise/scold speech bubbles, the gold
race flashes (用意して/スタート/終了), and MN3's `この位置に かたづけてね` arrow hint.

Runs AFTER repaint_mn_instr.py, on the committed textures (counter + instruction boxes already
baked), and adds these. Bubbles are green boards with Mama's portrait on the left; we erase only
the text area to the RIGHT of the portrait (per-row median of the board-green pixels, so the
vertical gradient survives and the face is untouched) and redraw the Catalan, auto-fitting the font
so every line stays inside the bubble. Flashes/arrow sit on the transparent atlas bg (alpha erase).

    repaint_mn_dialog.py <in-dir> <out-dir>     # reads/writes MN1.PVM MN2.PVM MN3.PVM
"""
import sys, os, struct, re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))  # dc/ codecs
import pvr_codec as pv
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ARIAL = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
WHITE = (245, 245, 245)

# Speech bubbles: file -> [ (chunk, (text_x0, text_x1), [(cy, "line"), ...]) ]. cy = measured band centre.
BUBBLES = {
    "MN1.PVM": [
        (3, (166, 484), [(142, "Que bé, Doraemon!"), (174, "Fas molt bon massatge"), (206, "Menja molts pastissets")]),
        (3, (166, 484), [(380, "Gràcies, Doraemon"), (412, "Té, pastissets per a tu")]),
        (4, (166, 484), [(366, "Escolta, Doraemon…"), (399, "No t'esforces?"), (433, "Doncs res de pastissets!")]),
    ],
    "MN2.PVM": [
        (1, (166, 484), [(365, "T'has escaquejat!"), (399, "Avui et quedes"), (433, "sense pastissets")]),
        (2, (166, 484), [(157, "Ostres, que net!"), (191, "Gràcies, Doraemon")]),
        (2, (166, 484), [(376, "Bona feina, Doraemon"), (410, "Ha quedat prou net, oi?")]),
    ],
    "MN3.PVM": [
        (1, (166, 484), [(380, "Això no està endreçat…"), (412, "Res de berenar")]),
        (2, (166, 484), [(143, "Que net ha quedat!"), (173, "Gràcies, Doraemon"), (203, "Té, per berenar")]),
        (2, (166, 484), [(367, "Gràcies, Doraemon"), (397, "Torna a ajudar-me, eh?"), (427, "Té, pastissets")]),
    ],
}


# Gold text (race flashes 用意/スタート/終了, and MN3's この位置に/かたづけてね arrow hint): a vertical
# yellow->orange gradient with a thick dark outline, on the transparent bg (alpha erase). file ->
# [ (chunk, (erase box), [(cy, size, "line")]) ].
GOLD_TOP, GOLD_BOT = (238, 238, 119), (238, 170, 68)
FLASH = [(87, 54, "Llestos…"), (169, 54, "Ja!!"), (248, 54, "Fi!!")]
FLASH_ERASE = (0, 38, 492, 292)                       # full width: 用意して〜/スタート！！/終了〜！！ run long
GOLD = {
    "MN1.PVM": [(4, FLASH_ERASE, FLASH)],
    "MN2.PVM": [(4, FLASH_ERASE, FLASH)],
    "MN3.PVM": [(4, FLASH_ERASE, FLASH),
                (4, (0, 286, 492, 416), [(317, 42, "Desa-ho"), (380, 42, "aquí")])],
}


def draw_gold(im, x_left, cy, text, size):
    f = ImageFont.truetype(ARIAL, size)
    l, t, r, b = f.getbbox(text)
    tw, th = r - l, b - t
    W2, H2 = tw + 16, th + 16
    ox, oy = 8 - l, 8 - t
    base = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    bd = ImageDraw.Draw(base)
    for dx in range(-3, 4):                           # thick dark outline
        for dy in range(-3, 4):
            if (dx or dy) and dx * dx + dy * dy <= 9:
                bd.text((ox + dx, oy + dy), text, font=f, fill=(50, 25, 0, 255))
    mask = Image.new("L", (W2, H2), 0)
    ImageDraw.Draw(mask).text((ox, oy), text, font=f, fill=255)
    ma = np.array(mask)
    fr = np.clip((np.arange(H2) - oy) / max(1, th), 0, 1)
    grad = np.zeros((H2, W2, 4), np.uint8)
    for i in range(3):
        grad[:, :, i] = (GOLD_TOP[i] + (GOLD_BOT[i] - GOLD_TOP[i]) * fr).astype(np.uint8)[:, None]
    grad[:, :, 3] = ma
    base.alpha_composite(Image.fromarray(grad, "RGBA"))
    im.alpha_composite(base, (x_left - 8, cy - H2 // 2))


def chunk_offsets(d):
    return [m.start() for m in re.finditer(b"PVRT", d)]


def outline_text(im, x_left, cy, text, size, fill):
    f = ImageFont.truetype(ARIAL, size)
    l, t, r, b = f.getbbox(text)
    tw, th = r - l, b - t
    tmp = Image.new("RGBA", (tw + 12, th + 12), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    ox, oy = 6 - l, 6 - t
    for dx in (-2, -1, 0, 1, 2):
        for dy in (-2, -1, 0, 1, 2):
            if dx or dy:
                td.text((ox + dx, oy + dy), text, font=f, fill=(0, 0, 0, 255))
    td.text((ox, oy), text, font=f, fill=fill + (255,))
    im.alpha_composite(tmp, (x_left - 6, cy - (th + 12) // 2))


def fit_size(lines, avail_w, base=24, lo=15):
    for sz in range(base, lo - 1, -1):
        f = ImageFont.truetype(ARIAL, sz)
        if all((f.getbbox(t)[2] - f.getbbox(t)[0]) <= avail_w for t in lines):
            return sz
    return lo


def erase_board_region(arr, x0, x1, y0, y1):
    """Erase text keeping the vertical board gradient: per row, fill with the median of that row's
    board-green pixels (glyphs are white/coloured -> excluded), so the face and gradient stay intact."""
    R, G, B = arr[..., 0].astype(int), arr[..., 1].astype(int), arr[..., 2].astype(int)
    for y in range(y0, y1):
        seg = arr[y, x0:x1]
        r, g, b = R[y, x0:x1], G[y, x0:x1], B[y, x0:x1]
        board = seg[(g > r + 10) & (g > b + 3) & (g > 55)]
        if len(board):
            fill = np.median(board[:, :3], 0).astype(np.uint8)
            arr[y, x0:x1, :3] = fill
            arr[y, x0:x1, 3] = 255


def build(d, bubbles, golds):
    out = bytearray(d)
    offs = chunk_offsets(d)
    chunks = {}                                       # chunk index -> {"b": [...], "g": [...]}
    for ci, xr, lines in bubbles:
        chunks.setdefault(ci, {}).setdefault("b", []).append((xr, lines))
    for ci, eb, lines in golds:
        chunks.setdefault(ci, {}).setdefault("g", []).append((eb, lines))
    for ci, ops in chunks.items():
        off = offs[ci]
        W, H = struct.unpack_from("<HH", d, off + 12)
        arr = pv.decode_argb4444(bytes(d), off + 16, W, H)
        for (x0, x1), lines in ops.get("b", []):      # bubble text: board-green refill erase
            ys = [cy for cy, _ in lines]
            erase_board_region(arr, x0, x1, min(ys) - 22, max(ys) + 22)
        for (ex0, ey0, ex1, ey1), _lines in ops.get("g", []):   # gold text: alpha erase (transparent bg)
            arr[ey0:ey1, ex0:ex1, 3] = 0
        im = Image.fromarray(arr, "RGBA")
        for (x0, x1), lines in ops.get("b", []):
            size = fit_size([t for _, t in lines], (x1 - x0) - 12)
            for cy, t in lines:
                outline_text(im, x0 + 8, cy, t, size, WHITE)
        for (ex0, _ey0, _ex1, _ey1), lines in ops.get("g", []):
            for cy, size, t in lines:
                draw_gold(im, ex0 + 8, cy, t, size)
        enc = pv.encode_argb4444(np.array(im))
        assert len(enc) == W * H * 2, (len(enc), W * H * 2)
        out[off + 16: off + 16 + len(enc)] = enc
    return bytes(out)


def main():
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    for fn in BUBBLES:
        d = open(os.path.join(src, fn), "rb").read()
        patched = build(d, BUBBLES.get(fn, []), GOLD.get(fn, []))
        assert len(patched) == len(d), (fn, len(patched), len(d))
        open(os.path.join(out, fn), "wb").write(patched)
        print("  %s: %d bubbles + %d gold groups (%d B)" % (
            fn, len(BUBBLES.get(fn, [])), len(GOLD.get(fn, [])), len(patched)))


if __name__ == "__main__":
    main()
