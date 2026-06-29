#!/usr/bin/env python3
"""`ptrtable` packer -- inverse of `parsers/ptrtable.py`.

Rebuilds a u32-pointer-table file with the Catalan text in place. Because Catalan
is longer than the Japanese it replaces, we DON'T patch in place: we re-emit every
record back-to-back and rewrite the pointer table to the new offsets (the index
rewrite). The file grows; standalone subdir files (ITEMTBL.PAC, SECRET.TBL) are
replaced wholesale by the disc rebuild, so growth is fine.

Record shape (matches the parser): `2d f0 <u16 len=textbytes+4> <SJIS text> <4B trailer>`,
where the text may carry internal `01 ff` line breaks (multi-line hints) and the
trailer (`01 ff 00 ff`) is captured from the original and re-emitted verbatim.
Pointer entries that aren't records (sentinels like `0xffffffff` / `0xbfffffff`,
the table-size entry [0]) are preserved. Generalises the original itemtbl-expand proof
to ALL records + accent glyphs via `fon_codec.fw`.

    pack(orig, blocks, encode, box=None, keep_size=True) -> bytes
        encode    : str -> bytes   (full-width + accent encoder)
        box       : wrap width in full-width chars (multi-line hints); None = single line
        keep_size : pad back to the original byte length when the repacked data is
                    smaller (the original's trailing slack) -- conservative, matches
                    itemtbl-expand. Files that need MORE room (SECRET) grow regardless.
"""
import struct

LB = b"\x01\xff"          # in-text line break


def _wrap(text, width):
    if not width:
        return [text]
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


def pack(orig, blocks, encode, box=None, keep_size=True):
    orig = bytes(orig)
    n = struct.unpack_from("<I", orig, 0)[0] // 4
    ptrs = list(struct.unpack_from("<%dI" % n, orig, 0))

    bymap = {}
    for b in blocks:
        o = b.get("offset")
        bymap[int(o, 16) if isinstance(o, str) else o] = b

    # records = in-range pointer entries (sentinels like 0xffffffff/0xbfffffff are
    # out of range and skipped). The record magic is NOT assumed -- it's captured from
    # the file per record, so this stays game-agnostic (the technique, not the game).
    recs = [(i, ptrs[i]) for i in range(n) if 0 <= ptrs[i] + 4 <= len(orig)]

    tbl_size = n * 4
    new_tbl = list(ptrs)
    body = bytearray()

    for k, (idx, p) in enumerate(recs):
        old_len = struct.unpack_from("<H", orig, p + 2)[0]
        textbytes = old_len - 4
        text_start = p + 4
        text_end = text_start + textbytes
        trailer = orig[text_end:text_end + 4]            # capture verbatim (e.g. 01 ff 00 ff)
        next_off = recs[k + 1][1] if k + 1 < len(recs) else None
        sep = orig[text_end + 4:next_off] if next_off is not None else b""   # ff-padding between records

        blk = bymap.get(text_start)
        ca = blk.get("ca") if blk else None
        if ca:
            new_text = LB.join(encode(line) for line in _wrap(ca, box))
        else:
            new_text = orig[text_start:text_end]         # untranslated -> keep JP

        magic = orig[p:p + 2]                             # captured, not hardcoded
        new_rec = magic + struct.pack("<H", len(new_text) + 4) + new_text + trailer
        new_tbl[idx] = tbl_size + len(body)
        body += new_rec + sep

    out = bytearray()
    for v in new_tbl:
        out += struct.pack("<I", v)
    out += body
    if keep_size and len(out) < len(orig):
        out += b"\x00" * (len(orig) - len(out))          # restore original trailing slack
    return bytes(out)
