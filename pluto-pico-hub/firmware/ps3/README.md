# firmware/ps3 — the Pico impersonates a PS3 controller

This firmware makes a Raspberry Pi Pico **present itself as a PS3 / DualShock 3
USB gamepad** to whatever it's plugged into. It's the Pico running
[GP2040-CE](https://github.com/OpenStickCommunity/GP2040-CE) (in PS3 mode) plus
our small **UartInput** addon, which makes GP2040 read its inputs from a UART
feed instead of physical buttons.

It is **target-agnostic** — a PS3 controller is a passport: anything that accepts
one accepts this. It's **tested driving a real Dreamcast** through a USB→Maple
adapter (the adapter wants a PS3 pad, and the DC menu navigates), but the same
firmware is just as valid on a PS3, a PC, or a PS5 through a licensed PS-controller
upgrader. The Dreamcast is simply the first thing we proved it on.

The Pi-side sender that feeds the UART is `pluto-pico-hub/bridges/hid.py`.

## Files (committed)
- `uartinput.h` / `uartinput.cpp` — the GP2040 addon, now carried by the GP2040-CE fork
  (`../gp2040-ce`), which is what the build uses. These copies are superseded: delete them
  once the fork's commit is pushed. It reads the frame
  `AA 55 <dpad> <btnL> <btnH> <lx> <ly> <rx> <ry> <xor>` on `uart0` (GP0 TX / GP1 RX) and writes
  it into the gamepad state each loop. Frame `dpad=0xFF, btnL=0x01` = reboot to
  BOOTSEL (remote reflash, no physical button).
- `fsdata.c` — a stub so the build can skip the web-config UI (`SKIP_WEBBUILD`)
  without a link error.
- `build.sh` / `flash.sh` — build `firmware.uf2` (gitignored), and flash it over
  the UART.

## Build
There is no hand-wired checkout any more: the firmware is the **GP2040-CE fork**
(`consolesplayingconsoles/GP2040-CE`) checked out as the `../gp2040-ce` submodule. It carries
our `UartInput` addon, the mouse driver, and the input mode fixed **per build**
(`-DCPC_INPUT_MODE`): `ps3` and `mouse` are two modes of the same firmware.

1. apt: `cmake gcc-arm-none-eabi libnewlib-arm-none-eabi libstdc++-arm-none-eabi-newlib build-essential`
2. The Pico SDK (ref **2.2.0**) at `$PICO_SDK_PATH` (default `~/pico-sdk`).
3. `git submodule update --init pluto-pico-hub/firmware/gp2040-ce`, then
   `git -C pluto-pico-hub/firmware/gp2040-ce submodule update --init` (its TinyUSB fork and
   Pico-PIO-USB).

Then `./build.sh` → `firmware.uf2` (it calls `../gp2040-build.sh INPUT_MODE_PS3`).

## Flashing
The Pico runs GP2040 (no MicroPython REPL), so it flashes via BOOTSEL + `picotool`,
not `mpremote`. `./flash.sh` does it: send the reset frame down the UART → the Pico
drops to BOOTSEL → `picotool load -x firmware.uf2`. First flash: hold BOOTSEL,
replug, then `picotool load -x firmware.uf2`.

## Note for the Maple/Dreamcast consumer
That adapter gets confused if you hot-swap modes/controllers while the console is
powered. After any reflash, **fully power-cycle the console + adapter** before
testing.
