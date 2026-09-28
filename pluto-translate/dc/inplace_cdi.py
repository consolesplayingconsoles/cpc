#!/usr/bin/env python3
"""In-place file patch for a CDI (Mode-2 Form-1) Dreamcast image -- the CDI twin of `inplace.py`.

Same rule as the GDI build: never rebuild the image. This game reads assets by hardcoded disc
position, so any rebuild hangs it. You overwrite a same-size file's bytes where they already sit,
and the image stays byte-identical everywhere else.

Two things differ from `inplace.py`, and they are the whole reason this is a separate tool:

  * SECTOR LAYOUT. A GDI data track is Mode 1: 12 sync + 4 header + 2048 user + 288 EDC/ECC, so the
    user window starts at byte 16. A CDI is Mode 2 Form 1: 12 sync + 4 header + 8 subheader + 2048
    user + 280 EDC/ECC, so the window starts at 24. Get this wrong and you write 8 bytes off into
    the tail of the previous sector.
  * EDC/ECC. `inplace.py` leaves the error-correction bytes stale, because Flycast and the ODEs
    that read a GDI do not check them. A CDI is what a real burner writes to a CD-R, and the drive
    DOES care, so every sector you touch gets its EDC and its P/Q parity recomputed here.

    inplace_cdi.py <image> <orig-file> <patched-file>
    inplace_cdi.py --chunk <image> <orig-PAC> <chunk-bin> <chunk-index>

The first form patches a whole file (orig and patched MUST be the same length; orig is only used to
find the file in the image). The second is the twin of `splice_pac_chunk.py`: it rewrites ONE PVR
chunk inside a huge PAC without ever loading the PAC, which is how the opening-sequence lines and
the SOD banner get patched inside the ~464 MB STORYGRA.PAC.

Both forms read the patched region back and compare before they report success.
"""
import sys, os, mmap, struct

SECTOR, USER_OFF, USER = 2352, 24, 2048          # Mode 2 Form 1: user data starts 24 B in


# --- EDC (CRC-32 with the CD polynomial) and P/Q parity (Reed-Solomon over GF(256)) -------------
# Straight out of ECMA-130. The tables are built once at import; a full disc's worth of sectors is
# never touched, only the handful you patch.
_EDC_T = []
for _i in range(256):
    _e = _i
    for _ in range(8):
        _e = (_e >> 1) ^ (0xD8018001 if _e & 1 else 0)
    _EDC_T.append(_e)

_F = [0] * 256          # multiply by 2 in GF(256), generator polynomial 0x11D
_B = [0] * 256          # the inverse lookup the parity pass needs
for _i in range(256):
    _j = ((_i << 1) ^ (0x11D if _i & 0x80 else 0)) & 0xFF
    _F[_i] = _j
    _B[_i ^ _j] = _i


def edc(data):
    c = 0
    for x in data:
        c = (c >> 8) ^ _EDC_T[(c ^ x) & 0xFF]
    return c


def _parity(buf, major_count, minor_count, major_mult, minor_inc, out):
    """One Reed-Solomon pass over the sector, writing `out` (P or Q parity)."""
    size = major_count * minor_count
    for major in range(major_count):
        idx = (major >> 1) * major_mult + (major & 1)
        a = b = 0
        for _ in range(minor_count):
            t = buf[idx]
            idx += minor_inc
            if idx >= size:
                idx -= size
            a ^= t
            b ^= t
            a = _F[a]
        a = _B[_F[a] ^ b]
        out[major] = a
        out[major + major_count] = a ^ b


def fix_sector(sector):
    """Refresh EDC + P/Q for a 2352-byte sector whose user data you just rewrote."""
    s = bytearray(sector)
    struct.pack_into("<I", s, 2072, edc(bytes(s[16:2072])))
    # The parity is computed with the sector address zeroed, then the real header stays as it was.
    buf = bytearray(s[12:2076])
    buf[0:4] = b"\0\0\0\0"
    p = bytearray(172); _parity(buf, 86, 24, 2, 86, p)
    q = bytearray(104); _parity(bytes(buf) + bytes(p), 52, 43, 86, 88, q)
    s[2076:2248] = p
    s[2248:2352] = q
    return bytes(s)


# --- mapping a file's bytes onto the sector user windows ----------------------------------------

def deinterleave(mm, start_user, off, length):
    """Read `length` bytes at intra-file offset `off`, gathered from the user windows.
    start_user = image offset of the file's first user byte."""
    out = bytearray()
    while length > 0:
        k, within = divmod(off, USER)
        seg = min(USER - within, length)
        p = start_user + k * SECTOR + within
        out += mm[p:p + seg]
        off += seg
        length -= seg
    return bytes(out)


def splice(mm, start_user, off, data):
    """Write `data` at intra-file offset `off`, fixing every sector it lands in."""
    touched = set()
    i, length = 0, len(data)
    while length > 0:
        k, within = divmod(off, USER)
        seg = min(USER - within, length)
        p = start_user + k * SECTOR + within
        mm[p:p + seg] = data[i:i + seg]
        touched.add(start_user - USER_OFF + k * SECTOR)
        off += seg
        i += seg
        length -= seg
    for sec in sorted(touched):
        mm[sec:sec + SECTOR] = fix_sector(mm[sec:sec + SECTOR])
    return len(touched)


def find_file(mm, signature, confirm=None):
    """Image offset of the first user byte of the file whose first 2048 B are `signature`.

    A signature can repeat (two files can start with the same block), so `confirm` gets a chance to
    reject a candidate by reading something further in -- that is what stops a chunk splice writing
    into the wrong PAC."""
    pos = 0
    while True:
        cand = mm.find(signature, pos)
        if cand < 0:
            return -1
        if (cand - USER_OFF) % SECTOR == 0 and (confirm is None or confirm(cand)):
            return cand
        pos = cand + 1


def patch_file(image, orig_p, patch_p):
    orig = open(orig_p, "rb").read()
    patch = open(patch_p, "rb").read()
    if len(orig) != len(patch):
        raise SystemExit("size mismatch: orig %d vs patched %d (must be equal)" % (len(orig), len(patch)))

    fd = os.open(image, os.O_RDWR)
    mm = mmap.mmap(fd, 0)
    try:
        # The WHOLE original has to match, not just the block that located it. A CDI is a conversion
        # of the GD-ROM, and the conversion edits the game: this disc's 1ST_READ.BIN carries 12 bytes
        # of self-boot patch the GDI's copy does not have. Locating on the first 2048 bytes alone
        # matched it happily, and writing the GDI-derived build over it reverted those 12 bytes, so
        # the game looked for a GD-ROM, did not find one, and dropped to the BIOS. Refuse instead:
        # a file that differs must be rebuilt from THIS disc's copy.
        start = find_file(mm, orig[:USER],
                          confirm=lambda c: deinterleave(mm, c, 0, len(orig)) == orig)
        if start < 0:
            loose = find_file(mm, orig[:USER])
            if loose >= 0:
                on_disc = deinterleave(mm, loose, 0, len(orig))
                first = next(i for i in range(len(orig)) if on_disc[i] != orig[i])
                n = sum(1 for i in range(len(orig)) if on_disc[i] != orig[i])
                raise SystemExit(
                    "%s: this image's copy differs from the original you passed (%d bytes, first at %d).\n"
                    "Rebuild the patch from THIS image's copy -- writing the other disc's version would\n"
                    "revert whatever the conversion changed." % (os.path.basename(orig_p), n, first))
            raise SystemExit("%s not found in %s" % (os.path.basename(orig_p), os.path.basename(image)))
        nsec = splice(mm, start, 0, patch)
        mm.flush()
        if deinterleave(mm, start, 0, len(patch)) != patch:
            raise SystemExit("VERIFY FAILED: re-read != patched for %s" % os.path.basename(patch_p))
        print("  %-22s %d sectors @ %#x (verified)" % (os.path.basename(patch_p), nsec, start))
    finally:
        mm.close(); os.close(fd)


def nth_pvrt_offset(path, n):
    """File offset of the n-th 'PVRT' marker, found by streaming so a 464 MB PAC never loads."""
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


def patch_chunk(image, orig_pac, chunk_p, index):
    j = nth_pvrt_offset(orig_pac, index)
    if j < 0:
        raise SystemExit("chunk #%d (PVRT) not found in %s" % (index, orig_pac))
    data_off = j + 16                                  # pixel data starts 16 B past the PVRT marker
    chunk = open(chunk_p, "rb").read()
    sig = read_slice(orig_pac, 0, min(USER, os.path.getsize(orig_pac)))
    orig_chunk = read_slice(orig_pac, data_off, len(chunk))

    fd = os.open(image, os.O_RDWR)
    mm = mmap.mmap(fd, 0)
    try:
        start = find_file(
            mm, sig,
            confirm=lambda c: deinterleave(mm, c, data_off, len(chunk)) == orig_chunk)
        if start < 0:
            raise SystemExit("%s not found in %s" % (os.path.basename(orig_pac), os.path.basename(image)))
        nsec = splice(mm, start, data_off, chunk)
        mm.flush()
        if deinterleave(mm, start, data_off, len(chunk)) != chunk:
            raise SystemExit("VERIFY FAILED: re-read chunk #%d != patched" % index)
        print("  chunk #%-4d %d B, %d sectors @ file+%#x (verified)" % (index, len(chunk), nsec, data_off))
    finally:
        mm.close(); os.close(fd)


def main():
    a = sys.argv[1:]
    if a[:1] == ["--chunk"]:
        if len(a) != 5:
            raise SystemExit(__doc__.strip().splitlines()[-6].strip())
        patch_chunk(a[1], a[2], a[3], int(a[4]))
    elif len(a) == 3:
        patch_file(a[0], a[1], a[2])
    else:
        raise SystemExit("usage: inplace_cdi.py <image> <orig> <patched>\n"
                         "       inplace_cdi.py --chunk <image> <orig-PAC> <chunk-bin> <index>")


if __name__ == "__main__":
    main()
