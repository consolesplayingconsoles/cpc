#!/usr/bin/env python3
"""`itemtbl` packer -- inverse of `parsers/itemtbl.py`. Patches BOTH halves of
`DOUGU/ITEMTBL.PAC` without destroying either, keeping the file byte-size stable (the
disc splices it in place, no GDI rebuild):

  * DESCRIPTIONS: rewrite each IN PLACE at its own 0x800 sector (index*0x800), which has
    ~2KB of room, preserving the 8-byte sector header and re-padding the sector. An
    untranslated description is left byte-for-byte intact (the whole point: the generic
    ptrtable packer used to zero-fill this half). Done FIRST so each sector's free tail is
    known before names spill into it.
  * NAMES: pack the `2df0` records CONTIGUOUSLY in the item area only (table_end .. 0x1800).
    Never spill into the description sectors -- doing so corrupted the high-index gadgets (they
    render as dots and crash on select). The names share the one item-area budget, so a long
    gadget name borrows the slack short ones leave (a single aggregate, like a STORY box). If the
    total exceeds the item area, the original names are kept and the byte overflow is reported;
    the operator trims to fit (trimming is expected), guided by the UI's item-area aggregate meter.

See memory `project_boku_itemtbl_descriptions`.

    pack(orig, blocks, encode, name_box=20, desc_box=18, desc_lpp=3) -> (bytes, stats)
"""
import struct

from packers import ptrtable

DESC_BASE = 0x1800
SECTOR = 0x800
LB = b"\x01\xff"                       # in-box line break
MID = b"\x01\xff\x04\xff\x01\xff"      # line, page-wait, line -- the game's page-break grammar


def _off(b):
    o = b.get("offset")
    return int(o, 16) if isinstance(o, str) else o


def _wrap(text, width):
    out, cur = [], ""
    for w in text.split(" "):
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= width:
            cur += " " + w
        else:
            out.append(cur); cur = w
    if cur:
        out.append(cur)
    return out


def _paginate(ca, encode, box, lpp):
    lines = _wrap(ca, box)
    pages = [lines[i:i + lpp] for i in range(0, len(lines), lpp)] or [[]]
    return MID.join(LB.join(encode(l) for l in pg) for pg in pages)


def _desc_sectors(orig):
    """Sector offsets that lead with a description record (0x1800, 0x2000, ...)."""
    out, off = [], DESC_BASE
    while off + 8 <= len(orig):
        j = orig[off:off + 0x40].find(b"\x2d\xf0")
        if 0 <= j < 0x20:
            out.append(off)
        off += SECTOR
    return out


def pack(orig, blocks, encode, name_box=20, desc_box=18, desc_lpp=3):
    orig = bytes(orig)
    out = bytearray(orig)
    st = {"names_placed": 0, "names_over": 0, "item_area": 0, "names_bytes": 0,
          "desc_placed": 0, "desc_over": []}

    # ── DESCRIPTIONS FIRST: rewrite translated ones in place; untranslated stay byte-exact. ──
    desc_by_sector = {}
    for b in blocks:
        o = _off(b)
        if o >= DESC_BASE:
            desc_by_sector[((o - DESC_BASE) // SECTOR) * SECTOR + DESC_BASE] = b
    for sector in _desc_sectors(orig):
        b = desc_by_sector.get(sector)
        ca = (b.get("ca") or "").strip() if b else ""
        if not ca:
            continue                                 # untranslated -> original description untouched
        sec = orig[sector:sector + SECTOR]
        j = sec.find(b"\x2d\xf0")
        magic = sec[j:j + 2]
        old_len = struct.unpack_from("<H", sec, j + 2)[0]
        rel = _off(b) - sector
        trailer = sec[rel + b["jpBytes"]: j + 4 + old_len]      # terminating control, verbatim
        new_text = _paginate(ca, encode, desc_box, desc_lpp)
        new_rec = magic + struct.pack("<H", len(new_text) + len(trailer)) + new_text + trailer
        if j + len(new_rec) > SECTOR:
            st["desc_over"].append((sector, j + len(new_rec)))
            continue
        out[sector + j:sector + j + len(new_rec)] = new_rec
        out[sector + j + len(new_rec):sector + SECTOR] = b"\x00" * (SECTOR - (j + len(new_rec)))
        st["desc_placed"] += 1

    # ── NAMES: pack CONTIGUOUSLY in the item area ONLY (table_end .. 0x1800). Never spill into the
    # description sectors -- that relocation corrupted the high-index gadgets (dots + crash). Names
    # share the one item-area budget (a long gadget borrows the slack a short one leaves), same as a
    # STORY box. If the total overflows, keep the original names and report the byte overflow; the
    # operator trims to fit, guided by the item-area aggregate meter in the UI. ──
    name_blocks = [b for b in blocks if _off(b) < DESC_BASE]
    packed = ptrtable.pack(orig, name_blocks, encode, box=name_box, keep_size=False)
    n = struct.unpack_from("<I", packed, 0)[0] // 4
    body_end = 0
    for p in struct.unpack_from("<%dI" % n, packed, 0):
        if p in (0xffffffff, 0xbfffffff) or p == 0 or p + 4 > len(packed):
            continue
        ln = struct.unpack_from("<H", packed, p + 2)[0]
        body_end = max(body_end, p + 4 + ln)
    real_names = sum(1 for b in name_blocks if (b.get("ca") or "").strip())
    st["item_area"] = DESC_BASE - n * 4          # bytes available for name records
    st["names_bytes"] = body_end - n * 4         # bytes the names actually use
    if body_end <= DESC_BASE:
        out[0:body_end] = packed[0:body_end]     # table + names; descriptions untouched
        st["names_placed"] = real_names
    else:
        st["names_over"] = body_end - DESC_BASE  # over the item-area budget -> keep original names

    return bytes(out), st
