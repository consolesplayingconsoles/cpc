#!/usr/bin/env python3
"""Which disc files a repainted texture replaces -- shared by translate.sh (the image) and make_dcp.py
(the patch), so both always patch the same copies.

A disc can hold several files with one name that are the SAME picture used on different screens. Boku
Doraemon's CONT_0.PVR (the D-pad/A/B legend) is at the root, in MEMORY/ and in DOUGU/: byte-identical
except the GBIX global index (bytes 8-15), which the game uses to tell textures apart. Picking one by
`find` order translated only whichever copy the filesystem listed first and overwrote its index with the
repaint's. Instead: every same-name, same-size original showing the same picture as the repaint's base
gets the repaint, each keeping its OWN GBIX payload.

    texture_targets.py <extract-root> <texture> <out-dir>    # prints "<disc path>\t<patched file>" per copy
"""
import os, sys

GBIX = b"GBIX"
IDX = slice(8, 16)                                   # GBIX payload: global index (+ padding)


def _without_index(data):
    """The picture alone: the GBIX index blanked, so copies that differ only by index compare equal."""
    if data[:4] == GBIX and len(data) >= 16:
        return data[:8] + b"\0" * 8 + data[16:]
    return data


def targets(extract_root, tex_path):
    """-> [(disc path, patched bytes)] for every original the repaint replaces."""
    tex = open(tex_path, "rb").read()
    name = os.path.basename(tex_path)
    cands = []
    for dirpath, _, files in os.walk(extract_root):
        if name in files:
            p = os.path.join(dirpath, name)
            if os.path.getsize(p) == len(tex):
                cands.append((os.path.relpath(p, extract_root).replace(os.sep, "/"), open(p, "rb").read()))
    if not cands:
        return []
    # the repaint's base = the candidate sharing the most bytes with it; its picture defines the group
    base = max(cands, key=lambda c: sum(1 for a, b in zip(c[1], tex) if a == b))[1]
    picture = _without_index(base)
    out = []
    for rel, orig in sorted(cands):
        if _without_index(orig) != picture:
            continue                                  # same name, different picture: not this texture
        patched = tex
        if orig[:4] == GBIX and tex[:4] == GBIX:
            patched = tex[:IDX.start] + orig[IDX] + tex[IDX.stop:]
        out.append((rel, patched))
    return out


def main():
    if len(sys.argv) != 4:
        raise SystemExit("usage: texture_targets.py <extract-root> <texture> <out-dir>")
    root, tex, out_dir = sys.argv[1:4]
    for rel, data in targets(root, tex):
        dst = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, "wb").write(data)
        print("%s\t%s" % (rel, dst))


if __name__ == "__main__":
    main()
