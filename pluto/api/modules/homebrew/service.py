"""Homebrew: discover buildable projects by path convention and run their scripts.

Convention (one naming, scripts are free to differ):
    nodes/local/<node>/homebrew/mods/<game>/<mod>/build.sh    -> kind "mods"
    nodes/local/<node>/homebrew/games/<game>/build.sh         -> kind "games"
    nodes/local/<node>/homebrew/tools/<tool>/build.sh         -> kind "tools"

A folder is an item when it has build.sh. Parameters come from .env.sample files: a mod gets its game's (mods/<game>/, shared
by every mod of that game, e.g. the base ROM path) plus its own; each value is saved to the
.env beside the sample it came from, which every repo gitignores. A mod's own key wins over
a game key of the same name.

A game folder (mods/<game>/) can carry a CATALOGUE file: one line "<system> <game-key>",
the game's identity in the Media catalogue (catalogue/<system>/digital.json). It gives the
real title, the cover and the Media link, and tells deploy which system the builds are.
A game made from scratch (games/<name>/) can carry its own.

A build announces what it produced with a "##OUTPUT:<path>" line (like deploy.sh's
##STEP:). The last output per item is kept (outputs file, set by the API), so Deploy can
publish it into the Lab library as a catalogue file and send it on to other nodes.

A released item has a RELEASE file: one line "<owner>/<repo> <tag-prefix>" pointing at its
GitHub releases (the distribution repo, e.g. game-mods). The newest stable release whose
tag starts with the prefix is shown; if there is none, the newest pre-release.
"""
import os
import re
import signal
import subprocess
import threading
import time
import json
from urllib.request import urlopen, Request

KINDS = ("mods", "games", "tools")
ACTIONS = ("build",)                  # sending is the catalogue job, never a per-item script
_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")

_STAGE = re.compile(r"(alpha|beta|rc|pre)", re.I)
_VERSION = re.compile(r"v?(\d+(?:\.\d+)*(?:-[A-Za-z0-9.]+)?)$")
_releases_cache = {}           # "owner/repo" -> (fetched_at, releases list or None)
_RELEASES_TTL = 600            # GitHub unauthenticated API allows 60 calls/hour

_titles_cache = {}             # system -> (mtime, {game-key: title})

_outputs_path = None           # set by the API: <pluto>/logs/homebrew-outputs.json
_outputs_lock = threading.Lock()

_procs = {}                    # item id -> Popen of the running action
_procs_lock = threading.Lock()


def _nodash(text):
    """No em or en dashes in the UI: a spaced dash used as a pause becomes a colon, any
    other one a comma (titles and descriptions come from READMEs and GitHub, not us)."""
    if not text:
        return text
    text = re.sub(r"\s+[\u2014\u2013]\s+", ": ", text)
    return re.sub(r"\s*[\u2014\u2013]\s*", ", ", text)


def _unquote(raw):
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        inner = raw[1:-1]
        if raw[0] == "'":
            return inner
        return re.sub(r'\\(["\\$`])', r"\1", inner)   # undo _quote's escapes
    return raw


def _parse_env(path):
    """KEY -> value, last one wins. Missing file -> {}."""
    values = {}
    if not os.path.isfile(path):
        return values
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = _KEY.match(line.strip())
            if m:
                values[m.group(1)] = _unquote(m.group(2))
    return values


def _parse_sample(path):
    """Ordered params from a .env.sample. Comment lines directly above a key are its help;
    a blank line ends a comment block (so a file's header comment is not a param's help)."""
    params, notes = [], []
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                notes = []
            elif s.startswith("#"):
                notes.append(s.lstrip("#").strip())
            else:
                m = _KEY.match(s)
                if m:
                    params.append({"key": m.group(1), "default": _unquote(m.group(2)),
                                   "help": " ".join(notes)})
                notes = []
    return params


def _readme(folder):
    """(title, first paragraph) of README.md, or (None, None)."""
    path = os.path.join(folder, "README.md")
    if not os.path.isfile(path):
        return None, None
    title, para, lines = None, [], open(path, encoding="utf-8").read().splitlines()
    for line in lines:
        s = line.strip()
        if title is None and s.startswith("# "):
            title = s[2:].strip()
            continue
        if not s:
            if para:
                break
            continue
        if s.startswith(("#", "```", "|", "-", "*", ">")) and not para:
            continue
        para.append(s)
    text = _nodash(" ".join(para))
    return _nodash(title), (text[:400] + "...") if len(text) > 400 else (text or None)


def _node_name(repo_root, node):
    """The node's display name (NODE_NAME in its .env, else .env.sample), e.g. "Mega Drive"."""
    for f in (".env", ".env.sample"):
        name = _parse_env(os.path.join(repo_root, "nodes", "local", node, f)).get("NODE_NAME")
        if name:
            return name
    return node


def _releases(repo):
    now = time.time()
    hit = _releases_cache.get(repo)
    if hit and now - hit[0] < _RELEASES_TTL:
        return hit[1]
    try:
        req = Request("https://api.github.com/repos/%s/releases?per_page=100" % repo,
                      headers={"Accept": "application/vnd.github+json", "User-Agent": "pluto-homebrew"})
        with urlopen(req, timeout=4) as r:
            data = json.load(r)
    except Exception:
        data = None                                   # offline / rate limited: no links, retry later
    _releases_cache[repo] = (now, data)
    return data


def _release(folder):
    path = os.path.join(folder, "RELEASE")
    if not os.path.isfile(path):
        return None
    ref = next((l.split() for l in open(path, encoding="utf-8") if l.strip() and not l.startswith("#")), [])
    if len(ref) != 2:
        return None
    repo, prefix = ref
    matches = [r for r in (_releases(repo) or [])
               if not r.get("draft") and r.get("tag_name", "").startswith(prefix)]
    if not matches:
        return None
    matches.sort(key=lambda r: r.get("published_at") or "", reverse=True)
    stable = [r for r in matches if not r.get("prerelease") and not _STAGE.search(r["tag_name"][len(prefix):])]
    pick = (stable or matches)[0]
    version = _VERSION.search(pick["tag_name"])
    return {"url": pick.get("html_url"), "name": _nodash(pick.get("name") or pick["tag_name"]),
            "version": version.group(1) if version else None, "stable": bool(stable)}


def _catalogue_game(repo_root, folder):
    """{system, key, title} from the CATALOGUE file in folder, or None. Title from the
    catalogue's digital.json (cached by mtime); the key itself if the game isn't listed."""
    path = os.path.join(folder, "CATALOGUE")
    if not os.path.isfile(path):
        return None
    ref = next((l.split() for l in open(path, encoding="utf-8") if l.strip() and not l.startswith("#")), [])
    if len(ref) != 2:
        return None
    system, key = ref
    digital = os.path.join(repo_root, "catalogue", system, "digital.json")
    titles = {}
    try:
        mtime = os.path.getmtime(digital)
        hit = _titles_cache.get(system)
        if hit and hit[0] == mtime:
            titles = hit[1]
        else:
            with open(digital, encoding="utf-8") as f:
                games = json.load(f).get("games", {})
            titles = {k: (v.get("title") if isinstance(v, dict) else None) for k, v in games.items()}
            _titles_cache[system] = (mtime, titles)
    except (OSError, ValueError):
        pass
    return {"system": system, "key": key, "title": _nodash(titles.get(key) or key), "listed": key in titles}


def _param_scopes(folder, group):
    """[(scope, sample_path)] for an item: its game's sample first (mods only), then its own."""
    scopes = []
    if group:
        scopes.append(("game", os.path.join(os.path.dirname(folder), ".env.sample")))
    scopes.append(("item", os.path.join(folder, ".env.sample")))
    return [(sc, p) for sc, p in scopes if os.path.isfile(p)]


def _item(repo_root, node, kind, group, name, folder):
    scopes = _param_scopes(folder, group)
    own = set()
    for sc, sample in scopes:
        if sc == "item":
            own = {p["key"] for p in _parse_sample(sample)}
    params, env_paths = [], []
    for sc, sample in scopes:
        env_path = os.path.join(os.path.dirname(sample), ".env")
        env_paths.append(os.path.relpath(env_path, repo_root))
        current = _parse_env(env_path)
        for p in _parse_sample(sample):
            if sc == "game" and p["key"] in own:
                continue
            p["value"] = current.get(p["key"], p["default"])
            p["scope"] = sc
            params.append(p)
    title, description = _readme(folder)
    item_id = "/".join(x for x in (node, kind, group, name) if x)
    return {
        "id": item_id, "node": node, "nodeName": _node_name(repo_root, node),
        "kind": kind, "group": group, "name": name,
        "title": title or name, "description": description,
        "path": os.path.relpath(folder, repo_root),
        "actions": [a for a in ACTIONS if os.path.isfile(os.path.join(folder, a + ".sh"))],
        "params": params,
        "paramsPaths": env_paths,
        "running": item_id in _procs,
        "release": _release(folder),
        "output": last_output(item_id),
        "game": _catalogue_game(repo_root, os.path.dirname(folder) if group else folder),
    }


def _dirs(parent):
    if not os.path.isdir(parent):
        return []
    return sorted(d for d in os.listdir(parent)
                  if not d.startswith(".") and os.path.isdir(os.path.join(parent, d)))


def discover(repo_root):
    items = []
    local = os.path.join(repo_root, "nodes", "local")
    for node in _dirs(local):
        hb = os.path.join(local, node, "homebrew")
        for game in _dirs(os.path.join(hb, "mods")):
            for mod in _dirs(os.path.join(hb, "mods", game)):
                folder = os.path.join(hb, "mods", game, mod)
                if os.path.isfile(os.path.join(folder, "build.sh")):
                    items.append(_item(repo_root, node, "mods", game, mod, folder))
        for kind in ("games", "tools"):
            for name in _dirs(os.path.join(hb, kind)):
                folder = os.path.join(hb, kind, name)
                if os.path.isfile(os.path.join(folder, "build.sh")):
                    items.append(_item(repo_root, node, kind, None, name, folder))
    return items


def find(repo_root, item_id):
    """The item with this id, re-discovered (never trust a client-supplied path)."""
    return next((i for i in discover(repo_root) if i["id"] == item_id), None)


def _quote(value):
    return '"%s"' % value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")


def save_params(repo_root, item, values):
    """Write each .env the item's params come from (game, then own), in its .env.sample's
    layout: a key gets the submitted value (or keeps its current one), comments stay, and
    keys only present in the old .env are kept at the end so nothing set by hand is lost."""
    folder = os.path.join(repo_root, item["path"])
    scopes = _param_scopes(folder, item["group"])
    if not scopes:
        raise ValueError("this item has no parameters")
    owners = {p["key"]: p["scope"] for p in item["params"]}
    for sc, sample_path in scopes:
        _write_env(sample_path, {k: v for k, v in values.items() if owners.get(k) == sc})


def _write_env(sample_path, values):
    env_path = os.path.join(os.path.dirname(sample_path), ".env")
    current = _parse_env(env_path)
    raw_lines = {}                                   # key -> its original line, for keys kept as-is
    if os.path.isfile(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                m = _KEY.match(line.strip())
                if m:
                    raw_lines[m.group(1)] = line.strip() + "\n"
    declared = set()
    out = []
    with open(sample_path, encoding="utf-8") as f:
        for line in f:
            m = _KEY.match(line.strip())
            if m:
                key = m.group(1)
                declared.add(key)
                val = values.get(key, current.get(key, _unquote(m.group(2))))
                out.append("%s=%s\n" % (key, _quote(str(val))))
            else:
                out.append(line if line.endswith("\n") else line + "\n")
    extra = [k for k in current if k not in declared]
    if extra:
        out.append("\n# kept from the previous .env (not in .env.sample)\n")
        out.extend(raw_lines[k] for k in extra)
    tmp = env_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.writelines(out)
    os.replace(tmp, env_path)


def start(repo_root, item, action):
    """Start an action; returns the Popen (stdout = merged output) or raises RuntimeError."""
    if action not in item["actions"]:
        raise RuntimeError("no %s.sh for %s" % (action, item["id"]))
    folder = os.path.join(repo_root, item["path"])
    env = os.environ.copy()
    env["PATH"] = "/usr/local/bin:/opt/homebrew/bin:" + env.get("PATH", "")   # docker/colima when launched outside a login shell
    env["PYTHONUNBUFFERED"] = "1"
    with _procs_lock:
        if item["id"] in _procs:
            raise RuntimeError("%s is already running" % item["id"])
        proc = subprocess.Popen(["bash", os.path.join(folder, action + ".sh")], cwd=folder, env=env,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, errors="replace", start_new_session=True)
        _procs[item["id"]] = proc
    return proc


def set_outputs_file(path):
    global _outputs_path
    _outputs_path = path


def _load_outputs():
    try:
        with open(_outputs_path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, TypeError):
        return {}


def record_output(item_id, path):
    """Remember an item's latest build output (from a ##OUTPUT: line)."""
    if not _outputs_path:
        return
    with _outputs_lock:
        data = _load_outputs()
        data[item_id] = {"path": path, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        os.makedirs(os.path.dirname(_outputs_path), exist_ok=True)
        tmp = _outputs_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, sort_keys=True)
        os.replace(tmp, _outputs_path)


def last_output(item_id):
    """{path, at} of the item's last build output if the file still exists, else None."""
    out = _load_outputs().get(item_id)
    return out if out and os.path.isfile(out.get("path", "")) else None


_UNSAFE = re.compile(r'[\\/:*?"<>|]+')


def lab_filename(item, output_path):
    """The name a build gets in the Lab library, in the catalogue's naming (names.py):
    "<game title> [<mod> v<version>]<ext>". The bracket makes it a variant of the game, so it
    groups with the game but never replaces the original file. Vanilla is [Vanilla Build]:
    a rebuilt ROM, as opposed to the regular retail one."""
    game = item.get("game") or {}
    title = _UNSAFE.sub(" ", game.get("title") or item["name"]).strip()
    mod = "Vanilla Build" if item["name"] == "vanilla" else item["title"]
    version = (item.get("release") or {}).get("version")
    tag = _UNSAFE.sub(" ", "%s v%s" % (mod, version) if version else mod).replace("[", "(").replace("]", ")").strip()
    return "%s [%s]%s" % (title, tag, os.path.splitext(output_path)[1].lower())


def finish(item_id):
    with _procs_lock:
        _procs.pop(item_id, None)


def stop(item_id):
    """Terminate the running action's whole process group (build containers, Flycast...)."""
    with _procs_lock:
        proc = _procs.get(item_id)
    if not proc:
        return False
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    return True
