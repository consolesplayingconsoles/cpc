#!/usr/bin/env bash
# build.sh -- build the CPC "ps3" firmware: a Pico that impersonates a PS3 controller.
# It is the PS3 input mode of the GP2040-CE fork in ../gp2040-ce (a submodule that carries
# our UartInput addon); the shared build script does the work. Emits ./firmware.uf2
# (gitignored). Prereqs and notes: ../gp2040-build.sh and README.md.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
exec "$HERE/../gp2040-build.sh" INPUT_MODE_PS3 "$HERE/firmware.uf2"
