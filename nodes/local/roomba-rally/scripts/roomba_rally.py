import network
import socket
from machine import UART, Pin
import time

# --- 1. DASHBOARD LED HARDWARE MAP ---
dashboard_led = Pin(15, Pin.OUT)

# --- 2. GLOBAL STATE TRACKING ---
headlights_active = False

# --- 3. SET UP THE WAKEUP LINE (GP2) ---
brc_pin = Pin(2, Pin.OUT)

def wakeup_651():
    brc_pin.value(1)
    time.sleep(0.1)
    for _ in range(3):
        brc_pin.value(0)
        time.sleep(0.1)
        brc_pin.value(1)
        time.sleep(0.1)
    time.sleep(1.5)

# --- 4. PRE-COMPILED ARCADE COMMAND LITERALS ---
LIGHTS_ON = b'\x80\x84\x8b\x0d\xff\xff'
LIGHTS_OFF = b'\x80\x84\x8b\x00\x00\x00'
SEGA_CHIME = b'\x80\x84\x8c\x00\x04\x4c\x08\x4f\x08\x51\x08\x54\x18\x8d\x00'

# NAVIGATION BYTES (Opcode 145 / Drive Direct)
# \x91 = Drive Direct Opcode
# Forward Crawl: Right speed 75 mm/s (\x00\x4b), Left speed 75 mm/s (\x00\x4b)
CRAWL_FORWARD = b'\x80\x84\x91\x00\x4b\x00\x4b'
# Drift Right: Right speed -50 mm/s (\xff\xce), Left speed 75 mm/s (\x00\x4b)
DRIFT_RIGHT   = b'\x80\x84\x91\xff\xce\x00\x4b'
# Drift Left: Right speed 75 mm/s (\x00\x4b), Left speed -50 mm/s (\xff\xce)
DRIFT_LEFT    = b'\x80\x84\x91\x00\x4b\xff\xce'
# Handbrake / Full Stop: All motor speeds 0
MOTOR_BRAKE   = b'\x80\x84\x91\x00\x00\x00\x00'

# Game Over Sequence (Plays chord down and issues Opcode 173 / \xad to reset board control)
GAME_OVER_PAYLOAD = b'\x80\x84\x8c\x00\x04\x43\x18\x41\x18\x3f\x18\x3c\x30\x8d\x00\xad'

# --- 5. DATA TELEMETRY FUNCTION ---
def get_battery_stats():
    wakeup_651()
    uart = UART(0, baudrate=19200, tx=Pin(0), rx=Pin(1), bits=8, parity=None, stop=1)
    if uart.any():
        uart.read()
    uart.write(bytes([142, 3])) 
    time.sleep(0.2)
    if uart.any():
        data = uart.read()
        if len(data) >= 10:
            # Fixed indexing parsing structure to prevent string render crashes
            charge = (data[2] << 8) | data[3]
            capacity = (data[4] << 8) | data[5]
            if capacity > 0:
                return f"{int((charge / capacity) * 100)}%"
    return "ONLINE"

# --- 6. VISUAL BOOT SEQUENCE ---
print("[Hardware] Initialising Dashboard Activity Indicator...")
for _ in range(3):
    dashboard_led.value(1)
    time.sleep(0.1)
    dashboard_led.value(0)
    time.sleep(0.1)

# --- 7. SPIN UP THE ACCESS POINT ---
print("[Wi-Fi] Booting Roomba Rally Wireless Hotspot...")
ap = network.WLAN(network.AP_IF)
ap.config(essid="Roomba Rally", password="celica123")
ap.active(True)
ap_config = ap.ifconfig()

print("\n==========================================")
print("🕹️ GAME START: ROOMBA RALLY ACCESS POINT IS LIVE")
print("1. Join Wi-Fi Network: Roomba Rally")
print("2. Enter Password: celica123")
print(f"3. Open web browser to: http://{ap_config[0]}")
print("==========================================\n")

# --- 8. BLOCK FUNCTION FOR SEGA RALLY HTML ---
def generate_dashboard(lights_state, battery_text):
    if lights_state:
        light_label = "LIGHTS OFF"
        light_class = "lights-active"
        light_url = "/lightsoff"
    else:
        light_label = "LIGHTS ON"
        light_class = "lights-idle"
        light_url = "/lightson"

    return f"""<!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Roomba Rally</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: 'Impact', 'Arial Black', sans-serif; text-align: center; background-color: #111216; color: #ffffff; padding-top: 30px; letter-spacing: 0.5px; }}
            .container {{ background-color: #1a1c24; border-radius: 12px; width: 90%; max-width: 380px; margin: 0 auto; padding: 20px 15px; box-shadow: 0px 10px 30px rgba(0, 0, 0, 0.5); }}
            h1 {{ color: #ffcc00; font-size: 42px; margin: 0px auto 5px auto; font-style: italic; text-transform: uppercase; }}
            .sub {{ color: #ffffff; font-size: 14px; margin-top: 0; margin-bottom: 10px; font-style: italic; background-color: #e60012; display: inline-block; padding: 4px 14px; transform: skewX(-12deg); font-weight: bold; letter-spacing: 1px; }}
            .telemetry {{ font-size: 14px; color: #89b4fa; margin-bottom: 20px; text-transform: uppercase; background: #252834; padding: 6px; border-radius: 5px; display: block; }}
            .btn {{ display: block; width: 85%; margin: 12px auto; padding: 14px; font-size: 18px; font-weight: bold; border-radius: 6px; cursor: pointer; text-decoration: none; font-style: italic; text-transform: uppercase; transition: transform 0.05s; }}
            .btn:active {{ transform: scale(0.97); }}
            .lights-idle {{ background-color: #ffcc00; color: #111216; }}
            .lights-active {{ background-color: #3e414f; color: #ffffff; }}
            .blue {{ background-color: #0066ff; color: #ffffff; }}
            .orange {{ background-color: #ff6600; color: #ffffff; }}
            .red {{ background-color: #e60012; color: #ffffff; }}
            
            /* Steering Pad Grid Alignment */
            .wheel-pad {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; width: 85%; margin: 0 auto; }}
            .grid-btn {{ padding: 14px; font-size: 18px; font-weight: bold; border-radius: 6px; text-decoration: none; font-style: italic; text-transform: uppercase; color: white; background-color: #3e414f; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>ROOMBA RALLY</h1>
            <div class="sub">TOYOTA CELICA GT-FOUR</div>
            <div class="telemetry">🔋 FUEL CELL STAGE: {battery_text}</div>
            
            <a href="{light_url}" class="btn {light_class}">🏁 {light_label}</a>
            <a href="/melody" class="btn blue">🎵 GAME START TUNE</a>
            <a href="/crawl" class="btn orange">🏎️ THROTTLE FORWARD</a>
            
            <div class="wheel-pad">
                <a href="/left" class="grid-btn">◀️ STEER LEFT</a>
                <a href="/right" class="grid-btn">STEER RIGHT ▶️</a>
            </div>
            
            <a href="/brake" class="btn blue">⚠️ ENGAGE HANDBRAKE</a>
            <a href="/stop" class="btn red">🛑 GAME OVER YEAH</a>
        </div>
    </body>
    </html>
    """

# --- 9. SOCKET INITIALISATION ---
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind(('', 80))
server_socket.listen(5)

# --- 10. RACING ENGINE LOOP ---
while True:
    try:
        connection, client_address = server_socket.accept()
        web_request = connection.recv(1024).decode('utf-8')

        should_redirect = False

        if '/lightson' in web_request:
            print(" -> Dashboard: Headlights ON")
            headlights_active = True
            dashboard_led.value(1)
            wakeup_651()
            uart = UART(0, baudrate=19200, tx=Pin(0), rx=Pin(1), bits=8, parity=None, stop=1)
            uart.write(LIGHTS_ON)
            should_redirect = True

        elif '/lightsoff' in web_request:
            print(" -> Dashboard: Headlights OFF")
            headlights_active = False
            dashboard_led.value(0)
            wakeup_651()
            uart = UART(0, baudrate=19200, tx=Pin(0), rx=Pin(1), bits=8, parity=None, stop=1)
            uart.write(LIGHTS_OFF)
            should_redirect = True

        elif '/melody' in web_request:
            print(" -> Dashboard: Launching Arcade Start Chime")
            wakeup_651()
            uart = UART(0, baudrate=19200, tx=Pin(0), rx=Pin(1), bits=8, parity=None, stop=1)
            uart.write(SEGA_CHIME)
            should_redirect = True

        elif '/crawl' in web_request:
            print(" -> Dashboard: Crawling Forward Active")
            wakeup_651()
            uart = UART(0, baudrate=19200, tx=Pin(0), rx=Pin(1), bits=8, parity=None, stop=1)
            uart.write(CRAWL_FORWARD)
            should_redirect = True

        elif '/left' in web_request:
            print(" -> Dashboard: Drifting Left")
            wakeup_651()
            uart = UART(0, baudrate=19200, tx=Pin(0), rx=Pin(1), bits=8, parity=None, stop=1)
            uart.write(DRIFT_LEFT)
            should_redirect = True

        elif '/right' in web_request:
            print(" -> Dashboard: Drifting Right")
            wakeup_651()
            uart = UART(0, baudrate=19200, tx=Pin(0), rx=Pin(1), bits=8, parity=None, stop=1)
            uart.write(DRIFT_RIGHT)
            should_redirect = True

        elif '/brake' in web_request:
            print(" -> Dashboard: Handbrake Applied")
            wakeup_651()
            uart = UART(0, baudrate=19200, tx=Pin(0), rx=Pin(1), bits=8, parity=None, stop=1)
            uart.write(MOTOR_BRAKE)
            should_redirect = True

        elif '/stop' in web_request:
            print(" -> Dashboard: Game Over Sequence Triggered")
            headlights_active = False
            dashboard_led.value(0)
            wakeup_651()
            uart = UART(0, baudrate=19200, tx=Pin(0), rx=Pin(1), bits=8, parity=None, stop=1)
            uart.write(GAME_OVER_PAYLOAD)
            should_redirect = True

        # --- REDIRECT REFRESH ENGINE ---
        if should_redirect:
            connection.send('HTTP/1.1 303 See Other\nLocation: /\n\n')
        else:
            bat_status = get_battery_stats()
            current_html = generate_dashboard(headlights_active, bat_status)
            connection.send('HTTP/1.1 200 OK\nContent-Type: text/html\n\n' + current_html)
            
        connection.close()

    except Exception as network_error:
        print("[Pit Lane Error] Comm failure:", network_error)