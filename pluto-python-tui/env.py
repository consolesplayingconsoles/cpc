"""
core/env.py — shared environment file parsing.

Provides raw key=value parsing used by both the TUI (via core.ui.config.loader)
and standalone scripts (e.g. bridge scripts that need to read peer console envs).

No validation, no fatal exits — that is the caller's responsibility.
"""
import os


def load_env(path):
    """Parse a .env file and return a plain dict.
    Lines starting with '#' and lines without '=' are silently skipped.
    Returns an empty dict if the file does not exist.
    """
    config = {}
    if not os.path.exists(path):
        return config
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, _, v = line.partition('=')
            config[k.strip()] = v.strip()
    return config


def sibling_env(console, anchor):
    """Load the .env file of a sibling console directory.

    anchor  -- __file__ of the calling script. Used to locate the repo root
               (one level above the console directory the script lives in).

    Example (from batocera/dreame_to_wii_bridge.py):
        wii_cfg = sibling_env('wii', __file__)
    """
    script_dir = os.path.dirname(os.path.abspath(anchor))
    path = os.path.normpath(os.path.join(script_dir, '..', console, '.env'))
    return load_env(path)
