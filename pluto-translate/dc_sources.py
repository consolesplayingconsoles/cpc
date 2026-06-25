#!/usr/bin/env python3
"""Discover translatable text files in an extracted DC disc and cache them.

Scans every file by Shift-JIS density (reusing dc_text_scan's heuristic), keeps
the ones that read as real text (kana ratio high enough), copies just those
(small) into a cache dir under sanitized names, and writes a JSON manifest of
"tabs" for the translation workbench. The big non-text blobs (graphics, audio,
video) are left behind, so the cache stays tiny and per-tab extraction later
reads straight from the cache instead of re-extracting the whole disc.

    dc_sources.py <extracted-dir> <cache-files-dir> <manifest-path>
"""
import json
import os
import shutil
import sys

from dc_text_scan import scan   # same density heuristic, one source of truth

MIN_KANA = 50      # need enough kana to mean anything
MIN_RATIO = 0.45   # >=45% of Shift-JIS pairs are kana == real text, not a blob


def _safe(rel):
    # buildgdi emits some names with literal backslashes; flatten for the cache
    return rel.replace("\\", "_").replace("/", "_")


def main(root, outdir, manifest):
    rows = []
    for dp, _dirs, fns in os.walk(root):
        for fn in fns:
            p = os.path.join(dp, fn)
            try:
                with open(p, "rb") as fh:
                    data = fh.read()
            except Exception:
                continue
            doubles, kana, _runs = scan(data)
            if kana >= MIN_KANA and doubles and kana / doubles >= MIN_RATIO:
                rel = os.path.relpath(p, root)
                sn = _safe(rel)
                shutil.copyfile(p, os.path.join(outdir, sn))
                rows.append({
                    "file": rel,
                    "safe": sn,
                    "kanaPct": round(100 * kana / doubles),
                    "size": len(data),
                })
    rows.sort(key=lambda r: -r["kanaPct"])
    with open(manifest, "w") as fh:
        json.dump({"sources": rows}, fh)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
