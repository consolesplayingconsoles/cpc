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
# The mode is SET EXPLICITLY by the hub -- no TH sniffing (that scheme false-triggered off
# our own CLK toggling and never cleanly handed the lines back). The hub knows the intent
# from which Pluto surface is driving: the chat/network drawer sends datalink events (DATA);
# the Control tab streams controller ops (CONTROLLER). It sends MODE:DATA / MODE:CTRL and the
# pico switches, handing the 6 pins between Python (open-drain) and the PIO (push-pull, fine
# through the BSS138 shifters). Boot default = DATA.
#
# All hub->pico traffic is newline-terminated LINES, so MODE: is understood in either mode.
# Framing the serial costs controller mode nothing: its real-time is entirely in the PIO;
# Python only feeds the PIO a new pattern when a button CHANGES, never per console poll.
#   MODE:DATA / MODE:CTRL  -> switch mode (idempotent; the hub sends it only on a transition)
#   DATA lines:
#     <text>   -> print it on the MD          (opcode 0x01)
#     /g <id>  -> render graphic <id>         (opcode 0x02)
#     /psg     -> audio bring-up test         (opcode 0x03, PSG bytes)
#   CTRL lines:
#     <hex>    -> button mask, e.g. '80' = Start (see BTN_* below), latest-wins
import sys
import select
import time
import rp2
from machine import Pin

# TH / GP2 / DE-9 pin7. In CONTROLLER mode this is the PIO's clock input (the console drives
# it push-pull every frame). It's also sampled for md:on/off liveness. Nothing reads it to
# choose the mode any more -- the hub commands that explicitly.
SELECT = Pin(2, Pin.IN)   # GP2 / DE-9 pin7

# The 6 DE-9 data lines. In DATALINK mode these are Python open-drain outputs (idle HIGH =
# released); in CONTROLLER mode the PIO owns them. Names carry the datalink role; in
# controller mode GP3=Up GP4=Down GP5=Left GP6=Right GP7=B/A GP8=C/Start.
PAYLOAD = [Pin(g, Pin.OPEN_DRAIN, value=1) for g in (3, 4, 5, 6)]
CTRL = Pin(7, Pin.OPEN_DRAIN, value=1)
CLK  = Pin(8, Pin.OPEN_DRAIN, value=1)

# ── health window (ms) ───────────────────────────────────────────────────────────────
ON_WINDOW_MS = 500   # TH seen high within this long -> console is powered (covers a game
                     # that holds TH low for part of each frame; static-low = off). Liveness
                     # only now -- not used to pick the mode.

# ══ DATALINK ═════════════════════════════════════════════════════════════════════════
CTRL_START, CTRL_END = 0x1, 0x2
OP_PRINT, OP_RENDER, OP_PSG = 0x01, 0x02, 0x03
OP_LIST = 0x20                      # Pico -> MD: track names, '\n' separated
REQ_LIST, REQ_PLAY = 0x10, 0x11     # MD -> Pico: the autonomous player's commands
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
    _bus_drive()
    _xfer(True, CTRL_START)
    _byte(opcode)
    for b in data:
        _byte(b)
    _xfer(True, CTRL_END)
    _bus_listen()


# ══ half-duplex: LISTEN for MD-driven frames, DRIVE our replies ════════════════════════
# In data mode the six lines default to LISTEN (inputs, pulled high) so the autonomous
# player ROM can drive command frames back to us. To reply (list / audio / debug text) we
# briefly DRIVE (open-drain) then hand the bus back. The MD and Pico never drive at once:
# the ROM sends a command, flips to input, and waits for our reply.
_rx_clk = 1


def _bus_listen():
    global _rx_clk
    for p in PAYLOAD:
        p.init(Pin.IN, Pin.PULL_UP)
    CTRL.init(Pin.IN, Pin.PULL_UP)
    CLK.init(Pin.IN, Pin.PULL_UP)
    _rx_clk = CLK.value()


def _bus_drive():
    global _clk
    for p in PAYLOAD:
        p.init(Pin.OPEN_DRAIN, value=1)
    CTRL.init(Pin.OPEN_DRAIN, value=1)
    CLK.init(Pin.OPEN_DRAIN, value=1)
    _clk = 1                # match the idle-HIGH line so the first _xfer toggles it LOW =
                            # a clean START edge. Without this the first edge is a coin-flip
                            # (carried-over parity), the ROM misses START, whole frame lost.


def _read_bus():
    return ((CLK.value() << 5) | (CTRL.value() << 4)
            | PAYLOAD[0].value() | (PAYLOAD[1].value() << 1)
            | (PAYLOAD[2].value() << 2) | (PAYLOAD[3].value() << 3))


def _recv_md_frame():
    """We just saw a CLK edge; read this MD-driven frame to END (or a watchdog abort) and
    relay it to the Pi. Idle/stray edges read id=0xF, never a valid START, so they no-op."""
    last = CLK.value()
    started = have_hi = got_op = False
    hi = opcode = 0
    payload = bytearray()
    first = True
    idle = 0
    while True:
        if first:
            first = False
            v = _read_bus()
        else:
            clk = CLK.value()
            if clk == last:
                idle += 1
                if idle > 40000:            # MD went quiet mid-frame -> give up
                    return
                continue
            last = clk
            idle = 0
            v = _read_bus()
        if (v >> 4) & 1:                     # CTRL
            nib = v & 0x0F
            if nib == CTRL_START:
                started = True; have_hi = got_op = False; payload = bytearray()
            elif nib == CTRL_END and started:
                _relay_md(opcode, payload)
                return
        elif started:
            nib = v & 0x0F
            if not have_hi:
                hi = nib; have_hi = True
            else:
                b = (hi << 4) | nib; have_hi = False
                if not got_op:
                    opcode = b; got_op = True
                else:
                    payload.append(b)


def _relay_md(opcode, payload):
    """Forward an MD command to the Pi over USB (the hub answers on the same serial)."""
    if opcode == REQ_LIST:
        print("MD:LIST")
    elif opcode == REQ_PLAY and len(payload) >= 1:
        print("MD:PLAY:%d" % payload[0])


def _md_poll():
    """One idle tick: if the MD drove a CLK edge, receive + relay the whole frame."""
    global _rx_clk
    clk = CLK.value()
    if clk == _rx_clk:
        return
    _recv_md_frame()
    _rx_clk = CLK.value()


def send_list(names_line):
    """Drive an OP_LIST frame (track names, '\\n' separated) to the MD, at speed."""
    payload = names_line.replace("|", "\n").encode()
    _bus_drive()
    _xfer_fast(True, CTRL_START)
    _byte_fast(OP_LIST)
    for b in payload:
        _byte_fast(b)
    _xfer_fast(True, CTRL_END)
    _bus_listen()


# ── SN76489 PSG, step-1 audio bring-up: prove pitched sound comes out of the chip
#    over the datalink before we stream a whole VGM. OP_PSG payload = raw chip bytes,
#    written straight to the PSG port by the ROM. A note is three bytes:
#      tone latch  1 cc 0 dddd   (low 4 bits of the 10-bit period)
#      tone data   0 0 dddddd    (high 6 bits of the period)
#      volume      1 cc 1 vvvv   (attenuation, 0 = loudest, 15 = off)
SN_CLOCK = 3579545


def _psg_period(freq):
    p = round(SN_CLOCK / (32 * freq))
    return 1 if p < 1 else (1023 if p > 1023 else p)


def psg_note(chan, freq, atten=0):
    p = _psg_period(freq)
    send(OP_PSG, bytes([0x80 | (chan << 5) | (p & 0x0F),
                        (p >> 4) & 0x3F,
                        0x80 | (chan << 5) | 0x10 | (atten & 0x0F)]))


def psg_off(chan):
    send(OP_PSG, bytes([0x80 | (chan << 5) | 0x1F]))   # volume = 15 (silent)


def psg_demo():
    for f in (261.63, 293.66, 329.63, 349.23, 392.0, 440.0, 493.88, 523.25):
        psg_note(0, f)                 # a C-major scale on channel 0
        time.sleep_ms(180)
    psg_off(0)
    time.sleep_ms(120)
    psg_note(0, 261.63)                # a 3-channel C-major chord
    psg_note(1, 329.63)
    psg_note(2, 392.0)
    time.sleep_ms(700)
    for c in range(3):
        psg_off(c)


# ── fast path for streaming real music (VGM) ──────────────────────────────────────────
# The demo's send() holds 40ms/transfer for the 60fps ROM. Music needs hundreds of writes/s
# (Green Hill Zone peaks ~345/s), so the ROM has a tight psg_stream() loop and we clock as
# fast as MicroPython will: no sleeps -- setting the 4 data + CTRL pins (~tens of us) is
# itself the settle before CLK toggles, and the ROM polls far tighter than that.
def _xfer_fast(is_ctrl, nib):
    global _clk
    for i in range(4):
        PAYLOAD[i].value((nib >> i) & 1)
    CTRL.value(1 if is_ctrl else 0)
    time.sleep_us(20)          # settle: data stable before the clock edge
    _clk ^= 1
    CLK.value(_clk)
    time.sleep_us(120)         # HOLD data stable AFTER the edge so the ROM reads it before
                               # the next transfer changes the lines (this was the desync)


def _byte_fast(b):
    _xfer_fast(False, (b >> 4) & 0xF)
    _xfer_fast(False, b & 0xF)


def psg_stream():
    """Open one OP_PSG frame (ROM drops into its tight loop) and relay a LIVE stream of PSG
    bytes from the Pi: 2 hex chars = one byte, forwarded immediately; 'X' ends it. The Pi
    paces the bytes to the VGM's own timing, so we just forward + self-clock. A 2s idle
    watchdog closes the frame if the Pi stops mid-stream, so the ROM never wedges."""
    _bus_drive()
    _xfer_fast(True, CTRL_START)
    _byte_fast(OP_PSG)
    si = sys.stdin.buffer
    p = select.poll()
    p.register(sys.stdin, select.POLLIN)
    hexbuf = ""
    while True:
        if not p.poll(2000):
            break
        ch = si.read(1)
        if not ch:
            continue
        c = chr(ch[0])
        if c in "0123456789abcdefABCDEF":
            hexbuf += c
            if len(hexbuf) == 2:
                _byte_fast(int(hexbuf, 16))
                hexbuf = ""
        elif c == "X":
            break
    _xfer_fast(True, CTRL_END)
    _bus_listen()


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
    """Stop the PIO and hand the 6 pins to the datalink. Idle state is LISTEN (inputs), so
    the autonomous player ROM can drive command frames back; a reply DRIVEs then re-listens."""
    global _sm
    if _sm is not None:
        _sm.active(0)
        _sm = None
    _bus_listen()


_mode = "data"   # boot default: Python owns the lines open-drain, so a datalink ROM works
                 # immediately; a game just sees an idle pad until the hub sends MODE:CTRL.


# ══ line dispatch: MODE: switches, everything else is routed by the current mode ═══════
def _dispatch(line):
    global _mode, _btn
    line = line.rstrip("\r\n")
    if not line:
        return
    if line == "MODE:CTRL":
        if _mode != "controller":
            _enter_controller()
            _mode = "controller"
        return
    if line == "MODE:DATA":
        if _mode != "data":
            _enter_datalink()
            _mode = "data"
        return
    if _mode == "controller":
        try:
            _btn = int(line, 16) & 0xFF     # hex button mask, latest-wins
        except ValueError:
            return
        _pio_feed()                         # push the new patterns to the PIO
        return
    # data mode: datalink opcode stream
    if line == "/psgstream":
        psg_stream()                    # live VGM stream follows on stdin (hex, 'X' ends)
    elif line.startswith("/mdlist "):
        send_list(line[8:])             # reply to the ROM's REQ_LIST with the track names
    elif line.startswith("/psg"):
        psg_demo()
    elif line.startswith("/g"):
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


print("datalink pico up: hub-commanded mode (MODE:DATA / MODE:CTRL), boot = DATA")
_stdin = sys.stdin.buffer              # binary read; lines are ASCII either way
_poll = select.poll()
_poll.register(sys.stdin, select.POLLIN)
_buf = b""
_last_high = time.ticks_add(time.ticks_ms(), -ON_WINDOW_MS - 1)   # start reporting 'off'
_bus_listen()                          # data-mode idle = listen for the ROM's command frames
try:
    while True:
        # MD -> Pico: the autonomous player drives REQ_LIST / REQ_PLAY back to us. Poll every
        # spin (non-blocking on USB below) so we never miss the ROM's ~2ms-held CLK edges.
        if _mode == "data":
            _md_poll()

        # Pi -> Pico over USB, non-blocking so the port keeps getting polled.
        if _poll.poll(0):
            ch = _stdin.read(1)
            if ch:
                if ch in (b"\n", b"\r"):
                    if _buf:
                        _dispatch(_buf.decode("utf-8", "replace"))
                        _buf = b""
                else:
                    _buf += ch

        now = time.ticks_ms()
        if SELECT.value():
            _last_high = now
        _push_health(time.ticks_diff(now, _last_high) < ON_WINDOW_MS)
except KeyboardInterrupt:
    _enter_datalink()
    print("datalink stopped")
