#!/bin/sh
# translate.sh <gdi-path>  — Dreamcast translation engine, runs on Batocera.
#
# Takes one GDI (the path the UI picked from /userdata/roms/<system>/), and:
#   1. extracts it           (buildgdi -extract)
#   2. auto-patches STORY.PAC (codec-free, full-width Catalan smoke-test fill)
#   3. rebuilds              (buildgdi -rebuild, original + patched file)
#   4. writes the patched GDI back next to the original, named per the ROM
#      convention: "Title (Region) [Tag] (Version)" -> "<Game> [T-Cat] (v1.0)/"
#
# GDI-native end to end: no CHD conversion. All work in a temp dir; only the
# final output folder is durable. The UI/refresh picks it up.
#
# TAG / VER are overridable (the UI passes them): TAG=T-Esp VER=v1.1 translate.sh ...
set -eu

GDI="${1:?usage: translate.sh <gdi-path>}"
[ -f "$GDI" ] || { echo "no such GDI: $GDI" >&2; exit 1; }

TAG="${TAG:-T-Cat}"   # translation tag: T-Cat=Català, T-Esp=Español, ...
VER="${VER:-v1.0}"

DOTNET=/userdata/dotnet/dotnet
BUILDGDI=/userdata/buildgdi-out/buildgdi.dll
HERE=$(CDPATH= cd "$(dirname "$0")" && pwd)   # scripts root; dc/ holds story_patch.py

GAMEDIR=$(dirname "$GDI")
GAME=$(basename "$GAMEDIR")
SYSDIR=$(dirname "$GAMEDIR")
DEST="$SYSDIR/$GAME [$TAG] ($VER)"

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
EXTRACT="$WORK/extract"; PATCH="$WORK/patch"; OUT="$WORK/out"
mkdir -p "$EXTRACT" "$PATCH" "$OUT"

echo "[1/4] extract"
"$DOTNET" "$BUILDGDI" -extract -gdi "$GDI" -output "$EXTRACT" >/dev/null

echo "[2/4] patch STORY.PAC (codec-free)"
python3 "$HERE/dc/story_patch.py" "$EXTRACT/STORY.PAC" "$PATCH/STORY.PAC"

echo "[3/4] rebuild"
"$DOTNET" "$BUILDGDI" -rebuild -gdi "$GDI" -data "$PATCH" -output "$OUT" >/dev/null

echo "[4/4] write back -> $DEST"
rm -rf "$DEST"; mkdir -p "$DEST"
cp "$OUT"/* "$DEST/"

echo "DONE: $DEST"
