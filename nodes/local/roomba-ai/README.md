# roomba-ai

Firefox OS handset mounted on the roomba, carrying video and audio in both
directions between the roomba and the brain (laptop or Pi).

## Two planes

**Control** is the Firefox Remote Debugging Protocol, spoken over adb by
`pluto/api/modules/fxos/client.py`. You use it to install the media app, launch
it, eval JS inside it and read device state.

**Media** is a WebSocket held by the app on the handset, straight to the brain.
Frames and audio never travel over the control plane.

## First-time setup

The handset must be USB-tethered once, to switch its adb daemon to TCP:

1. On the handset: `Settings > Device information > More information >
   Developer`, set Remote debugging to `ADB and DevTools`. `ADB only` gives you
   a shell but no debugger socket.
2. Plug it in, confirm `adb devices` lists it.
3. Run `client.enable_tcpip()`. This also sets `persist.adb.tcp.port`, without
   which adbd reverts to USB on the next reboot, which is no good for a handset
   with no cable on it.
4. Unplug. From then on `client.connect_device(HOST_IP)` reaches it over wifi.

## Status

The control plane client is written and its protocol layer is tested. It has not
yet run against the handset, and the media app does not exist.

The aim is full senses on the handset: camera and mic in, screen and speaker out.
Screen and speaker are safe on any version. Camera and mic are not, and decide
the design:

- Before Firefox OS 1.4 the camera is the `mozCameras` API, reachable only by a
  CERTIFIED app, so a privileged app cannot have it.
- From 1.4 it is `getUserMedia`, which a privileged app can use with the
  `camera` and `audio-capture` permissions.

The handset reports adb serial `roamer2`, which is the original ZTE Open. That
model shipped 1.0 and went to 1.1 over the air, so it probably lands on the wrong
side of that line. Confirm before designing anything:

    adb shell getprop | grep -i -E "version|ro.product"

If it is below 1.4 there are three ways out, in order of effort: sideload the
media app as certified on a dev build, flash a community 1.4 or 2.x build for
this model, or fall back to the mounted camera and a mic on the Pico.
