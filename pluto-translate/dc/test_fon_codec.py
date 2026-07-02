#!/usr/bin/env python3
"""Unit tests for fon_codec: prove glyph placement/indexing is self-consistent.

The bug we hunted: an authored glyph rendering as some OTHER glyph. In this codec that can only
happen if (a) two authored glyphs are written to the SAME font offset (one clobbers the other), or
(b) fw() emits a code whose glyph is not the one build_patched_font placed there, or (c) jis_index
doesn't actually address the record it claims to (grid not dense). Each test isolates one of those.

Separately: this game renders a RIGHT-edge apostrophe (M'/S') but NOT a left one, so enclitics are
encoded as the preceding vowel carrying a right-apostrophe (a'/e'...) -- tested here too.

    python3 test_fon_codec.py     # plain asserts, no pytest (runs on the old box Python too)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fon_codec as f

ORIG = os.path.join(os.path.dirname(__file__), "..", "..", "sandbox", "boku-doraemon-japan", "original", "S18RM04.FON")
_raw = open(ORIG, "rb").read()


def _idx(code):
    jhi, jlo = f.sjis2jis(code >> 8, code & 0xFF)
    return f.jis_index(jhi, jlo)


def _authored_codes():
    """Every SJIS code build_patched_font writes a glyph to, with a label."""
    out = []
    for ch, (_, _, _, _, shi, slo) in f.ACCENT_SPEC.items():
        out.append(("accent " + ch, (shi << 8) | slo))
    out.append(("hyphen", 0x83C9))
    out.append(("ellipsis", 0x8394))
    interrobang = f._OSLOT.get("?!")
    for seq in f._CSLOT:
        if f._CSLOT[seq] == interrobang:      # ?! / !? are intentional aliases of ONE glyph
            continue
        out.append(("cslot " + seq, f._CSLOT[seq]))
    for name in f._OSLOT:
        out.append(("oslot " + name, f._OSLOT[name]))
    for seq in f._CLSLOT:
        out.append(("clslot " + seq, f._CLSLOT[seq]))
    return out


def test_sjis2jis_matches_reference():
    """sjis2jis must equal Python's own shift_jis->JIS for every real double-byte code."""
    bad = []
    for hi in range(0x81, 0xA0):
        for lo in range(0x40, 0xFD):
            if lo == 0x7F:
                continue
            code = (hi << 8) | lo
            try:
                ch = bytes([hi, lo]).decode("shift_jis")
                raw = ch.encode("iso-2022-jp")
            except Exception:
                continue
            body = raw.replace(b"\x1b$B", b"").replace(b"\x1b(B", b"")
            if len(body) != 2:
                continue
            if f.sjis2jis(hi, lo) != (body[0], body[1]):
                bad.append(hex(code))
    assert not bad, "sjis2jis disagrees with reference at: %s" % bad[:20]


def test_grid_is_dense():
    """jis_index must address the record whose stored header equals that code (grid is dense)."""
    bad = []
    for hi in range(0x81, 0xA0):
        for lo in range(0x40, 0xFD):
            if lo == 0x7F:
                continue
            try:
                bytes([hi, lo]).decode("shift_jis")
            except Exception:
                continue
            jhi, jlo = f.sjis2jis(hi, lo)
            off = f.jis_index(jhi, jlo) * f.STRIDE
            if off + 2 > len(_raw):
                continue
            rec = _raw[off:off + f.STRIDE]
            if (rec[1], rec[0]) != (jhi, jlo):
                bad.append((hex((hi << 8) | lo), (rec[1], rec[0]), (jhi, jlo)))
    assert not bad, "grid not dense (header != jis_index) at: %s" % bad[:20]


def test_encode_decode_roundtrip():
    """decode then encode must reproduce the original bitmap bytes exactly."""
    for code in (0x8281, 0x83A9, 0x8394, 0x83C2, 0x826C):
        off = _idx(code) * f.STRIDE
        bmp = _raw[off + f.BMP: off + f.BMP + f.ROWS * f.BPR]
        assert f.encode(f.decode(bytearray(_raw[off:off + f.STRIDE]))) == bmp, hex(code)


def test_no_two_glyphs_share_an_offset():
    """THE big one: no two authored glyphs may land on the same font record."""
    seen = {}
    dupes = []
    for label, code in _authored_codes():
        off = _idx(code)
        if off in seen:
            dupes.append("0x%04X (%s) collides with 0x%04X (%s) at record %d"
                         % (code, label, seen[off][1], seen[off][0], off))
        else:
            seen[off] = (label, code)
    assert not dupes, "GLYPH OFFSET COLLISIONS:\n  " + "\n  ".join(dupes)


def test_authored_codes_are_distinct():
    """Every authored SJIS code is unique (no code assigned to two glyphs)."""
    codes = {}
    dupes = []
    for label, code in _authored_codes():
        if code in codes:
            dupes.append("0x%04X used by both '%s' and '%s'" % (code, codes[code], label))
        codes[code] = label
    assert not dupes, "DUPLICATE CODES:\n  " + "\n  ".join(dupes)


def test_fw_placement_agrees():
    """For each sequence fw can emit as one custom glyph, the code it emits must be the code
    build_patched_font wrote that glyph to (i.e. fw and the builder use the same slot)."""
    data = f.build_patched_font(_raw)
    bad = []
    for seq, code in list(f._CSLOT.items()) + list(f._CLSLOT.items()):
        out = f.fw(seq)
        emitted = [(out[i] << 8) | out[i + 1] for i in range(0, len(out), 2)]
        if emitted != [code]:
            bad.append("fw(%r) -> %s but slot is 0x%04X" % (seq, [hex(c) for c in emitted], code))
    assert not bad, "fw/placement mismatch:\n  " + "\n  ".join(bad)


def test_enclitic_via_vowel_right_apostrophe():
    """Enclitics render through the PRECEDING vowel carrying a right-apostrophe (a'/e'...), because
    this game renders a right-edge apostrophe but not a left one. Verify fw puts the vowel+apostrophe
    combo just before the enclitic consonant, and that combo glyph has its mark on the RIGHT."""
    data = f.build_patched_font(_raw)
    out = f.fw("Canvia't")
    codes = [(out[i] << 8) | out[i + 1] for i in range(0, len(out), 2)]
    assert f._CSLOT["a'"] in codes, "fw did not use the a' combo for canvia't: %s" % [hex(c) for c in codes]
    assert codes[-1] == 0x8294, "the enclitic letter 't' must follow the a' combo"
    for seq in ("a'", "e'", "i'", "o'", "u'"):
        off = _idx(f._CSLOT[seq]) * f.STRIDE
        g = f.decode(bytearray(data[off:off + f.STRIDE]))
        assert any(g[r][c] for r in range(6) for c in (16, 17, 18)), "%s: apostrophe not on the RIGHT" % seq


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fails = 0
    for t in tests:
        try:
            t()
            print("PASS  %s" % t.__name__)
        except AssertionError as e:
            fails += 1
            print("FAIL  %s\n      %s" % (t.__name__, e))
    print("\n%d passed, %d failed" % (len(tests) - fails, fails))
    return fails


if __name__ == "__main__":
    sys.exit(1 if _run() else 0)
