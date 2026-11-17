#!/usr/bin/env bash
# gp2040-build.sh -- build one CPC firmware from the GP2040-CE fork (the gp2040-ce submodule).
#
# One image covers every input mode (gamepad modes and a mouse): the fork carries our UartInput
# addon and the mouse driver, and the mode is switched at runtime over the UART (control frame
# FF 04 <mode>, sent by the Pi hub). -DCPC_INPUT_MODE only sets what a board with no stored mode
# boots as. ps3/build.sh calls this; the result is its own ./firmware.uf2 (gitignored).
# Nothing is downloaded here: the submodule and the SDK have to be there.
#
#   ./gp2040-build.sh <INPUT_MODE_...> <out.uf2>      e.g.  INPUT_MODE_PS3 ps3/firmware.uf2
#
# Prereqs on the build host (the Pi bench):
#   apt: cmake gcc-arm-none-eabi libnewlib-arm-none-eabi libstdc++-arm-none-eabi-newlib build-essential
#   pico-sdk (ref 2.2.0) at $PICO_SDK_PATH (default ~/pico-sdk), with its lib/lwip and lib/tinyusb
#                               submodules: GP2040-CE's network stack (lib/lwip-port) links them even
#                               though the board itself uses GP2040-CE's own TinyUSB fork
#   the submodule checked out:  git submodule update --init pluto-pico-hub/firmware/gp2040-ce
#   GP2040-CE's own two submodules (its TinyUSB fork and Pico-PIO-USB):
#                               git -C pluto-pico-hub/firmware/gp2040-ce submodule update --init
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:?usage: gp2040-build.sh <INPUT_MODE_...> <out.uf2>}"
OUT="${2:?usage: gp2040-build.sh <INPUT_MODE_...> <out.uf2>}"
GP2040_DIR="${GP2040_DIR:-$HERE/gp2040-ce}"
PICO_SDK_PATH="${PICO_SDK_PATH:-$HOME/pico-sdk}"
BOARD="${GP2040_BOARDCONFIG:-Pico}"
BUILD="build-$(echo "$MODE" | tr 'A-Z_' 'a-z-')"

[ -f "$GP2040_DIR/src/addons/uartinput.cpp" ] || { echo "[ERR] no GP2040-CE fork at $GP2040_DIR (git submodule update --init pluto-pico-hub/firmware/gp2040-ce)"; exit 1; }
[ -d "$PICO_SDK_PATH/src" ]                   || { echo "[ERR] no pico-sdk at $PICO_SDK_PATH (git clone --branch 2.2.0 https://github.com/raspberrypi/pico-sdk)"; exit 1; }
[ -f "$PICO_SDK_PATH/lib/lwip/src/include/lwip/init.h" ] && [ -f "$PICO_SDK_PATH/lib/tinyusb/src/tusb.h" ] || { echo "[ERR] the pico-sdk's submodules are missing (git -C $PICO_SDK_PATH submodule update --init lib/lwip lib/tinyusb)"; exit 1; }
[ -f "$GP2040_DIR/lib/tinyusb/src/tusb.h" ]   || { echo "[ERR] GP2040-CE's own submodules are missing (git -C $GP2040_DIR submodule update --init)"; exit 1; }

echo "[1/3] the web-UI stub (SKIP_WEBBUILD needs lib/httpd/fsdata.c)"
cp -f "$HERE/ps3/fsdata.c" "$GP2040_DIR/lib/httpd/fsdata.c"

echo "[2/3] configure + build ($MODE, board=$BOARD, dir=$BUILD)"
cd "$GP2040_DIR"
PICO_SDK_PATH="$PICO_SDK_PATH" GP2040_BOARDCONFIG="$BOARD" SKIP_WEBBUILD=TRUE SKIP_SUBMODULES=TRUE \
  cmake -B "$BUILD" -DCMAKE_BUILD_TYPE=Release -DCPC_INPUT_MODE="$MODE"
GP2040_BOARDCONFIG="$BOARD" cmake --build "$BUILD" --parallel "$(nproc 2>/dev/null || echo 3)"

echo "[3/3] extract UF2"
UF2="$(ls -t "$BUILD"/GP2040-CE_*_"$BOARD".uf2 | head -1)"
cp -f "$UF2" "$OUT"
echo "OK -> $OUT   (from $GP2040_DIR/$UF2)"
