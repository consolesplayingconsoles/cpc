#!/usr/bin/env python3
"""`exemsg` parser -- text records embedded directly in a game's main executable
(e.g. Dreamcast 1ST_READ.BIN), not inside a container file.

Some prompts the engine shows itself (save / sleep confirmations) live in the exe as
control-coded records rather than in the .SCP/ITEMTBL tables:

    <XX f0> <u16 len> <text ...>        XX in 0x20..0x3f ; len = text byte length

The text mixes Shift-JIS with inline control tokens: `01 ff` (line break), `04 ff`,
and `05 ff <u16>` (colour/style). We surface every Shift-JIS text RUN (the bytes
between control tokens) as its own editable block, keyed by ABSOLUTE file offset, so
the same-size packer can rewrite each run in place while copying every control token
verbatim. The gate -- record magic + a `05 ff` token + kana -- isolates the real
prompts from code that only coincidentally looks like a record.

Pairs with packers/exemsg.py (the same-size in-place rewriter).
"""
import struct

# inline control tokens: 01ff / 04ff = 2 bytes ; 05ff <u16> = 4 bytes
_CTRL_LEADS = (0x01, 0x04, 0x05)


def _is_ctrl(b, k):
    return k + 1 < len(b) and b[k] in _CTRL_LEADS and b[k + 1] == 0xff


def _ctrl_len(b, k):
    return 4 if b[k] == 0x05 else 2


def records(d):
    """Yield (magic_off, textlen, text_start, text_end) for each embedded message record.
    Shared with the packer so parse and pack agree on record boundaries exactly."""
    d = bytes(d)
    n = len(d)
    out = []
    i = 0
    while i < n - 4:
        if 0x20 <= d[i] <= 0x3f and d[i + 1] == 0xf0:
            ln = struct.unpack_from("<H", d, i + 2)[0]
            if 4 < ln < 400 and i + 2 + ln <= n:
                txt = d[i + 4:i + 2 + ln]
                has_ctrl = b"\x05\xff" in txt
                has_kana = any(0x82 <= txt[j] <= 0x83 for j in range(len(txt) - 1))
                if has_ctrl and has_kana:
                    out.append((i, ln, i + 4, i + 2 + ln))
                    i += 2 + ln
                    continue
        i += 1
    return out


def parse(data):
    d = bytes(data)
    blocks = []
    for (_mo, _ln, ts, te) in records(d):
        k = ts
        while k < te:
            if _is_ctrl(d, k):
                k += _ctrl_len(d, k)
                continue
            if d[k] == 0xff:                       # stray terminator byte between tokens
                k += 1
                continue
            j = k
            while j < te and not _is_ctrl(d, j) and d[j] != 0xff:
                j += 1
            seg = d[k:j]
            if seg:
                blocks.append({"offset": k, "jpBytes": len(seg), "hex": seg.hex(), "speaker": 0})
            k = j
    return blocks
