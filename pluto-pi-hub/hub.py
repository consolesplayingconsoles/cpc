#!/usr/bin/env python3
"""
hub.py -- CPC Pi-Hub entrypoint (SCAFFOLD).

The Pi-Hub is NOT a Pluto instance and NOT a webserver. It is a small set of
purpose-built, single-purpose BRIDGE processes that let consoles which never
spoke TCP/IP reach the network: HID over UART to a Pico, per-console serial
transports, DreamPi for the Dreamcast. The Lab/C2 Pluto instances manage these
bridges remotely as a C2 feature; this process is the thing they manage, not a
peer instance of Pluto.

Two entrypoints:
  hub.py <env>          -- report what this node's .env configures (the scaffold).
  hub.py serve <env>    -- the ALWAYS-UP op receiver: listen on PI_BRIDGE_PORT,
                           accept Pluto's controller-op stream, and frame each op to
                           the Pico via the controller bridge. Run under systemd
                           (deploy/cpc-hub.service); a redeploy's `systemctl restart`
                           SIGTERMs the running one so it releases the UART + port
                           before the fresh one binds them.

The Pi only LISTENS here -- Pluto dials in. Pure stdlib, 3.6-safe, ASCII output only.
"""
import os
import sys
import time


def load_env(path):
    """Minimal .env parser (stdlib, 3.6). Same shape as the client's env.load_env."""
    cfg = {}
    if path and os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                cfg[k.strip()] = v.strip()
    return cfg


def parse_pico(value):
    """A PICO_<chipid> .env value -> a fields dict. Accepts 'role=hid,conn=uart,
    dev=...,baud=...' or the bare role shorthand 'hid'. (Mirrors propagate.py.)"""
    value = (value or "").strip()
    if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
        value = value[1:-1].strip()        # tolerate a quoted .env value
    if "=" not in value:
        return {"role": value} if value else {}
    out = {}
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition("=")
        out[k.strip()] = v.strip()
    return out


# Bridges are built from the node .env -- config decides which exist. Each exposes
# start()/stop()/status(); the Phase-2 supervisor wires an op source into them.
def build_bridges(cfg):
    """One controller bridge per UART-connected Pico. A UART is one TX/RX pin set =
    one board, so device + baud come from THAT Pico's line (PICO_<chipid>=...,conn=uart,
    dev=...,baud=...), not a node-global. baud defaults to 115200; dev is required."""
    bridges = []
    from bridges.hid import HidBridge
    pluto_ip = (cfg.get("PLUTO_IP") or "").strip()
    pluto_url = ("http://%s:7700" % pluto_ip) if pluto_ip else ""
    for k in sorted(cfg):
        if not k.startswith("PICO_"):
            continue
        spec = parse_pico(cfg[k])
        if (spec.get("conn") or "").lower() != "uart":
            continue                            # USB Picos aren't driven over a tty here
        dev = spec.get("dev")
        if not dev:
            print("  [skip] %s: conn=uart but no dev= on its line" % k)
            continue
        bridges.append(HidBridge(dev, spec.get("baud") or "115200", pluto_url=pluto_url))
    return bridges


# -- op receiver (the always-up bridge) ---------------------------------------
# Match Pluto's DRIVE_TIMEOUT: if the op stream goes silent this long (Pluto crashed
# mid-drive, link wedged), neutralise the pad so a dead link can't leave inputs held.
IDLE_TIMEOUT = 6.0


def _pump(conn, bridges, stop):
    """Read newline-delimited JSON op-lists off one connection and apply them to the
    bridges until the client closes (or SIGTERM). Each op-list is ROUTED by the `dev`
    the API tags onto its ops (multi-Pico); untagged or an unknown dev -> the first
    bridge (back-compat single-pico path). A blank line is a keepalive. On prolonged
    silence, release everything once (dead-man's switch); on any data, re-arm. Always
    releases on the way out so a dropped link can't leave keys held."""
    import json
    import socket
    by_dev = {b.device: b for b in bridges}
    default = bridges[0]
    conn.settimeout(1.0)                    # so SIGTERM + the idle check are noticed
    buf = b""
    last = time.time()
    released = False
    try:
        while not stop["flag"]:
            try:
                chunk = conn.recv(4096)
            except socket.timeout:
                if time.time() - last > IDLE_TIMEOUT:
                    # Stale client: neutralise AND drop the connection so the single
                    # accept slot frees up -- otherwise a lingering press-and-hold sink
                    # squats it and every NEW drive (incl. the UI's) silently can't get
                    # in. The real sink reconnects on its next op (_live_ensure remakes).
                    for b in bridges:
                        b.release_all()
                    break
                continue
            if not chunk:
                break                       # client closed the connection
            last = time.time()
            released = False
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue                # keepalive
                try:
                    ops = json.loads(line.decode("ascii"))
                except (ValueError, UnicodeDecodeError):
                    continue                # ignore a garbled line, stay up
                if ops:
                    # Route by the dev the API tagged onto the ops; untagged/unknown -> first.
                    dev = ops[0].get("dev") if isinstance(ops[0], dict) else None
                    (by_dev.get(dev, default)).apply(ops)
    finally:
        for b in bridges:
            b.release_all()
        try:
            conn.close()
        except Exception:
            pass


def serve(cfg):
    """Always-up op receiver: bind PI_BRIDGE_PORT, accept ONE Pluto client at a time,
    and stream its ops into the controller bridge. SIGTERM-clean so a redeploy's
    `systemctl restart` hands the UART + the listen port to the next instance."""
    import signal
    import socket

    port = cfg.get("PI_BRIDGE_PORT", "").strip()
    if not port:
        print("\n  ERROR: serve needs PI_BRIDGE_PORT in the node .env\n")
        return 2
    port = int(port)

    bridges = build_bridges(cfg)
    if not bridges:
        print("  serve: no controller bridge (no UART Pico in the .env) -- nothing to drive")
        return 0
    for b in bridges:            # start ALL: the op stream routes to each by its dev
        b.start()                           # opens the UART, sends a neutral frame

    stop = {"flag": False}
    def _term(*_):
        stop["flag"] = True
    signal.signal(signal.SIGTERM, _term)
    signal.signal(signal.SIGINT, _term)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)   # quick restart, no TIME_WAIT stall
    srv.bind(("0.0.0.0", port))
    srv.listen(1)
    srv.settimeout(1.0)                     # so SIGTERM is noticed between accepts
    print("CPC Pi-Hub op receiver up -- :%d -> %s" % (
        port, ", ".join("%s(%s)" % (b.name, b.device) for b in bridges)))
    try:
        while not stop["flag"]:
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            print("  client %s:%d connected" % addr)
            _pump(conn, bridges, stop)
            print("  client gone -- released")
    finally:
        for b in bridges:
            try:
                b.stop()
            except Exception:
                pass
        srv.close()
    return 0


def main(argv):
    args = argv[1:]
    serve_mode = bool(args) and args[0] == "serve"
    if serve_mode:
        args = args[1:]
    env_path = args[0] if args else ""
    cfg = load_env(env_path)

    if serve_mode:
        return serve(cfg)

    name = cfg.get("NODE_NAME", "Pi-Hub")
    bridges = build_bridges(cfg)
    print("CPC Pi-Hub -- %s" % name)
    print("  env    : %s" % (env_path or "(none)"))
    print("  bridges: %d configured" % len(bridges))
    for b in bridges:
        print("    - %s" % b.name)
    if not bridges:
        print("  scaffold: no bridges configured (add a PICO_<chipid>=...,conn=uart,dev=... line)")
        return 0
    print("  run 'hub.py serve %s' to start the op receiver" % (env_path or "<env>"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
