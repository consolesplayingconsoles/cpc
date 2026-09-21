#!/usr/bin/env python3
"""Unit tests for make_dcp: the .dcp must be framed the way Universal Dreamcast Patcher frames its own.

This is the bug a player hit on v1.0 (2026-09-20): deltas encoded without `-A -n` carry an app
header (a BLAKE3 gate on the source) and an adler32 window checksum, and UDP refuses them with
"not the right version or region" on 1ST_READ.BIN -- the alphabetically first entry, so it reads
like a boot-binary or wrong-dump problem when every file would in fact fail.

    python3 test_make_dcp.py     # plain asserts, no pytest
"""
import os, sys, shutil, subprocess, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_dcp


def _hdr(delta):
    return subprocess.run([make_dcp.XDELTA, "printhdr", delta],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout.decode(errors="replace")


def _encode(tmp, flags):
    src = os.path.join(tmp, "src.bin"); dst = os.path.join(tmp, "dst.bin"); d = os.path.join(tmp, "d.xdelta")
    body = (b"Doraemon" * 4096)
    open(src, "wb").write(body)
    open(dst, "wb").write(body.replace(b"Doraemon", b"Dorayaki", 1))
    subprocess.run([make_dcp.XDELTA] + flags + ["-B", "67108864", "-s", src, dst, d],
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return src, dst, d


def test_flags_carry_the_udp_compatibility_switches():
    """-A (no app header) and -n (no checksum) are what make UDP accept the patch at all."""
    assert "-A" in make_dcp.ENC_FLAGS, "-A missing: UDP will reject the patch"
    assert "-n" in make_dcp.ENC_FLAGS, "-n missing: UDP will reject the patch"
    assert "lzma" in make_dcp.ENC_FLAGS, "UDP's own patches use lzma secondary compression"


def test_encoded_delta_has_no_appheader_and_no_checksum():
    """The real check: encode with the module's flags and read the VCDIFF header back."""
    tmp = tempfile.mkdtemp(prefix="dcptest-")
    try:
        _, _, d = _encode(tmp, make_dcp.ENC_FLAGS)
        h = _hdr(d)
        assert "VCD_APPHEADER" not in h, "app header present -- UDP will refuse this delta:\n%s" % h
        assert "VCD_ADLER32" not in h, "adler32 present -- UDP will refuse this delta:\n%s" % h
        assert "lzma" in h, "secondary compressor is not lzma:\n%s" % h
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_the_bad_framing_is_what_we_think_it_is():
    """Guard the diagnosis itself: WITHOUT -A -n the same encode does produce both fields, so a
    future xdelta3 that stops writing them would make this whole workaround obsolete (and this
    test would say so) rather than leaving a cargo-culted flag behind."""
    tmp = tempfile.mkdtemp(prefix="dcptest-")
    try:
        _, _, d = _encode(tmp, ["-e", "-f", "-9", "-S", "lzma"])
        h = _hdr(d)
        assert "VCD_APPHEADER" in h and "VCD_ADLER32" in h, \
            "xdelta3 no longer writes the fields -A -n suppress; re-check whether they are needed:\n%s" % h
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_window_covers_the_whole_source():
    """A source window smaller than the file misses matches in the huge PACs (STORYGRA ~465 MB)."""
    assert int(make_dcp.window(10)) >= (1 << 26)
    assert int(make_dcp.window(1 << 30)) == (1 << 30)


def _run():
    if not make_dcp.XDELTA:
        print("SKIP (xdelta3 not installed)"); return 0
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
