#!/bin/bash
# watch.sh - block until operator sends look or stop via session.log
# Exits 0 on "look", exits 1 on "stop"
SESSION_LOG="/Users/francesc.montserrat/workspace/cpc/dist/capture/latest-session/session.log"

# track last seen line count so we only react to NEW entries
SEEN=$(wc -l < "$SESSION_LOG" 2>/dev/null || echo 0)

while true; do
    sleep 2
    NOW=$(wc -l < "$SESSION_LOG" 2>/dev/null || echo 0)
    if [ "$NOW" -gt "$SEEN" ]; then
        NEW=$(tail -n "$((NOW - SEEN))" "$SESSION_LOG")
        SEEN=$NOW
        while IFS= read -r line; do
            ROLE=$(echo "$line" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('role',''))" 2>/dev/null)
            STATE=$(echo "$line" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('state',''))" 2>/dev/null)
            if [ "$ROLE" = "operator" ] || [ "$ROLE" = "system" ]; then
                echo "[$ROLE] $STATE"
                if [ "$STATE" = "look" ]; then exit 0; fi
                if [ "$STATE" = "stop" ]; then exit 1; fi
            fi
        done <<< "$NEW"
    fi
done
