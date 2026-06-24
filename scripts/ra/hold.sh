#!/bin/bash
# hold.sh <axis> <x> <y> <ms> [target] [mapping]
# Hold an analog axis for <ms> milliseconds by sending frames every 100ms.
# axis=MAIN or C. x/y in 0.0..1.0 (0.5=neutral). Release (0.5 0.5) on exit.
NAME="${1:?axis name required}"
X="${2:?x required}"
Y="${3:?y required}"
MS="${4:?duration ms required}"
TARGET="${5:-pi}"
MAPPING="${6:-dreamcast}"

END=$(( $(date +%s%3N) + MS ))
while [ "$(date +%s%3N)" -lt "$END" ]; do
    curl -s http://localhost:7700/control/drive -X POST \
      -H 'Content-Type: application/json' \
      -d "{\"action\":\"axis\",\"name\":\"$NAME\",\"x\":$X,\"y\":$Y,\"target\":\"$TARGET\",\"mapping\":\"$MAPPING\",\"source\":\"claude\"}" > /dev/null
    sleep 0.1
done
# release
curl -s http://localhost:7700/control/drive -X POST \
  -H 'Content-Type: application/json' \
  -d "{\"action\":\"axis\",\"name\":\"$NAME\",\"x\":0.5,\"y\":0.5,\"target\":\"$TARGET\",\"mapping\":\"$MAPPING\",\"source\":\"claude\"}" > /dev/null
echo "released $NAME after ${MS}ms"
