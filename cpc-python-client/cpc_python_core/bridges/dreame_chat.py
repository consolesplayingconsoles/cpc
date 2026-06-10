"""
cpc_python_core/bridges/dreame_chat.py -- Dreame L40 -> CPC chat event bridge.

One of the cpc_python_core.bridges family. Reads the vacuum's live motion/state
and narrates it as events onto the Pluto group chat, so the L40 becomes a node
on the wire -- "Consoles Playing Consoles", now with a vacuum heckling from the
corner. No controller injection, no Bluetooth, no USB gadget: just network
events, so nothing hardware-gated stands in the way (the Pi 5's missing USB
peripheral mode etc. is irrelevant here).

The vacuum READ is pluggable (a "source"):
  * SimSource   -- fake motion, pure stdlib, needs no vacuum or creds. Use it to
                   build/test the entire pipeline offline.
  * CloudSource -- the real Dreamehome cloud read (SKELETON -- see the class).
                   The L40 is a Dreamehome device, so there is NO local miio
                   token and the local API is disabled; reads go through the
                   Dreame account cloud. Wiring + running that is the operator's
                   job, by design (it authenticates to the vacuum).

Latency is intentionally a non-issue: the event stream is recorded and synced
against game video in post, so a laggy cloud read is perfectly fine.

Pure stdlib, Python 3.6+, ASCII-only output (console terminals may be ASCII).
"""
import time
import random

from cpc_python_core import chat as chat_mod

# 8-point compass for heading buckets (ASCII only -- no arrows/unicode).
_COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

# activity vocabulary the sources agree on:
#   docked | cleaning | returning | paused | idle | error
_GREETINGS = {
    "docked":    "back on the dock. charging.",
    "cleaning":  "undocked. on the prowl.",
    "returning": "heading home to dock.",
    "paused":    "paused. taking five.",
    "idle":      "idle, awaiting orders.",
    "error":     "stuck! someone come help.",
}


def bucket_heading(deg):
    """Map a 0..359 heading to one of 8 compass points; None passes through."""
    if deg is None:
        return None
    return _COMPASS[int((deg % 360 + 22.5) // 45) % 8]


# -- Event vocabulary ----------------------------------------------------------

def motion_to_events(prev, cur):
    """Diff two state dicts -> list of ASCII chat lines. [] means nothing to say.

    A state dict is:
      {"activity": str, "heading": int|None, "battery": int|None, "note": str}
    """
    if prev is None:
        return ["L40 online. " + _GREETINGS.get(cur.get("activity", ""), "ready.")]

    events = []

    if cur.get("activity") != prev.get("activity"):
        events.append(_GREETINGS.get(
            cur.get("activity", ""), "state: %s" % cur.get("activity", "?")))

    # heading only matters while it is actually moving
    if cur.get("activity") in ("cleaning", "returning"):
        cb = bucket_heading(cur.get("heading"))
        if cb and cb != bucket_heading(prev.get("heading")):
            events.append("heading %s" % cb)

    # battery, only when it crosses a 10%% boundary downward
    pb, cbatt = prev.get("battery"), cur.get("battery")
    if pb is not None and cbatt is not None and cbatt // 10 < pb // 10:
        events.append("battery %d%%" % cbatt)

    if cur.get("note"):
        events.append(cur["note"])

    return events


# -- Sources -------------------------------------------------------------------

class SimSource:
    """Fake vacuum motion -- pure stdlib, no vacuum, no creds. The L40 wakes,
    cleans while drifting heading + draining battery, occasionally bumps, then
    returns to dock and recharges. Drives the whole pipeline offline."""

    def __init__(self, seed=None):
        self._r = random.Random(seed)
        self._heading = self._r.randint(0, 359)
        self._battery = 100
        self._activity = "docked"
        self._t = 0

    def read(self):
        self._t += 1
        if self._activity == "docked":
            if self._t > 2:
                self._activity = "cleaning"
        elif self._activity == "cleaning":
            self._heading = (self._heading + self._r.randint(-45, 45)) % 360
            self._battery = max(0, self._battery - 1)
            if self._r.random() < 0.06:
                return self._state("bumped something.")
            if self._battery <= 20:
                self._activity = "returning"
        elif self._activity == "returning":
            self._heading = (self._heading + self._r.randint(-20, 20)) % 360
            self._battery = max(0, self._battery - 1)
            if self._r.random() < 0.25:
                self._activity = "docked"
                self._battery = 100  # pretend the dock tops it up
        return self._state()

    def _state(self, note=""):
        return {
            "activity": self._activity,
            "heading": self._heading,
            "battery": self._battery,
            "note": note,
        }


class CloudSource:
    """Real Dreamehome cloud read -- SKELETON. The operator wires + runs this.

    The L40 is a Dreamehome (not Mi Home) device: no local miio token, local API
    disabled, so reads go through the Dreame account cloud (Alibaba-hosted). The
    community has reverse-engineered it -- port the auth/poll from the
    `dreame-vacuum` HA integration (Dreamehome account support) rather than
    reinventing it. Reference endpoints (region prefix varies: eu / us / cn):

        POST https://<region>.iot.dreame.tech:13267/dreame-auth/oauth/token
        GET  https://<region>.iot.dreame.tech:13267/dreame-user-iot/iotuserbind/device/listV2
        POST https://<region>.iot.dreame.tech:13267/dreame-iot-com-10000/device/sendCommand

    read() must return the SAME state dict SimSource produces, so the rest of the
    pipeline is unchanged. Authenticating here talks to your vacuum/account --
    that is operator-run on purpose.
    """

    def __init__(self, account, password, region="eu", did=None):
        self.account = account
        self.password = password
        self.region = region
        self.did = did

    def login(self):
        raise NotImplementedError(
            "Dreamehome cloud auth not wired. Port it from the dreame-vacuum "
            "integration and have the operator run it (it touches the vacuum)."
        )

    def read(self):
        raise NotImplementedError(
            "CloudSource.read(): wire the Dreamehome poll first (see class doc)."
        )


# -- Bridge loop ---------------------------------------------------------------

def run(pluto_url, sender, source, should_stop, on_status,
        poll_s=2.0, heartbeat_s=30.0):
    """Poll `source`, narrate state changes onto the Pluto chat as `sender`.

    pluto_url   -- e.g. "http://<pluto-host>:7700"; if falsy -> DRY RUN (no post).
    sender      -- chat handle the events appear under (e.g. "dreame").
    source      -- anything with .read() -> state dict (SimSource / CloudSource).
    should_stop -- () -> bool, checked each tick.
    on_status   -- (ascii_text) -> None, latest UI line.
    """
    prev = None
    last_event_t = time.time()

    while not should_stop():
        try:
            cur = source.read()
        except NotImplementedError as exc:
            on_status("source not wired: %s" % str(exc)[:48])
            return
        except Exception as exc:
            on_status("read error: %s" % str(exc)[:48])
            time.sleep(poll_s)
            continue

        events = motion_to_events(prev, cur)
        prev = cur

        now = time.time()
        if not events and (now - last_event_t) >= heartbeat_s:
            batt = cur.get("battery")
            events = ["still here." + (" (%d%%)" % batt if batt is not None else "")]

        if events:
            last_event_t = now
            for line in events:
                if pluto_url:
                    ok, err = chat_mod.post_message(pluto_url, sender, line)
                    on_status(("posted: " + line) if ok
                              else ("post failed: %s" % err[:32]))
                else:
                    on_status("[dry] %s: %s" % (sender, line))
        else:
            on_status("L40 %-9s heading=%-2s batt=%s" % (
                cur.get("activity", ""),
                bucket_heading(cur.get("heading")) or "-",
                cur.get("battery", "-")))

        time.sleep(poll_s)


def ready(config):
    """The chat bridge always runs (sim works with no vacuum); it just needs
    somewhere to post. True when the running node knows where Pluto is."""
    return bool(config.get("PLUTO_IP", "").strip())


if __name__ == "__main__":
    # Standalone sim demo:
    #   python3 -m cpc_python_core.bridges.dreame_chat            (dry run)
    #   python3 -m cpc_python_core.bridges.dreame_chat <pluto-host>   (-> Pluto)
    import sys

    pluto_ip = sys.argv[1] if len(sys.argv) > 1 else ""
    url = ("http://%s:7700" % pluto_ip) if pluto_ip else ""
    print("dreame_chat sim %s" % (("-> " + url) if url else "(dry run, no Pluto)"))

    ticks = [0]

    def _stop():
        ticks[0] += 1
        return ticks[0] > 60  # self-terminate after ~60 ticks

    try:
        run(url, "dreame", SimSource(seed=1), should_stop=_stop,
            on_status=lambda s: print("  " + s), poll_s=0.05, heartbeat_s=1.0)
    except KeyboardInterrupt:
        print("\nstopped.")
    print("done.")
