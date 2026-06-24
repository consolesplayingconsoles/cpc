#!/bin/bash
# signal.sh "<text>" [target] [mapping]
# Post an observation or message to the Guide Dog channel.
TEXT="${1:?text required}"
TARGET="${2:-pi}"
MAPPING="${3:-dreamcast}"
curl -s http://localhost:7700/control/signal -X POST \
  -H 'Content-Type: application/json' \
  -d "{\"state\":\"$TEXT\",\"role\":\"claude\",\"source\":\"claude\",\"target\":\"$TARGET\",\"mapping\":\"$MAPPING\"}"
