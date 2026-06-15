# consolesplayingconsoles

> "Join me on a journey to connect every retro console I own into a single network and discover what happens when they finally meet."

---

In 1996, Sega built a Saturn with built-in networking. They called it Pluto. Only two units survived. It never shipped.

This project started while waiting for a Saturn to arrive from Japan. Reading about Pluto sent me down a rabbit hole. This is where I ended up.

consolesplayingconsoles is an asymmetric private cloud project connecting retro consoles from different manufacturers and generations, giving internet access to hardware that predates the web and enabling cross-console experiences that were never designed to exist. The dashboard is called Pluto. This time it will ship.

---

## Start here

Shared infrastructure:

| Folder                                     | What's inside                                                                                           |
|--------------------------------------------|---------------------------------------------------------------------------------------------------------|
| [cpc-python-client/](./cpc-python-client/) | Python console client: the shared `cpc_python_core` package (UI, env, chat), entrypoints, vendored deps |
| [pluto/](./pluto/)                         | The C2 heart of CPC                                                                                     |

The [./nodes](./nodes) dir contains the definition of each potential node in the network. Any new dir with a valid .env file will be picked at startup.

---

## Contributing

PRs welcome across all components.

Built something on top of this? Share it on Instagram [@consolesplayingconsoles](https://instagram.com/consolesplayingconsoles). Found a bug? Open an issue.

Do what you want with this. Credit the project and share what you find.

#peopleplayingconsolesplayingconsoles
