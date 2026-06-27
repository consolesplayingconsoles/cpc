#!/usr/bin/env python3
"""Read a Dreamcast disc's IP.BIN metadata (title, region, product #, version,
date, maker) straight from the GDI's high-density data track.

IP.BIN is the disc BOOTSTRAP, not an ISO file -- it sits at the start of the
high-density data session (LBA 45000), so there's no buildgdi extract: just a few
KB read off the track. Fast enough to fetch instantly, before /sources scans.

Codec-free (Batocera has no shift_jis codec): ASCII fields are decoded here; the
title also ships as raw hex so the browser can shift_jis-decode JP titles.

    meta.py <gdi-path>
"""
import json
import os
import sys

REGION = {"J": "Japan", "U": "USA", "E": "Europe"}


def _track_at_lba(gdi, lba):
    """The data-track file (type 4) starting at the given LBA, from the .gdi."""
    base = os.path.dirname(gdi)
    for line in open(gdi).read().splitlines()[1:]:   # line 0 is the track count
        p = line.split()
        if len(p) >= 6 and p[1] == str(lba) and p[2] == "4":
            return os.path.join(base, " ".join(p[4:-1]))   # filename may have spaces
    return None


def main(gdi):
    track = _track_at_lba(gdi, 45000)                # GD-ROM high-density session start
    if not track or not os.path.isfile(track):
        print('{"error":"no high-density data track found"}')
        return
    with open(track, "rb") as fh:
        data = fh.read(8192)
    i = data.find(b"SEGA SEGAKATANA")
    if i < 0:
        print('{"error":"no IP.BIN bootstrap found"}')
        return
    ip = data[i:i + 256]

    def a(s, e):
        return ip[s:e].decode("ascii", "replace").rstrip()

    date = a(80, 88)
    meta = {
        "title":    a(128, 208),                                   # ASCII title (most games)
        "titleHex": ip[128:208].rstrip(b"\x20\x00").hex(),         # raw -- shift_jis for JP titles
        "region":   [REGION[c] for c in a(48, 56) if c in REGION] or None,
        "product":  a(64, 74),
        "version":  a(74, 80),
        "date":     "%s-%s-%s" % (date[:4], date[4:6], date[6:8]) if len(date) == 8 and date.isdigit() else date,
        "maker":    a(16, 32),
    }
    print(json.dumps({"meta": meta}))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('{"error":"usage: meta.py <gdi>"}')
        sys.exit(1)
    main(sys.argv[1])
