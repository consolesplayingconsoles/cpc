#!/usr/bin/env python3
"""
pi/dreame_to_console.py -- launcher: a captured Dreame clean plays a console.

Wires the pipeline for the Pi node, mirroring batocera/dreame_to_wii_bridge.py:

    routes.json session
      -> cpc_python_core.bridges.dreame_events.events_from_route   (action triggers)
      -> cpc_python_core.controller.translate(., pi/mapping.json)   (translation logic)
      -> a Sink                                                     (Dolphin now, Pico later)

The mapping (this node's "translation logic") is pi/mapping.json. The translator
and sinks are generic and live in cpc_python_core. Default sink is PRINT (dry run,
no console needed); --sink dolphin streams to a Dolphin Pipe FIFO.

Examples:
  # dry-run the translation of the most-recent captured clean, fast:
  python3 pi/dreame_to_console.py ~/workspace/dreamehome-client/routes.json --speed 200
  # drive Dolphin live (start Dolphin first, Pipe controller named 'cpc'):
  python3 pi/dreame_to_console.py routes.json --sink dolphin --speed 1

Pure stdlib, ASCII.
"""
import os
import sys
import time
import json
import argparse

# The shared client lives at the repo root (same hop as the batocera launcher).
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "cpc-python-client"))

from cpc_python_core.bridges import dreame_events as events
from cpc_python_core import controller


def _pick_session(sessions, want):
    if want:
        return next((s for s in sessions if str(s.get("session_id")) == want), None)
    with_route = [s for s in sessions if s.get("route")]
    pool = with_route or sessions
    return pool[-1] if pool else None  # most recent with geometry


def main():
    ap = argparse.ArgumentParser(description="Dreame clean -> console controller")
    ap.add_argument("routes", help="path to routes.json")
    ap.add_argument("--session", help="session_id (default: most recent with a route)")
    ap.add_argument("--sink", choices=["print", "dolphin", "keyboard"], default="print")
    ap.add_argument("--pipe", default="cpc", help="Dolphin Pipe name (sink=dolphin)")
    ap.add_argument("--keys", choices=["arrows", "wasd"], default="arrows",
                    help="keyboard sink: which keys map to the stick (default arrows)")
    ap.add_argument("--mapping", default="dreame-to-gamecube",
                    help="shared mapping name (cpc_python_core/mappings) or a path")
    ap.add_argument("--speed", type=float, default=1.0, help=">1 = faster than real time")
    args = ap.parse_args()

    blob = json.load(open(args.routes))
    sessions = blob.get("sessions", blob) if isinstance(blob, dict) else blob
    sess = _pick_session(sessions, args.session)
    if not sess:
        print("[ERROR] no matching session in %s" % args.routes)
        return 1

    mapping = controller.load_mapping(args.mapping)
    evs = events.events_from_route(sess)
    print("[pi] session %s  %s  %dmin  %d events %s  sink=%s speed=%g" % (
        sess.get("session_id"), sess.get("date"), sess.get("cleaning_min") or 0,
        len(evs), events.summarize(evs), args.sink, args.speed))

    if args.sink == "dolphin":
        path = controller.dolphin_pipe_path(args.pipe)
        if not os.path.exists(path):
            print("[ERROR] no Dolphin pipe at %s" % path)
            print("        mkfifo it and set GC Port 1 device to 'Pipe/0/%s' in Dolphin first." % args.pipe)
            return 1
        print("[pi] opening Dolphin pipe %s (waiting for Dolphin to read)..." % path)
        sink = controller.DolphinPipeSink(path)
    elif args.sink == "keyboard":
        try:
            sink = controller.KeyboardSink(keyset=args.keys, button_keys=mapping.get("keys"))
        except Exception as exc:
            print("[ERROR] keyboard sink unavailable: %s" % exc)
            print("        pip install pynput, and grant this terminal Accessibility")
            print("        (System Settings > Privacy & Security > Accessibility).")
            return 1
        # Keys land in the FOCUSED window -- give the operator a moment to click
        # the emulator. Make sure its Control Stick is bound to the %s keys.
        for n in (4, 3, 2, 1):
            print("[pi] focus the emulator window... starting in %ds " % n)
            time.sleep(1)
    else:
        sink = controller.PrintSink()

    try:
        controller.drive(evs, mapping, sink, speed=args.speed)
    except KeyboardInterrupt:
        sink.release_all()
        print("\n[pi] stopped.")
    if hasattr(sink, "close"):
        sink.close()
    print("[pi] done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
