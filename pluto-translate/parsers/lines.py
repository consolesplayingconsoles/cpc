#!/usr/bin/env python3
"""`lines` parser -- newline-delimited records (INI / TXT menus).

A generic source FORMAT strategy, not DC-specific: each `\\n`-delimited line that
holds >=1 Shift-JIS double-byte char is one block. Offsets track the original byte
position so the patcher writes back in place. Lines without JP are skipped (keys,
blanks) but still advance the offset.

    parse(data) -> [{offset, jpBytes, hex, speaker}, ...]   (raw SJIS hex; UI decodes)
"""
from . import sjis


def parse(data):
    blocks, off = [], 0
    for line in data.split(b"\n"):
        seg = line.rstrip(b"\r")
        if sjis.jp_doubles(seg, 0, len(seg)) >= 1:
            blocks.append({"offset": off, "jpBytes": len(seg),
                           "hex": bytes(seg).hex(), "speaker": 0})
        off += len(line) + 1
    return blocks
