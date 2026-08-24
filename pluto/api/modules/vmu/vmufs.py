#!/usr/bin/env python3
"""
vmufs.py -- read the Dreamcast VMU filesystem out of a raw 128KB image.

Pluto owns this rather than the Pi hub because the sync logic it feeds (crc32,
the /saves/<console> ledger, conflict detection) all lives in api.py, and the
Batocera side stores Dreamcast saves as whole VMU images too -- so the same
parser serves both nodes. The hub only hands over the raw bytes.

READ ONLY, by design: this backs saves up to the cloud and nothing here writes
to a VMU. Adding a writer means touching real hardware, which is a separate
decision from backing progress up.

Image layout (256 blocks x 512 bytes):
    255       root / superblock -- filesystem geometry
    254       FAT (1 block, 256 little-endian u16 entries)
    253..241  directory (13 blocks, indexed HIGH to LOW), 200 x 32-byte entries
    0..199    user data

The root block declares that geometry at 0x46..0x50. Real cards in the wild
leave it zeroed, so an uninitialised field falls back to the standard layout
above -- which is what every image we've read actually uses.

FAT entry: 0xFFFC = free, 0xFFFA = last block of a chain, else next block index.

Pure stdlib, 3.6-safe, ASCII only.
"""
import struct

BLOCK_SIZE  = 512
BLOCK_COUNT = 256
IMAGE_SIZE  = BLOCK_SIZE * BLOCK_COUNT

FAT_FREE = 0xFFFC
FAT_LAST = 0xFFFA

TYPE_DATA = 0x33
TYPE_GAME = 0xCC
FILE_TYPES = {TYPE_DATA: "data", TYPE_GAME: "game"}

# Standard geometry, used when the root block leaves a field at zero.
DEFAULT_FAT_LOC = 254
DEFAULT_FAT_SIZE = 1
DEFAULT_DIR_LOC = 253
DEFAULT_DIR_SIZE = 13
DEFAULT_USER_BLOCKS = 200

DIR_ENTRY_SIZE = 32
DIR_ENTRIES_PER_BLOCK = BLOCK_SIZE // DIR_ENTRY_SIZE


class VmuError(Exception):
    """Malformed image -- bad size, bad geometry, or a corrupt FAT chain."""


def _u16(buf, off):
    return struct.unpack_from("<H", buf, off)[0]


class VmuImage(object):
    """A parsed 128KB VMU image. Construct, then call saves()."""

    def __init__(self, data):
        if len(data) != IMAGE_SIZE:
            raise VmuError("not a VMU image: %d bytes, expected %d" % (len(data), IMAGE_SIZE))
        self.data = data
        root = self.block(255)
        # Zeroed fields mean "uninitialised", not "block 0" -- fall back to standard.
        self.fat_loc     = _u16(root, 0x46) or DEFAULT_FAT_LOC
        self.fat_size    = _u16(root, 0x48) or DEFAULT_FAT_SIZE
        self.dir_loc     = _u16(root, 0x4A) or DEFAULT_DIR_LOC
        self.dir_size    = _u16(root, 0x4C) or DEFAULT_DIR_SIZE
        self.user_blocks = _u16(root, 0x50) or DEFAULT_USER_BLOCKS
        if not (0 < self.dir_loc < BLOCK_COUNT and 0 < self.dir_size <= self.dir_loc + 1):
            raise VmuError("bad directory geometry: loc=%d size=%d" % (self.dir_loc, self.dir_size))
        if not 0 < self.fat_loc < BLOCK_COUNT:
            raise VmuError("bad FAT location: %d" % self.fat_loc)
        if not 0 < self.user_blocks <= BLOCK_COUNT:
            raise VmuError("bad user block count: %d" % self.user_blocks)

    def block(self, n):
        if not 0 <= n < BLOCK_COUNT:
            raise VmuError("block %d out of range" % n)
        return self.data[n * BLOCK_SIZE:(n + 1) * BLOCK_SIZE]

    def fat_entry(self, i):
        return _u16(self.data, self.fat_loc * BLOCK_SIZE + i * 2)

    def chain(self, first):
        """Follow a FAT chain from `first`, returning its block numbers in file order."""
        out, cur = [], first
        while cur != FAT_LAST:
            if not 0 <= cur < BLOCK_COUNT:
                raise VmuError("FAT chain leaves the image at block %d" % cur)
            if cur in out:
                raise VmuError("FAT chain loops at block %d" % cur)
            out.append(cur)
            if len(out) > BLOCK_COUNT:
                raise VmuError("FAT chain longer than the image")
            cur = self.fat_entry(cur)
        return out

    def free_blocks(self):
        return [i for i in range(self.user_blocks) if self.fat_entry(i) == FAT_FREE]

    def _directory(self):
        """The directory blocks concatenated in entry order (they run high to low)."""
        out = []
        for i in range(self.dir_size):
            out.append(self.block(self.dir_loc - i))
        return b"".join(out)

    def saves(self):
        """Every real file on the card, in directory order.

        Each entry is a dict: name, type ('data'|'game'), first_block, blocks,
        timestamp (ISO string, or '' if the BCD is unreadable) and data (bytes).
        """
        directory = self._directory()
        out = []
        for i in range(self.dir_size * DIR_ENTRIES_PER_BLOCK):
            raw = directory[i * DIR_ENTRY_SIZE:(i + 1) * DIR_ENTRY_SIZE]
            if len(raw) < DIR_ENTRY_SIZE:
                break
            ftype = raw[0]
            if ftype not in FILE_TYPES:
                continue                        # 0x00 = empty slot; anything else, junk
            first  = _u16(raw, 2)
            blocks = _u16(raw, 24)
            name   = raw[4:16].decode("ascii", "replace").rstrip("\x00 ")
            chain  = self.chain(first)
            if len(chain) != blocks:
                raise VmuError("%s: directory says %d blocks, FAT chain has %d"
                               % (name, blocks, len(chain)))
            out.append({
                "name":        name,
                "type":        FILE_TYPES[ftype],
                "first_block": first,
                "blocks":      blocks,
                "timestamp":   _decode_bcd_timestamp(raw[16:24]),
                "data":        b"".join(self.block(b) for b in chain),
            })
        return out


def _decode_bcd_timestamp(raw):
    """Directory timestamps are BCD: century, year, month, day, hour, min, sec, weekday.

    The game writes this when it saves, so it is a real save time -- better evidence
    than a file mtime. Returns '' rather than raising: a card with one odd timestamp
    is still perfectly backable-up.
    """
    try:
        vals = []
        for b in raw[:7]:
            hi, lo = b >> 4, b & 0x0F
            if hi > 9 or lo > 9:
                return ""
            vals.append(hi * 10 + lo)
        century, year, month, day, hour, minute, second = vals
        if not (1 <= month <= 12 and 1 <= day <= 31 and hour < 24 and minute < 60 and second < 60):
            return ""
        return "%04d-%02d-%02dT%02d:%02d:%02dZ" % (century * 100 + year, month, day,
                                                   hour, minute, second)
    except Exception:
        return ""


def read_saves(image):
    """Convenience wrapper: raw image bytes -> list of save dicts."""
    return VmuImage(image).saves()
