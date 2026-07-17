# Nokia phone controller node

A Nokia 6103 (Series 40, 2006) turned into a Bluetooth game controller. A J2ME
MIDlet on the phone captures the keypad and streams key events over Bluetooth to
the Pi, which maps them to buttons and drives a console through the Pico. It shows
up in Pluto Control as the **Nokia Phone** input source.

## How it flows

```
phone keypad -> CpcPad MIDlet -> Bluetooth rfcomm -> Pi (bridges/nokia.py)
             -> map key->button -> local Pico HidBridge -> Maple -> console
```

Pluto only pushes the mapping and start/stop; keypresses never leave the Pi, so
input stays low latency. The bridge lives in the hub (`pluto-pico-hub/bridges/nokia.py`,
wired into `hub.py serve()`), so it runs under `cpc-hub.service` like the others.

> Bluetooth is handled on the **Pi**, not a Mac: macOS refuses to reach a MIDlet's
> custom rfcomm service (TCC aborts IOBluetooth; the serial port won't link an
> SDP-invisible channel). Linux `bluez` does it in a few lines.

## Parts

- `midlet/` — the phone app (`src/CpcPad.java`) + the J2ME build toolchain (Docker).
- `bridge` — lives in `pluto-pico-hub/bridges/nokia.py` (Pi runtime, with the other bridges).
- mapping — `pluto/config/mappings/nokia/dreamcast.json` (phone key -> DC button).
- Control panel — `pluto/src/components/control/NokiaControl.vue`.

## Build the MIDlet

The 6103 needs MIDP 2.0 / CLDC 1.1, too old for a modern JDK. Build in the Docker
toolchain (colima on an Intel Mac):

```sh
cd midlet
docker build -t cpc-j2me .
# colima only mounts $HOME, so copy the sources in rather than bind-mount:
cid=$(docker create cpc-j2me sh -c "cd /work && sh build.sh")
docker cp ./. "$cid":/work
docker start -a "$cid"
docker cp "$cid":/work/CpcPad.jar ./
docker rm "$cid"
```

Bump the version in `MANIFEST.MF` (`MIDlet-1` name + `MIDlet-Version`) each release
so installs are distinguishable on the phone (S40 lists same-named apps out of order).

## Install on the phone

Push the JAR over Bluetooth (OBEX), then install it from the phone's Inbox:

```sh
open -a "Bluetooth File Exchange" CpcPad.jar   # pick the phone, accept on the phone
```

## Pair the phone to the Pi (one time)

The phone must be **near the Pi** (classic Bluetooth is ~10 m). On the Pi:

```sh
bluetoothctl        # power on; agent KeyboardDisplay; default-agent; pairable on
scan on             # wait for the phone (needs "Shown to all" on the phone)
pair <PHONE_MAC>    # accept on the phone; PIN 0000 on both sides
trust <PHONE_MAC>
```

Put `NOKIA_ADDR` (the phone MAC), `NOKIA_CHANNEL` (the `ch=` shown on the CPC Pad
screen), and `NOKIA_ENGINE_PORT=7740` in `nodes/local/pi/.env`, then deploy:
`./deploy.sh nodes/local/pi/.env`.

## Use

Launch **CPC Pad** on the phone. In Pluto: **Control -> source Nokia Phone ->
target Console (Raspberry Pi) -> the dreamcast Pico -> Connect**. Accept the
connection prompt on the phone, then play. Mapping: `2/4/6/8` d-pad, `1/3/7/9` =
X/Y/A/B, `5` = Start, the two soft keys = L/R (volume keys are captured by the
phone and can't be used).
