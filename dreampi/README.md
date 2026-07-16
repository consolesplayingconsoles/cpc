# DreamPi

Puts the Dreamcast online through its built-in 56K modem, with no dial-up ISP.
The daemon answers the DC's "call", runs PPP over the modem line, and bridges
the console onto your LAN. Once up, the DC is a real pinged node in Pluto
(`nodes/local/dc`, `HOST_IP=192.168.68.98`), reachable, FTP-writable (DreamShell),
and drivable headless from the dashboard through the Pico.

This directory is the **integration** only. The daemon itself is a fork:

- **Code:** [consolesplayingconsoles/dreampi](https://github.com/consolesplayingconsoles/dreampi),
  forked from [Kazade/dreampi](https://github.com/Kazade/dreampi) (GPL). Our
  patches port it to Python 3 and adapt it to a Pi 5 running Debian 13 (trixie).
- **This dir:** the `/etc` config, pinned `requirements.txt`, and `install.sh`
  that ties them together. Same split we use for the GP2040-CE fork.

There is no SD image: the official DreamPi image targets older Pis and will not
boot clean on a Pi 5, so we install the daemon by hand.

## Install

Run on the Pi:

```sh
./install.sh            # into /opt/dreampi
```

It clones the fork, builds a venv (PEP 668 forbids system-wide pip on trixie),
installs `ppp` + `dnsmasq`, drops the config into `/etc`, and enables the
service on boot. Power-on is then the only action: the daemon arms itself and
Pluto shows the DC green once it dials in.

## What the fork patches, and why

Two features, both generic and worth upstreaming:

**1. Run on a modern Pi.** The daemon is Python 2 and assumes an old userland;
neither survives on current Debian.

- **Py2 to Py3** in `config_server.py`, `dcnow.py`, `dreampi.py`. The `sha256`
  and `urllib2` fixes are real crashes, not cosmetics.
- **journald**: the daemon tailed `/var/log/messages` and `/var/log/syslog`,
  which do not exist on trixie (systemd journal, no rsyslog). Repointed to
  `journalctl`.
- **`nocrtscts`** in the pppd options. On a modern setup the modem is USB
  (`cdc_acm`), where RTS/CTS flow control garbles every received PPP byte and the
  link never negotiates. This was the hard one to find.

**2. Run on a non-dedicated device.** Stock DreamPi assumes it owns the box and
the modem is the only `cdc_acm` device, so it defaults to `/dev/ttyACM0` and
autodetects with `wvdialconf`. On a Pi that also runs other USB serial gadgets
both assumptions break: it would grab or poke the wrong device. So
`ENABLE_SPEED_DETECTION=False` and the modem is pinned to a stable
`/dev/dreampi-modem` by USB id (`0572:1340`, via the udev rule), leaving the
other devices alone.

## Hardware

- **Modem:** KALEA 56K USB fax modem (Conexant CX93001, USB `0572:1340`). The
  built-in `cdc_acm` driver binds it, no softmodem needed.
- **Line voltage inducer:** required. With no telephone exchange between the two
  modems there is no loop voltage, and the handshake will not complete without
  it. Ours is an ~18V build.
- **Plug the modem straight into a Pi USB port,** not a passive/switched hub.
  A flaky hub drops the modem off the bus and it will not re-enumerate behind it.

## Networking model

DreamPi uses **proxyarp, not NAT**. It assigns the DC a real LAN IP (Pi ppp end
`.99`, DC `.98`) and proxy-answers ARP for it, so the DC looks like a native LAN
host. The only firewall rule is a TTL fix. `dnsmasq` on `:53` forwards the DC's
DNS to the game-server DNS so revived servers resolve.

Keep `.98`/`.99` out of your router's DHCP pool (end the pool at `.97`) so the
DC's address stays stable and its Pluto node never points at a stray device.

## Gotchas that cost real time

- **Hub power switch:** if the modem "isn't detected", a switched USB hub port
  is the first suspect. Enumerate it direct on the Pi to isolate.
- **Voice-mode wedge:** the daemon holds the modem off-hook playing a dial tone.
  Sending plain AT commands to it in that state wedges it (it answers with a DLE
  byte and ignores AT). Un-wedge in software: write `\x10\x03` (end voice TX),
  then `+++` with guard time, then `ATH0`, then `ATZ0`. No unplug needed.
- **Do not add modem-side flow-control commands** (`AT&K0`) to the reset
  sequence: it wedged the dial-tone init here. `nocrtscts` on the pppd side is
  enough.

## Verify

```sh
journalctl -t dreampi -f          # <LISTENING> = armed and waiting for a call
ip -br addr show ppp0              # UP with 192.168.68.99 peer .98 = connected
ping 192.168.68.98                # the Dreamcast, on your LAN
```
