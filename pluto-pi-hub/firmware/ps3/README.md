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

The Pi-side sender that feeds the UART is `pluto-pi-hub/bridges/hid.py`.

## Files (committed)
- `uartinput.h` / `uartinput.cpp` — the GP2040 addon. Reads the frame
  `AA 55 <dpad> <btnL> <btnH> <xor>` on `uart0` (GP0 TX / GP1 RX) and writes it
  into the gamepad state each loop. Frame `dpad=0xFF, btnL=0x01` = reboot to
  BOOTSEL (remote reflash, no physical button).
- `fsdata.c` — a stub so the build can skip the web-config UI (`SKIP_WEBBUILD`)
  without a link error.
- `build.sh` / `flash.sh` — build `firmware.uf2` (gitignored), and flash it over
  the UART.

## One-time GP2040-CE wiring
`build.sh` syncs our files and compiles, but does **not** patch GP2040 for you.
Once, in `$GP2040_DIR` (default `~/GP2040-CE`):

1. Clone GP2040-CE and the Pico SDK (ref **2.2.0**) at `$PICO_SDK_PATH` (default
   `~/pico-sdk`). apt: `cmake gcc-arm-none-eabi libnewlib-arm-none-eabi
   libstdc++-arm-none-eabi-newlib build-essential`.
2. `src/gp2040.cpp`: add `#include "addons/uartinput.h"` with the other addon
   includes, and `addons.LoadAddon(new UartInput());` with the other input addons.
3. `CMakeLists.txt`: add `src/addons/uartinput.cpp` to the GP2040-CE sources.
4. `src/gp2040.cpp`: the mode **is** the role. Where it reads
   `InputMode inputMode = bootAction.inputMode;`, use
   `InputMode inputMode = InputMode::INPUT_MODE_PS3;` (`ps3` = present as a PS3 pad;
   an `xinput` role would be the same addon, different mode). *Cleanup TODO: make
   it a config default, not a source edit.*

Then `./build.sh` → `firmware.uf2`.

## Flashing
The Pico runs GP2040 (no MicroPython REPL), so it flashes via BOOTSEL + `picotool`,
not `mpremote`. `./flash.sh` does it: send the reset frame down the UART → the Pico
drops to BOOTSEL → `picotool load -x firmware.uf2`. First flash: hold BOOTSEL,
replug, then `picotool load -x firmware.uf2`.

## Note for the Maple/Dreamcast consumer
That adapter gets confused if you hot-swap modes/controllers while the console is
powered. After any reflash, **fully power-cycle the console + adapter** before
testing.
