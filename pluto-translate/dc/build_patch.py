#!/usr/bin/env python3
"""Build every patched text binary from a workbench state.json, via `packers/`.

Repeatable, format-driven: each source's `kind` (from sources.config.json) selects
the packer; the per-source map below says which original file + output path + options.
The packers are game-agnostic (the technique); this script is the thin per-game wiring.

    build_patch.py <state.json> <original-root> <patch-root>

`<original-root>/<file>` is read, `<patch-root>/<file>` written, for each source. The
state-key -> on-disc path mapping restores the subdir (DOUGU_ITEMTBL.PAC -> DOUGU/ITEMTBL.PAC).
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # pluto-translate
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))                    # dc (fon_codec)
import fon_codec
from packers import ptrtable, nullsplit

# source key -> (on-disc relative path, packer, kwargs). box=full-width wrap width.
PLAN = {
    # prefer: the New Year opening line's offset = where PLAY starts in that scenario (file order
    # != play order), so the scene the player sees first wins the slack. POC hint; see packers note.
    "STORY.PAC":          ("STORY.PAC",          "nullsplit", dict(box=15, grow=False, prefer=0xce514)),
    "DOUGU_ITEMTBL.PAC":  ("DOUGU/ITEMTBL.PAC",  "ptrtable",  dict(box=None)),
    "INFO_SECRET.TBL":    ("INFO/SECRET.TBL",    "ptrtable",  dict(box=12)),
}


def main():
    state, orig_root, patch_root = sys.argv[1], sys.argv[2], sys.argv[3]
    st = json.load(open(state, encoding="utf-8"))
    for key, (rel, kind, kw) in PLAN.items():
        blocks = st["sources"].get(key)
        if blocks is None:
            print("  skip %s (not in state)" % key); continue
        orig = open(os.path.join(orig_root, rel), "rb").read()
        if kind == "nullsplit":
            out, s = nullsplit.pack(orig, blocks, fon_codec.fw, **kw)
            real = sum(1 for b in blocks if (b.get("ca") or "").strip())
            note = "%d/%d lines (%d%%), %d->%dB" % (
                s["lines_placed"], real, 100 * s["lines_placed"] // max(1, real), len(orig), len(out))
        else:
            out = ptrtable.pack(orig, blocks, fon_codec.fw, **kw)
            real = sum(1 for b in blocks if (b.get("ca") or "").strip())
            note = "%d records, %d->%dB" % (real, len(orig), len(out))
        dst = os.path.join(patch_root, rel)
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        open(dst, "wb").write(out)
        print("  %-20s [%s] -> %s  (%s)" % (key, kind, rel, note))


if __name__ == "__main__":
    main()
