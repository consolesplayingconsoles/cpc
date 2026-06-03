#!/usr/bin/env python3
"""
dev.py — local development entrypoint.

Bypasses all live infrastructure checks and force-feeds a complete
layout into the UI engine so every menu and feature is testable
without physical hardware or a production host context.
"""
import os
import sys
import atexit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.ui import renderer, menu as menu_mod, input as input_mod, actions

DEV_ENV = os.path.join(os.path.dirname(__file__), "wii", "dev.env")


def _load_dev_config() -> dict:
    config = {}
    if os.path.exists(DEV_ENV):
        with open(DEV_ENV) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                config[k.strip()] = v.strip()
    config.setdefault("NODE_NAME",          "Wii")
    config.setdefault("SHORT_NAME",         "wii")
    config.setdefault("MANUFACTURER",       "Nintendo")
    config.setdefault("BUTTON_CONFIRM",     "A")
    config.setdefault("BUTTON_CANCEL",      "Q")
    config.setdefault("BUTTON_BACK",        "◀")
    config.setdefault("BUTTON_UP",          "UP")
    config.setdefault("BUTTON_DOWN",        "DOWN")
    config.setdefault("UI_PRIMARY_COLOR",   "#75B2DD")
    config.setdefault("UI_SECONDARY_COLOR", "#4A6878")
    return config


MENU_ITEMS = [
    "List ROMs",
    "List Share",
]

ACTION_MAP = {
    "List ROMs":  actions.list_roms,
    "List Share": actions.list_share,
}


def run():
    config = _load_dev_config()
    sys.stdout.write(renderer.ALT_ENTER)
    sys.stdout.flush()
    atexit.register(lambda: sys.stdout.write(renderer.ALT_EXIT + renderer.SHOW_CUR) or sys.stdout.flush())
    menu   = menu_mod.Menu(MENU_ITEMS)

    # Stack of (title, items) — when non-empty we're in a list view.
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
                    stack.append((menu.selected, items, 0))


if __name__ == "__main__":
    run()
