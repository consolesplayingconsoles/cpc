#!/usr/bin/env python3
"""Codec-free STORY.PAC patcher for the Dreamcast translation flow.

Batocera's minimal Python has no shift_jis codec, so this works purely at the
byte level: it finds Japanese dialogue blocks by Shift-JIS byte patterns and
replaces the Japanese with repeating full-width Latin (ＣＡＴＡＬＡ), preserving
control bytes and the exact file size. This is the smoke-test auto-patch that
proves the pipeline end to end; real per-block translation is a later step.

Mirrors the codec-using latinize on a machine that has shift_jis; output is
meant to be byte-identical for the same input.
"""
import sys

# "ＣＡＴＡＬＡ　" (full-width C A T A L A + full-width space) in Shift-JIS bytes.
# Full-width Latin A-Z are contiguous 0x8260-0x8279 (L = 0x826B); space = 0x8140.
FILL = bytes.fromhex("8262826082738260826b82608140")
MIN_RUN = 4  # only replace printable runs of >= this many bytes

def _is_lead(b):  return 0x82 <= b <= 0x9F or 0xE0 <= b <= 0xEA   # kana/kanji leads (skip 0x81 symbols)
def _is_trail(b): return 0x40 <= b <= 0x7E or 0x80 <= b <= 0xFC

def _jp_doubles(data, start, end):
    """Count Shift-JIS double-byte (kana/kanji) chars in data[start:end]."""
    i, n = start, 0
    while i + 1 < end:
        if _is_lead(data[i]) and _is_trail(data[i + 1]):
            n += 1; i += 2
        else:
            i += 1
    return n

def _fill_run(data, start, end):
    """Overwrite the printable run data[start:end] with full-width Latin, same length."""
    run = end - start
    even = run - (run & 1)
    buf = (FILL * (even // len(FILL) + 1))[:even]
    if run & 1:
        buf += b"\x20"
    data[start:end] = buf

def patch(data):
    """In place. Returns the number of printable runs replaced."""
    n, i, count = len(data), 0, 0
    while i < n:
        if data[i] == 0:                       # blocks are null-delimited
            i += 1; continue
        seg_start = i
        while i < n and data[i] != 0:
            i += 1
        seg_end = i
        if _jp_doubles(data, seg_start, seg_end) >= 2:   # looks like dialogue
            j = seg_start
            while j < seg_end:
                if data[j] < 0x20:             # control byte (line/page) -> keep
                    j += 1; continue
                run_start = j
                while j < seg_end and data[j] >= 0x20:
                    j += 1
                if j - run_start >= MIN_RUN:
                    _fill_run(data, run_start, j); count += 1
    return count

def main():
    if len(sys.argv) < 2:
        print("usage: dc_story_patch.py <STORY.PAC> [out]", file=sys.stderr)
        sys.exit(1)
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else src
    data = bytearray(open(src, "rb").read())
    orig = len(data)
    c = patch(data)
    assert len(data) == orig, "size changed!"
    open(dst, "wb").write(data)
    print("patched %d runs, size %d (unchanged)" % (c, orig))

if __name__ == "__main__":
    main()
