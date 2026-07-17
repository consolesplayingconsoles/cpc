"""
nokia.py -- Nokia phone keypad controller bridge.

A Nokia 6103 (running the CpcPad J2ME MIDlet) pairs to the Pi over Bluetooth and
streams key up/down events over an rfcomm serial channel. This bridge binds that
channel, reads the key stream, and forwards each keypress to the LOCAL drive service
(pluto-drive on :7702) as a /control/drive `hold` -- so the phone rides the exact
same distributed drive path as every other input. The mapping + sink routing live in
pluto-drive, not here; this bridge only carries source/mapping/target/dev + the key.

On-demand + self-reaping, mirroring the Kinect bridge: Pluto's NokiaControl POSTs
start/stop/ping to the HTTP endpoint; a watchdog tears the session down if the pings
stop. Runs inside the hub process (root, under cpc-hub.service) so it can bind rfcomm
and open /dev/rfcomm0.

  POST /engine {action:"start", source, mapping, target, dev}
  POST /engine {action:"stop"}
  POST /engine {action:"ping"}
  GET  /engine  -> {"running": bool}

Config (node .env): NOKIA_ENGINE_PORT (enables the bridge), NOKIA_ADDR (phone BT
MAC), NOKIA_CHANNEL (the MIDlet's rfcomm channel), NOKIA_DRIVE_URL (default the local
drive service http://127.0.0.1:7702/control/drive).
"""
import json
import subprocess
import threading
import time
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    import serial
except ImportError:
    serial = None

RFCOMM_DEV = "/dev/rfcomm0"
WATCHDOG_S = 45          # reap a session that stops pinging (tab closed / asleep)
DRIVE_URL = "http://127.0.0.1:7702/control/drive"   # the node's local drive service


class NokiaBridge:
    """Bluetooth keypad -> the LOCAL drive service (which maps the key + drives the
    sink). No in-process Pico driving; the phone is just another input on the
    distributed /control/drive path."""

    def __init__(self, port, cfg):
        self.port = port
        self.addr = (cfg.get("NOKIA_ADDR") or "").strip()
        self.channel = (cfg.get("NOKIA_CHANNEL") or "25").strip()
        self.drive_url = (cfg.get("NOKIA_DRIVE_URL") or DRIVE_URL).strip()
        self._sess = {}          # {source, mapping, target, dev} of the active session
        self._reader = None
        self._stop = threading.Event()
        self._last_ping = 0.0
        self._lock = threading.Lock()

    # -- lifecycle ------------------------------------------------------------
    def start(self):
        if serial is None:
            print("  [nokia] pyserial missing -- bridge disabled")
            return False
        if not self.addr:
            print("  [nokia] no NOKIA_ADDR in .env -- bridge disabled")
            return False
        srv = HTTPServer(("0.0.0.0", self.port), self._make_handler())
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        threading.Thread(target=self._watchdog, daemon=True).start()
        threading.Thread(target=self._keepalive_loop, daemon=True).start()
        return True

    def _running(self):
        return self._reader is not None and self._reader.is_alive()

    def _start_session(self, source, mapping, target, dev):
        self._stop_session()
        self._sess = {"source": source or "nokia", "mapping": mapping or "",
                      "target": target or "pi", "dev": dev or ""}
        self._stop.clear()
        self._rfcomm("release", "0")
        self._rfcomm("bind", "0", self.addr, self.channel)
        self._last_ping = time.time()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        print("  [nokia] session start (source=%s mapping=%s target=%s dev=%s)" % (
            self._sess["source"], self._sess["mapping"], self._sess["target"], self._sess["dev"]))

    def _stop_session(self):
        self._stop.set()
        r = self._reader
        if r and r.is_alive():
            r.join(2)
        self._reader = None
        self._drive({"action": "stop"})        # release the held sink in the drive service
        self._rfcomm("release", "0")

    # -- read + forward -------------------------------------------------------
    def _read_loop(self):
        try:
            ser = serial.Serial(RFCOMM_DEV, 115200, timeout=1)
            ser.dtr = True                      # wake the rfcomm link (as the AT modem needed)
            time.sleep(0.2)
            ser.reset_input_buffer()
            try:
                ser.write(b"\n")                # kick the link so CpcPad's accept fires
            except Exception:
                pass
        except Exception as exc:
            print("  [nokia] rfcomm open failed: %s" % exc)
            return
        buf = b""
        while not self._stop.is_set():
            try:
                chunk = ser.read(64)
            except Exception:
                break
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                s = line.decode("ascii", "ignore").strip()
                if not s or s == "PING" or s.startswith("HELLO"):
                    continue                    # link liveness -- not a key
                parts = s.split()
                if len(parts) == 2 and parts[0] in ("D", "U"):
                    self._hold(parts[0] == "D", parts[1])
        try:
            ser.close()
        except Exception:
            pass
        self._drive({"action": "stop"})

    def _hold(self, down, key):
        s = self._sess
        self._drive({"action": "hold", "down": down, "key": key,
                     "source": s.get("source"), "mapping": s.get("mapping"),
                     "target": s.get("target"), "dev": s.get("dev")})

    def _drive(self, body):
        """POST to the local drive service (best-effort; a drive failure must not kill
        the read loop -- the phone keeps working, the operator sees nothing move)."""
        try:
            req = urllib.request.Request(
                self.drive_url, data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=3).read()
        except Exception:
            pass

    def _keepalive_loop(self):
        # Hold the drive service's sink open between keystrokes (the NetworkSink -> hub
        # idle-releases after ~6s otherwise -- "works a bit then stops" on press-hold).
        while True:
            time.sleep(2)
            if self._running():
                self._drive({"action": "keepalive"})

    def _rfcomm(self, *args):
        subprocess.call(["rfcomm"] + list(args),
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _watchdog(self):
        while True:
            time.sleep(5)
            with self._lock:
                if self._running() and time.time() - self._last_ping > WATCHDOG_S:
                    print("  [nokia] watchdog reap (no ping)")
                    self._stop_session()

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
                self._send({"running": bridge._running()})

            def do_POST(self):
                try:
                    n = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(n) or b"{}")
                except Exception:
                    self._send({"ok": False, "error": "bad json"}, 400)
                    return
                action = body.get("action")
                with bridge._lock:
                    try:
                        if action == "start":
                            bridge._start_session(body.get("source"), body.get("mapping"),
                                                  body.get("target"), body.get("dev"))
                        elif action == "stop":
                            bridge._stop_session()
                        elif action == "ping":
                            bridge._last_ping = time.time()
                        else:
                            self._send({"ok": False, "error": "unknown action"}, 400)
                            return
                        self._send({"ok": True, "running": bridge._running()})
                    except Exception as exc:
                        self._send({"ok": False, "error": str(exc)}, 200)

            def log_message(self, *a):
                pass

        return Handler
