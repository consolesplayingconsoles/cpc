#!/bin/sh
# list-games.sh <system>  — Batocera node helper for the translation flow.
#
# Lists translatable (GDI) games under /userdata/roms/<system>/, one full path
# per line. The Pluto UI populates the game dropdown from this output and passes
# the chosen path straight to translate.sh. CHD/other formats are skipped on
# purpose: the pipeline is GDI-native (no conversion).
#
# A "game" is a .gdi file either directly in the system dir or one folder deep
# (the standard "<Game>/disc.gdi" layout).
set -eu

SYSTEM="${1:?usage: list-games.sh <system>}"
ROMS="/userdata/roms/${SYSTEM}"

[ -d "$ROMS" ] || { echo "no roms dir: $ROMS" >&2; exit 1; }

find "$ROMS" -maxdepth 2 -iname '*.gdi' 2>/dev/null | sort
