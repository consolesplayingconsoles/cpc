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
from parsers import nullsplit, lines, ptrtable, exemsg   # console-agnostic format strategies

PARSERS = {"nullsplit": nullsplit.parse, "lines": lines.parse, "ptrtable": ptrtable.parse,
           "exemsg": exemsg.parse}


def _has_gaiji(hexstr):
    """True if a block contains an SJIS user-defined (gaiji) glyph -- lead byte 0xF0-0xFC. Those are
    font/texture data, not real text. Walks SJIS lead/trail so a normal char's trail isn't misread.
    Codec-free (Batocera's python has no shift_jis)."""
    try:
        b = bytes.fromhex(hexstr or "")
    except ValueError:
        return False
    i = 0
    while i < len(b):
        c = b[i]
        if 0xf0 <= c <= 0xfc:
            return True
        i += 2 if (0x81 <= c <= 0x9f or 0xe0 <= c <= 0xef) else 1
    return False


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
    # Mark texture/graphics artifacts as DONE (keep-original) up front: a block carrying an SJIS
    # user-defined (gaiji) glyph -- lead byte 0xF0-0xFC -- is font/texture data the parser swept up,
    # never real dialogue. Using the existing `done` state (not a UI heuristic) keeps them out of the
    # progress %, out of the build (no-op), and reusable across games. Codec-free for Batocera.
    for blk in blocks:
        if _has_gaiji(blk.get("hex", "")):
            blk["done"] = True
    out = {"blocks": blocks, "total": len(blocks), "kind": kind, "parser": parser}

    # Box-budget data (static, baked in at extract, NOT a separate endpoint): tag each block with
    # its scene and ship the per-scene slack, so the UI can group blocks into scenes and meter the
    # Catalan against each box's budget. Only the SCP/CMD format (nullsplit) has per-scene boxes.
    if parser == "nullsplit":
        import bisect
        from packers import nullsplit as _nspack
        b = _nspack.budget(data)
        starts = b["starts"]
        for blk in blocks:
            o = blk.get("offset", 0)
            o = int(o, 16) if isinstance(o, str) else o
            blk["scene"] = max(0, bisect.bisect_right(starts, o) - 1)
        out["scenes"] = b["scenes"]
    print(json.dumps(out))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('{"error":"usage: extract.py <cache-dir> <safe-name>"}')
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
