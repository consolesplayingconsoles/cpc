#!/usr/bin/python3
"""Raw string table packer -- inverse of parsers/raw_strings.

Rewrites null-terminated strings with Catalan (via `encode`), IN PLACE
and SAME-SIZE. The entire region (orig_bytes) is preserved and padded
with nulls.

    pack(orig, blocks, encode, box=None) -> bytes   # whole file, same length as orig
"""

def pack(orig, blocks, encode, box=None):
    orig = bytes(orig)
    d = bytearray(orig)
    bymap = {}
    for b in blocks:
        o = b.get("offset")
        bymap[int(o, 16) if isinstance(o, str) else o] = b

    for block in blocks:
        offset = int(block.get("offset"), 16) if isinstance(block.get("offset"), str) else block.get("offset")
        jpBytes = block.get("jpBytes")
        ca = block.get("ca", "").strip()

        if offset + jpBytes > len(d):
            continue

        if ca:
            # Encode Catalan
            encoded = encode(ca)
        else:
            # Keep original
            encoded = orig[offset:offset + jpBytes]

        # Build the replacement: encoded text + null terminator + padding
        region = jpBytes
        new = bytearray()

        if encoded:
            new += encoded

        # Pad with nulls to fill the region
        while len(new) < region:
            new += b"\x00"

        # Truncate or pad to exact size
        if len(new) > region:
            # Overflow: keep original
            d[offset:offset + jpBytes] = orig[offset:offset + jpBytes]
        else:
            # Replace with padded version
            d[offset:offset + jpBytes] = new[:region]

    return bytes(d)
