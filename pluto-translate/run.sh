#!/bin/sh
# Entry point for the CPC translation API payload (pluto-translate), mirroring
# pluto-pi-hub/run.sh. The batocera-service / systemd unit calls `run.sh serve`.
#   run.sh serve   -> start the HTTP API (cpc_translate_api.py)
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
case "${1:-}" in
  serve) exec python3 -u "$DIR/cpc_translate_api.py" ;;   # -u: unbuffered, so service.log is live
  *)     echo "usage: run.sh serve" >&2; exit 1 ;;
esac
