"""
birdfeed.py — optional BirdBuddy postcard feed -> chat events.

Polls the BirdBuddy cloud for new postcards (a bird visited the feeder) and posts
each as a chat message from the `birdbuddy` member. RECEIVE-ONLY: no settings,
no battery/monitoring, no device control — just events in the chat.

NOTE: this module is deliberately NOT named birdbuddy.py — the pybirdbuddy package
installs a top-level `birdbuddy` package, and a same-named local module would
shadow it and break `from birdbuddy.client import BirdBuddy`.

pybirdbuddy is an OPTIONAL dependency. If it is not installed, the poller logs a
notice and stays idle (the node simply shows offline). To enable:
    pip install pybirdbuddy

Credentials (email/password) come from birdbuddy/.env on the Pluto host and are
never deployed to consoles. Messages are ASCII-only so the console TUIs render them.
"""
import asyncio
import random

POLL_INTERVAL = 120   # seconds between feed checks

# ASCII-only on purpose: these can be fetched and rendered by the console TUIs.
_BB_LINES = [
    "a little visitor just landed on the feeder!",
    "incoming postcard -- something feathery stopped by.",
    "*chirp* -- new bird at the feeder.",
    "the feeder has a guest. a postcard is on the way.",
    "flap flap -- a bird dropped by for a snack.",
]


def _species_of(node):
    """Best-effort species name from a postcard FeedNode (dict-like), or None.

    Raw postcards usually have no species yet (that comes after AI analysis), so
    this is a bonus when present rather than something to rely on.
    """
    try:
        for key in ("species", "speciesName", "name"):
            val = node.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        sightings = node.get("sightings") or []
        for s in sightings:
            sp = (s or {}).get("species") or {}
            nm = sp.get("name") if isinstance(sp, dict) else None
            if isinstance(nm, str) and nm.strip():
                return nm.strip()
    except Exception:
        pass
    return None


def describe(node):
    """Build an ASCII chat line for a postcard FeedNode."""
    species = _species_of(node)
    line = "a %s just visited the feeder!" % species if species else random.choice(_BB_LINES)
    return line.encode("ascii", "ignore").decode("ascii")


def run_poller(email, password, post_fn, set_status, stop_check, interval=POLL_INTERVAL):
    """Blocking poller — run inside a daemon thread.

    post_fn(text):    called once per new postcard.
    set_status(bool): mark the feeder online/offline (drives the graph node).
    stop_check():     return True to stop the loop.
    """
    try:
        from birdbuddy.client import BirdBuddy
    except ImportError:
        print("  [birdbuddy] pybirdbuddy not installed (pip install pybirdbuddy) -- poller idle")
        set_status(False)
        return

    async def main():
        bb = BirdBuddy(email, password)
        # Prime the feed cursor first so we don't dump the whole backlog on boot —
        # new_postcards() tracks the newest timestamp for subsequent calls.
        try:
            await bb.new_postcards()
            set_status(True)
            print("  [birdbuddy] connected, watching for postcards")
        except Exception as exc:
            print("  [birdbuddy] login/poll failed: %s" % exc)
            set_status(False)

        while not stop_check():
            await asyncio.sleep(interval)
            try:
                cards = await bb.new_postcards()
                set_status(True)
                for c in cards:
                    post_fn(describe(c))
            except Exception as exc:
                print("  [birdbuddy] poll error: %s" % exc)
                set_status(False)

    try:
        asyncio.run(main())
    except Exception as exc:
        print("  [birdbuddy] poller crashed: %s" % exc)
        set_status(False)
