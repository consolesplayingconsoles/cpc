#!/usr/bin/env python3
"""Codec-free STORY.PAC extractor CLI -> the dialogue table as JSON.

Thin DC entry point: STORY.PAC is null-delimited dialogue, so the actual work is
the console-agnostic `nullsplit` parser. We do NOT decode here (Batocera's Python
has no shift_jis codec) -- each block is RAW bytes (hex) + offset + byte budget;
the browser decodes with TextDecoder('shift_jis'). Kept for the standalone
extract.sh dev path; the live workbench goes through the /sources cache.

    story_extract.py <STORY.PAC>
"""
import json
import os
import sys

# the parsers package sits at the scripts root (one level up from dc/)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers import nullsplit


def main():
    if len(sys.argv) < 2:
        print('{"error":"usage: story_extract.py <STORY.PAC>"}'); sys.exit(1)
    data = bytearray(open(sys.argv[1], "rb").read())
    blocks = nullsplit.parse(data)
    print(json.dumps({"blocks": blocks, "total": len(blocks)}))


if __name__ == "__main__":
    main()
