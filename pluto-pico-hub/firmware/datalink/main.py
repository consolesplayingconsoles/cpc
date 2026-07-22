# main.py -- CPC DATALINK + CONTROLLER sender (MicroPython). Lives in the hub
# (pluto-pico-hub/firmware/datalink/); propagate.py flashes it to the board bound to
# PICO_<chipid>=role=datalink in the Pi node .env (the "genesis" board, on USB).
#
# ONE firmware, TWO modes on the SAME 6 data lines (GP3-8) + TH (GP2) -- no re-wire:
#
#   DATALINK  -- our homebrew ROM reads the port raw and NEVER toggles TH. The pico
#                self-clocks an opcode stream out (text -> NPC bubble, /g -> graphic).
#   CONTROLLER-- a real game DRIVES TH every frame to read the 3-button matrix. The pico
#                presents button state (fed from the Pi) synced to TH, active-low.
#
# The mode is AUTO-DETECTED off TH itself, the same signal we already watch for health:
# TH edges arriving (a game polling) -> CONTROLLER; TH static -> DATALINK. Boot Sonic and
# it's a pad; boot the room ROM and it's the data channel. Zero config, zero extra wire.
# (6-button needs microsecond TH-edge timing -> PIO/C; this is 3-button only, per plan.)
#
# From the Pi over USB-serial, interpreted BY MODE (auto-detected off TH):
#   DATALINK   -- newline-terminated text lines:
#                   <text>   -> print it on the MD          (opcode 0x01)
#                   /g <id>  -> render graphic <id>         (opcode 0x02)
#   CONTROLLER -- ONE raw byte = the whole pad, latest-wins (no framing, no newline): the
#                 current pressed-button mask (see BTN_* below). This is the TAStm32/
#                 TASLink pattern -- the device holds the latest state and the console read
#                 is serviced from it by the TH IRQ, so serial is NEVER in the console's
#                 read path and the byte needs no low-latency framing; the IRQ is the fast
#                 part. (Only 3-button here; 6-button's us-tight select-counting wants PIO/C.)
#
# Bus (open-drain, 1 = released/high, 0 = pressed/low). DATALINK roles: bits0-3 = GP3-GP6
# payload nibble, bit4 = GP7 CTRL flag, bit5 = GP8 CLK (self-clocked). CONTROLLER roles:
# those SAME pins are the DE-9 button lines (GP3=Up GP4=Down GP5=Left GP6=Right GP7=B/A
# GP8=C/Start), multiplexed by TH. A datalink frame is
#   START(CTRL=1,id=1) -> opcode byte -> payload bytes -> END(CTRL=1,id=2)
# with each byte sent as two nibbles, high first.
import sys
import select
import time
from machine import Pin

# The 6 DE-9 data lines + TH. Open-drain outputs idle HIGH (= released / logic 1); the
# console's pull-ups hold them there and we only ever drive LOW. Names carry the datalink
# role; in controller mode GP7/GP8 are the pin6/pin9 button lines (B/A, C/Start).
PAYLOAD = [Pin(g, Pin.OPEN_DRAIN, value=1) for g in (3, 4, 5, 6)]
CTRL = Pin(7, Pin.OPEN_DRAIN, value=1)
CLK  = Pin(8, Pin.OPEN_DRAIN, value=1)
SELECT = Pin(2, Pin.IN)          # GP2 / DE-9 pin7 TH -- console output; our clock/mode tell

# ── mode auto-detect + health windows (ms) ──────────────────────────────────────────
CTRL_IDLE_MS = 150   # no TH edge for this long -> back to datalink (game stopped polling)
ON_WINDOW_MS = 500   # TH seen high within this long -> console is powered (covers a game
                     # that holds TH low for part of each frame; static-low = off)

# ══ DATALINK ═════════════════════════════════════════════════════════════════════════
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


# ══ CONTROLLER (3-button) ════════════════════════════════════════════════════════════
# Pressed-button mask from the Pi (one raw state byte, latest-wins). The Pi's controller
# source maps its own buttons onto these bits; the pico just renders them onto the matrix per TH.
BTN_UP, BTN_DOWN, BTN_LEFT, BTN_RIGHT = 0x01, 0x02, 0x04, 0x08
BTN_A, BTN_B, BTN_C, BTN_START        = 0x10, 0x20, 0x40, 0x80
_btn = 0


def _drive_pad(th):
    """Present the 3-button matrix for the current TH level (active-low). TH high: L/R +
    B/C; TH low: L/R forced 0 (the pad-detect signature) + A/Start. Up/Down are the same
    in both halves. Called from the TH IRQ so it tracks the console's per-frame strobe."""
    b = _btn
    PAYLOAD[0].value(0 if b & BTN_UP else 1)        # GP3 = Up
    PAYLOAD[1].value(0 if b & BTN_DOWN else 1)      # GP4 = Down
    if th:
        PAYLOAD[2].value(0 if b & BTN_LEFT else 1)  # GP5 = Left
        PAYLOAD[3].value(0 if b & BTN_RIGHT else 1) # GP6 = Right
        CTRL.value(0 if b & BTN_B else 1)           # GP7 = B
        CLK.value(0 if b & BTN_C else 1)            # GP8 = C
    else:
        PAYLOAD[2].value(0)                         # GP5 = 0  (3-button detect)
        PAYLOAD[3].value(0)                         # GP6 = 0  (3-button detect)
        CTRL.value(0 if b & BTN_A else 1)           # GP7 = A
        CLK.value(0 if b & BTN_START else 1)        # GP8 = Start


def _release_lines():
    """Let all six data lines float high (released) -- hand the bus back to datalink."""
    for p in PAYLOAD:
        p.value(1)
    CTRL.value(1)
    CLK.value(1)


# ── TH edge IRQ: timestamp for mode-detect, and in controller mode drive the matrix the
#    instant the console flips TH (the read follows within microseconds). ──────────────
_last_edge = time.ticks_ms()
_mode = "datalink"


def _th_irq(pin):
    global _last_edge
    _last_edge = time.ticks_ms()
    if _mode == "controller":
        _drive_pad(pin.value())


SELECT.irq(handler=_th_irq, trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING)


# ══ datalink command handling (data mode only; control bytes are handled in the loop) ══
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


# ── health push: emit md:on/md:off only on a flip so the Pi caches it without polling.
#    On = TH seen high within ON_WINDOW (static-high datalink OR a polling game); off =
#    TH stuck low. ──────────────────────────────────────────────────────────────────
_md_on = None


def _push_health(on):
    global _md_on
    if on != _md_on:
        _md_on = on
        print("md:on" if on else "md:off")


print("datalink pico up: datalink + 3-button controller, mode auto-detected off TH")
_stdin = sys.stdin.buffer              # binary: control masks reach 0x80 (Start), text stays ASCII
_poll = select.poll()
_poll.register(sys.stdin, select.POLLIN)
_buf = b""
_last_high = time.ticks_add(time.ticks_ms(), -ON_WINDOW_MS - 1)   # start reporting 'off'
try:
    while True:
        if _poll.poll(5):
            ch = _stdin.read(1)
            if ch:
                if _mode == "controller":
                    _btn = ch[0]                       # one byte = the whole pad, latest-wins
                    _drive_pad(SELECT.value())         # apply now; the TH IRQ tracks it after
                elif ch in (b"\n", b"\r"):
                    handle(_buf.decode("utf-8", "replace"))
                    _buf = b""
                else:
                    _buf += ch
        else:
            time.sleep_ms(2)               # yield so mpremote can break in

        now = time.ticks_ms()
        if SELECT.value():
            _last_high = now
        _push_health(time.ticks_diff(now, _last_high) < ON_WINDOW_MS)

        # Auto-detect: recent TH edges = a game polling = controller; else datalink. On the
        # transition, take/hand-back the bus (drive the matrix / release the lines) and drop
        # any half-typed datalink line.
        want = "controller" if time.ticks_diff(now, _last_edge) < CTRL_IDLE_MS else "datalink"
        if want != _mode:
            _mode = want
            if want == "controller":
                _buf = b""
                _drive_pad(SELECT.value())
            else:
                _release_lines()
except KeyboardInterrupt:
    print("datalink stopped")
