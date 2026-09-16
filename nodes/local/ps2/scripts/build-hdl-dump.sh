#!/bin/bash
# Build hdl_dump (ps2homebrew/hdl-dump, pinned) for this Mac and install it at HDL_DUMP
# from nodes/local/ps2/.env. Needs git + Xcode command line tools. No sudo.
set -e

COMMIT=32c296c
ENV_FILE="$(cd "$(dirname "$0")/.." && pwd)/.env"
HDL_DUMP=$(grep -E '^HDL_DUMP=' "$ENV_FILE" | cut -d= -f2-)
HDL_DUMP="${HDL_DUMP/#\~/$HOME}"
if [ -z "$HDL_DUMP" ]; then
  echo "HDL_DUMP is not set in $ENV_FILE"
  exit 1
fi

SRC=$(mktemp -d)
trap 'rm -rf "$SRC"' EXIT
git clone -q https://github.com/ps2homebrew/hdl-dump "$SRC"
git -C "$SRC" checkout -q "$COMMIT"
make -C "$SRC" -j4 RELEASE=yes > "$SRC/build.log" 2>&1 || { tail -20 "$SRC/build.log"; exit 1; }

mkdir -p "$(dirname "$HDL_DUMP")"
cp "$SRC/hdl_dump" "$HDL_DUMP"
echo "Installed $HDL_DUMP ($("$HDL_DUMP" 2>&1 | head -1))"
