#!/usr/bin/env python3
"""In-place file patch for a raw (2352-byte Mode-1 sector) Dreamcast GDI data track.

Why: buildgdi/GDIBuilder -rebuild relay the ISO filesystem and move files to new LBAs; this game
reads assets by hardcoded disc position, so ANY rebuild (even byte-identical) hangs. So we never
rebuild -- we overwrite a same-size file's bytes where they already sit. Zero LBA change: the disc
is byte-identical to the original except the file's own sector user-windows.

Mode-1 raw sector = [0:12] sync, [12:16] header, [16:2064] 2048B user data, [2064:2352] EDC/ECC.
A file's user data is spread across consecutive sectors' [16:2064] windows. We find the file by its
original first-2048 bytes (contiguous in sector 0), then rewrite each sector's user window with the
patched bytes. EDC/ECC left as-is -- Flycast/ODEs don't verify it. mmap so an 865MB track never
loads into RAM (matters on the box).

    inplace.py <track> <orig-file> <patched-file>     # patches <track> IN PLACE

`orig-file` (to locate) and `patched-file` (to write) MUST be the same length.
"""
import sys, os, mmap

SECTOR, USER_OFF, USER = 2352, 16, 2048


def main():
    track_p, orig_p, patch_p = sys.argv[1], sys.argv[2], sys.argv[3]
    orig = open(orig_p, "rb").read()
    patch = open(patch_p, "rb").read()
    if len(orig) != len(patch):
        raise SystemExit("size mismatch: orig %d vs patched %d (must be equal)" % (len(orig), len(patch)))

    n = len(patch)
    nsec = -(-n // USER)                                    # sectors the file spans (last may be partial)

    def read_at(mm, cand):                                  # de-interleave nsec sectors from a candidate
        back, sec = bytearray(), cand - USER_OFF
        for _ in range(nsec):
            back += mm[sec + USER_OFF: sec + USER_OFF + USER]; sec += SECTOR
        return bytes(back[:n])

    fd = os.open(track_p, os.O_RDWR)
    mm = mmap.mmap(fd, 0)
    try:
        # locate by the WHOLE file, not just the first sector: a file header (e.g. the font's) can
        # appear elsewhere, and splicing a false hit corrupts unrelated data. Walk every first-window
        # match, accept only the one where the full de-interleaved file equals `orig`.
        start, pos = -1, 0
        while True:
            cand = mm.find(orig[:min(USER, n)], pos)
            if cand < 0:
                break
            if (cand - USER_OFF) % SECTOR == 0 and read_at(mm, cand) == orig:
                start = cand; break
            pos = cand + 1
        if start < 0:
            raise SystemExit("file not found in track (no full-content match)")
        print("  %s @ %#x (%d sectors, last %d B)" % (os.path.basename(patch_p), start, nsec, n - (nsec - 1) * USER))
        sec = start - USER_OFF
        for i in range(0, n, USER):
            chunk = patch[i:i + USER]                       # last chunk may be < USER; leave the rest of
            mm[sec + USER_OFF: sec + USER_OFF + len(chunk)] = chunk   # that sector's padding untouched
            sec += SECTOR
        mm.flush()
        # round-trip verify straight from the mapping
        back = bytearray()
        sec = start - USER_OFF
        for _ in range(nsec):
            back += mm[sec + USER_OFF: sec + USER_OFF + USER]
            sec += SECTOR
        if bytes(back[:n]) != patch:
            raise SystemExit("VERIFY FAILED: re-read bytes != patched")
        print("  verified in place (%d B track, size unchanged)" % len(mm))
    finally:
        mm.close(); os.close(fd)


if __name__ == "__main__":
    main()
