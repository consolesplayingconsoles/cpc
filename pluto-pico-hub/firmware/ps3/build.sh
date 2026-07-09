#!/usr/bin/env bash
# build.sh -- build the CPC "ps3" firmware: a Pico that impersonates a PS3 controller.
#
# Syncs our UartInput addon source into a WIRED GP2040-CE checkout, compiles, and
# emits ./firmware.uf2 (gitignored). The one-time GP2040 source wiring (register
# the addon + set the PS3 mode that names this role) is documented in README.md;
# this script re-syncs our files and rebuilds, it does not re-patch GP2040 for you.
#
# Prereqs on the build host (the Pi bench), see README.md:
#   apt: cmake gcc-arm-none-eabi libnewlib-arm-none-eabi libstdc++-arm-none-eabi-newlib build-essential
#   pico-sdk (ref 2.2.0) at $PICO_SDK_PATH   (default ~/pico-sdk)
#   GP2040-CE checkout, wired per README, at $GP2040_DIR (default ~/GP2040-CE)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
GP2040_DIR="${GP2040_DIR:-$HOME/GP2040-CE}"
PICO_SDK_PATH="${PICO_SDK_PATH:-$HOME/pico-sdk}"
BOARD="${GP2040_BOARDCONFIG:-Pico}"

[ -d "$GP2040_DIR/src/addons" ] || { echo "[ERR] no GP2040-CE at $GP2040_DIR (README: clone + wire it)"; exit 1; }
[ -d "$PICO_SDK_PATH/src" ]     || { echo "[ERR] no pico-sdk at $PICO_SDK_PATH (README: clone ref 2.2.0)"; exit 1; }

echo "[1/3] sync addon source -> GP2040-CE"
cp -f "$HERE/uartinput.h"   "$GP2040_DIR/headers/addons/uartinput.h"
cp -f "$HERE/uartinput.cpp" "$GP2040_DIR/src/addons/uartinput.cpp"
cp -f "$HERE/fsdata.c"      "$GP2040_DIR/lib/httpd/fsdata.c"
grep -q 'new UartInput()' "$GP2040_DIR/src/gp2040.cpp" || {
  echo "[ERR] UartInput not registered in src/gp2040.cpp -- do the one-time wiring (README) first."; exit 1; }

echo "[2/3] configure + build (SKIP_WEBBUILD, board=$BOARD)"
cd "$GP2040_DIR"
PICO_SDK_PATH="$PICO_SDK_PATH" GP2040_BOARDCONFIG="$BOARD" SKIP_WEBBUILD=TRUE \
  cmake -B build -DCMAKE_BUILD_TYPE=Release
GP2040_BOARDCONFIG="$BOARD" cmake --build build --parallel "$(nproc 2>/dev/null || echo 3)"

echo "[3/3] extract UF2"
UF2="$(ls -t build/GP2040-CE_*_"$BOARD".uf2 | head -1)"
cp -f "$UF2" "$HERE/firmware.uf2"
echo "OK -> firmware/dreamcast/firmware.uf2   (from $UF2)"
