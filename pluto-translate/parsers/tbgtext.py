#!/usr/bin/env python3
"""`tbgtext` parser -- Tokyo Bus Guide `*_TEXT.DAT` (the chat you hear while driving).

A three-level container, all little-endian:

    [u32 scene table]   first entry = the table's own byte size, so count = first // 4;
                        each entry points into the pair area below
    [pair area]         (u32 textOffset, u32 id) records. A scene is a run of pairs
                        ending in one whose id is 0x7fffffff and whose text is empty.
                        In SYSTEM/S_TEXT.DAT the second field is a text offset too
                        (a second line), so any value inside the string area counts
    [strings]           NUL-terminated Shift-JIS, 4-aligned, `<E>` = line break

Every area ships the same three files (`S_`, `W_`, `O_`), so the 21 files on the disc
hold only ~1300 distinct lines. Pairs with `packers/tbgtext.py`, which grows the string
area and repoints the pairs (index rewrite), so English is not byte-limited.

    parse(data) -> [{offset, jpBytes, hex, speaker}, ...]   (raw SJIS hex; UI decodes)
"""
import struct

TERMINATOR = 0x7fffffff


def pairs(data):
    """[(pairPos, textOffset, id)] for every pair record, in file order."""
    if len(data) < 8:
        return []
    first = struct.unpack_from("<I", data, 0)[0]
    if first == 0 or first % 4 or first > len(data):
        return []                                  # not this format
    out, i = [], first
    while i + 8 <= len(data):
        off, ident = struct.unpack_from("<II", data, i)
        if off < first or off >= len(data):        # past the pair area
            break
        out.append((i, off, ident))
        i += 8
    return out


def text_offsets(data):
    """Every offset in the pair area that points at a string, in file order.

    The first field of a pair always does; the second is normally a voice id, but in
    SYSTEM/S_TEXT.DAT it is a second line, so it counts when it lands in the strings.
    """
    recs = pairs(data)
    if not recs:
        return []
    start = min(r[1] for r in recs)
    out = []
    for pos, off, ident in recs:
        out.append((pos, off))
        if start <= ident < len(data):
            out.append((pos + 4, ident))
    return out


def parse(data):
    data = bytes(data)
    seen, blocks = set(), []
    for _, off in text_offsets(data):
        if off in seen:
            continue                               # the same line can be shared by scenes
        seen.add(off)
        end = data.find(b"\0", off)
        if end < 0 or end == off:                  # unterminated, or a scene's empty end marker
            continue
        blocks.append({"offset": off, "jpBytes": end - off,
                       "hex": data[off:end].hex(), "speaker": 0})
    blocks.sort(key=lambda b: b["offset"])
    return blocks
