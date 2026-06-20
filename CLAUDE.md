# System Architecture & Operational Rules

### 1. Control Plane & Monitoring
The network is monitored and administered from **Pluto**, a web dashboard that channels a highly functional, dense, and hyper-reliable router console aesthetic — optimized for pure engineering utility rather than flashy corporate web design.

### 2. Unified Environment Configuration (.env)
Environment configuration files live inside each node's own directory under `nodes/`, split into two kinds: pinged LAN nodes under `nodes/local/` (e.g. `nodes/local/wii/.env`, `nodes/local/wii/dev.env`) and off-network connectors under `nodes/cloud/` (e.g. `nodes/cloud/dropbox/`, `nodes/cloud/claude/`); `pluto/` is the dashboard app and also the host node (its own `pluto/.env`). They are the single source of truth for branding, networking, and security credentials across both the web and terminal interfaces. The API discovers the node roster from `nodes/local/*/` and `nodes/cloud/*/` at startup — every dir is a node, **keyed by its dir name** (the display name lives in the node's `.env` as `NODE_NAME`). Local nodes are pinged (up / down / unconfigured); cloud nodes carry the `cloud` status — never pinged, always shown (the dir IS the declaration). Never create a flat `console/` dir for env files — each node owns its own under `nodes/`.

* **Sandboxing**: Variables must remain strictly sandboxed to their specific deployment runtime contexts.
* **Unified Template (`.env.sample`)**: Each console directory includes a `.env.sample` template file containing zero real data. This file is the strict structural blueprint. Never commit `*.env` files — only `*.env.sample`.
* **Strict Validation (Fail Fast)**: At boot time, the system validates all required environment parameters. If a required field is missing or empty, the application must immediately terminate execution and output a clean, highly scannable terminal error detailing exactly what is missing. It will never proceed with silent fallback values.
* **Shared Network & Access Variables**:
  * `NODE_NAME`: The unique host identity string used as the header/title across all user interfaces (e.g., `Pluto - Dev Node`).
  * `HOST_IP`: The dedicated IP address of the console environment.
  * `SSH_USER`: The administrative username for console access.
  * `SSH_KEY_PATH`: Path to the local private key file.
* **Shared UI Branding Variables**:
  * `UI_PRIMARY_COLOR`: Controls the dominant UI accent (e.g., active cursor in terminal, main accent lines in Pluto).
  * `UI_SECONDARY_COLOR`: Controls background accents, borders, and metadata states.

### 3. External File Systems
Data synchronization relies on a **commercial cloud storage provider**, abstracting the external file system from the core application. The provider is modeled as an **operator-named node** under `nodes/cloud/` — name the dir after whatever storage you actually use (this instance: `dropbox`; another operator might use `nextcloud`, `gdrive`, …); the dir name is the node key and its chat `@handle`. Keep the integration code provider-agnostic (no SDK lock-in) — only the node's identity is yours to name.

### 4. Repository Tidy Rules & Dynamic Scaffolding
To prevent platform collisions, all assets, firmware, and executables are encapsulated into console-specific root application directories. 

* **On-Demand Initialization**: The development pipeline monitors `nodes/` for empty directories matching the designated console codenames listed in the parent README. When a matched empty directory is created, the system initializes it with the single in-repo storage convention below:
  * **`/share`**: Shared media, document templates, and static external resources that are architecture-independent (aligns with the Linux `/usr/share` convention) — a clean storage dir.

  ROMs and binaries are **not** committed to the repo. Game/ROM files are referenced live over SMB and the per-console `*_GAMES_PATH` env vars, so a `/roms` dir is obsolete. Native console code (e.g. Wii homebrew) lives in the console's own `homebrew/` directory and builds to a bootable artifact, so a `/bin` dir is obsolete too.

### 5. Python Compatibility & Dependency Rules

Console nodes run constrained hardware (PowerPC, ARM, MIPS) with Python built from source. Every Python feature and dependency choice must be **validated against the minimum target before use**.

* **Minimum Python version: 3.6** — f-strings and basic type annotations are fine. Nothing from 3.7+ unless explicitly noted as safe (e.g. `importlib.resources` is 3.7+ and is **banned**).
* **No C extension dependencies** — packages that compile native code (e.g. `evdev`, `cryptography`, `lxml`) will fail to build on exotic architectures. Use pure-Python alternatives or implement the feature directly using stdlib.
* **No modern setuptools/pip assumptions** — pip on these nodes is old (18.x). Dependencies must install cleanly without requiring `setuptools>=61` or PEP 517 build backends. When in doubt, test with pip 18.
* **Prefer stdlib over third-party** — if something can be done with `struct`, `os`, `select`, `termios`, `subprocess`, or `socket`, do it that way. External packages must justify their presence.
* **Raw hardware access over libraries** — for input devices, serial ports, audio, etc., read/write device files directly using `struct` and `os.read/write` rather than pulling in a library wrapper.
* **Conservative pyfiglet version** — locked to `0.8.post1`, the last release before `importlib.resources` was introduced. Do not upgrade without verifying 3.6 compatibility.
* **ASCII-safe output** — console terminals may be ASCII-only (no UTF-8 locale). Never use Unicode box-drawing characters, emoji, or non-ASCII symbols in terminal output. Plain `-`, `|`, `+` only.

### 6. Interface Design Guidelines

#### 5.1 Pluto Web Dashboard (Remote Monitoring)
Pluto is a web-based management dashboard. 
* **Web Stack**: Built using **TypeScript** and **Vue.js**, adhering to a safe, highly conservative linting configuration to guarantee rock-solid runtime stability.
* **Aesthetic**: A modern, premium **functional admin tool** — think **Stripe or Wise**: a calm neutral canvas, *one* confident accent used intentionally (not on every border), a clear typographic hierarchy (a clean UI **sans** for labels/headings/body; **monospace reserved for data** — IDs, metrics, code, coordinates, technical labels), purposeful whitespace, soft elevation, quiet borders. Dense where data comprehension genuinely benefits, breathable everywhere else. Premium because it is *clear*, not because it is decorated. Explicitly **not** consumer e-commerce/media — no carousels, hero imagery, sliding pictures, or merchandising (not Spotify/Amazon) — and no longer the old dense gray router-console look (monospace-everything, hierarchy carried only by borders, no air). Borders, radius, shadows, and colour coding are welcome when they carry information or structure; they become noise as pure decoration.
* **Function-first modernism**: When a modern pattern genuinely improves usability or data comprehension — colour-coded status, KPI cards, the interactive map, skeleton/loading states, progressive disclosure — prefer it. The goal is *useful beauty*, not retro for its own sake, and not decoration for its own sake either. Clarity beats conformity. The target user is an operator who knows the tool, not a first-time visitor being sold on it.
* **Design tokens**: Colour, type, spacing, radius, and elevation live as CSS custom properties in `pluto/src/style.css` (`:root`). Build from the tokens; do not scatter ad-hoc hex/px. The accent derives from `UI_PRIMARY_COLOR`; neutrals are a calm grey scale, not flat mid-grey. The **network diagram is the engineered centrepiece and stays as-is** (it earns its density and may keep monospace technical labels); the **chat and vacuum surfaces** carry the modern admin treatment.
* **Node Icons (avatars)**: Node avatars live in `pluto/src/assets/avatars/`, with attribution in that dir's `NOTICES`. Console icons come from `libretro/retroarch-assets` xmb/systematic/png (CC BY 4.0); originals (`gateway.svg`, `pi.svg`, `cloud.svg`, `cloud-storage.svg`, `substack.svg`) and identification-use marks (`dreame.png`, `claude.svg`) are noted there too. Do not fetch additional icons without updating NOTICES.
* **Flagship Feature (Dynamic Network Diagram)**: The core of the interface is an interactive, real-time topological diagram mapping the network structure, live connection data, and device availability directly onto a visual map.
* **Dynamic Node Discovery Model**: The system relies on zero static configuration JSON files. Pluto dynamically renders the map by compiling defined `.env` targets and executing live runtime ICMP checks:
  * **Not Present**: If a device IP or configuration parameter is missing from the environment file, the system flags the entity as not present and dynamically strips it from the map viewport entirely.
  * **System Up**: If the environment variable exists and a live runtime network ping to the target IP succeeds, the system marks the node active, drawing the active connection arrows and loading its custom console asset icon.
  * **System Down**: If the environment variable exists but a live network ping fails to resolve, the node remains on the grid but falls back into a visual offline/down state.
* **UI/UX Balance (Premium Simplicity)**: The diagram balances high utility with a sharp, premium finish. It features crisp custom console icons, clean directional connection vectors, and a clear grid layout. It behaves like Mac utility software—stripping away visual clutter and heavy animations, while using beautiful asset design, deliberate typography, and absolute pixel-precision to look incredibly cool and professional.
* **Environment Branding**: Reads `NODE_NAME`, `UI_PRIMARY_COLOR`, and `UI_SECONDARY_COLOR` from the environment `.env` to brand and skin the web page dynamically.

#### 5.2 Python Console Interface (Local Administration)
The Python application features a terminal-based administrative interface for direct host interaction.
* **Navigation**: Uses an ASCII-rendered, keyboard and hardware D-pad navigable menu system.
* **Environment Branding**: Dynamically skins its ANSI terminal borders and title bars using the exact same `NODE_NAME` and `UI_PRIMARY_COLOR` properties utilized by Pluto.
* **Input Model**: Displays interactive text input fields dynamically at the exact time and place user configuration is required.
* **Config Printing**: Capable of reading and printing raw configuration files (such as controller mappings) directly into the terminal window for instant inspection.
* **Title format**: ASCII header always renders as `CPC MANUFACTURER CONSOLENAME` using pyfiglet. CPC + manufacturer on one line (secondary color), console name large below (primary color).
* **Dependencies**: managed via `pluto-python-tui/requirements.txt`, vendored into `pluto-python-tui/vendor/`, deployed via `deploy.sh nodes/local/<console>/.env`.

### 7. Cross-Platform Topology & Dynamic Availability
The core Python interface executes natively on a **master** Linux console. However, its management scope extends beyond the host machine to coordinate specialized **client** devices directly from the master interface.

#### 6.1 Input & Controller Navigation
* **Dual Control Schemes**: The interface is fully navigable using both standard keyboard inputs and physical hardware controller D-pads.

#### 6.2 Master/Client Relationship & Dynamic UI Visibility
* **Master/Client Architecture**: The Linux machine acts as the central master console, driving administrative actions for connected client hardware.
* **Context-Aware Menu Visibility**: Client-specific submenus and management features are completely dynamic. Mirroring Pluto's discovery logic, they only become visible and usable within the UI if the master console actively detects that the client configuration exists and the live device responds to network pinging. Disabled, missing, or disconnected clients are automatically stripped from the active menu options to keep the terminal view clean.

### 8. Application Layer & Byproduct Services (Webapps & Servers)
Beyond the administrative control plane, the platform hosts an ecosystem of localized web applications, custom test pages, and Proof of Concept (POC) servers. These byproducts (e.g., experimental servers, diagnostic test views, or localized online/LAN game rooms for any given title) represent the creative and functional outputs of the system rather than the core infrastructure tools themselves.

#### 7.1 Web Stack & Coding Standards
* **Core Technologies**: Built using **TypeScript** and **Vue.js**, utilizing the same safe, conservative linting profile used by Pluto.

#### 7.2 Console Browser Optimization & Real-Time Fallbacks
Pluto itself is never loaded on a console browser. However, consumer-facing byproduct applications, test views, and game lobbies are optimized to scale down cleanly for embedded or legacy console web engines:
* **Legacy Transpilation Target**: The build pipeline compiles these specific webapps down to a backward-compatible JavaScript baseline (e.g., ES5/ES6) to avoid execution errors on primitive console browsers.
* **Graceful Degradation ("Strip Rather Than Break")**: If a console browser breaks on modern CSS layout rules or advanced properties, the system strips those layers entirely, gracefully dropping back to a functional, unstyled text-and-grid layout.
* **Real-Time Fallback Workflow**: Because console rendering behaviors must be verified interactively in real-time, the architecture permits writing explicit, lightweight fallback templates or alternative stylesheets. If real-time physical device testing reveals visual or structural breakage, the engine will explicitly serve the simplified fallback view to that legacy target.

### 9. Local Development & Interface Testing
To keep production application logic perfectly clean and free of testing conditionals, the platform utilizes separate execution scripts for live deployments versus local development environments.

* **Production Entrypoint (`pluto-python-tui/main.py`)**: Runs the strict live logic. It parses the namespace-targeted `.env` file, evaluates real host infrastructure, executes live pings, and dynamically hides/strips UI menus based on physical hardware availability.
* **Development Entrypoint (`pluto-python-tui/dev.py`)**: A dedicated wrapper script used solely for local interface testing (the python equivalent to running `yarn dev`). It completely bypasses the live infrastructure pipeline and force-feeds a complete layout matrix directly into the UI engine. This ensures all menus and text inputs remain visible and editable locally without requiring a production host context or physical devices attached.

### 10. Device Access Discipline
Connecting to a physical console or device (e.g. `ssh wii ...`) is an explicit, per-command action — **never** a standing grant. See [`SECURITY.md`](./SECURITY.md) for the full policy.

* **Per-command authorization**: Before each connection to a device — including read-only ones — state the exact command and its purpose and obtain approval. Approval of a task does not roll forward into later connections.
* **Capability is not consent**: Passwordless key auth makes a connection possible, not permitted. The operator draws that line, per request.
* **Least privilege & transparency**: Default to read-only; call out and confirm anything that writes to a device; never access a device silently or in the background.
* **Credentials**: One dedicated SSH key per host (never a shared key file). Private keys and real `*.env` files are never committed — only `*.env.sample`.
