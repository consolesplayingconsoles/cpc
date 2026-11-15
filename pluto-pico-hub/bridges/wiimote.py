"""
wiimote.py -- Wii Remote pairing + status bridge.

A Wii Remote connects to the Pi over Bluetooth (BlueZ + the kernel hid-wiimote
driver, which turns it into evdev input devices: buttons, accelerometer, and the IR
camera's dots). This bridge only owns the LINK: it finds a Wiimote that is in
pairing mode (1+2, or the red Sync button), connects + trusts it, and reports which
remotes are connected and their battery. It does not read the remote's input -- that
is a separate stage (the IR dots -> aim -> mouse step).

On-demand, mirroring the Kinect/Nokia bridges: Pluto's WiimoteControl talks to the
HTTP endpoint. Pairing is a bounded one-shot (SCAN_S seconds), so there is no
session watchdog. Runs inside the hub process (root, under cpc-hub.service) so it can
drive bluetoothctl.

  POST /engine {action:"pair"}        start a scan and connect the first Wiimote seen
  POST /engine {action:"stop"}        cancel a running pairing scan
  POST /engine {action:"disconnect"}  disconnect every connected Wiimote
  GET  /engine -> {"ok", "pairing", "message", "wiimotes": [{addr, name, battery}]}

Config (node .env): WIIMOTE_ENGINE_PORT (enables the bridge).
"""
import glob
import json
import os
import re
import subprocess
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

SCAN_S = 40              # how long a pairing scan runs (the remote stays discoverable ~20 s per press)
RETRY_S = 3              # do not retry connecting to the same address more often than this
CONNECT_TIMEOUT_S = 12

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
        self._state = {"pairing": False, "message": ""}
        self._cancel = threading.Event()
        self._scan = None            # the running `bluetoothctl scan on` process
        self._thread = None

    # -- lifecycle ------------------------------------------------------------
    def start(self):
        if not os.path.exists("/usr/bin/bluetoothctl"):
            print("  [wiimote] bluetoothctl missing -- bridge disabled")
            return False
        srv = HTTPServer(("0.0.0.0", self.port), self._make_handler())
        threading.Thread(target=srv.serve_forever, daemon=True).start()
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

    def _stop(self):
        self._cancel.set()

    # -- status ---------------------------------------------------------------
    def _connected(self):
        out = []
        for addr, name in parse_devices(_btctl("devices", "Connected")):
            if is_wiimote(name):
                out.append({"addr": addr, "name": name, "battery": _battery(addr)})
        return out

    def _disconnect(self):
        for w in self._connected():
            _btctl("disconnect", w["addr"])
        self._set(message="Disconnected")

    def status(self):
        with self._lock:
            st = dict(self._state)
        st["ok"] = True
        st["wiimotes"] = self._connected()
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
                        bridge._stop()
                    elif action == "disconnect":
                        bridge._disconnect()
                    else:
                        self._send({"ok": False, "error": "unknown action"}, 400)
                        return
                    self._send(bridge.status())
                except Exception as exc:
                    self._send({"ok": False, "error": str(exc)}, 200)

            def log_message(self, *a):
                pass

        return Handler
