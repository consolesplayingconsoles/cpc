#!/bin/sh
# Per-scene budget "used" via the packer; the translated blocks (with ca) arrive on STDIN.
# Same cache key as sources.sh / extract.sh, so it reuses the already-extracted source.
#   measure.sh <gdi-path> <safe>     # blocks JSON on stdin
set -e

GDI="$1"; SAFE="$2"
[ -n "$GDI" ] && [ -n "$SAFE" ] || { echo '{"error":"usage: measure.sh <gdi> <safe>"}'; exit 1; }

KEY=$(printf '%s' "$GDI" | md5sum | cut -c1-12)
CACHE="/userdata/cpc-cache/$KEY"
[ -f "$CACHE/files/$SAFE" ] || { echo '{"error":"source not cached; call /sources first"}'; exit 1; }

python3 /userdata/cpc-scripts/dc/measure.py "$CACHE" "$SAFE"
