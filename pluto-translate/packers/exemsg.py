#!/usr/bin/env python3
"""`exemsg` packer -- inverse of parsers/exemsg. Rewrites each embedded message
record's Shift-JIS text runs with Catalan (via `encode`, i.e. fon_codec.fw), IN PLACE
and SAME-SIZE.

Why same-size: this text lives in the main executable (1ST_READ.BIN). The disc is
patched by splicing files straight into their existing sectors (dc/inplace.py) -- any
size change would shift every following byte and the game reads assets by hardcoded
disc position, so the exe MUST stay byte-for-byte the same length.

How: walk each record's text region; copy every control token (01ff / 04ff / 05ff xxxx)
verbatim in its original order, replace only the text runs (matched by absolute offset),
then pad the region back to its exact original length with full-width spaces (rendered
blank, valid glyphs). A record whose Catalan overflows its region is left ENTIRELY as
Japanese -- fail-safe; the workbench byte meter is meant to catch it first.

    pack(orig, blocks, encode, box=None) -> bytes   # whole file, same length as orig
"""
from parsers.exemsg import records, _is_ctrl, _ctrl_len

FWSPACE = b"\x81\x40"   # full-width space -- valid glyph, renders blank, used as tail padding


def pack(orig, blocks, encode, box=None):
    orig = bytes(orig)
    d = bytearray(orig)
    bymap = {}
    for b in blocks:
        o = b.get("offset")
        bymap[int(o, 16) if isinstance(o, str) else o] = b

    for (_mo, _ln, ts, te) in records(orig):
        new = bytearray()
        k = ts
        while k < te:
            if _is_ctrl(orig, k):
                new += orig[k:k + _ctrl_len(orig, k)]
                k += _ctrl_len(orig, k)
                continue
            if orig[k] == 0xff:
                new += orig[k:k + 1]
                k += 1
                continue
            j = k
            while j < te and not _is_ctrl(orig, j) and orig[j] != 0xff:
                j += 1
            blk = bymap.get(k)
            ca = blk.get("ca") if blk else None
            new += encode(ca) if ca else orig[k:j]      # untranslated run -> keep original JP
            k = j

        region = te - ts
        if len(new) > region:
            continue                                    # over budget -> keep this record's JP
        new += FWSPACE * ((region - len(new)) // 2)     # pad the tail (after the final terminator)
        if len(new) < region:                           # odd byte (shouldn't happen: all runs even)
            new += b"\x00" * (region - len(new))
        d[ts:te] = new
    return bytes(d)
