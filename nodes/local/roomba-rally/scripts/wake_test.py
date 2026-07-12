# SILENT decisive A/B: is the BRC low pulse (wake) what enables actuation?
# Runs the SAME LED command twice -- once with NO pulse, once WITH the 3x pulse.
# NO SOUND. Just watch the Clean ring: which run turns it solid RED (5s)?
from machine import UART, Pin
import time

brc = Pin(2, Pin.OUT)

def open_uart():
    u = UART(0, baudrate=19200, tx=Pin(0), rx=Pin(1), bits=8, parity=None, stop=1)
    time.sleep(0.1)
    if u.any(): u.read()
    return u

def init_full(u):
    u.write(b'\x80'); time.sleep(0.1)     # Start
    u.write(b'\x84'); time.sleep(0.1)     # Full

def led_red(u):
    u.write(b'\x8b\x00\xff\xff')          # Clean ring RED full (NO song, silent)
    time.sleep(5.0)                        # hold 5s so you can see it clearly
    u.write(b'\x8b\x00\x00\x00')           # off

print(">>> TEST 1: NO BRC pulse -- watch Clean ring for RED (5s)")
brc.value(1); time.sleep(0.3)
u = open_uart(); init_full(u); led_red(u); u.deinit()
time.sleep(1.5)

print(">>> TEST 2: WITH 3x BRC pulse (wake) -- watch Clean ring for RED (5s)")
brc.value(1); time.sleep(0.5)
for _ in range(3):
    brc.value(0); time.sleep(0.2)
    brc.value(1); time.sleep(0.2)
time.sleep(2.0)
u = open_uart(); init_full(u); led_red(u); u.deinit()

print(">>> DONE. Which turned the ring RED? TEST 1, TEST 2, both, or neither?")
