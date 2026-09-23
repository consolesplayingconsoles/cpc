#!/usr/bin/env python3
"""Twiddled Dreamcast PVR codec — decode AND encode, byte-identical round-trip.

This is the reusable core behind translating BAKED-IN text (title menus, logos)
that lives as PVR textures rather than editable strings. Dreamcast textures are
TWIDDLED (Morton / Z-order); decode detwiddles + unpacks the pixel format to
RGBA, encode reverses it. ARGB4444 round-trips EXACTLY because each 4-bit channel
decodes to an exact x17 multiple (decode v -> v*17, encode v -> v>>4 recovers v).

Needs numpy. See textures.md for the full find -> decode -> edit -> encode ->
repack method and the gotchas.
"""
import struct
import numpy as np

PIXFMT = {0: "ARGB1555", 1: "RGB565", 2: "ARGB4444"}

def twiddle_table(n):
    """Morton spread: output[i] = bits of i interleaved into even positions.
    A pixel at (x, y) lives at twiddled index (tw[x] << 1) | tw[y]."""
    seq = np.zeros(n, dtype=np.uint32)
    for i in range(n):
        v = 0; bit = 0; t = i
        while t:
            v |= (t & 1) << (2 * bit); t >>= 1; bit += 1
        seq[i] = v
    return seq

def find_chunk(d, index):
    """(data_offset, w, h, pixfmt_code) for the Nth 'PVRT' chunk in bytes d.
    A PVM is a PVMH container of these; pixel data starts 16 bytes after PVRT."""
    i = 0; n = 0
    while True:
        j = d.find(b"PVRT", i)
        if j < 0:
            raise IndexError("no PVRT chunk %d" % index)
        if n == index:
            pf = d[j + 8]
            w, h = struct.unpack("<HH", d[j + 12:j + 16])
            return j + 16, w, h, pf
        n += 1; i = j + 4

def _twiddled_u16(d, off, w, h):
    """The shared part of every format: read w*h little-endian u16 and un-twiddle to (h, w)."""
    raw = np.frombuffer(d, dtype="<u2", count=w * h, offset=off)
    sx = twiddle_table(w); sy = twiddle_table(h)
    idx = (sx[None, :] << 1) | sy[:, None]
    return raw[idx.ravel()].reshape(h, w).astype(np.uint16)


def _untwiddle_to_bytes(v, w, h):
    """The shared inverse: (h, w) u16 -> twiddled little-endian bytes."""
    sx = twiddle_table(w); sy = twiddle_table(h)
    out = np.zeros(w * h, dtype=np.uint16)
    dst = (sx[None, :] << 1) | sy[:, None]
    out[dst.ravel()] = v.ravel()
    return out.astype("<u2").tobytes()


def decode_rgb565(d, off, w, h):
    """Twiddled RGB565 (pixfmt 1) -> (h, w, 4) uint8 RGBA, alpha forced opaque.

    The opening-sequence text lines (STORYGRA chunks 140-145) are this format, not the ARGB4444
    the SOD banner uses. 565 carries no alpha at all, so the white behind the glyphs is real
    picture, not transparency: a repaint must paint the background, it cannot leave it clear.
    Expansion is the usual bit-replication so the round trip is exact.
    """
    v = _twiddled_u16(d, off, w, h)
    r = ((v >> 11) & 0x1F); g = ((v >> 5) & 0x3F); b = (v & 0x1F)
    r = (r << 3) | (r >> 2); g = (g << 2) | (g >> 4); b = (b << 3) | (b >> 2)
    a = np.full_like(r, 255)
    return np.dstack([r, g, b, a]).astype(np.uint8)


def encode_rgb565(rgba):
    """(h, w, 4) uint8 RGBA -> twiddled RGB565 bytes. Inverse of decode_rgb565 (alpha dropped)."""
    h, w, _ = rgba.shape
    r = rgba[:, :, 0].astype(np.uint16) >> 3
    g = rgba[:, :, 1].astype(np.uint16) >> 2
    b = rgba[:, :, 2].astype(np.uint16) >> 3
    return _untwiddle_to_bytes((r << 11) | (g << 5) | b, w, h)


def decode_argb4444(d, off, w, h):
    """Twiddled ARGB4444 -> (h, w, 4) uint8 RGBA. (ARGB1555 is similar; add its unpack if
    needed — see textures.md. RGB565 is `decode_rgb565`.)"""
    raw = np.frombuffer(d, dtype="<u2", count=w * h, offset=off)
    sx = twiddle_table(w); sy = twiddle_table(h)
    idx = (sx[None, :] << 1) | sy[:, None]          # src twiddled index per (x, y)
    v = raw[idx.ravel()].reshape(h, w).astype(np.uint16)
    a = ((v >> 12) & 0xF) * 17; r = ((v >> 8) & 0xF) * 17
    g = ((v >> 4) & 0xF) * 17;  b = (v & 0xF) * 17
    return np.dstack([r, g, b, a]).astype(np.uint8)

def encode_argb4444(rgba):
    """(h, w, 4) uint8 RGBA -> twiddled ARGB4444 bytes. Inverse of decode;
    byte-identical for data that came from decode_argb4444."""
    h, w, _ = rgba.shape
    r = rgba[:, :, 0].astype(np.uint16) >> 4; g = rgba[:, :, 1].astype(np.uint16) >> 4
    b = rgba[:, :, 2].astype(np.uint16) >> 4; a = rgba[:, :, 3].astype(np.uint16) >> 4
    v = (a << 12) | (r << 8) | (g << 4) | b
    sx = twiddle_table(w); sy = twiddle_table(h)
    out = np.zeros(w * h, dtype=np.uint16)
    dst = (sx[None, :] << 1) | sy[:, None]          # twiddled dest index per (x, y)
    out[dst.ravel()] = v.ravel()
    return out.astype("<u2").tobytes()

if __name__ == "__main__":
    # self-test: decode a chunk then re-encode and confirm byte-identical
    import sys
    d = open(sys.argv[1], "rb").read()
    idx = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    off, w, h, pf = find_chunk(d, idx)
    assert pf == 2, "this self-test expects ARGB4444 (pf=2), got %s" % PIXFMT.get(pf, pf)
    rgba = decode_argb4444(d, off, w, h)
    reenc = encode_argb4444(rgba)
    print("chunk %d: %dx%d %s  round-trip identical: %s"
          % (idx, w, h, PIXFMT[pf], reenc == d[off:off + w * h * 2]))
