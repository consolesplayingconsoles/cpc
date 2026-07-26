# main.py -- CPC DATALINK + CONTROLLER sender (MicroPython). Lives in the hub
# (pluto-pico-hub/firmware/datalink/); propagate.py flashes it to the board bound to
# PICO_<chipid>=role=datalink in the Pi node .env (the "genesis" board, on USB).
#
# ONE firmware, TWO modes on the SAME 6 data lines (GP3-8) + TH (GP2) -- no re-wire:
#
#   DATALINK  -- our homebrew ROM reads the port raw and NEVER toggles TH. Python drives
#                the 6 lines OPEN-DRAIN, self-clocking an opcode stream out (text/graphics).
#   CONTROLLER-- a real game DRIVES TH every frame to read the 3-button matrix. This needs
#                microsecond TH->data response, which interpreted MicroPython CANNOT hit
#                (~18us/GPIO). So controller mode is done in the RP2040's PIO: a hardware
#                state machine mirrors TH onto the data lines in nanoseconds. Python only
#                feeds it the two precomputed line patterns (TH-high / TH-low) per button
#                change; the console-facing timing is entirely PIO's.
#
# The mode is AUTO-DETECTED off TH: TH edges arriving (a game polling) -> CONTROLLER; TH
# static -> DATALINK. Boot Sonic and it's a pad; boot the room ROM and it's the data
# channel. On the switch we hand the 6 pins between Python (open-drain) and PIO (push-pull,
# fine through the BSS138 shifters).
#
# From the Pi over USB-serial, interpreted BY MODE:
#   DATALINK   -- newline-terminated text lines:
#                   <text>   -> print it on the MD          (opcode 0x01)
#                   /g <id>  -> render graphic <id>         (opcode 0x02)
#   CONTROLLER -- ONE raw byte = the whole pad, latest-wins (no framing): the pressed-button
#                 mask (see BTN_* below). Only 3-button (6-button's extra TH pulses later).
import sys
import select
import time
import rp2
from machine import Pin

# TH (console output -> our input / PIO clock / mode tell).
SELECT = Pin(2, Pin.IN)          # GP2 / DE-9 pin7

# The 6 DE-9 data lines. In DATALINK mode these are Python open-drain outputs (idle HIGH =
# released); in CONTROLLER mode the PIO owns them. Names carry the datalink role; in
# controller mode GP3=Up GP4=Down GP5=Left GP6=Right GP7=B/A GP8=C/Start.
PAYLOAD = [Pin(g, Pin.OPEN_DRAIN, value=1) for g in (3, 4, 5, 6)]
CTRL = Pin(7, Pin.OPEN_DRAIN, value=1)
CLK  = Pin(8, Pin.OPEN_DRAIN, value=1)

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


# ══ CONTROLLER (3-button, PIO) ═══════════════════════════════════════════════════════
BTN_UP, BTN_DOWN, BTN_LEFT, BTN_RIGHT = 0x01, 0x02, 0x04, 0x08
BTN_A, BTN_B, BTN_C, BTN_START        = 0x10, 0x20, 0x40, 0x80
_btn = 0


# PIO program: hold the two 6-bit line patterns (X = TH-low, Y = TH-high), then loop
# forever mirroring TH onto the data lines. `jmp pin` reads the state machine's jmp_pin
# (= TH); each iteration is ~3 cycles @ 125MHz (~24ns), so the lines always reflect the
# current TH long before the console samples them. Pattern bit i -> GP(3+i); 1 = released
# (line high), 0 = pressed (line low).
@rp2.asm_pio(out_init=(rp2.PIO.OUT_HIGH,) * 6)
def _mdpad():
    pull()                  # TH-low pattern -> OSR
    mov(x, osr)
    pull()                  # TH-high pattern -> OSR
    mov(y, osr)
    label("poll")
    jmp(pin, "hi")          # TH high?
    mov(pins, x)            # TH low  -> drive TH-low pattern
    jmp("poll")
    label("hi")
    mov(pins, y)            # TH high -> drive TH-high pattern
    jmp("poll")


_sm = None   # the PIO StateMachine while in controller mode; None in datalink mode


def _patterns(b):
    """The two 6-bit line patterns for button mask b (1 = released). TH-high exposes
    L/R + B/C; TH-low forces L/R to 0 (the 3-button detect signature) and exposes A/Start.
    Up/Down are the same in both halves."""
    hi = 0x3F
    if b & BTN_UP:    hi &= ~0x01
    if b & BTN_DOWN:  hi &= ~0x02
    if b & BTN_LEFT:  hi &= ~0x04
    if b & BTN_RIGHT: hi &= ~0x08
    if b & BTN_B:     hi &= ~0x10
    if b & BTN_C:     hi &= ~0x20
    lo = 0x3F & ~0x04 & ~0x08        # GP5/GP6 low = 3-button detect
    if b & BTN_UP:    lo &= ~0x01
    if b & BTN_DOWN:  lo &= ~0x02
    if b & BTN_A:     lo &= ~0x10
    if b & BTN_START: lo &= ~0x20
    return lo, hi


def _pio_feed():
    """Push the current button state's patterns to the running PIO. restart FIRST (send the
    SM back to its two opening pulls), THEN feed lo,hi -- so the pulls consume exactly those
    two words and fall into the drive loop with an empty FIFO. Feeding before the restart
    would leave a trailing pull that stalls the SM. ~us of glitch, invisible vs the frame."""
    lo, hi = _patterns(_btn)
    _sm.restart()
    _sm.put(lo)
    _sm.put(hi)


def _enter_controller():
    """Hand the 6 data pins to the PIO and start mirroring TH."""
    global _sm
    _sm = rp2.StateMachine(0, _mdpad, freq=125_000_000, out_base=Pin(3), jmp_pin=SELECT)
    _sm.active(1)
    _pio_feed()


def _enter_datalink():
    """Stop the PIO and reclaim the 6 pins for Python open-drain (datalink)."""
    global _sm
    if _sm is not None:
        _sm.active(0)
        _sm = None
    for p in PAYLOAD:
        p.init(Pin.OPEN_DRAIN, value=1)
    CTRL.init(Pin.OPEN_DRAIN, value=1)
    CLK.init(Pin.OPEN_DRAIN, value=1)


# TH IRQ: only timestamps edges for mode-detect now -- the PIO does the fast pad driving.
_last_edge = time.ticks_ms()
_mode = "datalink"


def _th_irq(pin):
    global _last_edge
    _last_edge = time.ticks_ms()


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
#    On = TH seen high within ON_WINDOW; off = TH stuck low. ──────────────────────────
_md_on = None


def _push_health(on):
    global _md_on
    if on != _md_on:
        _md_on = on
        print("md:on" if on else "md:off")


print("datalink pico up: datalink + PIO 3-button controller, mode auto-detected off TH")
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
                    _pio_feed()                        # push the new patterns to the PIO
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
        # transition, hand the 6 pins between PIO and Python and drop any half-typed line.
        want = "controller" if time.ticks_diff(now, _last_edge) < CTRL_IDLE_MS else "datalink"
        if want != _mode:
            _mode = want
            if want == "controller":
                _buf = b""
                _enter_controller()
            else:
                _enter_datalink()
except KeyboardInterrupt:
    _enter_datalink()
    print("datalink stopped")
