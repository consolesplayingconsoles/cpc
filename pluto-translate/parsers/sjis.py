#!/usr/bin/env python3
"""Shared Shift-JIS byte helpers for the parsers -- console-agnostic.

Pure byte predicates, no decoding (the parsers stay codec-free; the browser
decodes). Two lead ranges: the narrower `is_lead` for dialogue kana/kanji, and
the broader `fw_lead` that also admits the 0x81 marks (long-vowel ー, full-width
（）) common in names/labels. Trail range is shared.
"""


def is_lead(b):  return 0x82 <= b <= 0x9F or 0xE0 <= b <= 0xEA
def is_trail(b): return 0x40 <= b <= 0x7E or 0x80 <= b <= 0xFC

def fw_lead(b):  return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xEF
def fw_trail(b): return 0x40 <= b <= 0x7E or 0x80 <= b <= 0xFC


def jp_doubles(data, start, end):
    """Count Shift-JIS double-byte (kana/kanji) chars in data[start:end]."""
    i, n = start, 0
    while i + 1 < end:
        if is_lead(data[i]) and is_trail(data[i + 1]):
            n += 1; i += 2
        else:
            i += 1
    return n
