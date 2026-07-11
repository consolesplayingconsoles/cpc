import network
import socket
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
FIRMWARE_VERSION = "4"

# --- CONFIGURATION (injected from .env at flash time) ---
# Deployment process: substitute @@ROOMBA_SSID@@, @@ROOMBA_PASSWORD@@, @@HOST_PORT@@
# from nodes/local/roomba-rally/.env before flashing to Pico
WIFI_SSID = "@@ROOMBA_SSID@@"
WIFI_PASSWORD = "@@ROOMBA_PASSWORD@@"
LISTEN_PORT = int("@@HOST_PORT@@")

# --- HARDWARE ---
dashboard_led = Pin(15, Pin.OUT)
brc_pin = Pin(2, Pin.OUT)

# --- STATE ---
headlights_active = False
session_active = True     # in an OI session (Full mode) vs. relinquished after game-over
last_command = None

# --- ROOMBA PAYLOADS ---
# Every payload is prefixed 0x80 0x84 (Start + Full) so it re-wakes into Full mode --
# that's why control is never permanently lost: any command re-enters the OI.
LIGHTS_ON = b'\x80\x84\x8b\x0d\xff\xff'
LIGHTS_OFF = b'\x80\x84\x8b\x00\x00\x00'
SEGA_CHIME = b'\x80\x84\x8c\x00\x04\x4c\x08\x4f\x08\x51\x08\x54\x18\x8d\x00'
# Game-over: TRIUMPHANT rising G-major arpeggio (G5 B5 D6) landing on a held high G6 --
# the "...YEAAAH!". NO trailing OI-Stop here: we play it, wait it out, THEN relinquish,
# so the tune isn't cut off (the old payload stopped the OI in the same write).
GAME_OVER_TUNE = b'\x80\x84\x8c\x00\x04\x4f\x08\x53\x08\x56\x0c\x5b\x28\x8d\x00'
GAME_OVER_MS = 1100      # ~ (8+8+12+40)/64 s of song, + slack, before we drop the OI
# Re-enter chime: two quick rising notes confirming we're back in Full mode.
START_TUNE = b'\x80\x84\x8c\x00\x02\x4f\x08\x56\x10\x8d\x00'
OI_STOP = b'\xad'         # 173: stop the OI (relinquish control until the next command)

def wakeup_651():
    """Wake Roomba and switch to 19200 baud via BRC pin."""
    brc_pin.value(1)
    time.sleep(0.1)
    for _ in range(3):
        brc_pin.value(0)
        time.sleep(0.1)
        brc_pin.value(1)
        time.sleep(0.1)
    time.sleep(1.5)

def get_battery_stats():
    """Query Roomba battery; return percentage or 'ONLINE'."""
    try:
        wakeup_651()
        uart = UART(0, baudrate=19200, tx=Pin(0), rx=Pin(1), bits=8, parity=None, stop=1)
        if uart.any():
            uart.read()
        uart.write(bytes([142, 3]))  # Sensor Packet 3
        time.sleep(0.2)
        if uart.any():
            data = uart.read()
            if len(data) >= 10:
                charge = (data[2] << 8) | data[3]
                capacity = (data[4] << 8) | data[5]
                if capacity > 0:
                    return int((charge / capacity) * 100)
        return 100  # fallback
    except Exception as e:
        print(f"[Battery] Error: {e}")
        return 100

def _open():
    """Wake the Roomba (BRC pulse) and return an OI-ready UART at 19200."""
    wakeup_651()
    return UART(0, baudrate=19200, tx=Pin(0), rx=Pin(1), bits=8, parity=None, stop=1)

def send_command(action):
    """Execute a Roomba command by action name."""
    global headlights_active, session_active, last_command

    try:
        if action == "lights":
            # Toggle: the roomba owns its own lights state, so one event flips it.
            headlights_active = not headlights_active
            dashboard_led.value(1 if headlights_active else 0)
            _open().write(LIGHTS_ON if headlights_active else LIGHTS_OFF)
        elif action == "melody":
            _open().write(SEGA_CHIME)
        elif action == "session":
            # START button, toggled: game-over <-> re-enter. Same button restarts.
            uart = _open()
            if session_active:
                # Play the triumphant tune to COMPLETION, then relinquish the OI.
                uart.write(GAME_OVER_TUNE)
                time.sleep(GAME_OVER_MS / 1000)
                uart.write(OI_STOP)
                headlights_active = False
                dashboard_led.value(0)
                session_active = False
            else:
                # _open()'s wake + the payload's Start+Full already re-establish
                # control; the chime just confirms we're back in the game.
                uart.write(START_TUNE)
                session_active = True
        else:
            return False    # drive-forward/back, turn-left/right, horn: not wired yet
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
        "Connection: close\r\n"
        "\r\n%s" % (status, content_type, len(body), body)
    ).encode()

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind(('', LISTEN_PORT))
server_socket.listen(5)

print(f"[Server] Listening on port {LISTEN_PORT}")

while True:
    conn = None
    try:
        conn, addr = server_socket.accept()
        # Never let one slow/silent client wedge the single-threaded loop: a blocking
        # recv() with no timeout hangs forever if a client connects but doesn't send a
        # full request (a browser preconnect, a port scan, a half-open probe). The
        # timeout turns that into an exception we swallow, and finally: always closes.
        conn.settimeout(5)
        # MicroPython's decode() takes NO keyword args (no errors='ignore' like CPython)
        # -- passing one raises "function doesn't take keyword arguments" before we ever
        # parse the request. HTTP request lines/headers are ASCII, so plain decode() is fine.
        request_data = conn.recv(1024).decode()

        method, path, body = parse_request(request_data)
        print("[Req] %r %r (%d bytes raw)" % (method, path, len(request_data)))

        if method is None:
            continue

        # --- ROUTES ---
        if path == '/health':
            response = http_response("200 OK", "application/json",
                                   json.dumps({"ok": True, "version": FIRMWARE_VERSION}))

        elif path == '/status':
            battery = get_battery_stats()
            response = http_response("200 OK", "application/json",
                                   json.dumps({
                                       "online": True,
                                       "battery": battery,
                                       "lights": headlights_active,
                                       "last_command": last_command
                                   }))

        elif path == '/command' and method == 'POST':
            try:
                data = json.loads(body) if body else {}
                action = data.get("action")
                success = send_command(action) if action else False
                if success:
                    response = http_response("200 OK", "application/json",
                                           json.dumps({"success": True, "action": action}))
                else:
                    response = http_response("400 Bad Request", "application/json",
                                           json.dumps({"success": False, "error": "unknown action"}))
            except Exception as e:
                response = http_response("500 Internal Error", "application/json",
                                       json.dumps({"success": False, "error": str(e)}))

        else:
            response = http_response("404 Not Found", "text/plain", "Not Found")

        conn.send(response)

    except Exception as e:
        print(f"[Server Error] {e}")
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
