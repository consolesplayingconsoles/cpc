# main.py -- CPC DATALINK sender (MicroPython). Lives in the hub
# (pluto-pico-hub/firmware/datalink/); propagate.py flashes it to the board bound to
# PICO_<chipid>=role=datalink in the Pi node .env (the "genesis" board, on USB).
#
# Role: turn command lines from the Pi into frames on the Mega Drive controller port
# (port 2) via GPIO. The MD ROM (room / datalink receiver) decodes them, e.g. into the
# NPC's dialog bubble. The Pi writes lines to this board's /dev/ttyACM*; we read stdin.
#
# Line protocol from the Pi (one command per line):
#   <text>        -> print it on the MD          (opcode 0x01)
#   /g <id>       -> render graphic <id>          (opcode 0x02)
# (controls/other opcodes come later -- this is a command channel, not just text.)
#
# Bus (open-drain, 1 = released/high, 0 = low): bits0-3 = GP3-GP6 payload nibble,
# bit4 = GP7 CTRL flag, bit5 = GP8 CLK (self-clocked). A frame is
#   START(CTRL=1,id=1) -> opcode byte -> payload bytes -> END(CTRL=1,id=2)
# with each byte sent as two nibbles, high first.
#
# The loop is non-blocking (polls stdin, yields) and catches KeyboardInterrupt so
# mpremote can always break in to re-flash -- no BOOTSEL needed.
import sys
import select
import time
from machine import Pin

PAYLOAD = [Pin(g, Pin.OPEN_DRAIN, value=1) for g in (3, 4, 5, 6)]
CTRL = Pin(7, Pin.OPEN_DRAIN, value=1)
CLK  = Pin(8, Pin.OPEN_DRAIN, value=1)

# SELECT (GP2 / DE-9 pin7) carries the MD's +5V presence through the shifter: its LEVEL
# is high while the console is powered (HV rail live), low when it's off. We watch the
# LEVEL, not edges -- our ROM reads the port raw and never toggles SELECT, so there are
# no edges to see; the level is the honest on/off signal.
SELECT = Pin(2, Pin.IN)

CTRL_START, CTRL_END = 0x1, 0x2
OP_PRINT, OP_RENDER = 0x01, 0x02
_clk = 1


def _xfer(is_ctrl, nib):
    global _clk
    for i in range(4):
        PAYLOAD[i].value((nib >> i) & 1)   # set payload nibble
    CTRL.value(1 if is_ctrl else 0)        # CTRL flag
    time.sleep_ms(5)                       # let the lines settle
    _clk ^= 1                              # toggle CLK last -> "new transfer"
    CLK.value(_clk)
    time.sleep_ms(35)                      # hold so the 60fps ROM catches it


def _byte(b):
    _xfer(False, (b >> 4) & 0xF)
    _xfer(False, b & 0xF)


def send(opcode, data):
    _xfer(True, CTRL_START)
    _byte(opcode)
    for b in data:
        _byte(b)
    _xfer(True, CTRL_END)


_md_on = None   # last REPORTED state; None until the first check emits it

def check_md_state():
    """Emit 'md:on'/'md:off' on the serial only when the console's power flips, so the
    Pi caches the latest without polling. On = SELECT reads HIGH (MD's +5V present)."""
    global _md_on
    on = bool(SELECT.value())
    if on != _md_on:
        _md_on = on
        print("md:on" if on else "md:off")


def handle(line):
    line = line.rstrip("\r\n")
    if not line:
        return
    if line.startswith("/g"):
        try:
            gid = int(line[2:].strip() or "0")
        except ValueError:
            return
        send(OP_RENDER, bytes([gid & 0xFF]))
    else:
        send(OP_PRINT, line.encode())


print("datalink pico up: reading commands from the Pi over USB-serial")
_poll = select.poll()
_poll.register(sys.stdin, select.POLLIN)
_buf = ""
try:
    while True:
        if _poll.poll(10):
            c = sys.stdin.read(1)
            if c in ("\n", "\r"):
                handle(_buf)
                _buf = ""
            elif c:
                _buf += c
        else:
            time.sleep_ms(2)               # yield so mpremote can break in
        check_md_state()                   # push md:on/off when the console flips
except KeyboardInterrupt:
    print("datalink stopped")
