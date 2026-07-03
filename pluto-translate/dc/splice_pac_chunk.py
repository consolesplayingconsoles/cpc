#!/usr/bin/env python3
"""Splice ONE patched PVR chunk into a big PAC that already lives in the GDI track -- in place,
without ever loading the whole PAC. For STORYGRA.PAC (~464 MB) inplace.py's whole-file locate +
verify is infeasible on the box, but only a single 128 KB chunk changed, so we splice just that.

How: the PAC sits contiguously in the track's Mode-1 user windows (2048 B per 2352 B sector). We
  1. find where the PAC starts in the track by its first user-window (2048 B) signature, at a
     sector boundary, and CONFIRM by checking the original chunk bytes sit exactly where expected;
  2. map the chunk's intra-file byte range onto the sector user-windows and overwrite it.
Only the PAC's first 2048 B and the chunk region are ever read -- memory stays tiny.

    splice_pac_chunk.py <track> <orig-PAC> <chunk-bin> <chunk-index>
"""
import sys, os, mmap, struct

SECTOR, USER_OFF, USER = 2352, 16, 2048


def nth_pvrt_offset(path, n):
    """File offset of the n-th 'PVRT' via a streaming scan (overlap keeps a split marker findable)."""
    with open(path, "rb") as f:
        count, base, tail = 0, 0, b""
        while True:
            buf = f.read(1 << 20)
            if not buf:
                return -1
            hay = tail + buf
            pos = 0
            while True:
                k = hay.find(b"PVRT", pos)
                if k < 0:
                    break
                if count == n:
                    return base - len(tail) + k
                count += 1
                pos = k + 4
            tail = hay[-3:]
            base += len(buf)


def read_slice(path, off, length):
    with open(path, "rb") as f:
        f.seek(off)
        return f.read(length)


def deinterleave(mm, start_user, o, length):
    """Read `length` bytes of the file starting at intra-file offset `o`, from the track user windows.
    start_user = track offset of the file's first user byte (sector boundary + USER_OFF)."""
    out = bytearray()
    while length > 0:
        k, within = divmod(o, USER)
        seg = min(USER - within, length)
        p = start_user + k * SECTOR + within
        out += mm[p:p + seg]
        o += seg
        length -= seg
    return bytes(out)


def splice(mm, start_user, o, data):
    length = len(data)
    i = 0
    while length > 0:
        k, within = divmod(o, USER)
        seg = min(USER - within, length)
        p = start_user + k * SECTOR + within
        mm[p:p + seg] = data[i:i + seg]
        o += seg
        i += seg
        length -= seg


def main():
    track_p, orig_p, chunk_p, idx = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
    j = nth_pvrt_offset(orig_p, idx)
    if j < 0:
        raise SystemExit("chunk #%d (PVRT) not found in %s" % (idx, orig_p))
    data_off = j + 16                                   # pixel data starts 16 B after PVRT
    chunk = open(chunk_p, "rb").read()
    L = len(chunk)
    sig = read_slice(orig_p, 0, min(USER, os.path.getsize(orig_p)))
    orig_chunk = read_slice(orig_p, data_off, L)

    fd = os.open(track_p, os.O_RDWR)
    mm = mmap.mmap(fd, 0)
    try:
        pos = 0
        while True:
            cand = mm.find(sig, pos)
            if cand < 0:
                raise SystemExit("PAC start not found in track")
            if (cand - USER_OFF) % SECTOR == 0:
                start_user = cand
                if deinterleave(mm, start_user, data_off, L) == orig_chunk:   # confirm it's the right file
                    break
            pos = cand + 1
        splice(mm, start_user, data_off, chunk)
        mm.flush()
        if deinterleave(mm, start_user, data_off, L) != chunk:
            raise SystemExit("VERIFY FAILED: re-read chunk != patched")
        print("  spliced chunk #%d (%d B) @ file+%#x  (verified)" % (idx, L, data_off))
    finally:
        mm.close(); os.close(fd)


if __name__ == "__main__":
    main()
