#!/usr/bin/env python3
"""Repaint flagged sprite records (tiles in CG2.ROM): the section headers and the button legend.

    repaint_cg2.py <SPRITE.LST> <orig TBL.ROM> <orig CG2.ROM> <PAL.DAT> <out TBL.ROM> <out CG2.ROM> [preview-dir]

Each record here is a column of labels, one per fixed-height band, drawn in one fill index with three
antialiasing indices (no shadow: the engine adds that). A band is cleared and the English is drawn with
the same indices, so the record's palette, which the record does not name, never matters.

Then re-tile and deduplicate. A tile that already exists anywhere in CG2.ROM keeps that id; new tiles take
the ids of tiles only these records used; the file is rebuilt with every other tile's bytes untouched and
must not grow, since the disc is patched in place.
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

# record: band height, x, cap height, index ramp (fill first, then fainter), preview palette, labels
HEADERS = ["Main Menu", "Controls", "Difficulty", "Vibration", "Sound", "Speedometer", "Distances",
           "Load and Save", "Game Setting", "Load", "Save"]
RECORDS = {
    "OBJz_submenu":  dict(band=48, x=2, cap=30, ramp=[92, 91, 90, 89], pal=22, labels=HEADERS),
    "OBJz_submenu2": dict(band=48, x=2, cap=30, ramp=[92, 91, 90, 89], pal=22,
                          labels=HEADERS + ["Train Select", "Route Select"]),
    "OBJz_kettei":   dict(band=32, x=3, cap=12, ramp=[7, 78, 77, 4], pal=1,
                          labels=["Select", "Cancel", "OK", "Quit"]),
}


def coverage(text, cap, w, h, x):
    """(h, w) coverage of `text`, cap height `cap`, left at x, vertically centred, squeezed to fit."""
    font = ImageFont.truetype(FONT, int(round(cap * SS / CAP)))
    l, t, r, b = font.getbbox(text)
    img = Image.new("L", (r - l + 8, b - t + 8))
    ImageDraw.Draw(img).text((4 - l, 4 - t), text, 255, font=font)
    img = img.crop(img.getbbox())
    tw = min(img.width / SS, w - x - 2)
    img = img.resize((max(1, int(round(tw))), max(1, int(round(img.height / SS)))), Image.LANCZOS)
    out = np.zeros((h, w))
    y = (h - img.height) // 2
    out[y:y + img.height, x:x + img.width] = np.asarray(img) / 255.0
    return out


def paint(a, cfg):
    a = a.copy()
    H, W = a.shape
    ramp = cfg["ramp"]
    for i, text in enumerate(cfg["labels"]):
        y0 = i * cfg["band"]
        band = a[y0:y0 + cfg["band"]]
        band[:] = 0
        cov = coverage(text, cfg["cap"], W, cfg["band"], cfg["x"])
        for lo, idx in zip((0.8, 0.55, 0.3, 0.1), ramp):          # strongest coverage -> fill index
            band[(cov >= lo) & (band == 0)] = idx
    if len(cfg["labels"]) * cfg["band"] != H:
        raise SystemExit("band layout does not cover the record (%d x %d != %d)" % (
            len(cfg["labels"]), cfg["band"], H))
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

    # who uses each tile, to know which ids the repainted records can free
    users = {}
    for n in names:
        if sp.flagged(n):
            for t in sp.tilemap(n)[2]:
                users.setdefault(t, set()).add(n)
    ours = set(RECORDS)
    freeable = sorted(t for t, u in users.items() if u <= ours)
    existing = {}
    for t, (k, b) in enumerate(tiles):
        existing.setdefault(bytes(A.cg2_decode(k, b)), t)

    new = {}
    for name, cfg in RECORDS.items():
        a = paint(sp.indices(name), cfg)
        new[name] = a
        if preview:
            os.makedirs(preview, exist_ok=True)
            Image.fromarray(sp.palette(cfg["pal"])[a], "RGBA").save(os.path.join(preview, name + ".png"))

    placed, kept_ids = {}, set()
    for name, a in new.items():
        w, h, _ = sp.tilemap(name)
        for k in range(w * h):
            px = bytes(a[(k // w) * 16:(k // w) * 16 + 16, (k % w) * 16:(k % w) * 16 + 16].ravel())
            if px in existing and existing[px] not in freeable:
                placed[px] = existing[px]
            elif px in existing and px not in placed:
                placed[px] = existing[px]; kept_ids.add(existing[px])
    pool = [t for t in freeable if t not in kept_ids]
    out_tiles = list(tiles)
    ids_for = {}
    for name, a in new.items():
        w, h, _ = sp.tilemap(name)
        ids = []
        for k in range(w * h):
            px = bytes(a[(k // w) * 16:(k // w) * 16 + 16, (k % w) * 16:(k % w) * 16 + 16].ravel())
            if px not in placed:
                if not pool:
                    raise SystemExit("out of tile ids")
                t = pool.pop(0); placed[px] = t
                e = A.cg2_encode(px)
                out_tiles[t] = (e[0], e[1:])
            ids.append(placed[px])
        ids_for[name] = ids
    for t in pool:                                           # freed and unused: smallest valid tile
        out_tiles[t] = (1, bytes([0x7F, 0, 0x7F, 0]))

    over = len(A.cg2_build(out_tiles)) - len(cg2)
    if over > 0:
        reclaim(out_tiles, over, set(t for ids in ids_for.values() for t in ids))
    data = A.cg2_build(out_tiles)
    if len(data) > len(cg2):
        raise SystemExit("CG2.ROM would grow by %d bytes" % (len(data) - len(cg2)))
    data += b"\0" * (len(cg2) - len(data))
    for name, ids in ids_for.items():
        struct.pack_into("<%dH" % len(ids), tbl, names[name] + 2, *ids)
    open(out_tbl, "wb").write(tbl); open(out_cg2, "wb").write(data)
    print("%d tiles freed, %d new tiles written, %d ids spare; CG2.ROM %d bytes to spare" % (
        len(freeable), len(freeable) - len(pool) - len(kept_ids), len(pool), len(cg2) - len(A.cg2_build(out_tiles))))


if __name__ == "__main__":
    if len(sys.argv) not in (7, 8):
        sys.exit(__doc__)
    main(*sys.argv[1:])
