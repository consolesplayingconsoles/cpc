"""
Unit tests for bridges/hid.py -- the UART frame builder.

Tests cover the frame math and the bridge state machine without any hardware.
UartLink is stubbed so no serial port is needed.

Run from the repo root:
    python3 -m pytest pluto-pi-hub/test_hid.py
    python3 pluto-pi-hub/test_hid.py
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "bridges"))


# ── Stub UartLink so HidBridge can be instantiated without a real device ───────

class _StubLink(object):
    def __init__(self, device, baud):
        self.device = device
        self.baud = baud
        self.sent = []          # all frames written, in order

    def open(self):  pass
    def close(self): pass
    def send(self, frame):
        self.sent.append(bytes(frame))


# Patch UartLink before importing HidBridge
import bridges.uart as uart_mod
_real_UartLink = uart_mod.UartLink
uart_mod.UartLink = _StubLink

from bridges.hid import HidBridge, _to8, BUTTON_BITS, DPAD_BITS, _STICK_MID


# ── _to8 ────────────────────────────────────────────────────────────────────────

class TestTo8(unittest.TestCase):

    def test_center(self):
        self.assertEqual(_to8(0.5), 128)       # round(0.5*255=127.5) -> 128 (Python banker's rounding)

    def test_min(self):
        self.assertEqual(_to8(0.0), 0)

    def test_max(self):
        self.assertEqual(_to8(1.0), 255)

    def test_clamp_below(self):
        self.assertEqual(_to8(-1.0), 0)

    def test_clamp_above(self):
        self.assertEqual(_to8(2.0), 255)

    def test_three_quarter(self):
        self.assertEqual(_to8(0.75), int(round(0.75 * 255)))


# ── _frame / checksum ──────────────────────────────────────────────────────────

class TestFrame(unittest.TestCase):

    def setUp(self):
        self.link = _StubLink("/dev/null", 115200)
        self.bridge = HidBridge.__new__(HidBridge)
        self.bridge.link = self.link
        self.bridge.repeat = 1
        self.bridge.device = "/dev/null"
        self.bridge.baud = 115200
        self.bridge.dpad = self.bridge.buttons = 0
        self.bridge.lx = self.bridge.ly = self.bridge.rx = self.bridge.ry = _STICK_MID
        self.bridge._open = True

    def _last_frame(self):
        return self.link.sent[-1]

    def test_header_bytes(self):
        self.bridge._send()
        f = self._last_frame()
        self.assertEqual(f[0], 0xAA)
        self.assertEqual(f[1], 0x55)

    def test_frame_length(self):
        self.bridge._send()
        self.assertEqual(len(self._last_frame()), 10)

    def test_neutral_checksum(self):
        self.bridge._send()
        f = self._last_frame()
        dpad, btnL, btnH, lx, ly, rx, ry, xor = f[2], f[3], f[4], f[5], f[6], f[7], f[8], f[9]
        self.assertEqual(xor, dpad ^ btnL ^ btnH ^ lx ^ ly ^ rx ^ ry)

    def test_neutral_sticks_are_mid(self):
        self.bridge._send()
        f = self._last_frame()
        self.assertEqual(f[5], _STICK_MID)   # lx
        self.assertEqual(f[6], _STICK_MID)   # ly
        self.assertEqual(f[7], _STICK_MID)   # rx
        self.assertEqual(f[8], _STICK_MID)   # ry

    def test_checksum_with_dpad(self):
        self.bridge.dpad = 0x01
        self.bridge._send()
        f = self._last_frame()
        xor = f[2] ^ f[3] ^ f[4] ^ f[5] ^ f[6] ^ f[7] ^ f[8]
        self.assertEqual(f[9], xor)

    def test_repeat(self):
        self.bridge.repeat = 3
        self.bridge._send()
        self.assertEqual(len(self.link.sent), 3)

    def test_no_send_when_closed(self):
        self.bridge._open = False
        self.bridge._send()
        self.assertEqual(self.link.sent, [])


# ── HidBridge state machine ─────────────────────────────────────────────────────

class TestHidBridgeState(unittest.TestCase):

    def setUp(self):
        self.link = _StubLink("/dev/null", 115200)
        self.bridge = HidBridge("/dev/null", 115200)
        self.bridge.link = self.link
        self.bridge.start()
        self.link.sent.clear()   # discard the neutral start frame

    def _last_frame(self):
        return self.link.sent[-1]

    # -- dpad ------------------------------------------------------------------

    def test_press_dpad_up(self):
        self.bridge._set("D_UP", True)
        f = self._last_frame()
        self.assertTrue(f[2] & (1 << DPAD_BITS["D_UP"]))

    def test_release_dpad_up(self):
        self.bridge._set("D_UP", True)
        self.bridge._set("D_UP", False)
        f = self._last_frame()
        self.assertFalse(f[2] & (1 << DPAD_BITS["D_UP"]))

    def test_dpad_aliases(self):
        # "UP" and "D_UP" map to the same bit
        self.bridge._set("UP", True)
        f_alias = self._last_frame()
        self.bridge._set("UP", False)
        self.bridge._set("D_UP", True)
        f_canonical = self._last_frame()
        self.assertEqual(f_alias[2], f_canonical[2])

    # -- buttons ---------------------------------------------------------------

    def test_press_button_a(self):
        self.bridge._set("A", True)
        f = self._last_frame()
        self.assertTrue(f[3] & (1 << BUTTON_BITS["A"]))

    def test_press_button_start(self):
        self.bridge._set("START", True)
        f = self._last_frame()
        btnL = f[3]
        btnH = f[4]
        bit = 1 << BUTTON_BITS["START"]
        # START is button 9 (index 8), so it's in btnH
        buttons = btnL | (btnH << 8)
        self.assertTrue(buttons & bit)

    def test_unknown_button_ignored(self):
        before = list(self.link.sent)
        self.bridge._set("NONEXISTENT", True)
        self.assertEqual(self.link.sent, before)   # no new frame

    # -- analog axis -----------------------------------------------------------

    def test_axis_main_left(self):
        # x=0.0 (full left): lx should be 0x00
        self.bridge.axis("MAIN", 0.0, 0.5)
        f = self._last_frame()
        self.assertEqual(f[5], 0)    # lx = 0

    def test_axis_main_right(self):
        self.bridge.axis("MAIN", 1.0, 0.5)
        f = self._last_frame()
        self.assertEqual(f[5], 255)  # lx = 255

    def test_axis_main_up(self):
        # y=1.0 (up in op space) -> by=_to8(1.0-1.0)=0 (DC: 0x00=up)
        self.bridge.axis("MAIN", 0.5, 1.0)
        f = self._last_frame()
        self.assertEqual(f[6], 0)    # ly = 0x00 = up

    def test_axis_main_down(self):
        # y=0.0 (down in op space) -> by=_to8(1.0-0.0)=255 (DC: 0xFF=down)
        self.bridge.axis("MAIN", 0.5, 0.0)
        f = self._last_frame()
        self.assertEqual(f[6], 255)  # ly = 0xFF = down

    def test_axis_center(self):
        self.bridge.axis("MAIN", 0.5, 0.5)
        f = self._last_frame()
        self.assertEqual(f[5], _to8(0.5))    # lx
        self.assertEqual(f[6], _to8(0.5))    # ly

    def test_axis_right_stick(self):
        self.bridge.axis("RIGHT", 0.0, 0.5)
        f = self._last_frame()
        self.assertEqual(f[7], 0)    # rx = 0 (full left on right stick)
        self.assertEqual(f[5], _STICK_MID)   # lx unchanged

    def test_axis_c_stick(self):
        self.bridge.axis("C", 1.0, 0.5)
        f = self._last_frame()
        self.assertEqual(f[7], 255)  # rx = 255

    def test_axis_unknown_name_does_nothing(self):
        before = list(self.link.sent)
        self.bridge.axis("UNKNOWN", 0.0, 0.0)
        self.assertEqual(self.link.sent, before)

    # -- release_all -----------------------------------------------------------

    def test_release_all_neutralises(self):
        self.bridge._set("A", True)
        self.bridge._set("D_UP", True)
        self.bridge.axis("MAIN", 0.0, 0.0)
        self.bridge.release_all()
        f = self._last_frame()
        self.assertEqual(f[2], 0)            # dpad clear
        self.assertEqual(f[3], 0)            # btnL clear
        self.assertEqual(f[5], _STICK_MID)   # lx re-centred
        self.assertEqual(f[6], _STICK_MID)   # ly re-centred

    # -- apply dispatch --------------------------------------------------------

    def test_apply_press_release(self):
        self.bridge.apply([{"op": "press", "btn": "A"}])
        f_press = self._last_frame()
        self.assertTrue(f_press[3] & (1 << BUTTON_BITS["A"]))

        self.bridge.apply([{"op": "release", "btn": "A"}])
        f_release = self._last_frame()
        self.assertFalse(f_release[3] & (1 << BUTTON_BITS["A"]))

    def test_apply_axis(self):
        self.bridge.apply([{"op": "axis", "name": "MAIN", "x": 0.0, "y": 0.5}])
        f = self._last_frame()
        self.assertEqual(f[5], 0)

    def test_apply_unknown_op_ignored(self):
        before = list(self.link.sent)
        self.bridge.apply([{"op": "teleport", "dst": "mars"}])
        self.assertEqual(self.link.sent, before)

    # -- checksum integrity across ops ----------------------------------------

    def test_checksum_after_axis(self):
        self.bridge.axis("MAIN", 0.25, 0.75)
        f = self._last_frame()
        xor = f[2] ^ f[3] ^ f[4] ^ f[5] ^ f[6] ^ f[7] ^ f[8]
        self.assertEqual(f[9], xor, "XOR checksum broken after axis op")

    def test_checksum_after_press(self):
        self.bridge._set("A", True)
        self.bridge._set("D_UP", True)
        f = self._last_frame()
        xor = f[2] ^ f[3] ^ f[4] ^ f[5] ^ f[6] ^ f[7] ^ f[8]
        self.assertEqual(f[9], xor, "XOR checksum broken after button press")


if __name__ == "__main__":
    unittest.main()
