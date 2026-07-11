import network
import socket
import select
from machine import UART, Pin
import time
import json

# --- API ROUTES (sync'd with openapi.yaml) ---
ROUTES = {
    ("GET", "/health"): "health",
    ("GET", "/status"): "status",
    ("POST", "/command"): "command",
}

# Firmware version. Reported in /health so you can confirm a Pluto DEPLOY actually
# flashed the running board: bump this, deploy, then re-check /health -- if the number
# changed, the new bytes are live. (The Thonny-saved copy predates this field.)
FIRMWARE_VERSION = "19"

# --- CONFIGURATION (injected from .env at flash time) ---
# Deployment process: substitute @@ROOMBA_SSID@@, @@ROOMBA_PASSWORD@@, @@HOST_PORT@@
# from nodes/local/roomba-rally/.env before flashing to Pico
WIFI_SSID = "@@ROOMBA_SSID@@"
WIFI_PASSWORD = "@@ROOMBA_PASSWORD@@"
LISTEN_PORT = int("@@HOST_PORT@@")
# Real-time command stream: Pluto holds ONE persistent TCP connection here and streams
# newline-delimited verbs, instead of a fresh HTTP POST per event (which saturated the
# single-threaded server during movement). HTTP (LISTEN_PORT) stays for health/status.
CMD_PORT = LISTEN_PORT + 1
# Deadman: auto-stop movement if no drive command / keepalive arrives within this window
# (a dropped stop, a stalled or crashed Pluto, a half-open wifi link). The safety net that
# lets us hold-to-move without a runaway into the tether.
DEADMAN_MS = 2500

# --- HARDWARE ---
dashboard_led = Pin(15, Pin.OUT)
# BRC held idle-high: we talk at the OI FACTORY DEFAULT 115200 baud (the proven-working
# path). Pulsing BRC low would drop the Roomba to 19200 -- a different, flakier mode we
# deliberately avoid. So the pin is parked high and never pulsed.
brc_pin = Pin(2, Pin.OUT)
brc_pin.value(1)

# One OI UART, opened once and reused (like the proven script). 115200 = OI default;
# no wake pulse needed once the battery has charge -- a flat battery is what looked like
# "asleep/ignoring commands". tx=GP0, rx=GP1.
ROOMBA_BAUD = 115200
roomba = UART(0, baudrate=ROOMBA_BAUD, tx=Pin(0), rx=Pin(1), bits=8, parity=None, stop=1)

# Battery % divides charge by THIS fixed capacity, not the Roomba's live (shrinking)
# capacity estimate. Set to the pack's healthy full-charge capacity in mAh.
DESIGN_CAPACITY_MAH = 2696

# --- STATE ---
headlights_active = False
session_active = True     # in an OI session (Full mode) vs. relinquished after game-over
last_command = None
driving = False           # currently holding a drive velocity (movement in progress)
last_drive_ms = 0         # ticks_ms of the last drive/keepalive -- watched by the deadman

# --- ROOMBA PAYLOADS ---
# Every payload is prefixed 0x80 0x83 (Start + SAFE mode). Safe keeps the Roomba's built-in
# cliff + wheel-drop safeties ON (Full mode disables them). Everything we do -- LED (139),
# songs (140/141), Drive (137) -- is valid in Safe, so there's no reason to be in Full. Re-
# prefixing every command re-enters Safe, so if a cliff/wheel-drop event bumps it to Passive
# it self-recovers on the next command.
LIGHTS_ON = b'\x80\x83\x8b\x0d\xff\xff'
LIGHTS_OFF = b'\x80\x83\x8b\x00\x00\x00'
SEGA_CHIME = b'\x80\x83\x8c\x00\x04\x4c\x08\x4f\x08\x51\x08\x54\x18\x8d\x00'

HORN = b'\x8c\x00\x01\x43\x30\x8d\x00'

# Game-over: TRIUMPHANT rising G-major arpeggio (G5 B5 D6) landing on a held high G6 --
# the "...YEAAAH!". NO trailing OI-Stop here: we play it, wait it out, THEN relinquish,
# so the tune isn't cut off (the old payload stopped the OI in the same write).
GAME_OVER_TUNE = b'\x80\x83\x8c\x00\x04\x4f\x08\x53\x08\x56\x0c\x5b\x28\x8d\x00'
GAME_OVER_MS = 1100      # ~ (8+8+12+40)/64 s of song, + slack, before we drop the OI
# Re-enter chime: two quick rising notes confirming we're back in Full mode.
START_TUNE = b'\x80\x83\x8c\x00\x02\x4f\x08\x56\x10\x8d\x00'
OI_STOP = b'\xad'         # 173: stop the OI (relinquish control until the next command)

# --- MOVEMENT (OI Drive, opcode 137 = 0x89: [vel_hi vel_lo][radius_hi radius_lo]) ---
# HOLD-TO-MOVE model: a drive verb just SETS a velocity (no blocking sleep -- that sleep
# was half the saturation) and the Roomba holds it until 'drive-stop' (key release) or the
# DEADMAN fires. Modest velocity + the deadman keep the ~1m tether safe. Radius 0x8000 =
# straight; 0x0001 = turn-in-place CCW (left); 0xFFFF = turn-in-place CW (right).
DRIVE_FWD  = b'\x80\x83\x89\x00\x96\x80\x00'   # +150 mm/s, straight
DRIVE_BACK = b'\x80\x83\x89\xff\x6a\x80\x00'   # -150 mm/s, straight
TURN_LEFT  = b'\x80\x83\x89\x00\x96\x00\x01'   # +150 mm/s, turn in place CCW
TURN_RIGHT = b'\x80\x83\x89\x00\x96\xff\xff'   # +150 mm/s, turn in place CW
DRIVE_STOP = b'\x89\x00\x00\x00\x00'           # velocity 0 (already in Safe)
DRIVE_ACTIONS = {
    "drive-forward": DRIVE_FWD, "drive-back": DRIVE_BACK,
    "turn-left": TURN_LEFT, "turn-right": TURN_RIGHT,
}

def _open():
    """The shared OI UART, with any stale RX line-noise flushed first. No BRC wake --
    at 115200 with a charged battery the Roomba responds directly."""
    if roomba.any():
        roomba.read()
    return roomba

def get_telemetry():
    """Full battery telemetry via OI Sensor GROUP Packet 3 (opcode 142) -- it bundles
    packets 21-26 in 10 bytes. Layout: [0]=charging state, [1:3]=voltage u16 mV,
    [3:5]=current s16 mA, [5]=temperature s8 C, [6:8]=charge u16 mAh, [8:10]=capacity
    u16 mAh. (The old code read charge/capacity at bytes 2-5 -- WRONG; those are voltage
    /current. Corrected here.) Returns {} on read failure. `raw` (hex) is included so
    offsets can be eyeballed against the real device."""
    try:
        uart = _open()
        uart.write(bytes([142, 3]))
        time.sleep(0.15)
        data = uart.read()
        if not data or len(data) < 10:
            return {}
        pkt = data[-10:]     # last 10 bytes: skip any line-noise ahead of the packet
        def u16(i): return (pkt[i] << 8) | pkt[i + 1]
        def s16(i): return u16(i) - 65536 if u16(i) >= 32768 else u16(i)
        charge, capacity = u16(6), u16(8)
        # % against a FIXED healthy design capacity, NOT the Roomba's live `capacity` -- it
        # re-estimates that DOWNWARD as the battery wears, which inflates charge/capacity to
        # ~93% on a nearly-dead pack. charge (coulomb-counted mAh remaining) / design is the
        # honest SoC. DESIGN_CAPACITY_MAH: set to your pack's healthy full capacity (the
        # `capacity` reading when freshly charged; 2696 was observed earlier). Tune it.
        pct = min(100, int(charge / DESIGN_CAPACITY_MAH * 100)) if charge else None
        return {
            "charging_state": pkt[0],
            "voltage_mv":     u16(1),
            "current_ma":     s16(3),
            "temp_c":         pkt[5] - 256 if pkt[5] >= 128 else pkt[5],
            "charge_mah":     charge,
            "capacity_mah":   capacity,     # LIVE estimate (drifts down with wear) -- health signal
            "battery_pct":    pct,
        }
    except Exception as e:
        print("[Telemetry] Error:", e)
        return {}

def get_sensors():
    """OI mode + bump/wheel-drop + cliff sensors via Query List (opcode 149). Fixed 6-byte
    reply in request order: [bumps(7)][mode(35)][cliffL(9)][cliffFL(10)][cliffFR(11)][cliffR(12)].
    Kept SEPARATE from the battery read so that (working) 10-byte packet stays untouched."""
    try:
        uart = _open()
        uart.write(bytes([149, 6, 7, 35, 9, 10, 11, 12]))
        time.sleep(0.1)
        d = uart.read()
        if not d or len(d) < 6:
            return {}
        s = d[-6:]
        b = s[0]
        MODES = {0: "off", 1: "passive", 2: "safe", 3: "full"}
        return {
            "mode": MODES.get(s[1], "?"),
            "bump_left":  bool(b & 0x02), "bump_right": bool(b & 0x01),
            "wheeldrop_left": bool(b & 0x08), "wheeldrop_right": bool(b & 0x04),
            "cliff_left": bool(s[2]), "cliff_front_left": bool(s[3]),
            "cliff_front_right": bool(s[4]), "cliff_right": bool(s[5]),
        }
    except Exception as e:
        print("[Sensors] Error:", e)
        return {}

def send_command(action):
    """Execute a Roomba command by action name."""
    global headlights_active, session_active, last_command, driving, last_drive_ms

    try:
        if action == "lights":
            # Toggle: the roomba owns its own lights state, so one event flips it.
            headlights_active = not headlights_active
            dashboard_led.value(1 if headlights_active else 0)
            _open().write(LIGHTS_ON if headlights_active else LIGHTS_OFF)
        elif action == "melody":
            _open().write(SEGA_CHIME)
        elif action == "horn":
            _open().write(HORN)
        elif action == "session":
            # START button, toggled: game-over <-> restart, each with its own tune. We do
            # NOT relinquish the OI on game-over: the trailing OI-Stop (173) was racing and
            # KILLING the tune (why "off" was silent while "on" beeped). Staying in Full
            # means the tune plays AND control is never lost -- both wins.
            uart = _open()
            if session_active:
                uart.write(GAME_OVER_TUNE)
                headlights_active = False
                dashboard_led.value(0)
                session_active = False
            else:
                uart.write(START_TUNE)
                session_active = True
        elif action in DRIVE_ACTIONS:
            # Movement is gated on the session: a PAUSED (game-over) roomba ignores drive
            # verbs -- ack but don't move. Otherwise SET the velocity (non-blocking) and
            # let it hold until 'drive-stop' or the deadman. Feeds the deadman clock.
            if session_active:
                _open().write(DRIVE_ACTIONS[action])
                driving = True
                last_drive_ms = time.ticks_ms()
        elif action == "drive-stop":
            _open().write(DRIVE_STOP)
            driving = False
        elif action == "ping":
            # keepalive from the command stream: proves Pluto is alive so the deadman
            # doesn't cut a legitimate hold. Only meaningful while driving.
            if driving:
                last_drive_ms = time.ticks_ms()
        else:
            return False    # genuinely unknown action
        last_command = action
        print(f"[Roomba] {action}")
        return True
    except Exception as e:
        print(f"[Roomba Error] {e}")
        return False

# --- BOOT ---
print(f"[Boot] Roomba Rally firmware v{FIRMWARE_VERSION}")
print("[Hardware] Initialising LED...")
for _ in range(3):
    dashboard_led.value(1)
    time.sleep(0.1)
    dashboard_led.value(0)
    time.sleep(0.1)

print("[Wi-Fi] Connecting to station mode...")
sta = network.WLAN(network.STA_IF)
sta.active(True)
sta.connect(WIFI_SSID, WIFI_PASSWORD)

# Wait for connection
for _ in range(20):
    if sta.isconnected():
        break
    time.sleep(0.5)

if sta.isconnected():
    print(f"[Wi-Fi] Connected: {sta.ifconfig()[0]}")
else:
    print("[Wi-Fi] FAILED to connect")

# --- HTTP SERVER ---
def parse_request(data):
    """Extract method, path, and body from HTTP request."""
    lines = data.split('\r\n')
    if not lines:
        return None, None, None

    parts = lines[0].split()
    if len(parts) < 2:
        return None, None, None

    method = parts[0]
    path = parts[1]
    body = None

    # Find body (after blank line)
    try:
        blank_idx = lines.index('')
        if blank_idx + 1 < len(lines):
            body = lines[blank_idx + 1]
    except:
        pass

    return method, path, body

def http_response(status, content_type, body):
    """Build a fully-framed HTTP/1.1 response as BYTES. Content-Length + Connection:
    close are what let the client (curl, Pluto's probe) know the body is complete and
    the response is done -- without them an HTTP/1.1 client hangs waiting for more or
    reports an empty reply when the socket closes mid-stream. Encode: MicroPython's
    socket.send wants bytes, not str."""
    return (
        "HTTP/1.1 %s\r\n"
        "Content-Type: %s\r\n"
        "Content-Length: %d\r\n"
        # Open CORS so Pluto's SPA (a different origin: its host vs this Pico's IP) can
        # fetch /status directly from the browser for the telemetry panel. LAN device.
        "Access-Control-Allow-Origin: *\r\n"
        "Connection: close\r\n"
        "\r\n%s" % (status, content_type, len(body), body)
    ).encode()

def serve_http(conn):
    """Handle ONE blocking HTTP request/response (health / status / one-off command).
    Kept for discovery + the telemetry panel + curl; the real-time drive stream is the
    separate CMD_PORT socket. Short recv timeout so a stalled HTTP client can't wedge the
    loop (and thus the deadman) for long."""
    try:
        conn.settimeout(2)
        raw = conn.recv(1024)
        if not raw:
            return
        while b'\r\n\r\n' not in raw:
            chunk = conn.recv(1024)
            if not chunk:
                break
            raw += chunk
        head, sep, body_bytes = raw.partition(b'\r\n\r\n')
        clen = 0
        for line in head.split(b'\r\n'):
            if line[:15].lower() == b'content-length:':
                try:
                    clen = int(line[15:].strip())
                except Exception:
                    clen = 0
                break
        while len(body_bytes) < clen:
            chunk = conn.recv(clen - len(body_bytes))
            if not chunk:
                break
            body_bytes += chunk
        method, path, body = parse_request((head + sep + body_bytes).decode())
        if method is None:
            return

        if path == '/health':
            response = http_response("200 OK", "application/json",
                                   json.dumps({"ok": True, "version": FIRMWARE_VERSION}))
        elif path == '/status':
            tel = get_telemetry()
            response = http_response("200 OK", "application/json",
                                   json.dumps({
                                       "online": True,
                                       "active": session_active,     # play/pause gate
                                       "lights": headlights_active,
                                       "last_command": last_command,
                                       "battery": tel.get("battery_pct"),
                                       "telemetry": tel,             # OI battery group
                                       "sensors": get_sensors(),     # mode + bumps + cliffs
                                   }))
        elif path == '/command' and method == 'POST':
            try:
                data = json.loads(body) if body else {}
                action = data.get("action")
                ok = send_command(action) if action else False
                response = http_response("200 OK" if ok else "400 Bad Request", "application/json",
                                       json.dumps({"success": True, "action": action} if ok
                                                  else {"success": False, "error": "unknown action"}))
            except Exception as e:
                response = http_response("500 Internal Error", "application/json",
                                       json.dumps({"success": False, "error": str(e)}))
        else:
            response = http_response("404 Not Found", "text/plain", "Not Found")
        conn.send(response)
    except Exception as e:
        print("[HTTP Error]", e)
    finally:
        try:
            conn.close()
        except Exception:
            pass

def _stop_moving():
    global driving
    if driving:
        try:
            _open().write(DRIVE_STOP)
        except Exception:
            pass
        driving = False

# Two listeners: HTTP (health/status/command) + the persistent command STREAM. select.poll
# multiplexes them in one thread so the drive stream isn't throttled by HTTP, and the loop
# ticks every 200ms so the DEADMAN runs even when idle.
http_srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
http_srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
http_srv.bind(('', LISTEN_PORT))
http_srv.listen(5)

cmd_srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
cmd_srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
cmd_srv.bind(('', CMD_PORT))
cmd_srv.listen(1)

poller = select.poll()
poller.register(http_srv, select.POLLIN)
poller.register(cmd_srv, select.POLLIN)

cmd_conn = None
cmd_buf = b''
print("[Server] HTTP :%d  cmd-stream :%d" % (LISTEN_PORT, CMD_PORT))

while True:
    try:
        for sock, ev in poller.poll(200):
            if sock is http_srv:
                c, _ = http_srv.accept()
                serve_http(c)
            elif sock is cmd_srv:
                nc, _ = cmd_srv.accept()
                if cmd_conn:                         # only one stream client; newest wins
                    try:
                        poller.unregister(cmd_conn); cmd_conn.close()
                    except Exception:
                        pass
                cmd_conn = nc
                # Blocking with a SHORT timeout, not non-blocking: a non-blocking recv on a
                # spurious poll wake raises EAGAIN, which we'd mistake for a close and kill a
                # healthy stream ("works once then dead"). Blocking + poll-gated means recv
                # returns real data or b'' (clean close); the 0.3s bound covers spurious wakes.
                cmd_conn.settimeout(0.3)
                poller.register(cmd_conn, select.POLLIN)
                cmd_buf = b''
                print("[Cmd] stream connected")
            elif sock is cmd_conn:
                try:
                    chunk = cmd_conn.recv(256)
                except Exception:
                    chunk = None                     # timeout / would-block: TRANSIENT, don't close
                if chunk == b'':                     # clean peer close -> fail safe: stop
                    try:
                        poller.unregister(cmd_conn); cmd_conn.close()
                    except Exception:
                        pass
                    cmd_conn = None; cmd_buf = b''
                    _stop_moving()
                    print("[Cmd] stream closed")
                elif chunk:
                    cmd_buf += chunk
                    while b'\n' in cmd_buf:
                        line, cmd_buf = cmd_buf.split(b'\n', 1)
                        a = line.decode().strip()
                        if a:
                            send_command(a)
        # DEADMAN: holding a velocity but no drive/keepalive within the window -> stop.
        if driving and time.ticks_diff(time.ticks_ms(), last_drive_ms) > DEADMAN_MS:
            _stop_moving()
            print("[Deadman] auto-stop")
    except Exception as e:
        print("[Loop Error]", e)
