"""
Unit tests for controller.py -- the pure translation layer.

Run from the repo root:
    python3 -m pytest pluto/api/drive/test_controller.py   (if pytest installed)
    python3 pluto/api/drive/test_controller.py             (stdlib unittest)

No hardware, no network, no filesystem -- pure logic only.
"""
import sys
import os
import math
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import controller


# ── _vector_xy ─────────────────────────────────────────────────────────────────

class TestVectorXY(unittest.TestCase):

    def _close(self, a, b, tol=1e-6):
        self.assertAlmostEqual(a, b, delta=tol, msg="%r != %r" % (a, b))

    def test_dx_dy_center(self):
        x, y = controller._vector_xy({"dx": 0.0, "dy": 0.0})
        self._close(x, 0.5)
        self._close(y, 0.5)

    def test_dx_dy_right(self):
        x, y = controller._vector_xy({"dx": 1.0, "dy": 0.0})
        self._close(x, 1.0)
        self._close(y, 0.5)

    def test_dx_dy_up(self):
        x, y = controller._vector_xy({"dx": 0.0, "dy": 1.0})
        self._close(x, 0.5)
        self._close(y, 1.0)

    def test_heading_north(self):
        # Heading 0 = north = up = +dy
        x, y = controller._vector_xy({"heading": 0.0})
        self._close(x, 0.5)
        self._close(y, 1.0)

    def test_heading_east(self):
        x, y = controller._vector_xy({"heading": 90.0})
        self._close(x, 1.0)
        self._close(y, 0.5)

    def test_heading_south(self):
        x, y = controller._vector_xy({"heading": 180.0})
        self._close(x, 0.5)
        self._close(y, 0.0)

    def test_heading_west(self):
        x, y = controller._vector_xy({"heading": 270.0})
        self._close(x, 0.0)
        self._close(y, 0.5)

    def test_non_dict_returns_center(self):
        x, y = controller._vector_xy("something")
        self.assertEqual(x, 0.5)
        self.assertEqual(y, 0.5)

    def test_missing_keys_returns_center(self):
        x, y = controller._vector_xy({})
        self.assertEqual(x, 0.5)
        self.assertEqual(y, 0.5)


# ── _is_opspec ─────────────────────────────────────────────────────────────────

class TestIsOpspec(unittest.TestCase):

    def test_pulse_is_opspec(self):
        self.assertTrue(controller._is_opspec({"pulse": "A", "ms": 80}))

    def test_press_is_opspec(self):
        self.assertTrue(controller._is_opspec({"press": "B"}))

    def test_axis_is_opspec(self):
        self.assertTrue(controller._is_opspec({"axis": "MAIN"}))

    def test_value_keyed_is_not_opspec(self):
        # A value-keyed rule has arbitrary string keys like "cleaning"
        self.assertFalse(controller._is_opspec({"cleaning": {"pulse": "A"}}))

    def test_empty_is_not_opspec(self):
        self.assertFalse(controller._is_opspec({}))

    def test_non_dict_is_not_opspec(self):
        self.assertFalse(controller._is_opspec("press"))
        self.assertFalse(controller._is_opspec(None))


# ── _spec_to_ops ───────────────────────────────────────────────────────────────

class TestSpecToOps(unittest.TestCase):

    def test_pulse(self):
        ops = controller._spec_to_ops({"pulse": "A", "ms": 100}, None)
        self.assertEqual(ops, [{"op": "pulse", "btn": "A", "ms": 100}])

    def test_pulse_default_ms(self):
        ops = controller._spec_to_ops({"pulse": "B"}, None)
        self.assertEqual(ops[0]["ms"], 80)

    def test_press(self):
        ops = controller._spec_to_ops({"press": "X"}, None)
        self.assertEqual(ops, [{"op": "press", "btn": "X"}])

    def test_release(self):
        ops = controller._spec_to_ops({"release": "X"}, None)
        self.assertEqual(ops, [{"op": "release", "btn": "X"}])

    def test_release_all(self):
        ops = controller._spec_to_ops({"release_all": True}, None)
        self.assertEqual(ops, [{"op": "release_all"}])

    def test_axis_from_dx_dy(self):
        ops = controller._spec_to_ops({"axis": "MAIN"}, {"dx": 1.0, "dy": 0.0})
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["op"], "axis")
        self.assertEqual(ops[0]["name"], "MAIN")
        self.assertAlmostEqual(ops[0]["x"], 1.0, delta=1e-3)
        self.assertAlmostEqual(ops[0]["y"], 0.5, delta=1e-3)

    def test_combined_press_release(self):
        ops = controller._spec_to_ops({"press": "A", "release": "B"}, None)
        self.assertEqual(len(ops), 2)
        kinds = {o["op"] for o in ops}
        self.assertIn("press", kinds)
        self.assertIn("release", kinds)


# ── translate ──────────────────────────────────────────────────────────────────

class TestTranslate(unittest.TestCase):

    MAPPING = {
        "rules": {
            "move": {"axis": "MAIN"},
            "status": {
                "cleaning": {"pulse": "START", "ms": 50},
                "idle":     {"release_all": True},
            },
        }
    }

    def test_unmapped_kind_returns_empty(self):
        ops = controller.translate({"kind": "unknown"}, self.MAPPING)
        self.assertEqual(ops, [])

    def test_move_axis(self):
        ops = controller.translate({"kind": "move", "value": {"dx": 0.0, "dy": 1.0}},
                                   self.MAPPING)
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["op"], "axis")
        self.assertEqual(ops[0]["name"], "MAIN")
        self.assertAlmostEqual(ops[0]["y"], 1.0, delta=1e-3)

    def test_value_keyed_hit(self):
        ops = controller.translate({"kind": "status", "value": "cleaning"}, self.MAPPING)
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["op"], "pulse")
        self.assertEqual(ops[0]["btn"], "START")

    def test_value_keyed_miss(self):
        ops = controller.translate({"kind": "status", "value": "charging"}, self.MAPPING)
        self.assertEqual(ops, [])

    def test_release_all(self):
        ops = controller.translate({"kind": "status", "value": "idle"}, self.MAPPING)
        self.assertEqual(ops, [{"op": "release_all"}])

    def test_no_rules_key(self):
        ops = controller.translate({"kind": "move"}, {})
        self.assertEqual(ops, [])


# ── PrintSink state ─────────────────────────────────────────────────────────────

class TestPrintSink(unittest.TestCase):

    def setUp(self):
        self.sink = controller.PrintSink()

    def test_press_adds_to_held(self):
        self.sink.press("A")
        self.assertIn("A", self.sink.held)

    def test_release_removes_from_held(self):
        self.sink.press("A")
        self.sink.release("A")
        self.assertNotIn("A", self.sink.held)

    def test_release_all_clears_held(self):
        self.sink.press("A")
        self.sink.press("B")
        self.sink.release_all()
        self.assertEqual(self.sink.held, set())

    def test_apply_pulse(self):
        # pulse should not leave the button held
        self.sink.apply([{"op": "pulse", "btn": "A", "ms": 0}])
        self.assertNotIn("A", self.sink.held)

    def test_apply_axis_is_a_noop_on_print_sink(self):
        # PrintSink.axis just prints; no state change expected
        self.sink.apply([{"op": "axis", "name": "MAIN", "x": 0.0, "y": 0.5}])
        self.assertEqual(self.sink.held, set())


if __name__ == "__main__":
    unittest.main()
