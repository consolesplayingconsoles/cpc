"""
wiimote_aim.py -- the Wii Remote's IR dots -> a screen position. Pure math, no I/O.

The remote's camera reports up to 4 IR dots (x 0..1023, y 0..767, 1023 = "no dot").
With one emitter at each corner of the screen, the four dots are the screen's outline
as the camera sees it. The point the remote POINTS at is the middle of the camera's
image, so the aim is: where does the image centre land inside that outline?

  1. order the 4 dots as the outline's corners (top-left, top-right, bottom-right,
     bottom-left, in the camera's own image frame);
  2. a homography H maps the unit square onto the 4 dots; its inverse maps the image
     centre back into the square -> (u, v), the aim in the LED frame;
  3. calibration: the user aims at the picture's 4 real corners (the LEDs sit on the
     bezel, outside the picture), the 4 raw (u, v) are recorded, and a second
     homography maps them onto the unit square -> the aim on the picture itself.

Orientation/mirroring of the camera image never has to be known: the calibration
corners are recorded in the order top-left, top-right, bottom-right, bottom-left of
the PICTURE, so whatever the camera's axes do is absorbed by the second homography.

Python 3.6, stdlib only.
"""
import math

IR_W = 1024
IR_H = 768
IR_NONE = 1023                 # the "no dot" value the kernel reports
CENTER = (IR_W / 2.0, IR_H / 2.0)

UNIT_SQUARE = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]   # TL, TR, BR, BL


def valid_dots(raw):
    """raw = [(x, y)] * 4 from the kernel (1023 = no dot) -> only the real dots."""
    return [(x, y) for (x, y) in raw if x != IR_NONE and y != IR_NONE]


def order_corners(dots):
    """4 dots -> [TL, TR, BR, BL] in the image frame. Sorted by angle around their
    centre (a rotated outline keeps its cyclic order), then rotated so the first is
    the one nearest the image's top-left. Holds for a remote rolled up to ~45 degrees."""
    if len(dots) != 4:
        raise ValueError("need exactly 4 dots")
    cx = sum(p[0] for p in dots) / 4.0
    cy = sum(p[1] for p in dots) / 4.0
    ring = sorted(dots, key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
    first = min(range(4), key=lambda i: ring[i][0] + ring[i][1])
    return ring[first:] + ring[:first]


def _solve(a, b):
    """Solve a*x = b (n x n) by Gaussian elimination with partial pivoting."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            raise ValueError("degenerate points")
        m[col], m[piv] = m[piv], m[col]
        for r in range(col + 1, n):
            f = m[r][col] / m[col][col]
            for c in range(col, n + 1):
                m[r][c] -= f * m[col][c]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (m[r][n] - sum(m[r][c] * x[c] for c in range(r + 1, n))) / m[r][r]
    return x


def homography(src, dst):
    """The 3x3 homography (row-major list of 9, last = 1) taking the 4 src points to
    the 4 dst points."""
    a, b = [], []
    for (x, y), (u, v) in zip(src, dst):
        a.append([x, y, 1, 0, 0, 0, -x * u, -y * u])
        b.append(u)
        a.append([0, 0, 0, x, y, 1, -x * v, -y * v])
        b.append(v)
    h = _solve(a, b)
    return h + [1.0]


def apply(h, p):
    x, y = p
    w = h[6] * x + h[7] * y + h[8]
    if abs(w) < 1e-12:
        raise ValueError("point at infinity")
    return ((h[0] * x + h[1] * y + h[2]) / w, (h[3] * x + h[4] * y + h[5]) / w)


def invert(h):
    a, b, c, d, e, f, g, i, j = h
    det = a * (e * j - f * i) - b * (d * j - f * g) + c * (d * i - e * g)
    if abs(det) < 1e-12:
        raise ValueError("singular homography")
    return [(e * j - f * i) / det, (c * i - b * j) / det, (b * f - c * e) / det,
            (f * g - d * j) / det, (a * j - c * g) / det, (c * d - a * f) / det,
            (d * i - e * g) / det, (b * g - a * i) / det, (a * e - b * d) / det]


def raw_aim(dots4):
    """4 dots (any order) -> (u, v): where the image centre falls inside the outline,
    0..1 across and down the outline. Raises ValueError if the outline is degenerate."""
    corners = order_corners(dots4)
    h = homography(UNIT_SQUARE, corners)
    return apply(invert(h), CENTER)


def make_calibration(raw_corners):
    """The 4 raw (u, v) recorded while aiming at the picture's TL, TR, BR, BL corners
    -> the homography that maps a raw aim onto the picture (0..1, y down)."""
    if len(raw_corners) != 4:
        raise ValueError("need 4 corner samples")
    return homography(raw_corners, UNIT_SQUARE)


def to_axis(raw, calibration=None):
    """A raw (u, v) -> the drive axis (x, y): 0..1, 0.5 = centre, +y = UP, clamped.
    Without a calibration the raw aim is used as it is (orientation unknown)."""
    u, v = apply(calibration, raw) if calibration else raw
    x = min(1.0, max(0.0, u))
    y = min(1.0, max(0.0, 1.0 - v))
    return (x, y)


# ---- relative aim: an optical mouse made of the IR dots --------------------------------
# The absolute aim above needs all 4 dots in view (the camera sees them together in a
# fraction of the frames) and a calibration. A MOUSE needs neither: when the remote turns,
# every dot in the camera's view shifts together, so the pointer moves by how far the dots
# moved between two frames, whichever dots (1 to 4) are visible. The Wii Remote keeps a
# dot in the same slot while it tracks it, so each slot is compared with itself.
PX_TO_UNIT = 1.0 / 600.0      # camera pixels -> screen fraction, at a typical desk distance
MAX_STEP = 150                # a slot that jumps further than this changed to another dot


def _clamp01(v):
    return min(1.0, max(0.0, v))


class RelativePointer(object):
    """Pointer position (0..1, y up) integrated from the dots' movement. The virtual
    pointer stops at the screen edges, like a mouse cursor does."""

    def __init__(self, sensitivity=1.0, invert_x=False, invert_y=False):
        self.sensitivity = sensitivity
        self.invert_x = invert_x
        self.invert_y = invert_y
        self.prev = [None] * 4
        self.x = 0.5
        self.y_down = 0.5

    def update(self, slots):
        """slots: 4 entries, each (x, y) or None for "no dot". Returns (x, y), y up."""
        moves = []
        for cur, prv in zip(slots, self.prev):
            if cur is None or prv is None:
                continue
            dx, dy = cur[0] - prv[0], cur[1] - prv[1]
            if abs(dx) > MAX_STEP or abs(dy) > MAX_STEP:
                continue
            moves.append((dx, dy))
        self.prev = [tuple(s) if s is not None else None for s in slots]
        if moves:
            mdx = sum(m[0] for m in moves) / float(len(moves))
            mdy = sum(m[1] for m in moves) / float(len(moves))
            k = PX_TO_UNIT * self.sensitivity
            # Default: turning the remote right moves the dots left (so the pointer goes
            # right: -dx), and the camera's y runs up, so a dot moving down means the
            # remote turned up (pointer up = y_down decreasing: +dy). invert_* flips them.
            ax = mdx if self.invert_x else -mdx
            ay = -mdy if self.invert_y else mdy
            self.x = _clamp01(self.x + ax * k)
            self.y_down = _clamp01(self.y_down + ay * k)
        return (self.x, 1.0 - self.y_down)
