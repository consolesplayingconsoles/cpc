"""
bridges/hid.py -- the Pi-side gamepad bridge: controller ops -> GP2040 UART frames.

The Pi drives a Pico running GP2040-CE (gp2040-ce.info), which presents itself as a
PS3/DualShock USB gamepad -- target-agnostic: anything that accepts a PS3 pad takes
it (a Maple adapter into a Dreamcast, a licensed PS5 upgrader, a PC, a real PS3).
GP2040 normally reads physical buttons; our custom UartInput addon (firmware/<role>/)
makes it read THIS UART instead. This bridge is the Pi-side half: it consumes the
same abstract ops the server's pluto/api/drive/controller.py emits
(press/release/pulse/axis/release_all) and renders each into GP2040's frame.

Wire frame (must match the UartInput addon):
    0xAA 0x55  <dpad>  <btnL>  <btnH>  <lx> <ly> <rx> <ry>  <xor>
      dpad : bit0 UP, bit1 DOWN, bit2 LEFT, bit3 RIGHT
      btnL : buttons B1..B8  (bit = button index - 1)
      btnH : buttons B9..B16
      lx ly: LEFT stick  (8-bit, 0x80 = center); rx ry: RIGHT stick
      xor  : dpad ^ btnL ^ btnH ^ lx ^ ly ^ rx ^ ry   (firmware rejects a bad checksum)
A control frame (dpad=0xFF, btnL=0x01) asks the firmware to reboot to BOOTSEL, so
the hub can reflash over the same wire with no physical button.

Button STATE is held here (like controller.py's Sink) so the same op stream drives
either target. Pure stdlib, 3.6-safe, ASCII -- runs on the Pi unchanged.
"""
import time

try:
    from .uart import UartLink
except ImportError:                       # when run as a plain script
    from uart import UartLink

# Abstract op button -> GP2040 button bit (index - 1). Proven on the real
# Dreamcast: B1(bit0) = DualShock Cross = DC 'A'; the rest follow the DS3 order the
# Maple adapter maps to the DC. A per-target override can move to a mapping later.
BUTTON_BITS = {"A": 0, "B": 1, "X": 2, "Y": 3, "L": 4, "R": 5, "Z": 7,
               "SELECT": 8, "START": 9}
DPAD_BITS = {"D_UP": 0, "D_DOWN": 1, "D_LEFT": 2, "D_RIGHT": 3,
             "UP": 0, "DOWN": 1, "LEFT": 2, "RIGHT": 3}
_STICK_MID = 0x80                          # 8-bit stick center (0x80 << 8 ~ GAMEPAD_JOYSTICK_MID)


def _to8(v):
    """A 0..1 axis value -> an 8-bit stick byte (0..255), clamped."""
    return max(0, min(255, int(round(v * 255.0))))


class HidBridge(object):
    name = "hid"

    def __init__(self, device="/dev/ttyAMA0", baud=115200, repeat=2):
        # device + baud are per-board (a UART is one TX/RX pin set = one Pico), passed
        # in from that Pico's .env line -- not a node-global.
        self.device = device
        self.baud = int(baud)
        self.link = UartLink(device, self.baud)
        self.repeat = repeat               # frames per change; link's solid, >1 = belt+braces
        self.dpad = 0
        self.buttons = 0
        self.lx = self.ly = self.rx = self.ry = _STICK_MID
        self._open = False

    # -- lifecycle (the hub supervises this) ----------------------------------
    def start(self):
        self.link.open()
        self._open = True
        self._send()                       # neutral: a known starting state
        return self

    def stop(self):
        if self._open:
            self.release_all()
            self.link.close()
            self._open = False

    def status(self):
        return {"name": self.name, "active": self._open,
                "device": self.device,
                "dpad": self.dpad, "buttons": self.buttons}

    # -- op application (same shape as controller.py's Sink) ------------------
    def apply(self, ops):
        for op in ops:
            k = op.get("op")
            if k == "press":
                self._set(op["btn"], True)
            elif k == "release":
                self._set(op["btn"], False)
            elif k == "pulse":
                self.pulse(op["btn"], op.get("ms", 80))
            elif k == "axis":
                self.axis(op.get("name"), op.get("x", 0.5), op.get("y", 0.5))
            elif k == "release_all":
                self.release_all()

    def pulse(self, btn, ms=80):
        self._set(btn, True)
        time.sleep(max(ms, 0) / 1000.0)
        self._set(btn, False)

    def axis(self, name, x, y):
        """Analog axis -> the real GP2040 stick. Op space is 0..1 (0.5=center,
        +x = right, +y = up). The stick byte is 0x80=center; on the DC the Y byte
        is inverted (0x00 = up), so flip y here -- proven on the date BIOS sweep.
        name MAIN/None/LEFT -> left stick; RIGHT or C (the GameCube C-stick) ->
        right stick. (The C-stick's Y sign is unverified -- calibrate it on the GC
        the same way the DC MAIN stick was proven on the date BIOS.)"""
        bx, by = _to8(x), _to8(1.0 - y)        # op +y=up -> 0x00=up on the stick
        if name in ("MAIN", None, "LEFT", "L"):
            self.lx, self.ly = bx, by
        elif name in ("RIGHT", "R", "C"):
            self.rx, self.ry = bx, by
        else:
            return
        self._send()

    def release_all(self):
        self.dpad = self.buttons = 0
        self.lx = self.ly = self.rx = self.ry = _STICK_MID
        self._send()

    # -- encoding / wire ------------------------------------------------------
    def _set(self, btn, down):
        if btn in DPAD_BITS:
            bit = 1 << DPAD_BITS[btn]
            self.dpad = (self.dpad | bit) if down else (self.dpad & ~bit)
        elif btn in BUTTON_BITS:
            bit = 1 << BUTTON_BITS[btn]
            self.buttons = (self.buttons | bit) if down else (self.buttons & ~bit)
        else:
            return                         # unmapped: ignore (a partial map is fine)
        self._send()

    def _frame(self, dpad, btnL, btnH, lx=_STICK_MID, ly=_STICK_MID, rx=_STICK_MID, ry=_STICK_MID):
        xor = dpad ^ btnL ^ btnH ^ lx ^ ly ^ rx ^ ry
        return bytes((0xAA, 0x55, dpad, btnL, btnH, lx, ly, rx, ry, xor))

    def _send(self):
        if not self._open:
            return
        frame = self._frame(self.dpad & 0x0F, self.buttons & 0xFF, (self.buttons >> 8) & 0xFF,
                            self.lx & 0xFF, self.ly & 0xFF, self.rx & 0xFF, self.ry & 0xFF)
        for _ in range(self.repeat):
            self.link.send(frame)

    def reboot_to_bootsel(self):
        """Reset the Pico to BOOTSEL over the wire (for remote reflash)."""
        if self._open:
            self.link.send(self._frame(0xFF, 0x01, 0x00))


# Standalone smoke test, so a deploy is verifiable on the bench:
#   python3 -m bridges.hid ../pi/.env       (DOWN x3, UP x3, A)
if __name__ == "__main__":
    import sys
    device = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyAMA0"
    baud   = sys.argv[2] if len(sys.argv) > 2 else "115200"
    bridge = HidBridge(device, baud).start()
    print("hid bridge: %s" % bridge.status())
    seq = ([{"op": "pulse", "btn": "D_DOWN", "ms": 200}] * 3
           + [{"op": "pulse", "btn": "D_UP", "ms": 200}] * 3
           + [{"op": "pulse", "btn": "A", "ms": 200}])
    for one in seq:
        print("  %s" % one)
        bridge.apply([one])
        time.sleep(0.4)
    bridge.stop()
    print("done.")
