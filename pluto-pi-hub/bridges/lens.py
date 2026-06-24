"""
bridges/lens.py -- DC controller passthrough + hardware translate trigger.

Reads physical DC controller presses from OrangeFox86 DreamPicoPort evdev
devices, forwards every input over UART via HidBridge, and fires a Pluto
grab -> scan -> translate-last sequence when L+R are held simultaneously.

Pure stdlib + struct (no evdev C extension). 3.6-safe.
"""
import os
import json
import select
import struct
import time
import threading
import urllib.request
import urllib.error

DEVICES  = ["/dev/input/event%d" % i for i in range(4)]
COOLDOWN = 2.0   # seconds before re-triggering

EV_KEY     = 1
EV_ABS     = 3
EVENT_SIZE = struct.calcsize("llHHi")

BUTTON_MAP = {
    304: "A",       # BTN_SOUTH
    305: "B",       # BTN_EAST
    307: "Y",       # BTN_NORTH
    308: "X",       # BTN_WEST
    306: "Z",       # BTN_C
    309: "Z",       # BTN_Z (alias)
    310: "L",       # BTN_TL
    311: "R",       # BTN_TR
    314: "SELECT",  # BTN_SELECT
    315: "START",   # BTN_START
}
ABS_X     = 0
ABS_Y     = 1
ABS_HAT0X = 16
ABS_HAT0Y = 17
L_CODE    = 310
R_CODE    = 311


def _norm_axis(v, lo=-127, hi=127):
    span = hi - lo
    return (v - lo) / float(span) if span else 0.5


def _http(method, url, body=None, timeout=15):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            rbody = json.loads(exc.read())
        except Exception:
            rbody = {"error": str(exc)}
        return False, rbody
    except Exception as exc:
        return False, {"error": str(exc)}


def _trigger(pluto, lang):
    print("[lens] L+R -- grab -> scan -> translate (%s)" % lang)
    # 1. fresh frame (noop if capture already running)
    ok, r = _http("POST", "%s/control/capture/grab" % pluto, {}, timeout=12)
    if not ok:
        print("[lens] grab: %s" % r.get("error", r))
        # non-fatal: try scanning whatever frame is already there
    # 2. scan
    ok, r = _http("GET", "%s/control/lens" % pluto, timeout=15)
    if not ok:
        print("[lens] scan: %s" % r.get("error", r))
        return
    # 3. translate
    ok, r = _http("POST", "%s/control/lens/translate-last" % pluto,
                  {"target": lang}, timeout=15)
    if ok:
        print("[lens] translated: %s" % str(r.get("translated", ""))[:80])
    else:
        print("[lens] translate: %s" % r.get("error", r))


def _watch(device, bridges, shared, stop):
    try:
        f = open(device, "rb")
    except OSError as exc:
        print("[lens] %s: %s (skipping)" % (device, exc))
        return
    print("[lens] watching %s" % device)
    stick = {"x": 0.5, "y": 0.5}
    fd = f.fileno()
    while not stop.is_set():
        ready, _, _ = select.select([fd], [], [], 1.0)
        if not ready:
            continue
        try:
            data = f.read(EVENT_SIZE)
        except Exception:
            break
        if len(data) < EVENT_SIZE:
            break
        _, _, etype, code, value = struct.unpack("llHHi", data)

        if etype == EV_KEY:
            down = value == 1
            with shared["lock"]:
                if code == L_CODE:
                    shared["l_down"] = down
                elif code == R_CODE:
                    shared["r_down"] = down
                if down and shared["l_down"] and shared["r_down"]:
                    now = time.monotonic()
                    if now - shared["last_trigger"] >= COOLDOWN:
                        shared["last_trigger"] = now
                        threading.Thread(
                            target=_trigger,
                            args=(shared["pluto"], shared["lang"]),
                            daemon=True,
                        ).start()
            btn = BUTTON_MAP.get(code)
            if btn:
                for b in bridges:
                    b.apply([{"op": "press" if down else "release", "btn": btn}])

        elif etype == EV_ABS:
            ops = []
            if code == ABS_HAT0X:
                if value < 0:
                    ops = [{"op": "release", "btn": "RIGHT"},
                           {"op": "press",   "btn": "LEFT"}]
                elif value > 0:
                    ops = [{"op": "release", "btn": "LEFT"},
                           {"op": "press",   "btn": "RIGHT"}]
                else:
                    ops = [{"op": "release", "btn": "LEFT"},
                           {"op": "release", "btn": "RIGHT"}]
            elif code == ABS_HAT0Y:
                if value < 0:
                    ops = [{"op": "release", "btn": "DOWN"},
                           {"op": "press",   "btn": "UP"}]
                elif value > 0:
                    ops = [{"op": "release", "btn": "UP"},
                           {"op": "press",   "btn": "DOWN"}]
                else:
                    ops = [{"op": "release", "btn": "UP"},
                           {"op": "release", "btn": "DOWN"}]
            elif code == ABS_X:
                stick["x"] = _norm_axis(value)
                ops = [{"op": "axis", "name": "MAIN",
                        "x": stick["x"], "y": stick["y"]}]
            elif code == ABS_Y:
                stick["y"] = 1.0 - _norm_axis(value)
                ops = [{"op": "axis", "name": "MAIN",
                        "x": stick["x"], "y": stick["y"]}]
            if ops:
                for b in bridges:
                    b.apply(ops)

    try:
        f.close()
    except Exception:
        pass


class LensTrigger(object):
    name = "lens"

    def __init__(self, pluto_url, bridges, devices=None):
        self.pluto_url = pluto_url.rstrip("/")
        self.bridges   = bridges
        self.devices   = devices or DEVICES
        self._stop     = threading.Event()
        self._threads  = []

    def _fetch_lang(self):
        ok, r = _http("GET", "%s/control/lens/config" % self.pluto_url, timeout=5)
        lang = r.get("lang", "en") if ok else "en"
        return lang or "en"

    def start(self):
        lang = self._fetch_lang()
        print("[lens] translate lang: %s" % lang)
        shared = {
            "l_down":       False,
            "r_down":       False,
            "last_trigger": 0.0,
            "lock":         threading.Lock(),
            "pluto":        self.pluto_url,
            "lang":         lang,
        }
        for dev in self.devices:
            t = threading.Thread(
                target=_watch,
                args=(dev, self.bridges, shared, self._stop),
                daemon=True,
            )
            t.start()
            self._threads.append(t)
        return self

    def stop(self):
        self._stop.set()

    def status(self):
        return {
            "name":   self.name,
            "pluto":  self.pluto_url,
            "active": not self._stop.is_set(),
        }
