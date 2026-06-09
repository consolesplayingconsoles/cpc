# CPC Chat — native Wii homebrew

A chat client that runs on the bare Wii (Homebrew Channel), no OS underneath.
Built incrementally; see the step comments in `source/`.

## Prerequisites (build host)
```sh
sudo dkp-pacman -S wii-dev        # devkitPPC, libogc, wiiload, etc.
```
Make sure `$DEVKITPPC` is exported (the devkitPro profile sets it).

## Build
```sh
make            # -> boot.dol
make clean
```

## Run on the Wii
Open the Homebrew Channel (so it's listening), then from this dir:
```sh
WIILOAD=tcp:<wii-ip> make run     # pushes boot.dol over the network
```
Or copy `boot.dol` + `meta.xml` to the SD card under `/apps/cpc-chat/`.

## Steps
1. **it lives** — boot, banner, exit on HOME  *(current)*
2. wifi — bring up network, show IP
3. reach Pluto — HTTP GET `/messages`
4. render — draw the channel
5. type — USB keyboard input
6. send — POST a message
7. polish — cadence, look, optional game list
