#!/usr/bin/env python3
"""Font capacity probe: hijack the FIRST dialogue block with a width-test string.

The question we're answering: does the game's font engine render HALF-WIDTH
characters at half width, or is every glyph a fixed full cell? That decides
whether the "add half-width Latin glyphs" capacity hack is a small win or a big
font-RE project.

We overwrite the opening line (のどかな　お正月だなぁ) with three things side by
side, so one screen shows all the answers at once:

    ＡＢＣ   full-width Latin (2-byte SJIS)  -- known good, our baseline width
    ｱｲｳ     half-width katakana (1-byte)     -- THE TEST
    ABC     ASCII (1-byte)                   -- control (known to render as dots)

Read the dialogue box:
  * half-width katakana shows NARROW  -> engine has a half-width path; adding
    Latin to those glyph slots ~doubles capacity. Hack is worth it.
  * half-width katakana shows dots/blank like ASCII -> no half-width font present;
    the hack means authoring a whole half-width set into the vector font. Big lift.

Codec-free (Batocera's Python has no shift_jis codec): all probe bytes are raw
hex. Size-preserving: pads to the original block length with full-width spaces so
the file layout/offsets don't move. Run against the REAL STORY.PAC (the local
extract is stale/compressed and has no usable text).

    font-probe-patch.py <STORY.PAC-in> [STORY.PAC-out]
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from parsers import nullsplit

# probe pieces, raw Shift-JIS bytes (no codec needed)
FW_ABC   = bytes.fromhex("826082618262")   # ＡＢＣ  full-width Latin
HW_KANA  = bytes.fromhex("b1b2b3")         # ｱｲｳ    half-width katakana
ASCII    = b"ABC"                          # ABC    half-width ASCII
FW_SPACE = bytes.fromhex("8140")           # 　     full-width space (padding)
SEP      = FW_SPACE
PROBE    = FW_ABC + SEP + HW_KANA + SEP + ASCII


OPENING = "のどかな".encode("shift_jis")   # marks the opening-line block


def main(src, dst):
    data = bytearray(open(src, "rb").read())
    blocks = nullsplit.parse(data)
    if not blocks:
        print("ERROR: no dialogue blocks parsed -- wrong/stale/compressed file?")
        sys.exit(1)

    # target the OPENING-line block (のどかな　お正月だなぁ), not block 0
    target = next((b for b in blocks if OPENING in bytes.fromhex(b["hex"])), None)
    if target is None:
        print("ERROR: opening line (のどかな) not found -- wrong file?")
        sys.exit(1)

    off, budget = target["offset"], target["jpBytes"]
    original = bytes(data[off:off + budget])
    print("opening-line block @ 0x%x, %d bytes" % (off, budget))
    print("  text: %s" % original.decode("shift_jis", errors="replace"))

    # replace ONLY the first printable span (up to the first control byte < 0x20).
    # the block holds embedded 01ff/04ff/02ff control codes + a 2nd sentence -- KEEP them.
    span = 0
    while span < len(original) and original[span] >= 0x20:
        span += 1
    if span == 0:
        print("ERROR: block starts with a control byte; no printable span to hijack")
        sys.exit(1)

    if len(PROBE) > span:
        print("ERROR: probe (%d B) longer than first span (%d B)" % (len(PROBE), span))
        sys.exit(1)
    pad = span - len(PROBE)
    payload = PROBE + FW_SPACE * (pad // 2) + (b"\x20" * (pad % 2))
    assert len(payload) == span, (len(payload), span)

    new = payload + original[span:]            # keep control bytes + 2nd sentence intact
    assert len(new) == budget, (len(new), budget)
    data[off:off + budget] = new
    print("  span replaced: %d bytes (kept %d trailing control/2nd-line bytes)"
          % (span, budget - span))
    print("  new hex: %s" % new.hex())

    open(dst, "wb").write(data)
    print("\nwrote %s" % dst)
    print("rebuild + boot. FIRST dialogue line shows side by side:")
    print("  ＡＢＣ (full-width) | ｱｲｳ (half-width kana) | ABC (ascii)")
    print("  -> half-width kana NARROW = engine has a half-width path (hack worth it)")
    print("  -> kana = dots like ascii = no half-width font (big lift)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: font-probe-patch.py <STORY.PAC-in> [STORY.PAC-out]")
        sys.exit(1)
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else src + ".probe"
    main(src, dst)
