#!/usr/bin/env python3
"""Mega Drive text extractor with LZ77 decompression.

Mega Drive games typically use LZ77 compression. This extractor:
1. Scans for LZ77 headers (0x10 + 3-byte size)
2. Attempts decompression
3. Searches decompressed data for Shift-JIS text blocks

Usage:
    python3 extract.py <rom.md> <output/state.json> [game-id]
"""

import json
import os
import sys

def decompress_lz77(data, offset):
    """Decompress LZ77 block starting at offset.

    LZ77 format (Mega Drive):
    - Byte 0: 0x10 (magic)
    - Bytes 1-3: Uncompressed size (big-endian)
    - Remaining bytes: Compressed data
    """
    if offset + 4 > len(data) or data[offset] != 0x10:
        return None

    size = (data[offset+1] << 16) | (data[offset+2] << 8) | data[offset+3]
    if size > 0x100000:  # Sanity check (max 1MB)
        return None

    result = bytearray()
    i = offset + 4

    while len(result) < size and i < len(data):
        flag = data[i]
        i += 1

        for bit in range(8):
            if len(result) >= size:
                break

            if flag & (0x80 >> bit):
                # Literal byte
                if i < len(data):
                    result.append(data[i])
                    i += 1
            else:
                # Back-reference: 2 bytes (offset, length)
                if i + 2 > len(data):
                    break

                ref_byte1 = data[i]
                ref_byte2 = data[i+1]
                i += 2

                offset_val = ((ref_byte1 & 0xF0) << 4) | ref_byte2
                length = (ref_byte1 & 0x0F) + 3

                if offset_val == 0:
                    break

                src_offset = len(result) - offset_val
                for _ in range(length):
                    if len(result) >= size:
                        break
                    if src_offset >= 0 and src_offset < len(result):
                        result.append(result[src_offset])
                        src_offset += 1

    return bytes(result[:size]) if len(result) >= size else None

def find_shift_jis_text(data):
    """Find Shift-JIS text blocks in data."""
    blocks = []
    i = 0

    while i < len(data):
        if (0x81 <= data[i] <= 0x9f or 0xe0 <= data[i] <= 0xfc):
            start = i
            text = []
            jp_count = 0

            while i < len(data) and len(text) < 200:
                b = data[i]
                if b == 0x00:
                    break
                elif 0x20 <= b <= 0x7e:
                    text.append(chr(b))
                    i += 1
                elif (0x81 <= b <= 0x9f or 0xe0 <= b <= 0xfc) and i + 1 < len(data):
                    try:
                        c = data[i:i+2].decode('shift_jis')
                        text.append(c)
                        jp_count += 1
                        i += 2
                    except:
                        break
                else:
                    break

            if jp_count >= 2 and len(text) >= 4:
                blocks.append((start, ''.join(text)))
        else:
            i += 1

    return blocks

def extract(rom_path, output_path, game_id=None):
    """Extract text from Mega Drive ROM with LZ77 decompression."""

    if game_id is None:
        game_id = os.path.splitext(os.path.basename(rom_path))[0].lower().replace(' ', '-')

    with open(rom_path, 'rb') as f:
        data = f.read()

    print(f'[extract] Scanning {len(data) / 1024 / 1024:.1f}MB ROM...')

    # Find and decompress LZ77 blocks
    print('[extract] Searching for LZ77 blocks...')
    blocks = []
    seen = set()

    for i in range(len(data) - 4):
        if data[i] == 0x10 and i not in seen:
            decompressed = decompress_lz77(data, i)
            if decompressed:
                # Search decompressed block for text
                text_blocks = find_shift_jis_text(decompressed)
                for offset, text in text_blocks:
                    if text not in seen:
                        seen.add(text)
                        blocks.append({
                            'offset': f'0x{i:06X}',
                            'decompressed_offset': f'0x{offset:06X}',
                            'jp': text[:100],
                            'jpBytes': len(text.encode('shift_jis', errors='ignore'))
                        })

    print(f'[extract] Found {len(blocks)} text blocks from {len([i for i in range(len(data)) if data[i] == 0x10 and decompress_lz77(data, i)])} valid LZ77 blocks')

    # Build output
    state = {
        'game': game_id,
        'status': 'partial' if blocks else 'blocked',
        'statusText': f'Extracted {len(blocks)} dialogue blocks from LZ77-compressed data',
        'blocks': blocks,
        'speakers': {},
        'notes': 'Fighting game; minimal dialogue expected. LZ77 decompression applied.'
    }

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    print('[extract] Done -> %s' % output_path)
    return state

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: extract.py <rom.md> <output/state.json> [game-id]')
        sys.exit(1)
    extract(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
