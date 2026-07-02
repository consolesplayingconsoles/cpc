#!/bin/sh
# list-systems.sh  — Batocera node helper for the translation flow.
#
# Lists the SOURCE roms systems (one dir name per line) under $ROMS_SRC (a roms dir in the user
# home, default ~/roms). These are the systems that have originals available to translate. Pairs
# with list-games.sh, which lists the games inside a chosen system from the same source tree.
#
# Kept a script (not a hardcoded `ls` in the API) so the whole roms-path policy lives in ONE place:
# change ROMS_SRC here and both the systems picker and the games picker follow.
set -eu

ROMS_SRC="${ROMS_SRC:-$HOME/roms}"
[ -d "$ROMS_SRC" ] || { echo "no source roms dir: $ROMS_SRC (set ROMS_SRC or create it)" >&2; exit 1; }

for d in "$ROMS_SRC"/*/; do
  [ -d "$d" ] || continue
  b=$(basename "$d")
  echo "$b"
done | sort
