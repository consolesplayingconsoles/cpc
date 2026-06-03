import os


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _list_dir(subdir: str, config: dict) -> list:
    """List contents of <console>/<subdir> for the current node."""
    node     = config["SHORT_NAME"]
    path     = os.path.join(_repo_root(), node, subdir)

    if not os.path.isdir(path):
        return [f"{node}/{subdir}  (not found)"]

    entries = sorted(os.listdir(path))
    if not entries:
        return [f"{node}/{subdir}  (empty)"]

    return [f"[{node}/{subdir}]"] + [f"  {e}" for e in entries]


def list_roms(config: dict) -> list:
    return _list_dir("roms", config)


def list_share(config: dict) -> list:
    return _list_dir("share", config)
