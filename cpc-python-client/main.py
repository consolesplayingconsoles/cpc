#!/usr/bin/env python3

import sys
import os

# Only add the vendor path if it exists — relative to this file, so it works
# wherever the client dir is deployed (/opt/cpc/cpc-python-client, etc.).
vendor_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vendor')
if os.path.exists(vendor_path):
    sys.path.insert(0, vendor_path)

"""
main.py — production entrypoint.

Runs the strict live console interface. Parses the namespace-targeted
.env file, validates it (fail fast), and renders the keyboard / D-pad
navigable administrative menu against real host infrastructure.

Local interface testing without a host context uses dev.py instead
(see section 8 of CLAUDE.md — prod logic stays free of test conditionals).

Usage: python3 main.py <console>/.env
       python3 main.py            # auto-detects the sole console .env
"""
import os
import sys
import glob
import atexit
import io

# Ensure stdout can handle UTF-8 regardless of the terminal's locale settings.
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cpc_python_core.ui import renderer, menu as menu_mod, input as input_mod, actions
from cpc_python_core.ui.config import loader


ROOT = os.path.dirname(os.path.abspath(__file__))


def _resolve_env() -> str:
    if len(sys.argv) >= 2:
        return sys.argv[1]

    # No argument: a deployed console ships exactly one console directory
    # (deploy.sh strips every sibling), so discover the sole env automatically.
    # Console dirs sit one level up from this client dir (cpc-python-client/).
    candidates = [
        p for p in glob.glob(os.path.join(ROOT, "..", "*", ".env"))
        if os.path.basename(os.path.dirname(p)) != "pluto"
    ]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        loader._fatal("no <console>/.env found — pass one explicitly: main.py wii/.env")
    names = ", ".join(sorted(os.path.basename(os.path.dirname(p)) for p in candidates))
    loader._fatal(f"multiple console envs found ({names}) — pass one explicitly: main.py <console>/.env")


def _build_menu(config):
    """Build menu items and action map dynamically based on the current console."""
    items = []
    action_map = {}

    if config.get("NODE_KEY") == "wii":
        if config.get("GC_GAMES_PATH"):
            items.append("GameCube Games")
            action_map["GameCube Games"] = actions.list_gc_games
        if config.get("WII_GAMES_PATH"):
            items.append("Wii Games")
            action_map["Wii Games"] = actions.list_wii_games
        # pending gcn-pad + gcn-mic kernel support
        # items.append("Bongo Censor")
        # action_map["Bongo Censor"] = actions.bongo_censor

    if config.get("PLUTO_IP", "").strip():
        items.append("Chat")
        action_map["Chat"] = actions.chat_view

    return items, action_map


def run():
    env_path = _resolve_env()
    config   = loader.load(env_path)

    sys.stdout.write(renderer.ALT_ENTER)
    sys.stdout.flush()
    atexit.register(lambda: sys.stdout.write(renderer.ALT_EXIT + renderer.SHOW_CUR) or sys.stdout.flush())

    items, ACTION_MAP = _build_menu(config)
    menu  = menu_mod.Menu(items)
    stack = []

    while True:
        if stack:
            title, items, cursor = stack[-1]
            renderer.render_list(config, title, items, cursor)
            key = input_mod.get_key()

            if key == "QUIT":
                print(renderer.RESET)
                sys.exit(0)
            elif key == "BACK":
                stack.pop()
            elif key == "UP":
                cursor = (cursor - 1) % len(items)
                stack[-1] = (title, items, cursor)
            elif key == "DOWN":
                cursor = (cursor + 1) % len(items)
                stack[-1] = (title, items, cursor)
        else:
            renderer.render_menu(config, menu.items, menu.cursor)
            key = input_mod.get_key()

            if key == "QUIT":
                print(renderer.RESET)
                sys.exit(0)
            elif key == "UP":
                menu.up()
            elif key == "DOWN":
                menu.down()
            elif key == "ENTER":
                action = ACTION_MAP.get(menu.selected)
                if action:
                    items = action(config)
                    if items is not None:
                        stack.append((menu.selected, items, 0))


if __name__ == "__main__":
    run()
