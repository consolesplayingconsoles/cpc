# 19200 is the live baud (confirmed). This probe checks the OI MODE after each command,
# because sensor reads work in Passive but LED/song/Drive need Safe/Full. It reads mode
# back (packet 35: 0=off 1=passive 2=safe 3=full) so we SEE whether Start/Safe/Full take.
# Paste the whole output.
from machine import UART, Pin
import time

led = Pin(15, Pin.OUT)
brc = Pin(2, Pin.OUT)
brc.value(1)
time.sleep(0.3)

u = UART(0, baudrate=19200, tx=Pin(0), rx=Pin(1), bits=8, parity=None, stop=1)
time.sleep(0.1)
if u.any():
    u.read()

def read_mode(tag):
    if u.any():
        u.read()
    u.write(bytes([142, 35]))     # request OI mode (packet 35, 1 byte)
    time.sleep(0.2)
    d = u.read()
    if d:
        m = d[-1]
        names = {0: "OFF", 1: "PASSIVE", 2: "SAFE", 3: "FULL"}
        print("  mode after %s = %d (%s)  raw=%s" % (tag, m, names.get(m, "?"), d))
    else:
        print("  mode after %s = NO REPLY" % tag)

print("### mode probe @ 19200 ###")
read_mode("open (no start)")

u.write(b'\x80'); time.sleep(0.5)
read_mode("START(0x80)")

u.write(b'\x83'); time.sleep(0.5)      # SAFE
read_mode("SAFE(0x83)")

# actuate in SAFE: LED + long beep
led.value(1)
u.write(b'\x8b\x0d\xff\xff')                        # LEDs on
u.write(b'\x8c\x00\x01\x48\x40\x8d\x00')            # define 1-note song (dur 1.0s) + play
print("  >>> SAFE actuation sent (listen for beep, watch Roomba LEDs)")
time.sleep(1.5)
u.write(b'\x8b\x00\x00\x00')                        # LEDs off
led.value(0)

u.write(b'\x84'); time.sleep(0.5)      # FULL
read_mode("FULL(0x84)")

# actuate in FULL
led.value(1)
u.write(b'\x8b\x0d\xff\xff')
u.write(b'\x8c\x00\x01\x48\x40\x8d\x00')
print("  >>> FULL actuation sent (listen for beep)")
time.sleep(1.5)
u.write(b'\x8b\x00\x00\x00')
led.value(0)

print("### DONE - paste output + say if EITHER actuation beeped ###")
