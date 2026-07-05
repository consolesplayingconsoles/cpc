#!/usr/bin/env python3
"""`lines` packer -- inverse of `parsers/lines.py`, same-size in-place line rewrite.

For newline-delimited text files (INI / TXT menus) that must NOT change length -- so the
patched file can be spliced into the raw GD-ROM track by `dc/inplace.py` with ZERO LBA
movement (this game reads assets by hardcoded disc position; a rebuild hangs it -- see
translate.sh). Each block carries the byte `offset` + original line length (`jpBytes`) from
the parser; we overwrite that exact span with the Catalan line, PADDED with trailing spaces
back to the original length. The `\r\n` and every untranslated byte stay put, so the total
file size is identical and unedited lines are byte-for-byte preserved.

Two hard rules for staying in budget:
  * the Catalan line must be <= the original line's byte length; if it's longer it does NOT
    fit the slot and is SKIPPED (JP kept) -- report it so the operator can shorten it.
  * this file is rendered by the Dream Passport font, NOT the game S18RM04.FON, so the game
    `encode` (fon_codec.fw) is IGNORED here -- we emit plain Shift-JIS. Keep the Catalan
    ASCII-safe (no accents) unless the DP font is confirmed to carry them.

    pack(orig, blocks, encode=None, **kw) -> (bytes, stats)
"""

# The Catalan here is ASCII-safe by design (DP font, no accents), and the target box's minimal
# Python has NO shift_jis codec -- so encode ASCII (byte-identical to SJIS for 0x00-0x7F, and
# codec-free so it runs on Batocera). A stray non-ASCII char is replaced, never crashes the build.
CP = "ascii"


def pack(orig, blocks, encode=None, **kw):
    out = bytearray(orig)
    placed = skipped = 0
    over = []
    for b in blocks:
        ca = (b.get("ca") or "").strip()
        if not ca:
            continue
        off = b.get("offset")
        off = int(off, 16) if isinstance(off, str) else off
        budget = b.get("jpBytes")
        if budget is None:                     # fall back to the stored original line length
            budget = len(bytes.fromhex(b["hex"]))
        enc = ca.encode(CP, "replace")
        if len(enc) > budget:
            skipped += 1
            over.append((b.get("offset"), len(enc), budget, ca))
            continue
        enc = enc + b" " * (budget - len(enc))  # pad to the exact original span
        out[off:off + budget] = enc
        placed += 1
    assert len(out) == len(orig), (len(out), len(orig))
    return bytes(out), {"placed": placed, "skipped": skipped, "over_budget": over}
