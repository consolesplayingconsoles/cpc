#!/usr/bin/env python3
"""
poc_blink.py -- the most-basic Pi-hub POC: blink the Pico's LED over UART.

Writes b'1'/b'0' on a loop down the GPIO UART. With the Pico running its blink
main.py, the onboard LED blinks in time -> the Pi -> /dev/serial0 -> Pico spine
is proven. One byte, no protocol: a dark LED means wiring / baud / pins, never logic.

  python3 poc_blink.py [device]      # default /dev/serial0   (Ctrl-C to stop)
"""
import sys
import time

from bridges.uart import UartLink

device = sys.argv[1] if len(sys.argv) > 1 else "/dev/serial0"
link = UartLink(device).open()
print("blinking the Pico via %s @115200 -- Ctrl-C to stop" % device)
try:
    while True:
        link.send(b"1")
        time.sleep(0.5)
        link.send(b"0")
        time.sleep(0.5)
except KeyboardInterrupt:
    link.send(b"0")
    link.close()
    print("\nstopped")
