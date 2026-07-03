#!/bin/sh
# translate.sh <gdi-path>  — in-place Dreamcast translation build, runs on Batocera.
#
# NEVER rebuilds the GDI. buildgdi/GDIBuilder -rebuild move files to new LBAs and this game reads
# assets by hardcoded disc position -> any rebuild hangs mid-game (proven, even byte-identical). So
# we build the patched files from the LIVE app state and splice each SAME-SIZE file straight into
# its own sectors in the raw track (dc/inplace.py). The disc stays byte-identical except those
# files' sector windows -- zero LBA change, nothing to hang on.
#
#   1. extract the originals      (buildgdi -extract -- extraction is fine, only rebuild is poison)
#   2. build patched files        (build_patch.py from the live state at $LAB_API + fon_codec font)
#   3. copy the GDI               (hardlink tracks; real-copy track05, the one we splice)
#   4. splice same-size files     (STORY.PAC, S18RM04.FON, DOUGU/ITEMTBL.PAC -- all in track05)
#   5. name the .gdi + gamelist   (so Batocera lists "<Game> <Lang>", not "disc")
#
# Source originals live in $ROMS_SRC (~/roms, out of Batocera's scan); output lands in $ROMS_OUT.
# TAG/VER/LAB_API/ROMS_OUT overridable via env.
set -eu

GDI="${1:?usage: translate.sh <gdi-path>}"
[ -f "$GDI" ] || { echo "no such GDI: $GDI" >&2; exit 1; }

TAG="${TAG:-T-Cat}"
VER="${VER:-v1.0}"
ROMS_OUT="${ROMS_OUT:-/userdata/roms}"
LAB_API="${LAB_API:-http://192.168.68.51:7700}"     # the Mac's Pluto API (live translation state)

case "$TAG" in
  T-Cat) LANGNAME=Català; LANG2=ca ;;
  T-Esp) LANGNAME=Español; LANG2=es ;;
  T-Eng) LANGNAME=English; LANG2=en ;;
  *)     LANGNAME="$TAG";  LANG2="$TAG" ;;
esac

DOTNET=/userdata/dotnet/dotnet
BUILDGDI=/userdata/buildgdi-out/buildgdi.dll
HERE=$(CDPATH= cd "$(dirname "$0")" && pwd)

GAMEDIR=$(dirname "$GDI")
GAME=$(basename "$GAMEDIR")               # e.g. "Boku Doraemon (Japan)"
SYSTEM=$(basename "$(dirname "$GAMEDIR")")
GAME_KEY="$GAME [$LANG2]"                  # state key in Pluto, e.g. "Boku Doraemon (Japan) [ca]"
OUT_SYSDIR="$ROMS_OUT/$SYSTEM"
DEST="$OUT_SYSDIR/$GAME $LANGNAME [$TAG] ($VER)"

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
EXTRACT="$WORK/extract"; PATCH="$WORK/patch"
mkdir -p "$EXTRACT" "$PATCH"

echo "[1/5] extract originals"
"$DOTNET" "$BUILDGDI" -extract -gdi "$GDI" -output "$EXTRACT" >/dev/null
# buildgdi writes subdir files as literal-backslash names ("DOUGU\ITEMTBL.PAC"); make them real
# subdirs so build_patch + the splice loop find them the same way everywhere (forward-slash).
python3 - "$EXTRACT" <<'PY'
import os, sys
d = sys.argv[1]
for f in os.listdir(d):
    if "\\" in f:
        sub, base = f.rsplit("\\", 1)
        os.makedirs(os.path.join(d, sub), exist_ok=True)
        os.rename(os.path.join(d, f), os.path.join(d, sub, base))
PY

echo "[2/5] build patched files from live state ($GAME_KEY @ $LAB_API)"
python3 "$HERE/dc/build_patch.py" "$GAME_KEY" "$EXTRACT" "$PATCH" "$LAB_API"
python3 "$HERE/dc/fon_codec.py" "$EXTRACT/S18RM04.FON" "$PATCH/S18RM04.FON"

echo "[3/5] copy GDI -> $DEST (track05 real, rest linked)"
mkdir -p "$OUT_SYSDIR"
rm -rf "$DEST"; mkdir -p "$DEST"
for f in "$GAMEDIR"/*; do
  b=$(basename "$f")
  if [ "$b" = "track05.bin" ]; then cp "$f" "$DEST/$b"; else ln "$f" "$DEST/$b" 2>/dev/null || cp "$f" "$DEST/$b"; fi
done

echo "[4/5] splice same-size files in place (into track05)"
# only same-size files can be spliced in place; inplace.py refuses a mismatch (SECRET.TBL grows -> skip)
for rel in STORY.PAC S18RM04.FON DOUGU/ITEMTBL.PAC DEFMENU.SCP MAINMENU.SCP MAP.SCP NOBIMAP.SCP 1ST_READ.BIN; do
  [ -f "$PATCH/$rel" ] && [ -f "$EXTRACT/$rel" ] || continue
  python3 "$HERE/dc/inplace.py" "$DEST/track05.bin" "$EXTRACT/$rel" "$PATCH/$rel" || echo "  (skipped $rel)"
done
# translated textures (repainted on the Lab, PIL/fonts the box lacks) come from the SOURCE OF TRUTH:
# the committed textures/ dir, served by the Lab API as a tar and fetched here just like the state.
# So a box deploy (which wipes cpc-scripts) can't lose them and nothing is hand-placed. Same-size,
# static (don't depend on state) -> spliced in place.
TEX="$WORK/tex"; mkdir -p "$TEX"
python3 - "$LAB_API" "$GAME_KEY" "$TEX" <<'PY' || echo "  (no textures fetched)"
import sys, io, tarfile, urllib.request, urllib.parse
api, game, dest = sys.argv[1], sys.argv[2], sys.argv[3]
url = api.rstrip("/") + "/translate/" + urllib.parse.quote(game) + "/textures"
with urllib.request.urlopen(url, timeout=120) as r:
    tarfile.open(fileobj=io.BytesIO(r.read())).extractall(dest)
print("  textures fetched from %s" % url)
PY
for f in "$TEX"/*.PVR "$TEX"/*.PVM; do
  [ -f "$f" ] || continue; b=$(basename "$f"); [ -f "$EXTRACT/$b" ] || continue
  python3 "$HERE/dc/inplace.py" "$DEST/track05.bin" "$EXTRACT/$b" "$f" || echo "  (skipped tex $b)"
done

echo "[5/5] name the .gdi + gamelist"
# rename disc.gdi -> "<full name>.gdi" so Batocera lists the game, not "disc"
if [ -f "$DEST/disc.gdi" ]; then mv "$DEST/disc.gdi" "$DEST/$(basename "$DEST").gdi"; fi
NICE=$(printf '%s' "$GAME" | sed 's/ *([^)]*)//g; s/ *\[[^]]*\]//g')
python3 "$HERE/gamelist_name.py" "$OUT_SYSDIR/gamelist.xml" "$OUT_SYSDIR" "$DEST" "$NICE $LANGNAME" ".gdi" || \
  echo "  (gamelist name skipped)"

echo "DONE: $DEST"
