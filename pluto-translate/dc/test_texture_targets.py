#!/usr/bin/env python3
"""Unit tests for texture_targets: which disc copies a repainted texture replaces.

Uses the real Boku Doraemon extract + the committed en textures (skips if absent).

    python3 test_texture_targets.py     # plain asserts, no pytest
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import texture_targets as tt

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
ORIG = os.path.join(ROOT, "sandbox", "boku-doraemon-japan", "original")
TEX = "/Users/francesc.montserrat/workspace/translations/dc/Boku Doraemon (Japan) [en]/textures"


def test_same_picture_copies_all_patched_with_their_own_index():
    """CONT_0.PVR sits at root, MEMORY/ and DOUGU/ (same picture, different GBIX). All three get the
    repaint, and each keeps its own index -- the old `find -print -quit` patched only one."""
    res = dict(tt.targets(ORIG, os.path.join(TEX, "CONT_0.PVR")))
    assert sorted(res) == ["CONT_0.PVR", "DOUGU/CONT_0.PVR", "MEMORY/CONT_0.PVR"], sorted(res)
    tex = open(os.path.join(TEX, "CONT_0.PVR"), "rb").read()
    for rel, data in res.items():
        orig = open(os.path.join(ORIG, rel), "rb").read()
        assert data[8:16] == orig[8:16], "%s lost its GBIX index" % rel
        assert data[:8] == tex[:8] and data[16:] == tex[16:], "%s is not the repaint" % rel


def test_unique_texture_resolves_to_its_one_disc_path():
    """A texture that exists once keeps resolving to exactly that path (subdir included)."""
    assert [r for r, _ in tt.targets(ORIG, os.path.join(TEX, "JYOU_00.PVR"))] == ["INFO/JYOU_00.PVR"]
    assert [r for r, _ in tt.targets(ORIG, os.path.join(TEX, "TITLE.PVM"))] == ["TITLE.PVM"]


def _run():
    if not (os.path.isdir(ORIG) and os.path.isdir(TEX)):
        print("SKIP (no extract or textures on this host)")
        return 0
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
