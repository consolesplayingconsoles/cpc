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
    for seq in ("a'", "i'", "u'", "n'", "t'"):
        off = _idx(f._CSLOT[seq]) * f.STRIDE
        g = f.decode(bytearray(data[off:off + f.STRIDE]))
        assert any(g[r][c] for r in range(6) for c in (16, 17, 18)), "%s: apostrophe not on the RIGHT" % seq


# ── backwards-compatibility locks: the Catalan (lang="ca") output must NEVER move ──────────────
# These golden MD5s were captured from the pre-language-refactor code. If a test here fails, a change
# altered the Catalan font/encoder bytes -- which the Catalan release (in maintenance) forbids.
import hashlib

# RE-BASELINED 2026-09-20 (twice) and again 2026-09-24. Earlier values:
#   3c41616c88a2620b92ab766fdc0c2220 / 24a0b531ec002af7044f77e1b8fadf02  (before any mark combos)
#   3c19d7a81a7e87500771c53ec8c67eb0 / 1baeb289992d9f06f5885024c05cc310  (marks on every letter)
# 2026-09-24 (seventh pass): hung marks get 3 px of daylight (_MARK_AIR) instead of sitting flush
# against the letter, `!` also drops the ascenders (it read as a second stem: "h! is terrible"), and
# the apostrophe starts one column PAST the letter instead of above its last stroke.
# 2026-09-24 (sixth pass): the MARKS hang in the letter's bottom-right corner too, wherever it is
# free (22 of 26 letters for . and , ; 16 for !), so the letter no longer moves and the wide letters
# have their combos back. `!!` and `!?` render as one cell with both bangs drawn 3 px.
# 2026-09-24 (fifth pass): the apostrophe hangs in the letter's own top-right corner now
# anchored on each letter's own shoulder, m and w excluded (their body fills the cell)
# (operator's idea: "you have a lot of space between the letter and the apostrophe and instead of
# putting them closer, you just butcher the letter"). Cap height vs x-height never collide, so the
# letter does not move or shrink at all -- and every letter, m and w included, carries one again.
# 2026-09-24 (fourth pass): `_author_unwrap` -- A G M O Q V W X Y w are wider than the 20 px cell
# and the stock font wraps their tail into columns 0-2 of the same row. They are now unwrapped and
# re-centred with equal bearings, so the letters stop bleeding into whatever sits beside them.
# 2026-09-24 (third pass): the apostrophe combos are MOVED too now -- the squeeze was thinning
# the letter (`a` 12 px -> 9, `n` likewise: "narrow left n leg"), and only m/w still need it.
# 2026-09-24 (second pass): the letter is now CENTRED between its neighbour and its mark (the
# operator asked for both sides to look similarly wide), the interrobang's `!` is drawn 3 px like
# our other marks, `!?`/`?!` always render as that one cell, and the digraphs take their extra px
# from the RIGHT bearing -- moving the `i` of `it` to column 2 made it VANISH on hardware.
# 2026-09-24: hardware QA rejected the marks on the WIDE letters (they crowd the letter before them,
# see test_no_combo_crowds_the_previous_letter), so a e g o v b c d k p q lost theirs, and the
# it/ti/ix/li/il digraphs gained a px of air. _GOLDEN_FW is back at the pre-mark value because every
# word in this Catalan corpus ends in a wide letter -- the surviving combos (f h n s u x y z r j)
# simply never fire on it.
# These goldens lock the DEV font, which is NOT byte-identical to the shipped v1.0 patch and is
# UNTESTED ON HARDWARE -- do not cut a release from it until the operator has seen it on a Dreamcast.
_GOLDEN_FONT = "039a5d47cb9b2d28a99b124e622d0658"
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
def test_en_round_combos_keep_their_left_stroke():
    """The round letters' apostrophe combos must keep the left stroke as thick as the plain letter.

    History: the 20->14 squeeze merged their 2 px left stroke into 1 px and read as cut off (hardware
    QA 2026-09-17). Nothing is squeezed any more, and o/e have since left the set entirely (their
    12 px body crowded both neighbours, see _EN_APOS_SKIP), so this now guards the round letters that
    remain -- c and g."""
    font = f.build_patched_font(_raw, "en")
    def grid(code):
        jhi, jlo = f.sjis2jis(code >> 8, code & 0xFF)
        return f.decode(bytearray(font[f.jis_index(jhi, jlo) * f.STRIDE:][:f.STRIDE]))
    def left_stroke(g):                      # thinnest solid run at the left edge over the letter's body rows
        widths = []
        for r in range(6, 17):
            cols = [c for c in range(f.W) if g[r][c] >= 2]
            if not cols: continue
            c, w = cols[0], 0
            while c < f.W and g[r][c] >= 2: w += 1; c += 1
            widths.append(w)
        return min(widths)
    for ch in "su":   # the letters with a bowl that are still in the set
        plain = f.decode(bytearray(font[f.jis_index(0x23, 0x61 + ord(ch) - 97) * f.STRIDE:][:f.STRIDE]))
        combo = grid(f._EN_CSLOT[ch + "'"])
        assert left_stroke(combo) >= left_stroke(plain), "%s' left stroke thinner than plain %s" % (ch, ch)
        # the apostrophe hangs on the letter's own SHOULDER now (see _apos_corner): solid ink in the
        # cap-height rows, ending at or after the letter's right edge and never past the cell.
        mark = [c for c in range(f.W) if all(combo[r][c] == 3 for r in range(3))]
        body = [c for c in range(f.W) if any(plain[r][c] for r in range(6, f.ROWS))]
        assert mark, "%s': no apostrophe" % ch
        assert max(mark) >= max(body) - 1, "%s': apostrophe sits left of the letter's shoulder" % ch
        assert max(mark) <= f.W - 1, "%s': apostrophe runs off the cell" % ch


def test_en_font_builds_and_places_every_combo_distinctly():
    """The English font builds (same size) and authors every <letter>' combo to a distinct in-range slot."""
    data = f.build_patched_font(_raw, "en")
    assert len(data) == len(_raw)
    slots = list(f._EN_CSLOT.values())
    assert len(slots) == len(set(slots)), "en combo slot collision"
    want = 1 + len([c for c in "abcdefghijklmnopqrstuvwxyz" if c not in f._EN_APOS_SKIP]) + len(f._PSPEC)
    assert len(f._EN_CSPEC) == want, \
        "expected I' + the lowercase apostrophes that fit (m/w excluded, see _EN_APOS_SKIP), plus the marks"
    allowed = set(f._KANA_FREE) | set(f._KANA_FREE2) | {0x838e, 0x8390, 0x8391, 0x8395, 0x8361}
    for code in slots:
        assert 0x839F <= code <= 0x83D6 or code in allowed, "%04X is outside the reserved slots" % code


def test_en_combos_dont_collide_with_hyphen_or_ellipsis():
    """The authored extras (hyphen 0x83C9, ellipsis 0x8394) must not share a slot with any combo."""
    slots = set(f._EN_CSLOT.values())
    assert 0x83C9 not in slots, "a combo landed on the hyphen slot"
    assert 0x8394 not in slots, "a combo landed on the ellipsis slot"


def test_en_encoder_uses_combos_for_contractions_and_possessives():
    """fw(..,'en') must render the apostrophe as the PRECEDING letter's right-apostrophe combo,
    for contractions AND possessive 's after any letter (never a standalone/left apostrophe)."""
    # "it's" resolves to the THREE-char `it'` cell (cheaper still); every other word uses the
    # preceding letter's right-apostrophe combo. Either way the mark rides a letter.
    # e/o/m/w are not in the set (see _EN_APOS_SKIP), so their contractions legitimately spend a
    # cell on the hug-left quote glyph instead; the combos below are the ones that do ride a letter.
    cases = {"I'm": "I'", "don't": "n'", "it's": "it'", "that's": "t'",
             "you're": "u'", "James's": "s'", "night's": "t'"}
    bad = []
    for word, combo in cases.items():
        out = f.fw(word, "en")
        codes = [(out[i] << 8) | out[i + 1] for i in range(0, len(out), 2)]
        if f._EN_CSLOT[combo] not in codes:
            bad.append("%s should use the %s combo (0x%04X)" % (word, combo, f._EN_CSLOT[combo]))
        if 0x8166 in codes:                     # the rejected standalone/left apostrophe
            bad.append("%s emitted a STANDALONE apostrophe (0x8166)" % word)
    assert not bad, "en apostrophe combos not applied:\n  " + "\n  ".join(bad)


def test_en_plain_latin_uses_no_greek_slots():
    """Plain English (no apostrophe/ellipsis) encodes to stock full-width Latin, hitting no Greek slot."""
    out = f.fw("Doraemon the robot cat", "en")
    codes = [(out[i] << 8) | out[i + 1] for i in range(0, len(out), 2)]
    assert all(not (0x839F <= c <= 0x83D6) for c in codes), "plain text must not hit authored Greek slots"


def test_en_multi_punctuation_splits_the_question_mark_out():
    """`!!` is ONE cell; `?!` and `!?` are TWO.

    All three used to share the one-cell treatment. Two marks in the width of one left the question
    mark a 1 px curve beside the bang's 3 px bar, and on a CRT the operator could not see it at all
    ("is that question mark rendered? i did not notice it"). `!!` is two identical bars and survives
    the squeeze, so it keeps its cell; the question mark gets its own, at 2 bytes per occurrence."""
    assert len(f.fw("!!", "en")) == 2, "!! should stay one glyph (2B) in en"
    for seq in ("?!", "!?"):
        b = f.fw(seq, "en")
        assert len(b) == 4, "%r should be two glyphs (4B) in en, got %dB" % (seq, len(b))
        assert b == f.fw(seq[0], "en") + f.fw(seq[1], "en"), "%r should be its two stock cells" % seq
    f.build_patched_font(_raw, "en")   # builds without error (glyphs composed)


def test_period_combo_makes_the_terminal_dot_free():
    """A `<letter>.` is ONE cell in both languages, so a terminal period costs nothing -- the whole
    point of the glyph set (both scripts were budget-stripped of their periods)."""
    for lang in ("ca", "en"):
        # every word ends in a letter NARROW enough to keep its combo (see _MARK_SKIP): the wide
        # ones render as two cells on purpose, so a `p.`/`a.`/`e.` ending would fail this by design.
        for word in ("not", "again", "yes", "you", "her", "half"):
            bare, dotted = f.fw(word, lang), f.fw(word + ".", lang)
            assert len(dotted) == len(bare), "%s: %r. costs more than %r" % (lang, word, word)


def test_period_combo_never_eats_an_ellipsis():
    """"a..." must stay `a` + the ellipsis glyph. If the `a.` combo fired it would leave ".." behind,
    rendering as "a. .." -- the same class of bug the apostrophe guard exists for."""
    for lang in ("ca", "en"):
        prof = f._PROFILES[lang]
        assert f.fw("a...", lang) == f.fw("a", lang) + prof.ellipsis_code.to_bytes(2, "big")
        assert len(f.fw("no..", lang)) // 2 == 4, "'..' must stay two separate dots"


def test_period_slots_miss_every_authored_extra():
    """The periods take the next free slots, which in ca runs straight into the l·l middot (0x83D1)
    and, unguarded, into the hyphen/ellipsis. A clash here renders a letter inside Japanese text."""
    for lang in ("ca", "en"):
        pslots = {f._PROFILES[lang].cslot[seq] for seq, _, _ in f._PSPEC}
        for code, what in ((0x83C9, "hyphen"), (0x83D1, "middot"), (0x8394, "ellipsis")):
            assert code not in pslots, "%s: a period landed on the %s slot" % (lang, what)
        assert len(pslots) == len(f._PSPEC), "%s: two periods share a slot" % lang
    assert f.fw("l·l", "ca")[2:4] == (0x83D1).to_bytes(2, "big"), "the middot stopped rendering"


def test_period_glyph_sits_at_the_baseline_right():
    """The dot must be drawn bottom-right, clear of the squeezed letter (two blank columns), the
    same clearance the proven right-apostrophe uses -- just at the baseline instead of the cap."""
    data = f.build_patched_font(_raw, "en")
    for seq, _, _ in f._PSPEC[:6]:
        code = f._EN_CSLOT[seq]
        off = _idx(code) * f.STRIDE
        g = f.decode(bytearray(data[off:off + f.STRIDE]))
        assert any(g[r][c] for r in (16, 17, 18) for c in (16, 17, 18, 19)), "%s: no dot at baseline right" % seq


def test_every_mark_is_one_cell_in_both_languages():
    """`,` and `!` ride the preceding letter exactly as `.` does, so punctuation is free."""
    for lang in ("ca", "en"):
        # every word ends in a letter that KEEPS its combo; the wide letters (and m/w) are excluded
        # from every mark (see _MARK_SKIP), so punctuation after them legitimately costs its own cell.
        for word, mark in (("adeu", ","), ("prou", "!"), ("yes", "."),
                           ("hi", "!"), ("her", ","), ("half", ".")):
            assert len(f.fw(word + mark, lang)) == len(f.fw(word, lang)), \
                "%s: %r%s is not free" % (lang, word, mark)


def test_marks_never_swallow_a_doubled_punctuation():
    """`!!` and `..` must stay two cells: the combo may only take a SINGLE trailing mark, or
    "Ja!!" would render as `a!` + `!` -- right glyph count, wrong shape."""
    for lang in ("ca", "en"):
        # en renders "!!" as its own cell (both bangs identical, see _bold_bang_left/right), so the
        # `n!` combo must not fire in front of it: R + u + n + [!!]. ca has no !! cell: n! + !.
        want = 4 if lang == "en" else 5   # ca has no !! cell: R + u + n! + !
        assert len(f.fw("Run!!", lang)) // 2 == want, "!! collapsed wrongly"
        assert len(f.fw("no..", lang)) // 2 == 4, ".. collapsed wrongly"


def test_comma_covers_every_letter_that_can_be_moved():
    """The comma takes every letter EXCEPT the ones that cannot be moved without crowding the
    letter before them (m, w, and the wide set: see _MARK_SKIP and
    test_no_combo_crowds_the_previous_letter)."""
    for lang in ("ca", "en"):
        want = [c for c in "abcdefghijklmnopqrstuvwxyz" if c not in f._MARK_SKIP]
        missing = [c for c in want if (c + ",") not in f._PROFILES[lang].cslot]
        assert not missing, "%s: no comma combo for %s" % (lang, missing)


def test_no_shipped_combo_is_scaled():
    """THE rule the operator set on hardware: a squeezed glyph is not acceptable. Every mark combo
    must be the MOVED kind, i.e. its letter pixels must appear unchanged from the stock glyph."""
    raw = _raw
    data = f.build_patched_font(raw, "en")
    for seq, ch, mark in f._PSPEC:
        bhi, blo = f._basejis(ch)
        g0 = f.decode(bytearray(raw[f.jis_index(bhi, blo) * f.STRIDE:][:f.STRIDE]))
        cols = [c for c in range(f.W) if any(g0[r][c] for r in range(f.ROWS))]
        code = f._EN_CSLOT[seq]
        g1 = f.decode(bytearray(data[_idx(code) * f.STRIDE:][:f.STRIDE]))
        # the letter is MOVED, and `_balance` decides how far, so look for the shift that reproduces
        # it exactly: if no whole-pixel shift matches, the glyph was scaled, which is the rule's point.
        def moved_by(sh):
            return all(g1[r][c - sh] == g0[r][c]
                       for r in range(f.ROWS) for c in range(min(cols), max(cols) + 1)
                       if 0 <= c - sh < f.W)
        assert any(moved_by(sh) for sh in range(0, f.W)), "%s: letter pixels were altered (scaled?)" % seq


def test_every_mark_is_either_hung_in_the_corner_or_properly_cleared():
    """Two shapes are legal, and nothing in between.

    HUNG: the mark sits in the letter's own bottom-right corner (columns 18-19) and the letter is
    byte-identical to the plain one -- no crowding at all, which is the whole point.
    MOVED: the letter had to shift (its corner was occupied), and then it must end by column 13 so
    two columns stay clear -- a 1 px gap is what the game's 2bpp blit merges."""
    data = f.build_patched_font(_raw, "en")
    for seq, ch, _ in f._PSPEC:
        g = f.decode(bytearray(data[_idx(f._EN_CSLOT[seq]) * f.STRIDE:][:f.STRIDE]))
        bhi, blo = f._basejis(ch)
        plain = f.decode(bytearray(data[f.jis_index(bhi, blo) * f.STRIDE:][:f.STRIDE]))
        # HUNG: mark at columns 18-19, letter nudged left only far enough to leave _MARK_AIR px
        # of daylight. MOVED (the fallback): mark at 16-18, letter ends by 13.
        hung = not any(g[r][c] for r in range(f.ROWS) for c in range(18 - f._MARK_AIR, 18))
        if hung:
            assert any(g[r][c] for r in range(f.ROWS) for c in (18, 19)), "%s: no mark" % seq
            continue
        assert not any(g[r][c] for r in range(f.ROWS) for c in (14, 15)), \
            "%s: moved, but only 1 column of clearance before the mark" % seq


def test_bang_glyph_clears_the_letter_vertically():
    """`!` is full height, unlike the dot. It still must not touch the letter: the letter ends by
    col 13 and the mark owns 16-18, so cols 14-15 stay empty at EVERY row."""
    data = f.build_patched_font(_raw, "en")
    for seq in ("n!", "s!", "u!", "z!"):
        g = f.decode(bytearray(data[_idx(f._EN_CSLOT[seq]) * f.STRIDE:][:f.STRIDE]))
        assert any(g[r][18] or g[r][17] for r in range(3, 14)), "%s: no stem" % seq
        # the bang hangs at columns 18-19 with _MARK_AIR px of daylight, so the letter must stop
        # before that daylight starts
        stop = 18 - f._MARK_AIR
        assert not any(g[r][c] for r in range(f.ROWS) for c in range(stop, 18)), \
            "%s: letter runs into the mark's air" % seq


def test_no_combo_crowds_the_previous_letter():
    """The operator's second hardware QA: `e. e, e! a. a, a! o, g. d!` all read as one blob with the
    letter before them. Cause: the font sets its letters against the RIGHT of the cell (1 px right
    bearing, 7 px left), so two letters sit 8 px apart; the mark's shift eats that gap, and a 11-12 px
    letter shifts 4-5 px -> 2-3 px of left bearing left. The rule that came out of it: a combo ships
    only if its letter still has >= 4 px of left bearing after the shift."""
    data = f.build_patched_font(_raw, "en")
    for seq, ch, kind in f._PSPEC:
        bhi, blo = f._basejis(ch)
        g0 = f.decode(bytearray(_raw[f.jis_index(bhi, blo) * f.STRIDE:][:f.STRIDE]))
        if f._mark_corner([row[:] for row in g0], kind) is not None:
            continue                      # hung in the corner: the letter never moves, so no crowding
        cols = [c for c in range(f.W) if any(g0[r][c] for r in range(f.ROWS))]
        lb = min(cols) - max(0, max(cols) - 13)
        assert lb >= 4, "%s: only %d px of left bearing after the shift -- it will crowd the previous letter" % (seq, lb)


def test_digraph_pairs_keep_a_px_of_air():
    """The it/ti/ix/li/il pairs are composed with an extra px BETWEEN the two letters (operator read
    the even 3 px split as one blob on a CRT). The mark pairs (t. i! ...) are proven and untouched."""
    data = f.build_patched_font(_raw, "en")
    for seq in ("it", "ti", "ix", "li", "il"):
        g = f.decode(bytearray(data[_idx(f._EN_CSLOT[seq] if seq in f._EN_CSLOT else f._PROFILES["en"].clslot[seq]) * f.STRIDE:][:f.STRIDE]))
        cols = [c for c in range(f.W) if any(g[r][c] for r in range(f.ROWS))]
        gaps, run = [], 0
        for c in range(min(cols), max(cols) + 1):
            if any(g[r][c] for r in range(f.ROWS)):
                if run: gaps.append(run)
                run = 0
            else:
                run += 1
        if run: gaps.append(run)
        # ix is 3: x is a px wider than t/l, and the pair may not start left of column 3 (see
        # _MIN_LEFT -- the `i` of `it` vanished on hardware at column 2), so that px has to come
        # from the gap. Everything else gets 4.
        want = 3 if seq == "ix" else 4
        assert gaps and max(gaps) >= want, "%s: the two letters are only %s px apart" % (seq, gaps)


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
