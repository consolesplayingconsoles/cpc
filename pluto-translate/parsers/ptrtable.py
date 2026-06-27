#!/usr/bin/env python3
"""`ptrtable` parser -- u32 offset table + length-tagged text records.

A generic source FORMAT strategy, not DC-specific (offset tables are everywhere):
the file opens with a little-endian u32 offset table whose first entry is the
table's own byte size (so count = first // 4), each entry pointing at a record
`2d f0 <len> 00 <Shift-JIS text> 01 ff ...`. `01 ff` both separates lines AND
terminates a record -- it's an internal line break when full-width text follows,
the terminator when padding does. One block per record, offset at the text, so
the patcher writes in place. Handles single-line tables (gadget names, ITEMTBL.PAC)
and multi-line ones (gadget hints, INFO\\SECRET.TBL -- breaks kept for round-trip).
The trailing pointer is a 0xffffffff terminator.

    parse(data) -> [{offset, jpBytes, hex, speaker}, ...]   (raw SJIS hex; UI decodes)
"""
import struct

from . import sjis   # fw_lead / fw_trail -- the broader full-width run helpers


def parse(data):
    if len(data) < 4:
        return []
    first = struct.unpack_from("<I", data, 0)[0]
    if first == 0 or first % 4 or first > len(data):
        return []                                  # not a pointer table
    n = first // 4
    ptrs = list(struct.unpack_from("<%dI" % n, data, 0)) + [len(data)]
    blocks = []
    for i in range(n):
        s = ptrs[i]
        if s == 0xffffffff or s >= len(data):      # terminator / out of range
            continue
        e = ptrs[i + 1]
        if e == 0xffffffff or e > len(data) or e <= s:
            e = len(data)
        rec = data[s:e]
        # skip the record header to the first full-width char
        j = 0
        while j + 1 < len(rec) and not (sjis.fw_lead(rec[j]) and sjis.fw_trail(rec[j + 1])):
            j += 1
        # consume the whole payload: full-width chars + internal `01 ff` line breaks
        # (kept, so multi-line records round-trip); stop at the terminating `01 ff`
        # (followed by padding, not text) or any other byte.
        k = j
        while k < len(rec):
            if k + 1 < len(rec) and sjis.fw_lead(rec[k]) and sjis.fw_trail(rec[k + 1]):
                k += 2
            elif (rec[k] == 0x01 and k + 2 < len(rec) and rec[k + 1] == 0xff
                  and sjis.fw_lead(rec[k + 2])):
                k += 2                              # internal line break
            else:
                break                              # terminator / padding
        if k > j:
            blocks.append({"offset": s + j, "jpBytes": k - j,
                           "hex": bytes(rec[j:k]).hex(), "speaker": 0})
    return blocks
