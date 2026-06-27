#!/usr/bin/env python3
"""Extract ONE discovered source's text blocks from the /sources cache.

DC glue only: pick the parser by the source's `kind` (from the scan manifest, via
sources.config.json), run it on the cached file, emit JSON. The parsers live in
the console-agnostic `parsers/` package (a sibling of dc/), so any console reuses
them -- adding a format is a new parsers/ file + a config edit, not a change here.
Blocks carry RAW Shift-JIS bytes (hex); the browser decodes them. Emits
{"blocks":[...], "total":N, "kind":..., "parser":...}.

    extract.py <cache-dir> <safe-name>
"""
import json
import os
import sys

# the parsers package sits at the scripts root (one level up from dc/)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sources                              # _load_config (typology + parser per kind)
from parsers import nullsplit, lines, ptrtable   # console-agnostic format strategies

PARSERS = {"nullsplit": nullsplit.parse, "lines": lines.parse, "ptrtable": ptrtable.parse}


def main(cache_dir, safe):
    cfg = sources._load_config()
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
    blocks = PARSERS.get(parser, nullsplit.parse)(data)
    print(json.dumps({"blocks": blocks, "total": len(blocks),
                      "kind": kind, "parser": parser}))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('{"error":"usage: extract.py <cache-dir> <safe-name>"}')
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
