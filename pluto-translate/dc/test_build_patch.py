#!/usr/bin/env python3
"""Unit tests for build_patch's LANGUAGE wiring.

The build must hand the packers an encoder bound to the state's `lang`, and Catalan (lang='ca',
default, or missing) must stay byte-for-byte the original fon_codec.fw so the maintenance build is
unchanged. A new language must actually change the encoder (not silently fall back to Catalan).

    python3 test_build_patch.py     # plain asserts, no pytest
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # pluto-translate
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))                     # dc
import fon_codec
import build_patch as bp

_CORPUS = ["Doraemon", "Pa de la memòria", "Canvia't", "col·lecció", "Ves-te'n", "tres...",
           "Sí", "què vols?", "l'illa", "100%"]


def test_lang_defaults_to_ca():
    """Missing/empty lang must resolve to Catalan -- an old state without `lang` still builds ca."""
    assert bp._lang({}) == "ca"
    assert bp._lang({"lang": None}) == "ca"
    assert bp._lang({"lang": ""}) == "ca"
    assert bp._lang({"lang": "  "}) == "ca"
    assert bp._lang({"lang": "ca"}) == "ca"
    assert bp._lang({"lang": "en"}) == "en"


def test_ca_encoder_is_byte_identical_to_default_fw():
    """The encoder the build binds for Catalan must equal fon_codec.fw exactly (maintenance lock)."""
    enc = bp._encoder("ca")
    for s in _CORPUS:
        assert enc(s) == fon_codec.fw(s) == fon_codec.fw(s, "ca"), s


def test_encoder_follows_the_language():
    """A non-Catalan encoder must actually use that language -- not silently behave like Catalan.
    English has no profile yet, so its encoder raises; that difference is the proof of binding."""
    enc = bp._encoder("en")
    try:
        enc("hi")
        assert False, "en encoder should raise until the en profile exists (proves it's not ca)"
    except ValueError:
        pass


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fails = 0
    for t in tests:
        try:
            t(); print("PASS  %s" % t.__name__)
        except AssertionError as e:
            fails += 1; print("FAIL  %s\n      %s" % (t.__name__, e))
    print("\n%d passed, %d failed" % (len(tests) - fails, fails))
    return fails


if __name__ == "__main__":
    sys.exit(1 if _run() else 0)
