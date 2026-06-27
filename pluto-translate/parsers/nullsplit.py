#!/usr/bin/env python3
"""`nullsplit` parser -- NUL-delimited segments with speaker tags.

A generic source FORMAT strategy, console-agnostic: the file is a run of
NUL-separated segments; a segment with >=2 Shift-JIS double-byte chars is a text
block, and a `\\x02\\xff<id>` tag sets the speaker for the lines that follow.
(This is the shape Boku Doraemon's STORY.PAC uses, but the strategy isn't
DC-specific -- any console that null-delimits dialogue can reuse it.)

The `\\x02\\xff<id>` speaker tag can START its own segment OR appear MID-segment
when two turns are NOT NUL-separated (cutscenes: `...turn1<ctrl><02ff id2>turn2`).
Both cases split + retag here -- otherwise the trailing turn inherits the previous
speaker and turn1's text leaks the raw tag bytes as garbage.

    parse(data) -> [{offset, jpBytes, hex, speaker}, ...]   (raw SJIS hex; UI decodes)
"""
from . import sjis


def _emit(blocks, data, start, end, speaker):
    # One text block per sub-message; skip empty/tag-only/control-only spans.
    if end > start and sjis.jp_doubles(data, start, end) >= 2:
        blocks.append({"offset": start, "jpBytes": end - start,
                       "hex": data[start:end].hex(), "speaker": speaker})


def parse(data):
    n, i, blocks = len(data), 0, []
    speaker = 0
    while i < n:
        if data[i] == 0:
            i += 1
            continue
        # One NUL-delimited segment: [i, seg_end).
        seg_end = i
        while seg_end < n and data[seg_end] != 0:
            seg_end += 1
        # Walk it, cutting a new sub-message at every 02ff<id> speaker tag.
        p = sub = i
        while p < seg_end:
            if p + 2 < seg_end and data[p] == 0x02 and data[p + 1] == 0xff:
                _emit(blocks, data, sub, p, speaker)   # close the turn before the tag
                speaker = data[p + 2]                  # retag who speaks next
                p += 3
                sub = p
            else:
                p += 1
        _emit(blocks, data, sub, seg_end, speaker)
        i = seg_end
    return blocks
