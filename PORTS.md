# Ports: a fourth homebrew kind

Built. This is what it does, and what it decided.

## What a port is

A port takes a game built for one system and makes it run on another. The
conversion of **Sonic The Hedgehog's Gameworld** (Sega Pico, 1994) into a Mega
Drive ROM is the first one.

It is not a mod. A mod changes a game on the system it already belongs to, so
one system answers every question: where the title and cover come from, which
library the build belongs in, which card it can be sent to. A port is the one
case where those answers split in two, and that is the whole reason it needs
its own kind rather than living in `mods/`.

| | mod | port |
|---|---|---|
| the game's identity (title, cover, Media link) | its own system | the **origin** system |
| what the build is | a ROM for that same system | a ROM for the **target** system |
| which library it is filed under | that system | the target |
| which cards can take it | that system's | the target's |

## Layout

```
nodes/local/<node>/homebrew/ports/<game>/<port>/
    build.sh        required, as every homebrew item
    .env.sample     required, with a filled .env beside it
    CATALOGUE       "<origin system> <game key>"   e.g. "pico sonic-the-hedgehog-s-gameworld"
    TARGET          "<system>"                     optional, e.g. "megadrive"
```

`<game>` groups ports of one game the way `mods/<game>/` groups mods, so a
second port of the same game (a Master System one, say) sits beside the first.

`CATALOGUE` keeps its current meaning and format. `TARGET` is new, and it is
what today's `CATALOGUE` second job (telling deploy which system the builds
are) splits off into.

`TARGET` is **optional**, because a port lives under the node whose hardware
runs its build, so that node already is the target. Write a `TARGET` only when
a port builds for something other than its own node. What a port never does is
take the origin game's system: that is the bug this kind exists to prevent.

## What changes in the API

**Discovery** (`pluto/api/modules/homebrew/service.py:437`) gains a fourth
kind beside `mods`, `games` and `tools`, grouped like `mods`:

```python
for game in _dirs(os.path.join(hb, "ports")):
    for port in _dirs(os.path.join(hb, "ports", game)):
        ...
        items.append(_item(repo_root, node, "ports", game, port, folder))
```

The `vanilla` and `*-decomp` skips apply here too: a port repo may well carry
a decomp beside the patcher.

**`_catalogue_game`** (`service.py:328`) is unchanged. It already returns
`{system, key, title}` read from `CATALOGUE`, and for a port that system is
the origin, which is exactly what the title and cover should come from.

**`lab_filename`** (`service.py:573`) is unchanged, and that is the point:
the game title still comes from `item["game"]["title"]`, so the build is
`Sonic The Hedgehog's Gameworld [Genesis Conversion by CPC].bin` with no
seeded entry anywhere.

**The item's `system`** (what everything already reads to decide where a build
is filed and sent) is computed one way for a port and the old way for
everything else:

```python
target = _target(folder)                       # the TARGET file, or None
if kind == "ports":
    system = target or node                    # never the origin game's system
else:
    system = target or (game or {}).get("system") or node
```

Mods, games and tools are unchanged, verified: every existing item still
reports the system it did before. The item also gains `origin`, the system a
port came from, which is `None` for every other kind.

**Deploy and send** (`pluto/api/modules/catalogue/send.py`) file the build
under the target system: the target's Lab library, the target's
`digital.json`, the target's cards. A port's build is never offered to the
origin system's cards, because it does not run there any more.

**Covers** needed nothing: `covers.from_other_system`
(`pluto/api/modules/catalogue/covers.py:181`, used by
`catalogue/service.py:184`) already serves art the catalogue holds for the same
game key under another system. A port's cover resolves from its origin by
itself.

## What changes in the UI

`HomebrewTab.vue` gains a fourth sub-tab, Ports, and the kind route accepts it.
A port's row ends with the conversion instead of its folder name, in the mono
data type:

```
Sonic The Hedgehog's Gameworld: Genesis Conversion    Unreleased    pico -> megadrive
```

Nothing else about the tab changes. The app header and tab row are untouched.

## Migration, done

1. `mods/sonic-gameworld/` moved to `ports/sonic-gameworld/`, submodule and all.
2. `CATALOGUE` back to `pico sonic-the-hedgehog-s-gameworld`, with
   `TARGET` holding `megadrive` (written explicitly, though the node would
   give the same answer).
3. The two things seeded by hand reverted: the empty
   `sonic-the-hedgehog-s-gameworld` entry in `catalogue/megadrive/digital.json`
   and the cover copied into `catalogue/megadrive/covers/`.

Discovery now reports it as: game `pico sonic-the-hedgehog-s-gameworld` (listed,
so cover and Media link work), system `megadrive`, origin `pico`, built as
`Sonic The Hedgehog's Gameworld [Genesis Conversion by CPC].bin`.

## Decisions

* **A port lives under the target node**, because the build is a Mega Drive ROM
  and that node owns the toolchain that makes it. It also means a Pico node is
  never required for a Pico port, which matters: there is no Pico node.
* **One target per port.** A patcher emitting a Mega Drive and a Master System
  build is two ports of one game, which the `<game>/` grouping already holds.
* **`ports/` takes a `RELEASE` file** like any other kind: a port ships a patch
  the way a mod ships a patch.
