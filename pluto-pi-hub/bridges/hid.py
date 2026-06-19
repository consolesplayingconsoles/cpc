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
    0xAA 0x55  <dpad>  <btnL>  <btnH>  <xor>
      dpad : bit0 UP, bit1 DOWN, bit2 LEFT, bit3 RIGHT
      btnL : buttons B1..B8  (bit = button index - 1)
      btnH : buttons B9..B16
      xor  : dpad ^ btnL ^ btnH   (the firmware rejects a bad checksum)
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
_AXIS_DEADZONE = 0.30                      # quantise an analog axis onto the d-pad


class HidBridge(object):
    name = "hid"

    def __init__(self, cfg, repeat=2):
        self.cfg = cfg or {}
        self.link = UartLink(self.cfg.get("UART_DEVICE", "/dev/ttyAMA0"),
                             int(self.cfg.get("UART_BAUD", "115200")))
        self.repeat = repeat               # frames per change; link's solid, >1 = belt+braces
        self.dpad = 0
        self.buttons = 0
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
                "device": self.cfg.get("UART_DEVICE", "/dev/ttyAMA0"),
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
        """Analog axis -> d-pad (the firmware is digital for now). 0..1, 0.5=center,
        +y = up. This is what turns a vacuum's heading into a direction."""
        if name not in ("MAIN", None):
            return
        self.dpad &= ~0x0F
        if y > 0.5 + _AXIS_DEADZONE:   self.dpad |= 1 << 0      # up
        elif y < 0.5 - _AXIS_DEADZONE: self.dpad |= 1 << 1      # down
        if x > 0.5 + _AXIS_DEADZONE:   self.dpad |= 1 << 3      # right
        elif x < 0.5 - _AXIS_DEADZONE: self.dpad |= 1 << 2      # left
        self._send()

    def release_all(self):
        self.dpad = self.buttons = 0
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

    def _frame(self, dpad, btnL, btnH):
        return bytes((0xAA, 0x55, dpad, btnL, btnH, dpad ^ btnL ^ btnH))

    def _send(self):
        if not self._open:
            return
        frame = self._frame(self.dpad & 0x0F, self.buttons & 0xFF, (self.buttons >> 8) & 0xFF)
        for _ in range(self.repeat):
            self.link.send(frame)

    def reboot_to_bootsel(self):
        """Reset the Pico to BOOTSEL over the wire (for remote reflash)."""
        if self._open:
            self.link.send(self._frame(0xFF, 0x01, 0x00))


# Standalone smoke test, so a deploy is verifiable on the bench:
#   python3 -m bridges.hid ../pi/.env       (DOWN x3, UP x3, A)
if __name__ == "__main__":
    import os
    import sys
    env = {}
    p = sys.argv[1] if len(sys.argv) > 1 else ""
    if p and os.path.exists(p):
        for ln in open(p):
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                key, _, val = ln.partition("=")
                env[key.strip()] = val.strip()
    bridge = HidBridge(env).start()
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
