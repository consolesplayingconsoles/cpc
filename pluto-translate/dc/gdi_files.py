#!/usr/bin/env python3
"""List and read files straight off a GDI's high-density data track (ISO9660 at LBA 45000), no extract.

buildgdi -extract copies the whole disc (minutes, gigabytes) when a tool wants two or three files; this
reads just those files' sectors. Stdlib only, so it runs on the box and on the Mac alike.

    gdi_files.py <gdi>                   # {"files": [{"path", "lba", "size"}, ...]}
    gdi_files.py <gdi> <name> <out>      # write one file (matched by path or bare name)
"""
import json
import os
import struct
import sys

BASE = 45000                                             # GD-ROM high-density session


def _track(gdi):
    """(track file, sector size) of the data track starting at LBA 45000."""
    base = os.path.dirname(gdi)
    for line in open(gdi).read().splitlines()[1:]:
        p = line.split()
        if len(p) >= 6 and p[1] == str(BASE) and p[2] == "4":
            return os.path.join(base, " ".join(p[4:-1])), int(p[3])
    raise SystemExit("no high-density data track in %s" % gdi)


class Disc:
    def __init__(self, gdi):
        path, self.sector = _track(gdi)
        self.f = open(path, "rb")
        self.skip = 16 if self.sector == 2352 else 0     # Mode 1 raw: user data after sync + header

    def read(self, lba, size):
        out = bytearray()
        for i in range((size + 2047) // 2048):
            self.f.seek((lba - BASE + i) * self.sector + self.skip)
            out += self.f.read(2048)
        return bytes(out[:size])

    def files(self):
        pvd = self.read(BASE + 16, 2048)
        if pvd[1:6] != b"CD001":
            raise SystemExit("no ISO9660 volume on the data track")
        out = []

        def walk(lba, size, prefix):
            d = self.read(lba, size)
            i = 0
            while i < len(d):
                n = d[i]
                if n == 0:
                    i = (i // 2048 + 1) * 2048
                    continue
                ext, sz = struct.unpack_from("<I", d, i + 2)[0], struct.unpack_from("<I", d, i + 10)[0]
                name = d[i + 33:i + 33 + d[i + 32]]
                if name not in (b"\0", b"\1"):
                    name = name.decode("ascii", "replace").split(";")[0]
                    if d[i + 25] & 2:
                        walk(ext, sz, prefix + name + "/")
                    else:
                        out.append({"path": prefix + name, "lba": ext, "size": sz})
                i += n
        root = pvd[156:190]
        walk(struct.unpack_from("<I", root, 2)[0], struct.unpack_from("<I", root, 10)[0], "/")
        return out

    def file(self, name):
        """Bytes of the file whose path, or bare name, is `name` (case-insensitive)."""
        key = name.upper().lstrip("/")
        for e in self.files():
            if e["path"].upper().lstrip("/") == key or os.path.basename(e["path"]).upper() == key:
                return self.read(e["lba"], e["size"])
        raise KeyError(name)


if __name__ == "__main__":
    if len(sys.argv) == 2:
        print(json.dumps({"files": Disc(sys.argv[1]).files()}))
    elif len(sys.argv) == 4:
        open(sys.argv[3], "wb").write(Disc(sys.argv[1]).file(sys.argv[2]))
    else:
        sys.exit(__doc__)
