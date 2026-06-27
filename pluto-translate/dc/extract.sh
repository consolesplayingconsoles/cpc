#!/bin/sh
# Extract ONE discovered source's text blocks from the cache the /sources scan
# built (so it's fast -- no disc re-extraction). Same cache key as sources.sh.
#   extract.sh <gdi-path> <safe-name>
set -e

GDI="$1"; SAFE="$2"
[ -n "$GDI" ] && [ -n "$SAFE" ] || { echo '{"error":"usage: extract.sh <gdi> <safe>"}'; exit 1; }

KEY=$(printf '%s' "$GDI" | md5sum | cut -c1-12)
CACHE="/userdata/cpc-cache/$KEY"
[ -f "$CACHE/files/$SAFE" ] || { echo '{"error":"source not cached; call /sources first"}'; exit 1; }

python3 /userdata/cpc-scripts/dc/extract.py "$CACHE" "$SAFE"
