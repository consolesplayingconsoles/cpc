#!/usr/bin/env python3
"""Codec-free STORY.PAC extractor -> the dialogue table as JSON.

Batocera's minimal Python has no shift_jis codec, so we do NOT decode here: each
dialogue block is returned as its RAW bytes (hex) plus offset + byte budget. The
browser decodes the hex with TextDecoder('shift_jis') to show the Japanese and to
let the translator type Catalan against the byte budget.

Block detection mirrors dc_story_patch.py: null-delimited segments that contain
>=2 Shift-JIS double-byte (kana/kanji) chars are dialogue.
"""
import sys, json

def _is_lead(b):  return 0x82 <= b <= 0x9F or 0xE0 <= b <= 0xEA
def _is_trail(b): return 0x40 <= b <= 0x7E or 0x80 <= b <= 0xFC

def _jp_doubles(data, start, end):
    i, n = start, 0
    while i + 1 < end:
        if _is_lead(data[i]) and _is_trail(data[i + 1]):
            n += 1; i += 2
        else:
            i += 1
    return n

def extract(data):
    n, i, blocks = len(data), 0, []
    speaker = 0
    while i < n:
        if data[i] == 0:
            i += 1; continue
        start = i
        while i < n and data[i] != 0:
            i += 1
        seg = data[start:i]
        # Speaker tag \x02\xff<id> precedes a character's lines — track it.
        if len(seg) >= 3 and seg[0] == 0x02 and seg[1] == 0xff:
            speaker = seg[2]
        elif _jp_doubles(data, start, i) >= 2:
            blocks.append({"offset": start, "jpBytes": i - start,
                           "hex": seg.hex(), "speaker": speaker})
    return blocks

def main():
    if len(sys.argv) < 2:
        print('{"error":"usage: dc_story_extract.py <STORY.PAC>"}'); sys.exit(1)
    data = bytearray(open(sys.argv[1], "rb").read())
    blocks = extract(data)
    print(json.dumps({"blocks": blocks, "total": len(blocks)}))

if __name__ == "__main__":
    main()
