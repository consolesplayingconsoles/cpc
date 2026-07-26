#!/usr/bin/env python3
"""`itemtbl` parser -- Boku Doraemon `DOUGU/ITEMTBL.PAC` (gadget names + descriptions).

The file is TWO structures in one, so the generic `ptrtable` parser (which only knows
the pointer table) sees just half of it:

  * NAMES: a u32 pointer table @0 -> gadget-name `2df0` records, packed in 0x274..~0x1800.
    Parsed by delegating to `ptrtable`.
  * DESCRIPTIONS: one record PER 0x800 SECTOR from 0x1800 (each sector = an
    `08 00 00 00 ff ff ff ff` header + a multi-line `2df0` record + zero padding). The
    game finds a gadget's description by index*0x800, so they are position-locked and
    are NOT in the pointer table. Multi-line: `01 ff` line breaks AND `04 ff` page breaks.

Emits name blocks (offset < 0x1800) and description blocks (offset >= 0x1800) in one
list; the packer tells them apart by that 0x1800 boundary.
"""
from . import ptrtable, sjis

DESC_BASE = 0x1800
SECTOR = 0x800


def _walk_text(rec, start):
    """From `start`, skip to the first full-width char then consume the payload -- full-width
    chars plus internal `01 ff` / `04 ff` breaks (kept, so the record round-trips) -- stopping
    at the terminating control (a break NOT followed by more text, or any other byte)."""
    p = start
    while p + 1 < len(rec) and not (sjis.fw_lead(rec[p]) and sjis.fw_trail(rec[p + 1])):
        p += 1
    k = p
    while k < len(rec):
        if k + 1 < len(rec) and sjis.fw_lead(rec[k]) and sjis.fw_trail(rec[k + 1]):
            k += 2
        elif (rec[k] in (0x01, 0x04) and k + 2 < len(rec) and rec[k + 1] == 0xff
              and sjis.fw_lead(rec[k + 2])):
            k += 2                                  # internal line (01ff) / page (04ff) break
        else:
            break
    return p, k


def parse(data):
    blocks = ptrtable.parse(data)                   # the names (pointer-table records)
    off = DESC_BASE
    while off + 8 <= len(data):
        sec = data[off:off + SECTOR]
        j = sec.find(b"\x2d\xf0")
        if 0 <= j < 0x20:                           # a description record leads this sector
            p, k = _walk_text(sec, j + 4)           # skip 2df0 + u16 len
            if k > p:
                blocks.append({"offset": off + p, "jpBytes": k - p, "desc": True,
                               "hex": bytes(sec[p:k]).hex(), "speaker": 0})
        off += SECTOR
    return blocks


def budget(data):
    """TEXT-byte budget the gadget NAMES share: the item area (pointer-table end .. 0x1800) minus
    the fixed per-record overhead (magic + len + trailer + inter-record padding), so the UI can sum
    caBytes(ca) straight against it -- one aggregate, like a STORY box. Names spill NOWHERE (the
    packer keeps them in the item area), so this single total is the real fit signal; a gadget can
    borrow the slack a shorter one leaves. Returns {"names": <text-byte budget>}."""
    import struct
    n = struct.unpack_from("<I", data, 0)[0] // 4
    item_area = DESC_BASE - n * 4
    names = [b for b in ptrtable.parse(data)
             if (b["offset"] if isinstance(b["offset"], int) else int(b["offset"], 16)) < DESC_BASE]
    ptrs = sorted(p for p in struct.unpack_from("<%dI" % n, data, 0)
                  if p not in (0xffffffff, 0xbfffffff) and p and p < DESC_BASE)
    if not ptrs:
        return {"names": item_area}
    last = ptrs[-1]
    body = (last + 4 + struct.unpack_from("<H", data, last + 2)[0]) - n * 4   # bytes the records use
    overhead = body - sum(b["jpBytes"] for b in names)                        # non-text bytes
    # Each DESCRIPTION has its OWN 0x800 sector (separate budget from the shared name area): the
    # sector minus its 8-byte header and the record framing (2df0 + len + trailer).
    return {"names": max(0, item_area - overhead), "desc": SECTOR - 8 - 8}
