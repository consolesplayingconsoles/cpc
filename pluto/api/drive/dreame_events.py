"""
dreame_events.py -- Dreame L40 -> action-trigger events.

The console-agnostic SPINE of the "vacuum plays a console" build. It turns vacuum
data into a stream of typed ACTION TRIGGERS -- discrete, timestamped events that a
downstream consumer maps to controller buttons/stick. Capturing them is decoupled
from (and unblocked by) the hardware hop: Wii via Pico, Dreamcast via USB-to-Maple,
or just a Mac driving Flycast/Dolphin -- all consume the SAME event stream, so this
layer never changes when the target console does.

Two producers, by data source:
  * events_from_route(session)  -- REPLAY of a captured clean (routes.json). The
        rich source: a {x,y} path yields direction/turn/reposition triggers plus
        session one-shots. Works today, no creds, no live device.
  * events_from_state(prev,cur) -- LIVE state deltas (the typed sibling of
        dreame_chat.motion_to_events). Face-button triggers only: the L40's
        live_state has NO heading (pose undecoded), so live can't drive direction.

An event is a plain dict (3.6-safe, json-able):
    {"t": float_seconds_from_start, "kind": str, "value": <json-able>}

Pure stdlib, Python 3.6+, ASCII-only.
"""
import math
import statistics

# -- Action-trigger vocabulary -------------------------------------------------
# Console-agnostic on purpose. A consumer binds these to its own pad:
#   MOVE/TURN -> stick or D-pad ; STATE -> face buttons ; one-shots -> Start/etc.
START      = "start"        # value: {"kind","area_m2","cleaning_min","session_id","date"}
END        = "end"          # value: {"completed": bool}
STATE      = "state"        # value: activity bucket (cleaning/idle/paused/returning/docked/error)
MOVE       = "move"         # value: {"heading": int, "dir8": str, "dx": float, "dy": float}
TURN       = "turn"         # value: "left" | "right"
REPOSITION = "reposition"   # value: {"dist": int}  (a teleport/relocalize jump in the path)
BATTERY    = "battery"      # value: int level, on a downward 10%% crossing
PET        = "pet"          # value: True

_COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

# Tuning (calibrate against the emulator once a consumer exists).
MOVE_DEG    = 12.0    # re-aim: emit MOVE when the true heading drifts this far, so
                      # the analog stick GLIDES along the path instead of snapping
                      # between 8 compass octants (natural open-world walk)
TURN_DEG    = 35.0    # heading change that counts as a deliberate turn
JUMP_FACTOR = 6.0     # step > JUMP_FACTOR * median step  => a reposition jump
JUMP_MIN_MM = 300     # ...and at least this far, so tiny-median noise never trips it


def _ev(t, kind, value=None):
    return {"t": round(float(t), 3), "kind": kind, "value": value}


def bucket_heading(deg):
    """0..359 compass bearing (0=N, clockwise) -> one of 8 points; None passes."""
    if deg is None:
        return None
    return _COMPASS[int((deg % 360 + 22.5) // 45) % 8]


def _bearing(p0, p1):
    """Compass bearing p0->p1 in degrees (0=N/+y, 90=E/+x, clockwise).

    Assumes map +x = east, +y = north. If a calibration pass shows the stick is
    mirrored/rotated on real hardware, flip the sign here (or in the consumer) --
    it's one constant, intentionally isolated."""
    dx = p1["x"] - p0["x"]
    dy = p1["y"] - p0["y"]
    return (90.0 - math.degrees(math.atan2(dy, dx))) % 360.0


def _signed_delta(a, b):
    """Smallest signed angle a->b in (-180, 180]. Positive = clockwise (right)."""
    return (b - a + 180.0) % 360.0 - 180.0


# -- Producer: replay a captured clean ----------------------------------------

def events_from_route(session, move_deg=MOVE_DEG, turn_deg=TURN_DEG, jump_factor=JUMP_FACTOR):
    """A routes.json session dict -> time-ordered list of action-trigger events.

    Timestamps are interpolated linearly over the session duration (cleaning_min),
    so the stream can be replayed against a synchronized clock. Direction comes
    purely from the {x,y} geometry (atan2), which is why replay -- not live -- is
    the source that can actually drive a stick/D-pad.
    """
    route = session.get("route") or []
    mins  = session.get("cleaning_min") or 0
    n     = len(route)
    duration = float(mins * 60) if mins else float(max(n - 1, 1))

    out = [_ev(0.0, START, {
        "kind":         session.get("kind"),
        "area_m2":      session.get("area_m2"),
        "cleaning_min": session.get("cleaning_min"),
        "session_id":   session.get("session_id"),
        "date":         session.get("date"),
    })]
    if session.get("pet"):
        # We only know a pet was seen *this clean* (per-clean boolean -- the data has
        # no detection time/location), so place one representative "encounter" at the
        # route midpoint: a real point on the path, ~halfway through. Sorted into the
        # stream by time below.
        if n >= 2:
            mid = n // 2
            out.append(_ev((mid / float(n - 1)) * duration, PET,
                           {"x": route[mid]["x"], "y": route[mid]["y"]}))
        else:
            out.append(_ev(0.0, PET, True))

    if n >= 2:
        # Median step length sets the reposition (path discontinuity) threshold.
        dists = [math.hypot(route[i]["x"] - route[i - 1]["x"],
                            route[i]["y"] - route[i - 1]["y"]) for i in range(1, n)]
        med = statistics.median(dists) if dists else 0.0
        jump_at = max(med * jump_factor, JUMP_MIN_MM)

        emit_brg = None   # last heading we re-aimed the stick to (MOVE gate)
        prev_brg = None   # previous step heading (TURN gate)
        for i in range(1, n):
            t = (i / (n - 1)) * duration
            d = dists[i - 1]
            if d >= jump_at:
                # A teleport in the path (segment break / relocalization): emit a
                # reposition trigger and reset heading so the jump isn't a "turn".
                out.append(_ev(t, REPOSITION, {"dist": int(d)}))
                emit_brg = None
                prev_brg = None
                continue
            if d <= 0:
                continue
            brg = _bearing(route[i - 1], route[i])
            # MOVE on a small true-heading drift -> the stick follows the path
            # smoothly. dir8 is still in the value for any D-pad consumer.
            if emit_brg is None or abs(_signed_delta(emit_brg, brg)) >= move_deg:
                rad = math.radians(90.0 - brg)  # back to math angle for the vector
                out.append(_ev(t, MOVE, {
                    "heading": int(round(brg)),
                    "dir8":    bucket_heading(brg),
                    "dx":      round(math.cos(rad), 3),
                    "dy":      round(math.sin(rad), 3),
                }))
                emit_brg = brg
            if prev_brg is not None and abs(_signed_delta(prev_brg, brg)) >= turn_deg:
                out.append(_ev(t, TURN, "right" if _signed_delta(prev_brg, brg) > 0 else "left"))
            prev_brg = brg

    out.append(_ev(duration, END, {"completed": bool(session.get("completed"))}))
    out.sort(key=lambda e: e["t"])   # PET sits mid-route, so re-order by time (stable)
    return out


# -- Producer: live state deltas ----------------------------------------------

def events_from_state(prev, cur, t=0.0):
    """Typed action triggers from a live state delta -- the button-mappable
    sibling of dreame_chat.motion_to_events. State dict:
        {"activity": str, "heading": int|None, "battery": int|None, "note": str}
    Note: the L40's live heading is None (pose undecoded), so MOVE won't fire live
    -- direction is a replay-only capability until map pose is decoded."""
    out = []
    if prev is None:
        out.append(_ev(t, STATE, cur.get("activity")))
    elif cur.get("activity") != prev.get("activity"):
        out.append(_ev(t, STATE, cur.get("activity")))

    if cur.get("activity") in ("cleaning", "returning"):
        cb = bucket_heading(cur.get("heading"))
        if cb and (prev is None or cb != bucket_heading(prev.get("heading"))):
            brg = cur.get("heading")
            rad = math.radians(90.0 - brg)
            out.append(_ev(t, MOVE, {
                "heading": int(brg), "dir8": cb,
                "dx": round(math.cos(rad), 3), "dy": round(math.sin(rad), 3),
            }))

    pb, cbatt = (prev or {}).get("battery"), cur.get("battery")
    if pb is not None and cbatt is not None and cbatt // 10 < pb // 10:
        out.append(_ev(t, BATTERY, cbatt))
    return out


# -- Helpers -------------------------------------------------------------------

def summarize(events):
    """{kind: count} over an event list -- a quick shape-check."""
    counts = {}
    for e in events:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    return counts


def iter_realtime(events, speed=1.0):
    """Yield events paced by their `t` deltas (a thin replay driver for whatever
    consumer comes next). speed>1 = faster than real time. Stdlib time import is
    local so importing this module stays side-effect free on constrained nodes."""
    import time
    t0 = None
    start = time.time()
    for e in events:
        if t0 is None:
            t0 = e["t"]
        target = (e["t"] - t0) / max(speed, 1e-6)
        wait = target - (time.time() - start)
        if wait > 0:
            time.sleep(wait)
        yield e


# -- Demo: capture the event stream from a real captured clean -----------------

if __name__ == "__main__":
    # python3 -m drive.dreame_events <routes.json> [session_id]
    import sys
    import json

    if len(sys.argv) < 2:
        print("usage: python3 -m drive.dreame_events "
              "<routes.json> [session_id]")
        sys.exit(1)

    blob = json.load(open(sys.argv[1]))
    sessions = blob.get("sessions", blob) if isinstance(blob, dict) else blob
    want = sys.argv[2] if len(sys.argv) > 2 else None

    sess = None
    if want:
        sess = next((s for s in sessions if str(s.get("session_id")) == want), None)
    else:
        # default to the most recent clean that actually has geometry
        with_route = [s for s in sessions if s.get("route")]
        sess = (with_route or sessions)[-1] if (with_route or sessions) else None

    if not sess:
        print("no matching session"); sys.exit(1)

    events = events_from_route(sess)
    print("session %s  %s  %s  %dmin  %dm2  route=%d pts" % (
        sess.get("session_id"), sess.get("date"), sess.get("kind"),
        sess.get("cleaning_min") or 0, sess.get("area_m2") or 0,
        len(sess.get("route") or [])))
    print("captured %d events: %s\n" % (len(events), summarize(events)))
    for e in events:
        print("  t=%7.1fs  %-11s %s" % (e["t"], e["kind"], e["value"]))
