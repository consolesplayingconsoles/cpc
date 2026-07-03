#!/usr/bin/env python3
"""Discover translatable text files in an extracted DC disc and cache them.

Scans every file by Shift-JIS density (reusing text_scan's heuristic), keeps
the ones that read as real text (kana ratio high enough), copies just those
(small) into a cache dir under sanitized names, and writes a JSON manifest of
"tabs" for the translation workbench. The big non-text blobs (graphics, audio,
video) are left behind, so the cache stays tiny and per-tab extraction later
reads straight from the cache instead of re-extracting the whole disc.

    sources.py <extracted-dir> <cache-files-dir> <manifest-path>
"""
import json
import os
import shutil
import sys

from text_scan import scan   # same density heuristic, one source of truth

# Thresholds + typology live in config (sources.config.json), so expanding the
# discovery is a DATA edit, not a code change. Falls back to a permissive default
# if the file is missing.
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sources.config.json")
_FALLBACK = {"minKana": 50, "minRatio": 0.45,
             "typology": [{"kind": "text", "view": 9, "match": ["*"]}]}

# Never even read these -- graphics/audio/video blobs that can't be dialogue. Skipping them (+ the
# size cap) is what keeps the scan seconds, not minutes: the disc is ~473 PVR/PVM + big SFD/AFS/MLT.
_SKIP_EXT = {".pvr", ".pvm", ".sfd", ".afs", ".mlt", ".mpb", ".adx", ".pss", ".str", ".mpg", ".wav"}
_MAX_SCAN = 16 * 1024 * 1024   # bytes; the biggest real text is STORY.PAC (~1.5 MB). STORYGRA.PAC
                               # (487 MB) and other giant .PAC/.BIN blobs are graphics, not text.


def _load_config():
    try:
        with open(CONFIG_PATH) as fh:
            return json.load(fh)
    except Exception:
        return _FALLBACK


def _safe(rel):
    # buildgdi emits some names with literal backslashes; flatten for the cache
    return rel.replace("\\", "_").replace("/", "_")


def _classify(rel, typology):
    """(kind, view-priority) for a filename, matched top-to-bottom against the
    config. A pattern is "*" (any), "*.EXT" (extension), or a plain substring."""
    u = rel.upper()
    for entry in typology:
        for pat in entry.get("match", []):
            p = pat.upper()
            if p == "*" or (p.startswith("*.") and u.endswith(p[1:])) \
                    or (not p.startswith("*") and p in u):
                return entry.get("kind", "text"), entry.get("view", 99), entry.get("force", False)
    return "text", 99, False


def main(root, outdir, manifest):
    cfg = _load_config()
    min_kana = cfg.get("minKana", 50)
    min_ratio = cfg.get("minRatio", 0.45)
    typology = cfg.get("typology", [])
    rows = []
    for dp, _dirs, fns in os.walk(root):
        for fn in fns:
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, root)
            kind, pri, force = _classify(rel, typology)
            if not force:
                # PERF: the disc is mostly graphics/audio/video (473 PVR/PVM, a 487 MB STORYGRA.PAC,
                # 67 MB SFD videos, AFS/MLT audio). READING + density-scanning those was the multi-minute
                # hang. Skip binaries by extension + a hard size cap BEFORE the read; the density gate
                # still guards correctness on what's left (a few small text tables).
                if os.path.splitext(fn)[1].lower() in _SKIP_EXT:
                    continue
                try:
                    if os.path.getsize(p) > _MAX_SCAN:
                        continue
                except OSError:
                    continue
            try:
                with open(p, "rb") as fh:
                    data = fh.read()
            except Exception:
                continue
            doubles, kana, _runs = scan(data)
            dense = kana >= min_kana and doubles and kana / doubles >= min_ratio
            # `force` (config) surfaces a named short file (menus/maps) the density gate would skip.
            if dense or force:
                sn = _safe(rel)
                shutil.copyfile(p, os.path.join(outdir, sn))
                rows.append({
                    "file": rel, "safe": sn, "kind": kind, "_pri": pri,
                    "kanaPct": round(100 * kana / doubles) if doubles else 0, "size": len(data),
                })
    # VIEW order (the tab order): by config priority, density as the tiebreak.
    rows.sort(key=lambda r: (r["_pri"], -r["kanaPct"]))
    for view_idx, r in enumerate(rows):
        r["view"] = view_idx
        del r["_pri"]
    # LOAD order (the fetch sequence): smallest first, so a tab paints fast while
    # the big ones (STORY.PAC) extract behind them.
    for load_idx, row_idx in enumerate(
            sorted(range(len(rows)), key=lambda i: rows[i]["size"])):
        rows[row_idx]["loadOrder"] = load_idx
    with open(manifest, "w") as fh:
        json.dump({"sources": rows}, fh)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
