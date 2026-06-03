#!/usr/bin/env bash
# Start local API and Vite dev server together.
# Ctrl-C kills both.

trap 'kill 0' SIGINT

python3 api/api.py .env &
npm run dev &

wait
