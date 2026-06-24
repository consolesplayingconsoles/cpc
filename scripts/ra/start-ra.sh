#!/bin/bash
# start-ra.sh - bootstrap a Reverse Animus session
# Run once at the start of each session to confirm wiring and launch watch mode.
# Usage: ./scripts/ra/start-ra.sh [target] [mapping]
TARGET="${1:-pi}"
MAPPING="${2:-dreamcast}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SESSION_LOG="$REPO_ROOT/dist/capture/latest-session/session.log"
FLAG="$REPO_ROOT/dist/capture/state.flag"

cd "$REPO_ROOT" || exit 1

echo "--- RA bootstrap ---"

# 1. API up?
if ! curl -s -m 2 http://localhost:7700/nodes > /dev/null; then
    echo "ERROR: API not reachable at localhost:7700. Start it first."
    exit 1
fi
echo "API: ok"

# 2. Session log present?
if [ ! -f "$SESSION_LOG" ]; then
    echo "ERROR: No session log at $SESSION_LOG. Start capture first."
    exit 1
fi
echo "Session log: $SESSION_LOG"

# 3. Bump state flag
python3 -c "
import json, time
p = '$FLAG'
try: d = json.load(open(p))
except: d = {}
d['ts'] = time.time(); d['by'] = 'start-ra'; d['state'] = 'go'
open(p, 'w').write(json.dumps(d))
" && echo "State flag: bumped"

# 4. Signal ready on Guide Dog
./scripts/ra/signal.sh "RA session started. target=$TARGET mapping=$MAPPING. Send look to begin." "$TARGET" "$MAPPING"

echo "--- watch mode ---"
echo "Send 'look' from Pluto to read a frame."
echo "Send 'stop' to end the session."
echo ""

# 5. Launch watch loop
while true; do
    ./scripts/ra/watch.sh
    CODE=$?
    if [ $CODE -eq 1 ]; then
        echo "STOP received. Session ended."
        ./scripts/ra/signal.sh "Session ended by operator." "$TARGET" "$MAPPING"
        break
    fi
    # look received — read processed frame, signal, wait for next command from caller
    echo "look — pass to Claude for frame read"
    break
done
