# Actuation probe @ 19200. Mode changes already proven to register, so TX reaches the
# Roomba. This isolates LED + SONG with UNAMBIGUOUS signals:
#   - Clean ring forced GREEN (3s) then RED (3s) -- if the LED cmd works you CANNOT miss it
#   - your EXACT original 4-note song, with a gap between define and play
# Re-reads OI mode around actuation so we confirm we're really in FULL the whole time.
from machine import UART, Pin
import time

brc = Pin(2, Pin.OUT); brc.value(1); time.sleep(0.3)
u = UART(0, baudrate=19200, tx=Pin(0), rx=Pin(1), bits=8, parity=None, stop=1)
time.sleep(0.1)
if u.any(): u.read()

def mode(tag):
    if u.any(): u.read()
    u.write(bytes([142, 35])); time.sleep(0.2)
    d = u.read()
    print("  mode @ %s = %s" % (tag, (d[-1] if d else "NO REPLY")))

print("### actuation probe @ 19200 ###")
u.write(b'\x80'); time.sleep(0.3)     # Start
u.write(b'\x84'); time.sleep(0.3)     # Full
mode("after FULL")

print(">>> Clean ring should turn GREEN now (3s)")
u.write(b'\x8b\x00\x00\xff')          # power LED: color=0 (green), intensity=255
time.sleep(3.0)
mode("during green")

print(">>> Clean ring should turn RED now (3s)")
u.write(b'\x8b\x00\xff\xff')          # power LED: color=255 (red), intensity=255
time.sleep(3.0)

print(">>> LEDs off + play your original 4-note song")
u.write(b'\x8b\x00\x00\x00')          # LEDs off
u.write(b'\x8c\x00\x04\x43\x10\x45\x10\x47\x10\x48\x20')   # define song0 (4 notes)
time.sleep(0.1)                        # gap between define and play
u.write(b'\x8d\x00')                   # play song0
time.sleep(2.0)
mode("after song")

print("### DONE - report: 1) did the ring turn GREEN then RED?  2) did the song play? ###")
