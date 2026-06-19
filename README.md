# consolesplayingconsoles

> "Join me on a journey to connect every retro console I own into a single network and discover what happens when they finally meet."

---

In 1996, Sega built a Saturn with built-in networking. They called it Pluto. Only two units survived. It never shipped.

This project started while waiting for a Saturn to arrive from Japan. Reading about Pluto sent me down a rabbit hole. This is where I ended up.

This time it will ship.

---

## CPC Pluto

The management console for an asymmetric private network of retro consoles. It brings internet access to hardware that predates the web, and enables cross-console experiences that were never designed to exist.

- **Live network map**: a real-time diagram of the whole network, with every node shown present, up, down, or not yet configured at a glance.
- **Self-deploying**: from the dashboard, Pluto installs itself in any of its distributed variants, along with each node's client (Python or native), showing live progress.
- **Serves legacy browsers**: a pared-down "retro" web page, served from the API, that even primitive console browsers can render.
- **Command-and-control over chat**: one group chat where every node is a participant. Mention a node to act on it.
- **Everything is a node**: consoles, handhelds, cloud storage, an LLM, even a robot vacuum. LAN devices (with or without IP) and cloud services live on one map.
- **Bridges hardware that never spoke IP**: it translates the native protocols of pre-internet consoles so they can join the network at all.

### How it runs

Pluto is a single app you run one of two ways:

- **Lab**: the full development environment, where Pluto is built and where you develop it and everything it deploys.
- **C2** *(optional)*: a stripped-down, single-purpose, stable build of the same app, for when you have an always-on server to host it.

---

## Start here

| Folder                                   | What's inside                                                                                  |
|------------------------------------------|------------------------------------------------------------------------------------------------|
| [pluto/](./pluto/)                       | CPC Pluto: the server, dashboard and control plane (runs as Lab or C2)                         |
| [pluto-python-tui/](./pluto-python-tui/) | The native client/TUI that Pluto deploys to Linux nodes                                        |
| [pluto-pi-hub/](./pluto-pi-hub/)         | The Pi-side hub: native-protocol bridges for non-IP consoles, and the Pico firmware it flashes |

The [./nodes](./nodes) dir defines every node in the network. Any dir with a valid `.env` is picked up at startup. Devices on the LAN are checked live; cloud services are declared. Consoles too old to speak TCP/IP join through a Raspberry Pi that talks their native protocols on their behalf.

### Getting Started

Start the **Lab**, Pluto's development instance, from the repo root:

```bash
cp pluto/.env.sample pluto/.env     # first time only, then edit the config
(cd pluto && yarn install)          # first time, or if dependencies change
./start-pluto-lab.sh                # API :7700 + Vite :5173 + Swagger :7800
```

Once it's up, you can deploy from the map. Set `HOST_IP` in the target node's `.env` (`pluto/.env` for the **Pluto C2** node, `nodes/local/pi/.env` for the **Pi** node), then hit the **Deploy** button on that node in the local Pluto Lab's network diagram.

---

## Acknowledgements

This is built on a lot of other people's work. A few that earned a specific mention:

- **[GP2040-CE](https://github.com/OpenStickCommunity/GP2040-CE)**: the multi-platform gamepad firmware that lets a Raspberry Pi Pico *be* a real controller. It's what finally drove a Dreamcast over a single wire here, presenting as a DualShock the Maple adapter trusts. A genuinely lovely piece of open firmware.
- **[Wii-Linux](https://github.com/Wii-Linux)**: a full Linux kept alive on the Wii's PowerPC (the active [`wii-linux-ngx`](https://github.com/Wii-Linux/wii-linux-ngx) revival), the long unglamorous work that turns a dead console into a real network node.
- **[Nintendont](https://github.com/FIX94/Nintendont)** and the wider **Wii homebrew & hardware scene** ([WiiBrew](https://wiibrew.org), the Homebrew Channel, and everyone who cracked this hardware open long before me).
- **[libretro/retroarch-assets](https://github.com/libretro/retroarch-assets)**: the console icons on the network map (CC BY 4.0; see `pluto/src/assets/avatars/NOTICES`).

Built on these, not instead of them.

---

## Contributing

PRs welcome across all components.

Built something on top of this? Share it on Instagram [@consolesplayingconsoles](https://instagram.com/consolesplayingconsoles). Found a bug? Open an issue.

Do what you want with this. Credit the project and share what you find.

#peopleplayingconsolesplayingconsoles
