"""
nokia.py -- Nokia phone keypad controller bridge.

A Nokia 6103 (running the CpcPad J2ME MIDlet) pairs to the Pi over Bluetooth and
streams key up/down events over an rfcomm serial channel. This bridge binds that
channel, reads the key stream, maps keys -> Dreamcast buttons (the mapping is
pushed by Pluto's NokiaControl when the Control tab opens), and drives the local
Pico HidBridge DIRECTLY -- keypresses never leave the Pi, so input stays snappy.

On-demand + self-reaping, mirroring the Kinect bridge: Pluto POSTs start/stop/ping
to the HTTP endpoint; a watchdog tears the session down if the pings stop (tab
closed / laptop asleep). Runs inside the hub process (root, under cpc-hub.service),
so it can bind rfcomm and open /dev/rfcomm0.

  POST /engine {action:"start", mapping:{"2":"D_UP",...}, dev:"/dev/ttyAMA0"}
  POST /engine {action:"stop"}
  POST /engine {action:"ping"}
  GET  /engine  -> {"running": bool}

Config (node .env): NOKIA_ENGINE_PORT (enables the bridge), NOKIA_ADDR (phone BT
MAC), NOKIA_CHANNEL (the MIDlet's rfcomm channel, shown on the phone screen).
"""
import json
import subprocess
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    import serial
except ImportError:
    serial = None

RFCOMM_DEV = "/dev/rfcomm0"
WATCHDOG_S = 45          # reap a session that stops pinging (tab closed / asleep)


class NokiaBridge:
    """Bluetooth keypad -> local Pico. Drives the HidBridge in-process (no :7720 hop)."""

    def __init__(self, port, cfg, bridges):
        self.port = port
        self.addr = (cfg.get("NOKIA_ADDR") or "").strip()
        self.channel = (cfg.get("NOKIA_CHANNEL") or "25").strip()
        self._by_dev = {b.device: b for b in bridges}
        self._default = bridges[0] if bridges else None
        self._controls = {}
        self._drive_dev = None
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
        if self._default is None:
            print("  [nokia] no Pico bridge to drive -- bridge disabled")
            return False
        srv = HTTPServer(("0.0.0.0", self.port), self._make_handler())
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        threading.Thread(target=self._watchdog, daemon=True).start()
        return True

    def _running(self):
        return self._reader is not None and self._reader.is_alive()

    def _start_session(self, mapping, dev):
        self._stop_session()
        self._controls = dict(mapping or {})
        self._drive_dev = dev or None
        self._stop.clear()
        self._rfcomm("release", "0")
        self._rfcomm("bind", "0", self.addr, self.channel)
        self._last_ping = time.time()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        print("  [nokia] session start (dev=%s, %d keys)" % (dev, len(self._controls)))

    def _stop_session(self):
        self._stop.set()
        r = self._reader
        if r and r.is_alive():
            r.join(2)
        self._reader = None
        self._release_all()
        self._rfcomm("release", "0")

    # -- read + drive ---------------------------------------------------------
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
                    btn = self._controls.get(parts[1])
                    if btn:                     # unmapped key -> ignore
                        self._apply(parts[0] == "D", btn)
        try:
            ser.close()
        except Exception:
            pass
        self._release_all()

    def _apply(self, down, btn):
        bridge = self._by_dev.get(self._drive_dev, self._default)
        if bridge:
            bridge.apply([{"op": "press" if down else "release", "btn": btn}])

    def _release_all(self):
        bridge = self._by_dev.get(self._drive_dev, self._default)
        if bridge:
            try:
                bridge.release_all()
            except Exception:
                pass

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
                            bridge._start_session(body.get("mapping") or {}, body.get("dev"))
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
