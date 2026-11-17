"""
Unit tests for bridges/wiimote_aim.py -- the IR dots -> screen position math.

Synthetic camera: a flat screen outline is projected through a known homography into
the camera image, the remote "aims" at a known screen point, and the math must give
that point back. No hardware.

Run from the repo root:
    python3 pluto-pico-hub/test_wiimote_aim.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "bridges"))

import wiimote_aim as aim  # noqa: E402


def _close(test, a, b, tol=1e-6):
    for x, y in zip(a, b):
        test.assertAlmostEqual(x, y, delta=tol)


def _camera_dots(corners_img, order):
    """The 4 corner points in the order the kernel would list them (any order)."""
    return [corners_img[i] for i in order]


class HomographyTests(unittest.TestCase):
    def test_roundtrip(self):
        src = aim.UNIT_SQUARE
        dst = [(300.0, 200.0), (700.0, 240.0), (660.0, 560.0), (330.0, 520.0)]
        h = aim.homography(src, dst)
        for s, d in zip(src, dst):
            _close(self, aim.apply(h, s), d)
        _close(self, aim.apply(aim.invert(h), dst[2]), src[2])

    def test_degenerate_raises(self):
        with self.assertRaises(ValueError):
            aim.homography(aim.UNIT_SQUARE, [(0, 0), (0, 0), (0, 0), (0, 0)])


class OrderingTests(unittest.TestCase):
    def test_any_order_gives_tl_tr_br_bl(self):
        tl, tr, br, bl = (300, 200), (700, 210), (690, 560), (310, 550)
        for order in ([0, 1, 2, 3], [3, 2, 1, 0], [2, 0, 3, 1], [1, 3, 0, 2]):
            pts = _camera_dots([tl, tr, br, bl], order)
            self.assertEqual(aim.order_corners(pts), [tl, tr, br, bl])

    def test_rolled_remote_keeps_cyclic_order(self):
        # The outline rotated 20 degrees: still TL, TR, BR, BL around the ring.
        import math
        c, s = math.cos(math.radians(20)), math.sin(math.radians(20))
        base = [(-200, -150), (200, -150), (200, 150), (-200, 150)]
        rot = [(512 + x * c - y * s, 384 + x * s + y * c) for x, y in base]
        self.assertEqual(aim.order_corners(rot[::-1]), rot)

    def test_needs_four(self):
        with self.assertRaises(ValueError):
            aim.order_corners([(1, 1), (2, 2), (3, 3)])

    def test_valid_dots_drops_the_none_marker(self):
        raw = [(100, 100), (1023, 1023), (200, 300), (1023, 40)]
        self.assertEqual(aim.valid_dots(raw), [(100, 100), (200, 300)])


class AimTests(unittest.TestCase):
    def _outline(self, aim_uv):
        """The outline's 4 image corners for a remote that points at aim_uv in the LED
        frame: a scaled, slightly skewed outline placed so that aim_uv sits at the image
        centre."""
        u, v = aim_uv
        w, h = 520.0, 400.0
        ox = 512 - u * w
        oy = 384 - v * h
        return [(ox, oy), (ox + w, oy + 10), (ox + w - 15, oy + h), (ox + 5, oy + h - 12)]

    def test_centre_of_outline_is_the_image_centre(self):
        dots = [(512 - 260, 384 - 200), (512 + 260, 384 - 200),
                (512 + 260, 384 + 200), (512 - 260, 384 + 200)]
        u, v = aim.raw_aim(dots)
        _close(self, (u, v), (0.5, 0.5), 1e-6)

    def test_aim_moves_the_other_way_in_the_image(self):
        # Outline shifted right in the image = the remote points left of its centre.
        right = [(x + 100, y) for x, y in
                 [(252, 184), (772, 184), (772, 584), (252, 584)]]
        u, _ = aim.raw_aim(right)
        self.assertLess(u, 0.5)

    def test_recovers_known_aim_points(self):
        for uv in [(0.1, 0.2), (0.5, 0.5), (0.9, 0.8)]:
            dots = self._outline(uv)
            got = aim.raw_aim(dots)
            # the outline is mildly skewed, so allow a small tolerance
            _close(self, got, uv, 0.03)


class CalibrationTests(unittest.TestCase):
    def test_corner_samples_map_to_the_unit_square(self):
        # LEDs on the bezel: the picture's corners read as these raw (u, v).
        raw = [(0.06, 0.08), (0.94, 0.07), (0.95, 0.93), (0.05, 0.92)]
        cal = aim.make_calibration(raw)
        for r, want in zip(raw, aim.UNIT_SQUARE):
            _close(self, aim.apply(cal, r), want)

    def test_axis_is_clamped_and_y_is_up(self):
        raw = [(0.06, 0.08), (0.94, 0.07), (0.95, 0.93), (0.05, 0.92)]
        cal = aim.make_calibration(raw)
        # the picture's top-left corner is axis (0, 1): left edge, TOP = y up
        _close(self, aim.to_axis(raw[0], cal), (0.0, 1.0))
        _close(self, aim.to_axis(raw[2], cal), (1.0, 0.0))
        # aiming off the picture clamps
        x, y = aim.to_axis((-0.5, 1.7), cal)
        self.assertEqual((x, y), (0.0, 0.0))

    def test_mirrored_camera_is_absorbed(self):
        # A camera that mirrors left/right: corners recorded as the user aimed at them.
        raw = [(0.94, 0.08), (0.06, 0.07), (0.05, 0.93), (0.95, 0.92)]
        cal = aim.make_calibration(raw)
        _close(self, aim.to_axis(raw[0], cal), (0.0, 1.0))
        _close(self, aim.to_axis(raw[1], cal), (1.0, 1.0))

    def test_uncalibrated_passes_the_raw_aim(self):
        _close(self, aim.to_axis((0.25, 0.25)), (0.25, 0.75))


class RelativePointerTests(unittest.TestCase):
    def test_starts_in_the_middle(self):
        r = aim.RelativePointer()
        self.assertEqual(r.update([None] * 4), (0.5, 0.5))

    def test_dots_moving_left_move_the_pointer_right(self):
        r = aim.RelativePointer()
        r.update([(500, 300), None, None, None])
        x, y = r.update([(440, 300), None, None, None])      # dots 60 px left
        self.assertAlmostEqual(x, 0.5 + 60 / 600.0, places=6)
        self.assertAlmostEqual(y, 0.5, places=6)

    def test_dots_rising_in_the_camera_move_the_pointer_down(self):
        # The camera's y runs up, so dy > 0 is a dot rising in its view = the remote turned down.
        r = aim.RelativePointer()
        r.update([(500, 300), None, None, None])
        x, y = r.update([(500, 360), None, None, None])
        self.assertAlmostEqual(y, 0.5 - 60 / 600.0, places=6)    # pointer down (y is up)
        r2 = aim.RelativePointer()
        r2.update([(500, 300), None, None, None])
        x, y = r2.update([(500, 240), None, None, None])          # dot falls = remote turned up
        self.assertAlmostEqual(y, 0.5 + 60 / 600.0, places=6)    # pointer up

    def test_works_with_any_dots_and_averages_them(self):
        r = aim.RelativePointer()
        r.update([(100, 100), (900, 100), None, (500, 700)])
        x, _ = r.update([(80, 100), None, None, (460, 700)])  # two slots in common: -20 and -40
        self.assertAlmostEqual(x, 0.5 + 30 / 600.0, places=6)

    def test_a_slot_that_jumps_to_another_dot_is_ignored(self):
        r = aim.RelativePointer()
        r.update([(100, 100), (500, 400), None, None])
        x, y = r.update([(700, 100), (480, 400), None, None])  # slot 0 jumped 600 px: ignore it
        self.assertAlmostEqual(x, 0.5 + 20 / 600.0, places=6)

    def test_no_common_dot_means_no_movement(self):
        r = aim.RelativePointer()
        r.update([(100, 100), None, None, None])
        self.assertEqual(r.update([None, (300, 300), None, None]), (0.5, 0.5))

    def test_stops_at_the_edges_like_a_cursor(self):
        r = aim.RelativePointer()
        r.update([(900, 300), None, None, None])
        x, y = r.update([(300, 300), None, None, None])      # a huge move left: clamps (jump > MAX_STEP ignored)
        self.assertEqual((x, y), (0.5, 0.5))
        for px in range(850, 300, -100):
            x, y = r.update([(px, 300), None, None, None])
        self.assertLessEqual(x, 1.0)

    def test_invert_and_sensitivity(self):
        r = aim.RelativePointer(sensitivity=2.0, invert_x=True, invert_y=True)
        r.update([(500, 300), None, None, None])
        x, y = r.update([(560, 340), None, None, None])
        self.assertAlmostEqual(x, 0.5 + 2 * 60 / 600.0, places=6)    # inverted: +dx -> pointer right
        self.assertAlmostEqual(y, 0.5 + 2 * 40 / 600.0, places=6)    # inverted: the pointer goes the other way


if __name__ == "__main__":
    unittest.main()
