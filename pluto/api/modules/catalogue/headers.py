#!/usr/bin/env python3
"""
headers.py -- pull a game's ID and internal title out of the first bytes of a ROM.

The ID is the first thing a file is matched on (names.key() is the fallback), so a
renamed file or a mod that keeps its base game's header still lands on the right game.
Readers are keyed by FORMAT, not system: config/consoles.json `systems.<x>.header` says
which format a system uses (mastersystem and gamegear both use "sms").
Callers hand over the first HEAD_BYTES of the file; which file that is for a disc
(.gdi -> track03, .cue -> first .bin) is the scanner's job, not this module's.

FORMATS
  megadrive  0x100 "SEGA", 0x150 overseas title (48), 0x180 serial (14),
             0x1F0 region: letters "JUE" or one hex digit (bit0 Japan, bit1 Asia,
             bit2 USA, bit3 Europe)
  gba        0x0A0 title (12), 0x0AC game code (4), region = code's 4th char
  sms        "TMR SEGA" at 0x7FF0/0x3FF0/0x1FF0, product code BCD at +0xC..+0xE,
             region = high nibble of +0xF (3/5 Japan, 4/6 Export, 7 World)
  saturn     IP.BIN "SEGA SEGASATURN ", product number +0x20 (10), area +0x40 (10),
             title +0x60 (112)
  dreamcast  IP.BIN "SEGA SEGAKATANA ", area +0x30 (8), product number +0x40 (10),
             title +0x80 (128)

Every reader returns {"id", "title", "regions"}. Regions come ONLY from here.

Disc IP.BIN sits at 0 in a 2048-byte image and at 0x10 in a raw 2352-byte one.
No format (or .chd, .smd interleaved, a missing header) returns None: match by name.

Pure stdlib, 3.6-safe, ASCII only.
"""
HEAD_BYTES = 0x8000


def _text(b):
    return b.decode("ascii", "replace").replace("\ufffd", "?").strip(" \x00")


def _codes(text, table):
    out = []
    for c in text:
        r = table.get(c)
        if r and r not in out:
            out.append(r)
    return out


_MD_LETTERS = {"J": "Japan", "U": "USA", "E": "Europe"}
_MD_BITS    = [(1, "Japan"), (2, "Asia"), (4, "USA"), (8, "Europe")]


def _md_regions(raw):
    t = _text(raw)
    if t and all(c in _MD_LETTERS for c in t):
        return _codes(t, _MD_LETTERS)
    if len(t) == 1 and t in "0123456789ABCDEF":
        n = int(t, 16)
        return [name for bit, name in _MD_BITS if n & bit]
    return []


def _megadrive(h):
    if len(h) < 0x1F3 or h[0x100:0x104] != b"SEGA":
        return None
    return {"id": _text(h[0x180:0x18E]), "title": _text(h[0x150:0x180]) or _text(h[0x120:0x150]),
            "regions": _md_regions(h[0x1F0:0x1F3])}


_GBA_REGIONS = {"J": "Japan", "E": "USA", "P": "Europe", "D": "Germany", "F": "France",
                "I": "Italy", "S": "Spain", "H": "Netherlands", "K": "Korea", "C": "China",
                "X": "Europe", "Y": "Europe"}


def _gba(h):
    if len(h) < 0xB0:
        return None
    code = _text(h[0xAC:0xB0])
    if len(code) != 4 or not code.isalnum():
        return None
    return {"id": code, "title": _text(h[0xA0:0xAC]), "regions": _codes(code[3], _GBA_REGIONS)}


def _bcd(b):
    return (b >> 4) * 10 + (b & 0x0F)


_SMS_REGIONS = {"3": "Japan", "4": "Export", "5": "Japan", "6": "Export", "7": "World"}


def _sms(h):
    for base in (0x7FF0, 0x3FF0, 0x1FF0):
        if len(h) >= base + 0x10 and h[base:base + 8] == b"TMR SEGA":
            code = (h[base + 0xE] >> 4) * 10000 + _bcd(h[base + 0xD]) * 100 + _bcd(h[base + 0xC])
            return {"id": "%05d" % code, "title": "",
                    "regions": _codes(str(h[base + 0xF] >> 4), _SMS_REGIONS)}
    return None


_SATURN_AREAS = {"J": "Japan", "T": "Asia", "U": "USA", "B": "Brazil", "K": "Korea",
                 "A": "Asia", "E": "Europe", "L": "Latin America"}
_DC_AREAS     = {"J": "Japan", "U": "USA", "E": "Europe"}


def _ipbin(h, magic, id_off, title_off, title_len, area_off, area_len, areas):
    for base in (0x00, 0x10):
        if h[base:base + 16] == magic:
            s = h[base:]
            return {"id": _text(s[id_off:id_off + 10]), "title": _text(s[title_off:title_off + title_len]),
                    "regions": _codes(_text(s[area_off:area_off + area_len]), areas)}
    return None


_READERS = {
    "megadrive": _megadrive,
    "gba":       _gba,
    "sms":       _sms,
    "saturn":    lambda h: _ipbin(h, b"SEGA SEGASATURN ", 0x20, 0x60, 112, 0x40, 10, _SATURN_AREAS),
    "dreamcast": lambda h: _ipbin(h, b"SEGA SEGAKATANA ", 0x40, 0x80, 128, 0x30, 8, _DC_AREAS),
}


def read(fmt, head):
    """-> {"id", "title", "regions"} or None when there is no such format or no header."""
    reader = _READERS.get(fmt)
    if reader is None:
        return None
    got = reader(bytes(head))
    return got if got and got["id"] else None
