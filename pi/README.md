# pi — Dreame clean → console

A captured Dreame clean drives a console character: the robot's route becomes the
character's movement. Pipeline (all in `cpc_python_core`, the node just launches it):

```
routes.json → events_from_route → mapping (dreame-to-gamecube) → Sink → console
```

The `KeyboardSink` is the **local dev transport**: it holds real keyboard keys, so
any emulator whose controls are mapped to the keyboard works. (The named-pipe path
is a dead end on macOS — see the project notes.) Real hardware later is just a
different `Sink` (Pico HID), engine + mapping unchanged.

## Requirements (macOS dev)
- **`pynput`** under the *same* interpreter you launch with. `pip3` here is py3.11
  while `python3` is 3.14, so install/run with the matching one:
  `python3.11 -m pip install pynput` and launch with `python3.11`.
- **Accessibility permission** for your terminal (System Settings → Privacy &
  Security → Accessibility → add Terminal/iTerm). Without it macOS silently drops
  synthesized keys.
- An emulator (e.g. **Dolphin**) running, with a save state at a safe open spot.

## Dolphin setup (one time) — 1:1 keyboard map
Controllers → GameCube Port 1 = **Standard Controller** → **Configure**:
- **Device**: `Quartz/0/Keyboard & Mouse`
- **Control Stick**: Up/Down/Left/Right → **Arrow keys**
- **Buttons (1:1, nothing to remember)**: A→`A`, B→`B`, X→`X`, Y→`Y`, Z→`Z`,
  Start→`Return`, L→`L`, R→`R`
- **C-Stick** → `1` `2` `3` `4` and **D-Pad** → `5` `6` `7` `8` (Up/Down/Left/Right
  order). C-stick is doc-only for now (no mapping emits it); D-pad keys are wired.
- Tick **Background Input** — confirmed working: keys reach Dolphin even when it's
  not the focused window, so the replay runs in the background while you do other
  things. (Focusing it still works too; the launcher's countdown is just a courtesy.)

The mapping is currently **move-only**, so only the Control Stick (arrows) is
exercised today; the 1:1 buttons are wired for when the mapping starts pressing
them (`state`/`pet` reactions). It doesn't need to be "playable" — 1:1 is just the
simplest thing to set up and document.

## Save state (so it doesn't fall)
The route is bounded to the house footprint (~tens of m²) around the origin, so the
character only ever wanders a small area and never past the start point. Park them
somewhere they can't fall (e.g. mid-bridge / open field), then save a Dolphin state.
Save states are tied to the exact Dolphin build — remake after a Dolphin update.

## Run it
```
python3.11 /Users/francesc.montserrat/workspace/cpc/pi/dreame_to_console.py \
  /Users/francesc.montserrat/workspace/dreamehome-client/routes.json \
  --sink keyboard --keys arrows --speed 3
```
- 4-second countdown → **click the emulator window** so it has focus.
- `--speed` scales playback (1 = real time; bump for a quick look). `--session <id>`
  picks a specific clean (default: most recent with a route). Ctrl-C stops + releases.

## Sanity-check without an emulator
```
python3 pi/dreame_to_console.py <routes.json> --sink print --speed 200000
```
Prints the controller ops (`SET MAIN x y`, etc.) instead of pressing keys.
