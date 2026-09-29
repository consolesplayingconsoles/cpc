#!/usr/bin/env python3
"""Densha de Go! 2 Kousoku-hen 3000 (DC): read the ROM2 containers, the dev index lists, and dump textures.

    ddg_assets.py dump    <CG1.ROM | VQ_CG.ROM> <out-dir>     # every PVRT entry -> NNN.png + sheet.png
    ddg_assets.py lst     <SPRITE.LST | TBL.OUT> <TBL.ROM | VQ_TBL.ROM>   # check the list names the container
    ddg_assets.py record  <SPRITE.LST> <TBL.ROM> <name>       # one sprite record as u16s
    ddg_assets.py render  <SPRITE.LST> <TBL.ROM> <CG1.ROM> <name> <out.png>   # reassemble a sprite
    ddg_assets.py sheets  <SPRITE.LST | TBL.OUT> <TBL.ROM | VQ_TBL.ROM> <CG1.ROM | VQ_CG.ROM> <out-dir>
                                                              # every record rendered, named, 48 per sheet

Inputs are files from the extracted disc (buildgdi -extract). No text lives in this game's files:
every on-screen word is a texture, so the repaint path is the only one (see
docs/dc/games/Densha de Go 2 Kousoku-hen/).

ROM2 = u32 'ROM2', u32 count, then count x (u32 offset, u32 size), offsets from the file start.
CG1.ROM and VQ_CG.ROM hold PVRT textures; TBL.ROM / VQ_TBL.ROM hold the sprite records that
assemble on-screen pictures from those textures; SPRITE.LST / TBL.OUT are the developers' own
C-style listings of those records, `OBJname, /* offset, size */`, one per ROM2 entry, in order.
SPRITE.LST matches TBL.ROM exactly. TBL.OUT is an older build's listing of VQ_TBL.ROM: same 1165
records in the same order, but every size is 2 bytes larger, so trust its names by index only.

A sprite record is a tilemap: u16 header (low byte & 0x7F = width in tiles, bit 7 a flag not yet
understood, high byte = height in tiles), then width*height u16 tile ids, row by row. Tiles are
16x16, 256 per 256x256 texture, row-major: id -> texture id // 256, x = (id % 16) * 16,
y = (id % 256 // 16) * 16. TBL.ROM tiles index CG1.ROM, VQ_TBL.ROM tiles index VQ_CG.ROM.
"""
import os, re, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
from dc import pvr_codec as P


def rom2(d):
    """-> [(offset, size)] for a ROM2 container."""
    if d[:4] != b"ROM2":
        raise ValueError("not a ROM2 container")
    n = struct.unpack_from("<I", d, 4)[0]
    return [struct.unpack_from("<II", d, 8 + 8 * i) for i in range(n)]


def lst(text):
    """-> [(name, offset, size)] from a SPRITE.LST / TBL.OUT listing."""
    return [(a, int(b), int(c)) for a, b, c in re.findall(r"(\w+), /\* (\d+), (\d+) \*/", text)]


def dump(rom, out):
    import numpy as np
    from PIL import Image, ImageDraw
    d = open(rom, "rb").read()
    os.makedirs(out, exist_ok=True)
    tiles = []
    for i, (o, s) in enumerate(rom2(d)):
        if d[o:o + 4] != b"PVRT":
            continue
        im = Image.fromarray(P.decode_pvrt(d, o), "RGBA")
        im.save(os.path.join(out, "%03d.png" % i))
        tiles.append((i, im))
    # contact sheet on magenta so transparency shows; entry number under each
    cols, cell = 10, 150
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 12)), (40, 40, 40))
    dr = ImageDraw.Draw(sheet)
    for k, (i, im) in enumerate(tiles):
        bg = Image.new("RGBA", im.size, (90, 0, 90, 255)); bg.alpha_composite(im)
        x, y = (k % cols) * cell, (k // cols) * (cell + 12)
        sheet.paste(bg.convert("RGB").resize((cell - 4, cell - 4)), (x + 2, y + 2))
        dr.text((x + 2, y + cell - 2), str(i), fill=(255, 255, 0))
    sheet.save(os.path.join(out, "sheet.png"))
    print("%d textures -> %s" % (len(tiles), out))


def check_lst(lst_path, rom):
    names = lst(open(lst_path, encoding="latin-1").read())
    ents = rom2(open(rom, "rb").read())
    same = sum(1 for (_, o, s), (eo, es) in zip(names, ents) if (o, s) == (eo, es))
    print("%s: %d names, %s: %d entries, %d match offset+size" % (
        os.path.basename(lst_path), len(names), os.path.basename(rom), len(ents), same))


def tilemap(tbl, o):
    """-> (w, h, [tile ids]) for the sprite record at offset o of TBL.ROM / VQ_TBL.ROM."""
    hdr = struct.unpack_from("<H", tbl, o)[0]
    w, h = hdr & 0x7F, hdr >> 8
    return w, h, list(struct.unpack_from("<%dH" % (w * h), tbl, o + 2))


class Sprites:
    """A sprite table + its texture container. Names come from the listing by INDEX (TBL.OUT's offsets
    are from an older build), offsets from the table itself."""

    def __init__(self, lst_path, tbl_path, cg_path):
        self.tbl = open(tbl_path, "rb").read()
        self.cg = open(cg_path, "rb").read()
        self.ents = rom2(self.cg)
        names = [a for a, o, s in lst(open(lst_path, encoding="latin-1").read())]
        self.records = dict(zip(names, (o for o, s in rom2(self.tbl))))
        self.texs = {}

    def tilemap(self, name):
        return tilemap(self.tbl, self.records[name])

    def texture(self, i):
        from PIL import Image
        if i not in self.texs:
            self.texs[i] = Image.fromarray(P.decode_pvrt(self.cg, self.ents[i][0]), "RGBA")
        return self.texs[i]

    def render(self, name):
        from PIL import Image
        w, h, ids = self.tilemap(name)
        im = Image.new("RGBA", (w * 16, h * 16))
        for k, t in enumerate(ids):
            x, y = (t % 16) * 16, (t % 256 // 16) * 16
            im.paste(self.texture(t // 256).crop((x, y, x + 16, y + 16)), ((k % w) * 16, (k // w) * 16))
        return im


def render(lst_path, tbl_path, cg_path, name, out):
    sp = Sprites(lst_path, tbl_path, cg_path)
    sp.render(name).save(out)
    w, h, ids = sp.tilemap(name)
    print("%s: %dx%d tiles from textures %s -> %s" % (name, w, h, sorted({t // 256 for t in ids}), out))


def sheets(lst_path, tbl_path, cg_path, out):
    """Every record on labelled contact sheets, so a screen can be found by eye."""
    from PIL import Image, ImageDraw
    sp = Sprites(lst_path, tbl_path, cg_path)
    os.makedirs(out, exist_ok=True)
    names = list(sp.records)
    cols, cw, ch, per = 6, 256, 160, 48
    for k in range(0, len(names), per):
        chunk = names[k:k + per]
        sheet = Image.new("RGB", (cols * cw, ((len(chunk) + cols - 1) // cols) * (ch + 14)), (40, 40, 40))
        dr = ImageDraw.Draw(sheet)
        for j, n in enumerate(chunk):
            im = sp.render(n); im.thumbnail((cw - 4, ch - 4))
            bg = Image.new("RGBA", im.size, (90, 0, 90, 255)); bg.alpha_composite(im)
            x, y = (j % cols) * cw, (j // cols) * (ch + 14)
            sheet.paste(bg.convert("RGB"), (x + 2, y + 2))
            dr.text((x + 2, y + ch), n, fill=(255, 255, 0))
        sheet.save(os.path.join(out, "sheet_%02d.png" % (k // per)))
    print("%d records on %d sheets -> %s" % (len(names), (len(names) + per - 1) // per, out))


def record(lst_path, rom, name):
    names = {a: (o, s) for a, o, s in lst(open(lst_path, encoding="latin-1").read())}
    o, s = names[name]
    d = open(rom, "rb").read()[o:o + s]
    print(name, s, "bytes:", struct.unpack_from("<%dH" % (s // 2), d))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "dump" and len(sys.argv) == 4:
        dump(sys.argv[2], sys.argv[3])
    elif cmd == "lst" and len(sys.argv) == 4:
        check_lst(sys.argv[2], sys.argv[3])
    elif cmd == "sheets" and len(sys.argv) == 6:
        sheets(*sys.argv[2:6])
    elif cmd == "render" and len(sys.argv) == 7:
        render(*sys.argv[2:7])
    elif cmd == "record" and len(sys.argv) == 5:
        record(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        sys.exit(__doc__)
