# consolesplayingconsoles

> "Join me on a journey to connect every retro console I own into a single network and discover what happens when they finally meet."

---

In 1996, Sega built a Saturn with built-in networking. They called it Pluto. Only two units survived. It never shipped.

This project started while waiting for a Saturn to arrive from Japan. Reading about Pluto sent me down a rabbit hole. This is where I ended up.

consolesplayingconsoles is a distributed network connecting retro consoles from different manufacturers and generations, giving internet access to hardware that predates the web and enabling cross-console experiences that were never designed to exist. The dashboard is called Pluto. This time it will ship.

---

## Start here

| Folder             | What's inside                                                                                     |
|--------------------|---------------------------------------------------------------------------------------------------|
| [core/](./core/)   | Shared core: orchestration, cloud sync, UI layer, shared libs                                     |
| [wii/](./wii/)     | Wii node: input orchestration, controller translation, Maple bus bridge                           |
| [dc/](./dc/)       | Dreamcast node: Maple bus protocol, VMU tools, WiFi client                                        |
| [ps3/](./ps3/)     | PlayStation 3 node: input orchestration, controller translation                                   |
| [gba/](./gba/)     | Game Boy Advance: link cable tools, physical network remote                                       |
| [ws/](./ws/)       | WonderSwan: serial cable tools, RAM homebrew                                                      |
| [pluto/](./pluto/) | Network dashboard: node status, cloud sync client, distributed messaging, distributed deployments |

---

## Contributing

PRs welcome across all components.

Built something on top of this? Share it on Instagram [@consolesplayingconsoles](https://instagram.com/consolesplayingconsoles). Found a bug? Open an issue.

Do what you want with this. Credit the project and share what you find.

#peopleplayingconsolesplayingconsoles
