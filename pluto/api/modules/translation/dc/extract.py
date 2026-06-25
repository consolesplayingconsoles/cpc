#!/usr/bin/env python3
"""Dreamcast GDI text extractor.

Reads a GDI disc image, scans track 5 for Shift-JIS text blocks tagged with
speaker IDs, and writes a state.json file for the Pluto translation pipeline.

Usage:
    python3 extract.py <disc.gdi> <output/state.json> [game-id]

The track files referenced in the .gdi must be in the same directory as the
.gdi file. Supports 2352-byte raw sectors (Mode 1, data at offset 16).

**Documentation**: See `extract.md` (this directory) for console-level
guide and `games/` subdirectory for per-game extraction notes.

**Example**: Boku Doraemon (Japan) uses speaker tag pattern
`\\x02\\xff[speaker_id]\\x00` + Shift-JIS text. See `games/boku-doraemon.md`.
"""

import json
import os
import re
import struct
import sys

SECTOR_RAW  = 2352
DATA_OFFSET = 16    # Mode 1 user data starts at byte 16
DATA_SIZE   = 2048

# Speaker-tag pattern preceding each text block: 02 ff <id_byte> 00
SPEAKER_TAG = re.compile(b'\x02\xff([\x00-\xff])\x00')

MIN_TEXT_LEN = 8
MAX_TEXT_LEN = 300


# ── GDI parsing ──────────────────────────────────────────────────────────────

def parse_gdi(gdi_path):
    tracks = []
    gdi_dir = os.path.dirname(os.path.abspath(gdi_path))
    with open(gdi_path, 'r') as f:
        lines = f.readlines()
    for line in lines[1:]:
        parts = line.strip().split()
        if len(parts) < 5:
            continue
        num, lba, typ, ss, fname = (
            int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]), parts[4]
        )
        tracks.append({
            'num':         num,
            'lba':         lba,
            'type':        typ,
            'sector_size': ss,
            'path':        os.path.join(gdi_dir, fname),
        })
    return tracks


# ── Sector / byte reading ─────────────────────────────────────────────────────

def _sector_data(track, lba):
    ss  = track['sector_size']
    off = (lba - track['lba']) * ss
    if ss == SECTOR_RAW:
        off += DATA_OFFSET
        size = DATA_SIZE
    else:
        size = ss
    with open(track['path'], 'rb') as f:
        f.seek(off)
        return f.read(size)

def read_bytes(track, start_lba, byte_count):
    # start_lba can be absolute (disc LBA) or track-relative depending on context.
    # If it's larger than 100000, assume it's absolute and convert to track-relative.
    lba = start_lba if start_lba < 100000 else start_lba - track['lba']
    buf = b''
    while len(buf) < byte_count:
        chunk = _sector_data(track, lba)
        buf  += chunk
        lba  += 1
    return buf[:byte_count]


# ── ISO9660 ───────────────────────────────────────────────────────────────────

def _parse_dir_sector(data):
    entries, pos = {}, 0
    while pos < len(data):
        rec_len = data[pos]
        if rec_len == 0:
            break
        name_len = data[pos + 32]
        raw_name = data[pos + 33: pos + 33 + name_len]
        name     = raw_name.decode('ascii', errors='replace').split(';')[0].rstrip('\x00')
        lba      = struct.unpack_from('<I', data, pos + 2)[0]
        size     = struct.unpack_from('<I', data, pos + 10)[0]
        if name not in ('\x00', '\x01'):
            entries[name] = (lba, size)
        pos += rec_len
    return entries

def iso_find(tracks, path_parts):
    t3  = next(t for t in tracks if t['num'] == 3)
    pvd = read_bytes(t3, t3['lba'] + 16, DATA_SIZE)
    root_lba = struct.unpack_from('<I', pvd, 156 + 2)[0]
    entries  = _parse_dir_sector(read_bytes(t3, root_lba, DATA_SIZE))
    for part in path_parts[:-1]:
        lba, _ = entries[part]
        entries = _parse_dir_sector(read_bytes(t3, lba, DATA_SIZE))
    return entries[path_parts[-1]]  # (lba, size)

def track_for_lba(tracks, lba):
    best = None
    for t in sorted(tracks, key=lambda t: t['lba']):
        if t['lba'] <= lba:
            best = t
    return best


# ── Shift-JIS text scanning ───────────────────────────────────────────────────

def _is_sjis_lead(b):
    return (0x81 <= b <= 0x9f) or (0xe0 <= b <= 0xfc)

def _decode_run(data, pos):
    chars = []
    while pos < len(data):
        b = data[pos]
        if 0x20 <= b <= 0x7e:
            chars.append(chr(b))
            pos += 1
        elif b in (0x0a, 0x0d):
            chars.append('\n')
            pos += 1
        elif _is_sjis_lead(b) and pos + 1 < len(data):
            try:
                chars.append(data[pos:pos+2].decode('shift_jis'))
                pos += 2
            except UnicodeDecodeError:
                break
        else:
            break
    return ''.join(chars).strip(), pos

def scan_blocks(pac_data):
    blocks, seen = [], set()
    for m in SPEAKER_TAG.finditer(pac_data):
        text_start = m.end()
        if text_start in seen:
            continue
        text, _ = _decode_run(pac_data, text_start)
        if not (MIN_TEXT_LEN <= len(text) <= MAX_TEXT_LEN):
            continue
        # Require at least one multi-byte Shift-JIS character (actual Japanese)
        has_japanese = any(0x81 <= b <= 0x9f or 0xe0 <= b <= 0xfc
                          for b in text.encode('shift_jis', errors='ignore'))
        if not has_japanese:
            continue
        seen.add(text_start)
        speaker_id = m.group(1)[0]
        blocks.append({
            'offset':    '0x%06X' % m.start(),
            'speakerId': speaker_id,
            'jp':        text,
            'jpBytes':   len(text.encode('shift_jis', errors='ignore')),
            'ca':        '',
        })
    return blocks


# ── Main ──────────────────────────────────────────────────────────────────────

def _checkpoint(output_path, payload):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False)
    print('[extract] %s' % payload.get('statusText', payload.get('status', '')))


def extract(gdi_path, output_path, game_id=None):
    if game_id is None:
        game_id = os.path.splitext(os.path.basename(gdi_path))[0].lower().replace(' ', '-')

    _checkpoint(output_path, {
        'game': game_id, 'status': 'parsing',
        'statusText': 'Parsing GDI disc image...',
    })
    tracks = parse_gdi(gdi_path)
    print('[extract] Found %d tracks' % len(tracks))

    _checkpoint(output_path, {
        'game': game_id, 'status': 'scanning',
        'statusText': 'Scanning track 5 for text blocks...',
    })
    # Game data is stored raw on track 5, not in ISO 9660 directory.
    # Read the entire track 5 file directly.
    track5 = next((t for t in tracks if t['num'] == 5), None)
    if not track5:
        raise IOError("no track 5 found")
    with open(track5['path'], 'rb') as f:
        pac_data = f.read()
    blocks   = scan_blocks(pac_data)

    speaker_ids = sorted(set(b['speakerId'] for b in blocks))
    speakers    = {
        i: {'name': 'Speaker %02d' % i, 'status': 'unconfirmed', 'suggestion': ''}
        for i in speaker_ids
    }

    state = {
        'game': game_id, 'status': 'done',
        'statusText': 'Extracted %d blocks from %d speakers.' % (len(blocks), len(speaker_ids)),
        'blocks': blocks, 'speakers': speakers,
    }

    _checkpoint(output_path, state)
    print('[extract] Done -> %s' % output_path)
    return state


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: extract.py <disc.gdi> <output/state.json> [game-id]')
        sys.exit(1)
    extract(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
