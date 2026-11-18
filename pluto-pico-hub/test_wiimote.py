"""
Unit tests for bridges/wiimote.py -- the Wii Remote session logic (no hardware, no
Bluetooth, no drive service): input-device discovery, how buttons and the aim become
drive events, and the calibration walk-through.

Run from the repo root:
    python3 pluto-pico-hub/test_wiimote.py
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "bridges"))

import wiimote as wm  # noqa: E402

PROC_SAMPLE = """I: Bus=0003 Vendor=1209 Product=2f07 Version=0111
N: Name="OrangeFox86 DreamPicoPort"
H: Handlers=event3 js0

I: Bus=0005 Vendor=057e Product=0330 Version=8001
N: Name="Nintendo Wii Remote Accelerometer"
H: Handlers=event9

I: Bus=0005 Vendor=057e Product=0330 Version=8001
N: Name="Nintendo Wii Remote IR"
H: Handlers=event10

I: Bus=0005 Vendor=057e Product=0330 Version=8001
N: Name="Nintendo Wii Remote"
H: Handlers=kbd event11 js4
"""


def _outline(uv):
    """4 IR dots for a remote aiming at uv in the LED frame (see test_wiimote_aim)."""
    u, v = uv
    w, h = 520.0, 400.0
    ox, oy = 512 - u * w, 384 - v * h
    return [[int(ox), int(oy)], [int(ox + w), int(oy + 10)],
            [int(ox + w - 15), int(oy + h)], [int(ox + 5), int(oy + h - 12)]]


def _ir(dots):
    """The 4 kernel IR slots (1023 = no dot) filled from a list of dots."""
    ir = [[wm.aim.IR_NONE, wm.aim.IR_NONE] for _ in range(4)]
    for i, d in enumerate(dots):
        ir[i] = list(d)
    return ir


class _Bridge(wm.WiimoteBridge):
    """The real bridge with the outside world cut off: every drive POST is recorded."""

    def __init__(self):
        self._tmp = tempfile.mkdtemp()
        wm.CAL_FILE = os.path.join(self._tmp, "cal.json")
        wm.OPT_FILE = os.path.join(self._tmp, "opts.json")      # never the real /var/lib/cpc-hub
        wm.WiimoteBridge.__init__(self, 0, {})
        self.posts = []
        self._sess = {"mapping": "dreamcast", "target": "pi", "dev": "/dev/ttyAMA0", "aim_axis": "MAIN"}
        self._aim_mode = "absolute"     # these tests cover the absolute aim; see RelativeAimTests below

    def _drive(self, body):
        self.posts.append(body)

    def _running(self):
        return True


class DiscoveryTests(unittest.TestCase):
    def test_finds_the_wii_remote_devices_only(self):
        found = wm.find_input_devices(PROC_SAMPLE)
        self.assertEqual(found["Nintendo Wii Remote"], "/dev/input/event11")
        self.assertEqual(found["Nintendo Wii Remote IR"], "/dev/input/event10")
        self.assertNotIn("OrangeFox86 DreamPicoPort", found)

    def test_nothing_connected(self):
        self.assertEqual(wm.find_input_devices("N: Name=\"Other\"\nH: Handlers=event1\n"), {})


class ButtonTests(unittest.TestCase):
    def test_button_becomes_a_hold_with_the_mapping_and_target(self):
        b = _Bridge()
        b._button("B", True)
        b._button("B", False)
        self.assertEqual(b.posts[0], {"action": "hold", "down": True, "key": "B", "source": "wiimote",
                                      "mapping": "dreamcast", "target": "pi", "dev": "/dev/ttyAMA0"})
        self.assertFalse(b.posts[1]["down"])

    def test_kernel_codes_cover_every_button(self):
        self.assertEqual(sorted(wm.KEYS.values()),
                         sorted(["LEFT", "RIGHT", "UP", "DOWN", "PLUS", "MINUS",
                                 "ONE", "TWO", "A", "B", "HOME"]))


class AimTests(unittest.TestCase):
    def test_four_dots_post_an_axis(self):
        b = _Bridge()
        last = b._aim_frame(_ir(_outline((0.5, 0.5))), 0.0)
        self.assertGreater(last, 0.0)
        post = b.posts[0]
        self.assertEqual((post["action"], post["name"]), ("axis", "MAIN"))
        self.assertAlmostEqual(post["x"], 0.5, delta=0.05)
        self.assertAlmostEqual(post["y"], 0.5, delta=0.05)
        self.assertEqual(b._dots, 4)

    def test_fewer_than_four_dots_hold_the_last_aim(self):
        b = _Bridge()
        b._aim_frame(_ir(_outline((0.5, 0.5))), 0.0)
        n = len(b.posts)
        b._aim_frame(_ir(_outline((0.5, 0.5))[:3]), 1.0)
        self.assertEqual(len(b.posts), n)
        self.assertEqual(b._dots, 3)
        self.assertIsNone(b._raw)

    def test_a_still_remote_does_not_spam_the_drive_service(self):
        b = _Bridge()
        ir = _ir(_outline((0.4, 0.6)))
        last = b._aim_frame(ir, 0.0)
        b._aim_frame(ir, last + 1.0)
        self.assertEqual(len(b.posts), 1)

    def test_updates_are_rate_limited(self):
        b = _Bridge()
        last = b._aim_frame(_ir(_outline((0.2, 0.2))), 100.0)
        # a big move, but straight away (same instant as the previous post)
        b._aim_frame(_ir(_outline((0.8, 0.8))), last + 0.0)
        self.assertEqual(len(b.posts), 1)


class CalibrationTests(unittest.TestCase):
    def _walk(self, b, corners):
        b._calibrate_start()
        for uv in corners:
            b._aim_frame(_ir(_outline(uv)), 0.0)
            b._button("B", True)

    def test_walkthrough_then_corners_read_as_picture_corners(self):
        b = _Bridge()
        # the picture's corners as raw LED-frame aims (the LEDs sit outside the picture)
        corners = [(0.07, 0.09), (0.93, 0.08), (0.94, 0.92), (0.06, 0.91)]
        b._calibrate_start()
        self.assertIn("TOP-LEFT", b._cal_message)
        self._walk(b, corners)
        self.assertTrue(b._calib is not None)
        self.assertEqual(b._cal_message, "Calibrated")
        b.posts = []
        b._aim_frame(_ir(_outline(corners[0])), 0.0)
        post = [p for p in b.posts if p.get("action") == "axis"][0]     # the corner is an edge: a reload press rides along
        self.assertAlmostEqual(post["x"], 0.0, delta=0.05)     # picture's left edge
        self.assertAlmostEqual(post["y"], 1.0, delta=0.05)     # picture's top = y up

    def test_b_during_calibration_does_not_fire(self):
        b = _Bridge()
        b._calibrate_start()
        b._aim_frame(_ir(_outline((0.1, 0.1))), 0.0)
        b._button("B", True)
        self.assertEqual([p for p in b.posts if p.get("action") == "hold"], [])

    def test_capture_needs_all_four_dots(self):
        b = _Bridge()
        b._calibrate_start()
        b._button("B", True)                       # no aim seen yet
        self.assertEqual(b._cal["step"], 0)
        self.assertIn("4 dots", b._cal_message)

    def test_calibration_is_saved_and_reloaded(self):
        b = _Bridge()
        self._walk(b, [(0.07, 0.09), (0.93, 0.08), (0.94, 0.92), (0.06, 0.91)])
        again = wm.WiimoteBridge(0, {})
        self.assertEqual(len(again._calib), 9)

    def test_reset_forgets_it(self):
        b = _Bridge()
        self._walk(b, [(0.07, 0.09), (0.93, 0.08), (0.94, 0.92), (0.06, 0.91)])
        b._calibrate_reset()
        self.assertIsNone(b._calib)
        self.assertIsNone(wm.WiimoteBridge(0, {})._calib)


class _RelBridge(_Bridge):
    def __init__(self):
        _Bridge.__init__(self)
        self._aim_mode = "relative"


class RelativeAimTests(unittest.TestCase):
    def test_the_relative_aim_is_the_default(self):
        wm.CAL_FILE = os.path.join(tempfile.mkdtemp(), "cal.json")
        self.assertEqual(wm.WiimoteBridge(0, {})._aim_mode, "relative")

    def test_one_dot_is_enough_and_the_pointer_follows_it(self):
        b = _RelBridge()
        last = b._aim_frame(_ir([(500, 300)]), 0.0)
        first = b.posts[0]
        self.assertEqual((first["x"], first["y"]), (0.5, 0.5))       # starts in the middle
        b._aim_frame(_ir([(440, 300)]), last - 1.0)                     # the dot moves 60 px left
        second = b.posts[1]
        self.assertAlmostEqual(second["x"], 0.5 + 60 / 600.0, places=3)  # the pointer goes right
        self.assertEqual(b._dots, 1)

    def test_a_still_remote_sends_nothing_after_the_first_post(self):
        b = _RelBridge()
        ir = _ir([(500, 300), (700, 300)])
        last = b._aim_frame(ir, 0.0)
        b._aim_frame(ir, last + 1.0)
        b._aim_frame(ir, last + 2.0)
        self.assertEqual(len(b.posts), 1)

    def test_losing_all_dots_keeps_the_pointer_where_it_is(self):
        b = _RelBridge()
        last = b._aim_frame(_ir([(500, 300)]), 0.0)
        b._aim_frame(_ir([(440, 300)]), last - 1.0)
        n = len(b.posts)
        b._aim_frame(_ir([]), last + 2.0)
        self.assertEqual(len(b.posts), n)
        self.assertEqual(b._dots, 0)

    def test_no_calibration_in_relative_mode(self):
        b = _RelBridge()
        with self.assertRaises(RuntimeError):
            b._calibrate_start()

    def test_options_apply_live_and_show_in_the_status(self):
        b = _RelBridge()
        b._set_opts({"sensitivity": 2.0, "invert_x": True})
        self.assertEqual((b._rel.sensitivity, b._rel.invert_x, b._rel.invert_y), (2.0, True, False))
        last = b._aim_frame(_ir([(500, 300)]), 0.0)
        b._aim_frame(_ir([(560, 300)]), last - 1.0)                     # +60 px, inverted x: pointer right
        self.assertAlmostEqual(b.posts[1]["x"], 0.5 + 2 * 60 / 600.0, places=3)

    def test_sensitivity_is_bounded(self):
        b = _RelBridge()
        b._set_opts({"sensitivity": 999})
        self.assertEqual(b._opts["sensitivity"], 10.0)
        b._set_opts({"sensitivity": 0})
        self.assertEqual(b._opts["sensitivity"], 0.1)


if __name__ == "__main__":
    unittest.main()
