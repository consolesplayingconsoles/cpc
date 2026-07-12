# Reads the Roomba's REAL state to explain why actuators are dead while serial works.
# Key facts it prints:
#   - OI mode (35): 0 off / 1 passive / 2 safe / 3 full
#   - charging state (21) and charging SOURCES available (34): bit0=internal charger,
#     bit1=home base. If a charger is seen, a 600-series Roomba REFUSES safe/full -> passive.
#   - bumps/wheel-drops (7)
# It also sends Full, then an LED cmd, then RE-READS mode immediately -- to catch a silent
# revert to Passive at the moment of actuation.
from machine import UART, Pin
import time

brc = Pin(2, Pin.OUT); brc.value(1); time.sleep(0.3)
u = UART(0, baudrate=19200, tx=Pin(0), rx=Pin(1), bits=8, parity=None, stop=1)
time.sleep(0.1)
if u.any(): u.read()

def q(pkt):
    if u.any(): u.read()
    u.write(bytes([142, pkt])); time.sleep(0.2)
    d = u.read()
    return d[-1] if d else None

print("### state probe @ 19200 ###")
u.write(b'\x80'); time.sleep(0.3)     # Start
u.write(b'\x84'); time.sleep(0.3)     # Full

MODES = {0:"OFF",1:"PASSIVE",2:"SAFE",3:"FULL",None:"NO-REPLY"}
CHG   = {0:"not charging",1:"reconditioning",2:"full charging",3:"trickle",4:"waiting",5:"fault",None:"?"}

m   = q(35)
chg = q(21)
src = q(34)     # charging sources available
bmp = q(7)      # bumps + wheel drops

print("  OI mode         : %s" % MODES.get(m, m))
print("  charging state  : %s" % CHG.get(chg, chg))
if src is not None:
    print("  charge sources  : 0x%02x  (internal=%d  homebase=%d)  <-- if either 1, Roomba refuses Full" % (src, src & 1, (src >> 1) & 1))
else:
    print("  charge sources  : NO-REPLY")
if bmp is not None:
    print("  bumps/wheeldrop : 0x%02x  (wheeldrop L=%d R=%d)" % (bmp, (bmp>>3)&1, (bmp>>2)&1))

# now actuate and immediately re-check mode for a silent revert
print("  -> sending FULL again + LED, then re-reading mode...")
u.write(b'\x84'); time.sleep(0.2)
u.write(b'\x8b\x00\xff\x80')          # power LED red, mid intensity
m2 = q(35)
print("  OI mode right AFTER LED cmd : %s" % MODES.get(m2, m2))

print("### DONE - paste this whole output ###")
