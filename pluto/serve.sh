#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  serve.sh — run Pluto on the host box: API + static SPA.
#
#  Pure stdlib python3, no deps to install. This is what `deploy.sh pluto/.env`
#  drops at /opt/cpc/serve.sh; run it there to bring the dashboard up.
#
#    API : http://<host>:7700   (api/api.py — nodes, chat, deploys)
#    SPA : http://<host>:5173   (the pre-built dist/, served static)
#
#  Override the SPA port with SPA_PORT=8080 ./serve.sh. Ctrl-C stops both.
# ─────────────────────────────────────────────────────────────
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SPA_PORT="${SPA_PORT:-5173}"

API_PID=""
SPA_PID=""
cleanup() {
  [[ -n "$API_PID" ]] && kill "$API_PID" 2>/dev/null || true
  [[ -n "$SPA_PID" ]] && kill "$SPA_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if [[ ! -d "$HERE/dist" ]]; then
  echo "[ERROR] $HERE/dist not found — was this deployed with deploy.sh pluto/.env?"
  exit 1
fi

# Mappings (event->controller-op config) ship inside config/; point the core there.
[[ -d "$HERE/config/mappings" ]] && export CPC_MAPPINGS="$HERE/config/mappings"

# Pick an interpreter that HAS Pillow. The API only needs it for the capture renders
# (the Kindle e-ink frames, latest-processed.jpg) and degrades to raw frames without
# it -- which on this Lab Mac meant `python3` = Homebrew 3.14 = no Pillow = the Kindle
# silently served unrotated full-size frames for a whole session. Probe rather than
# hardcode a version, since this same script is deployed to the Pi and the EEE PC.
# Override with PLUTO_PYTHON=... if you want a specific one.
PY="${PLUTO_PYTHON:-}"
if [[ -z "$PY" ]]; then
  for c in python3 python3.13 python3.12 python3.11 python3.10; do
    command -v "$c" >/dev/null 2>&1 || continue
    if "$c" -c 'import PIL' >/dev/null 2>&1; then PY="$c"; break; fi
  done
fi
if [[ -z "$PY" ]]; then
  PY=python3
  echo "[WARN] no python with Pillow found — capture renders will be degraded (see the API's boot banner)"
fi
echo "[info] api interpreter: $PY ($("$PY" --version 2>&1))"

# -u: unbuffered. Under systemd/nohup stdout is a pipe, so Python block-buffers it and
# the boot output (including the PILLOW MISSING banner) would sit unflushed in memory --
# a warning you can't see is no warning at all.
"$PY" -u "$HERE/api/api.py"                             & API_PID=$!
# SPA static server with history-fallback: serves real files from dist/, and
# falls back to dist/index.html for any path that doesn't resolve (so deep
# links / refreshes on /chat and /dreame work). Pure stdlib, Python 3.6-safe.
python3 -c '
import os, sys
try:
    from http.server import SimpleHTTPRequestHandler, HTTPServer
except ImportError:
    from BaseHTTPServer import HTTPServer
    from SimpleHTTPServer import SimpleHTTPRequestHandler
root = sys.argv[1]
port = int(sys.argv[2])
os.chdir(root)
class Handler(SimpleHTTPRequestHandler):
    def send_head(self):
        path = self.translate_path(self.path)
        if not (os.path.isfile(path) or os.path.isdir(path)):
            self.path = "/index.html"
        return SimpleHTTPRequestHandler.send_head(self)
HTTPServer(("", port), Handler).serve_forever()
' "$HERE/dist" "$SPA_PORT"  > /dev/null 2>&1 & SPA_PID=$!

echo "  pluto up — API :7700, SPA :${SPA_PORT}  (ctrl-c to stop)"
wait
