#!/usr/bin/env python3
"""Repaint the main menu (OBJz_mainmenu): on each button with a DDG64 match, the Japanese label and Taito's small
English subtitle become one large label in Zoinkity's English. Buttons without a match are left as they are.

    repaint_mainmenu.py <SPRITE.LST> <orig TBL.ROM> <orig CG1.ROM> <out TBL.ROM> <out CG1.ROM> [preview.png]

The menu is a 32x30 tilemap of 16x16 tiles in CG1.ROM entries 86-88 (plain ARGB1555, so it re-encodes
exactly), and no other sprite uses its tiles. So: render the record, repaint, cut the new picture back into
tiles, deduplicate, and give each new tile a slot. A tile that already exists keeps its id; changed tiles
take the menu's own freed slots, then the free slots no record uses. The record is rewritten in place and
both files keep their sizes, so the disc can be patched in place.

Only the grey text pixels right of each coloured bar are touched: the frames, bars and numbers are kept.
Wording is Zoinkity's DDG64 English only (LABELS below); buttons without a DDG64 match keep their original art.
"""
import os, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from dc import pvr_codec as P
import ddg_assets as A

RECORD = "OBJz_mainmenu"
# A port (CLAUDE.md section 11): Zoinkity's DDG64 English, matched on the same Japanese, texture number noted.
# "operator" = the operator's own curation of a gap. None = still a gap: the button's original art (Japanese +
# Taito's small English) is left untouched.
LABELS = ["Arcade Mode",          # アーケードモード 1019
          "Options",              # ゲーム設定       1021
          "Rankings",             # ランキングを見る 1022
          "Load & Save",          # ロード・セーブ   operator
          None]                   # LOVE特急こまち   no DDG64 match
FONT = "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf"
BG, FG = 8, 189                 # the buttons' near-black and text grey
BUTTON_H = 96
TEXT_X0, TEXT_X1 = 100, 498     # right of the coloured bar, inside the frame
TEXT_Y0, TEXT_Y1 = 3, 93
CAP_H = 48                      # cap height, about the Japanese glyphs' height
SS = 4                          # supersampling for the antialiasing


def label(text, w, h):
    """-> (h, w) float coverage of `text`, centred, cap height CAP_H, squeezed to fit w."""
    font = ImageFont.truetype(FONT, int(CAP_H * SS / 0.716))        # Arial Narrow cap height = 0.716 em
    l, t, r, b = font.getbbox(text)
    img = Image.new("L", (r - l + 8, b - t + 8)); ImageDraw.Draw(img).text((4 - l, 4 - t), text, 255, font=font)
    img = img.crop(img.getbbox())
    tw = min(img.width / SS, w - 16)
    img = img.resize((int(round(tw)), int(round(img.height / SS))), Image.LANCZOS)
    out = np.zeros((h, w))
    x, y = (w - img.width) // 2, (h - img.height) // 2
    out[y:y + img.height, x:x + img.width] = np.asarray(img) / 255.0
    return out


def repaint(rgba):
    out = rgba.copy()
    for i, text in enumerate(LABELS):
        if text is None:
            continue
        y0, y1 = i * BUTTON_H + TEXT_Y0, i * BUTTON_H + TEXT_Y1
        reg = out[y0:y1, TEXT_X0:TEXT_X1]
        c = reg[..., :3].astype(int)
        grey = (np.ptp(c, axis=-1) < 12) & (reg[..., 3] == 255)     # text, its antialiasing, and the black
        reg[grey, :3] = BG
        cov = label(text, TEXT_X1 - TEXT_X0, y1 - y0)
        v = (BG + (FG - BG) * cov).round().astype(np.uint8)
        ink = cov > 0
        reg[ink, 0] = reg[ink, 1] = reg[ink, 2] = v[ink]
    return out


def main(lst_p, tbl_p, cg_p, out_tbl, out_cg, preview=None):
    names = {a: (o, s) for a, o, s in A.lst(open(lst_p, encoding="latin-1").read())}
    tbl = bytearray(open(tbl_p, "rb").read()); cg = bytearray(open(cg_p, "rb").read())
    ents = A.rom2(bytes(cg))
    off, _ = names[RECORD]
    w, h, ids = A.tilemap(bytes(tbl), off)

    texs = sorted({t // 256 for t in ids})
    u16 = {}                                    # texture -> (256, 256) u16, untwiddled
    for tx in texs:
        o = ents[tx][0]
        assert cg[o + 8] == 0 and cg[o + 9] == 1, "texture %d is not twiddled ARGB1555" % tx
        u16[tx] = P._twiddled_u16(bytes(cg), o + 16, 256, 256).copy()

    def tile(t):
        tx, p = t // 256, t % 256
        return u16[tx][(p // 16) * 16:(p // 16) * 16 + 16, (p % 16) * 16:(p % 16) * 16 + 16]

    rgba = np.zeros((h * 16, w * 16, 4), np.uint8)
    for k, t in enumerate(ids):
        rgba[(k // w) * 16:(k // w) * 16 + 16, (k % w) * 16:(k % w) * 16 + 16] = P._unpack(tile(t), 0)
    new = repaint(rgba)
    packed = P.pack_argb1555(new)

    # every tile id any record uses, to find the slots nobody does
    used = set()
    for a, (o, s) in names.items():
        used.update(A.tilemap(bytes(tbl), o)[2])
    free = [tx * 256 + p for tx in texs for p in range(256) if tx * 256 + p not in used]
    existing = {tile(t).tobytes(): t for t in sorted(set(ids))}

    want = []                                   # new tile bytes per position
    for k in range(w * h):
        want.append(packed[(k // w) * 16:(k // w) * 16 + 16, (k % w) * 16:(k % w) * 16 + 16].copy())
    keep = {}                                   # tile bytes -> id, for tiles that already exist unchanged
    for b in (x.tobytes() for x in want):
        if b in existing:
            keep[b] = existing[b]
    pool = [t for t in sorted(set(ids)) if t not in keep.values()] + free
    new_ids, placed = [], dict(keep)
    for x in want:
        b = x.tobytes()
        if b not in placed:
            if not pool:
                raise SystemExit("out of tile slots: need more than %d" % (len(set(ids)) + len(free)))
            t = pool.pop(0); placed[b] = t
            tx, p = t // 256, t % 256
            u16[tx][(p // 16) * 16:(p // 16) * 16 + 16, (p % 16) * 16:(p % 16) * 16 + 16] = x
        new_ids.append(placed[b])
    print("%s: %d unique tiles (was %d), %d kept, %d rewritten, %d slots left" % (
        RECORD, len(placed), len(set(ids)), len(keep), len(placed) - len(keep), len(pool)))

    struct.pack_into("<%dH" % len(new_ids), tbl, off + 2, *new_ids)
    for tx in texs:
        o = ents[tx][0]
        cg[o + 16:o + 16 + 256 * 256 * 2] = P._untwiddle_to_bytes(u16[tx], 256, 256)
    open(out_tbl, "wb").write(tbl); open(out_cg, "wb").write(cg)
    if preview:
        Image.fromarray(P._unpack(packed, 0), "RGBA").save(preview)   # as the game will show it (5-bit colour)


if __name__ == "__main__":
    if len(sys.argv) not in (6, 7):
        sys.exit(__doc__)
    main(*sys.argv[1:])
