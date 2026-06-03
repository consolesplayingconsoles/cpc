import os
import sys

REQUIRED_KEYS = [
    "NODE_NAME",
    "SHORT_NAME",
    "MANUFACTURER",
    "HOST_IP",
    "SSH_USER",
    "SSH_KEY_PATH",
    "UI_PRIMARY_COLOR",
    "UI_SECONDARY_COLOR",
    "BUTTON_CONFIRM",
    "BUTTON_CANCEL",
    "BUTTON_BACK",
    "BUTTON_UP",
    "BUTTON_DOWN",
]


def load(env_path: str) -> dict:
    """Parse an env file and return a config dict.
    Fails fast if any required key is missing or empty."""
    if not os.path.exists(env_path):
        _fatal(f"env file not found: {env_path}")

    config = {}
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            config[key.strip()] = value.strip()

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
