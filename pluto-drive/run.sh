#!/usr/bin/env bash
# run.sh -- start the standalone CPC drive API.
#
# Env paths default to the /opt/cpc deploy layout (pluto-drive, pluto, nodes are
# siblings). Override CPC_MAPPINGS / CPC_NODES_DIR / DRIVE_PORT to run elsewhere,
# e.g. locally from the repo root.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(cd .. && pwd)"

# Mapping store: repo (pluto/config/mappings) or a deployed box (config/mappings under
# the flattened root). Node roster: structured nodes/ (Lab/C2) or the flat deploy root
# (the Pi's /opt/cpc, where node config is /opt/cpc/<node>/.env). Env overrides win.
if [ -z "${CPC_MAPPINGS:-}" ]; then
  for m in "$ROOT/pluto/config/mappings" "$ROOT/config/mappings"; do
    [ -d "$m" ] && { CPC_MAPPINGS="$m"; break; }
  done
fi
if [ -z "${CPC_NODES_DIR:-}" ]; then
  for n in "$ROOT/nodes" "/opt/nodes" "$ROOT"; do
    [ -d "$n" ] && { CPC_NODES_DIR="$n"; break; }
  done
fi
export CPC_MAPPINGS CPC_NODES_DIR
export DRIVE_PORT="${DRIVE_PORT:-7702}"

if command -v python3 >/dev/null 2>&1; then PY=python3; else
  echo "[ERROR] no python3 found"; exit 1
fi
exec "$PY" server.py
