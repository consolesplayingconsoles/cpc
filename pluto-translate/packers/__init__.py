#!/usr/bin/env python3
"""`packers` -- the write-side twin of `parsers`.

`parsers` decode a binary FORMAT into translation blocks; `packers` do the
inverse: take the original bytes + the translated blocks and re-emit the binary
with the Catalan text in place. Same config-driven, format-decoupled design
(`sources.config.json` maps a source's `kind` to both a `parser` and a `packer`),
so the repack engine is reusable across games and formats, not a per-line hack.

Each packer exposes:

    pack(orig: bytes, blocks: list[dict], encode, box=None) -> bytes

where `blocks` carry `{offset, ca, ...}` (the workbench shape) and `encode` is a
`str -> bytes` glyph encoder (e.g. `dc.fon_codec.fw`, full-width + accent glyphs).
The cardinal trick is the INDEX REWRITE: where a format stores an offset/pointer
table, longer Catalan is handled by relocating the text and repointing the table,
never by fragile in-place shifting.
"""

from . import ptrtable          # noqa: F401
from . import nullsplit         # noqa: F401

# ptrtable.pack -> bytes ; nullsplit.pack -> (bytes, stats). Callers handle the shape.
PACKERS = {"ptrtable": ptrtable.pack, "nullsplit": nullsplit.pack}


def pack(kind, orig, blocks, encode, **kw):
    if kind not in PACKERS:
        raise KeyError("no packer for kind %r (have %s)" % (kind, sorted(PACKERS)))
    return PACKERS[kind](orig, blocks, encode, **kw)
