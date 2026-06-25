#!/usr/bin/env python3
"""Content-based text recon for a Dreamcast disc.

DC has no naming convention, so don't guess by extension/folder — scan EVERY
extracted file for dense Shift-JIS and rank by how much Japanese it holds. The
files that light up are where the text lives (dialogue, menus, subtitles), in
whatever container the studio happened to use.

Codec-free (no shift_jis codec needed): we just test byte pairs against the
Shift-JIS lead/trail ranges, same heuristic as dc_story_extract. Ranks by the
KANA RATIO (kana / all pairs), NOT raw count: real text is mostly kana, while a
huge graphics/audio/video blob scatters many incidental pairs of which few are
kana. (Doraemon: STORY.PAC 71%, ITEMTBL.PAC 74%, MESSAGE.INI 55% = text;
STORYGRA.PAC 1.3%, *.SFD ~2%, *.AFS ~0.2% = graphics/video/voice, correctly sunk.)

    python3 dc_text_scan.py <extracted-disc-dir> [top_n]
"""
import os
import sys


def _lead(b):   # Shift-JIS lead byte (kanji + kana planes)
    return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xEF


def _trail(b):
    return 0x40 <= b <= 0x7E or 0x80 <= b <= 0xFC


def _kana(b0, b1):  # hiragana / katakana blocks — strongest "this is Japanese" tell
    w = (b0 << 8) | b1
    return 0x829F <= w <= 0x82F1 or 0x8340 <= w <= 0x8396


def scan(data):
    n = len(data)
    i = 0
    doubles = kana = runs4 = run = 0
    while i < n - 1:
        if _lead(data[i]) and _trail(data[i + 1]):
            doubles += 1
            if _kana(data[i], data[i + 1]):
                kana += 1
            run += 1
            i += 2
        else:
            if run >= 4:
                runs4 += 1
            run = 0
            i += 1
    if run >= 4:
        runs4 += 1
    return doubles, kana, runs4


def main(root, top_n):
    rows = []
    for dp, _dirs, fns in os.walk(root):
        for fn in fns:
            p = os.path.join(dp, fn)
            try:
                with open(p, "rb") as fh:
                    data = fh.read()
            except Exception:
                continue
            d, k, r = scan(data)
            # Rank by the KANA RATIO (kana / all pairs), not raw count: a huge
            # graphics/audio/video blob scatters many incidental pairs but few are
            # kana, so its ratio is tiny; real text is mostly kana. Floor the
            # absolute kana so a one-pair file can't show a bogus 100%.
            if k >= 50:
                rows.append((k / d if d else 0.0, k, d, r, len(data),
                             os.path.relpath(p, root)))
    rows.sort(reverse=True)
    print("%6s %8s %8s %7s %11s  file" % ("kana%", "kana", "doubles", "runs4+", "size"))
    print("-" * 66)
    for ratio, k, d, r, sz, rel in rows[:top_n]:
        print("%5.0f%% %8d %8d %7d %11d  %s" % (ratio * 100, k, d, r, sz, rel))
    print("-" * 66)
    print("%d files with >=50 kana pairs (high kana%% = real text, not a blob)" % len(rows))


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 40)
