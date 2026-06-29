#!/usr/bin/env python3
"""Per-scene Catalan EXPANSION ("used" bytes) for the box-budget meter -- the authoritative number
the build will actually pay, computed by the packer (NOT a UI estimate that ignores control bytes).

Reads the translated blocks (carrying `ca`) as JSON on STDIN, loads the cached source, runs the
packer's `measure`, and prints {"used": {scene: bytes}}.

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
        blocks = json.load(sys.stdin).get("blocks", [])
    except ValueError:
        blocks = []
    with open(os.path.join(cache_dir, "files", safe), "rb") as fh:
        data = fh.read()
    m = nullsplit.measure(data, blocks, fon_codec.fw, box=15)
    print(json.dumps({"used": {str(k): v for k, v in m["scene"].items()}, "line": m["line"]}))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('{"error":"usage: measure.py <cache-dir> <safe>"}')
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
