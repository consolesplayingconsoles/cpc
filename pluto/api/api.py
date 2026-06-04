#!/usr/bin/env python3
"""
api.py — local API server for Pluto.
Handles network pings and deploy triggers.
Listens on localhost only. Never exposed externally.

Usage: python3 api/api.py
"""
import os
import sys
import json
import platform
import subprocess
import http.server
import urllib.parse


def open_path(path: str):
    """Open a file or directory in the system file manager, cross-platform."""
    system = platform.system()
    if system == "Darwin":
        subprocess.Popen(["open", path])
    elif system == "Linux":
        subprocess.Popen(["xdg-open", path])
    elif system == "Windows":
        subprocess.Popen(["explorer", path])


PORT = 7700
def _is_allowed_origin(origin: str) -> bool:
    import re
    return bool(re.match(r'^https?://(localhost|127\.0\.0\.1)(:\d+)?$', origin))

# The explicit checklist of variables required for your environment infrastructure
REQUIRED_VARS = [
    "LOCAL_PATH",
    "WORKSPACE_PATH",
    "GATEWAY_IP",
    "WII_IP",
    "WII_ENV"
]


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
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                v = v[1:-1]
            config[k.strip()] = v
    return config


class Handler(http.server.BaseHTTPRequestHandler):
    config: dict = {}
    base_dir: str = ""

    def log_message(self, format, *args):
        if self.path.startswith('/deploy'):
            print(f"  [{self.command}] {self.path}")

    def _send(self, status: int, body: dict):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        origin = self.headers.get("Origin", "")
        if _is_allowed_origin(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        origin = self.headers.get("Origin", "")
        if _is_allowed_origin(origin):
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
        parts = parsed.path.strip("/").split("/")

        if len(parts) == 2 and parts[0] == "deploy":
            self._handle_deploy(parts[1])
        elif len(parts) == 2 and parts[0] in ("open", "workspace"):
            self._handle_open(action=parts[0], target_node=parts[1])
        else:
            self._send(404, {"error": "not found"})

    def _handle_open(self, action: str, target_node: str):
        key = {"open": "LOCAL_PATH", "workspace": "WORKSPACE_PATH"}.get(action)
        if not key:
            self._send(404, {"error": "unknown action"})
            return

        path = self.__class__.config.get(key, "").strip()
        if not path:
            self._send(400, {"error": f"{key} not configured"})
            return

        path = os.path.expanduser(path)
        if action == "open" and target_node != "host":
            path = os.path.join(path, target_node)
        print(f"  [OPEN:{action}] Targeted Node: {target_node} → {path}")
        open_path(path)
        self._send(200, {"status": "opened", "path": path, "target": target_node})

    def _handle_deploy(self, node_id: str):
        cfg = self.__class__.config
        base_dir = self.__class__.base_dir

        env_key = f"{node_id.upper()}_ENV"
        env_path = cfg.get(env_key, "").strip()

        if not env_path:
            self._send(400, {"error": f"no env path configured for {node_id}"})
            return

        full_env = os.path.join(base_dir, env_path)
        repo_root = os.path.dirname(base_dir)
        deploy_sh = os.path.join(repo_root, "deploy.sh")

        if not os.path.exists(deploy_sh):
            self._send(500, {"error": f"deploy.sh not found at {deploy_sh}"})
            return

        print(f"  [DEPLOY] {node_id} → {full_env}")
        try:
            result = subprocess.run(
                ["bash", deploy_sh, full_env],
                cwd=repo_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            self._send(504, {"status": "error", "node": node_id, "output": "timed out after 120s"})
            return

        output = result.stdout.strip() if result.stdout else ""
        ok = result.returncode == 0
        for line in output.splitlines():
            print(f"  [DEPLOY:{node_id}] {line}")
        self._send(200 if ok else 500, {
            "status": "ok" if ok else "error",
            "node": node_id,
            "output": output,
            "returncode": result.returncode,
        })

    def _build_nodes(self):
        cfg = self.__class__.config
        base_dir = self.__class__.base_dir
        nodes = {}

        node_defs = {
            "gateway": ("GATEWAY_IP", None),
            "wii": ("WII_IP", "WII_ENV"),
            "dc": ("DC_IP", "DC_ENV"),
            "ps3": ("PS3_IP", "PS3_ENV"),
            "gba": ("GBA_IP", "GBA_ENV"),
            "ws": ("WS_IP", "WS_ENV"),
        }

        nodes["host"] = {
            "id": "host",
            "name": cfg.get("NODE_NAME", "Host"),
            "ip": "127.0.0.1",
            "color": cfg.get("UI_PRIMARY_COLOR") or None,
            "status": "up",
        }

        for node_id, (ip_key, env_key) in node_defs.items():
            ip = cfg.get(ip_key, "").strip()
            if not ip:
                continue

            name = node_id
            color = None
            if env_key:
                env_path = cfg.get(env_key, "").strip()
                if env_path:
                    full_path = os.path.join(base_dir, env_path)
                    console_cfg = load_env(full_path)
                    name = console_cfg.get("NODE_NAME", node_id)
                    color = console_cfg.get("UI_PRIMARY_COLOR") or None

            nodes[node_id] = {
                "id": node_id,
                "name": name,
                "ip": ip,
                "color": color,
                "status": "up" if ping(ip) else "down",
            }

        return nodes


def run():
    # Find the parent directory relative to where api.py physically sits
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    env_path = os.path.join(parent_dir, ".env")

    if not os.path.exists(env_path):
        print(f"\n❌ Error: Configuration file not found at: {env_path}")
        print("Please ensure your .env file is placed in the project root directory.\n")
        sys.exit(1)

    config = load_env(env_path)

    # Validation block checks if required variables exist
    missing_keys = [var for var in REQUIRED_VARS if not config.get(var, "").strip()]
    if missing_keys:
        print("\n❌ CRITICAL: Configuration values are empty or completely missing!")
        print(f"Target Configuration Location: {env_path}\n")
        print("Please configure the following missing variables immediately:")
        for missing in missing_keys:
            print(f"  ➡️  {missing}=")
        print()
        sys.exit(1)

    Handler.config = config
    Handler.base_dir = parent_dir  # Aligns relative paths straight out of project root

    http.server.HTTPServer.allow_reuse_address = True
    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"  api running on http://127.0.0.1:{PORT}")
    print(f"  reading from {env_path}")
    print(f"  ctrl-c to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopping server...")
        server.server_close()


if __name__ == "__main__":
    run()