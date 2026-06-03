#!/usr/bin/env python3
"""
api.py — local API server for Pluto.
Handles network pings and deploy triggers.
Listens on localhost only. Never exposed externally.

Usage: python3 server/api.py <env-file>
"""
import os
import sys
import json
import subprocess
import http.server
import urllib.parse


PORT = 7700
ALLOWED_ORIGINS = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
}


def ping(ip: str) -> bool:
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "1", ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        return result.returncode == 0
    except Exception:
        return False


def load_env(path: str) -> dict:
    """Load env file leniently — missing keys are empty strings, not fatal."""
    config = {}
    if not os.path.exists(path):
        return config
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            config[k.strip()] = v.strip()
    return config


class Handler(http.server.BaseHTTPRequestHandler):
    config: dict = {}

    def log_message(self, format, *args):
        if self.path.startswith('/deploy'):
            print(f"  [{self.command}] {self.path}")

    def _send(self, status: int, body: dict):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/nodes":
            self._send(200, self._build_nodes())
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            pass  # CORS handled in _send

        parts = parsed.path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "deploy":
            node_id = parts[1]
            self._handle_deploy(node_id)
        else:
            self._send(404, {"error": "not found"})

    def _handle_deploy(self, node_id: str):
        cfg      = self.__class__.config
        base_dir = self.__class__.base_dir

        env_key  = f"{node_id.upper()}_ENV"
        env_path = cfg.get(env_key, "").strip()

        if not env_path:
            self._send(400, {"error": f"no env path configured for {node_id}"})
            return

        full_env  = os.path.join(base_dir, env_path)
        deploy_sh = os.path.join(base_dir, "..", "deploy.sh")
        deploy_sh = os.path.normpath(deploy_sh)

        if not os.path.exists(deploy_sh):
            self._send(500, {"error": "deploy.sh not found"})
            return

        print(f"  [DEPLOY] {node_id} → {full_env}")
        proc = subprocess.Popen(
            ["bash", deploy_sh, full_env],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        # Stream output in background thread
        import threading
        def _stream(p):
            for line in p.stdout:
                print(f"  [DEPLOY:{node_id}] {line}", end="")
        threading.Thread(target=_stream, args=(proc,), daemon=True).start()
        self._send(200, {"status": "deploying", "node": node_id})

    def _build_nodes(self):
        cfg      = self.__class__.config
        base_dir = self.__class__.base_dir
        nodes    = {}

        node_defs = {
            "gateway": ("GATEWAY_IP", None),
            "wii":     ("WII_IP",     "WII_ENV"),
            "dc":      ("DC_IP",      "DC_ENV"),
            "ps3":     ("PS3_IP",     "PS3_ENV"),
            "gba":     ("GBA_IP",     "GBA_ENV"),
            "ws":      ("WS_IP",      "WS_ENV"),
        }

        # Host is always present and always up — it's the machine running Pluto
        nodes["host"] = {
            "id":     "host",
            "name":   cfg.get("NODE_NAME", "Host"),
            "ip":     "127.0.0.1",
            "status": "up",
        }

        for node_id, (ip_key, env_key) in node_defs.items():
            ip = cfg.get(ip_key, "").strip()
            if not ip:
                continue

            name = node_id
            if env_key:
                env_path = cfg.get(env_key, "").strip()
                if env_path:
                    full_path = os.path.join(base_dir, env_path)
                    console_cfg = load_env(full_path)
                    name = console_cfg.get("NODE_NAME", node_id)

            nodes[node_id] = {
                "id":     node_id,
                "name":   name,
                "ip":     ip,
                "status": "up" if ping(ip) else "down",
            }

        return nodes


def run(env_path: str):
    config = load_env(env_path)
    Handler.config   = config
    Handler.base_dir = os.path.dirname(os.path.abspath(env_path))

    http.server.HTTPServer.allow_reuse_address = True
    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"  api running on http://127.0.0.1:{PORT}")
    print(f"  reading from {env_path}")
    print(f"  ctrl-c to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    env = sys.argv[1] if len(sys.argv) > 1 else "dev.env"
    run(env)
