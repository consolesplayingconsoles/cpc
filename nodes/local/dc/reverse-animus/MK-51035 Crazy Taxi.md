# Crazy Taxi (Dreamcast), sandbox mod

MK-51035 (Europe, V1.000). Hitmaker / Sega, 2000. Drive the cab, or, in the sandbox mod
(`nodes/local/dc/homebrew/mods/crazy-taxi/sandbox`), step out and walk, run, jump, hail and take
over traffic cars. This file covers playing the sandbox build for testing.

Operating doctrine (the loop, confidence tiers, the format of this file) lives in
[`REVERSE-ANIMUS.md`](../../../../REVERSE-ANIMUS.md). One difference from it: here the eyes and
limbs are not Pluto's capture and pad but RetroArch's network ports, through the sandbox's
`tools/ra.py` (memory reads by address, screenshots, network gamepad). So you read numbers first
and frames only when a number cannot settle it.

## Menu and boot
* **Launch**: `python3 tools/ra.py launch` (RetroArch in the background, Flycast core, the
  sandbox's own build). Check `ra.py status` first: RetroArch is shared with other sessions, and
  `ra.py` refuses to act on a game that is not the sandbox. Never quit, pause or write to another
  game.
* **To the city**: wait about 15 s (BIOS animation), then Start, Start (title), Down (Original),
  A, A (Play by Arcade Rules), A (first driver), then about 20 s of intro. If a Start lands in the
  attract demo, it only returns to the title: one more Start. Confirm you are in by reading the
  mod's car count (`_carCount` from `build/work/mod/mod.map`, non-zero) and `MainMode` = 1.
* **Arcade rules**: the timer is frozen by the mod; the run does not end.
* **Quit RetroArch**: send `QUIT` twice (the first asks to confirm). It rewrites its config on
  quit: edit `retroarch.cfg` only while it is closed.

## Controls
Network gamepad names are Dreamcast buttons (`ra.py press/hold/release/stick`).

| Move | Function | Dreamcast | Tier |
|------|----------|-----------|------|
| Accelerate | drive | R (hold) | Platform-confirmed |
| Gear | reverse / forward | A / B | operator |
| Step out | leave the cab beside its door | Y | Platform-confirmed |
| Get in | at the driver's door (cab's left side), within 10 on the ground | Y | Platform-confirmed |
| Take over | a traffic car (types 0-10) beside you | Y | Platform-confirmed |
| Walk | camera-relative | stick | Platform-confirmed |
| Run | while walking | R (hold) | Platform-confirmed |
| Jump | on foot, no animation | A | Platform-confirmed |
| Hail | hold about 1.5 s on foot | X | LIVE / TBD (never confirmed working) |

## Engine and game facts
* **Camera-relative walking**: the stick's up is away from the camera. To walk to a point, take
  the camera position (`0x0C179840`) and the walker's, and steer by their difference (the scratch
  helper `goto.py` does this; overshoot near the target, so scale the stick down close in).
* **Where things are**: player car at `0x0C1790CC` (`+0x78` position, `+0x86` yaw); walker
  position at `_ped + 4` (mod.map); the draw list of live cars at `0x0C2A44CC` with the mod's
  copy of its count `_carCount`; traffic `_car`: `+0x78` type, `+0x7C` colour, `+0x84` flags,
  `+0x8C` position, `+0xA6` yaw.
* **Traffic lives around the walker** (the mod moves the traffic centre to him); cars appear only
  at the edge of a 1100 radius as road sections enter it, never in the middle.
* **The city is hilly**: a car's height changing fast is usually a crest, not a fall. A real fall
  is a car below its own ground height (`_car + 0x104`).
* **Door side**: the door point is +15 along the car's x axis (side +1 in the helpers).

## Signature moves
* **Bail at speed**: hold R about 5 s, press Y, then A: the cab rolls on without you.
* **Hijack the nearest car**: pause, pick the nearest car of types 0-10 from the draw list,
  write the walker beside it (half-width + 6 along its x axis), unpause, press Y. Faster and more
  reliable than walking there.
* **Far test**: write the walker onto a course point 3000 from the traffic centre (course table
  `0x0C2A6690`, points 12 bytes each) to test what happens away from the car you left.
* **Frame stepping**: pause, then `FRAMEADVANCE`; input from the network gamepad does not reach
  the game while stepping, so step only to read state, not to move.

## Game structure
One city (Original course), Arcade rules. You start in the cab on the main street.

## Calibration / LIVE
* Hail (X): never seen to bring a taxi. TBD.
* Walking into set objects (crates): the step-out point ignores them. TBD.
* Dark spikes under taken cars: which model slot draws them. TBD.
* Probe timing: reads are UDP and can time out on a busy machine (the client retries); a
  multi-read probe spans frames, so pause around it when the values must agree.

## Sources
* `nodes/local/dc/homebrew/mods/crazy-taxi/crazy-taxi-decomp/docs/engine.md` (addresses, traffic,
  camera, player car).
* `nodes/local/dc/homebrew/mods/crazy-taxi/sandbox/src/mod.c` (the mod's controls).
* Live sessions, 2026-10-08 (RetroArch + Flycast).
