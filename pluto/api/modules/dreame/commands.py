"""
vacuum.py — @l40 chat-command parsing for the Dreame L40.

Maps a free-text chat message to a canonical verb (status / locate / clean / dock
/ stop). dreame_session then handles it via the DreameHome cloud: 'status' reads
live state; the control verbs report that the cloud command endpoint isn't decoded
yet. (The old local-miio control path lived here too -- it's gone, since the L40's
firmware disables the local API.) Replies are ASCII-only for the console TUIs.
"""
import re

# keyword -> canonical verb (first match in the message wins)
_KEYWORDS = {
    "status": "status", "state": "status", "battery": "status", "where": "status",
    "locate": "locate", "find": "locate", "ping": "locate",
    "clean": "clean", "start": "clean", "go": "clean", "vacuum": "clean", "mop": "clean",
    "dock": "dock", "home": "dock", "charge": "dock", "back": "dock", "return": "dock",
    "stop": "stop", "halt": "stop", "pause": "stop",
}

VERB_HINT = "try: @l40 status | locate | clean | dock | stop"


def parse_command(text):
    """Return a canonical verb if the message names one, else None."""
    for tok in re.findall(r"[a-z]+", text.lower()):
        if tok in _KEYWORDS:
            return _KEYWORDS[tok]
    return None
