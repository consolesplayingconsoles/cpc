import os
import sys

from cpc_python_core.env import load_env

# Keys the local console interface needs to render and brand itself.
# Networking / SSH fields (HOST_IP, SSH_USER, SSH_KEY_PATH, CUSTOM_SSH_ALIAS)
# are deploy-time concerns validated by deploy.sh — not required to run the
# TUI on the console itself, so they are intentionally not listed here.
REQUIRED_KEYS = [
    "NODE_NAME",
    "SHORT_NAME",
    "MANUFACTURER",
    "UI_PRIMARY_COLOR",
    "UI_SECONDARY_COLOR"
]


def load(env_path: str) -> dict:
    """Parse an env file and return a config dict.
    Fails fast if any required key is missing or empty."""
    if not os.path.exists(env_path):
        _fatal(f"env file not found: {env_path}")

    config = load_env(env_path)

    missing = [k for k in REQUIRED_KEYS if not config.get(k)]
    if missing:
        _fatal_missing(missing, env_path)

    return config


def _fatal(message: str):
    print(f"\n  [BOOT ERROR] {message}\n", file=sys.stderr)
    sys.exit(1)


def _fatal_missing(keys: list, env_path: str):
    lines = [
        "",
        "  ┌─ BOOT ERROR ──────────────────────────────────────┐",
        f"  │  Missing or empty fields in: {env_path}",
        "  │",
    ]
    for k in keys:
        lines.append(f"  │    ✗  {k}")
    lines += [
        "  │",
        "  │  Copy console/.env.sample and fill in all values.",
        "  └────────────────────────────────────────────────────┘",
        "",
    ]
    print("\n".join(lines), file=sys.stderr)
    sys.exit(1)
