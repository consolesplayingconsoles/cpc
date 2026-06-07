# consolesplayingconsoles

> "Join me on a journey to connect every retro console I own into a single network and discover what happens when they finally meet."

---

In 1996, Sega built a Saturn with built-in networking. They called it Pluto. Only two units survived. It never shipped.

This project started while waiting for a Saturn to arrive from Japan. Reading about Pluto sent me down a rabbit hole. This is where I ended up.

consolesplayingconsoles is a distributed network connecting retro consoles from different manufacturers and generations, giving internet access to hardware that predates the web and enabling cross-console experiences that were never designed to exist. The dashboard is called Pluto. This time it will ship.

---

## Start here

Shared infrastructure:

| Folder             | What's inside                                                                                     |
|--------------------|---------------------------------------------------------------------------------------------------|
| [core/](./core/)   | Shared core: orchestration, cloud sync, UI layer, shared libs                                     |
| [pluto/](./pluto/) | Network dashboard: node status, cloud sync client, distributed messaging, distributed deployments |

Console nodes — auto-generated from each folder's `.env.sample`, do not edit by
hand (run `python3 scripts/gen_readme.py`):

<!-- CONSOLES:START -->
| Folder | Node | Manufacturer |
|--------|------|--------------|
| [batocera/](./batocera/) | Batocera | Linux |
| [dc/](./dc/) | Dreamcast | Sega |
| [dreame/](./dreame/) | L40 Ultra | Dreame |
| [gba/](./gba/) | Game Boy Advance | Nintendo |
| [ps3/](./ps3/) | PlayStation 3 | Sony |
| [wii/](./wii/) | Wii | Nintendo |
| [ws/](./ws/) | WonderSwan | Bandai |
<!-- CONSOLES:END -->

---

## Contributing

PRs welcome across all components.

Built something on top of this? Share it on Instagram [@consolesplayingconsoles](https://instagram.com/consolesplayingconsoles). Found a bug? Open an issue.

Do what you want with this. Credit the project and share what you find.

#peopleplayingconsolesplayingconsoles
