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


# HTTP routes of the sync server -- the source of truth the dispatch checks AND
# scripts/check_openapi_drift.py reads (vs openapi.yaml). (METHOD, path). The raw
# controller-op TCP stream on PI_BRIDGE_PORT is a separate, non-HTTP protocol.
SYNC_ROUTES = {("GET", "/health"), ("POST", "/sync")}


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
            if ("GET", self.path) not in SYNC_ROUTES:
                self.send_response(404); self.end_headers(); return
            up = bool(_discover_vmu())
            self.send_response(200 if up else 503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write((_json.dumps({"vmu": up})).encode())

        def do_POST(self):
            try:
                if ("POST", self.path) not in SYNC_ROUTES:
                    self.send_response(404); self.end_headers(); return
                length = int(self.headers.get("Content-Length", 0))
                body = _json.loads(self.rfile.read(length).decode()) if length else {}
                action = (body.get("action") or "sync").strip()
                target = (body.get("target") or "").strip()
                text = body.get("text") or ""
                ctl_byte = body.get("byte")
                reply = _handle_sync(action, target, cfg, text=text, byte=ctl_byte,
                                     label=(body.get("label") or "").strip(),
                                     sub_path=(body.get("path") or "").strip(),
                                     exts=body.get("exts"))
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


# genesis datalink: hold the Pico serial open, CACHE the MD liveness it PUSHES (the Pico
# watches SELECT and emits md:on/md:off on change, so the hub never polls), and own the
# write handle for commands. _genesis_health_server serves the cache on its own port.
# mode tracks the last MODE: we sent the Pico so we only switch on a real transition (opening
# the Control tab, or going back to chat) -- never in the streaming hot path. Cleared on
# (re)connect so a freshly-booted Pico (which boots to DATA) gets re-synced on the next write.
_GENESIS = {"ser": None, "md_on": False, "mode": None, "streaming": False}


def _datalink_chip(cfg):
    for k, v in cfg.items():
        if k.startswith("PICO_") and "datalink" in (v or "").lower():
            return k[len("PICO_"):]
    return None


def _ensure_mode(ser, desired):
    """Send MODE:<desired> only if the Pico isn't already there. The action type IS the tab
    intent: datalink writes -> DATA, control writes -> CTRL."""
    if _GENESIS.get("mode") != desired:
        ser.write(("MODE:%s\n" % desired).encode())
        _GENESIS["mode"] = desired


def _datalink_write(cfg, text):
    """Write a datalink command line to the genesis Pico via the held-open serial; the Pico
    reads it off stdin and frames it onto the Mega Drive. Ensures DATA mode first."""
    ser = _GENESIS.get("ser")
    if not ser:
        return {"error": "datalink pico not connected"}
    try:
        _ensure_mode(ser, "DATA")
        ser.write((text + "\n").encode("utf-8", "replace"))
    except Exception as exc:
        return {"error": "datalink write failed: %s" % exc}
    return {"message": "sent to genesis: %s" % text}


def _datalink_write_byte(cfg, b):
    """Write ONE control byte to the genesis Pico (controller mode) as a hex line, latest-wins.
    Ensures CTRL mode first (idempotent, so only the first byte after a tab switch costs the
    MODE: line -- the rest are just the pad state)."""
    ser = _GENESIS.get("ser")
    if not ser:
        return {"error": "datalink pico not connected"}
    try:
        b = int(b) & 0xFF
    except (TypeError, ValueError):
        return {"error": "control byte must be an int 0-255"}
    try:
        _ensure_mode(ser, "CTRL")
        ser.write(("%02X\n" % b).encode())
    except Exception as exc:
        return {"error": "control write failed: %s" % exc}
    return {"message": "genesis control: 0x%02X" % b}


def _vgm_psg_events(path):
    """Parse a .vgm/.vgz into [(delay_samples_before, psg_byte), ...] -- just the SN76489
    (PSG) writes, with the VGM's own inter-write timing (44100 samples/sec). Pure stdlib."""
    import gzip
    d = open(path, "rb").read()
    if d[:2] == b"\x1f\x8b":
        d = gzip.decompress(d)
    if d[:4] != b"Vgm ":
        return None
    ver = int.from_bytes(d[8:12], "little")
    dat = 0x40
    if ver >= 0x150:
        rel = int.from_bytes(d[0x34:0x38], "little")
        dat = 0x34 + rel if rel else 0x40
    i = dat; n = len(d); pending = 0; ev = []
    while i < n:
        c = d[i]
        if c == 0x50:                              # SN76489 write
            ev.append((pending, d[i + 1])); pending = 0; i += 2
        elif c == 0x61:                            # wait NN samples
            pending += int.from_bytes(d[i + 1:i + 3], "little"); i += 3
        elif c == 0x62: pending += 735; i += 1     # wait 1/60s
        elif c == 0x63: pending += 882; i += 1     # wait 1/50s
        elif 0x70 <= c <= 0x7f: pending += (c & 0xf) + 1; i += 1
        elif c == 0x66: break                      # end of data
        elif c in (0x52, 0x53, 0x54): i += 3       # YM2612/YM2151 (skipped: PSG only)
        elif c == 0x67:                            # data block
            sz = int.from_bytes(d[i + 3:i + 7], "little"); i += 7 + sz
        elif 0x51 <= c <= 0x5f: i += 3
        elif 0xa0 <= c <= 0xbf: i += 3
        elif 0x80 <= c <= 0x8f: i += 1
        else: i += 1
    return ev


def _psg_stream_file(cfg, name):
    """Stream a VGM's PSG track to the genesis Pico, paced to the VGM's own timing. The Pico
    opens one OP_PSG frame and the ROM's tight loop writes each byte to the chip. Runs in a
    background thread (a song is ~20s+) with an absolute timeline so it doesn't drift."""
    ser = _GENESIS.get("ser")
    if not ser:
        return {"error": "datalink pico not connected"}
    if _GENESIS.get("streaming"):
        return {"error": "already streaming -- one song at a time"}
    music_dir = (cfg.get("MUSIC_DIR") or "/opt/cpc/music-lib").strip()
    path = name if os.path.isabs(name) else os.path.join(music_dir, name)
    if not os.path.exists(path):
        return {"error": "no such song: %s" % path}
    try:
        ev = _vgm_psg_events(path)
    except Exception as exc:
        return {"error": "vgm parse failed: %s" % exc}
    if not ev:
        return {"error": "no PSG data in %s" % os.path.basename(path)}

    def run():
        _GENESIS["streaming"] = True
        try:
            _ensure_mode(ser, "DATA")
            ser.write(b"/psgstream\n")
            time.sleep(0.05)
            t0 = time.monotonic(); samples = 0
            for delay, b in ev:
                samples += delay
                target = t0 + samples / 44100.0
                dt = target - time.monotonic()
                if dt > 0:
                    time.sleep(dt)
                ser.write(("%02X" % b).encode())
            ser.write(b"X")             # end the stream -> ROM closes the frame
        except Exception as exc:
            print("psgstream: %s" % exc)
        finally:
            _GENESIS["streaming"] = False

    threading.Thread(target=run, daemon=True).start()
    return {"message": "streaming %d PSG writes from %s" % (len(ev), os.path.basename(path))}


def _song_files(cfg):
    """(music_dir, sorted [filenames]) of the playable tracks. The sort order is the index
    the ROM's REQ_PLAY refers to, so listing and playing must use this same order."""
    music_dir = (cfg.get("MUSIC_DIR") or "/opt/cpc/music-lib").strip()
    try:
        files = sorted(f for f in os.listdir(music_dir)
                       if f.lower().endswith((".vgz", ".vgm")))
    except OSError:
        files = []
    return music_dir, files


def _display_name(fn):
    """A filename -> a short track title for the MD menu: drop the extension and any
    'Artist - NN - ' prefix, keeping the last ' - ' segment."""
    base = fn.rsplit(".", 1)[0]
    parts = base.split(" - ")
    return parts[-1] if len(parts) >= 2 else base


def _handle_md_cmd(cfg, line):
    """A command the ROM drove back to us (relayed by the Pico over USB). MD:LIST -> reply
    with the track names; MD:PLAY:<n> -> stream the n-th track."""
    ser = _GENESIS.get("ser")
    if not ser:
        return
    if line == "MD:LIST":
        _, files = _song_files(cfg)
        names = "|".join(_display_name(f) for f in files)
        ser.write(("/mdlist %s\n" % names).encode("utf-8", "replace"))
        print("genesis: sent list (%d tracks)" % len(files))
    elif line.startswith("MD:PLAY:"):
        try:
            idx = int(line[len("MD:PLAY:"):])
        except ValueError:
            return
        _, files = _song_files(cfg)
        if 0 <= idx < len(files):
            print("genesis: MD play #%d -> %s" % (idx, files[idx]))
            _psg_stream_file(cfg, files[idx])


def _genesis_manager(cfg, stop):
    """Hold the genesis Pico's serial open: cache the md:on/md:off it pushes, relay the
    MD's REQ_LIST/REQ_PLAY commands, reconnect if the board drops."""
    import glob as _glob
    chip = _datalink_chip(cfg)
    if not chip:
        return
    while not stop["flag"]:
        hits = _glob.glob("/dev/serial/by-id/*%s*" % chip)
        if not hits:
            _GENESIS["ser"] = None; _GENESIS["md_on"] = False; _GENESIS["mode"] = None
            time.sleep(2); continue
        dev = os.path.realpath(hits[0])
        try:
            import serial
            ser = serial.Serial(dev, 115200, timeout=1)
            _GENESIS["ser"] = ser; _GENESIS["mode"] = None   # re-sync mode on the next write
            print("genesis datalink: %s open, watching MD liveness" % dev)
            while not stop["flag"]:
                line = ser.readline().decode("utf-8", "replace").strip()
                if line == "md:on":
                    _GENESIS["md_on"] = True
                elif line == "md:off":
                    _GENESIS["md_on"] = False
                elif line.startswith("MD:"):
                    _handle_md_cmd(cfg, line)
        except Exception as exc:
            print("genesis datalink: serial dropped (%s), retrying" % exc)
        finally:
            _GENESIS["ser"] = None; _GENESIS["md_on"] = False; _GENESIS["mode"] = None
        time.sleep(2)


def _genesis_health_server(cfg, stop):
    """Own-port health for the megadrive node: 200 when the console is on (the last
    pushed md state), 503 when off. Pluto probes GET /health here via HOST_IP=<pi>:<port>."""
    import http.server
    import json as _json
    port = int((cfg.get("PI_MD_HEALTH_PORT") or "7722").strip())

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_GET(self):
            up = bool(_GENESIS.get("md_on"))
            self.send_response(200 if up else 503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(_json.dumps({"md": "on" if up else "off"}).encode())

    srv = http.server.HTTPServer(("0.0.0.0", port), H)
    srv.timeout = 1.0
    print("genesis health server up -- :%d" % port)
    while not stop["flag"]:
        srv.handle_request()
    srv.server_close()


def _handle_sync(action, target, cfg, text="", byte=None, label="", sub_path="", exts=None):
    """Dispatch a sync/list request. Returns {"message": ...} or {"error": ...}."""
    if action == "datalink":
        return _datalink_write(cfg, text)
    if action == "control":
        return _datalink_write_byte(cfg, byte)
    if action == "psgstream":
        return _psg_stream_file(cfg, text or label)
    if not target:
        return {"error": "no target specified -- try @dropbox %s @vmu" % action}
    if target == "sd":
        if action == "labels":
            return _sd_labels()
        if action == "scan":
            return _sd_scan(label)
        if action == "collect":
            return _sd_collect(label, exts)
        if action == "eject":
            return _sd_eject(label)
        return _sd_inspect(label, sub_path)
    if target == "vmu":
        if action == "console-list":
            return _console_list_vmu()
        if action == "read-image":
            return _read_vmu_image()
        return {"error": "unknown vmu action '%s' -- try console-list or read-image" % action}
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


def _blkid_labels():
    """{label: device} for every attached volume, straight from blkid.

    /dev/disk/by-label is NOT sufficient on its own: udev only makes a symlink for a
    proper volume-label directory entry, so a card carrying only a FAT BOOT-SECTOR label
    (blkid reports it as LABEL_FATBOOT -- a real GDEMU card does exactly this) is
    completely invisible there while being perfectly readable. Ask blkid, which is what
    udev derives from, and accept either spelling.
    """
    import subprocess as _sp
    out = {}
    try:
        r = _sp.run(["sudo", "blkid", "-o", "export"], capture_output=True, text=True, timeout=15)
    except Exception:
        return out
    dev, label = "", ""
    for line in (r.stdout or "").split("\n"):
        line = line.strip()
        if not line:
            if dev and label:
                out.setdefault(label, dev)
            dev, label = "", ""
            continue
        k, _, v = line.partition("=")
        if k == "DEVNAME":
            dev = v
        elif k in ("LABEL", "LABEL_FATBOOT") and not label:
            label = v
    if dev and label:
        out.setdefault(label, dev)
    return out


def _sd_labels():
    """Every labelled volume currently attached, so a wrong SD_LABEL is DIAGNOSABLE.

    Without this a typo'd label and an unplugged card look identical from Pluto: both
    just say "not there". Listing what IS present turns a confusing evening into an
    obvious one.
    """
    return {"labels": sorted(_blkid_labels().keys())}


# Cards mount HERE and stay mounted, rather than under /tmp for the life of one call:
# the dir is exported over SMB, so a card you plugged in is browsable from your desktop
# instead of appearing only for the fraction of a second an action holds it.
_SD_MOUNT_ROOT = "/mnt/cpc-sd"


def _sd_mount(label):
    """Attach the volume with this LABEL read-only -> (mountpoint, we_mounted_it, error).

    Pluto owns the node config and passes the label down, so the Pi never needs to know
    which console this is, nor which /dev the card landed on -- udev maintains
    /dev/disk/by-label and the symlink appears/disappears with the card, so its existence
    IS the "is it plugged in" test.

    READ ONLY, always: a backup must never be able to alter the card it reads. If
    something already mounted it, reuse that mountpoint (a second mount just fails) and
    leave it alone afterwards.
    """
    import os as _os, subprocess as _sp
    if not label:
        return None, False, {"error": "no label given -- Pluto must pass the node's SD_LABEL"}
    # by-label first (cheap), then blkid, which also sees boot-sector-only labels.
    link = "/dev/disk/by-label/" + label
    dev = _os.path.realpath(link) if _os.path.exists(link) else ""
    if not dev:
        found = _blkid_labels()
        dev = found.get(label) or next(
            (d for l, d in found.items() if l.lower() == label.lower()), "")
    if not dev:
        seen = sorted(_blkid_labels().keys())
        return None, False, {"present": False, "label": label, "labels_seen": seen,
                             "error": "no volume labelled '%s' attached (seen: %s)"
                                      % (label, ", ".join(seen) or "none")}
    existing = ""
    try:
        with open("/proc/mounts") as mf:
            for line in mf:
                parts = line.split()
                if len(parts) > 1 and parts[0] == dev:
                    existing = parts[1].replace("\\040", " ")
                    break
    except Exception:
        pass
    if existing:
        return existing, False, None
    mnt = _SD_MOUNT_ROOT + "/" + "".join(c for c in label if c.isalnum() or c in "-_")
    try:
        _sp.run(["sudo", "mkdir", "-p", mnt], timeout=10, capture_output=True)
        r = _sp.run(["sudo", "mount", "-o", "ro", dev, mnt],
                    capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            return None, False, {"error": "mount failed for %s (%s): %s"
                                          % (label, dev, r.stderr.strip())}
    except Exception as exc:
        return None, False, {"error": "mount failed for %s: %s" % (label, exc)}
    return mnt, True, None


def _sd_unmount(mnt, ours):
    """Deliberately does NOTHING for a card we mounted.

    Cards are left mounted (read-only) so the SMB share is useful and the next action
    reuses the mount instead of re-mounting. Use the explicit 'eject' action before
    pulling a card. Kept as a function so the call sites still read honestly.
    """
    return


def _sd_eject(label):
    """Unmount a card so it can be pulled. Read-only mounts make this a tidiness step,
    not a data-safety one, but a stale mountpoint confuses everything that follows."""
    import os as _os, subprocess as _sp
    if not label:
        return {"error": "no label given"}
    mnt = _SD_MOUNT_ROOT + "/" + "".join(c for c in label if c.isalnum() or c in "-_")
    if not _os.path.ismount(mnt):
        return {"message": "%s is not mounted." % label}
    r = _sp.run(["sudo", "umount", mnt], timeout=15, capture_output=True, text=True)
    if r.returncode != 0:
        return {"error": "eject failed: %s" % r.stderr.strip()}
    return {"message": "%s unmounted -- safe to pull." % label}


def _sd_inspect(label, sub_path=""):
    """One directory of the card, read-only. Use 'scan' to see the whole thing."""
    import os as _os
    mnt, ours, err = _sd_mount(label)
    if err:
        return err
    try:
        base = _os.path.normpath(_os.path.join(mnt, sub_path.lstrip("/"))) if sub_path else mnt
        if not base.startswith(mnt):
            return {"error": "path escapes the card"}
        if not _os.path.exists(base):
            return {"error": "%s not found on %s" % (sub_path, label)}
        entries = []
        for name in sorted(_os.listdir(base)):
            fp = _os.path.join(base, name)
            try:
                entries.append({"name": name, "dir": _os.path.isdir(fp),
                                "size": (0 if _os.path.isdir(fp) else _os.path.getsize(fp))})
            except Exception:
                continue
        return {"present": True, "label": label, "path": sub_path or "/", "entries": entries}
    except Exception as exc:
        return {"error": "SD read failed: %s" % exc}
    finally:
        _sd_unmount(mnt, ours)


_SD_SCAN_CAP = 40000


def _sd_scan(label, small_bytes=262144):
    """Walk the WHOLE card and describe its shape, so its layout can be DEFINED.

    A single directory listing is not enough: these cards have many directories and the
    interesting part is which file TYPES live where. Returns per-directory totals and an
    extension inventory rather than every filename, because a card is mostly ROMs and the
    saves we are hunting are the small files hiding among them -- hence `small` samples,
    which is where save data actually shows up.
    """
    import os as _os
    mnt, ours, err = _sd_mount(label)
    if err:
        return err
    try:
        dirs, exts, small = {}, {}, []
        total_files = total_bytes = small_total = 0
        truncated = False
        for base, _sub, files in _os.walk(mnt):
            rel = _os.path.relpath(base, mnt)
            rel = "/" if rel == "." else "/" + rel.replace("\\", "/")
            d_count = d_bytes = 0
            for fn in files:
                if total_files >= _SD_SCAN_CAP:
                    truncated = True
                    break
                fp = _os.path.join(base, fn)
                try:
                    sz = _os.path.getsize(fp)
                except Exception:
                    continue
                total_files += 1; total_bytes += sz
                d_count += 1; d_bytes += sz
                ext = (_os.path.splitext(fn)[1] or "(none)").lower()
                e = exts.setdefault(ext, {"count": 0, "bytes": 0, "examples": []})
                e["count"] += 1; e["bytes"] += sz
                if len(e["examples"]) < 3:
                    e["examples"].append((rel.rstrip("/") + "/" + fn).replace("//", "/"))
                if sz <= small_bytes:
                    small_total += 1
                    if len(small) < 400:
                        small.append({"path": (rel.rstrip("/") + "/" + fn).replace("//", "/"),
                                      "size": sz})
            dirs[rel] = {"files": d_count, "bytes": d_bytes}
            if truncated:
                break
        return {"present": True, "label": label,
                "totals": {"files": total_files, "bytes": total_bytes,
                           "dirs": len(dirs), "truncated": truncated},
                "dirs": dirs,
                "extensions": dict((k, v) for k, v in sorted(
                    exts.items(), key=lambda kv: -kv[1]["bytes"])),
                # A sampled list that silently stops at 400 reads as "that is all of
                # them", so say how many actually matched.
                "small_files": sorted(small, key=lambda x: x["path"]),
                "small_matched": small_total,
                "small_truncated": small_total > len(small)}
    except Exception as exc:
        return {"error": "SD scan failed: %s" % exc}
    finally:
        _sd_unmount(mnt, ours)


_SD_COLLECT_CAP = 64 * 1024 * 1024      # a save set is small; this is a runaway guard


def _sd_collect(label, exts):
    """Recursively take every file on the card matching these extensions.

    No per-card layout knowledge is needed: we know what a console's save files LOOK
    like, so walk the whole card and take whatever matches, wherever it happens to live.
    Pluto passes the pattern set down (it owns the console config), so the Pi stays
    generic and works the same for the next card.

    Read-only. Skips rather than truncating silently once the match set gets implausibly
    large, which would mean the patterns are too broad (matching ROMs, not saves).
    """
    import base64 as _b64, os as _os
    # A pattern is either an EXTENSION (".srm") or an exact FILENAME ("SS_SAVE.BIN").
    # Extensions alone cannot express SAROO: its saves are SS_SAVE.BIN / SS_MEMS.BIN,
    # while ".bin" is also every disc image on the card and its firmware blobs.
    pats = [str(e).lower() for e in (exts or []) if str(e).strip()]
    want_ext  = set(e for e in pats if e.startswith("."))
    want_name = set(e for e in pats if not e.startswith("."))
    if not (want_ext or want_name):
        return {"error": "no patterns given -- Pluto must pass the console's save patterns"}
    mnt, ours, err = _sd_mount(label)
    if err:
        return err
    try:
        out, total, skipped = [], 0, 0
        for base, _sub, files in _os.walk(mnt):
            for fn in sorted(files):
                low = fn.lower()
                # macOS leaves AppleDouble twins next to real files; they are not saves.
                if low.startswith("._"):
                    continue
                if low not in want_name and _os.path.splitext(low)[1] not in want_ext:
                    continue
                fp = _os.path.join(base, fn)
                try:
                    sz = _os.path.getsize(fp)
                except Exception:
                    continue
                if total + sz > _SD_COLLECT_CAP:
                    skipped += 1
                    continue
                try:
                    with open(fp, "rb") as f:
                        data = f.read()
                except Exception:
                    skipped += 1
                    continue
                rel = _os.path.relpath(fp, mnt).replace("\\", "/")
                out.append({"path": rel, "size": sz,
                            "data": _b64.b64encode(data).decode("ascii")})
                total += sz
        return {"present": True, "label": label, "matched": len(out),
                "bytes": total, "skipped": skipped,
                "patterns": sorted(want_ext | want_name), "files": out}
    except Exception as exc:
        return {"error": "SD collect failed: %s" % exc}
    finally:
        _sd_unmount(mnt, ours)


def _read_vmu_image():
    """Hand Pluto the raw 128KB VMU image so it can do the filesystem work.

    rsync cannot read a VMU -- it is an image behind a USB reader, not a directory --
    so the batocera pattern (Pluto rsyncs, Pluto parses, Pluto uploads) needs this one
    extra hop. Everything after it stays on Pluto: the Dropbox token and the whole
    /saves ledger live there and are not duplicated onto the Pi.

    READ ONLY. Mounted -o ro and never written; backing progress up must not be able
    to damage the card it is backing up. Reading a whole VMU takes about 3 seconds.
    """
    import base64 as _b64, glob as _glob, hashlib as _hashlib, os as _os, subprocess as _sp
    if not _discover_vmu():
        return {"error": "VMU not found -- is the DreamPicoPort plugged in?"}
    candidates = sorted(_glob.glob("/dev/sd?"))
    if not candidates:
        return {"error": "DreamPicoPort on bus but no block device found."}
    dev = candidates[0]
    mnt = "/tmp/cpc-vmu"
    try:
        _os.makedirs(mnt, exist_ok=True)
        r = _sp.run(["sudo", "mount", "-t", "vfat", "-o", "ro", dev, mnt],
                    capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return {"error": "mount failed: %s" % r.stderr.strip()}
        path = _os.path.join(mnt, "VMU0.BIN")
        if not _os.path.exists(path):
            return {"error": "VMU0.BIN not found at %s" % path}
        with open(path, "rb") as vf:
            raw = vf.read()
        return {"image": _b64.b64encode(raw).decode("ascii"),
                "bytes": len(raw),
                "md5":   _hashlib.md5(raw).hexdigest()}
    except Exception as exc:
        return {"error": "VMU read failed: %s" % exc}
    finally:
        _sp.run(["sudo", "umount", dev], timeout=5, capture_output=True)


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

    # genesis datalink: hold the Pico serial (push-based MD liveness cache + command
    # writes) and serve the megadrive node's health on its own port.
    if _datalink_chip(cfg):
        threading.Thread(target=_genesis_manager, args=(cfg, stop), daemon=True).start()
        threading.Thread(target=_genesis_health_server, args=(cfg, stop), daemon=True).start()
    else:
        print("  genesis datalink disabled (no role=datalink pico in .env)")

    # Lens trigger: watch DC controller evdev devices, forward all buttons via HidBridge,
    # fire grab -> scan -> translate-last on L+R. Needs PLUTO_IP to be set in the .env.
    pluto_ip = (cfg.get("PLUTO_IP") or "").strip()
    lens = None
    if pluto_ip:
        from bridges.lens import LensTrigger
        lens = LensTrigger("http://%s:7700" % pluto_ip, bridges).start()
    else:
        print("  lens trigger disabled (no PLUTO_IP in .env)")

    # Kinect: Xbox NUI sensor stream. Raw depth/RGB/skeleton, no control mappings yet.
    kinect_port = (cfg.get("KINECT_DEPTH_PORT") or "").strip()
    kinect = None
    if kinect_port:
        from bridges.kinect import KinectBridge
        kinect = KinectBridge(int(kinect_port))
        if kinect.start():
            print("  kinect stream up -- :%s" % kinect_port)
        else:
            print("  kinect not available (check device/drivers)")
    else:
        print("  kinect disabled (no KINECT_DEPTH_PORT in .env)")

    # Nokia: phone keypad over Bluetooth rfcomm -> the LOCAL drive service (:7702),
    # which maps the key + drives the sink. The phone rides the same distributed
    # /control/drive path as every other input. On-demand via its HTTP endpoint;
    # Pluto's NokiaControl pushes source/mapping/target/dev + start/stop.
    nokia_port = (cfg.get("NOKIA_ENGINE_PORT") or "").strip()
    nokia = None
    if nokia_port:
        from bridges.nokia import NokiaBridge
        nokia = NokiaBridge(int(nokia_port), cfg)
        if nokia.start():
            print("  nokia engine up -- :%s" % nokia_port)
        else:
            print("  nokia engine disabled (missing addr / pyserial)")
    else:
        print("  nokia disabled (no NOKIA_ENGINE_PORT in .env)")

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
