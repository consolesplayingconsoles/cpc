# consolesplayingconsoles

> "Join me on a journey to connect every retro console I own into a single network and discover what happens when they finally meet."

---

In 1996, Sega built a Saturn with built-in networking. They called it Pluto. Only two units survived. It never shipped.

This project started while waiting for a Saturn to arrive from Japan. Reading about Pluto sent me down a rabbit hole. This is where I ended up.

This time it will ship.

---

## A note on how this is built

I build this with heavy help from an AI assistant. It digs up tools and prior art, talks me through setup problems, writes a good deal of the code, and helps draft the write-ups. A single person taking on this many different consoles would not be realistic otherwise; the assistance is what makes the scale possible at all.

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

| Folder                                                             | What's inside                                                                                  |
|--------------------------------------------------------------------|------------------------------------------------------------------------------------------------|
| [pluto/](./pluto/)                                                 | CPC Pluto: the server, dashboard and control plane (runs as Lab or C2)                         |
| [pluto-translate/](./pluto-translate/) | Game text extraction/translation engine (parsers, patchers, font/PVR codecs); knowledge docs in `pluto-translate/docs/`   |
| [pluto-python-tui/](./pluto-python-tui/)                           | The on-console client/TUI that Pluto deploys to Linux nodes                                    |
| [pluto-pico-hub/](./pluto-pico-hub/)                                   | The Pico hub: native-protocol bridges for non-IP consoles, and the Pico firmware it flashes |

The [./nodes](./nodes) dir defines every node in the network. Any dir with a valid `.env` is picked up at startup. Devices on the LAN are checked live; cloud services are declared. Consoles too old to speak TCP/IP join through a Raspberry Pi that talks their native protocols on their behalf.

Two components live in their own repositories in this org: the **[GP2040-CE fork](https://github.com/consolesplayingconsoles/GP2040-CE)** (the Pico firmware, with our `UartInput` addon) and the standalone **[dreamehome-client](https://github.com/consolesplayingconsoles/dreamehome-client)** (the DreameHome cloud client).

### Getting Started

Start the **Lab**, Pluto's development instance, from the repo root:

```bash
cp pluto/.env.sample pluto/.env     # first time only, then edit the config
(cd pluto && yarn install)          # first time, or if dependencies change
./start-pluto-lab.sh                # API :7700 + Vite :5173 + Swagger :7800
```

Once it's up, you can deploy from the map. Set `HOST_IP` in the target node's `.env` (`pluto/.env` for the **Pluto C2** node, `nodes/local/pi/.env` for the **Pi** node), then hit the **Deploy** button on that node in the local Pluto Lab's network diagram.

---

## Requirements

Most of this is plain Python and a Node toolchain. A handful of features need an external account or a system package, and a couple of dev-only features pull extra libraries. The console nodes themselves stay deliberately light (pure stdlib plus `pyfiglet`), so the heavier dependencies live on the dev or capture host, never on the constrained hardware.

| Part                                        | Software                                                                                                                     | Hardware                              | Firmware                                                                                                                                                      |
|---------------------------------------------|------------------------------------------------------------------------------------------------------------------------------|---------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Pluto** (Lab or C2)                       | Node 20+ and Yarn (dashboard), Python 3 (API)                                                                                | a host (always-on for C2)             |                                                                                                                                                               |
| **On-console client** (TUI)                 | Python 3.6+ and `pyfiglet`, pure stdlib otherwise                                                                            | the Linux console node                |                                                                                                                                                               |
| **Pi hub + Pico drive**                     | Python 3 (stdlib) on the Pi                                                                                                  | a Raspberry Pi and Pico(s), wired     | the [GP2040-CE fork](https://github.com/consolesplayingconsoles/GP2040-CE) on the Pico (our `UartInput` addon), built with CMake, the Pico SDK and `picotool` |
| **Claude capture** (the "eyes", _Lab only_) | `ffmpeg`, `opencv-python`, `numpy`, `tesseract`                                                                              | Pluto Lab host + an HDMI capture card |                                                                                                                                                               |
| **Drive a local emulator** (_Lab only_)     | Python 3 and `pynput` (`requirements-dev.txt`)                                                                               | Pluto Lab host (Accessibility)        |                                                                                                                                                               |
| **DreameHome (vacuum) input**               | the bundled [`dreamehome` client](https://github.com/consolesplayingconsoles/dreamehome-client) (needs a DreameHome account) |                                       |                                                                                                                                                               |
| **Cloud storage**                           | provider-agnostic (needs a storage-provider account)                                                                         |                                       |                                                                                                                                                               |
| **VMU node**                                |                                                                                                                              | USB VMU reader                        | [DreamPicoPort](https://github.com/OrangeFox86/DreamPicoPort) on a Raspberry Pi Pico                                                                         |

> **Lab vs C2:** capture and the local-emulator drive are **Lab-only**:
> Capture needs the dev/capture host, with the LLM client co-located for speed.
> Local-emulator doesn't normally run on a headless server and the virtual keyboard has not been tested on Linux.
> Everything else runs on Pluto C2 too, including the DreameHome connector and driving the real console through the Pi/Pico.

The Python dev and capture libraries are externally managed (PEP 668), so install them into a venv:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

`ffmpeg` and `tesseract` are system packages, not pip: `brew install ffmpeg tesseract` (or your platform's equivalent).

---

## Acknowledgements

This is built on a lot of other people's work. A few that earned a specific mention:

- **[GP2040-CE](https://github.com/OpenStickCommunity/GP2040-CE)**: the multi-platform gamepad firmware that lets a Raspberry Pi Pico *be* a real controller. It's what finally drove a Dreamcast over a single wire here, presenting as a DualShock the Maple adapter trusts. A genuinely lovely piece of open firmware.
- **[Wii-Linux](https://github.com/Wii-Linux)**: a full Linux kept alive on the Wii's PowerPC (the active [`wii-linux-ngx`](https://github.com/Wii-Linux/wii-linux-ngx) revival), the long unglamorous work that turns a dead console into a real network node.
- **[Nintendont](https://github.com/FIX94/Nintendont)** and the wider **Wii homebrew & hardware scene** ([WiiBrew](https://wiibrew.org), the Homebrew Channel, and everyone who cracked this hardware open long before me).
- **[libretro/retroarch-assets](https://github.com/libretro/retroarch-assets)**: the console icons on the network map (CC BY 4.0; see `pluto/src/assets/avatars/NOTICES`).
- **[DreamPicoPort](https://github.com/OrangeFox86/DreamPicoPort)**: the Raspberry Pi Pico firmware that exposes a Dreamcast controller port (and VMU) over USB, presenting the VMU as a standard FAT16 mass storage device. The VMU node is built on top of it.
- **[FUSE-VMU](https://github.com/RossMeikleham/FUSE-VMU)**: FUSE filesystem implementation for the Dreamcast VMU — the reference for the VMU block format and filesystem layout.
- **Dreamcast ROM tooling**: Extraction and patching workflows built on [AFSPacker](https://github.com/MaikelChan/AFSPacker), [QuickBMS](https://aluigi.altervista.org/quickbms.html), [gditools](https://github.com/einsteinx2/gditools), [UniversalDreamcastPatcher](https://github.com/DerekPascarella/UniversalDreamcastPatcher), and [sega2asm](https://github.com/hansbonini/sega2asm).
- **[libfreenect](https://github.com/OpenKinect/libfreenect)**: open-source driver for Xbox Kinect v1 (depth, RGB, audio, skeletal tracking).
- **[MoveNet](https://github.com/tensorflow/tfjs-models/blob/master/pose-detection/src/movenet/README.md)** (Google): the SinglePose Lightning body-pose model behind the Kinect gesture controller — 17 keypoints, real-time on the Pi 5's CPU. Run from the ONNX export by **[Xenova](https://huggingface.co/Xenova/movenet-singlepose-lightning)**.
- **[ONNX Runtime](https://github.com/microsoft/onnxruntime)** (Microsoft): runs MoveNet on the Pi's aarch64 CPU — the piece that made on-device pose work where MediaPipe ships no ARM wheels.

Built on these, not instead of them.

---

## Contributing

PRs welcome across all components.

Built something on top of this? Share it on Instagram [@consolesplayingconsoles](https://instagram.com/consolesplayingconsoles). Found a bug? Open an issue.

Do what you want with this, and pass it on the same way. Credit the project and share what you find.

## License

© 2026 consolesplayingconsoles. Free software under the **GNU General Public License v3.0 or later** ([GPL-3.0-or-later](LICENSE)): use it, study it, share it, modify it. Derivative works stay under the same licence, so what gets built on this stays open too. The project is copyleft partly because it leans on GPL-3.0 tooling such as [GDIBuilder](https://github.com/Sappharad/GDIbuilder).

#peopleplayingconsolesplayingconsoles
