"""
wiimote.py -- Wii Remote bridge: the Bluetooth link, then the remote as a Control source.

A Wii Remote connects to the Pi over Bluetooth (BlueZ + the kernel hid-wiimote
driver, which turns it into evdev input devices: buttons, accelerometer, and the IR
camera's dots). Two jobs live here:

  1. THE LINK: find a remote in pairing mode (1+2, or the red Sync button), connect and
     trust it, and report which remotes are connected and their battery.
  2. THE SESSION (translation layer): read the remote's buttons and IR dots from the
     evdev devices and forward them to the LOCAL drive service (pluto-drive on :7702),
     exactly like the Nokia bridge: buttons as `hold` (the mapping file names what each
     button means), the AIM as an `axis` (the 4 IR dots worked out into a screen
     position, see wiimote_aim.py). The mapping + sink routing live in pluto-drive.

On-demand + self-reaping, mirroring the Kinect/Nokia bridges: Pluto's WiimoteControl
talks to the HTTP endpoint; a watchdog ends a session that stops pinging. Runs inside
the hub process (root, under cpc-hub.service) so it can drive bluetoothctl and read
/dev/input/event*.

  GET  /engine -> {"ok", "pairing", "message", "wiimotes": [{addr, name, battery}],
                   "session", "dots", "aim", "calibrated", "cal_step", "cal_message"}
  POST /engine {action:"pair"}                        start a scan, connect the first remote seen
  POST /engine {action:"stop"}                        cancel a running pairing scan
  POST /engine {action:"disconnect"}                  disconnect every connected remote
  POST /engine {action:"session_start", mapping, target, dev, aim_axis, aim_mode, sensitivity,
                invert_x, invert_y}              aim_mode "relative" (default) or "absolute"
  POST /engine {action:"aim_options", sensitivity, invert_x, invert_y, edge_reload}
                                                   live, no restart, saved on the Pi
  POST /engine {action:"session_stop"}
  POST /engine {action:"ping"}                        keeps a session alive
  POST /engine {action:"calibrate"}                   aim at the picture's 4 corners, B at each
  POST /engine {action:"calibrate_reset"}             forget the calibration

Config (node .env): WIIMOTE_ENGINE_PORT (enables the bridge).
"""
import glob
import json
import os
import re
import select
import struct
import subprocess
import threading
import time
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    from bridges import wiimote_aim as aim
except ImportError:                       # run from inside bridges/ (the unit tests)
    import wiimote_aim as aim

SCAN_S = 40              # how long a pairing scan runs (the remote stays discoverable ~20 s per press)
RETRY_S = 3              # do not retry connecting to the same address more often than this
CONNECT_TIMEOUT_S = 12

WATCHDOG_S = 45          # reap a session that stops pinging (tab closed / asleep)
DRIVE_URL = "http://127.0.0.1:7702/control/drive"   # the node's local drive service
CAL_FILE = "/var/lib/cpc-hub/wiimote_calibration.json"
OPT_FILE = "/var/lib/cpc-hub/wiimote_options.json"      # speed / invert / edge reload, kept across hub restarts
EDGE_COOLDOWN_S = 0.6        # two edge reloads are at least this far apart
EDGE_REARM = 0.05            # the pointer has to leave the edge by this much (0..1) before it can reload again
DEFAULT_OPTS = {"sensitivity": 1.0, "invert_x": False, "invert_y": False, "edge_reload": True}
AIM_MIN_INTERVAL_S = 1.0 / 30.0     # at most ~30 aim updates a second to the drive service
AIM_MIN_DELTA = 0.002               # ... and only when the aim moved this much (0..1)

# Linux input event codes (include/uapi/linux/input-event-codes.h) and the Wiimote
# button each one is (drivers/hid/hid-wiimote-modules.c, wiimod_keys_map).
EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
ABS_HAT0X = 0x10                    # IR dot n: ABS_HAT<n>X, ABS_HAT<n>Y (n = 0..3)
KEYS = {
    105: "LEFT", 106: "RIGHT", 103: "UP", 108: "DOWN",
    0x197: "PLUS", 0x19c: "MINUS", 0x101: "ONE", 0x102: "TWO",
    0x130: "A", 0x131: "B", 0x13c: "HOME",
}
_EVT = struct.Struct("llHHi")       # struct input_event on 64-bit Linux: timeval + type + code + value
NAME_BUTTONS = "Nintendo Wii Remote"
NAME_IR = "Nintendo Wii Remote IR"

CORNER_NAMES = ["TOP-LEFT", "TOP-RIGHT", "BOTTOM-RIGHT", "BOTTOM-LEFT"]

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_DEV = re.compile(r"^Device\s+((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})\s*(.*)$")


def parse_devices(text):
    """bluetoothctl `devices` output -> [(addr, name)]. Unnamed devices come back with
    the address as the name (BlueZ does that), so the caller filters on the name."""
    out = []
    for line in _ANSI.sub("", text or "").splitlines():
        m = _DEV.match(line.strip())
        if m:
            out.append((m.group(1).upper(), m.group(2).strip()))
    return out


def is_wiimote(name):
    """Every Wii Remote family device names itself 'Nintendo RVL-...' (RVL-CNT-01 is the
    Wii Remote, -TR the Plus, -UC the Wii U Pro controller)."""
    return (name or "").lower().startswith("nintendo rvl")


def find_input_devices(text=None):
    """/proc/bus/input/devices -> {input device name: /dev/input/eventN} for the Wii
    Remote's devices. With two remotes the names repeat; the first one wins."""
    if text is None:
        try:
            with open("/proc/bus/input/devices") as f:
                text = f.read()
        except OSError:
            return {}
    out = {}
    for block in text.split("\n\n"):
        nm = re.search(r'N: Name="([^"]*)"', block)
        ev = re.search(r"H: Handlers=.*?\b(event\d+)", block)
        if nm and ev and nm.group(1).startswith("Nintendo Wii Remote"):
            out.setdefault(nm.group(1), "/dev/input/" + ev.group(1))
    return out


def _btctl(*args, **kw):
    timeout = kw.get("timeout", 8)
    try:
        res = subprocess.run(["bluetoothctl"] + list(args), stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, timeout=timeout,
                             universal_newlines=True)
        return _ANSI.sub("", res.stdout or "")
    except Exception:
        return ""


def _battery(addr):
    """hid-wiimote exposes the remote's battery as a power_supply named
    wiimote_battery_<address>. Percent, or None if it is not exposed (yet)."""
    for path in glob.glob("/sys/class/power_supply/wiimote_battery_*"):
        if os.path.basename(path).lower().endswith(addr.lower()):
            try:
                with open(os.path.join(path, "capacity")) as f:
                    return int(f.read().strip())
            except Exception:
                return None
    return None


class WiimoteBridge:
    def __init__(self, port, cfg):
        self.port = port
        self._lock = threading.Lock()
        # pairing
        self._state = {"pairing": False, "message": ""}
        self._cancel = threading.Event()
        self._scan = None            # the running `bluetoothctl scan on` process
        self._thread = None
        # session
        self._sess = {}              # {mapping, target, dev, aim_axis} of the active session
        self._reader = None
        self._stop = threading.Event()
        self._last_ping = 0.0
        self._dots = 0               # valid IR dots in the latest frame
        self._raw = None             # latest raw (u, v) aim, only with all 4 dots in view
        self._raw_t = 0.0            # when _raw was last updated
        self._aim = None             # latest drive axis (x, y)
        self._drive_ok = True
        self._calib = self._load_cal()      # the 3x3 homography, or None
        self._cal = None             # {"step": 0..3, "samples": []} while calibrating
        self._cal_message = ""
        # How the aim is worked out. "relative" (the default) is an optical mouse made of the
        # IR dots: the pointer follows how the dots MOVE, with any 1..4 of them in view and no
        # calibration. "absolute" needs all 4 dots and the corner calibration (see wiimote_aim).
        self._aim_mode = "relative"
        self._opts = self._load_opts()
        self._rel = aim.RelativePointer()
        self._apply_opts()
        self._edge_armed = True
        self._last_reload = 0.0

    # -- lifecycle ------------------------------------------------------------
    def start(self):
        if not os.path.exists("/usr/bin/bluetoothctl"):
            print("  [wiimote] bluetoothctl missing -- bridge disabled")
            return False
        srv = HTTPServer(("0.0.0.0", self.port), self._make_handler())
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        threading.Thread(target=self._watchdog, daemon=True).start()
        threading.Thread(target=self._keepalive_loop, daemon=True).start()
        return True

    def _set(self, **kw):
        with self._lock:
            self._state.update(kw)

    # -- pairing --------------------------------------------------------------
    def _pair(self):
        with self._lock:
            if self._state["pairing"]:
                return
            self._state.update(pairing=True,
                               message="Press 1+2 (or the red Sync button) on the Wii Remote now")
        self._cancel.clear()
        self._thread = threading.Thread(target=self._pair_loop, daemon=True)
        self._thread.start()

    def _pair_loop(self):
        deadline = time.time() + SCAN_S
        connected = False
        try:
            _btctl("power", "on")
            self._scan = subprocess.Popen(
                ["bluetoothctl", "--timeout", str(SCAN_S), "scan", "on"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            tried = {}
            while time.time() < deadline and not self._cancel.is_set():
                for addr, name in parse_devices(_btctl("devices")):
                    if not is_wiimote(name) or time.time() - tried.get(addr, 0) < RETRY_S:
                        continue
                    tried[addr] = time.time()
                    self._set(message="Found %s (%s), connecting" % (name, addr))
                    _btctl("trust", addr)
                    out = _btctl("connect", addr, timeout=CONNECT_TIMEOUT_S)
                    if "Connection successful" in out:
                        self._set(message="Connected: %s" % addr)
                        connected = True
                        return
                time.sleep(1)
            if not self._cancel.is_set():
                self._set(message="No Wii Remote found. Press 1+2 and try again.")
        finally:
            self._end_scan()
            self._set(pairing=False)
            if self._cancel.is_set() and not connected:
                self._set(message="Pairing cancelled")

    def _end_scan(self):
        s = self._scan
        self._scan = None
        if s is not None:
            try:
                s.terminate()
                s.wait(3)
            except Exception:
                pass
        _btctl("scan", "off")

    def _stop_pairing(self):
        self._cancel.set()

    def _connected(self):
        out = []
        for addr, name in parse_devices(_btctl("devices", "Connected")):
            if is_wiimote(name):
                out.append({"addr": addr, "name": name, "battery": _battery(addr)})
        return out

    def _disconnect(self):
        self._stop_session()
        for w in self._connected():
            _btctl("disconnect", w["addr"])
        self._set(message="Disconnected")

    # -- calibration storage --------------------------------------------------
    def _load_cal(self):
        try:
            with open(CAL_FILE) as f:
                h = json.load(f).get("homography")
            if isinstance(h, list) and len(h) == 9:
                return [float(v) for v in h]
        except Exception:
            pass
        return None

    def _save_cal(self):
        try:
            os.makedirs(os.path.dirname(CAL_FILE), exist_ok=True)
            with open(CAL_FILE, "w") as f:
                json.dump({"homography": self._calib}, f)
        except Exception as exc:
            print("  [wiimote] could not save the calibration: %s" % exc)

    def _calibrate_start(self):
        if not self._running():
            raise RuntimeError("start the session first")
        if self._aim_mode != "absolute":
            raise RuntimeError("the relative aim needs no calibration")
        self._cal = {"step": 0, "samples": []}
        self._cal_message = "Aim at the %s corner of the picture and press B" % CORNER_NAMES[0]

    def _calibrate_reset(self):
        self._calib = None
        self._cal = None
        self._cal_message = "Calibration cleared"
        try:
            os.remove(CAL_FILE)
        except OSError:
            pass

    def _cal_capture(self):
        """B pressed while calibrating: take the current raw aim as this corner."""
        cal = self._cal
        if cal is None:
            return
        if self._raw is None or time.time() - self._raw_t > 0.5:
            self._cal_message = "Not all 4 dots in view. Aim again and press B"
            return
        cal["samples"].append(self._raw)
        cal["step"] += 1
        if cal["step"] < 4:
            self._cal_message = "Aim at the %s corner of the picture and press B" % CORNER_NAMES[cal["step"]]
            return
        try:
            self._calib = aim.make_calibration(cal["samples"])
        except ValueError:
            self._cal = None
            self._cal_message = "Calibration failed (the 4 corners were too close). Try again"
            return
        self._cal = None
        self._save_cal()
        self._cal_message = "Calibrated"

    # -- session --------------------------------------------------------------
    def _running(self):
        return self._reader is not None and self._reader.is_alive()

    def _load_opts(self):
        opts = dict(DEFAULT_OPTS)
        try:
            with open(OPT_FILE) as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                for k in DEFAULT_OPTS:
                    if k in saved:
                        opts[k] = saved[k]
        except Exception:
            pass
        return opts

    def _save_opts(self):
        try:
            os.makedirs(os.path.dirname(OPT_FILE), exist_ok=True)
            with open(OPT_FILE, "w") as f:
                json.dump(self._opts, f)
        except Exception as exc:
            print("  [wiimote] could not save the options: %s" % exc)

    def _apply_opts(self):
        r = self._rel
        r.sensitivity = self._opts["sensitivity"]
        r.invert_x = self._opts["invert_x"]
        r.invert_y = self._opts["invert_y"]

    def _set_opts(self, body):
        """sensitivity / invert_x / invert_y / edge_reload from a request body, when present.
        Saved, so they are what you left them as after a hub restart."""
        changed = False
        if body.get("sensitivity") is not None:
            self._opts["sensitivity"] = round(max(0.1, min(10.0, float(body["sensitivity"]))), 2)
            changed = True
        for k in ("invert_x", "invert_y", "edge_reload"):
            if body.get(k) is not None:
                self._opts[k] = bool(body[k])
                changed = True
        self._apply_opts()
        if changed:
            self._save_opts()

    def _session_start(self, mapping, target, dev, aim_axis, aim_mode=None, opts=None):
        self._stop_session()
        paths = find_input_devices()
        if NAME_BUTTONS not in paths or NAME_IR not in paths:
            raise RuntimeError("no Wii Remote connected (pair it first)")
        self._sess = {"mapping": mapping or "", "target": target or "pi",
                      "dev": dev or "", "aim_axis": aim_axis or "MAIN"}
        self._aim_mode = "absolute" if aim_mode == "absolute" else "relative"
        self._rel = aim.RelativePointer()
        self._apply_opts()
        self._edge_armed = True
        self._set_opts(opts or {})
        self._stop.clear()
        self._dots = 0
        self._raw = None
        self._aim = None
        self._cal = None
        self._cal_message = ""
        self._last_ping = time.time()
        self._reader = threading.Thread(target=self._read_loop, args=(paths,), daemon=True)
        self._reader.start()
        print("  [wiimote] session start (mapping=%s target=%s dev=%s axis=%s)" % (
            self._sess["mapping"], self._sess["target"], self._sess["dev"], self._sess["aim_axis"]))

    def _stop_session(self):
        self._stop.set()
        r = self._reader
        if r and r.is_alive() and r is not threading.current_thread():
            r.join(2)
        was_running = self._reader is not None
        self._reader = None
        self._dots = 0
        self._aim = None
        self._cal = None
        if was_running:
            self._drive({"action": "stop"})      # release the held sink in the drive service

    def _read_loop(self, paths):
        try:
            fb = os.open(paths[NAME_BUTTONS], os.O_RDONLY | os.O_NONBLOCK)
            fi = os.open(paths[NAME_IR], os.O_RDONLY | os.O_NONBLOCK)    # opening it switches the IR camera on
        except OSError as exc:
            print("  [wiimote] cannot open the input devices: %s" % exc)
            return
        ir = [[aim.IR_NONE, aim.IR_NONE] for _ in range(4)]
        last_post = 0.0
        try:
            while not self._stop.is_set():
                ready, _, _ = select.select([fb, fi], [], [], 0.2)
                for fd in ready:
                    try:
                        data = os.read(fd, _EVT.size * 64)
                    except BlockingIOError:
                        continue
                    for off in range(0, len(data) - _EVT.size + 1, _EVT.size):
                        _, _, etype, code, value = _EVT.unpack_from(data, off)
                        if fd == fb and etype == EV_KEY and code in KEYS and value in (0, 1):
                            self._button(KEYS[code], value == 1)
                        elif fd == fi and etype == EV_ABS and ABS_HAT0X <= code <= ABS_HAT0X + 7:
                            ir[(code - ABS_HAT0X) // 2][(code - ABS_HAT0X) % 2] = value
                        elif fd == fi and etype == EV_SYN:
                            last_post = self._aim_frame(ir, last_post)
        except OSError as exc:                   # the remote went away (slept / disconnected)
            print("  [wiimote] input lost: %s" % exc)
        finally:
            for fd in (fb, fi):
                try:
                    os.close(fd)
                except OSError:
                    pass
            self._dots = 0
            self._drive({"action": "stop"})

    def _edge_check(self, x, y, now):
        """The classic light-gun reload: pointing off the screen. A pointer can't leave the
        screen, so reaching its edge presses reload (the Wii Remote's A button, whatever the
        mapping makes of it), once per touch of the edge."""
        if not self._opts.get("edge_reload"):
            return
        at_edge = x <= 0.0 or x >= 1.0 or y <= 0.0 or y >= 1.0
        if at_edge:
            if self._edge_armed and now - self._last_reload >= EDGE_COOLDOWN_S:
                self._edge_armed = False
                self._last_reload = now
                s = self._sess
                self._drive({"action": "press", "key": "A", "ms": 120, "source": "wiimote",
                             "mapping": s.get("mapping"), "target": s.get("target"), "dev": s.get("dev")})
        elif EDGE_REARM <= x <= 1.0 - EDGE_REARM and EDGE_REARM <= y <= 1.0 - EDGE_REARM:
            self._edge_armed = True

    def _aim_frame(self, ir, last_post):
        """One IR frame -> the aim. Needs all 4 dots; with fewer the last aim is held."""
        if self._aim_mode == "relative":
            slots = [(p[0], p[1]) if (p[0] != aim.IR_NONE and p[1] != aim.IR_NONE) else None for p in ir]
            self._dots = sum(1 for sl in slots if sl is not None)
            self._raw = None
            x, y = self._rel.update(slots)
        else:
            dots = aim.valid_dots([tuple(p) for p in ir])
            self._dots = len(dots)
            if len(dots) != 4:
                self._raw = None
                return last_post
            try:
                raw = aim.raw_aim(dots)
            except ValueError:
                self._raw = None
                return last_post
            self._raw = raw
            self._raw_t = time.time()
            if self._cal is not None:
                return last_post                 # calibrating: the aim is not driven yet
            x, y = aim.to_axis(raw, self._calib)
        now = time.time()
        self._edge_check(x, y, now)
        prev = self._aim
        if prev is not None and abs(prev[0] - x) < AIM_MIN_DELTA and abs(prev[1] - y) < AIM_MIN_DELTA:
            return last_post
        if now - last_post < AIM_MIN_INTERVAL_S:
            return last_post
        self._aim = (x, y)
        s = self._sess
        self._drive({"action": "axis", "name": s.get("aim_axis"), "x": round(x, 4), "y": round(y, 4),
                     "source": "wiimote", "mapping": s.get("mapping"),
                     "target": s.get("target"), "dev": s.get("dev")})
        return now

    def _button(self, name, down):
        if self._cal is not None:
            if name == "B" and down:
                self._cal_capture()              # B records a calibration corner, it does not fire
            return
        s = self._sess
        self._drive({"action": "hold", "down": down, "key": name,
                     "source": "wiimote", "mapping": s.get("mapping"),
                     "target": s.get("target"), "dev": s.get("dev")})

    def _drive(self, body):
        """POST to the local drive service (best-effort; a drive failure must not kill
        the read loop -- the remote keeps working, the operator sees nothing move)."""
        try:
            req = urllib.request.Request(
                DRIVE_URL, data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=1).read()
            self._drive_ok = True
        except Exception:
            self._drive_ok = False

    def _keepalive_loop(self):
        # Hold the drive service's sink open between events (its watchdog releases after
        # a few seconds of silence, and the aim is quiet while the remote is still).
        while True:
            time.sleep(2)
            if self._running():
                self._drive({"action": "keepalive"})

    def _watchdog(self):
        while True:
            time.sleep(5)
            if self._running() and time.time() - self._last_ping > WATCHDOG_S:
                print("  [wiimote] watchdog reap (no ping)")
                self._stop_session()

    # -- status ---------------------------------------------------------------
    def status(self):
        with self._lock:
            st = dict(self._state)
        st["ok"] = True
        st["wiimotes"] = self._connected()
        st["session"] = self._running()
        st["dots"] = self._dots
        st["aim"] = [round(self._aim[0], 3), round(self._aim[1], 3)] if self._aim else None
        st["aim_mode"] = self._aim_mode
        st["sensitivity"] = self._opts["sensitivity"]
        st["invert_x"] = self._opts["invert_x"]
        st["invert_y"] = self._opts["invert_y"]
        st["edge_reload"] = self._opts["edge_reload"]
        st["calibrated"] = self._calib is not None
        st["cal_step"] = self._cal["step"] if self._cal else None
        st["cal_message"] = self._cal_message
        st["drive_ok"] = self._drive_ok
        return st

    # -- http -----------------------------------------------------------------
    def _make_handler(self):
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, obj, code=200):
                body = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)

            def do_OPTIONS(self):
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

            def do_GET(self):
                self._send(bridge.status())

            def do_POST(self):
                try:
                    n = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(n) or b"{}")
                except Exception:
                    self._send({"ok": False, "error": "bad json"}, 400)
                    return
                action = body.get("action")
                try:
                    if action == "pair":
                        bridge._pair()
                    elif action == "stop":
                        bridge._stop_pairing()
                    elif action == "disconnect":
                        bridge._disconnect()
                    elif action == "session_start":
                        bridge._session_start(body.get("mapping"), body.get("target"),
                                              body.get("dev"), body.get("aim_axis"),
                                              body.get("aim_mode"), body)
                    elif action == "aim_options":
                        bridge._set_opts(body)
                    elif action == "session_stop":
                        bridge._stop_session()
                    elif action == "ping":
                        bridge._last_ping = time.time()
                    elif action == "calibrate":
                        bridge._calibrate_start()
                    elif action == "calibrate_reset":
                        bridge._calibrate_reset()
                    else:
                        self._send({"ok": False, "error": "unknown action"}, 400)
                        return
                    self._send(bridge.status())
                except Exception as exc:
                    self._send({"ok": False, "error": str(exc)}, 200)

            def log_message(self, *a):
                pass

        return Handler
