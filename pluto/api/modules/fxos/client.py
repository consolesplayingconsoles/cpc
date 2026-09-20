"""
Firefox OS handset client, spoken over the Firefox Remote Debugging Protocol.

The handset runs the Gecko debugger on a unix socket at
/data/local/debugger-socket. adb bridges that socket to a local TCP port
(`adb forward`), and everything above the bridge is plain RDP:

    <byteLength>:<json>

where byteLength counts UTF-8 bytes of the JSON payload. Every packet carries a
`from` field naming the actor that sent it. The protocol allows at most one
outstanding request per actor, so replies are matched by actor name. Unsolicited
notifications carry a `type` field; replies never do, which is how the two are
told apart.

Transport is deliberately split from discovery: connect() takes a host and port,
so the same client works against a USB-tethered handset (adb forward to
localhost) or one reached over the network (adb connect, or a forward set up
elsewhere).

Pure stdlib: socket, json, subprocess -- no C extensions, pip-18 compatible,
Python 3.6 safe.
"""
import json
import socket
import subprocess

DEVICE_SOCKET = "localfilesystem:/data/local/debugger-socket"
DEFAULT_PORT = 6000
TCPIP_PORT = 5555
DEFAULT_TIMEOUT = 10.0


class FxosError(Exception):
    """Any failure talking to the handset."""


class ProtocolError(FxosError):
    """The device sent something that is not valid RDP."""


class DeviceError(FxosError):
    """The device answered, but with an error packet."""

    def __init__(self, message, code=None, packet=None):
        FxosError.__init__(self, message)
        self.code = code
        self.packet = packet


# --- adb plumbing -----------------------------------------------------------

def _adb(args, timeout=15):
    cmd = ["adb"] + list(args)
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        out, err = proc.communicate(timeout=timeout)
    except OSError as exc:
        raise FxosError("adb not found on PATH: %s" % exc)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise FxosError("adb %s timed out" % " ".join(args))
    if proc.returncode != 0:
        detail = err.decode("utf-8", "replace").strip() or "exit %d" % proc.returncode
        raise FxosError("adb %s: %s" % (" ".join(args), detail))
    return out.decode("utf-8", "replace")


def list_devices():
    """Attached devices as [{"serial": ..., "state": ...}]."""
    out = _adb(["devices"])
    devices = []
    for line in out.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            devices.append({"serial": parts[0], "state": parts[1]})
    return devices


def enable_tcpip(port=TCPIP_PORT, serial=None, persist=True):
    """
    Switch the handset's adb daemon to TCP, so it can be reached over wifi.

    Run this once while the handset is still USB-tethered. `persist` also sets
    persist.adb.tcp.port, without which stock adbd reverts to USB on reboot --
    which matters for a handset that is going to ride the roomba with no cable
    on it.
    """
    prefix = ["-s", serial] if serial else []
    if persist:
        try:
            _adb(prefix + ["shell", "setprop", "persist.adb.tcp.port", str(port)])
        except FxosError:
            pass  # non-fatal: tcpip still works until the next reboot
    _adb(prefix + ["tcpip", str(port)], timeout=20)
    return port


def connect_device(host, port=TCPIP_PORT):
    """Attach adb to a handset over the network. Returns its adb serial."""
    out = _adb(["connect", "%s:%d" % (host, port)], timeout=20)
    if "unable to connect" in out.lower() or "failed" in out.lower():
        raise FxosError("adb connect %s:%d: %s" % (host, port, out.strip()))
    return "%s:%d" % (host, port)


def forward(port=DEFAULT_PORT, serial=None):
    """
    Point a local TCP port at the handset's debugger socket.

    Some builds expose the debugger on a plain TCP port instead of the unix
    socket, so fall back to a straight tcp forward.
    """
    prefix = ["-s", serial] if serial else []
    try:
        _adb(prefix + ["forward", "tcp:%d" % port, DEVICE_SOCKET])
    except FxosError:
        _adb(prefix + ["forward", "tcp:%d" % port, "tcp:%d" % port])
    return port


# --- protocol ---------------------------------------------------------------

class Device(object):
    """
    A connected handset. Not thread-safe: one request is in flight at a time,
    so callers that share an instance across threads must serialise themselves.
    """

    def __init__(self, sock, timeout=DEFAULT_TIMEOUT):
        self._sock = sock
        self._sock.settimeout(timeout)
        self._buffer = b""
        self._events = []
        self.root = self._read_packet()

    # -- framing --

    def _read_packet(self):
        while True:
            colon = self._buffer.find(b":")
            if colon != -1:
                head = self._buffer[:colon]
                if not head.isdigit():
                    raise ProtocolError("bad length prefix: %r" % head[:40])
                length = int(head)
                start = colon + 1
                if len(self._buffer) >= start + length:
                    body = self._buffer[start:start + length]
                    self._buffer = self._buffer[start + length:]
                    try:
                        return json.loads(body.decode("utf-8"))
                    except ValueError as exc:
                        raise ProtocolError("bad JSON packet: %s" % exc)
            elif len(self._buffer) > 20:
                # A length prefix is never this long; the stream is not RDP.
                raise ProtocolError("no length prefix in stream")

            try:
                chunk = self._sock.recv(8192)
            except socket.timeout:
                raise FxosError("timed out waiting for the handset")
            if not chunk:
                raise FxosError("handset closed the connection")
            self._buffer += chunk

    def _write_packet(self, packet):
        body = json.dumps(packet).encode("utf-8")
        self._sock.sendall(str(len(body)).encode("ascii") + b":" + body)

    # -- requests --

    def request(self, packet):
        """
        Send a packet and return the reply from the actor it is addressed to.

        Notifications that arrive while waiting are stashed and can be drained
        with take_events().
        """
        actor = packet.get("to")
        if not actor:
            raise ValueError("packet has no `to` actor")
        self._write_packet(packet)

        while True:
            reply = self._read_packet()
            if reply.get("from") != actor or "type" in reply:
                self._events.append(reply)
                continue
            if "error" in reply:
                raise DeviceError(
                    reply.get("message") or reply["error"],
                    code=reply["error"],
                    packet=reply,
                )
            return reply

    def take_events(self):
        """Drain notifications received so far."""
        events, self._events = self._events, []
        return events

    # -- convenience --

    def list_tabs(self):
        """Browser tabs, and on Firefox OS the running app frames."""
        return self.request({"to": "root", "type": "listTabs"}).get("tabs", [])

    def _webapps_actor(self):
        actor = self.root.get("webappsActor")
        if not actor:
            raise FxosError("handset exposes no webapps actor")
        return actor

    def list_apps(self):
        """Every app installed on the handset."""
        reply = self.request({"to": self._webapps_actor(), "type": "getAll"})
        return reply.get("apps", [])

    def list_running_apps(self):
        """Manifest URLs of the apps currently running."""
        reply = self.request({"to": self._webapps_actor(), "type": "listRunningApps"})
        return reply.get("apps", [])

    def close(self):
        try:
            self._sock.close()
        except OSError:
            pass


def connect(host="127.0.0.1", port=DEFAULT_PORT, timeout=DEFAULT_TIMEOUT,
            setup_forward=True, serial=None):
    """
    Connect to a handset and complete the RDP handshake.

    setup_forward runs `adb forward` first, which is what you want for a
    USB-tethered handset. Pass False when the port already points at a device
    (a forward set up elsewhere, or a handset reached over the network).
    """
    if setup_forward:
        devices = [d for d in list_devices() if d["state"] == "device"]
        if not devices:
            raise FxosError(
                "no handset in `device` state -- check the cable, and set "
                "Remote debugging to 'ADB and DevTools' on the handset"
            )
        forward(port, serial=serial)

    try:
        sock = socket.create_connection((host, port), timeout)
    except OSError as exc:
        raise FxosError("cannot reach %s:%d: %s" % (host, port, exc))
    return Device(sock, timeout=timeout)
