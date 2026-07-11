from machine import UART, Pin
import time

# 1. Wake up the communication port
brc_pin = Pin(2, Pin.OUT)
print("Waking up serial line...")
brc_pin.value(1)
time.sleep(0.5)
for _ in range(3):
    brc_pin.value(0)
    time.sleep(0.2)
    brc_pin.value(1)
    time.sleep(0.2)
time.sleep(2.0)

# 2. Open UART
uart = UART(0, baudrate=19200, tx=Pin(0), rx=Pin(1), bits=8, parity=None, stop=1)

print("Sending Stop Command to restore physical button control...")
# \x80 = Start Open Interface
# \xad = Opcode 173: Stop Open Interface (reboots to normal consumer mode)
release_payload = b'\x80\xad'

uart.write(release_payload)
print("Done! The Roomba should play a chime, reset its lights, and buttons will work.")
