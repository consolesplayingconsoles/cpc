"""
engine.py -- the CPC drive engine.

Lifted verbatim from Pluto's api.py /control/drive handler so it can run as a
STANDALONE service on any node (Lab, Pi, C2). Behaviour is identical; the only
change is decoupling from Pluto's HTTP handler:

  * self._send(code, obj)      -> DriveEngine.handle() RETURNS (code, obj)
  * self.__class__.node_roster -> an injected `roster` (callable or dict)
  * module globals _drive_*     -> per-instance state (self._state / self._lock)

The engine resolves a SINK per target from the roster, so the SAME target drives
whatever hardware is local to the node running this engine. The mapping decides the
buttons; the engine only steers ops to a sink. Pure stdlib; controller.KeyboardSink
lazily imports pynput (Mac-lab only), so this imports fine on constrained nodes.
"""
import threading
import time

DRIVE_TIMEOUT = 6.0   # stop the drive if the client hasn't checked in for this long


class DriveEngine:
    def __init__(self, controller, dreame_events=None, roster=None):
        self._c = controller
        self._dreame = dreame_events
        # roster: a callable -> {node_id: {ENV..}} (so a live host can pass its
        # changing roster), or a plain dict. Provides pi HOST_IP/PI_BRIDGE_PORT and
        # roomba node HOST_IP for the networked sinks.
        self._roster = roster if callable(roster) else (lambda: (roster or {}))
        self._lock = threading.Lock()
        self._state = {"sink": None, "thread": None, "stop": None, "last_seen": 0.0,
                       "live_target": None, "live_dev": None}

    # ── drive lifecycle (the single-slot state machine) ──────────────────────
    def stop(self):
        with self._lock:
            st = self._state
            stop, th, sink = st["stop"], st["thread"], st["sink"]
            st["stop"] = st["thread"] = st["sink"] = None
            st["live_target"] = None
        if stop:
            stop.set()
        if th:
            th.join(timeout=1.0)
        if sink:
            try:
                sink.release_all()
            except Exception:
                pass

    def _play(self, events, mapping, sink, t0, speed):
        self.stop()
        stop = threading.Event()

        def run():
            try:
                self._c.drive_from(events, mapping, sink, t0=t0, speed=speed,
                                   should_stop=stop.is_set)
            except Exception as exc:
                print("  [drive] %s" % exc)
            finally:
                try:
                    sink.release_all()
                except Exception:
                    pass

        def watchdog():
            while not stop.wait(2.0):
                with self._lock:
                    current = self._state.get("stop") is stop
                    last = self._state.get("last_seen", 0.0)
                if not current:
                    return
                if time.time() - last > DRIVE_TIMEOUT:
                    self.stop()
                    return

        th = threading.Thread(target=run, daemon=True)
        with self._lock:
            self._state.update(sink=sink, thread=th, stop=stop, last_seen=time.time())
        th.start()
        threading.Thread(target=watchdog, daemon=True).start()

    # ── sink selection (per node, from the roster) ───────────────────────────
    def _make_sink(self, target, mapping, dev=None):
        """Open a FRESH sink for `target`. KEYBOARD is the local emulator sink (pynput);
        every other target drives a networked node from the roster. Raises ValueError
        (clean JSON error) on a bad/unreachable target."""
        if target == "keyboard":
            try:
                return self._c.KeyboardSink(button_keys=mapping.get("keys"))
            except Exception as exc:
                raise ValueError("keyboard sink: %s -- pip install pynput + grant the "
                                 "terminal Accessibility" % exc)
        roster = self._roster() or {}
        if target == "pi":
            pi_cfg = roster.get("pi") or {}
            host = (pi_cfg.get("HOST_IP") or "").strip()
            port = (pi_cfg.get("PI_BRIDGE_PORT") or "").strip()
            if not host or not port:
                raise ValueError("pi node has no HOST_IP/PI_BRIDGE_PORT in its .env")
            try:
                return self._c.NetworkSink(host, port, dev=dev)
            except Exception as exc:
                raise ValueError("can't reach the Pi receiver at %s:%s (%s) -- is the "
                                 "hub up (run.sh serve / cpc-hub.service)?" % (host, port, exc))
        if target == "roomba":
            node = roster.get(dev or "") or {}
            hostport = (node.get("HOST_IP") or "").strip()
            if not hostport:
                raise ValueError("roomba subtarget '%s' has no HOST_IP in its .env" % (dev or "?"))
            host, _, port_s = hostport.rpartition(":")
            if not host:
                host, port_s = hostport, "7724"
            cmd_port = int(port_s) + 1
            try:
                return self._c.RoombaSink(host, cmd_port, mapping.get("actions"))
            except Exception as exc:
                raise ValueError("can't reach the roomba command stream at %s:%d (%s) -- "
                                 "is the firmware (v17+) running?" % (host, cmd_port, exc))
        raise ValueError("unknown target: %s" % target)

    def _live_ensure(self, target, mapping, dev=None):
        """A PERSISTENT live-input sink held across keydowns, with a watchdog that
        releases everything if the client goes quiet. Reuses the single state slot."""
        with self._lock:
            sink = self._state.get("sink")
            if sink is not None and self._state.get("live_target") == target and self._state.get("live_dev") == dev:
                self._state["last_seen"] = time.time()
                return sink
        self.stop()
        sink = self._make_sink(target, mapping, dev=dev)
        stop = threading.Event()

        def watchdog():
            while not stop.wait(2.0):
                with self._lock:
                    current = self._state.get("stop") is stop
                    last = self._state.get("last_seen", 0.0)
                if not current:
                    return
                if time.time() - last > DRIVE_TIMEOUT:
                    self.stop()
                    return

        with self._lock:
            self._state.update(sink=sink, thread=None, stop=stop,
                               last_seen=time.time(), live_target=target, live_dev=dev)
        threading.Thread(target=watchdog, daemon=True).start()
        return sink

    def _mapping(self, body, src_default, map_default):
        return self._c.load_mapping(body.get("source") or src_default,
                                    body.get("mapping") or map_default)

    # ── per-action handlers (return (code, dict)) ────────────────────────────
    def _do_hold(self, body):
        try:
            mapping = self._mapping(body, "keyboard", "")
        except Exception as exc:
            return 200, {"ok": False, "error": "mapping: %s" % exc}
        btn = body.get("btn") or (mapping.get("controls") or {}).get(body.get("key") or "")
        if not btn:
            return 200, {"ok": True, "ignored": body.get("key")}
        try:
            sink = self._live_ensure(body.get("target"), mapping, dev=body.get("dev"))
        except ValueError as exc:
            return 200, {"ok": False, "error": str(exc)}
        op = "press" if body.get("down") else "release"
        try:
            sink.apply([{"op": op, "btn": btn}])
        except Exception as exc:
            return 200, {"ok": False, "error": "%s: %s" % (op, exc)}
        return 200, {"ok": True, op: btn}

    def _do_axis(self, body):
        try:
            mapping = self._mapping(body, "keyboard", "")
        except Exception as exc:
            return 200, {"ok": False, "error": "mapping: %s" % exc}
        try:
            sink = self._live_ensure(body.get("target"), mapping, dev=body.get("dev"))
        except ValueError as exc:
            return 200, {"ok": False, "error": str(exc)}
        try:
            x = float(body.get("x", 0.5)); y = float(body.get("y", 0.5))
        except (TypeError, ValueError):
            return 200, {"ok": False, "error": "axis x/y must be numbers"}
        name = body.get("name") or "MAIN"
        try:
            sink.apply([{"op": "axis", "name": name, "x": x, "y": y}])
        except Exception as exc:
            return 200, {"ok": False, "error": "axis: %s" % exc}
        return 200, {"ok": True, "axis": name}

    def _do_press(self, body):
        try:
            mapping = self._mapping(body, "dreame", "gamecube_dpad")
        except Exception as exc:
            return 200, {"ok": False, "error": "mapping: %s" % exc}
        btn = body.get("btn") or (mapping.get("controls") or {}).get(body.get("key") or "")
        if not btn:
            return 200, {"ok": True, "ignored": body.get("key")}
        ops = [{"op": "pulse", "btn": btn, "ms": int(body.get("ms") or 120)}]
        with self._lock:
            live = self._state.get("sink")
        if live is not None:                       # inject into the running drive
            try:
                live.apply(ops)
                return 200, {"ok": True, "pressed": btn, "via": "live"}
            except Exception as exc:
                return 200, {"ok": False, "error": "press: %s" % exc}
        try:                                       # no drive -> transient link
            sink = self._make_sink(body.get("target"), mapping, dev=body.get("dev"))
        except ValueError as exc:
            return 200, {"ok": False, "error": "can't reach target (%s)" % exc}
        try:
            sink.apply(ops)
        finally:
            try:
                sink.release_all()
            except Exception:
                pass
        return 200, {"ok": True, "pressed": btn, "via": "transient"}

    def _do_play(self, body):
        target = body.get("target")
        if target not in ("keyboard", "pi"):
            return 200, {"ok": False, "error": "unknown target: %s" % target}
        if self._dreame is None:
            return 200, {"ok": False, "error": "replay unavailable on this drive node"}
        try:
            mapping = self._mapping(body, "dreame", "gamecube_dpad")
        except Exception as exc:
            return 200, {"ok": False, "error": "mapping: %s" % exc}
        speed = float(body.get("speed") or 1.0)
        try:
            if target == "pi":
                sink = self._make_sink("pi", mapping, dev=body.get("dev"))
            else:
                # base movement duty (mapping) scaled by speed, capped at full tilt.
                eff_duty = min(1.0, float(mapping.get("move_duty", 1.0)) * max(speed, 1e-6))
                sink = self._c.KeyboardSink(keyset="arrows", button_keys=mapping.get("keys"),
                                            move_duty=eff_duty)
        except ValueError as exc:
            return 200, {"ok": False, "error": str(exc)}
        except Exception as exc:
            return 200, {"ok": False, "error": "keyboard sink: %s -- pip install pynput" % exc}
        events = self._dreame.events_from_route(body.get("session") or {})
        if not events:
            return 200, {"ok": False, "error": "no route in session"}
        self._play(events, mapping, sink, float(body.get("t") or 0.0), speed)
        print("  [drive] play target=%s t=%.1f speed=%g events=%d" % (
            target, float(body.get("t") or 0.0), speed, len(events)))
        return 200, {"ok": True, "events": len(events), "target": target}

    # ── entry point ──────────────────────────────────────────────────────────
    def handle(self, body):
        """A /control/drive request body -> (http_code, response_dict). Mirrors the
        old _handle_drive dispatch exactly."""
        action = (body or {}).get("action")
        if action in ("pause", "stop"):
            self.stop()
            return 200, {"ok": True}
        if action == "keepalive":
            with self._lock:
                self._state["last_seen"] = time.time()
                live = self._state.get("sink")
            if live is not None:
                try:
                    live.keepalive()
                except Exception:
                    pass
            return 200, {"ok": True}
        if action == "press":
            return self._do_press(body)
        if action == "hold":
            return self._do_hold(body)
        if action == "axis":
            return self._do_axis(body)
        if action == "play":
            return self._do_play(body)
        return 400, {"error": "unknown action"}
