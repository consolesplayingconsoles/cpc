# SILENT LED mapping. Wake pulse + Full, then hold each LED state 5s so you can SEE it.
# Report which STEP(s) light anything and where. No sound.
from machine import UART, Pin
import time

brc = Pin(2, Pin.OUT)
# wake + 19200 (matches the original script that visibly reacted)
brc.value(1); time.sleep(0.5)
for _ in range(3):
    brc.value(0); time.sleep(0.2)
    brc.value(1); time.sleep(0.2)
time.sleep(2.0)

u = UART(0, baudrate=19200, tx=Pin(0), rx=Pin(1), bits=8, parity=None, stop=1)
time.sleep(0.1)
if u.any(): u.read()
u.write(b'\x80'); time.sleep(0.1)     # Start
u.write(b'\x84'); time.sleep(0.1)     # Full

def hold(desc, payload):
    print(">>> %s (5s)" % desc)
    u.write(payload)
    time.sleep(5.0)
    u.write(b'\x8b\x00\x00\x00')       # all off between steps
    time.sleep(1.0)

hold("STEP A: all 4 discrete LEDs ON (debris/spot/dock/check)", b'\x8b\x0f\x00\x00')
hold("STEP B: power ring GREEN full",                           b'\x8b\x00\x00\xff')
hold("STEP C: power ring RED full",                             b'\x8b\x00\xff\xff')
hold("STEP D: discrete ON + power RED (original-style)",        b'\x8b\x0d\xff\xff')

print(">>> DONE. For each step A/B/C/D: did anything light up, and where?")
