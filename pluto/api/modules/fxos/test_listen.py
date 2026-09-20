"""Session semantics for AI mode. Run: python3 test_listen.py"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from modules.fxos import listen


def reset():
    listen.disable()
    listen._state["timeout"] = listen.DEFAULT_TIMEOUT


def test_off_by_default():
    reset()
    assert listen.is_live() is False
    assert listen.state()["enabled"] is False


def test_keepalive_alone_cannot_start_a_session():
    """A stray keepalive must never switch the mic on."""
    reset()
    listen.keepalive()
    assert listen.is_live() is False


def test_enable_is_live_immediately():
    reset()
    listen.enable(source="test")
    assert listen.is_live() is True
    assert listen.state()["source"] == "test"


def test_session_expires_without_keepalive():
    reset()
    listen.enable(source="test", timeout=0.3)
    assert listen.is_live() is True
    time.sleep(0.45)
    assert listen.is_live() is False, "session should have expired"
    assert listen.state()["enabled"] is True, "toggle stays on; only the session went stale"


def test_keepalive_holds_the_session_open():
    reset()
    listen.enable(source="test", timeout=0.3)
    for _ in range(3):
        time.sleep(0.15)
        listen.keepalive()
    assert listen.is_live() is True


def test_chunks_refused_unless_live():
    reset()
    assert listen.push_chunk(b"nope") is None, "audio accepted while off"
    listen.enable(source="test", timeout=0.3)
    assert listen.push_chunk(b"yes") == 1
    time.sleep(0.45)
    assert listen.push_chunk(b"stale") is None, "audio accepted after expiry"


def test_disable_drops_pending_audio():
    reset()
    listen.enable(source="test")
    listen.push_chunk(b"one")
    listen.push_chunk(b"two")
    assert listen.state()["pending"] == 2
    listen.disable()
    assert listen.state()["pending"] == 0, "audio outlived its session"


def test_take_chunks_drains_in_order():
    reset()
    listen.enable(source="test")
    listen.push_chunk(b"a")
    listen.push_chunk(b"b")
    got = listen.take_chunks()
    assert [c["data"] for c in got] == [b"a", b"b"]
    assert listen.take_chunks() == []


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("  PASS  %s" % name)
            except AssertionError as exc:
                failed += 1
                print("  FAIL  %s: %s" % (name, exc))
    print("\n%s" % ("ALL PASSED" if not failed else "%d FAILED" % failed))
    sys.exit(1 if failed else 0)
