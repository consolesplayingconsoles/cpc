#!/usr/bin/env python3
"""
metadata.py -- genre / developer / publisher / release year for catalogue games.

Source: libretro-database metadat/<field>/<System>.dat (clrmamepro text, no account).
<System> is the system's libretro name, the same one its thumbnails repo is named after
("Sega_-_Mega_Drive_-_Genesis" -> "Sega - Mega Drive - Genesis").

    game (
        comment "007 - NightFire (USA, Europe) (En,Fr,De)"
        genre "Shooter"
        rom ( crc 56C83C16 )
    )

Disc systems key some entries by `serial` (the header product number) and name them by
their track file instead of a comment. A game matches an entry by header ID == serial
first, then by name exactly like covers do (covers.best_match: title key, most shared
tags). Coverage is uneven (cartridge systems are rich, Saturn has almost nothing), so a
field with no value is simply absent.

Cache: catalogue/<system>/meta/<field>.json  parsed entries, fetched once.

Pure stdlib, 3.6-safe, ASCII only.
"""
import json
import os
import re
from urllib.parse import quote
from urllib.request import Request, urlopen

try:
    from . import covers, names, store
except ImportError:
    import covers
    import names
    import store

FIELDS = ("genre", "developer", "publisher", "releaseyear")
DAT = "https://raw.githubusercontent.com/libretro/libretro-database/master/metadat/%s/%s.dat"
_BLOCK = re.compile(r"^game \($(.*?)^\)", re.M | re.S)
_TRACK = re.compile(r"\s*\(Track \d+\)$", re.I)


def libretro_name(thumbnails_repo):
    return thumbnails_repo.replace("_", " ") if thumbnails_repo else None


def parse_dat(text, field):
    """-> [{"name", "value", "serial"}] for every game block carrying `field`."""
    out = []
    for m in _BLOCK.finditer(text):
        body = m.group(1)
        value = re.search(r'^\s*%s\s+"([^"]*)"' % re.escape(field), body, re.M)
        if not value or not value.group(1).strip():
            continue
        name = re.search(r'^\s*(?:comment|name)\s+"([^"]*)"', body, re.M)
        if name:
            name = name.group(1)
        else:
            rom = re.search(r'rom \(\s*name "([^"]*)"', body)
            name = _TRACK.sub("", os.path.splitext(rom.group(1))[0]) if rom else None
        serial = re.search(r'serial\s+"([^"]*)"', body)
        if name or serial:
            out.append({"name": name, "value": value.group(1).strip(),
                        "serial": serial.group(1) if serial else None})
    return out


def _entries(root, system, field, db_name, opener, timeout):
    p = os.path.join(root, system, "meta", field + ".json")
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    try:
        with opener(Request(DAT % (field, quote(db_name)), headers={"User-Agent": "cpc-pluto"}), timeout=timeout) as r:
            entries = parse_dat(r.read().decode("utf-8", "replace"), field)
    except Exception as exc:
        if getattr(exc, "code", None) != 404:
            raise                                   # network trouble: retry next sync
        entries = []                                # no such file for this system: cache the empty
    d = os.path.dirname(p)
    if not os.path.isdir(d):
        os.makedirs(d)
    with open(p, "w") as f:
        json.dump(entries, f)
    return entries


def _serial(s):
    """Serials are written with and without dashes (T42903M vs T-42903M): compare bare."""
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def index(entries):
    """Prepare one field's entries for fast lookups: by serial, exact name, title key."""
    by_serial, by_name, by_key = {}, {}, {}
    for e in entries:
        if e["serial"]:
            by_serial.setdefault(_serial(e["serial"]), e["value"])
        if e["name"]:
            by_name.setdefault(e["name"], e["value"])
            k = names.key(names.parse(e["name"] + ".x")["title"])
            by_key.setdefault(k, []).append(e["name"])
    return {"serial": by_serial, "name": by_name, "key": by_key}


def lookup(game, idx):
    """Value for one game from one field's index, or None. Header ID, exact name, then
    same title key with the most tags in common (the covers rule)."""
    for gid in game.get("ids") or []:
        if _serial(gid) in idx["serial"]:
            return idx["serial"][_serial(gid)]
    for n in covers.candidates(game):
        if n in idx["name"]:
            return idx["name"][n]
    pool = idx["key"].get(names.key(covers.match_title(game)))
    if not pool:
        return None
    return idx["name"][covers.best_match(game, pool)]


def annotate(root, system, doc, thumbnails_repo, opener=urlopen, timeout=20):
    """Set game["meta"] = {field: value} on every game in doc (in place). -> filled count.
    Raises on network trouble so the caller can warn; a partial doc is never saved."""
    db_name = libretro_name(thumbnails_repo)
    if not db_name:
        return 0
    labels = store.load_labels(root).get(system) or {}
    tables = {f: index(_entries(root, system, f, db_name, opener, timeout)) for f in FIELDS}
    filled = 0
    for key, game in doc["games"].items():
        g = dict(game, key=key, label=labels.get(key))
        meta = {}
        for field, entries in tables.items():
            v = lookup(g, entries) if entries["name"] or entries["serial"] else None
            if v:
                meta["year" if field == "releaseyear" else field] = v
        game["meta"] = meta
        filled += bool(meta)
    return filled
