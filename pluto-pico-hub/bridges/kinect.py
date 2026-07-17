"""
kinect.py -- Xbox Kinect v1 input bridge.

Streams raw depth, RGB, and skeletal data from an attached Kinect to Pluto over HTTP.
No control mappings yet; this is raw sensor data for visualization and future binding.
"""
import threading
import json
import time
import base64
import os
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    import freenect
except ImportError as e:
    freenect = None
    print(f"  [kinect-import-debug] ImportError: {e}", flush=True)


class KinectFrame:
    """Current Kinect frame (depth, RGB, skeleton)."""
    def __init__(self):
        self.depth = None
        self.rgb = None
        self.skeleton = {}
        self.timestamp = 0
        self.lock = threading.Lock()
        self.hand_left = False
        self.hand_right = False
        # Capture lifecycle, mirroring the HDMI capturer: nothing streams until Pluto
        # starts it (GO), so the sensor sits idle -- "no signal" -- by default and never
        # spams the pico unrequested. Stop (end) clears the last frame back to no-signal.
        #   capturing = frames flow (Play);  paused = warm but the pose engine idles (WAIT).
        # The heavy pose inference lives in a sibling engine that reads these flags off
        # /frame and only runs while capturing and not paused -- so Pause/Off hand the Pi's
        # CPU back to its other jobs. `context` is the engine's latest text (PERSON/DIR...).
        self.capturing = False
        self.paused = False
        self.context = ""
        self.context_ts = 0

    def set_capture(self, on):
        with self.lock:
            self.capturing = bool(on)
            self.paused = False          # start/stop always clears pause
            if not self.capturing:
                self.hand_left = False
                self.hand_right = False
                self.depth = None
                self.rgb = None
                self.context = ""

    def set_paused(self, on):
        with self.lock:
            self.paused = bool(on)

    def set_context(self, text):
        with self.lock:
            self.context = str(text or "")
            self.context_ts = time.time()

    def update(self, depth=None, rgb=None, skeleton=None):
        with self.lock:
            if not self.capturing:
                return                      # idle: drop frames so /frame reports no signal
            if depth is not None:
                self.depth = depth.tolist() if hasattr(depth, 'tolist') else depth
                self._detect_hands()
            if rgb is not None:
                self.rgb = rgb.tolist() if hasattr(rgb, 'tolist') else rgb
            if skeleton is not None:
                self.skeleton = skeleton
            self.timestamp = time.time()

    def _detect_hands(self):
        """Detect hands in left/right halves: look for foreground (closer than mean-2*std)."""
        if not self.depth:
            self.hand_left = False
            self.hand_right = False
            return

        try:
            import numpy
            depth_array = numpy.array(self.depth, dtype=numpy.uint16)
            h, w = depth_array.shape
            mid = w // 2

            # Foreground = significantly closer than background (80% of mean)
            mean = numpy.mean(depth_array)
            foreground_thresh = mean * 0.8

            # Left half: count foreground pixels
            left_half = depth_array[:, :mid]
            left_fg = numpy.count_nonzero(left_half < foreground_thresh)
            self.hand_left = bool(left_fg > 5)

            # Right half: count foreground pixels
            right_half = depth_array[:, mid:]
            right_fg = numpy.count_nonzero(right_half < foreground_thresh)
            self.hand_right = bool(right_fg > 5)
        except Exception as e:
            print(f"  [kinect] hand detection error: {e}", flush=True)
            self.hand_left = False
            self.hand_right = False

    def get_json(self):
        with self.lock:
            return {
                'timestamp': self.timestamp,
                'capturing': self.capturing,
                'paused': self.paused,
                'context': self.context,
                'depth': self.depth is not None,
                'rgb': self.rgb is not None,
                'skeleton': bool(self.skeleton),
                'hand_left': self.hand_left,
                'hand_right': self.hand_right,
            }


class PoseEngine:
    """On-demand manager for the sibling pose-inference process (vision/kinect_pose.py).

    The engine is NOT a daemon (nodes are on-demand + killable, never always-on). Pluto
    launches it when the Kinect source opens and on Play, and kills it on Stop. As a
    backstop for a forgotten Stop (tab closed, laptop asleep), Pluto heartbeats every 30s
    while the source is open; if a heartbeat lapses past TIMEOUT the watchdog kills the
    engine AND stops the capture, dropping the whole sensor back to idle.

    It runs the engine's OWN venv interpreter as a subprocess, so the hub's system python
    stays clean; the engine talks back to this bridge over loopback HTTP (never opens the
    Kinect itself). Missing venv/model is a soft no-op -- the bridge still serves frames.
    """
    TIMEOUT = 45.0   # seconds without a heartbeat -> operator walked away, kill (>1 missed 30s ping)

    def __init__(self, bridge_port, on_lapse=None):
        here = os.path.dirname(os.path.abspath(__file__))
        vroot = os.path.join(os.path.dirname(here), "vision")
        self.py = os.path.join(vroot, "venv", "bin", "python")
        self.script = os.path.join(vroot, "kinect_pose.py")
        self.cwd = vroot
        self.bridge_url = "http://127.0.0.1:%d" % bridge_port
        self.on_lapse = on_lapse          # called when the heartbeat watchdog fires (stop capture)
        self.proc = None
        self.last_ping = 0.0
        self.lock = threading.Lock()

    def _alive(self):
        return self.proc is not None and self.proc.poll() is None

    def ping(self):
        self.last_ping = time.time()

    def start(self):
        """Launch the engine if it isn't already running; always refreshes the heartbeat."""
        with self.lock:
            self.last_ping = time.time()
            if self._alive():
                return True
            if not (os.path.exists(self.py) and os.path.exists(self.script)):
                print("  [kinect] pose engine not set up (missing venv/script) -- skipping", flush=True)
                return False
            env = dict(os.environ, KINECT_BRIDGE_URL=self.bridge_url)
            try:
                self.proc = subprocess.Popen(
                    [self.py, self.script], cwd=self.cwd, env=env,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print("  [kinect] pose engine launched (pid %d)" % self.proc.pid, flush=True)
                return True
            except Exception as e:
                print("  [kinect] pose engine launch failed: %s" % e, flush=True)
                self.proc = None
                return False

    def stop(self):
        with self.lock:
            if self._alive():
                try:
                    self.proc.terminate()
                    try:
                        self.proc.wait(timeout=3)
                    except Exception:
                        self.proc.kill()
                    print("  [kinect] pose engine stopped", flush=True)
                except Exception:
                    pass
            self.proc = None

    def watchdog(self):
        """Kill the engine (and stop capture) if the operator's heartbeat lapses."""
        while True:
            time.sleep(5)
            if self._alive() and (time.time() - self.last_ping) > self.TIMEOUT:
                print("  [kinect] heartbeat lapsed (%.0fs) -> killing pose engine, stopping capture"
                      % (time.time() - self.last_ping), flush=True)
                self.stop()
                if self.on_lapse:
                    try:
                        self.on_lapse()
                    except Exception:
                        pass


class KinectHandler(BaseHTTPRequestHandler):
    """HTTP endpoint: GET /frame -> current Kinect frame metadata.
    POST /capture {action: start|stop} -> capture lifecycle (start = GO, stop = end).
    POST /engine {action: start|ping|stop} -> pose-engine lifecycle + heartbeat."""
    frame: KinectFrame = None
    engine: 'PoseEngine' = None

    def do_OPTIONS(self):
        # CORS preflight for the POST /capture the browser sends.
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        if self.path == '/capture':
            length = int(self.headers.get('Content-Length', 0) or 0)
            raw = self.rfile.read(length) if length else b''
            try:
                action = (json.loads(raw.decode() or '{}').get('action') or '').lower()
            except Exception:
                action = ''
            # start/go = capture on (clears pause -> resume-or-boot); pause = warm idle
            # (engine stops inferring); stop/end = off. Play's double duty (resume vs boot)
            # falls out naturally: start just clears pause and turns capturing on.
            if self.frame is not None:
                if action in ('start', 'go', 'resume'):
                    self.frame.set_capture(True)
                    if self.engine:            # Play launches (or re-launches after Stop) the engine
                        self.engine.start()
                elif action in ('pause', 'wait'):
                    self.frame.set_paused(True)  # engine stays up but idles (capturing-and-not-paused)
                elif action in ('stop', 'end'):
                    self.frame.set_capture(False)
                    if self.engine:            # Stop kills the engine -> nothing infers, Pi is free
                        self.engine.stop()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            f = self.frame
            self.wfile.write(json.dumps({'ok': True,
                'capturing': f.capturing if f else False,
                'paused': f.paused if f else False}).encode())
        elif self.path == '/context':
            # The sibling pose engine pushes its latest text line here; /frame returns it.
            length = int(self.headers.get('Content-Length', 0) or 0)
            raw = self.rfile.read(length) if length else b''
            try:
                text = json.loads(raw.decode() or '{}').get('text') or ''
            except Exception:
                text = ''
            if self.frame is not None:
                self.frame.set_context(text)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'ok': True}).encode())
        elif self.path == '/engine':
            # Pose-engine lifecycle, driven by the Kinect source in Pluto:
            #   start = source opened / Play (spawn if down);  ping = 30s heartbeat (keepalive);
            #   stop  = source closed / Stop (kill). The watchdog kills a forgotten engine
            #   when pings lapse. All actions are no-ops if the engine isn't set up.
            length = int(self.headers.get('Content-Length', 0) or 0)
            raw = self.rfile.read(length) if length else b''
            try:
                action = (json.loads(raw.decode() or '{}').get('action') or '').lower()
            except Exception:
                action = ''
            if self.engine is not None:
                if action == 'start':
                    self.engine.start()
                elif action == 'ping':
                    self.engine.ping()
                elif action == 'stop':
                    self.engine.stop()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'ok': True,
                'running': bool(self.engine and self.engine._alive())}).encode())
        else:
            self.send_response(404)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

    def do_GET(self):
        if self.path == '/frame':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            data = self.frame.get_json() if self.frame else {'error': 'no kinect'}
            self.wfile.write(json.dumps(data).encode())
        elif self.path == '/image':
            # Return current RGB frame as base64 JSON (width, height, RGBA data)
            if not self.frame or not self.frame.rgb:
                self.send_response(204)  # No content
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                return

            try:
                with self.frame.lock:
                    rgb = self.frame.rgb
                if rgb:
                    # Kinect captures 640x480 RGB frames
                    h, w = 480, 640
                    import numpy
                    rgb_array = numpy.array(rgb, dtype=numpy.uint8).reshape(h, w, 3)
                    # Canvas needs RGBA, so add alpha channel
                    rgba_array = numpy.zeros((h, w, 4), dtype=numpy.uint8)
                    rgba_array[:, :, :3] = rgb_array
                    rgba_array[:, :, 3] = 255  # Full opacity
                    rgba_bytes = rgba_array.tobytes()
                    b64 = base64.b64encode(rgba_bytes).decode()

                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    data = json.dumps({'w': w, 'h': h, 'data': b64})
                    self.wfile.write(data.encode())
                else:
                    self.send_response(204)
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
            except Exception as e:
                print(f"  [kinect] image error: {e}", flush=True)
                self.send_response(500)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
        elif self.path == '/debug':
            # Debug endpoint: depth statistics
            if not self.frame or not self.frame.depth:
                self.send_response(204)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                return

            try:
                import numpy
                with self.frame.lock:
                    depth = self.frame.depth
                depth_array = numpy.array(depth, dtype=numpy.uint16)
                stats = {
                    'shape': depth_array.shape,
                    'min': int(numpy.min(depth_array)),
                    'max': int(numpy.max(depth_array)),
                    'mean': float(numpy.mean(depth_array)),
                    'nonzero_count': int(numpy.count_nonzero(depth_array)),
                    'total_pixels': int(depth_array.size),
                }

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(stats).encode())
            except Exception as e:
                self.send_response(500)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
        elif self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b'kinect ok')
        else:
            self.send_response(404)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

    def log_message(self, format, *args):
        pass  # silence HTTP logs


class KinectBridge:
    """Bridge Kinect sensor data to Pluto."""
    def __init__(self, port=7732):
        if not freenect:
            print("  [kinect] libfreenect not available (install python3-freenect)")
            self.enabled = False
            return

        self.port = port
        self.frame = KinectFrame()
        self.running = False
        self.enabled = True
        # On-demand pose engine. If a heartbeat lapses, the watchdog kills the engine and
        # this callback drops capture back to idle too, so the sensor stops streaming.
        self.engine = PoseEngine(port, on_lapse=lambda: self.frame.set_capture(False))
        KinectHandler.frame = self.frame
        KinectHandler.engine = self.engine
        # Reap any stray engine from a previous hub run so we don't end up with two posting
        # context (last-writer-wins garbage). Best-effort; pkill may be absent.
        try:
            subprocess.run(["pkill", "-f", "kinect_pose.py"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

        # Try to open the device
        try:
            ctx = freenect.init()
            num = freenect.num_devices(ctx)
            if num > 0:
                dev = freenect.open_device(ctx, 0)
                try:
                    freenect.set_led(dev, freenect.LED_RED)
                except (AttributeError, Exception):
                    pass  # LED setting not available, continue anyway
                freenect.close_device(dev)
                freenect.shutdown(ctx)
                print(f"  [kinect] device found, listening on :{port}")
            else:
                freenect.shutdown(ctx)
                print(f"  [kinect] no devices found")
                self.enabled = False
        except Exception as e:
            print(f"  [kinect] device error: {e}")
            self.enabled = False

    def start(self):
        """Start Kinect stream and HTTP server."""
        if not self.enabled:
            return False

        self.running = True

        # Start HTTP server (separate thread)
        try:
            server = HTTPServer(('0.0.0.0', self.port), KinectHandler)
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            print(f"  [kinect] HTTP server started on :{self.port}", flush=True)
        except Exception as e:
            print(f"  [kinect] HTTP server error: {e}", flush=True)
            return False

        # Start Kinect reader (separate thread)
        try:
            reader_thread = threading.Thread(target=self._read_kinect, daemon=True)
            reader_thread.start()
            print(f"  [kinect] reader thread started", flush=True)
        except Exception as e:
            print(f"  [kinect] reader thread error: {e}", flush=True)
            return False

        # Start the pose-engine heartbeat watchdog (kills a forgotten engine).
        threading.Thread(target=self.engine.watchdog, daemon=True).start()

        return True

    def _read_kinect(self):
        """Read Kinect frames in a loop."""
        if not freenect:
            return

        try:
            ctx = freenect.init()
            dev = freenect.open_device(ctx, 0)

            freenect.set_depth_callback(dev, self._depth_callback)
            freenect.set_video_callback(dev, self._rgb_callback)
            freenect.start_depth(dev)
            freenect.start_video(dev)

            while self.running:
                if freenect.process_events(ctx) < 0:
                    break
                time.sleep(0.01)

            freenect.stop_depth(dev)
            freenect.stop_video(dev)
            freenect.close_device(dev)
            freenect.shutdown(ctx)
        except Exception as e:
            print(f"  [kinect] read error: {e}")

    def _depth_callback(self, dev, depth, timestamp):
        """Depth frame callback."""
        self.frame.update(depth=depth)

    def _rgb_callback(self, dev, rgb, timestamp):
        """RGB frame callback."""
        self.frame.update(rgb=rgb)

    def stop(self):
        """Stop reading frames."""
        self.running = False
