#!/usr/bin/env python3
"""
dev.py — local development entrypoint.

Bypasses all live infrastructure checks and force-feeds a complete
layout into the UI engine so every menu and feature is testable
without physical hardware or a production host context.

Usage: python3 dev.py <console>
       python3 dev.py wii
       python3 dev.py ps3
"""
import os
import sys
import atexit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Local dev runs on a trusted developer terminal — force full color on,
# regardless of how it advertises itself. Production (main.py) leaves this
# unset and only colors when the terminal explicitly reports support.
os.environ.setdefault("CPC_DEV", "1")

from core.ui import renderer, menu as menu_mod, input as input_mod, actions


def _resolve_console() -> str:
    if len(sys.argv) < 2:
        print("Usage: python3 dev.py <console>  (e.g. wii, ps3, dc)")
        sys.exit(1)
    return sys.argv[1].lower()


def _load_dev_config(console: str) -> dict:
    root = os.path.dirname(os.path.abspath(__file__))
    for filename in (".env",):
        path = os.path.join(root, console, filename)
        if os.path.exists(path):
            config = {}
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, _, v = line.partition("=")
                    v = v.strip()
                    if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                        v = v[1:-1]
                    config[k.strip()] = v
            config.setdefault("SHORT_NAME", console)
            config.setdefault("BUTTON_CONFIRM",     "A")
            config.setdefault("BUTTON_CANCEL",      "B")
            config.setdefault("BUTTON_BACK",        "<")
            config.setdefault("BUTTON_UP",          "UP")
            config.setdefault("BUTTON_DOWN",        "DOWN")
            return config

    print(f"Error: no env file found for '{console}' (checked {console}/.env)")
    sys.exit(1)


MENU_ITEMS = []

ACTION_MAP = {}


def run():
    console = _resolve_console()
    config  = _load_dev_config(console)
    sys.stdout.write(renderer.ALT_ENTER)
    sys.stdout.flush()
    atexit.register(lambda: sys.stdout.write(renderer.ALT_EXIT + renderer.SHOW_CUR) or sys.stdout.flush())
    menu   = menu_mod.Menu(MENU_ITEMS)

    stack  = []

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
