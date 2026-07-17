#!/usr/bin/env python3
"""
server.py -- standalone CPC drive API. Wraps DriveEngine in an HTTP server so the
drive logic runs as its own service on any node (Lab, Pi, C2), exposing the SAME
POST /control/drive contract Pluto used to serve in-process.

Config (env):
  DRIVE_PORT     listen port (default 7702)
  CPC_MAPPINGS   mapping store (pluto/config/mappings) -- controller.load_mapping reads it
  CPC_NODES_DIR  nodes/ root, to resolve networked-sink endpoints (pi/roomba HOST_IP)
"""
import json
import os
import sys
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import controller                                  # noqa: E402  (co-located engine dep)
try:
    import dreame_events                           # replay adapter (dreame routes)
except Exception:
    dreame_events = None
from engine import DriveEngine                     # noqa: E402

PORT = int(os.environ.get("DRIVE_PORT", "7702"))
NODES_DIR = os.environ.get("CPC_NODES_DIR", "")

# The HTTP surface, kept in sync with openapi.yaml by scripts/check_openapi_drift.py.
ROUTES = [
    ("POST", "/control/drive"),
    ("GET", "/health"),
]


def _read_env(path):
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    except OSError:
        pass
    return env


def load_roster():
    """Minimal node roster {dir_name: {ENV..}} -> the sink-relevant vars (HOST_IP,
    PI_BRIDGE_PORT). Read fresh each call so config edits apply without a restart.

    Handles both layouts: STRUCTURED nodes/{local,cloud}/<name>/.env (Lab / C2) and
    FLAT <dir>/<name>/.env (the Pi's /opt/cpc, where the node config is /opt/cpc/pi/.env)."""
    roster = {}
    if not NODES_DIR:
        return roster
    scopes = [os.path.join(NODES_DIR, s) for s in ("local", "cloud")
              if os.path.isdir(os.path.join(NODES_DIR, s))]
    if not scopes:
        scopes = [NODES_DIR]                    # flat: node dirs sit directly under NODES_DIR
    for base in scopes:
        try:
            names = os.listdir(base)
        except OSError:
            continue
        for name in names:
            envp = os.path.join(base, name, ".env")
            if os.path.isfile(envp):
                roster[name] = _read_env(envp)
    return roster


engine = DriveEngine(controller, dreame_events, roster=load_roster)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
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
        if self.path.rstrip("/") in ("", "/health"):
            self._send(200, {"ok": True, "service": "cpc-drive", "port": PORT})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path.rstrip("/") != "/control/drive":
            self._send(404, {"error": "not found"})
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n)) if n else {}
        except (ValueError, json.JSONDecodeError):
            self._send(400, {"error": "invalid json"})
            return
        try:
            code, resp = engine.handle(body)
        except Exception as exc:
            code, resp = 200, {"ok": False, "error": "drive: %s" % exc}
        self._send(code, resp)

    def log_message(self, *a):
        pass


def main():
    print("CPC drive API on :%d (mappings=%s nodes=%s dreame=%s)" % (
        PORT, os.environ.get("CPC_MAPPINGS", "?"), NODES_DIR or "?",
        "yes" if dreame_events else "no"), flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
