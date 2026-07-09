"""
kinect.py -- Xbox Kinect v1 input bridge.

Streams raw depth, RGB, and skeletal data from an attached Kinect to Pluto over HTTP.
No control mappings yet; this is raw sensor data for visualization and future binding.
"""
import threading
import json
import time
import base64
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
        self.capturing = False

    def set_capture(self, on):
        with self.lock:
            self.capturing = bool(on)
            if not self.capturing:
                self.hand_left = False
                self.hand_right = False
                self.depth = None
                self.rgb = None

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
                'depth': self.depth is not None,
                'rgb': self.rgb is not None,
                'skeleton': bool(self.skeleton),
                'hand_left': self.hand_left,
                'hand_right': self.hand_right,
            }


class KinectHandler(BaseHTTPRequestHandler):
    """HTTP endpoint: GET /frame -> current Kinect frame metadata.
    POST /capture {action: start|stop} -> capture lifecycle (start = GO, stop = end)."""
    frame: KinectFrame = None

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
            # start/go turns capture on; stop/end turns it off. Pause (WAIT) is a client
            # concern (keep streaming, just stop driving), so the bridge ignores it here.
            if self.frame is not None:
                if action in ('start', 'go', 'resume'):
                    self.frame.set_capture(True)
                elif action in ('stop', 'end'):
                    self.frame.set_capture(False)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            capturing = self.frame.capturing if self.frame else False
            self.wfile.write(json.dumps({'ok': True, 'capturing': capturing}).encode())
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
        KinectHandler.frame = self.frame

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
