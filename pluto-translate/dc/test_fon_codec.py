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


# ── backwards-compatibility locks: the Catalan (lang="ca") output must NEVER move ──────────────
# These golden MD5s were captured from the pre-language-refactor code. If a test here fails, a change
# altered the Catalan font/encoder bytes -- which the Catalan release (in maintenance) forbids.
import hashlib

_GOLDEN_FONT = "3c41616c88a2620b92ab766fdc0c2220"
_GOLDEN_FW = "24a0b531ec002af7044f77e1b8fadf02"
_FW_CORPUS = ["Doraemon", "Pa de la memòria", "Canvia't", "col·lecció", "Ves-te'n", "l'altre",
              "d'un", "Sí", "No", "què vols?", "tres...", "100%", "Gegant", "Això",
              "Nobita, l'amic", "de l'illa", "el tifó", "mig"]


def test_ca_font_is_byte_identical_golden():
    """The Catalan patched font must build byte-for-byte identical to the golden (default AND lang='ca')."""
    assert hashlib.md5(f.build_patched_font(_raw)).hexdigest() == _GOLDEN_FONT, "default (ca) font drifted"
    assert hashlib.md5(f.build_patched_font(_raw, "ca")).hexdigest() == _GOLDEN_FONT, "lang='ca' font drifted"


def test_ca_encoder_is_byte_identical_golden():
    """fw over a representative Catalan corpus (accents/contractions/digraphs/punct/ellipsis) must match."""
    h = hashlib.md5()
    for s in _FW_CORPUS:
        h.update(s.encode("utf-8") + b"\x00" + f.fw(s))
    assert h.hexdigest() == _GOLDEN_FW, "fw (ca) output drifted"


def test_default_lang_equals_explicit_ca():
    """The default argument must BE Catalan -- no caller that omits lang changes behaviour."""
    assert f.build_patched_font(_raw) == f.build_patched_font(_raw, "ca")
    for s in _FW_CORPUS:
        assert f.fw(s) == f.fw(s, "ca"), s


def test_unknown_lang_raises():
    """An unregistered language must fail loudly (a clean plug-in point for English), not silently ca."""
    try:
        f.build_patched_font(_raw, "xx"); assert False, "build_patched_font accepted unknown lang"
    except ValueError:
        pass
    try:
        f.fw("hi", "xx"); assert False, "fw accepted unknown lang"
    except ValueError:
        pass


# ── English profile (en): alphabet-wide right-apostrophe combos, no accents/digraphs ────────────
def test_en_font_builds_and_places_every_combo_distinctly():
    """The English font builds (same size) and authors every <letter>' combo to a distinct in-range slot."""
    data = f.build_patched_font(_raw, "en")
    assert len(data) == len(_raw)
    slots = list(f._EN_CSLOT.values())
    assert len(slots) == len(set(slots)), "en combo slot collision"
    assert len(f._EN_CSPEC) == 27, "expected 26 lowercase + I' = 27 combos"
    for code in slots:
        assert 0x839F <= code <= 0x83D6 or code in (0x838e, 0x8390, 0x8391, 0x8395, 0x8361)


def test_en_combos_dont_collide_with_hyphen_or_ellipsis():
    """The authored extras (hyphen 0x83C9, ellipsis 0x8394) must not share a slot with any combo."""
    slots = set(f._EN_CSLOT.values())
    assert 0x83C9 not in slots, "a combo landed on the hyphen slot"
    assert 0x8394 not in slots, "a combo landed on the ellipsis slot"


def test_en_encoder_uses_combos_for_contractions_and_possessives():
    """fw(..,'en') must render the apostrophe as the PRECEDING letter's right-apostrophe combo,
    for contractions AND possessive 's after any letter (never a standalone/left apostrophe)."""
    cases = {"I'm": "I'", "don't": "n'", "it's": "t'", "he's": "e'",
             "you're": "u'", "dog's": "g'", "o'clock": "o'", "James's": "s'"}
    bad = []
    for word, combo in cases.items():
        out = f.fw(word, "en")
        codes = [(out[i] << 8) | out[i + 1] for i in range(0, len(out), 2)]
        if f._EN_CSLOT[combo] not in codes:
            bad.append("%s should use the %s combo (0x%04X)" % (word, combo, f._EN_CSLOT[combo]))
    assert not bad, "en apostrophe combos not applied:\n  " + "\n  ".join(bad)


def test_en_plain_latin_uses_no_greek_slots():
    """Plain English (no apostrophe/ellipsis) encodes to stock full-width Latin, hitting no Greek slot."""
    out = f.fw("Doraemon the robot cat", "en")
    codes = [(out[i] << 8) | out[i + 1] for i in range(0, len(out), 2)]
    assert all(not (0x839F <= c <= 0x83D6) for c in codes), "plain text must not hit authored Greek slots"


def test_en_multi_punctuation_is_one_cell():
    """English !! ?! !? must each encode to ONE glyph (2B), authored to distinct slots."""
    for seq in ("?!", "!?", "!!"):
        b = f.fw(seq, "en")
        assert len(b) == 2, "%r should be one glyph (2B) in en, got %dB" % (seq, len(b))
    slots = [f._EN_CSLOT[s] for s in ("?!", "!?", "!!")]
    assert len(set(slots)) == 3, "en punctuation combos must not share a slot"
    f.build_patched_font(_raw, "en")   # builds without error (glyphs composed)


def test_en_does_not_perturb_ca():
    """Registering English must not change Catalan: the ca font is STILL byte-identical to the golden."""
    assert hashlib.md5(f.build_patched_font(_raw, "ca")).hexdigest() == _GOLDEN_FONT


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
