#!/usr/bin/env python3
"""Repaint flagged sprite records (tiles in CG2.ROM) with Zoinkity's Densha de Go! 64 English.

    repaint_cg2.py <SPRITE.LST> <orig TBL.ROM> <orig CG2.ROM> <PAL.DAT> <out TBL.ROM> <out CG2.ROM> [preview-dir]

This is a PORT (CLAUDE.md section 11): every English string below is Zoinkity's, taken from the DDG64 texture
whose original Japanese is the same text (`mld82r/Images/<n>.bin.png` -> `007gg4/<n>.bin.png`, same <n>; the
number is on each line). A label with no such match is None: its original Japanese art is left untouched and it
belongs on the gap list. No wording here is ours.

The game draws each label as its own box, sized to the Japanese: English is confined to that box (squeezed to
80% width, then scaled down, if it would run past). Drawn in the record's own palette indices (fill, antialiasing
ramp, and the baked drop shadow where the original has one), so the record's unnamed palette never matters.

Then re-tile and deduplicate. A tile that already exists anywhere in CG2.ROM keeps that id; new tiles take the
ids of tiles only these records used; the file is rebuilt at its original size (recompressing other tiles when
the English needs the room), since the disc is patched in place.
"""
import os, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import ddg_assets as A

FONT = "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf"
CAP = 0.716                      # Arial Narrow cap height, in em
SS = 4

# Styles measured from the originals: fill index, antialiasing ramp (strong -> faint), baked shadow.
HEADER = dict(cap=30, ramp=[92, 91, 90, 89], shadow=None, pal=22)          # no shadow: the engine adds it
LEGEND = dict(cap=12, ramp=[7, 78, 77, 4], shadow=None, pal=1)
ITEM   = dict(cap=19, ramp=[92, 91, 90, 89], shadow=(88, 3, 3), pal=22)    # OBJz_font
ITEM_H = dict(cap=19, ramp=[90, 89, 93, 94], shadow=(88, 3, 3), pal=22)    # OBJz_font2 (highlighted)
FOOTER = dict(cap=15, ramp=[6, 4, 5], shadow=(3, 3, 3), pal=1)

HEADERS = [None,                 # メインメニュー: no DDG64 match
           "Controls",           # コントロール  1032
           "Difficulty",         # 難易度        1033
           None,                 # 振動          no DDG64 match
           "Sound",              # サウンド      1034
           "Speedometer",        # 速度メーター  1035
           "Distances",          # 距離メーター  1036
           None,                 # ロード・セーブ no DDG64 match
           "Options",            # ゲーム設定    1031
           None,                 # ロードする    no DDG64 match
           None]                 # セーブする    no DDG64 match
ITEMS_LEFT = ["Controls",        # コントロール  1038
              "Difficulty",      # 難易度        1039
              None,              # 振動
              "Sound",           # サウンド      1040
              "Speedometer",     # 速度メーター  1041
              "Distances",       # 距離メーター  1042
              "Easy",            # イージー      1048
              "Normal",          # ノーマル      1049
              "Hard",            # ハード        1050
              "Very Hard",       # ベリーハード  1051
              None,              # 切弱並強
              "Stereo",          # ステレオ      1052
              "Mono",            # モノラル      1053
              "Hidden",          # 非表示        1061
              "cm",              # cm 表示       1054
              "m",               # m 表示        1055
              "Digital",         # デカデジ      1057
              None,              # ロードする
              None]              # セーブする
ITEMS_RIGHT = {0: "Two-Handed A",  # ツーハンドルA 1044
               1: "Two-Handed B"}  # ツーハンドルB 1045
               # ツーハンドルC/D, ワンハンドルA/B, 専用コントローラ, ポートA/B拡張ソケット1: no DDG64 match

RECORDS = {
    "OBJz_submenu":  dict(style=HEADER, band=48, cols=[(0, 288)], labels={(i, 0): t for i, t in enumerate(HEADERS)}),
    "OBJz_submenu2": dict(style=HEADER, band=48, cols=[(0, 288)], labels={(i, 0): t for i, t in enumerate(
        HEADERS + ["Train Select",         # 電車選択 869
                   "Route Select"])}),     # 路線選択 868
    "OBJz_kettei":   dict(style=LEGEND, band=32, cols=[(0, 112)], labels={
        (0, 0): "Select",                  # 選択       870
        (1, 0): "Back",                    # キャンセル 870
        (2, 0): "Choose",                  # 決定       870
        (3, 0): None}),                    # おわり     no DDG64 match
    "OBJz_font":  dict(style=ITEM, band=32, cols=[(0, 190), (190, 432)], labels=dict(
        [((i, 0), t) for i, t in enumerate(ITEMS_LEFT)] + [((i, 1), t) for i, t in ITEMS_RIGHT.items()])),
    "OBJz_font2": dict(style=ITEM_H, band=32, cols=[(0, 190), (190, 432)], labels=dict(
        [((i, 0), t) for i, t in enumerate(ITEMS_LEFT)] + [((i, 1), t) for i, t in ITEMS_RIGHT.items()])),
    # button icons at x 1-30 and 161-190 stay; only the two text boxes are redrawn
    "OBJz_ranking":  dict(style=FOOTER, band=32, cols=[(33, 158), (193, 384)], labels={
        (0, 0): "Next",                    # 次に進む       738
        (0, 1): "Main Menu"}),             # メニューに戻る 739
    "OBJz_ranking2": dict(style=FOOTER, band=32, cols=[(33, 158), (193, 384)], labels={
        (0, 0): "Next",                    # 次に進む       740
        (0, 1): "Main Menu"}),             # メニューに戻る 741
}


def coverage(text, cap, w, h):
    """(h, w) coverage of `text` at cap height `cap`, left-aligned and vertically centred, fitted to w."""
    font = ImageFont.truetype(FONT, int(round(cap * SS / CAP)))
    l, t, r, b = font.getbbox(text)
    img = Image.new("L", (r - l + 8, b - t + 8))
    ImageDraw.Draw(img).text((4 - l, 4 - t), text, 255, font=font)
    img = img.crop(img.getbbox())
    tw, th = img.width / SS, img.height / SS
    sx = min(1.0, w / tw)
    sy = 1.0
    if sx < 0.8:                                   # squeeze no further than 80%, then scale evenly
        sy = sx / 0.8; sx = sx
    img = img.resize((max(1, int(tw * sx)), max(1, int(round(th * sy)))), Image.LANCZOS)
    out = np.zeros((h, w))
    y = max(0, (h - img.height) // 2)
    out[y:y + img.height, :img.width] = np.asarray(img)[:h - y, :w] / 255.0
    return out


def paint(a, cfg):
    a = a.copy()
    st = cfg["style"]
    shadow = st["shadow"]
    for (row, col), text in cfg["labels"].items():
        if text is None:
            continue                               # gap: original Japanese stays
        y0, y1 = row * cfg["band"], (row + 1) * cfg["band"]
        cx0, cx1 = cfg["cols"][col]
        box = a[y0:y1, cx0:cx1]
        on = np.nonzero((box != 0).any(0))[0]
        if not len(on):
            raise SystemExit("empty label box at %s" % ((row, col),))
        bx0, bx1 = on.min(), on.max() + 1            # the Japanese label's own extent: English stays inside
        room = bx1 - bx0 - (shadow[1] if shadow else 0)
        box[:] = 0
        cov = coverage(text, st["cap"], room, cfg["band"] - (shadow[2] if shadow else 0))
        h, w = cov.shape
        sub = box[:, bx0:bx0 + w + (shadow[1] if shadow else 0)]
        if shadow:
            idx, dx, dy = shadow
            m = cov >= 0.5
            sub[dy:dy + h, dx:dx + w][m] = idx
        for lo, idx in zip((0.8, 0.55, 0.3, 0.1), st["ramp"]):
            part = sub[:h, :w]
            part[(cov >= lo) & ((part == 0) | (part == (shadow[0] if shadow else -1)))] = idx
    return a


def _reencode(tile):
    kind, body = tile
    px = A.cg2_decode(kind, body)
    e = A.cg2_encode(px)
    return (e[0], e[1:]) if len(e) < 1 + len(body) and A.cg2_decode(e[0], e[1:]) == px else tile


def reclaim(tiles, need, skip):
    """Recompress other tiles, largest first, until `need` bytes are saved. Their pictures do not change
    (each re-encoding is decoded and compared), only their bytes. The last tile is left alone: it is cut
    short in the original file."""
    from multiprocessing import Pool
    order = sorted((t for t in range(len(tiles) - 1) if t not in skip), key=lambda t: -len(tiles[t][1]))
    saved, pos = 0, 0
    with Pool() as pool:
        while saved < need and pos < len(order):
            batch = order[pos:pos + 256]; pos += 256
            for t, e in zip(batch, pool.map(_reencode, [tiles[t] for t in batch])):
                saved += len(tiles[t][1]) - len(e[1]); tiles[t] = e
    print("recompressed %d other tiles, %d bytes reclaimed" % (pos, saved))


def main(lst_p, tbl_p, cg2_p, pal_p, out_tbl, out_cg2, preview=None):
    names = {a: o for a, o, s in A.lst(open(lst_p, encoding="latin-1").read())}
    tbl = bytearray(open(tbl_p, "rb").read())
    cg2 = open(cg2_p, "rb").read()
    tiles = A.cg2_tiles(cg2)
    sp = A.Sprites(lst_p, tbl_p, None, cg2_p, pal_p)

    users = {}
    for n in names:
        if sp.flagged(n):
            for t in sp.tilemap(n)[2]:
                users.setdefault(t, set()).add(n)
    freeable = sorted(t for t, u in users.items() if u <= set(RECORDS))
    existing = {}
    for t, (k, b) in enumerate(tiles):
        existing.setdefault(bytes(A.cg2_decode(k, b)), t)

    new = {}
    for name, cfg in RECORDS.items():
        new[name] = paint(sp.indices(name), cfg)
        if preview:
            os.makedirs(preview, exist_ok=True)
            pal = sp.palette(cfg["style"]["pal"])
            Image.fromarray(pal[new[name]], "RGBA").save(os.path.join(preview, name + ".png"))

    def cut(a, w, k):
        return bytes(a[(k // w) * 16:(k // w) * 16 + 16, (k % w) * 16:(k % w) * 16 + 16].ravel())

    kept = set()                                   # freeable ids whose picture is still wanted as it is
    for name, a in new.items():
        w, h, _ = sp.tilemap(name)
        for k in range(w * h):
            px = cut(a, w, k)
            if px in existing and existing[px] in freeable:
                kept.add(existing[px])
    pool = [t for t in freeable if t not in kept]
    out_tiles = list(tiles)
    placed, ids_for = {}, {}
    for name, a in new.items():
        w, h, _ = sp.tilemap(name)
        ids = []
        for k in range(w * h):
            px = cut(a, w, k)
            if px not in placed:
                if px in existing:
                    placed[px] = existing[px]
                else:
                    if not pool:
                        raise SystemExit("out of tile ids")
                    t = pool.pop(0); placed[px] = t
                    e = A.cg2_encode(px)
                    out_tiles[t] = (e[0], e[1:])
            ids.append(placed[px])
        ids_for[name] = ids
    for t in pool:                                 # freed and unused: smallest valid tile
        out_tiles[t] = (1, bytes([0x7F, 0, 0x7F, 0]))

    over = len(A.cg2_build(out_tiles)) - len(cg2)
    if over > 0:
        reclaim(out_tiles, over, set(t for ids in ids_for.values() for t in ids))
    data = A.cg2_build(out_tiles)
    if len(data) > len(cg2):
        raise SystemExit("CG2.ROM would grow by %d bytes" % (len(data) - len(cg2)))
    spare = len(cg2) - len(data)
    data += b"\0" * spare
    for name, ids in ids_for.items():
        struct.pack_into("<%dH" % len(ids), tbl, names[name] + 2, *ids)
    open(out_tbl, "wb").write(tbl); open(out_cg2, "wb").write(data)
    print("%d tiles freed, %d kept, %d new, %d ids spare; CG2.ROM %d bytes to spare" % (
        len(freeable), len(kept), len(freeable) - len(kept) - len(pool), len(pool), spare))


if __name__ == "__main__":
    if len(sys.argv) not in (7, 8):
        sys.exit(__doc__)
    main(*sys.argv[1:])
