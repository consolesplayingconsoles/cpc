#!/usr/bin/env python3
# Patch wide-char text in a Buu's Fury ROM, in place (no repointing).
# edits file: lines of  0xROMADDR <TAB> new text   (blank lines / # comments ignored)
# Each replacement is written as wide-char ASCII + null terminator, and must fit the
# ORIGINAL slot (original char count). Shorter is fine (padded with nulls). Longer = error.
import sys
base, edits_path, outp = sys.argv[1], sys.argv[2], sys.argv[3]
rom = bytearray(open(base, "rb").read())
def orig_len_chars(off):                         # count wide-chars until 0x0000 terminator
    n = 0
    while off + 1 < len(rom) and not (rom[off] == 0 and rom[off+1] == 0):
        n += 1; off += 2
    return n
ok = warn = 0
for ln in open(edits_path, encoding="utf-8"):
    ln = ln.rstrip("\n")
    if not ln.strip() or ln.lstrip().startswith("#"): continue
    addr_s, _, new = ln.partition("\t")
    if not _: continue
    off = int(addr_s, 16) - 0x08000000
    cap = orig_len_chars(off)
    if len(new) > cap:
        print(f"!! {addr_s}: '{new}' is {len(new)} chars > slot {cap}; SKIPPED (shorten it)"); warn += 1; continue
    b = bytearray()
    for ch in new: b += bytes([ord(ch) & 0xFF, 0x00])
    b += b"\x00\x00"                              # null terminator
    while len(b) < (cap + 1) * 2: b += b"\x00\x00"  # pad rest of old slot with nulls
    rom[off:off + len(b)] = b
    ok += 1
open(outp, "wb").write(rom)
print(f"applied {ok} edits ({warn} skipped) -> {outp}")
