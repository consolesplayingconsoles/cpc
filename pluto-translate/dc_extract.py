#!/usr/bin/env python3
"""Extract ONE discovered source's text blocks from the /sources cache.

The parser is chosen by the source's `kind` (read from the scan manifest) via
sources.config.json -- so adding a format is a config edit, not a code change.
Blocks carry RAW Shift-JIS bytes (hex); the browser decodes them. Emits
{"blocks":[...], "total":N, "kind":..., "parser":...} JSON.

    dc_extract.py <cache-dir> <safe-name>
"""
import json
import os
import sys

import dc_sources         # _load_config (thresholds + typology + parser per kind)
import dc_story_extract   # the proven null-split + speaker extractor, and JP helpers


def parse_nullsplit(data):
    """Null-delimited segments with >=2 Shift-JIS pairs; \\x02\\xff<id> sets the
    speaker (STORY.PAC). Files without tags just get speaker 0."""
    return dc_story_extract.extract(data)


def parse_lines(data):
    """Newline-delimited (INI / TXT): each line with >=1 Shift-JIS pair is a block."""
    blocks, off = [], 0
    for line in data.split(b"\n"):
        seg = line.rstrip(b"\r")
        if dc_story_extract._jp_doubles(seg, 0, len(seg)) >= 1:
            blocks.append({"offset": off, "jpBytes": len(seg),
                           "hex": bytes(seg).hex(), "speaker": 0})
        off += len(line) + 1
    return blocks


PARSERS = {"nullsplit": parse_nullsplit, "lines": parse_lines}


def main(cache_dir, safe):
    cfg = dc_sources._load_config()
    parser_by_kind = {e["kind"]: e.get("parser", "nullsplit")
                      for e in cfg.get("typology", [])}
    # the scan manifest carries each source's kind
    try:
        with open(os.path.join(cache_dir, "sources.json")) as fh:
            manifest = json.load(fh)
        src = next((s for s in manifest.get("sources", [])
                    if s.get("safe") == safe), None)
    except Exception:
        src = None
    kind = src.get("kind") if src else "text"
    parser = parser_by_kind.get(kind, "nullsplit")
    with open(os.path.join(cache_dir, "files", safe), "rb") as fh:
        data = bytearray(fh.read())
    blocks = PARSERS.get(parser, parse_nullsplit)(data)
    print(json.dumps({"blocks": blocks, "total": len(blocks),
                      "kind": kind, "parser": parser}))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('{"error":"usage: dc_extract.py <cache-dir> <safe-name>"}')
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
