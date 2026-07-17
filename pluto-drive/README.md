# pluto-drive

The CPC **drive API**, extracted from Pluto so it can run as its own service on
each node. Same `POST /control/drive` contract Pluto served in-process; the point
of pulling it out is **distribution**: every node runs its own drive instance, so
the hot path (input → mapping → sink → hardware) stays *local* to whichever node
owns the output, and only config crosses the network.

## Contract

`POST /control/drive` with a JSON body, `{action, target, source, mapping, ...}`:

| action | what |
|---|---|
| `hold` | live press/release (`down`, `btn`\|`key`) — held sink, watchdog |
| `press` | one-off pulse (via the live sink if running, else transient) |
| `axis` | live analog stick (`name`, `x`, `y`) |
| `keepalive` | heartbeat; keeps the held sink alive between keystrokes |
| `pause` / `stop` | release the drive |
| `play` | paced replay of a dreame route (`session`, `t`, `speed`) |

Returns `(200, {ok, ...})` or `(200, {ok:false, error})`; never 500 on a drive
failure, so a client can surface it.

## Where the sink comes from

The **mapping** decides the buttons; the engine only steers ops to a sink resolved
per node from the roster:

- `keyboard` → `KeyboardSink` (local emulator via pynput; Mac-lab only)
- `pi` → `NetworkSink` to that node's hub op receiver (`HOST_IP:PI_BRIDGE_PORT`)
- `roomba` → `RoombaSink` to the roomba node's command stream

Because `HOST_IP` comes from the roster, the **same target drives different local
hardware depending on where the engine runs** — on the Pi, `pi` resolves to the
Pi's own hub (local); on the Lab, `keyboard` drives the local emulator.

## Files

- `engine.py` — `DriveEngine`: the state machine + sink selection + dispatch (pure,
  reusable; Pluto imports this too).
- `controller.py` / `dreame_events.py` — the translate + sinks + replay adapter
  (copied from `pluto/api/drive/`; the shared source once Pluto migrates onto this).
- `server.py` — the standalone HTTP wrapper + node-roster loader.
- `run.sh` / `deploy/cpc-drive.service` — entrypoint + systemd unit (payload: `drive`).

## Run

```sh
CPC_MAPPINGS=…/pluto/config/mappings CPC_NODES_DIR=…/nodes DRIVE_PORT=7702 ./run.sh
```
