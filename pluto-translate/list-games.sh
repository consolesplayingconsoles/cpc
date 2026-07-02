#!/bin/sh
# list-games.sh <system>  — Batocera node helper for the translation flow.
#
# Lists translatable (GDI) games under the SOURCE roms tree, $ROMS_SRC/<system>/, one full path
# per line. The Pluto UI populates the game dropdown from this output and passes the chosen path
# straight to translate.sh (which rebuilds into the Batocera-scanned tree). CHD/other formats are
# skipped on purpose: the pipeline is GDI-native (no conversion).
#
# Originals live in $ROMS_SRC (a roms dir in the user home, default ~/roms), NOT in /userdata/roms,
# so Batocera never scans the original and can't merge the patch into it. Both jobs (import here,
# rebuild in translate.sh) read the original from this same source tree.
#
# A "game" is a .gdi file either directly in the system dir or one folder deep
# (the standard "<Game>/disc.gdi" layout).
set -eu

SYSTEM="${1:?usage: list-games.sh <system>}"
ROMS_SRC="${ROMS_SRC:-$HOME/roms}"
ROMS="$ROMS_SRC/${SYSTEM}"

[ -d "$ROMS" ] || { echo "no source roms dir: $ROMS (set ROMS_SRC or create it)" >&2; exit 1; }

find "$ROMS" -maxdepth 2 -iname '*.gdi' 2>/dev/null | sort
