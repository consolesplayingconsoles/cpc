#!/usr/bin/env python3
"""Per-scene EXPANSION ("used" bytes) for the box-budget meter -- the authoritative number the build
will actually pay, computed by the packer (NOT a UI estimate that ignores control bytes).

Reads the translated blocks (carrying `ca`) as JSON on STDIN, loads the cached source, runs the
packer's `measure`, and prints {"used": {scene: bytes}}.

The STDIN body also carries `lang`, so the meter encodes with the SAME font profile the build will
use (`build_patch._lang`). Without it every project measured as Catalan, and `ca` is CHEAPER than `en`
(its it/ti/ix/li/il digraphs pack two letters per cell), so English scenes read as fitting when the
build would still spill. Absent/empty `lang` stays "ca" -- Catalan behaviour is unchanged.

    measure.py <cache-dir> <safe>     # blocks JSON on stdin
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # pluto-translate
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))                    # dc (fon_codec)

import fon_codec
from packers import nullsplit


def main(cache_dir, safe):
    try:
        body   = json.load(sys.stdin)
        blocks = body.get("blocks", [])
        lang   = (body.get("lang") or "ca").strip() or "ca"
    except ValueError:
        blocks, lang = [], "ca"
    if lang not in fon_codec.LANGS:          # no glyph profile yet -> draft against Catalan
        lang = "ca"
    with open(os.path.join(cache_dir, "files", safe), "rb") as fh:
        data = fh.read()
    m = nullsplit.measure(data, blocks, lambda t: fon_codec.fw(t, lang), box=15)
    print(json.dumps({"used": {str(k): v for k, v in m["scene"].items()}, "line": m["line"]}))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('{"error":"usage: measure.py <cache-dir> <safe>"}')
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
