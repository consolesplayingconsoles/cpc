#!/usr/bin/env bash
# -----------------------------------------------------------------
#  run.sh -- start the CPC Pi-Hub (scaffold).
#
#  Reads the node .env that sits one level up, named after the node (the SAME
#  .env the python client uses -- one node, one config), or pass a path:
#    ./run.sh                  # scaffold report, auto-detect ../<node>/.env
#    ./run.sh serve            # start the always-up op receiver (systemd ExecStart)
#    ./run.sh serve ../pi/.env # explicit env
# -----------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")"

MODE=""
if [[ "${1:-}" == "serve" ]]; then MODE="serve"; shift; fi

ENV_FILE="${1:-}"
if [[ -z "$ENV_FILE" ]]; then
  shopt -s nullglob
  for f in ../*/.env; do
    [[ "$f" == ../pluto/.env ]] && continue
    ENV_FILE="$f"; break
  done
fi

if command -v python3 >/dev/null 2>&1; then PY=python3; else
  echo "[ERROR] no python3 found"; exit 1
fi

exec "$PY" hub.py ${MODE:+$MODE} "$ENV_FILE"
