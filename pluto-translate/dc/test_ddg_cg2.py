#!/usr/bin/env python3
"""Unit tests for Densha de Go! 2's CG2.ROM tile codec (games/Densha de Go 2 Kousoku-hen/ddg_assets.py).

Self-contained: synthetic tiles plus one real tile's bytes, no disc needed.

    python3 test_ddg_cg2.py     # plain asserts, no pytest
"""
import os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "games", "Densha de Go 2 Kousoku-hen"))
import ddg_assets as A

# OBJdejic01's fifth tile as stored on the disc: type 2 (LZ). Row 0 is sixteen 1s, row 1 ten 4s then six 1s.
REAL = bytes.fromhex("0280010e00800408000f18050680020600070f803103000e0f010d01020a0f020e090f033b0313090f"
                     "0531280f06700c0f0a7f055d0b0f037d0c0f0cbf")


def test_type2_is_lz_not_runs():
    """The control below 0x80 copies from (next byte + 1) back: `0f 18` repeats the row above plus one."""
    px = A.cg2_decode(REAL[0], REAL[1:])
    assert len(px) == 256
    assert px[:16] == [1] * 16, px[:16]
    assert px[16:32] == [4] * 10 + [1] * 6, px[16:32]
    assert px[32:48] == [1] * 9 + [4] + [1] * 6, px[32:48]


def test_type1_is_runs():
    assert A.cg2_decode(1, bytes([0x7F, 0, 0x7F, 0])) == [0] * 256
    assert A.cg2_decode(1, bytes([0x81, 3, 5, 0x7F, 9, 0x7D, 9])) == [3, 5] + [9] * 254


def test_encode_round_trips_and_does_not_lose_to_the_original():
    rnd = random.Random(7)
    for _ in range(40):
        px = []
        while len(px) < 256:                              # text-like: runs, repeats, a few literals
            px += [rnd.choice([0, 0, 0, 7, 77, 92, rnd.randrange(256)])] * rnd.randint(1, 20)
        px = px[:256]
        e = A.cg2_encode(px)
        assert A.cg2_decode(e[0], e[1:]) == px
    e = A.cg2_encode(A.cg2_decode(REAL[0], REAL[1:]))
    assert len(e) <= len(REAL), (len(e), len(REAL))


def test_build_reads_back():
    tiles = [(1, bytes([0x7F, 0, 0x7F, 0])), (REAL[0], REAL[1:])]
    assert A.cg2_tiles(A.cg2_build(tiles)) == tiles


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fails = 0
    for t in tests:
        try:
            t(); print("PASS  %s" % t.__name__)
        except AssertionError as e:
            fails += 1; print("FAIL  %s\n      %s" % (t.__name__, e))
    print("\n%d passed, %d failed" % (len(tests) - fails, fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(_run())
