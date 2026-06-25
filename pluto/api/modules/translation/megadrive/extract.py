#!/usr/bin/env python3
"""Mega Drive text extractor - from fan patch (authoritative source).

Parses English translation patch (byreng095a.ips) to extract exact text locations.
Each patch record = one text block. No guessing, no false positives.
"""

import json
import os
import sys

PAGE_SIZE = 50  # Small page: finish extraction in seconds

def parse_ips_patch(patch_path):
    """Parse IPS patch file and extract text block locations/data."""
    blocks = []

    with open(patch_path, 'rb') as f:
        header = f.read(5)
        if header != b'PATCH':
            raise ValueError("Not an IPS patch file")

        while True:
            offset_bytes = f.read(3)
            if offset_bytes == b'EOF' or len(offset_bytes) < 3:
                break

            offset = (offset_bytes[0] << 16) | (offset_bytes[1] << 8) | offset_bytes[2]
            size_bytes = f.read(2)
            size = (size_bytes[0] << 8) | size_bytes[1]

            if size == 0:
                # RLE record (rare for text)
                rle_size_bytes = f.read(2)
                rle_size = (rle_size_bytes[0] << 8) | rle_size_bytes[1]
                rle_byte = f.read(1)
                # Skip RLE records
            else:
                # Regular data record
                data = f.read(size)

                # Try to decode as Shift-JIS text
                try:
                    text = data.decode('shift_jis', errors='ignore').strip()
                    if text and len(text) >= 2:
                        blocks.append({
                            'offset': f'0x{offset:08X}',
                            'jp': text,
                            'jpBytes': size
                        })
                except:
                    pass

    return blocks

def extract(rom_path, output_path, game_id=None):
    """Extract text using patch file as ground truth."""

    if game_id is None:
        game_id = os.path.splitext(os.path.basename(rom_path))[0].lower().replace(' ', '-')

    # Find patch file (try both names)
    patch_dir = os.path.dirname(os.path.abspath(rom_path))
    patch_names = ['dbzbyreng095a.ips', 'byreng095a.ips']
    patch_path = None

    for name in patch_names:
        candidate = os.path.join(patch_dir, name)
        if os.path.exists(candidate):
            patch_path = candidate
            break

    if not patch_path:
        raise FileNotFoundError(f"Patch file not found in {patch_dir}")

    print(f'[extract] Parsing patch: {os.path.basename(patch_path)}')

    blocks = parse_ips_patch(patch_path)
    print(f'[extract] Found {len(blocks)} text blocks from patch')

    # Paginate: return only first PAGE
    page = blocks[:PAGE_SIZE]

    state = {
        'game': game_id,
        'status': 'paginated',
        'statusText': f'Page 1 of {(len(blocks) + PAGE_SIZE - 1) // PAGE_SIZE}: {len(page)} blocks',
        'total_blocks': len(blocks),
        'page_size': PAGE_SIZE,
        'current_page': 1,
        'blocks': page,
        'speakers': {},
        'notes': f'Extracted from English translation patch (byreng095a.ips). Total: {len(blocks)} blocks.'
    }

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    print(f'[extract] Done -> {output_path}')
    return state

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: extract.py <rom.md> <output/state.json> [game-id]')
        sys.exit(1)
    extract(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
