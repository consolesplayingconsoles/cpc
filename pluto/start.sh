#!/usr/bin/env bash
# Start local API and Vite dev server raw and parallel.
# Ctrl-C kills both.

trap 'kill 0' SIGINT

# Force Python to flush print statements instantly
export PYTHONUNBUFFERED=1

# Start the API server in the background
python3 api/api.py &

# Start Vite in the background, telling it explicitly NOT to clear your terminal
npm run dev -- --clearScreen false &

wait
