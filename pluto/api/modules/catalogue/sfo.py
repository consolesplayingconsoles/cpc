#!/usr/bin/env python3
"""
sfo.py -- PARAM.SFO, the PS3's own label for a title.

A PS3 game carries no cartridge header; what it has is PARAM.SFO, a small key/value
table sitting next to the executable (`/dev_hdd0/game/<id>/PARAM.SFO` for an installed
title, `<dir>/PS3_GAME/PARAM.SFO` inside a folder game). TITLE is the name Sony shows in
the XMB and TITLE_ID the disc serial, so the two together are exactly what the catalogue
reads out of a header elsewhere.

Format: "\\0PSF" + version, then three offsets (key table, data table, entry count) and
`count` 16-byte index records. Each record says where its key is, how its value is
encoded (0x0204 = UTF-8, 0x0404 = u32), how long the value is, and where it starts.

Pure stdlib, 3.6-safe, ASCII only.
"""
import struct

MAGIC = b"\x00PSF"
_UTF8, _U32 = 0x0204, 0x0404


def parse(data):
    """PARAM.SFO bytes -> {key: str|int}. {} when it isn't a PARAM.SFO or is truncated:
    a drive read that came back short must not look like a title with no name."""
    if not data or data[:4] != MAGIC or len(data) < 20:
        return {}
    key_off, data_off, count = struct.unpack("<III", data[8:20])
    out = {}
    for i in range(count):
        rec = 20 + i * 16
        if rec + 16 > len(data):
            break
        ko, fmt, length, _max, do = struct.unpack("<HHIII", data[rec:rec + 16])
        k_at = key_off + ko
        end = data.find(b"\0", k_at)
        if k_at >= len(data) or end < 0 or data_off + do + length > len(data):
            break
        key = data[k_at:end].decode("ascii", "replace")
        raw = data[data_off + do:data_off + do + length]
        if fmt == _U32:
            out[key] = struct.unpack("<I", raw[:4])[0] if len(raw) >= 4 else 0
        else:
            out[key] = raw.rstrip(b"\0").decode("utf-8", "replace")
    return out


def title(data):
    """(serial, name, category) from PARAM.SFO bytes; each is "" when the file lacks it.

    CATEGORY says what the thing IS, which decides whether it can be booted at all:
    HG = a game installed on the drive, standalone and bootable. GD = game DATA, the
    install half of a disc game -- mounting it gets you "loaded" and nothing else,
    because the console still wants the disc. SF/CB = system apps and stores.
    """
    d = parse(data)
    return (str(d.get("TITLE_ID") or ""), str(d.get("TITLE") or ""), str(d.get("CATEGORY") or ""))


BOOTABLE = ("HG", "SF", "CB", "AP", "AM")     # GD is an install, not something to boot
