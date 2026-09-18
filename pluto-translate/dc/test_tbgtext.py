#!/usr/bin/env python3
"""Unit tests for the tbgtext parser/packer: Tokyo Bus Guide `*_TEXT.DAT`.

Builds the container in memory (no disc needed), then checks the two things the
packer promises: an untranslated repack is byte-identical, and a longer English line
relocates the strings while every pointer still finds its own text.

    python3 test_tbgtext.py     # plain asserts, no pytest
"""
import os, struct, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from parsers import tbgtext as parser
from packers import tbgtext as packer

TERM = 0x7fffffff
FW = lambda s: "".join(chr(ord(c) + 0xfee0) if "!" <= c <= "~" else
                      ("　" if c == " " else c) for c in s).encode("cp932")
ENC = lambda s: s.encode("cp932")


def build(lines):
    """A one-scene file: scene table -> pairs -> strings, as the game stores them."""
    scenes, pairs = struct.pack("<II", 8, 0), b""
    strings, offsets = b"", []
    base = len(scenes) + 8 * (len(lines) + 1)
    for text in lines:
        offsets.append(base + len(strings))
        strings += text.encode("cp932") + b"\0"
        while len(strings) % 4:
            strings += b"\0"
    end = base + len(strings)                      # the scene's empty end marker
    strings += b"\0\0\0\0"
    for i, off in enumerate(offsets):
        pairs += struct.pack("<II", off, 0x100 + i)
    pairs += struct.pack("<II", end, TERM)
    return scenes + pairs + strings


def test_parse_finds_every_line_but_not_the_end_marker():
    data = build(["あついわね", "そうね<E>まったく"])
    blocks = parser.parse(data)
    assert len(blocks) == 2, blocks
    assert [bytes.fromhex(b["hex"]).decode("cp932") for b in blocks] == ["あついわね", "そうね<E>まったく"]


def test_repack_without_translations_is_byte_identical():
    data = build(["あついわね", "そうね<E>まったく"])
    assert packer.pack(data, [], ENC) == data


def test_longer_english_relocates_the_strings_and_repoints_the_pairs():
    data = build(["あついわね", "そうね<E>まったく"])
    blocks = parser.parse(data)
    out = packer.pack(data, [{"offset": blocks[0]["offset"],
                              "ca": "It never stops being hot this year"}], FW, box=22)
    after = parser.parse(out)
    assert len(out) > len(data), "the file should grow"
    assert len(after) == 2, after
    first = bytes.fromhex(after[0]["hex"]).decode("cp932")
    assert first.startswith("Ｉｔ"), first
    assert "<E>" in first, "long lines are wrapped with the game's break tag"
    assert bytes.fromhex(after[1]["hex"]).decode("cp932") == "そうね<E>まったく", "the other line moved intact"


def test_a_second_pointer_field_is_treated_as_text_when_it_points_into_the_strings():
    """SYSTEM/S_TEXT.DAT stores a second line there instead of a voice id."""
    def pad(text):
        raw = text.encode("cp932") + b"\0"
        return raw + b"\0" * (-len(raw) % 4)      # strings are 4-aligned

    scenes = struct.pack("<II", 8, 0)
    base = len(scenes) + 8
    a, b = pad("ふわーあ"), pad("････")
    data = scenes + struct.pack("<II", base, base + len(a)) + a + b
    blocks = parser.parse(data)
    assert len(blocks) == 2, blocks
    assert packer.pack(data, [], ENC) == data


if __name__ == "__main__":
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS ", name)
                passed += 1
            except AssertionError as exc:
                print("FAIL ", name, exc)
                failed += 1
    print("\n%d passed, %d failed" % (passed, failed))
    sys.exit(1 if failed else 0)
