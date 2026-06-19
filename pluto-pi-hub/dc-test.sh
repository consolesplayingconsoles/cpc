#!/usr/bin/env bash
# dc-test.sh -- manual Dreamcast controller test over the Pico/UART.
#
# Run it ON THE PI; watch the Dreamcast screen. It sends DOWN x3, UP x3, then A
# (open) down the UART to the Pico -> Maple adapter -> Dreamcast. Use it to prove
# the chain is alive: once after a clean device reset, then again after a deploy,
# to confirm the deploy didn't disturb the controller.
#
# Device: arg 1, else $UART_DEVICE, else /dev/ttyAMA0.  (Re-execs itself as root.)
set -eu
[ "$(id -u)" -eq 0 ] || exec sudo "$0" "$@"

DEV="${1:-${UART_DEVICE:-/dev/ttyAMA0}}"
BAUD="${UART_BAUD:-115200}"

echo "DC test -> $DEV @ $BAUD ... watch the Dreamcast."
stty -F "$DEV" "$BAUD" cs8 -cstopb -parenb -crtscts clocal raw -echo -hupcl

byte()  { printf "\\x$(printf '%02x' "$1")"; }
frame() { printf '\xAA\x55'; byte "$1"; byte "$2"; byte "$3"; byte "$(( $1 ^ $2 ^ $3 ))"; }
press() {   # one discrete press: hold (dpad btnL btnH), then neutral
  { for _ in 1 2 3 4 5; do frame "$1" "$2" "$3"; sleep 0.05; done
    for _ in 1 2 3 4 5; do frame 0 0 0;          sleep 0.05; done
  } > "$DEV"
  sleep 0.6
}

echo "  DOWN x3"; for _ in 1 2 3; do press 2 0 0; done; sleep 1
echo "  UP x3";   for _ in 1 2 3; do press 1 0 0; done; sleep 1
echo "  A (open)"; press 0 1 0
echo "done -- did the cursor walk down 3, up 3, then open?"
