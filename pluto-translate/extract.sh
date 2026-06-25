#!/bin/sh
# extract.sh <gdi-path>  — Dreamcast dialogue extractor, runs on Batocera.
#
# Extracts the GDI, parses STORY.PAC, and prints the dialogue table as JSON on
# stdout (blocks = {offset, jpBytes, hex of raw Shift-JIS bytes}). The browser
# decodes the hex for display. Pure read: nothing is written back.
set -eu

GDI="${1:?usage: extract.sh <gdi-path>}"
[ -f "$GDI" ] || { echo '{"error":"no such GDI"}'; exit 1; }

DOTNET=/userdata/dotnet/dotnet
BUILDGDI=/userdata/buildgdi-out/buildgdi.dll
HERE=$(CDPATH= cd "$(dirname "$0")" && pwd)

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
EXT="$WORK/x"; mkdir -p "$EXT"   # buildgdi -extract wants a subdir, not the tmp root

"$DOTNET" "$BUILDGDI" -extract -gdi "$GDI" -output "$EXT" >/dev/null 2>&1
[ -f "$EXT/STORY.PAC" ] || { echo '{"error":"no STORY.PAC in this disc"}'; exit 1; }

python3 "$HERE/dc_story_extract.py" "$EXT/STORY.PAC"
