#!/usr/bin/env python3
"""
swagger.py — DEV-ONLY OpenAPI / Swagger UI for the Pluto API.

Lives OUTSIDE the deployed surface: deploy.sh ships only pluto/api + dist + config
+ serve.sh + deploy/, never pluto/tools/. So the production API stays pure-stdlib
with zero docs code or dependencies — exactly the "the box needs only python3"
property. This wrapper runs locally, on whatever python you like, and gives you the
Swagger experience without touching prod.

    # with the real API running on :7700 (start-pluto-lab.sh)
    python3 pluto/tools/swagger.py
    # -> Swagger UI at http://localhost:7800   ("Try it out" hits the live API)

It builds an OpenAPI 3.0 spec from the ROUTES table below (the route "annotations",
kept here, not in prod) and serves Swagger UI from a CDN. A best-effort DRIFT CHECK
diffs the table against api.py's actual dispatch and warns on mismatches, so the docs
don't quietly rot as the API grows. Pure stdlib — no install — but since nothing here
ships, swap in apispec / FastAPI freely if you ever want richer generation.
"""
import json
import os
import re
import http.server

API_PORT  = 7700   # the real Pluto API (target of "Try it out")
DOCS_PORT = 7800   # where this serves Swagger UI

# ── Route table — the documentation source (the "annotations") ────────────────
# Keep in sync with api.py's do_GET / do_POST. The drift check below flags
# exact-path routes that fall out of sync. Dynamic paths use {param}.
ROUTES = [
    {"m": "GET", "p": "/nodes", "tags": ["Topology"],
     "summary": "Network node map: roster + live ping status + per-node config."},
    {"m": "GET", "p": "/connections", "tags": ["Topology"],
     "summary": "Diagram edges (from / to / label)."},
    {"m": "GET", "p": "/whoami", "tags": ["Chat"],
     "summary": "Resolve the caller's chat identity (a known device id, or 'guest')."},
    {"m": "GET", "p": "/messages", "tags": ["Chat"],
     "summary": "Chat messages; incremental with ?since=<id> (else the recent backlog).",
     "query": [{"name": "since", "type": "integer",
                "desc": "Return only messages with id greater than this."}]},
    {"m": "POST", "p": "/messages", "tags": ["Chat"],
     "summary": "Post a chat message. Sender is resolved server-side (known device IP "
                "wins; guests may send a display name).",
     "body": {"text":   {"type": "string", "desc": "Message text (@mentions / /commands ok)."},
              "sender": {"type": "string", "desc": "Guest display name (ignored for known devices)."}},
     "required": ["text"]},
    {"m": "GET", "p": "/dreame", "tags": ["Dreame"],
     "summary": "Robutek/Dreame tab state: live device state + cleaning history.",
     "query": [{"name": "sync", "type": "string",
                "desc": "1 = pull fresh history from the cloud; otherwise the cache."}]},
    {"m": "POST", "p": "/dreame/login", "tags": ["Dreame"],
     "summary": "Sign in to DreameHome. Allowed from the local network only.",
     "body": {"region":        {"type": "string"},
              "username":       {"type": "string"},
              "password":       {"type": "string"},
              "secondary_key":  {"type": "string", "desc": "Reuse a refresh token instead of a password."}},
     "required": ["region"]},
    {"m": "POST", "p": "/dreame/logout", "tags": ["Dreame"],
     "summary": "Sign out of DreameHome (clears the in-memory session)."},
    {"m": "GET", "p": "/mappings", "tags": ["Mappings"],
     "summary": "All drive mappings, grouped by event source -> {source: [targets]}."},
    {"m": "GET", "p": "/mappings/{source}", "tags": ["Mappings"],
     "summary": "Targets for a source (the dir IS the filter), e.g. /mappings/dreame."},
    {"m": "GET", "p": "/mappings/{source}/{target}", "tags": ["Mappings"],
     "summary": "One mapping's JSON (event-source -> target-controller config)."},
    {"m": "POST", "p": "/robutek/drive", "tags": ["Dreame"],
     "summary": "Start / keep-alive / stop the vacuum->console drive (lab-only).",
     "body": {"action":  {"type": "string", "desc": "play | keepalive | stop"},
              "source":  {"type": "string", "desc": "Mapping source (default dreame)."},
              "mapping": {"type": "string", "desc": "Target controller, e.g. gamecube_dpad."},
              "speed":   {"type": "number"}},
     "required": ["action"]},
    {"m": "GET", "p": "/deploy/{node}/stream", "tags": ["Deploy"],
     "summary": "Server-sent-events stream of a node deploy's progress.",
     "path": [{"name": "node", "desc": "Node id (e.g. wii, pluto)."}]},
    {"m": "POST", "p": "/workspace/{node}", "tags": ["Deploy"],
     "summary": "Open the node's source checkout in the IDE on the API host (lab-only).",
     "path": [{"name": "node", "desc": "Node id."}]},
    {"m": "GET", "p": "/retro", "tags": ["Pages"], "html": True,
     "summary": "Barebones retro-console chat page (server-rendered HTML)."},
]


def build_spec():
    paths = {}
    for r in ROUTES:
        op = {"summary": r["summary"], "tags": r.get("tags", [])}
        params = []
        for q in r.get("query", []):
            params.append({"name": q["name"], "in": "query", "required": False,
                           "description": q.get("desc", ""),
                           "schema": {"type": q.get("type", "string")}})
        for pp in r.get("path", []):
            params.append({"name": pp["name"], "in": "path", "required": True,
                           "description": pp.get("desc", ""), "schema": {"type": "string"}})
        if params:
            op["parameters"] = params
        if "body" in r:
            props = {}
            for k, v in r["body"].items():
                props[k] = {"type": v.get("type", "string")}
                if "desc" in v:
                    props[k]["description"] = v["desc"]
            schema = {"type": "object", "properties": props}
            if r.get("required"):
                schema["required"] = r["required"]
            op["requestBody"] = {"required": True,
                                 "content": {"application/json": {"schema": schema}}}
        ctype = "text/html" if r.get("html") else "application/json"
        op["responses"] = {"200": {"description": "OK", "content": {ctype: {}}}}
        paths.setdefault(r["p"], {})[r["m"].lower()] = op
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Pluto API",
            "version": "1.0",
            "description": "Control-plane API for the Pluto dashboard (pure-stdlib "
                           "http.server). These docs are generated by the dev-only "
                           "tools/swagger.py and are NOT part of the deployed API.",
        },
        "servers": [{"url": "http://localhost:%d" % API_PORT, "description": "Local Pluto API"}],
        "paths": paths,
    }


def drift_check():
    """Best-effort: warn if api.py's exact-path dispatch and this table disagree."""
    api_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "api", "api.py")
    try:
        src = open(api_py, encoding="utf-8").read()
    except Exception as exc:
        print("  [drift] could not read api.py (%s)" % exc)
        return
    dispatched = set(re.findall(r'parsed\.path == "(/[^"]*)"', src))
    # Modular/prefix dispatch (e.g. `parts[0] == "mappings"`) serves a whole subtree;
    # treat "/<seg>" and anything under it as covered so REST resources don't drift.
    prefixes   = set("/" + seg for seg in re.findall(r'parts\[0\] == "([^"]+)"', src))
    covered    = lambda p: p in dispatched or any(p == x or p.startswith(x + "/") for x in prefixes)
    documented = set(r["p"] for r in ROUTES if "{" not in r["p"])
    missing = dispatched - documented                       # served but undocumented
    extra   = set(p for p in documented if not covered(p))  # documented but not dispatched
    if missing:
        print("  [drift] served by api.py but NOT documented: %s" % ", ".join(sorted(missing)))
    if extra:
        print("  [drift] documented but NOT found in api.py dispatch (renamed?): %s" % ", ".join(sorted(extra)))
    if not missing and not extra:
        print("  [drift] ok — table matches api.py's exact-path dispatch")


SWAGGER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Pluto API - Swagger</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"/>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.ui = SwaggerUIBundle({ url: "/openapi.json", dom_id: "#swagger-ui", deepLinking: true });
  </script>
</body>
</html>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, ctype, body):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/openapi.json":
            self._send(200, "application/json", json.dumps(build_spec(), indent=2))
        elif path in ("/", "/docs", "/index.html"):
            self._send(200, "text/html; charset=utf-8", SWAGGER_HTML)
        else:
            self._send(404, "text/plain; charset=utf-8", "not found")

    def log_message(self, *a):
        pass


def main():
    print("Pluto API docs (dev-only, not deployed)")
    drift_check()
    print("  Swagger UI:  http://localhost:%d/" % DOCS_PORT)
    print("  Spec:        http://localhost:%d/openapi.json" % DOCS_PORT)
    print("  'Try it out' targets the live API at http://localhost:%d" % API_PORT)
    http.server.ThreadingHTTPServer(("127.0.0.1", DOCS_PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
