# Roomba baud/BRC diagnostic. Tries 4 combos. For each:
#   - opens UART, does OI Start->Full
#   - READS sensor packet 3 (objective: valid voltage => this baud has a live link)
#   - fires LED + a single beep (subjective: you HEAR which combo drives the Roomba)
# Paste the whole console output back.
from machine import UART, Pin
import time

brc = Pin(2, Pin.OUT)
led = Pin(15, Pin.OUT)

def pulse_brc():
    brc.value(1); time.sleep(0.5)
    for _ in range(3):
        brc.value(0); time.sleep(0.2)
        brc.value(1); time.sleep(0.2)
    time.sleep(2.0)

def try_config(baud, do_pulse, label):
    print("=== TRY %s : baud=%d pulse=%s ===" % (label, baud, do_pulse))
    brc.value(1)
    if do_pulse:
        pulse_brc()
    else:
        time.sleep(0.3)
    u = UART(0, baudrate=baud, tx=Pin(0), rx=Pin(1), bits=8, parity=None, stop=1)
    time.sleep(0.1)
    if u.any():
        u.read()
    # OI init: Start -> Full
    u.write(b'\x80'); time.sleep(0.1)
    u.write(b'\x84'); time.sleep(0.1)
    # objective link test: request sensor group packet 3 (10-byte reply)
    if u.any():
        u.read()
    u.write(bytes([142, 3]))
    time.sleep(0.25)
    data = u.read()
    if data:
        print("  RX %d bytes: %s" % (len(data), data))
        if len(data) >= 10:
            pkt = data[-10:]
            volt = (pkt[1] << 8) | pkt[2]
            print("  -> voltage_mv=%d  (sane if ~10000-18000) *** LIVE LINK ***" % volt)
    else:
        print("  RX: none (no response at this baud)")
    # subjective test: LED on + one beep, so you can tell which combo actuates
    led.value(1)
    u.write(b'\x8b\x0d\xff\xff')                       # Roomba LEDs on
    u.write(b'\x8c\x00\x01\x40\x20\x8d\x00')           # define song0 (one note) + play
    time.sleep(1.2)
    u.write(b'\x8b\x00\x00\x00')                       # Roomba LEDs off
    led.value(0)
    u.deinit()
    time.sleep(0.6)

CONFIGS = [
    (115200, False, "A_115200_nopulse"),
    (19200,  True,  "B_19200_pulse"),
    (19200,  False, "C_19200_nopulse"),
    (115200, True,  "D_115200_pulse"),
]

print("### Roomba baud probe start ###")
for baud, dp, label in CONFIGS:
    try:
        try_config(baud, dp, label)
    except Exception as e:
        print("  ERROR %s: %s" % (label, e))
print("### DONE - tell me which letter(s) beeped, and paste the RX lines ###")
