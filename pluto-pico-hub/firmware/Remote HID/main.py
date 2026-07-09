# main.py -- CPC Pico HID EMULATOR firmware (MicroPython). Lives in the HUB
# (pluto-pico-hub/firmware/hid/), because flashing Picos is the hub's job, not the
# deploy engine's: Pluto ships the hub, the hub propagates this to the board.
#
# Role: a USB-HID device emulator. Receives input ops from the Pi over UART and
# renders them as a USB HID report to whatever its USB plugs into. (Other fleet
# roles -- serial bridges, spares -- get their own firmware/<role>/.)
#
# CURRENT STAGE -- POC: the HID report isn't wired yet, so the effector is the
# onboard LED. Reads UART0 (GP0=TX, GP1=RX) @115200: b'1' -> LED on, b'0' -> LED
# off. The Pi hub writes 1/0 on a loop; the LED blinking in time proves the
# Pi -> UART -> Pico spine. Next increment swaps led.on()/off() for a USB-HID report.
#
# Wiring (crossed): Pi GPIO14(TX) -> Pico GP1(RX), Pi GPIO15(RX) -> Pico GP0(TX), GND-GND.
# The loop yields (sleep_ms) and catches KeyboardInterrupt so mpremote can always
# break in to re-flash -- no BOOTSEL, no buttons.
from machine import UART, Pin
import time

led = Pin(25, Pin.OUT)
uart = UART(0, baudrate=115200, tx=Pin(0), rx=Pin(1))
led.off()

print("pico HID emulator (POC: blink) up: UART0 @115200 on GP0/GP1")
try:
    while True:
        if uart.any():
            b = uart.read(1)
            if b == b"1":
                led.on()
            elif b == b"0":
                led.off()
        time.sleep_ms(2)
except KeyboardInterrupt:
    led.off()
    print("stopped")
