#!/usr/bin/env python3
"""Build every patched text binary from the LIVE workbench state, via `packers/`.

Repeatable, format-driven: each source's `kind` (from sources.config.json) selects
the packer; the per-source map below says which original file + output path + options.
The packers are game-agnostic (the technique); this script is the thin per-game wiring.

    build_patch.py <game-name | state.json> <original-root> <patch-root> [api_base]

SOURCE OF TRUTH = the live app state, pulled from the API. A state.json FILE on disk can
silently drift behind the app (it did once — 245 blocks stale, so the build compiled the OLD
longer text, scenes overflowed, and translated lines dropped back to Japanese). So the default
is: treat arg 1 as a GAME NAME and fetch the current state from `api_base` (default
http://localhost:7700). Pass an explicit `*.json` path only to build a specific snapshot.

`<original-root>/<file>` is read, `<patch-root>/<file>` written, for each source. The
state-key -> on-disc path mapping restores the subdir (DOUGU_ITEMTBL.PAC -> DOUGU/ITEMTBL.PAC).
"""
import sys, os, json, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # pluto-translate
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))                    # dc (fon_codec)
import fon_codec
from packers import ptrtable, nullsplit, exemsg

# source key -> (on-disc relative path, packer, kwargs). box=full-width wrap width.
PLAN = {
    # prefer: the New Year opening line's offset = where PLAY starts in that scenario (file order
    # != play order), so the scene the player sees first wins the slack. POC hint; see packers note.
    "STORY.PAC":          ("STORY.PAC",          "nullsplit", dict(box=15, grow=False, prefer=0xce514)),
    "DOUGU_ITEMTBL.PAC":  ("DOUGU/ITEMTBL.PAC",  "ptrtable",  dict(box=20)),   # wrap long invention descriptions to 2 lines (short gadget NAMES <=20 stay on one line)
    "INFO_SECRET.TBL":    ("INFO/SECRET.TBL",    "ptrtable",  dict(box=12)),
    # menu / map screens -- same ptrtable format (u32 table + 2df0/22f0 records). Single-line items.
    "DEFMENU.SCP":        ("DEFMENU.SCP",        "ptrtable",  dict(box=None)),   # field/pause menu (4)
    "MAINMENU.SCP":       ("MAINMENU.SCP",       "ptrtable",  dict(box=None)),   # main menu (7)
    "MAP.SCP":            ("MAP.SCP",            "ptrtable",  dict(box=None)),   # map labels
    "NOBIMAP.SCP":        ("NOBIMAP.SCP",        "ptrtable",  dict(box=None)),   # Nobita's-room map labels
    # save / sleep confirmation prompts baked into the boot exe. exemsg = same-size in-place rewrite
    # (the exe must not change length -- see packers/exemsg + dc/inplace).
    "1ST_READ.BIN":       ("1ST_READ.BIN",       "exemsg",    dict()),
}


def load_state(arg, api_base):
    """Prefer the LIVE app state (the API) so the build always matches what's on screen. An explicit
    existing *.json path is honoured (snapshot builds); anything else is a game name -> fetch live."""
    if arg.endswith(".json") and os.path.isfile(arg):
        print("  state: file %s (snapshot build)" % arg)
        return json.load(open(arg, encoding="utf-8"))
    url = api_base.rstrip("/") + "/translate/" + urllib.parse.quote(arg)
    print("  state: LIVE from %s" % url)
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.load(r)


def main():
    if len(sys.argv) < 4:
        print("usage: build_patch.py <game-name | state.json> <original-root> <patch-root> [api_base]")
        sys.exit(1)
    state_arg, orig_root, patch_root = sys.argv[1], sys.argv[2], sys.argv[3]
    api_base = sys.argv[4] if len(sys.argv) > 4 else "http://localhost:7700"
    st = load_state(state_arg, api_base)
    for key, (rel, kind, kw) in PLAN.items():
        blocks = st["sources"].get(key)
        if blocks is None:
            print("  skip %s (not in state)" % key); continue
        src = os.path.join(orig_root, rel)
        if not os.path.isfile(src):
            print("  skip %s (original not in extract: %s)" % (key, rel)); continue
        orig = open(src, "rb").read()
        if kind == "nullsplit":
            out, s = nullsplit.pack(orig, blocks, fon_codec.fw, **kw)
            real = sum(1 for b in blocks if (b.get("ca") or "").strip())
            note = "%d/%d lines (%d%%), %d->%dB" % (
                s["lines_placed"], real, 100 * s["lines_placed"] // max(1, real), len(orig), len(out))
        elif kind == "exemsg":
            out = exemsg.pack(orig, blocks, fon_codec.fw, **kw)
            real = sum(1 for b in blocks if (b.get("ca") or "").strip())
            note = "%d runs, %d->%dB (same-size)" % (real, len(orig), len(out))
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
