#!/usr/bin/env python3
"""CPC translation service -- runs ON the Batocera node, where the GDIs and
buildgdi live. A small stdlib HTTP API so Pluto talks to it over HTTP instead of
SSH-ing a script per call. Threaded, so the per-source requests Pluto fires can
run in parallel and stream their tabs back as they finish.

Endpoints (discovery skeleton -- per-file extract + streaming come next):
  GET /health             -> {"ok": true, ...}
  GET /sources?path=<gdi> -> {"sources":[...]}  translatable text files, ranked

Stdlib only; kept Python 3.6-safe (ThreadingMixIn + HTTPServer, not 3.7's
ThreadingHTTPServer) to match the house rules even though the box runs 3.12.
"""
import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs

PORT = 7711
SCRIPTS = os.path.dirname(os.path.abspath(__file__))

# Route table = the single source of truth for what this API exposes. The
# dispatcher reads it AND scripts/check_openapi_drift.py reads it (vs openapi.yaml),
# so neither the dispatch nor the spec can silently drift. Keys are (METHOD, path).
ROUTES = {
    ("GET", "/health"):  "_r_health",
    ("GET", "/meta"):    "_r_meta",
    ("GET", "/games"):   "_r_games",
    ("GET", "/sources"): "_r_sources",
    ("GET", "/extract"): "_r_extract",
}


def _run(argv, timeout=300):
    p = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=timeout)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def _last_json(out):
    line = next((l for l in reversed(out.splitlines()) if l.strip()), "")
    return json.loads(line)   # raises if not JSON


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # quiet; the service.log captures crashes

    def do_GET(self):
        self._dispatch("GET")

    def _dispatch(self, method):
        u = urlparse(self.path)
        name = ROUTES.get((method, u.path))
        if not name:
            self._send(404, {"error": "not found"})
            return
        getattr(self, name)(parse_qs(u.query))

    def _r_health(self, qs):
        self._send(200, {"ok": True, "service": "cpc-translate", "port": PORT})

    def _r_games(self, qs):
        system = (qs.get("system") or [""])[0]
        if not system:
            self._send(400, {"error": "system required"})
            return
        rc, out = _run(["sh", os.path.join(SCRIPTS, "list-games.sh"), system])
        if rc != 0:
            self._send(502, {"error": "list failed", "detail": out[-500:]})
            return
        games = []
        for line in out.splitlines():
            path = line.strip()
            if not path:
                continue
            base   = os.path.basename(path)
            parent = os.path.basename(os.path.dirname(path))
            name   = parent if base.lower() == "disc.gdi" else os.path.splitext(base)[0]
            games.append({"name": name, "path": path})
        self._send(200, {"games": games})

    def _r_sources(self, qs):
        path = (qs.get("path") or [""])[0]
        if not path:
            self._send(400, {"error": "path required"})
            return
        rc, out = _run(["sh", os.path.join(SCRIPTS, "dc", "sources.sh"), path])
        try:
            self._send(200, _last_json(out))
        except Exception:
            self._send(502, {"error": "sources failed", "detail": out[-500:]})

    def _r_meta(self, qs):
        path = (qs.get("path") or [""])[0]
        if not path:
            self._send(400, {"error": "path required"})
            return
        rc, out = _run(["python3", os.path.join(SCRIPTS, "dc", "meta.py"), path], timeout=30)
        try:
            self._send(200, _last_json(out))
        except Exception:
            self._send(502, {"error": "meta failed", "detail": out[-500:]})

    def _r_extract(self, qs):
        path = (qs.get("path") or [""])[0]
        safe = (qs.get("file") or [""])[0]
        if not path or not safe:
            self._send(400, {"error": "path and file required"})
            return
        rc, out = _run(["sh", os.path.join(SCRIPTS, "dc", "extract.sh"), path, safe])
        try:
            self._send(200, _last_json(out))
        except Exception:
            self._send(502, {"error": "extract failed", "detail": out[-500:]})


class Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    print("cpc-translate listening on 0.0.0.0:%d" % PORT)
    Server(("0.0.0.0", PORT), Handler).serve_forever()
