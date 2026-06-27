#!/usr/bin/env python3
"""Real STORY.PAC translation patcher (size-preserving stage).

Reads the workbench state.json, encodes each translated block to Shift-JIS via
fon_codec.fw (full-width + the authored accent glyphs), word-wraps to the dialogue
box, and patches in place WITHOUT changing file size: pad short lines with
full-width spaces, and LEAVE overflow lines as the original Japanese (those need
the Option-1 expand/repack, a later stage). Trailing control codes (01ff/04ff
line/page breaks) are preserved so messages still terminate/advance.

Pure stdlib (Python 3.6, no shift_jis codec) so it runs on the Batocera box.

    story_translate.py <state.json> <orig STORY.PAC> <out STORY.PAC> [box_chars]
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fon_codec

LB = b"\x01\xff"          # in-box line break
FW_SP = b"\x81\x40"       # full-width space (padding)

def wrap(text, width):
    lines, cur = [], ""
    for word in text.split(" "):
        if not cur:                          cur = word
        elif len(cur) + 1 + len(word) <= width: cur += " " + word
        else:                                lines.append(cur); cur = word
    if cur: lines.append(cur)
    return lines

def encode_wrapped(text, width):
    return LB.join(fon_codec.fw(line) for line in wrap(text, width))

def _body_end(data, start, end):
    """Strip trailing [0x01-0x06][0xff] control pairs -> where the text body ends."""
    k = end
    while k - 2 >= start and 0x01 <= data[k-2] <= 0x06 and data[k-1] == 0xff:
        k -= 2
    return k

def patch(data, blocks, width):
    patched = overflow = skipped = 0
    for b in blocks:
        ca = (b.get("ca") or "").strip()
        if not ca:
            continue
        off = int(b["offset"], 16)
        body_end = _body_end(data, off, off + b["jpBytes"])
        body_len = body_end - off
        try:
            enc = encode_wrapped(ca, width)
        except ValueError:
            skipped += 1; continue            # char with no glyph -> leave JP
        if len(enc) > body_len:
            overflow += 1; continue           # needs the expand stage -> leave JP
        enc += FW_SP * ((body_len - len(enc)) // 2)
        data[off:off + len(enc)] = enc        # (== body_end; trailing controls untouched)
        patched += 1
    return patched, overflow, skipped

def main():
    if len(sys.argv) < 4:
        print("usage: story_translate.py <state.json> <orig.PAC> <out.PAC> [box_chars]", file=sys.stderr)
        sys.exit(1)
    width = int(sys.argv[4]) if len(sys.argv) > 4 else 14
    st = json.load(open(sys.argv[1], encoding="utf-8"))
    blocks = st.get("sources", {}).get("STORY.PAC", [])
    data = bytearray(open(sys.argv[2], "rb").read())
    orig = len(data)
    p, o, s = patch(data, blocks, width)
    assert len(data) == orig, "size changed!"
    open(sys.argv[3], "wb").write(data)
    print("patched %d  | left-as-JP: %d overflow + %d unencodable | size %d (unchanged)"
          % (p, o, s, orig))

if __name__ == "__main__":
    main()
