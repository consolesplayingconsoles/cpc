#!/usr/bin/env python3
# Scan a Buu's Fury GBA ROM for wide-char text runs, handling control codes.
# char  = 2 bytes LE, low = ASCII 0x20-0x7E, high = 0x00
# ctrl  = wchar 0x0008 followed by a code wchar 0x00xx  (name tags / colour / pause)  -> shown as {xx}
# run ends at terminator wchar 0x0000.
import sys
rom = open(sys.argv[1] if len(sys.argv) > 1 else "rom/baserom.gba", "rb").read()
MIN = int(sys.argv[2]) if len(sys.argv) > 2 else 12
N = len(rom); out = []; i = 0
while i + 1 < N:
    j = i; chars = []; printable = 0
    while j + 3 < N:
        lo, hi = rom[j], rom[j+1]
        if hi == 0x00 and 0x20 <= lo <= 0x7E:
            chars.append(chr(lo)); printable += 1; j += 2
        elif lo == 0x08 and hi == 0x00 and rom[j+3] == 0x00:
            chars.append("{%02x}" % rom[j+2]); j += 4          # control sequence
        else:
            break
    if printable >= MIN and j + 1 < N and rom[j] == 0 and rom[j+1] == 0:
        out.append((0x08000000 + i, j - i, "".join(chars))); i = j + 2
    else:
        i += 2
for addr, blen, txt in out:
    print(f"0x{addr:08X}\t{blen}\t{txt}")
print(f"\n# {len(out)} strings (>= {MIN} printable chars)", file=sys.stderr)
