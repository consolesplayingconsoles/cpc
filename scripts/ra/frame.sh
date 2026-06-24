#!/bin/bash
# frame.sh - bump state.flag (keep capture alive)
python3 -c "
import json, time
p = 'dist/capture/state.flag'
try:
    d = json.load(open(p))
except Exception:
    d = {}
d['ts'] = time.time()
d['by'] = 'claude'
d['state'] = d.get('state', 'go')
open(p, 'w').write(json.dumps(d))
print('flag bumped')
"
