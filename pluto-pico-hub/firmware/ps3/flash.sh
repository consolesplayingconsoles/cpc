#!/usr/bin/env bash
# flash.sh -- (re)flash this firmware onto the UART-attached GP2040 Pico.
#
# The Pico runs GP2040 (no MicroPython REPL), so it flashes via BOOTSEL + picotool.
# If our firmware is already running, the UART reset-frame drops it to BOOTSEL with
# no physical button; on a first flash, hold BOOTSEL + replug first. Idempotent.
#   ./flash.sh [firmware.uf2] [uart-device]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
UF2="${1:-$HERE/firmware.uf2}"
DEV="${2:-${UART_DEVICE:-/dev/ttyAMA0}}"
BAUD="${UART_BAUD:-115200}"
[ "$(id -u)" -eq 0 ] || exec sudo "$0" "$@"
[ -f "$UF2" ] || { echo "[ERR] no UF2 at $UF2 -- run ./build.sh first"; exit 1; }

echo "reset-to-BOOTSEL over $DEV (works if our firmware is already running)..."
stty -F "$DEV" "$BAUD" cs8 -cstopb -parenb -crtscts clocal raw -echo -hupcl || true
# control frame: dpad=0xFF, btnL=0x01 -> reset_usb_boot. The 10-byte frame (sticks 0x80,
# xor 0xFE), the same as bridges/hid.py reboot_to_bootsel; the old 6-byte one no longer
# passes the firmware's checksum now that the frame carries the sticks.
for _ in 1 2 3 4 5; do printf '\xAA\x55\xFF\x01\x00\x80\x80\x80\x80\xFE' > "$DEV"; sleep 0.3; done
sleep 3

if lsusb | grep -qi 2e8a; then
  echo "BOOTSEL reached -> flashing $UF2"
  picotool load -x "$UF2"
  echo "done."
else
  echo "no BOOTSEL device (2e8a) on this host's USB after the reset frame"
  exit 2
fi
