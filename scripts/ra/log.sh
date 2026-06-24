#!/bin/bash
# log.sh - print last N lines from latest-session/session.log
# Usage: log.sh [n]   (default 10)
N="${1:-10}"
SESSION_LOG="/Users/francesc.montserrat/workspace/cpc/dist/capture/latest-session/session.log"
tail -n "$N" "$SESSION_LOG" | python3 -c "
import json, sys
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        d = json.loads(line)
        print(d.get('iso',''), d.get('role',''), repr(d.get('state','')))
    except Exception:
        print(line)
"
