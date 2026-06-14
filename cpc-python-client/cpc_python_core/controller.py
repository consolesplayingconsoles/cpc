"""
cpc_python_core/controller.py -- configurable action-trigger -> controller translator.

The generic, console-agnostic CONSUMER half of the vacuum-plays-a-console pipeline.
A declarative MAPPING (the "translation logic", defined per node -- see
pi/mapping.json) binds dreame_events action triggers to controller ops; a SINK
renders those ops to a target. The same events + mapping drive any sink, so the
console/transport is swappable:

    DreameEvents --> translate(event, mapping) --> ops --> Sink --> target
                         (this file)                         |--> DolphinPipeSink  (local now)
                                                             |--> PrintSink        (test/dry-run)
                                                             '--> <Pico HID sink>  (real hardware, later)

translate(event, mapping) is a PURE function (event -> list of ops). Button STATE
lives in the Sink, so the translator is trivially testable. Pure stdlib, 3.6+, ASCII.

## Local Dolphin setup (the "if possible" -> yes)
Dolphin ships a Pipe input backend, no extra deps:
  1. mkfifo "~/Library/Application Support/Dolphin/Pipes/cpc"
  2. Dolphin > Controllers > GameCube Port 1 = Standard Controller > Configure,
     set Device to "Pipe/0/cpc", and bind the buttons/Main-Stick to themselves.
  3. Run the launcher with DolphinPipeSink -> it writes PRESS/RELEASE/SET lines.
Commands accepted by the pipe: PRESS/RELEASE <BTN>, SET <AXIS> <x> <y>, SET <TRIG> <v>.
"""
import os

# Keys that may appear in an op-spec: the action verbs plus their modifiers.
# Used to tell an op-spec ({"pulse":"L","ms":90}) from a value-keyed rule
# ({"left":..,"right":..} / {"cleaning":..}), which has arbitrary value keys.
_OPSPEC_KEYS = frozenset(("press", "release", "pulse", "axis", "release_all", "ms", "from"))


def _is_opspec(rule):
    return isinstance(rule, dict) and bool(rule) and all(k in _OPSPEC_KEYS for k in rule)


def _vector_xy(value):
    """An event value -> (x, y) in Dolphin stick space (0..1, 0.5 = center).

    Accepts a unit vector {dx,dy} (preferred) or {heading} degrees. +dy = up =
    higher Y (Dolphin stick up). Sign calibration, if a real pad reads mirrored,
    is a one-line change here -- intentionally the single choke point."""
    dx = dy = 0.0
    if isinstance(value, dict):
        if "dx" in value and "dy" in value:
            dx, dy = float(value["dx"]), float(value["dy"])
        elif "heading" in value:
            import math
            rad = math.radians(90.0 - float(value["heading"]))
            dx, dy = math.cos(rad), math.sin(rad)
    return (0.5 + 0.5 * dx, 0.5 + 0.5 * dy)


def _spec_to_ops(spec, value):
    """One op-spec dict -> list of concrete ops (filling axis from the value)."""
    ops = []
    if spec.get("release_all"):
        ops.append({"op": "release_all"})
    if "press" in spec:
        ops.append({"op": "press", "btn": spec["press"]})
    if "release" in spec:
        ops.append({"op": "release", "btn": spec["release"]})
    if "pulse" in spec:
        ops.append({"op": "pulse", "btn": spec["pulse"], "ms": int(spec.get("ms", 80))})
    if "axis" in spec:
        x, y = _vector_xy(value)
        ops.append({"op": "axis", "name": spec["axis"], "x": round(x, 3), "y": round(y, 3)})
    return ops


def translate(event, mapping):
    """PURE: an action-trigger event + a mapping -> list of controller ops.

    Unmapped kinds/values yield [] (silently ignored), so a partial mapping is fine.
    """
    rule = (mapping.get("rules") or {}).get(event.get("kind"))
    if rule is None:
        return []
    if not _is_opspec(rule):
        # value-keyed: pick the branch for this event's value (string key).
        val = event.get("value")
        key = val if isinstance(val, str) else None
        rule = rule.get(key) if (isinstance(rule, dict) and key is not None) else None
        if rule is None:
            return []
    if isinstance(rule, list):
        out = []
        for s in rule:
            out.extend(_spec_to_ops(s, event.get("value")))
        return out
    return _spec_to_ops(rule, event.get("value"))


# -- Sinks ---------------------------------------------------------------------

class Sink(object):
    """Renders ops to a target and tracks which buttons are held (for release_all
    and idempotent press/release). Subclass press/release/pulse/axis."""

    def __init__(self):
        self.held = set()

    def apply(self, ops):
        for op in ops:
            k = op["op"]
            if k == "press":
                self.press(op["btn"])
            elif k == "release":
                self.release(op["btn"])
            elif k == "pulse":
                self.pulse(op["btn"], op.get("ms", 80))
            elif k == "axis":
                self.axis(op["name"], op["x"], op["y"])
            elif k == "release_all":
                self.release_all()

    def press(self, btn):
        self.held.add(btn)

    def release(self, btn):
        self.held.discard(btn)

    def pulse(self, btn, ms):       # momentary, no hold
        self.press(btn)
        self.release(btn)

    def axis(self, name, x, y):
        pass

    def release_all(self):
        for b in list(self.held):
            self.release(b)


class PrintSink(Sink):
    """Dry-run sink: prints the exact line each op would send to Dolphin. No
    sleeps -- a pulse prints PRESS then RELEASE. For testing without a console."""

    def press(self, btn):
        super(PrintSink, self).press(btn)
        print("    PRESS %s" % btn)

    def release(self, btn):
        super(PrintSink, self).release(btn)
        print("    RELEASE %s" % btn)

    def axis(self, name, x, y):
        print("    SET %s %.3f %.3f" % (name, x, y))


class DolphinPipeSink(Sink):
    """Writes Dolphin Pipe-input commands to the FIFO. open() blocks until Dolphin
    (the reader) is up with the Pipe controller configured -- start Dolphin first."""

    def __init__(self, path):
        super(DolphinPipeSink, self).__init__()
        self.path = path
        self._f = open(path, "w")

    def _send(self, line):
        self._f.write(line + "\n")
        self._f.flush()

    def press(self, btn):
        super(DolphinPipeSink, self).press(btn)
        self._send("PRESS %s" % btn)

    def release(self, btn):
        super(DolphinPipeSink, self).release(btn)
        self._send("RELEASE %s" % btn)

    def pulse(self, btn, ms):
        import time
        self._send("PRESS %s" % btn)
        time.sleep(max(ms, 0) / 1000.0)
        self._send("RELEASE %s" % btn)

    def axis(self, name, x, y):
        self._send("SET %s %.3f %.3f" % (name, x, y))

    def close(self):
        try:
            self.release_all()
            self._f.close()
        except Exception:
            pass


class KeyboardSink(Sink):
    """Drive any emulator whose controls are mapped to the keyboard, by holding
    real key presses. A Mac-dev transport: when the named-pipe path is flaky but
    keyboard input works, this just sends the keys the game already responds to.

    Analog is quantized to 4/8-way key holds -- there's no true analog over the
    keyboard, but for 'just move' that reads as walking in the heading direction.

    pynput is imported lazily (Mac-dev only), so this module still imports on the
    constrained consoles -- the same lazy-import pattern used for optional deps. Needs
    `pip install pynput`, macOS Accessibility permission for the sending process,
    and the emulator window focused.
    """

    def __init__(self, keyset="arrows", button_keys=None, deadzone=0.18,
                 move_duty=1.0, duty_period=0.5):
        super(KeyboardSink, self).__init__()
        from pynput.keyboard import Controller, Key  # lazy: Mac-dev only
        self._kb = Controller()
        # key NAMES a mapping file can use as strings ("left", "enter", ...)
        self._special = {
            "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right,
            "enter": Key.enter, "return": Key.enter, "space": Key.space,
            "esc": Key.esc, "escape": Key.esc, "tab": Key.tab, "shift": Key.shift,
        }
        sets = {
            "arrows": {"up": "up", "down": "down", "left": "left", "right": "right"},
            "wasd":   {"up": "w", "down": "s", "left": "a", "right": "d"},
        }
        self._dir = {d: self._resolve(k) for d, k in sets.get(keyset, sets["arrows"]).items()}
        self._dead = deadzone
        # op -> key. Default is a 1:1 GC keyboard map; a mapping file's optional
        # "keys" section overrides per game/emulator. Values are single chars or
        # names ("left", "enter") -> resolved to real keys. E.g. GTA2-on-PSX:
        #   {"FWD":"s", "REV":"a", "STEERL":"left", "STEERR":"right"}.
        raw = button_keys or {
            "A": "a", "B": "b", "X": "x", "Y": "y", "Z": "z",
            "START": "enter", "L": "l", "R": "r",
            "D_UP": "5", "D_DOWN": "6", "D_LEFT": "7", "D_RIGHT": "8",
            "FWD": "up", "REV": "down", "STEERL": "left", "STEERR": "right",
        }
        self._button_keys = {op: self._resolve(k) for op, k in raw.items()}
        self._dir_down = set()   # held direction keys
        self._btn_down = set()   # held button keys
        # Movement throttle: the keyboard is binary (full-tilt or nothing), so to
        # move SLOWER than a sprint we duty-cycle the direction keys -- held for
        # duty*period, released for the rest. 1.0 = hold (full speed, no ticker).
        # The CALLER scales this by playback speed, so 1x clock = robot pace
        # ("tiptoe") and the speed multipliers ramp it toward a full sprint.
        self._duty = max(0.0, min(1.0, move_duty))
        self._want_dirs = set()    # direction keys the duty ticker should pulse
        self._ticker = None
        if 0.0 < self._duty < 1.0:
            # `duty_period` is the BURST LENGTH (on_t = period*duty). It must be long
            # enough that a 3D character breaks past its walk->run ramp during a burst
            # -- too short and it stutter-WALKS and feels slow no matter the speed; the
            # speed dial sets the on/off RATIO. Keep each press >= ~1.5 frames @60fps
            # (MIN_ON) so the emulator registers it at low duty, and stretch the OFF
            # time to preserve the ratio.
            MIN_ON = 0.025
            self._on_t = max(MIN_ON, duty_period * self._duty)
            self._off_t = self._on_t * (1.0 - self._duty) / self._duty
            import threading
            self._tick_stop = threading.Event()
            self._ticker = threading.Thread(target=self._duty_loop, daemon=True)
            self._ticker.start()

    def _resolve(self, k):
        """A key name/char -> a pynput key: 'left'/'enter'/... -> special keys; a
        single char (or already-a-key) passes through unchanged."""
        if isinstance(k, str) and k.lower() in self._special:
            return self._special[k.lower()]
        return k

    def axis(self, name, x, y):
        if name != "MAIN":
            return
        want = set()
        if y > 0.5 + self._dead:
            want.add(self._dir["up"])
        elif y < 0.5 - self._dead:
            want.add(self._dir["down"])
        if x > 0.5 + self._dead:
            want.add(self._dir["right"])
        elif x < 0.5 - self._dead:
            want.add(self._dir["left"])
        if self._ticker is not None:
            self._want_dirs = want    # the duty ticker presses/releases these
            return
        for k in want - self._dir_down:
            self._kb.press(k)
        for k in self._dir_down - want:
            self._kb.release(k)
        self._dir_down = want

    def _duty_loop(self):
        """Background ticker: hold the desired direction keys for on_t, release for
        off_t, so movement averages to `duty` of full speed. The OFF period is
        chunked so a direction change or a stop is picked up promptly."""
        import time
        while not self._tick_stop.is_set():
            dirs = set(self._want_dirs)
            if not dirs:
                time.sleep(0.02)
                continue
            for k in dirs:
                self._kb.press(k)
            time.sleep(self._on_t)
            for k in dirs:
                try:
                    self._kb.release(k)
                except Exception:
                    pass
            slept = 0.0
            while (slept < self._off_t and not self._tick_stop.is_set()
                   and set(self._want_dirs) == dirs):
                chunk = min(0.05, self._off_t - slept)
                time.sleep(chunk)
                slept += chunk

    def press(self, btn):
        k = self._button_keys.get(btn)
        if k is not None and k not in self._btn_down:
            self._kb.press(k)
            self._btn_down.add(k)

    def release(self, btn):
        k = self._button_keys.get(btn)
        if k is not None and k in self._btn_down:
            self._kb.release(k)
            self._btn_down.discard(k)

    def pulse(self, btn, ms):
        import time
        k = self._button_keys.get(btn)
        if k is None:
            return
        self._kb.press(k)
        time.sleep(max(ms, 0) / 1000.0)
        self._kb.release(k)

    def release_all(self):
        t = self._ticker
        if t is not None:
            self._tick_stop.set()
            self._want_dirs = set()
            try:
                t.join(timeout=0.3)
            except Exception:
                pass
            self._ticker = None
        for k in list(self._dir_down | self._btn_down) + list(self._dir.values()):
            try:
                self._kb.release(k)
            except Exception:
                pass
        self._dir_down.clear()
        self._btn_down.clear()


def mappings_dir(base=None):
    """The mapping store. Mappings are CONFIG/DATA, not engine code, so they live
    in a root-level `mappings/` dir (the CPC "database"), NOT inside this package.
    Override with the CPC_MAPPINGS env var, or pass an explicit base."""
    if base:
        return base
    return os.environ.get("CPC_MAPPINGS") or os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "mappings"))


def list_mappings(base=None):
    """Sorted stems of the available '<source>-to-<target>.mapping.json' files."""
    try:
        return sorted(f[:-len(".mapping.json")] for f in os.listdir(mappings_dir(base))
                      if f.endswith(".mapping.json"))
    except OSError:
        return []


def load_mapping(name, base=None):
    """Load a mapping by convention name (or a full path) from the mapping store.

    Mappings are pure input=>output config (event source => target controller),
    referenced by the bare stem, e.g. load_mapping('dreame-to-gamecube').
    """
    import json
    if os.path.isfile(name):
        path = name
    else:
        fname = name if name.endswith(".mapping.json") else name + ".mapping.json"
        path = os.path.join(mappings_dir(base), fname)
    with open(path) as f:
        return json.load(f)


def dolphin_pipe_path(name="cpc", base=None):
    """Default Dolphin Pipes FIFO path (macOS). Override base for Linux
    (~/.config/dolphin-emu/Pipes or ~/.local/share/dolphin-emu/Pipes)."""
    if base is None:
        base = os.path.expanduser("~/Library/Application Support/Dolphin/Pipes")
    return os.path.join(base, name)


# -- Driver --------------------------------------------------------------------

def drive(events, mapping, sink, speed=1.0, should_stop=None):
    """Replay an event list through the mapping into a sink, paced by each event's
    `t` (seconds). speed>1 = faster than real time. Releases everything at the end.
    """
    import time
    t0 = None
    start = time.time()
    for e in events:
        if should_stop and should_stop():
            break
        if t0 is None:
            t0 = e.get("t", 0.0)
        target = (e.get("t", 0.0) - t0) / max(speed, 1e-6)
        wait = target - (time.time() - start)
        if wait > 0:
            time.sleep(wait)
        sink.apply(translate(e, mapping))
    sink.release_all()


def sample_ops(events, t, mapping):
    """The controller ops for the state AT time t -- i.e. the latest MOVE at or
    before t, mapped. Lets a driver start (or seek) mid-route with the right stick
    direction already applied instead of a neutral jump. Events are time-ordered."""
    cur = None
    for e in events:
        if e.get("t", 0.0) > t:
            break
        if e.get("kind") == "move":
            cur = e
    return translate(cur, mapping) if cur is not None else []


def drive_from(events, mapping, sink, t0=0.0, speed=1.0, should_stop=None):
    """Like drive(), but starts the clock at offset t0 (seconds): applies the
    state at t0 first, then paces the remaining events from there. This is what a
    UI playback clock calls on play/seek so the output stays in sync with the map.
    """
    import time
    sink.apply(sample_ops(events, t0, mapping))   # initial direction at the offset
    start = time.time()
    for e in events:
        et = e.get("t", 0.0)
        if et < t0:
            continue
        if should_stop and should_stop():
            break
        wait = (et - t0) / max(speed, 1e-6) - (time.time() - start)
        if wait > 0:
            time.sleep(wait)
        sink.apply(translate(e, mapping))
    sink.release_all()
