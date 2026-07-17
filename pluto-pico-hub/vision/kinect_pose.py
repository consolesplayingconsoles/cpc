"""
kinect_pose.py -- Kinect body-pose engine (sibling of bridges/kinect.py).

A standalone process that turns the Kinect's RGB into directional control intent for the
console controller. It runs MoveNet SinglePose Lightning (ONNX Runtime) on each frame,
finds the active wrist relative to the shoulders, and classifies it as UP / DOWN / LEFT /
RIGHT / neutral. The result is pushed back to the kinect bridge as a text `context` line,
which rides along on the bridge's GET /frame for the UI's Pose Log.

WHY A SEPARATE PROCESS (not part of hub.py):
  hub.py runs the system python3 (with freenect). This engine needs onnxruntime + numpy,
  which live in their OWN venv so the hub's interpreter stays clean. It talks to the bridge
  only over HTTP (loopback) -- it does NOT open the Kinect itself, so no device contention.

LIFECYCLE (mirrors the Play / Pause / Off buttons):
  It polls the bridge state and only runs inference while `capturing and not paused`. So
  Pause and Off stop the heavy MoveNet work and hand the Pi's CPU back to its other jobs.

PRIVACY (hard rule): frames are processed here, on the Pi, and never leave the device. Only
  derived NUMBERS -- keypoints and the resulting context text -- are ever exposed. Do not add
  any path that ships raw frames off-box.

Config via env (all optional):
  KINECT_BRIDGE_URL   default http://127.0.0.1:7730
  KINECT_POSE_MODEL   default ./movenet.onnx (next to this file)  -- see README for the URL

Run:  <venv>/bin/python kinect_pose.py
"""
import os
import math
import json
import time
import base64
import urllib.request

import numpy as np
import onnxruntime as ort

BRIDGE = os.environ.get("KINECT_BRIDGE_URL", "http://127.0.0.1:7730")
MODEL = os.environ.get("KINECT_POSE_MODEL",
                       os.path.join(os.path.dirname(os.path.abspath(__file__)), "movenet.onnx"))

# MoveNet SinglePose Lightning: 192x192x3 int32 in, 17 (y,x,conf) keypoints out.
IN_SIZE = 192
# COCO keypoint indices we use.
L_SHO, R_SHO, L_WRI, R_WRI = 5, 6, 9, 10

CONF = 0.30   # per-keypoint confidence gate
EXT = 1.0     # a wrist must be >1 shoulder-width from the shoulder-centre to count as extended
PERIOD = 0.1  # seconds between inferences while active
IDLE = 0.3    # seconds between polls while off/paused


def _get(path):
    try:
        return json.load(urllib.request.urlopen(BRIDGE + path, timeout=2))
    except Exception:
        return None


def _post_context(text):
    try:
        urllib.request.urlopen(urllib.request.Request(
            BRIDGE + "/context",
            data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"}), timeout=2)
    except Exception:
        pass


def _classify(dx, dy):
    """Direction of an extended arm. dy is image-down, so negate it for 'up'."""
    if math.hypot(dx, dy) < EXT:
        return "neutral"
    ang = math.degrees(math.atan2(-dy, dx))
    if -45 <= ang < 45:
        return "RIGHT"
    if 45 <= ang < 135:
        return "UP"
    if ang >= 135 or ang < -135:
        return "LEFT"
    return "DOWN"


def _infer(session, rgb, w, h):
    """rgb: HxWx3 uint8 -> pose context string (numbers only)."""
    # Letterbox to a square so the person isn't stretched, then nearest-resize to 192.
    side = max(w, h)
    yo, xo = (side - h) // 2, (side - w) // 2
    sq = np.zeros((side, side, 3), np.uint8)
    sq[yo:yo + h, xo:xo + w] = rgb
    idx = (np.arange(IN_SIZE) * side // IN_SIZE)
    inp = sq[idx][:, idx].astype(np.int32)[None]
    kp = session.run(None, {"input": inp})[0][0, 0]   # (17, 3) = y, x, conf

    def real(i):
        y, x, c = kp[i]
        return (x * side - xo) / w, (y * side - yo) / h, c

    torso = float(np.mean([kp[i][2] for i in (L_SHO, R_SHO, 11, 12)]))
    lsx, lsy, lsc = real(L_SHO)
    rsx, rsy, rsc = real(R_SHO)
    lwx, lwy, lwc = real(L_WRI)
    rwx, rwy, rwc = real(R_WRI)

    d, which, dx, dy = "no-ref", "-", 0.0, 0.0
    if lsc > CONF and rsc > CONF:
        scx, scy = (lsx + rsx) / 2, (lsy + rsy) / 2
        sw = max(abs(lsx - rsx), 0.05)   # shoulder width = scale reference
        cand = []
        if lwc > CONF:
            cand.append(("L", (lwx - scx) / sw, (lwy - scy) / sw))
        if rwc > CONF:
            cand.append(("R", (rwx - scx) / sw, (rwy - scy) / sw))
        if cand:
            which, dx, dy = max(cand, key=lambda c: math.hypot(c[1], c[2]))
            d = _classify(dx, dy)

    # Absolute active-wrist position (screen-space, 0..1) for ZONE mode. Independent of the
    # shoulders (uses the higher-confidence wrist directly) so it still works when a raised
    # arm occludes them. "-" when no wrist is confidently found -> the UI reads it as neutral.
    zw = "WX=- WY=-"
    if max(lwc, rwc) > CONF:
        zwx, zwy = (lwx, lwy) if lwc >= rwc else (rwx, rwy)
        zw = "WX=%+.2f WY=%+.2f" % (zwx, zwy)
    return "PERSON=%.2f DIR=%s %s [%s dx=%+.2f dy=%+.2f]" % (torso, d, zw, which, dx, dy)


def main():
    if not os.path.exists(MODEL):
        raise SystemExit("model not found: %s  (see vision/README.md for the download)" % MODEL)
    session = ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    print("[kinect-pose] up -- bridge %s, model %s" % (BRIDGE, MODEL), flush=True)

    while True:
        st = _get("/frame")
        if not st or not st.get("capturing") or st.get("paused"):
            time.sleep(IDLE)                  # off/paused: no inference, Pi is free
            continue
        img = _get("/image")
        if not img or "data" not in img:
            time.sleep(PERIOD)
            continue
        w, h = img["w"], img["h"]
        rgb = np.frombuffer(base64.b64decode(img["data"]), dtype=np.uint8).reshape(h, w, 4)[:, :, :3]
        ctx = _infer(session, rgb, w, h)
        _post_context(ctx)
        print(ctx, flush=True)
        time.sleep(PERIOD)


if __name__ == "__main__":
    main()
