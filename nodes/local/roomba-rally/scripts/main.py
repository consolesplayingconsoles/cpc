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
last_command = None

# --- ROOMBA PAYLOADS ---
LIGHTS_ON = b'\x80\x84\x8b\x0d\xff\xff'
LIGHTS_OFF = b'\x80\x84\x8b\x00\x00\x00'
SEGA_CHIME = b'\x80\x84\x8c\x00\x04\x4c\x08\x4f\x08\x51\x08\x54\x18\x8d\x00'
GAME_OVER = b'\x80\x84\x8c\x00\x04\x43\x18\x41\x18\x3f\x18\x3c\x30\x8d\x00\xad'

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

def send_command(action):
    """Execute a Roomba command by action name."""
    global headlights_active, last_command

    payload = None
    if action == "lights-on":
        payload = LIGHTS_ON
        headlights_active = True
        dashboard_led.value(1)
    elif action == "lights-off":
        payload = LIGHTS_OFF
        headlights_active = False
        dashboard_led.value(0)
    elif action == "melody":
        payload = SEGA_CHIME
    elif action == "stop":
        payload = GAME_OVER
        headlights_active = False
        dashboard_led.value(0)
    else:
        return False

    if payload:
        try:
            wakeup_651()
            uart = UART(0, baudrate=19200, tx=Pin(0), rx=Pin(1), bits=8, parity=None, stop=1)
            uart.write(payload)
            last_command = action
            print(f"[Roomba] {action}")
            return True
        except Exception as e:
            print(f"[Roomba Error] {e}")
            return False
    return False

# --- BOOT ---
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
    """Build HTTP response."""
    response = f"HTTP/1.1 {status}\r\nContent-Type: {content_type}\r\n\r\n{body}"
    return response

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind(('', LISTEN_PORT))
server_socket.listen(5)

print(f"[Server] Listening on port {LISTEN_PORT}")

while True:
    try:
        conn, addr = server_socket.accept()
        request_data = conn.recv(1024).decode('utf-8', errors='ignore')

        method, path, body = parse_request(request_data)

        if method is None:
            conn.close()
            continue

        # --- ROUTES ---
        if path == '/health':
            response = http_response("200 OK", "application/json",
                                   json.dumps({"ok": True}))

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
        conn.close()

    except Exception as e:
        print(f"[Server Error] {e}")
