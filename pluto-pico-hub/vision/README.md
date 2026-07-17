# Kinect pose engine

`kinect_pose.py` turns the Kinect's body pose into directional control intent (UP / DOWN /
LEFT / RIGHT) for the console controller. It's a **separate process** from the hub: the hub
runs system `python3` (with freenect), while this needs `onnxruntime` + `numpy` in its own
venv. It talks to `bridges/kinect.py` only over HTTP (loopback), so it never opens the
Kinect directly and never contends for the device.

It runs MoveNet only while the bridge reports `capturing and not paused`, so the Play /
Pause / Off buttons control when the Pi pays for inference.

**Privacy:** frames are processed here, on the Pi, and never leave the box. Only derived
numbers (keypoints, the `context` text) are exposed. Don't add a path that ships frames off.

## Setup (on the Pi, one time)

The Pi is aarch64 / Python 3.13, where MediaPipe has no wheels — but `onnxruntime` does, and
MoveNet SinglePose Lightning runs on the A76 at ~39 FPS, plenty for real-time.

```sh
python3 -m venv venv                 # plain venv; this engine needs no system packages
venv/bin/pip install onnxruntime numpy
# MoveNet SinglePose Lightning (ONNX), ~9 MB -> movenet.onnx next to kinect_pose.py:
curl -L -o movenet.onnx \
  https://huggingface.co/Xenova/movenet-singlepose-lightning/resolve/main/onnx/model.onnx
```

## Run

```sh
venv/bin/python kinect_pose.py
```

Config via env (optional): `KINECT_BRIDGE_URL` (default `http://127.0.0.1:7730`),
`KINECT_POSE_MODEL` (default `./movenet.onnx`). Tuning constants (`CONF`, `EXT`) live at the
top of the script.

## What it emits

A context line per frame, e.g. `PERSON=0.55 DIR=UP WX=+0.42 WY=+0.18 [L dx=+0.10 dy=-1.60]`:
- `PERSON` — torso confidence (aim the sensor until this is solid).
- `DIR` — the classified direction of the extended arm (`neutral` = arm down; `no-ref` =
  shoulders not found). Drives the UI's **Movement** mode (body-relative).
- `WX WY` — the active wrist's ABSOLUTE position in the frame (0..1, screen-space), or `-`
  when no wrist is found. Drives the UI's **Zone** mode (3×3 grid). Shoulder-independent.
- `[which dx dy]` — active wrist and its position relative to the shoulder centre, in
  shoulder-width units (for tuning the thresholds).

The bridge returns this string on `GET /frame` as `context`; Pluto's Kinect source shows it
in the NE "Pose Log".
