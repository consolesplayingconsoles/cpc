#!/bin/bash
# axis.sh <name> <x> <y> [target] [mapping]
# Set analog stick. name=MAIN or C. x/y in -1.0..1.0 (0.5=neutral).
NAME="${1:?stick name required}"
X="${2:?x required}"
Y="${3:?y required}"
TARGET="${4:-pi}"
MAPPING="${5:-dreamcast}"
curl -s http://localhost:7700/control/drive -X POST \
  -H 'Content-Type: application/json' \
  -d "{\"action\":\"axis\",\"name\":\"$NAME\",\"x\":$X,\"y\":$Y,\"target\":\"$TARGET\",\"mapping\":\"$MAPPING\",\"source\":\"claude\"}"
