"""
AI mode: the listening session for the handset riding the roomba.

The handset only captures audio while a session is LIVE, and a session is live
only when both of these hold:

  1. AI mode was explicitly enabled. Off is the default and the resting state --
     nothing listens because a tab happened to be open.
  2. A keepalive arrived recently. Pluto stamps one while the Control panel is
     up, so a closed tab, a crashed Pluto or dropped wifi all expire the session
     on their own.

Two independent conditions on purpose: the toggle is the intent, the deadman is
the safety net for when intent cannot be withdrawn cleanly. This mirrors the
drive keepalive in pluto-drive/engine.py, which stamps last_seen the same way.

The handset polls state() and stops capturing the moment it reads back not-live,
so expiry does not depend on Pluto reaching the handset to tell it to stop.

Pure stdlib, no C extensions, Python 3.6 safe.
"""
import time
import threading
from collections import deque

# Seconds without a keepalive before a live session expires. Generous next to
# the 2.5s drive deadman: a stalled mic is not a runaway robot, and a handset on
# wifi at the far end of a flat deserves some slack before it drops the session.
DEFAULT_TIMEOUT = 15.0

# What the handset is being used for this session. The handset is a screen, a
# speaker and a mic on a roomba; the mode says what is driving them, and the
# page behaves differently for each rather than trying to be all of them at once.
#   chat    -- a person at the Pluto end: camera out, both mics live
#   ai      -- an agent at the Pluto end: Opus clips up, whole utterances
#   openemu -- a game streamed from the Mac: frames out, no mic needed
#   vlc     -- video streamed from the Mac
MODES = ("chat", "ai", "openemu", "vlc")
DEFAULT_MODE = "chat"

# Chunks held for the brain to collect. At ~3s of Opus per chunk this is about
# a minute and a half of audio and a couple of hundred KB, capped so a brain
# that never collects cannot grow the process without bound.
MAX_CHUNKS = 32

# The face frame the handset shows: one JPEG, replaced in place. Held in memory
# rather than written to disk on purpose -- this is a live video call between two
# devices on the LAN, not something to leave lying around in the repo.
_face = {"data": None, "at": 0.0, "seq": 0}

_lock = threading.Lock()
_state = {
    "enabled":   False,   # the explicit session toggle
    "mode":      "chat",  # see MODES
    "last_seen": 0.0,     # last keepalive
    "since":     0.0,     # when the current enable happened
    "timeout":   DEFAULT_TIMEOUT,
    "source":    None,    # who turned it on, for the audit line
    # What the handset should SHOW. Chat sends the Pluto end's camera, so it
    # defaults to the face stream; AR modes point it at the roomba's own camera
    # instead, since the handset's camera is not reachable from web content.
    "video":     None,
    "chunks_in": 0,       # lifetime count, survives draining
    "last_chunk_at": 0.0,
}
_chunks = deque(maxlen=MAX_CHUNKS)


def _live_locked(now):
    if not _state["enabled"]:
        return False
    return (now - _state["last_seen"]) <= _state["timeout"]


def enable(source=None, timeout=None, mode=None, video=None):
    """Turn AI mode on. The first keepalive is implicit, so a session is live
    immediately rather than waiting a poll interval to start."""
    now = time.time()
    with _lock:
        _state["enabled"] = True
        _state["since"] = now
        _state["last_seen"] = now
        _state["source"] = source
        if mode:
            # An unknown mode falls back rather than being stored: the handset
            # keys its whole behaviour off this string.
            _state["mode"] = mode if mode in MODES else DEFAULT_MODE
        _state["video"] = video or None
        if timeout:
            _state["timeout"] = float(timeout)
    return state()


def disable():
    """Turn AI mode off and drop anything not yet collected. Explicitly off is
    the resting state, and audio captured under a session nobody is watching has
    no reason to outlive it."""
    with _lock:
        _state["enabled"] = False
        _state["last_seen"] = 0.0
        _state["source"] = None
        _chunks.clear()
        # The face goes with the session: no lingering frame of somebody's living
        # room sitting in memory after the call ends.
        _face["data"] = None
        _face["at"] = 0.0
    return state()


def keepalive():
    """Stamp the session. A keepalive never STARTS one: without an explicit
    enable this is a no-op, so a stray keepalive cannot switch the mic on."""
    with _lock:
        if _state["enabled"]:
            _state["last_seen"] = time.time()
    return state()


def is_live():
    with _lock:
        return _live_locked(time.time())


def state():
    """What the handset polls. `live` is the only field it needs to act on."""
    now = time.time()
    with _lock:
        live = _live_locked(now)
        return {
            "live":      live,
            "enabled":   _state["enabled"],
            "mode":      _state["mode"],
            "video":     _state["video"],
            "face_at":   _face["at"],
            "timeout":   _state["timeout"],
            "expires_in": max(0.0, round(_state["timeout"] - (now - _state["last_seen"]), 1))
                          if _state["enabled"] else 0.0,
            "since":     _state["since"],
            "source":    _state["source"],
            "pending":   len(_chunks),
            "chunks_in": _state["chunks_in"],
            "last_chunk_at": _state["last_chunk_at"],
        }


def push_chunk(data, content_type="audio/ogg"):
    """
    Take a chunk of captured audio from the handset.

    Refused unless the session is live: the check is here rather than only in
    the handset page, so audio cannot be posted in by anything that simply
    ignores state(). Returns None when refused.
    """
    now = time.time()
    with _lock:
        if not _live_locked(now):
            return None
        _state["chunks_in"] += 1
        _state["last_chunk_at"] = now
        seq = _state["chunks_in"]
        _chunks.append({"seq": seq, "at": now, "type": content_type, "data": data})
    return seq


def take_chunks():
    """Drain everything captured so far, oldest first, for the brain."""
    with _lock:
        out = list(_chunks)
        _chunks.clear()
    return out


def push_face(data):
    """
    Take the current face frame (JPEG) from whoever is on the Pluto end.

    Refused outside a live session, same as audio: one gate, both directions.
    """
    with _lock:
        if not _live_locked(time.time()):
            return None
        _face["data"] = data
        _face["at"] = time.time()
        _face["seq"] += 1
        return _face["seq"]


def face():
    """The latest face frame as (data, seq, at), or (None, seq, 0.0)."""
    with _lock:
        return _face["data"], _face["seq"], _face["at"]


def pop_chunk(max_stale=None):
    """
    Take the oldest captured chunk, or None.

    With max_stale set, clips older than that many seconds are DROPPED rather
    than returned. Listening to a room is live audio, not a playlist: once a
    backlog builds, every queued clip plays in real time and the listener falls
    permanently further behind. Throwing the stale ones away keeps what you hear
    close to what is being said now.
    """
    now = time.time()
    with _lock:
        while _chunks:
            chunk = _chunks.popleft()
            if max_stale is None or (now - chunk["at"]) <= max_stale:
                return chunk
        return None


# ── live PCM (chat mode) ────────────────────────────────────────────────────
# Chat is a conversation, so the handset streams raw PCM continuously instead of
# uploading finished Opus clips. Clips are right for an agent, which wants whole
# utterances to transcribe; they are wrong for talking to someone, because the
# clip length is a hard floor on latency and any backlog plays out in real time.
#
# Format is fixed and dumb on purpose: 16 kHz, mono, signed 16-bit little-endian.
# The handset resamples to it, the server never transcodes, and a WAV header in
# front of the stream makes it playable by a plain <audio> element.
PCM_RATE = 16000
PCM_CHANNELS = 1
PCM_WIDTH = 2

# Per-reader queues. A reader that stops collecting is dropped rather than
# allowed to grow: this is live audio, and a stalled listener wants the present,
# not a recording of the past.
_pcm_readers = []
_PCM_QUEUE_MAX = 64          # ~8s at 128ms per push

# The other direction: Pluto's mic -> the handset's speaker, so you can talk back
# into the room. Same format, same drop-behind rule, separate queues.
_voice_readers = []


def wav_header(data_len=0x7FFFFFFF):
    """A WAV header with a deliberately huge length: the stream never ends, and
    every player treats an over-long declared size as "keep going"."""
    import struct
    byte_rate = PCM_RATE * PCM_CHANNELS * PCM_WIDTH
    return (b"RIFF" + struct.pack("<I", data_len + 36) + b"WAVEfmt " +
            struct.pack("<IHHIIHH", 16, 1, PCM_CHANNELS, PCM_RATE, byte_rate,
                        PCM_CHANNELS * PCM_WIDTH, PCM_WIDTH * 8) +
            b"data" + struct.pack("<I", data_len))


def push_pcm(data):
    """Take a block of PCM from the handset. Refused outside a live session."""
    with _lock:
        if not _live_locked(time.time()):
            return False
        for q in _pcm_readers:
            if len(q) >= _PCM_QUEUE_MAX:
                q.clear()        # listener fell behind: skip it forward to live
            q.append(data)
        return True


def add_pcm_reader():
    q = deque()
    with _lock:
        _pcm_readers.append(q)
    return q


def drop_pcm_reader(q):
    with _lock:
        if q in _pcm_readers:
            _pcm_readers.remove(q)


def push_voice(data):
    """Take a block of PCM from the Pluto end, bound for the handset's speaker."""
    with _lock:
        if not _live_locked(time.time()):
            return False
        for q in _voice_readers:
            if len(q) >= _PCM_QUEUE_MAX:
                q.clear()
            q.append(data)
        return True


def add_voice_reader():
    q = deque()
    with _lock:
        _voice_readers.append(q)
    return q


def drop_voice_reader(q):
    with _lock:
        if q in _voice_readers:
            _voice_readers.remove(q)
