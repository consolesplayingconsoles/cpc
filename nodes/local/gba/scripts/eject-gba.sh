#!/bin/bash
set -e

VOLUME="/Volumes/gba"

if [ ! -d "$VOLUME" ]; then
  echo "GBA SD card not mounted at $VOLUME"
  exit 1
fi

echo "Cleaning junk files..."
mdutil -i off "$VOLUME" > /dev/null 2>&1 || true
find "$VOLUME" -name ".DS_Store" -delete
find "$VOLUME" -name "._*" -delete
dot_clean "$VOLUME"

echo "Ejecting..."
diskutil eject "$VOLUME"

echo "Done."
