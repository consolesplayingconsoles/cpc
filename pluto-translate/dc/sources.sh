#!/bin/sh
# Discover translatable text files in a DC disc (the "tabs"). Extracts the disc
# ONCE, scans by Shift-JIS density, caches only the text files (small) + a JSON
# manifest, and prints the manifest. Cached by disc path, so the second call (and
# the per-tab extracts) skip the slow extraction.
#
#   sources.sh <gdi-path>
set -e

GDI="$1"
[ -n "$GDI" ] || { echo '{"error":"gdi path required"}'; exit 1; }
[ -f "$GDI" ] || { echo '{"error":"gdi not found"}'; exit 1; }

KEY=$(printf '%s' "$GDI" | md5sum | cut -c1-12)
CACHE="/userdata/cpc-cache/$KEY"
MAN="$CACHE/sources.json"

# cache hit -> done
if [ -f "$MAN" ]; then cat "$MAN"; exit 0; fi

mkdir -p "$CACHE/files"
W=$(mktemp -d); mkdir -p "$W/x"
/userdata/dotnet/dotnet /userdata/buildgdi-out/buildgdi.dll \
  -extract -gdi "$GDI" -output "$W/x" >/dev/null 2>&1
python3 /userdata/cpc-scripts/dc/sources.py "$W/x" "$CACHE/files" "$MAN"
rm -rf "$W"
cat "$MAN"
