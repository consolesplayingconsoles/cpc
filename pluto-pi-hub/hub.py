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
import threading


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


def _sync_server(cfg, stop):
    """Minimal HTTP server on PI_SYNC_PORT: accepts POST /sync from Pluto and
    delegates to the appropriate sync handler. Runs in a daemon thread alongside
    the op receiver. Pure stdlib, 3.6-safe."""
    import http.server
    import json as _json

    sync_port = int((cfg.get("PI_SYNC_PORT") or "7721").strip())

    class SyncHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_): pass   # silence access log

        def do_GET(self):
            if self.path != "/health":
                self.send_response(404); self.end_headers(); return
            up = bool(_discover_vmu())
            self.send_response(200 if up else 503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write((_json.dumps({"vmu": up})).encode())

        def do_POST(self):
            try:
                if self.path != "/sync":
                    self.send_response(404); self.end_headers(); return
                length = int(self.headers.get("Content-Length", 0))
                body = _json.loads(self.rfile.read(length).decode()) if length else {}
                action = (body.get("action") or "sync").strip()
                target = (body.get("target") or "").strip()
                dropbox_path = (body.get("dropbox_path") or "").strip()
                reply = _handle_sync(action, target, cfg, dropbox_path=dropbox_path)
            except Exception as exc:
                reply = {"error": "sync handler crashed: %s" % exc}
            data = _json.dumps(reply).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    srv = http.server.HTTPServer(("0.0.0.0", sync_port), SyncHandler)
    srv.timeout = 1.0
    print("CPC Pi-Hub sync server up -- :%d" % sync_port)
    while not stop["flag"]:
        srv.handle_request()
    srv.server_close()


def _handle_sync(action, target, cfg, dropbox_path=""):
    """Dispatch a sync/list request. Returns {"message": ...} or {"error": ...}."""
    if not target:
        return {"error": "no target specified -- try @dropbox %s @vmu" % action}
    if target == "vmu":
        if action == "console-list":
            return _console_list_vmu()
        return _sync_vmu(cfg, dropbox_path=dropbox_path)
    return {"error": "target '%s' is not implemented yet." % target}


def _parse_vmu_image(data, _struct):
    """Parse the VMU filesystem from a raw 128KB VMU image (VMU0.BIN).
    Returns a list of human-readable save entries, same info potato-tool view shows.

    VMU block layout (each block = 512 bytes):
      255: root/superblock -- filesystem geometry
      254: FAT (1 block)
      241-253: directory (13 blocks, read high-to-low)
      0-240: user data
    Directory entry (32 bytes each, 200 entries):
      0:    file type (0x33=data, 0xCC=game)
      1:    copy protect
      2-3:  first block
      4-15: filename (ASCII)
      16-23: creation timestamp (BCD)
      24-25: size in blocks
      26-27: header offset
    """
    BLOCK = 512
    FILE_TYPES = {0x33: "data", 0xCC: "game"}

    def block(n):
        return data[n * BLOCK:(n + 1) * BLOCK]

    root = block(255)
    fat_loc  = _struct.unpack_from("<H", root, 0x18)[0]
    dir_loc  = _struct.unpack_from("<H", root, 0x1C)[0]
    dir_sz   = _struct.unpack_from("<H", root, 0x1E)[0]

    # fall back to standard VMU layout if root is uninitialised (all 0x00 or 0x55)
    if dir_loc == 0 or dir_loc >= 256 or dir_sz == 0:
        fat_loc, dir_loc, dir_sz = 254, 253, 13

    dir_data = b""
    for i in range(dir_sz):
        dir_data += block(dir_loc - i)

    entries = []
    for i in range(200):
        e = dir_data[i * 32:(i + 1) * 32]
        if len(e) < 32:
            break
        ftype = e[0]
        if ftype not in FILE_TYPES:
            continue
        fname = e[4:16].decode("ascii", errors="replace").rstrip()
        size  = _struct.unpack_from("<H", e, 24)[0]
        tname = FILE_TYPES[ftype]
        entries.append("%s (%s, %d blocks)" % (fname, tname, size))
    return entries


def _transfer_vmu():
    """Copy VMU0.BIN from the DreamPicoPort reader (/dev/sda) to the active VMU
    pendrive (/dev/sdb). Both are FAT volumes. Mounts each in turn, copies the
    file, then unmounts. Requires sudoers entry for mount/umount of /dev/sd*."""
    import subprocess as _sp, os as _os, glob as _glob, shutil as _sh
    if not _discover_vmu():
        return {"error": "DreamPicoPort not found -- is the reader plugged in?"}
    devs = sorted(_glob.glob("/dev/sd?"))
    if len(devs) < 2:
        return {"error": "need 2 block devices (reader + active VMU pendrive), found: %s" % devs}
    src_dev, dst_dev = devs[0], devs[1]
    src_mnt, dst_mnt = "/tmp/cpc-vmu-src", "/tmp/cpc-vmu-dst"
    for d in (src_mnt, dst_mnt):
        _os.makedirs(d, exist_ok=True)
    try:
        r = _sp.run(["sudo", "mount", "-t", "vfat", "-o", "ro", src_dev, src_mnt],
                    capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return {"error": "mount source failed: %s" % r.stderr.strip()}
        r = _sp.run(["sudo", "mount", "-t", "vfat", dst_dev, dst_mnt],
                    capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            _sp.run(["sudo", "umount", src_dev], timeout=5, capture_output=True)
            return {"error": "mount target failed: %s" % r.stderr.strip()}
        src_file = _os.path.join(src_mnt, "VMU0.BIN")
        dst_file = _os.path.join(dst_mnt, "VMU0.BIN")
        if not _os.path.exists(src_file):
            return {"error": "VMU0.BIN not found on reader."}
        size = _os.path.getsize(src_file)
        _sh.copy2(src_file, dst_file)
        return {"message": "transfer done: copied VMU0.BIN (%d bytes) from %s to %s." % (size, src_dev, dst_dev)}
    except Exception as exc:
        return {"error": "transfer failed: %s" % exc}
    finally:
        _sp.run(["sudo", "umount", src_dev], timeout=5, capture_output=True)
        _sp.run(["sudo", "umount", dst_dev], timeout=5, capture_output=True)


def _console_list_vmu():
    """List save files on the VMU exposed by DreamPicoPort.
    The device only serves metadata sectors (boot/FAT/dir) over raw USB --
    data sectors return EIO. Mount via udisksctl (no sudo) to read VMU0.BIN,
    then parse the VMU filesystem image."""
    import struct as _struct, glob as _glob, subprocess as _sp, os as _os
    if not _discover_vmu():
        return {"error": "VMU not found -- is the DreamPicoPort plugged in?"}
    candidates = sorted(_glob.glob("/dev/sd?"))
    if not candidates:
        return {"error": "DreamPicoPort on bus but no block device found."}
    dev = candidates[0]
    mnt = None
    try:
        mnt = "/tmp/cpc-vmu"
        _os.makedirs(mnt, exist_ok=True)
        r = _sp.run(["sudo", "mount", "-t", "vfat", "-o", "ro", dev, mnt],
                    capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return {"error": "mount failed: %s" % r.stderr.strip()}

        vmu_path = _os.path.join(mnt, "VMU0.BIN")
        if not _os.path.exists(vmu_path):
            return {"error": "VMU0.BIN not found at %s" % vmu_path}
        with open(vmu_path, "rb") as vf:
            vmu_bin = vf.read()

        saves = _parse_vmu_image(vmu_bin, _struct)
        if not saves:
            return {"message": "VMU is empty (no save files)."}
        lines = ["VMU saves (%d):" % len(saves)] + ["  " + s for s in saves]
        return {"message": "\n".join(lines)}
    except Exception as exc:
        import traceback as _tb
        return {"error": "VMU read failed: %s | %s" % (exc, _tb.format_exc().splitlines()[-3])}
    finally:
        if mnt:
            _sp.run(["sudo", "umount", dev], timeout=5, capture_output=True)


def _discover_vmu():
    """Return True if the VMU USB reader (DreamPicoPort) is present on the Pi's bus."""
    import subprocess
    try:
        out = subprocess.check_output(["lsusb"], timeout=3).decode()
        return "DreamPicoPort" in out
    except Exception:
        return False


def _sync_vmu(cfg, dropbox_path=""):
    """Sync VMU data to Dropbox. dropbox_path is passed in from the Pluto request."""
    if not dropbox_path:
        return {"error": "no dropbox_path in request -- Pluto must provide it."}

    results = []

    # -- VMU via USB reader ---------------------------------------------------
    vmu_dev = _discover_vmu()
    if vmu_dev:
        try:
            out_dir = os.path.join(dropbox_path, "dc", "vmu")
            os.makedirs(out_dir, exist_ok=True)
            results.append("VMU: not implemented yet (device: %s)." % vmu_dev)
        except Exception as exc:
            results.append("VMU: error -- %s" % exc)
    else:
        results.append("VMU: no USB block device found, skipped.")

    # -- DreamShell / DreamPi -------------------------------------------------
    results.append("DreamShell: not implemented yet.")

    return {"message": " | ".join(results)}


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

    threading.Thread(target=_sync_server, args=(cfg, stop), daemon=True).start()

    # Lens trigger: watch DC controller evdev devices, forward all buttons via HidBridge,
    # fire grab -> scan -> translate-last on L+R. Needs PLUTO_IP to be set in the .env.
    pluto_ip = (cfg.get("PLUTO_IP") or "").strip()
    lens = None
    if pluto_ip:
        from bridges.lens import LensTrigger
        lens = LensTrigger("http://%s:7700" % pluto_ip, bridges).start()
    else:
        print("  lens trigger disabled (no PLUTO_IP in .env)")

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
        if lens:
            lens.stop()
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
