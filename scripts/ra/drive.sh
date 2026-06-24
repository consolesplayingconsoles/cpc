#!/bin/bash
# drive.sh <btn> [ms] [target] [mapping]
# Press a button via the control API.
# Defaults: target=pi, mapping=dreamcast, ms=120
BTN="${1:?btn required}"
MS="${2:-120}"
TARGET="${3:-pi}"
MAPPING="${4:-dreamcast}"
curl -s http://localhost:7700/control/drive -X POST \
  -H 'Content-Type: application/json' \
  -d "{\"action\":\"press\",\"btn\":\"$BTN\",\"ms\":$MS,\"target\":\"$TARGET\",\"mapping\":\"$MAPPING\",\"source\":\"claude\"}"
