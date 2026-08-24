#!/usr/bin/env python3
"""Unit tests for vmufs: prove we read a VMU's saves back EXACTLY.

This parser feeds a backup. If it mis-reads a card, the cloud copy is wrong in a way
nobody notices until a restore is attempted -- so the risk worth testing is silent
corruption, not crashes. Three things can cause it:

  (a) directory indexing. The directory runs HIGH to LOW (253, 252, 251...), so a
      naive ascending walk finds the first 16 files and then reads garbage. This
      card has 15 files, i.e. one slot short of exposing that bug in the wild.
  (b) FAT chain order. Real VMUs allocate DOWNWARD (199, 198, 197...), so a parser
      that assumes contiguous ascending blocks reassembles a save's halves swapped.
  (c) geometry. Real cards leave the root block's geometry fields zeroed, so the
      standard-layout fallback has to be right -- and must not fire when a card
      genuinely declares something else.

Images are synthesised here rather than committed as binary fixtures.

    python3 test_vmufs.py     # plain asserts, no pytest
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vmufs


def build_image(files, fat_loc=254, dir_loc=253, dir_size=13, user_blocks=200,
                declare_geometry=False):
    """Assemble a VMU image from (name, type_byte, [block payloads], ts_bytes) tuples.

    Blocks are handed out DOWNWARD from the top of the user area, the way a real card
    does it, so the tests exercise descending chains rather than a tidy 0,1,2 layout.
    """
    img = bytearray(b"\x00" * vmufs.IMAGE_SIZE)

    root = bytearray(b"\x00" * vmufs.BLOCK_SIZE)
    root[0:16] = b"\x55" * 16
    if declare_geometry:
        struct.pack_into("<H", root, 0x46, fat_loc)
        struct.pack_into("<H", root, 0x48, 1)
        struct.pack_into("<H", root, 0x4A, dir_loc)
        struct.pack_into("<H", root, 0x4C, dir_size)
        struct.pack_into("<H", root, 0x50, user_blocks)
    img[255 * vmufs.BLOCK_SIZE:256 * vmufs.BLOCK_SIZE] = root

    fat = bytearray()
    for i in range(256):
        fat += struct.pack("<H", vmufs.FAT_FREE if i < user_blocks else vmufs.FAT_LAST)
    img[fat_loc * vmufs.BLOCK_SIZE:(fat_loc + 1) * vmufs.BLOCK_SIZE] = fat

    def fat_set(i, v):
        struct.pack_into("<H", img, fat_loc * vmufs.BLOCK_SIZE + i * 2, v)

    next_free = user_blocks - 1
    for slot, (name, ftype, payloads, ts) in enumerate(files):
        blocks = []
        for payload in payloads:
            blocks.append(next_free)
            next_free -= 1
        for n, (b, payload) in enumerate(zip(blocks, payloads)):
            body = payload + b"\x00" * (vmufs.BLOCK_SIZE - len(payload))
            img[b * vmufs.BLOCK_SIZE:(b + 1) * vmufs.BLOCK_SIZE] = body
            fat_set(b, vmufs.FAT_LAST if n == len(blocks) - 1 else blocks[n + 1])
        entry = bytearray(b"\x00" * 32)
        entry[0] = ftype
        struct.pack_into("<H", entry, 2, blocks[0])
        entry[4:16] = name.encode("ascii").ljust(12, b" ")
        entry[16:24] = ts
        struct.pack_into("<H", entry, 24, len(blocks))
        off = (dir_loc - slot // 16) * vmufs.BLOCK_SIZE + (slot % 16) * 32
        img[off:off + 32] = entry
    return bytes(img)


TS = bytes(bytearray([0x20, 0x26, 0x05, 0x29, 0x22, 0x38, 0x44, 0x04]))  # 2026-05-29 22:38:44


def test_roundtrip():
    """A save's bytes come back exactly, across a multi-block descending chain."""
    a = b"RACER-BLOCK-A"
    b = b"RACER-BLOCK-B"
    img = build_image([("SW_EP1_RACER", vmufs.TYPE_DATA, [a, b], TS)])
    saves = vmufs.read_saves(img)
    assert len(saves) == 1, saves
    s = saves[0]
    assert s["name"] == "SW_EP1_RACER", s["name"]
    assert s["type"] == "data"
    assert s["blocks"] == 2
    assert len(s["data"]) == 2 * vmufs.BLOCK_SIZE
    # order matters: chain is 199 -> 198, so A must precede B
    assert s["data"].startswith(a), "first block wrong"
    assert s["data"][vmufs.BLOCK_SIZE:].startswith(b), "blocks reassembled out of order"
    assert s["timestamp"] == "2026-05-29T22:38:44Z", s["timestamp"]


def test_directory_runs_high_to_low():
    """Entry 16+ lives in the NEXT block DOWN. An ascending walk loses these."""
    files = [("FILE%08d" % i, vmufs.TYPE_DATA, [b"x%d" % i], TS) for i in range(20)]
    saves = vmufs.read_saves(build_image(files))
    assert len(saves) == 20, "found %d of 20 -- directory indexing is wrong" % len(saves)
    names = [s["name"] for s in saves]
    assert names == [f[0] for f in files], names
    # the ones past the first directory block are the whole point
    assert "FILE00000019" in names


def test_game_type_and_empty_slots_skipped():
    """0xCC is a game file; 0x00 slots are empty and must not become phantom saves."""
    img = build_image([("JETGRIND__VM", vmufs.TYPE_GAME, [b"g"], TS)])
    saves = vmufs.read_saves(img)
    assert len(saves) == 1, "empty directory slots leaked in as files"
    assert saves[0]["type"] == "game"


def test_geometry_fallback_and_explicit():
    """Real cards zero the root geometry; a card that declares it must still be honoured."""
    files = [("DORAEMON_000", vmufs.TYPE_DATA, [b"d"], TS)]
    zeroed = vmufs.read_saves(build_image(files, declare_geometry=False))
    declared = vmufs.read_saves(build_image(files, declare_geometry=True))
    assert zeroed[0]["data"] == declared[0]["data"]
    img = vmufs.VmuImage(build_image(files, declare_geometry=False))
    assert (img.fat_loc, img.dir_loc, img.dir_size, img.user_blocks) == (254, 253, 13, 200)


def test_free_block_accounting():
    """Free-block count must reflect what the FAT actually says."""
    img = vmufs.VmuImage(build_image([("A", vmufs.TYPE_DATA, [b"1", b"2", b"3"], TS)]))
    assert len(img.free_blocks()) == 197, len(img.free_blocks())


def test_rejects_bad_size():
    for bad in (b"", b"\x00" * 1024, b"\x00" * (vmufs.IMAGE_SIZE + 1)):
        try:
            vmufs.read_saves(bad)
        except vmufs.VmuError:
            continue
        raise AssertionError("accepted a %d-byte image" % len(bad))


def test_rejects_corrupt_chain():
    """A looping FAT chain must raise, not hang or return truncated data."""
    img = bytearray(build_image([("LOOPY", vmufs.TYPE_DATA, [b"a", b"b"], TS)]))
    struct.pack_into("<H", img, 254 * vmufs.BLOCK_SIZE + 198 * 2, 199)   # 199->198->199
    try:
        vmufs.read_saves(bytes(img))
    except vmufs.VmuError:
        return
    raise AssertionError("accepted a looping FAT chain")


def test_rejects_size_mismatch():
    """Directory block count disagreeing with the FAT chain means a damaged card."""
    img = bytearray(build_image([("SHORTY", vmufs.TYPE_DATA, [b"a", b"b"], TS)]))
    off = 253 * vmufs.BLOCK_SIZE + 24
    struct.pack_into("<H", img, off, 5)          # claim 5 blocks, chain holds 2
    try:
        vmufs.read_saves(bytes(img))
    except vmufs.VmuError:
        return
    raise AssertionError("accepted a directory/FAT size mismatch")


def test_unreadable_timestamp_is_empty_not_fatal():
    """DSCONFIG.CFG on the real card has non-BCD bytes here; it must still back up."""
    junk = bytes(bytearray([0xFF] * 8))
    saves = vmufs.read_saves(build_image([("DSCONFIG.CFG", vmufs.TYPE_DATA, [b"c"], junk)]))
    assert saves[0]["timestamp"] == "", saves[0]["timestamp"]
    assert saves[0]["data"], "a bad timestamp must not cost us the save data"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("  ok  %s" % t.__name__)
    print("\n%d tests passed" % len(tests))
