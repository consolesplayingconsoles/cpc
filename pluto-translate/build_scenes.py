#!/usr/bin/env python3
"""Incremental STORY.PAC build: patch ONLY the named scenes, leave every other scene original.

The scene-by-scene isolation harness. Start with one scene, confirm it plays in-game (dialogue
AND any mid-scene invention/texture load), then add the next. The first scene that hangs is the
culprit, with zero ambiguity. Everything not listed stays byte-identical to the original disc.

    build_scenes.py <game-name> <orig-root> <patch-root> <scene[,scene...] | all> [api_base]

e.g.  build_scenes.py "Boku Doraemon (Japan) [ca]" .../original .../patch 41
      build_scenes.py "Boku Doraemon (Japan) [ca]" .../original .../patch 41,42,43
"""
import sys, os, json, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "dc"))
import fon_codec
from packers import nullsplit


def load_state(arg, api_base):
    if arg.endswith(".json") and os.path.isfile(arg):
        return json.load(open(arg, encoding="utf-8"))
    url = api_base.rstrip("/") + "/translate/" + urllib.parse.quote(arg)
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.load(r)


def main():
    if len(sys.argv) < 5:
        print(__doc__); sys.exit(1)
    game, orig_root, patch_root, scenes_arg = sys.argv[1:5]
    api_base = sys.argv[5] if len(sys.argv) > 5 else "http://localhost:7700"
    st = load_state(game, api_base)
    blocks = st["sources"]["STORY.PAC"]

    if scenes_arg == "all":
        want, label = None, "ALL"
    else:
        want = {int(x) for x in scenes_arg.split(",")}
        label = ",".join(str(s) for s in sorted(want))

    # only feed the packer blocks from the wanted scenes -> every other scenario stays original
    sel = blocks if want is None else [b for b in blocks if b.get("scene") in want]
    orig = open(os.path.join(orig_root, "STORY.PAC"), "rb").read()
    out, s = nullsplit.pack(orig, sel, fon_codec.fw, box=15, grow=False, prefer=0xce514)
    assert len(out) == len(orig), "size changed!"
    os.makedirs(patch_root, exist_ok=True)
    open(os.path.join(patch_root, "STORY.PAC"), "wb").write(out)
    fon_codec.main2(os.path.join(orig_root, "S18RM04.FON"),
                    os.path.join(patch_root, "S18RM04.FON")) if hasattr(fon_codec, "main2") else None
    print("scenes patched: %s  (%d lines placed, STORY.PAC size kept %d)"
          % (label, s["lines_placed"], len(out)))
    print("patch/ ready -> rebuild in GDIBuilder and test JUST this chapter")


if __name__ == "__main__":
    main()
