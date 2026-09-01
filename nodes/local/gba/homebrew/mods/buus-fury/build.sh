#!/usr/bin/env bash
# Buu's Fury meme-mod build (macOS/Linux, no toolchain / no ADS).
# Applies text edits from edits.tsv onto the base ROM -> rom/buus-memes.gba
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BASE="$HERE/rom/baserom.gba"
OUT="$HERE/rom/buus-memes.gba"
[ -f "$BASE" ] || { echo "missing rom/baserom.gba"; exit 1; }
python3 "$HERE/tools/patch_text.py" "$BASE" "$HERE/edits.tsv" "$OUT"
echo "built: $OUT ($(stat -f%z "$OUT" 2>/dev/null || stat -c%s "$OUT") bytes)"
