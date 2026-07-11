"""
Roomba 651 MicroPython Control Template
---------------------------------------
A robust boilerplate template for interfacing a Raspberry Pi Pico with an
iRobot Roomba 651 via a bidirectional logic level shifter.

This script configures a hardware baud rate override down to 19,200 baud,
bypasses passive-mode firmware restrictions by entering Full Mode, and
simultaneously executes a synchronous LED flash and a 4-note ascending chime.
"""

from machine import UART, Pin
import time

# ==========================================
# 1. HARDWARE DEFINITIONS & CONSTANTS
# ==========================================
# UART0 default pins on Raspberry Pi Pico: GP0 (TX), GP1 (RX)
UART_PORT = 0
TX_PIN = 0
RX_PIN = 1

# Device Detect / Baud Rate Change (BRC) pin used to wake up & configure Roomba
BRC_PIN_NUM = 2

# The Roomba 651 hardware fallback speed when BRC is toggled on boot
TARGET_BAUD = 19200

# ==========================================
# 2. BAUD RATE BOOTSTRAP SEQUENCE
# ==========================================
print("[Initialization] Initializing Roomba 651 BRC wake pulse...")
brc = Pin(BRC_PIN_NUM, Pin.OUT)

# Hold line high briefly to establish a clean state
brc.value(1)
time.sleep(0.5)

# Pulse the BRC line low 3 times during the boot window.
# Per iRobot specifications, this drops the serial engine down to 19,200 baud.
for _ in range(3):
    brc.value(0)
    time.sleep(0.2)  # Low pulse length
    brc.value(1)
    time.sleep(0.2)  # High pulse relaxation window

print("[Initialization] Waiting 2 seconds for bootloader stabilization...")
time.sleep(2.0)

# ==========================================
# 3. SERIAL INSTANTIATION
# ==========================================
# Open UART communication channel matching the Roomba's fallback configuration
uart = UART(
    UART_PORT,
    baudrate=TARGET_BAUD,
    tx=Pin(TX_PIN),
    rx=Pin(RX_PIN),
    bits=8,
    parity=None,
    stop=1
)

# Clear any rogue electrical or transmission noise out of the serial FIFO buffer
if uart.any():
    uart.read()

# ==========================================
# 4. PRE-COMPILED MACHINE BYTE STREAM
# ==========================================
print("[Data Engine] Formatting and dispatching pre-compiled byte block...")

# Assembling instructions into a unified byte-literal sequence prevents
# MicroPython transmission jitter from causing Roomba framing errors.
#
# Byte Assembly Mapping:
# \x80 = Opcode 128: Start Open Interface
# \x84 = Opcode 132: Enter Full Mode (Disables safe timeouts & unlocks speaker)
# \x8b = Opcode 139: LED Manipulation Control
# \x0d = Data Byte: Binary 00001101 (Illuminates Dirt Detect, Spot, and Dock)
# \xff = Data Byte: Sets central Power LED color to pure Amber / Orange
# \xff = Data Byte: Sets central Power LED intensity to maximum (100%)
# \x8c = Opcode 140: Define Custom Song Structure
# \x00 = Data Byte: Assigns song profile to Memory Slot Index 0
# \x04 = Data Byte: Explicitly declares exactly 4 note-duration pairs follow
# \x43\x10 = Pair 1: Pitch 67 (Note G), Duration 16 (1/4 second execution)
# \x45\x10 = Pair 2: Pitch 69 (Note A), Duration 16 (1/4 second execution)
# \x47\x10 = Pair 3: Pitch 71 (Note B), Duration 16 (1/4 second execution)
# \x48\x20 = Pair 4: Pitch 72 (High C), Duration 32 (1/2 second execution)
# \x8d = Opcode 141: Play Custom Song Structure
# \x00 = Data Byte: Executes song array stored at Memory Slot Index 0

templated_payload = b'\x80\x84\x8b\x0d\xff\xff\x8c\x00\x04\x43\x10\x45\x10\x47\x10\x48\x20\x8d\x00'

# Dispatch the entire memory cluster down the physical TX pipeline at once
uart.write(templated_payload)

print("[Status] Code injection successful. Roomba active.")
