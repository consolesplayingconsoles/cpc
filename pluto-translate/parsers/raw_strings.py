#!/usr/bin/env python3
"""Raw null-terminated Shift-JIS string table parser.

Reads embedded string tables (null-terminated, no container format) directly
from binary files. Used for data like day-start week labels in 1ST_READ.BIN.

Returns blocks keyed by absolute file offset, same as other parsers, so the
packer can rewrite each string in place while preserving nulls + padding.
"""

def parse(data, offsets=None):
    """Parse null-terminated strings from a binary blob.

    Args:
        data: bytes to search
        offsets: list of (start_offset, expected_bytes) tuples to extract.
                If None, auto-scan for strings. If provided, extract exactly
                those ranges.

    Returns:
        list of dicts with keys: offset, jpBytes, hex, speaker (=0)
    """
    d = bytes(data)
    blocks = []

    if offsets:
        # Extract specified ranges
        for start, expected_len in offsets:
            if start + expected_len > len(d):
                continue
            raw = d[start:start + expected_len]
            # Check if it's really null-terminated within the expected range
            end = 0
            while end < len(raw) and raw[end:end+2] != b'\x00\x00':
                end += 2
            if end > 0:
                seg = raw[:end]
                blocks.append({"offset": start, "jpBytes": expected_len, "hex": seg.hex(), "speaker": 0})

    return blocks
