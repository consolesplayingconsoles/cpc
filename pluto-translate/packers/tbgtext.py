#!/usr/bin/env python3
"""`tbgtext` packer -- inverse of `parsers/tbgtext.py`.

INDEX REWRITE, like `ptrtable`: the scene table and the pair area keep their exact
size and position, so only the string area is rebuilt. Every string is re-emitted in
its original order (NUL-terminated, 4-aligned) and each pair's offset is rewritten to
where its string landed. English can therefore be longer than the Japanese it replaces.

Growth is safe here because these are standalone files in their own directory: the
disc rebuild writes the whole track, so file sizes may change (unlike 1ST_READ.BIN).

    pack(orig, blocks, encode, box=None, keep_size=True) -> bytes
        encode    : str -> bytes    (the game's Shift-JIS full-width encoder)
        box       : wrap width in full-width characters; None = leave the text alone
        keep_size : pad back to the original length when the result is shorter
"""
import struct

from parsers.tbgtext import pairs, text_offsets


def _encode(text, encode):
    """Encode the text, leaving the game's `<E>` line break as its own three bytes."""
    return b"<E>".join(encode(part) for part in text.split("<E>"))


def _wrap(text, width):
    """Break `text` into `<E>` lines of at most `width` characters, on spaces."""
    if not width:
        return text
    out = []
    for para in text.split("<E>"):
        line = ""
        for word in para.split(" "):
            if not line:
                line = word
            elif len(line) + 1 + len(word) <= width:
                line += " " + word
            else:
                out.append(line)
                line = word
        out.append(line)
    return "<E>".join(out)


def pack(orig, blocks, encode, box=None, keep_size=True):
    orig = bytes(orig)
    recs = text_offsets(orig)
    if not recs:
        return orig
    text_start = min(off for _, off in recs)
    by_offset = {}
    for blk in blocks or []:
        text = (blk.get("ca") or blk.get("en") or "").strip()
        if text:
            by_offset[blk["offset"]] = _encode(_wrap(text, box), encode)

    out = bytearray(orig[:text_start])             # scene table + pair area, unchanged
    moved = {}
    for _, off in recs:
        if off in moved:
            continue
        end = orig.find(b"\0", off)
        end = len(orig) if end < 0 else end
        payload = by_offset.get(off, orig[off:end])
        moved[off] = len(out)
        out += payload + b"\0"
        while len(out) % 4:                        # strings are 4-aligned
            out += b"\0"

    for pos, off in recs:                          # repoint every pair at its string
        struct.pack_into("<I", out, pos, moved[off])

    if keep_size and len(out) < len(orig):
        out += b"\0" * (len(orig) - len(out))
    return bytes(out)
