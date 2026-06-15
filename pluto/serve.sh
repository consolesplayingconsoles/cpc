#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  serve.sh — run Pluto on the host box: API + static SPA.
#
#  Pure stdlib python3, no deps to install. This is what `deploy.sh pluto/.env`
#  drops at /opt/pluto/serve.sh; run it there to bring the dashboard up.
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

python3 "$HERE/api/api.py"                              & API_PID=$!
python3 -m http.server "$SPA_PORT" --directory "$HERE/dist"  > /dev/null 2>&1 & SPA_PID=$!

echo "  pluto up — API :7700, SPA :${SPA_PORT}  (ctrl-c to stop)"
wait
