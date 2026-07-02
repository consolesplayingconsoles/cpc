#!/bin/sh
# build-local.sh <game-name> <original-root> <patch-root> [api_base]
#
# Full LOCAL build for GDIBuilder + Flycast, always from the LIVE app state (never a file that can
# drift — a stale state.json once built the old text and dropped translated lines back to Japanese).
# One command = every patched binary + the patched font into <patch-root>/, ready for GDIBuilder:
#   Original GDI + <patch-root> as the Modified-files folder + separate output + 2352 mode.
#
#   ./build-local.sh "Boku Doraemon (Japan) [ca]" \
#       sandbox/boku-doraemon-japan/original sandbox/boku-doraemon-japan/patch
set -eu

GAME="${1:?usage: build-local.sh <game-name> <original-root> <patch-root> [api_base]}"
ORIG="${2:?need original-root}"
PATCH="${3:?need patch-root}"
API="${4:-http://localhost:7700}"
HERE=$(CDPATH= cd "$(dirname "$0")" && pwd)

echo "[1/2] text binaries (from live state)"
python3 "$HERE/dc/build_patch.py" "$GAME" "$ORIG" "$PATCH" "$API"

# Font: only the DC glyph-codec games have S18RM04.FON; skip cleanly otherwise.
if [ -f "$ORIG/S18RM04.FON" ]; then
  echo "[2/2] patched font"
  python3 "$HERE/dc/fon_codec.py" "$ORIG/S18RM04.FON" "$PATCH/S18RM04.FON"
fi

echo "built -> $PATCH"
echo "GDIBuilder: Original GDI + '$PATCH' as Modified-files -> separate output, 2352 mode."
